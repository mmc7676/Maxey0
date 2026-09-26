"""Hash-chained containment evidence, verifiable without the enforcement engine.

This is the module that makes the containment claim falsifiable. Every decision
a `ContainmentProvider` makes is appended as an `Attestation` whose digest
covers both the record and the digest before it. Breaking the chain — editing a
decision, deleting an inconvenient denial, reordering events — changes every
subsequent digest, and `verify()` reports exactly where.

The verifier needs no knowledge of how decisions are made. It recomputes digests
from the published records alone. So a third party can check that the evidence
is intact and complete while the provider that produced it stays private:

    log.verify()          # anyone, offline, from exported records
    log.export()          # the records, as plain dicts

What the record answers: *what* was attempted, *where* (which SCW pair), *when*
(sequence and timestamp), *by whom* (agent SCW), and *which provider decided*.
What it does not answer is *how* the provider decided, which belongs in
documentation and research rather than in the wire format.

Persistence and signing (both opt-in; the default log is in-memory and
unsigned, exactly as before):

* ``MAXEY0_ATTESTATION_PATH`` names a JSONL file. Each record is appended as one
  line and fsynced before ``record()`` returns, and on construction the existing
  file is reloaded and verified. An in-memory log died with its process, so the
  evidence of a denial lasted exactly as long as the thing it was evidence
  about. A file that does not verify raises instead of being extended:
  appending to a broken chain would launder the break into history.
* ``MAXEY0_ATTESTATION_KEY_FILE`` names a key (64 hex characters, or at least 32
  raw bytes). Each record then carries ``sig`` = HMAC-SHA256(key, digest), a
  *sidecar* field outside the digested body, so digests and the chain are
  byte-identical with or without a key. An HMAC proves integrity to whoever
  holds the key: someone who can rewrite the file *and* recompute every digest
  still cannot forge the sigs. It does not prove public authorship -- every key
  holder can mint valid sigs, and a reader without the key learns nothing from
  them.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from dataclasses import dataclass, field, replace
from typing import Any, Iterable

from ..privacy import redact
from .protocol import ContainmentDecision, Operation

#: Digest of the empty chain. Every log starts here.
GENESIS = "0" * 64


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def compute_digest(record: dict[str, Any], prev_digest: str) -> str:
    """Digest over the record and its predecessor.

    Chaining on `prev_digest` is what makes deletion detectable. A log of
    independently-hashed records can lose an entry silently; a chained one
    cannot.
    """
    h = hashlib.sha256()
    h.update(prev_digest.encode("utf-8"))
    h.update(b"\x1f")
    h.update(_canonical(record).encode("utf-8"))
    return h.hexdigest()


#: Fields on an exported record that are not part of its digested body. `sig`
#: is here so that adding a signature never changes a digest; any extra field
#: not listed would be hashed and break every archived chain.
_UNDIGESTED = frozenset({"prev_digest", "digest", "sig"})


def sign_digest(key: bytes, digest: str) -> str:
    """HMAC-SHA256 over one record digest. Integrity for key holders only."""
    return hmac.new(key, digest.encode("utf-8"), hashlib.sha256).hexdigest()


def load_key(path: str | os.PathLike[str]) -> bytes:
    """Read a signing key: 64 hex characters, or at least 32 raw bytes.

    Fails closed. A missing, empty or short key raises rather than quietly
    producing an unsigned log, because an operator who configured signing and
    got none would be relying on evidence that was never protected.
    """
    raw = Path(path).read_bytes()
    text = raw.strip()
    if len(text) == 64:
        try:
            return bytes.fromhex(text.decode("ascii"))
        except (UnicodeDecodeError, ValueError):
            pass
    if len(raw) < 32:
        raise ValueError(
            f"attestation key {path} is too short ({len(raw)} bytes); "
            "use 32 random bytes or 64 hex characters"
        )
    return raw


@dataclass(frozen=True)
class Attestation:
    """One containment decision, fixed in a chain."""

    seq: int
    recorded_ms: int
    decision: ContainmentDecision
    prev_digest: str
    digest: str
    #: HMAC over `digest` when the log is keyed. Outside the digested body.
    sig: str | None = None

    def record_body(self) -> dict[str, Any]:
        """The digested portion. Excludes `digest` itself, by definition."""
        return {
            "seq": self.seq,
            "recorded_ms": self.recorded_ms,
            **self.decision.as_dict(),
        }

    def as_dict(self) -> dict[str, Any]:
        out = {**self.record_body(), "prev_digest": self.prev_digest, "digest": self.digest}
        if self.sig is not None:
            out["sig"] = self.sig
        return out


@dataclass
class VerificationResult:
    """Whether the evidence holds, and where it stops holding if it does not."""

    ok: bool
    entries: int
    head: str
    broken_at: int | None = None
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"ok": self.ok, "entries": self.entries, "head": self.head}
        if not self.ok:
            out["broken_at"] = self.broken_at
            out["reason"] = self.reason
        return out


class AttestationLog:
    """Append-only, hash-chained record of containment decisions."""

    def __init__(
        self,
        *,
        clock=None,
        path: str | os.PathLike[str] | None = None,
        key: bytes | None = None,
    ) -> None:
        self._clock = clock or (lambda: int(time.time() * 1000))
        self._entries: list[Attestation] = []
        if path is None:
            path = os.environ.get("MAXEY0_ATTESTATION_PATH") or None
        if key is None:
            key_file = os.environ.get("MAXEY0_ATTESTATION_KEY_FILE")
            if key_file:
                key = load_key(key_file)
        if key is not None and len(key) == 0:
            raise ValueError("attestation key is empty")
        self._key = key
        self._path = Path(path) if path is not None else None
        if self._path is not None:
            self._reload()

    def _reload(self) -> None:
        """Load and verify the persisted chain; raise if it does not hold.

        Fail closed: a torn line, an edited record or a missing sig (when keyed)
        stops construction. Continuing would append fresh, valid-looking
        records to a chain that no longer verifies.
        """
        assert self._path is not None
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            return
        records: list[dict[str, Any]] = []
        with self._path.open("r", encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                if not line.strip():
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"attestation log {self._path} line {lineno} is not JSON; "
                        "the chain cannot be trusted"
                    ) from exc
        result = self.verify_records(records, key=self._key)
        if not result.ok:
            raise ValueError(
                f"attestation log {self._path} does not verify at entry "
                f"{result.broken_at}: {result.reason}"
            )
        for r in records:
            decision = ContainmentDecision(
                allowed=r["allowed"],
                operation=Operation(r["operation"]),
                agent_scw=r["agent_scw"],
                target_scw=r["target_scw"],
                reason=r["reason"],
                provider=r["provider"],
                metadata=r.get("metadata", {}),
            )
            self._entries.append(Attestation(
                seq=r["seq"], recorded_ms=r["recorded_ms"], decision=decision,
                prev_digest=r["prev_digest"], digest=r["digest"], sig=r.get("sig"),
            ))

    # -- writing ------------------------------------------------------------

    @property
    def head(self) -> str:
        return self._entries[-1].digest if self._entries else GENESIS

    def record(self, decision: ContainmentDecision) -> Attestation:
        if self._path is not None:
            # A persisted log is a disk write, so it follows the rule every
            # other writer does: home paths shortened, secrets masked. The
            # redaction happens before the digest, so the chain in memory and
            # the chain on disk are the same chain and both verify.
            decision = replace(
                decision,
                reason=redact(decision.reason),
                metadata=redact(dict(decision.metadata)),
            )
        prev = self.head
        body = {
            "seq": len(self._entries),
            "recorded_ms": self._clock(),
            **decision.as_dict(),
        }
        entry = Attestation(
            seq=body["seq"],
            recorded_ms=body["recorded_ms"],
            decision=decision,
            prev_digest=prev,
            digest=compute_digest(body, prev),
        )
        if self._key is not None:
            entry = Attestation(
                seq=entry.seq, recorded_ms=entry.recorded_ms, decision=decision,
                prev_digest=prev, digest=entry.digest,
                sig=sign_digest(self._key, entry.digest),
            )
        if self._path is not None:
            # Written and fsynced before the entry joins the in-memory chain, so
            # a failed write raises without leaving memory ahead of disk.
            line = json.dumps(entry.as_dict(), sort_keys=True, separators=(",", ":"))
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
                fh.flush()
                os.fsync(fh.fileno())
        self._entries.append(entry)
        return entry

    # -- reading ------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._entries)

    def entries(self) -> tuple[Attestation, ...]:
        return tuple(self._entries)

    def export(self) -> list[dict[str, Any]]:
        """Plain records, suitable for publishing or independent checking."""
        return [e.as_dict() for e in self._entries]

    def denials(self) -> list[dict[str, Any]]:
        """Refused crossings — the evidence that containment did something."""
        return [e.as_dict() for e in self._entries if not e.decision.allowed]

    # -- verification -------------------------------------------------------

    @staticmethod
    def verify_records(
        records: Iterable[dict[str, Any]],
        *,
        expected_prev: str = GENESIS,
        start_seq: int = 0,
        expected_head: str | None = None,
        expected_entries: int | None = None,
        key: bytes | None = None,
    ) -> VerificationResult:
        """Verify exported records with no provider and no live system.

        This is the whole point: a reader who has the evidence but not the
        engine can still establish that the evidence is intact and unbroken.

        `expected_prev` and `start_seq` anchor a *segment*. Without them the
        verifier assumed every list began at GENESIS with seq 0, so any slice or
        filtered view — which is what the attestations tool hands out — was
        always reported as a broken chain. A segment is verifiable against the
        digest of the entry preceding it; what it cannot show on its own is that
        nothing was removed from the end, which `expected_head` on the caller's
        side is for.

        With `key`, every record must also carry a `sig` equal to
        HMAC-SHA256(key, digest). A missing sig fails: a keyed verifier that
        accepted unsigned records would let a forger simply drop the field.
        """
        prev = expected_prev
        count = 0
        for offset, record in enumerate(records):
            index = start_seq + offset
            count += 1
            body = {k: v for k, v in record.items() if k not in _UNDIGESTED}
            if record.get("prev_digest") != prev:
                return VerificationResult(
                    False, count, prev, index,
                    "prev_digest does not match the preceding entry; an entry was "
                    "removed, reordered, or inserted",
                )
            expected = compute_digest(body, prev)
            if record.get("digest") != expected:
                return VerificationResult(
                    False, count, prev, index, "digest does not match the record contents; an entry was edited",
                )
            if record.get("seq") != index:
                return VerificationResult(False, count, prev, index, "sequence number is out of order")
            if key is not None:
                sig = record.get("sig")
                if not isinstance(sig, str) or not hmac.compare_digest(sig, sign_digest(key, expected)):
                    return VerificationResult(
                        False, count, prev, index,
                        "signature missing or invalid; the record was not signed with this key",
                    )
            prev = expected
        # Truncation is the one edit a hash chain cannot see by itself: any
        # prefix of a valid chain is a valid chain, so deleting the most recent
        # denials verifies clean. A caller who knows what the head or the length
        # should be can say so, and that is what makes removal detectable.
        if expected_entries is not None and count != expected_entries:
            return VerificationResult(
                False, count, prev, count,
                f"expected {expected_entries} entries, got {count}; "
                f"entries were removed from the end",
            )
        if expected_head is not None and prev != expected_head:
            return VerificationResult(
                False, count, prev, count,
                "chain head does not match the expected head; entries were "
                "removed from the end",
            )
        return VerificationResult(True, count, prev)

    def verify(self) -> VerificationResult:
        return self.verify_records(
            self.export(), expected_head=self.head, expected_entries=len(self), key=self._key
        )

    def summary(self) -> dict[str, Any]:
        """Counts and chain head. Safe to publish; discloses no mechanism."""
        allowed = sum(1 for e in self._entries if e.decision.allowed)
        providers = sorted({e.decision.provider for e in self._entries})
        by_operation: dict[str, int] = {}
        for entry in self._entries:
            key = entry.decision.operation.value
            by_operation[key] = by_operation.get(key, 0) + 1
        return {
            "entries": len(self._entries),
            "allowed": allowed,
            "denied": len(self._entries) - allowed,
            "by_operation": by_operation,
            "providers": providers,
            "head": self.head,
            "chain_intact": self.verify().ok,
        }
