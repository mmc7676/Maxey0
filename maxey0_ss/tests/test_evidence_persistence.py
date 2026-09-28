"""Persisted, signed attestations and the standalone verifier.

The verifier restates every digest rule instead of importing the producers, so
these tests generate evidence with the *real* producers (AttestationLog, the
Gate journal, the scw_runtime EventLog) and check the verifier accepts it and
rejects a tampered copy. Drift between producer and verifier fails here.
"""
from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from maxey0_ss.containment import verify_cli
from maxey0_ss.containment.attestation import AttestationLog, load_key
from maxey0_ss.containment.protocol import ContainmentDecision, Operation

ROOT = Path(__file__).resolve().parents[2]
KEY_HEX = "11" * 32


def _decision(allowed: bool = True, **meta) -> ContainmentDecision:
    return ContainmentDecision(allowed, Operation.READ, "SCW1", "SCW2", "ok", "structural",
                               metadata=meta)


def _clock():
    n = iter(range(1000, 10**6))
    return lambda: next(n)


# -- persistence ------------------------------------------------------------


def test_default_log_stays_in_memory(tmp_path, monkeypatch):
    monkeypatch.delenv("MAXEY0_ATTESTATION_PATH", raising=False)
    monkeypatch.delenv("MAXEY0_ATTESTATION_KEY_FILE", raising=False)
    log = AttestationLog()
    log.record(_decision())
    assert "sig" not in log.export()[0]
    assert log._path is None


def test_env_path_persists_and_reloads(tmp_path, monkeypatch):
    path = tmp_path / "att.jsonl"
    monkeypatch.setenv("MAXEY0_ATTESTATION_PATH", str(path))
    log = AttestationLog(clock=_clock())
    log.record(_decision(model="mé"))
    log.record(_decision(False))
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2

    again = AttestationLog(clock=_clock())
    assert len(again) == 2 and again.head == log.head
    again.record(_decision())
    assert again.verify().ok
    assert AttestationLog.verify_records(
        [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]).ok


def test_broken_persisted_chain_fails_closed(tmp_path):
    path = tmp_path / "att.jsonl"
    log = AttestationLog(path=path)
    log.record(_decision())
    log.record(_decision())
    lines = path.read_text(encoding="utf-8").splitlines()
    rec = json.loads(lines[0])
    rec["allowed"] = False
    path.write_text(json.dumps(rec) + "\n" + lines[1] + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="does not verify"):
        AttestationLog(path=path)


def test_torn_line_fails_closed(tmp_path):
    path = tmp_path / "att.jsonl"
    AttestationLog(path=path).record(_decision())
    with path.open("a", encoding="utf-8") as fh:
        fh.write('{"seq": 1, "allo')
    with pytest.raises(ValueError, match="not JSON"):
        AttestationLog(path=path)


# -- signing ----------------------------------------------------------------


def test_signing_leaves_digests_unchanged(tmp_path):
    plain = AttestationLog(clock=_clock())
    signed = AttestationLog(clock=_clock(), key=bytes.fromhex(KEY_HEX))
    for log in (plain, signed):
        log.record(_decision())
        log.record(_decision(False))
    assert [e["digest"] for e in plain.export()] == [e["digest"] for e in signed.export()]
    assert all("sig" in e for e in signed.export())
    assert signed.verify().ok
    # Unkeyed verification still accepts a signed export.
    assert AttestationLog.verify_records(signed.export()).ok


def test_keyed_verify_rejects_wrong_or_missing_sig():
    key = bytes.fromhex(KEY_HEX)
    log = AttestationLog(key=key)
    log.record(_decision())
    records = log.export()
    assert not AttestationLog.verify_records(records, key=b"x" * 32).ok
    unsigned = [{k: v for k, v in r.items() if k != "sig"} for r in records]
    assert not AttestationLog.verify_records(unsigned, key=key).ok


