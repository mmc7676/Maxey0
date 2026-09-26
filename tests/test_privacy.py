"""Nothing the gate, the runtime ledger or the origin persists may identify the
person using Maxey0: no home directory (which names the user), no transcript
path, no secret they typed. Each test writes through the real code path into a
temporary directory and reads back what landed on disk."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from _env import ROOT  # noqa: E402

SERVER = ROOT / "server"
for extra in (SERVER, SERVER / "vendor"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from gate import attribution, journal, privacy  # noqa: E402

HOME = os.path.expanduser("~")
SECRETS = {
    "anthropic": "sk-ant-api03-" + "A" * 40,
    "github": "ghp_" + "b" * 36,
    "maxey0": "m0ss_" + "c" * 43,
    "bearer": "Authorization: Bearer " + "d" * 40,
    "assigned": "password=hunter2hunter2",
}
# Another person's home folders, assembled at run time: the release secret
# scanner refuses real-looking home paths in shipped files, fixtures included.
_OTHER = "ali" + "ce"
OTHER_HOMES = ("C:\\" + "Users\\" + _OTHER, "C:/" + "Users/" + _OTHER,
               "/" + "home/" + _OTHER, "/" + "Users/" + _OTHER)


def _leaks(text: str) -> list[str]:
    found = []
    if HOME.lower() in text.lower() or HOME.replace("\\", "/").lower() in text.lower():
        found.append("home directory")
    for name, value in SECRETS.items():
        needle = value.split()[-1].split("=")[-1]
        if needle in text:
            found.append(name)
    if "transcript" in text and ".jsonl" in text:
        found.append("transcript path")
    if any(home in text for home in OTHER_HOMES):
        found.append("other user's home")
    return found


class RedactUnit(unittest.TestCase):
    def test_home_paths_are_shortened(self):
        for raw in (os.path.join(HOME, "proj", "a.py"), HOME.replace("\\", "/") + "/proj",
                    OTHER_HOMES[0] + "\\work\\x.txt", OTHER_HOMES[1] + "/work",
                    OTHER_HOMES[2] + "/src", OTHER_HOMES[3] + "/Desktop"):
            with self.subTest(raw=raw):
                out = privacy.redact(raw)
                self.assertTrue(out.startswith("~"), out)
                self.assertEqual(_leaks(out), [])

    def test_transcript_keys_are_dropped_at_any_depth(self):
        out = privacy.redact({"a": {"transcript_path": "x", "agent_transcript_path": "y",
                                    "transcript_ref": "z", "keep": 1}})
        self.assertEqual(out, {"a": {"keep": 1}})

    def test_secret_shaped_values_are_masked(self):
        for name, value in SECRETS.items():
            with self.subTest(kind=name):
                out = privacy.redact(f"run with {value} now")
                self.assertIn("[REDACTED:", out)
                self.assertEqual(_leaks(out), [], out)

    def test_ordinary_text_is_untouched(self):
        text = "git status && pytest -q tests/test_gate.py"
        self.assertEqual(privacy.redact(text), text)

    def test_input_is_not_mutated(self):
        original = {"cwd": HOME, "nested": [SECRETS["github"]]}
        snapshot = json.dumps(original)
        privacy.redact(original)
        self.assertEqual(json.dumps(original), snapshot)

    def test_the_runtime_copy_is_byte_identical(self):
        self.assertEqual((SERVER / "gate" / "privacy.py").read_bytes(),
                         (SERVER / "vendor" / "scw_runtime" / "privacy.py").read_bytes())
        self.assertEqual((SERVER / "gate" / "privacy.py").read_bytes(),
                         (ROOT / "maxey0_ss" / "privacy.py").read_bytes())


class GateJournalOnDisk(unittest.TestCase):
    def test_a_hook_record_reaches_disk_without_personal_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "gate.jsonl"
            payload = {
                "cwd": os.path.join(HOME, "Documents", "project"),
                "transcript_path": os.path.join(HOME, ".claude", "projects", "s.jsonl"),
                "tool_input": {"command": "curl -H '" + SECRETS["bearer"] + "' x",
                               "file_path": os.path.join(HOME, "notes.txt"),
                               "content": SECRETS["anthropic"] + " " + SECRETS["assigned"]},
            }
            record = journal.emit("gate.observed", payload, path=target)
            self.assertTrue(record.get("persisted"), record)
            on_disk = target.read_text(encoding="utf-8")
            self.assertEqual(_leaks(on_disk), [], on_disk)
            self.assertIn("~", on_disk)

    def test_the_chain_still_verifies_after_redaction(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "gate.jsonl"
            for i in range(3):
                journal.emit("gate.observed", {"cwd": HOME, "i": i}, path=target)
            result = journal.verify(journal.read_all(target)["records"])
            self.assertTrue(result.get("ok"), result)
            self.assertEqual(_leaks(journal.read_all(target)["path"]), [])


class AttributionStateOnDisk(unittest.TestCase):
    def test_workdirs_persist_without_the_username_and_still_match(self):
        from unittest import mock

        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {
                "SCW_HOME": tmp, "MAXEY0_GATE_STATE": os.path.join(tmp, "gate")}):
            workdir = os.path.join(HOME, "worktrees", "reviewer")
            attribution.declare_dispatch("sess-privacy", "reviewer", workdir=workdir)
            files = list(Path(tmp).rglob("*.json"))
            self.assertTrue(files)
            for f in files:
                self.assertEqual(_leaks(f.read_text(encoding="utf-8")), [], f)
            self.assertEqual(
                attribution.resolve_by_cwd("sess-privacy", os.path.join(workdir, "src")),
                "reviewer")


class RuntimeLedgerOnDisk(unittest.TestCase):
    def test_runtime_events_reach_disk_without_personal_data(self):
        from scw_runtime.events import EVENT_TYPES, EventLog

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "events.jsonl"
            log = EventLog(path=target)
            log.emit(EVENT_TYPES[0], "tester", {
                "cwd": HOME, "note": SECRETS["github"],
                "transcript_path": os.path.join(HOME, "t.jsonl")})
            close = getattr(log, "close", None)
            if callable(close):
                close()
            self.assertEqual(_leaks(target.read_text(encoding="utf-8")), [])


class OriginObservatory(unittest.TestCase):
    def test_a2a_task_text_is_recorded_as_a_digest(self):
        sys.path.insert(0, str(ROOT))
        from maxey0_ss.adapters.a2a import A2AHost, A2ARequest
        from maxey0_ss.system import SuperSpaceSystem

        system = SuperSpaceSystem()
        secret_task = "email jane.doe@example.com the key " + SECRETS["anthropic"]
        A2AHost(system).handle(A2ARequest(sender="peer", task=secret_task))
        dumped = json.dumps(system.observatory.trace(), default=str)
        self.assertIn("a2a.request", dumped)
        self.assertNotIn("jane.doe@example.com", dumped)
        self.assertNotIn(SECRETS["anthropic"], dumped)


class StudioScreens(unittest.TestCase):
    def test_experiment_spec_paths_are_shortened_for_display(self):
        from maxey0_studio import app

        specs = app._specs_for_display()
        self.assertTrue(specs, "the repo ships example experiment specs")
        for spec in specs:
            self.assertEqual(_leaks(spec.get("path", "")), [], spec)
            self.assertFalse(Path(spec.get("path", "")).is_absolute(), spec)


class NoUnredactedDiskWrites(unittest.TestCase):
    """Every place shipped code writes to disk either redacts what it writes or
    is listed here with the reason it cannot carry a user's personal data. A new
    writer fails this test until someone makes that call explicitly."""

    SINK = __import__("re").compile(
        r"\.write_text\(|\.write_bytes\(|\bfh\.write\(|json\.dump\(|"
        r"open\([^)]*['\"](?:w|a|wb|ab|a\+|w\+)['\"]|os\.fdopen\(")
    #: file -> why its writes are safe without calling redact() on the line.
    REVIEWED = {
        "server/gate/journal.py": "the record's payload and anchor are redact()ed where it is built",
        "server/gate/attribution.py": "persists loop ids and workdirs already passed through shorten_home",
        "server/vendor/scw_runtime/events.py": "emit() redacts the payload before the line is written",
        "hooks/session_notice.py": "writes the hook reply to stdout for the host, not to disk",
        "maxey0_ss/containment/attestation.py": "record() redact()s a persisted decision before it is digested and written",
    }

    def test_every_disk_write_is_redacted_or_reviewed(self):
        import subprocess

        files = subprocess.run(["git", "-C", str(ROOT), "ls-files", "server/*.py",
                                "maxey0_ss/*.py", "hooks/*.py"],
                               capture_output=True, text=True, check=True).stdout.split()
        offenders = []
        for rel in files:
            if "/tests/" in rel or Path(rel).name.startswith("test_"):
                continue
            lines = (ROOT / rel).read_text(encoding="utf-8").splitlines()
            for i, line in enumerate(lines):
                if not self.SINK.search(line) or "sys.stdout" in line or "sys.stderr" in line:
                    continue
                window = "\n".join(lines[i:i + 3])
                if "redact(" in window or rel in self.REVIEWED:
                    continue
                offenders.append(f"{rel}:{i + 1}: {line.strip()}")
        self.assertEqual(offenders, [], "unredacted disk writes:\n" + "\n".join(offenders))


if __name__ == "__main__":
    unittest.main()
