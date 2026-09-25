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
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Iterable

from .protocol import ContainmentDecision

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


@dataclass(frozen=True)
class Attestation:
    """One containment decision, fixed in a chain."""

    seq: int
    recorded_ms: int
    decision: ContainmentDecision
    prev_digest: str
    digest: str

    def record_body(self) -> dict[str, Any]:
        """The digested portion. Excludes `digest` itself, by definition."""
        return {
            "seq": self.seq,
            "recorded_ms": self.recorded_ms,
            **self.decision.as_dict(),
        }

    def as_dict(self) -> dict[str, Any]:
        return {**self.record_body(), "prev_digest": self.prev_digest, "digest": self.digest}


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

    def __init__(self, *, clock=None) -> None:
        self._clock = clock or (lambda: int(time.time() * 1000))
        self._entries: list[Attestation] = []

    # -- writing ------------------------------------------------------------

    @property
    def head(self) -> str:
        return self._entries[-1].digest if self._entries else GENESIS

    def record(self, decision: ContainmentDecision) -> Attestation:
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
        """
        prev = expected_prev
        count = 0
        for offset, record in enumerate(records):
            index = start_seq + offset
            count += 1
            body = {k: v for k, v in record.items() if k not in {"prev_digest", "digest"}}
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
            self.export(), expected_head=self.head, expected_entries=len(self)
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
