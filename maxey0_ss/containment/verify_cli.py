"""``maxey0-verify``: check Maxey0 evidence files with nothing but the stdlib.

A verifier that imports the system it is verifying proves less than it seems
to: a bug or a tampered install on the producing side is then shared by the
checking side. So this module deliberately imports nothing from ``maxey0_ss``
or ``server/`` and restates each digest rule instead. The rules are copied, not
shared, and the tests generate records with the real producers so that any
drift between the two shows up as a failing verification.

Three formats:

``attestation``  containment attestations (``maxey0_ss.containment.attestation``):
                 sha256(prev_digest + 0x1f + canonical(body)), ASCII-escaped
                 canonical JSON, optional HMAC ``sig`` sidecar.
``gate``         the plugin Gate journal (``server/gate/journal.py``): one chain
                 per *file*, digest over the record minus
                 ``digest``/``persisted``/``write_error``, unlocked
                 (``seq: null``) records are residue, torn lines are losses.
``ledger``       the Context plane ledger (``scw_runtime/events.py``): one chain
                 per ``run_id``, digest over the record minus ``digest``,
                 optional ``--strict-runs`` back-link check.

Exit status: 0 verified, 1 evidence does not verify, 2 the input could not be
read at all.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import sys
from pathlib import Path
from typing import Any

GENESIS = "0" * 64


# ---------------------------------------------------------------------------
# reading
# ---------------------------------------------------------------------------


def _read_jsonl(path: Path) -> tuple[list[dict], int]:
    """Records plus the count of unparseable lines (never silently dropped)."""
    records: list[dict] = []
    damaged = 0
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                damaged += 1
                continue
            if isinstance(value, dict):
                records.append(value)
            else:
                damaged += 1
    return records, damaged


def _read_attestations(path: Path) -> tuple[list[dict], int]:
    """An exported JSON document (list, or an object holding one) or JSONL."""
    text = path.read_text(encoding="utf-8")
    try:
        doc = json.loads(text)
    except json.JSONDecodeError:
        return _read_jsonl(path)
    if isinstance(doc, dict):
        for name in ("records", "attestations", "entries"):
            if isinstance(doc.get(name), list):
                return doc[name], 0
        # A single-line JSONL file parses as one record object.
        return [doc], 0
    if isinstance(doc, list):
        return doc, 0
    raise ValueError("attestation file is neither a JSON list nor JSONL")


def _load_key(path: str) -> bytes:
    """Same rule as the producer: 64 hex characters, else >= 32 raw bytes."""
    raw = Path(path).read_bytes()
    text = raw.strip()
    if len(text) == 64:
        try:
            return bytes.fromhex(text.decode("ascii"))
        except (UnicodeDecodeError, ValueError):
            pass
    if len(raw) < 32:
        raise ValueError(f"key file {path} is too short ({len(raw)} bytes)")
    return raw


# ---------------------------------------------------------------------------
# attestation
# ---------------------------------------------------------------------------


def _attestation_digest(body: dict, prev: str) -> str:
    h = hashlib.sha256()
    h.update(prev.encode("utf-8"))
    h.update(b"\x1f")
    # ensure_ascii left at its default: that is what the producer hashes.
    h.update(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return h.hexdigest()


def verify_attestations(
    records: list[dict],
    *,
    key: bytes | None = None,
    expected_prev: str = GENESIS,
    start_seq: int = 0,
    expected_head: str | None = None,
    expected_entries: int | None = None,
    damaged: int = 0,
) -> dict[str, Any]:
    prev = expected_prev
    count = 0
    signed = 0

    def fail(index: int, reason: str) -> dict[str, Any]:
        return {"ok": False, "entries": count, "head": prev, "broken_at": index,
                "reason": reason, "signed": signed, "damaged": damaged}

    for offset, record in enumerate(records):
        index = start_seq + offset
        count += 1
        if not isinstance(record, dict):
            return fail(index, "record is not a JSON object")
        body = {k: v for k, v in record.items() if k not in ("prev_digest", "digest", "sig")}
        if record.get("prev_digest") != prev:
            return fail(index, "prev_digest does not match the preceding entry")
        expected = _attestation_digest(body, prev)
        if record.get("digest") != expected:
            return fail(index, "digest does not match the record contents")
        if record.get("seq") != index:
            return fail(index, "sequence number is out of order")
        if key is not None:
            sig = record.get("sig")
            want = hmac.new(key, expected.encode("utf-8"), hashlib.sha256).hexdigest()
            if not isinstance(sig, str) or not hmac.compare_digest(sig, want):
                return fail(index, "signature missing or invalid")
            signed += 1
        prev = expected
    if expected_entries is not None and count != expected_entries:
        return fail(count, f"expected {expected_entries} entries, got {count}")
    if expected_head is not None and prev != expected_head:
        return fail(count, "chain head does not match the expected head")
    if damaged:
        return fail(count, f"{damaged} line(s) were unparseable")
    return {"ok": True, "entries": count, "head": prev, "signed": signed,
            "signatures_checked": key is not None, "damaged": 0}


# ---------------------------------------------------------------------------
# gate journal
# ---------------------------------------------------------------------------


def _canonical_unicode(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(obj: Any) -> str:
    return hashlib.sha256(_canonical_unicode(obj).encode("utf-8")).hexdigest()


def verify_gate(records: list[dict], damaged: int = 0) -> dict[str, Any]:
    chained = [r for r in records if r.get("seq") is not None]
    skipped = len(records) - len(chained)
    ordered = sorted(chained, key=lambda r: r.get("seq", 0))
    broken: list[dict] = []
    prev = GENESIS
    expected = 0
    for record in ordered:
        seq = record.get("seq")
        if seq != expected:
            broken.append({"seq": seq, "expected": expected, "why": "sequence gap"})
            break
        if record.get("prev") != prev:
            broken.append({"seq": seq, "why": "broken link"})
            break
        body = {k: v for k, v in record.items() if k not in ("digest", "persisted", "write_error")}
        if _sha(body) != record.get("digest"):
            broken.append({"seq": seq, "why": "digest mismatch"})
            break
        prev = record.get("digest", GENESIS)
        expected += 1
    return {
        "ok": (not broken) and damaged == 0,
        "chain_intact": not broken,
        "damaged": damaged,
        "records": len(records),
        "chained": len(chained),
        "verified_prefix": expected,
        "head": prev,
        "broken": broken,
        "unlocked_writes": skipped,
    }


# ---------------------------------------------------------------------------
# context ledger
# ---------------------------------------------------------------------------


def verify_ledger(records: list[dict], *, strict_runs: bool = False, damaged: int = 0) -> dict[str, Any]:
    prev = GENESIS
    expected_seq = 0
    run_id: Any = None
    seen = False
    last_head: dict | None = None
    length = 0
    runs = 0

    def fail(reason: str, record: dict) -> dict[str, Any]:
        return {"ok": False, "records": len(records), "runs": runs, "run_id": run_id,
                "seq": record.get("seq"), "reason": reason, "damaged": damaged}

    for record in records:
        if record.get("run_id") != run_id:
            if seen:
                last_head = {"run_id": run_id, "digest": prev, "length": length}
            run_id = record.get("run_id")
            prev, expected_seq, length = GENESIS, 0, 0
            seen = True
            runs += 1
            if strict_runs and last_head is not None:
                if record.get("type") != "window.init":
                    return fail("run does not begin with window.init", record)
                payload = record.get("payload")
                link = payload.get("prev_run") if isinstance(payload, dict) else None
                if link is None:
                    return fail("run declares no prev_run back-link", record)
                if link != last_head:
                    return fail("prev_run back-link does not match the preceding run", record)
        if record.get("seq") != expected_seq:
            return fail(f"sequence gap: expected {expected_seq}", record)
        if record.get("prev") != prev:
            return fail("broken link", record)
        body = {k: v for k, v in record.items() if k != "digest"}
        if _sha(body) != record.get("digest"):
            return fail("digest mismatch", record)
        prev = record["digest"]
        expected_seq += 1
        length += 1
    if damaged:
        return {"ok": False, "records": len(records), "runs": runs,
                "reason": f"{damaged} line(s) were unparseable", "damaged": damaged}
    return {"ok": True, "records": len(records), "runs": runs, "head": prev, "damaged": 0}


# ---------------------------------------------------------------------------
# command line
# ---------------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="maxey0-verify",
        description="Verify Maxey0 evidence files offline, with the standard library only.",
    )
    sub = ap.add_subparsers(dest="kind", required=True)
    a = sub.add_parser("attestation", help="exported containment attestations (JSON or JSONL)")
    a.add_argument("file")
    a.add_argument("--key-file", help="HMAC key; every record must then carry a valid sig")
    a.add_argument("--expected-head", help="digest the chain must end at (detects truncation)")
    a.add_argument("--expected-entries", type=int, help="number of entries expected")
    a.add_argument("--expected-prev", default=GENESIS, help="digest preceding a segment")
    a.add_argument("--start-seq", type=int, default=0, help="seq of a segment's first record")
    g = sub.add_parser("gate", help="the plugin Gate journal (gate.jsonl)")
    g.add_argument("file")
    le = sub.add_parser("ledger", help="the Context plane ledger (events.jsonl)")
    le.add_argument("file")
    le.add_argument("--strict-runs", action="store_true", help="require prev_run back-links")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    path = Path(args.file)
    try:
        if args.kind == "attestation":
            records, damaged = _read_attestations(path)
            key = _load_key(args.key_file) if args.key_file else None
            result = verify_attestations(
                records, key=key, expected_prev=args.expected_prev,
                start_seq=args.start_seq, expected_head=args.expected_head,
                expected_entries=args.expected_entries, damaged=damaged,
            )
        elif args.kind == "gate":
            records, damaged = _read_jsonl(path)
            result = verify_gate(records, damaged)
        else:
            records, damaged = _read_jsonl(path)
            result = verify_ledger(records, strict_runs=args.strict_runs, damaged=damaged)
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}))
        return 2
    result = {"kind": args.kind, **result}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