def test_key_file_env_and_reload_requires_sigs(tmp_path, monkeypatch):
    keyfile = tmp_path / "k.hex"
    keyfile.write_text(KEY_HEX + "\n")
    path = tmp_path / "att.jsonl"
    AttestationLog(path=path).record(_decision())  # unsigned history
    monkeypatch.setenv("MAXEY0_ATTESTATION_KEY_FILE", str(keyfile))
    with pytest.raises(ValueError, match="signature"):
        AttestationLog(path=path)
    fresh = tmp_path / "signed.jsonl"
    AttestationLog(path=fresh).record(_decision())
    assert AttestationLog(path=fresh).verify().ok


def test_short_or_missing_key_fails_closed(tmp_path, monkeypatch):
    short = tmp_path / "short"
    short.write_bytes(b"abc")
    with pytest.raises(ValueError):
        load_key(short)
    monkeypatch.setenv("MAXEY0_ATTESTATION_KEY_FILE", str(tmp_path / "missing"))
    with pytest.raises(OSError):
        AttestationLog()
    raw = tmp_path / "raw"
    raw.write_bytes(b"k" * 40)
    assert load_key(raw) == b"k" * 40


# -- standalone verifier: attestations --------------------------------------


def _run_script(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "verify_records.py"), *args],
                          capture_output=True, text=True)


def test_verifier_accepts_real_attestations_json_and_jsonl(tmp_path):
    keyfile = tmp_path / "k.hex"
    keyfile.write_text(KEY_HEX)
    path = tmp_path / "att.jsonl"
    log = AttestationLog(path=path, key=bytes.fromhex(KEY_HEX))
    log.record(_decision(endpoint="https://x", note="☃"))
    log.record(_decision(False))
    exported = tmp_path / "export.json"
    exported.write_text(json.dumps({"records": log.export()}), encoding="utf-8")

    assert verify_cli.main(["attestation", str(path), "--key-file", str(keyfile),
                            "--expected-head", log.head]) == 0
    assert verify_cli.main(["attestation", str(exported), "--expected-entries", "2"]) == 0
    assert verify_cli.main(["attestation", str(exported), "--expected-entries", "3"]) == 1

    bad = tmp_path / "bad.jsonl"
    bad.write_text(path.read_text(encoding="utf-8").replace('"allowed":false', '"allowed":true'),
                   encoding="utf-8")
    proc = _run_script("attestation", str(bad))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert _run_script("attestation", str(path), "--key-file", str(keyfile)).returncode == 0
    wrong = tmp_path / "wrong.hex"
    wrong.write_text("22" * 32)
    assert _run_script("attestation", str(path), "--key-file", str(wrong)).returncode == 1
    assert _run_script("attestation", str(tmp_path / "nope.json")).returncode == 2


# -- standalone verifier: gate journal and context ledger -------------------


@pytest.fixture
def server_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("SCW_HOME", str(tmp_path / "scw"))
    monkeypatch.setenv("SCW_EVENT_LOG", str(tmp_path / "scw" / "events.jsonl"))
    monkeypatch.syspath_prepend(str(ROOT / "server" / "vendor"))
    monkeypatch.syspath_prepend(str(ROOT / "server"))
    return tmp_path / "scw"


def test_verifier_accepts_real_gate_journal(server_paths):
    journal = importlib.import_module("gate.journal")
    path = server_paths / "gate.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    for i in range(3):
        rec = journal.emit("gate.attempt", {"tool": "Read", "i": i, "t": "café"}, path=path)
        assert rec["persisted"]
    assert journal.verify(journal.read_all(path)["records"])["ok"]
    assert verify_cli.main(["gate", str(path)]) == 0
    assert _run_script("gate", str(path)).returncode == 0

    lines = path.read_text(encoding="utf-8").splitlines()
    rec = json.loads(lines[1])
    rec["actor"] = "someone-else"
    lines[1] = json.dumps(rec, ensure_ascii=False)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert verify_cli.main(["gate", str(path)]) == 1


def test_verifier_accepts_real_context_ledger(server_paths):
    events = importlib.import_module("scw_runtime.events")
    path = server_paths / "events.jsonl"
    first = events.EventLog(path, run_id="run-a")
    first.emit("window.init", "host", {"budget": 10})
    first.emit("scw.write", "loop:x", {"text": "héllo"})
    head = first.head()
    first.close()
    second = events.EventLog(path, run_id="run-b", prev_run=head)
    second.emit("window.init", "host", {"prev_run": head})
    second.close()

    events.verify_records(events.EventLog.load(path), strict_runs=True)
    assert verify_cli.main(["ledger", str(path), "--strict-runs"]) == 0

    # Reorder the runs: each run still verifies alone; only strict runs sees it.
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(lines[2:] + lines[:2]) + "\n", encoding="utf-8")
    assert verify_cli.main(["ledger", str(path)]) == 0
    assert verify_cli.main(["ledger", str(path), "--strict-runs"]) == 1
    lines = ["x"] + lines  # a torn line is a loss, not ignorable
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert verify_cli.main(["ledger", str(path)]) == 1


def test_concurrent_records_keep_one_chain_on_disk(tmp_path):
    """Threads recording at once used to fork the chain.

    record() read the head, fsynced, then appended; two threads between those
    steps chained to the same head. The file then refused to load, so the next
    restart failed closed and the evidence could only be kept by deleting it.
    """
    import threading

    from maxey0_ss.containment.attestation import AttestationLog
    from maxey0_ss.containment.protocol import ContainmentDecision, Operation

    decision = ContainmentDecision(
        allowed=True, operation=Operation.READ, agent_scw="SCW0",
        target_scw="SCW0", reason="concurrent", provider="test",
    )
    path = tmp_path / "attestations.jsonl"
    log = AttestationLog(path=path)
    start = threading.Barrier(8)

    def writer():
        start.wait()
        for _ in range(25):
            log.record(decision)

    threads = [threading.Thread(target=writer) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(log) == 200
    assert AttestationLog.verify_records(log.export()).ok
    reloaded = AttestationLog(path=path)
    assert len(reloaded) == 200 and reloaded.head == log.head


def test_concurrent_tool_calls_through_the_surface_keep_one_chain(tmp_path, monkeypatch):
    """The server's own execution path, not a bare log: tool handlers on threads.

    Drift anchors and measurements are attested, and the HTTP app runs tool
    handlers on a thread pool, so this is the path production traffic takes.
    """
    import threading

    from maxey0_ss.containment.attestation import AttestationLog
    from maxey0_ss.mcp_surface import build_surface

    path = tmp_path / "attestations.jsonl"
    monkeypatch.setenv("MAXEY0_ATTESTATION_PATH", str(path))
    surface = build_surface()
    tools = {t.name: t.handler for t in surface.tools}
    tools["maxey0-ss.scw.create"]({"scw_id": "SCW1", "task": "concurrency"})
    tools["maxey0-ss.scw.drift"]({"scw_id": "SCW1", "vector": [0.1, 0.2, 0.3], "anchor": True})
    start = threading.Barrier(8)

    def caller(n):
        start.wait()
        for i in range(10):
            tools["maxey0-ss.scw.drift"]({"scw_id": "SCW1", "vector": [0.1, 0.2 + i / 100, 0.3 + n / 100]})

    threads = [threading.Thread(target=caller, args=(n,)) for n in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    log = surface.system.context.isolation.log
    exported = log.export()
    assert len(exported) >= 81
    assert len({r["prev_digest"] for r in exported}) == len(exported), "duplicate predecessor"
    assert AttestationLog.verify_records(exported).ok
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(exported)
    reloaded = AttestationLog(path=path)
    assert reloaded.head == log.head and len(reloaded) == len(log)
