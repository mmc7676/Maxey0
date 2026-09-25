"""Unit tests for the two newest Studio modules.

    python tests/test_live_session_and_client.py

`live_session` and `anthropic_client` are the least-exercised code in the
repo, and both of them touch things a test must not: the user's real
`~/.scw/events.jsonl`, and the real Anthropic API. Neither is touched here.

SAFETY -- how the live log is redirected, and why it takes two steps
-------------------------------------------------------------------
`live_session` computes its target path *at import time*:

    LIVE_LOG = Path(os.environ.get("SCW_EVENT_LOG") or (Path.home() / ".scw" / "events.jsonl"))

but every function reads the module global `LIVE_LOG` *at call time*. So the
two mechanisms are needed for two different reasons:

1. `SCW_EVENT_LOG` is set BEFORE the import, so the module never even
   constructs a Path pointing at the user's real log. Setting it after the
   import would be too late -- the module-level default would already have
   resolved to `~/.scw/events.jsonl`.
2. `live_session.LIVE_LOG` is then reassigned per test, because the env var
   is no longer consulted after import and each test needs its own file.
   `importlib.reload` would also work, but reassigning the global is the
   narrower change and proves the call-time-read behavior directly.

`test_live_log_is_redirected_away_from_the_real_one` asserts the redirection
genuinely took effect rather than trusting it.
"""

from __future__ import annotations

import contextlib
import email.message
import importlib.util
import io
import itertools
import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
SERVER = REPO / "server"
VENDOR = SERVER / "vendor"
for _p in (str(VENDOR), str(SERVER)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# -- step 1 of the redirection: before importing live_session ----------------
_GUARD_DIR = Path(tempfile.mkdtemp(prefix="maxey0-live-guard-"))
os.environ["SCW_EVENT_LOG"] = str(_GUARD_DIR / "import-time-guard.jsonl")

from maxey0_studio import live_session  # noqa: E402
from scw_runtime import ContextWindow  # noqa: E402
from scw_runtime.events import EventLog, canonical, iter_records  # noqa: E402

REAL_CLIENT = SERVER / "maxey0_studio" / "anthropic_client.py"
REAL_HOME_LOG = Path.home() / ".scw" / "events.jsonl"

FAKE_KEY = "sk-ant-test-000"
FAKE_DOTENV_KEY = "sk-ant-test-dotenv-0001"

_counter = itertools.count(1)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def env_vars(**pairs: "str | None"):
    """Set/unset env vars for the duration of the block, then restore."""
    saved = {key: os.environ.get(key) for key in pairs}
    try:
        for key, value in pairs.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def write_run_with_activity(
    path: Path, loop_id: str = "loop-probe", unbind: bool = False
) -> str:
    """Drive a *real* ContextWindow so the log holds genuine events.

    Nothing here is hand-written JSON: create/write/bind/tick all go through
    the same enforcement engine the MCP server uses, which is the only way to
    know replay will accept the result.

    `unbind` defaults to False because that is what a *live* session looks
    like on disk: the loop is still bound when the Studio reads the log.
    """
    log = EventLog(path=path)
    window = ContextWindow(total_budget=8000, event_log=log, name="probe-window")
    reference = window.create_scw("ground-truth", region_type="reference")
    window.write(reference.scw_id, "the counts are evidence, not decoration")
    working = window.create_scw("draft", region_type="working")
    window.bind_scope(loop_id, working.scw_id, max_iterations=3, goal="write the draft")
    window.write(working.scw_id, "first pass", loop_id=loop_id)
    window.loop_tick(loop_id, verified=True, verified_by="judge")
    if unbind:
        window.unbind_scope(loop_id, terminal_state="success")
    log.close()
    return log.run_id


def write_run_without_activity(path: Path) -> str:
    """A run that started and did nothing -- only `window.init` on disk."""
    log = EventLog(path=path)
    ContextWindow(total_budget=8000, event_log=log, name="idle-window")
    log.close()
    return log.run_id


def rewrite_lines(path: Path, records: list) -> None:
    path.write_text("".join(canonical(r) + "\n" for r in records), encoding="utf-8")


def load_isolated_client(
    tmp_root: Path,
    dotenv_text: "str | None" = None,
    dotenv_at: str = "server",
):
    """Load a byte-identical copy of anthropic_client.py from a temp tree.

    `_load_dotenv_key()` resolves its candidates from `Path(__file__)`, so the
    only way to test .env pickup without writing into the user's real
    repository is to give the module a different `__file__`. The copy is
    asserted byte-identical to the real file by
    `AnthropicClientTests.test_isolated_copy_is_the_real_source`.
    """
    package = tmp_root / "server" / "maxey0_studio"
    package.mkdir(parents=True, exist_ok=True)
    target = package / "anthropic_client.py"
    shutil.copyfile(REAL_CLIENT, target)

    if dotenv_text is not None:
        # parents[1] of the module file is <tmp>/server; parents[2] is <tmp>.
        base = tmp_root / "server" if dotenv_at == "server" else tmp_root
        base.mkdir(parents=True, exist_ok=True)
        (base / ".env").write_text(dotenv_text, encoding="utf-8")

    name = f"_isolated_anthropic_client_{next(_counter)}"
    spec = importlib.util.spec_from_file_location(name, target)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


# ---------------------------------------------------------------------------
# live_session
# ---------------------------------------------------------------------------


class LiveSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="maxey0-live-"))
        self.log_path = self.tmp / "events.jsonl"
        self._saved_live_log = live_session.LIVE_LOG
        # step 2 of the redirection -- see the module docstring.
        live_session.LIVE_LOG = self.log_path

    def tearDown(self) -> None:
        live_session.LIVE_LOG = self._saved_live_log
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- the safety property itself -------------------------------------

    def test_live_log_is_redirected_away_from_the_real_one(self) -> None:
        """The redirection must be provable, not assumed."""
        self.assertEqual(live_session.LIVE_LOG, self.log_path)
        self.assertNotEqual(live_session.LIVE_LOG, REAL_HOME_LOG)
        # And the module reports back the path it actually used, so a payload
        # naming the real log would be caught here too.
        payload = live_session.read_live_session()
        self.assertEqual(payload["log_path"], str(self.log_path))
        self.assertNotIn(str(REAL_HOME_LOG), payload["log_path"])
        # The import-time guard also has to have kept the real path out.
        self.assertNotEqual(self._saved_live_log, REAL_HOME_LOG)

    # -- degenerate logs ------------------------------------------------

    def test_missing_log_is_unavailable_and_does_not_raise(self) -> None:
        self.assertFalse(self.log_path.exists())
        payload = live_session.read_live_session()
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["available"])
        self.assertEqual(payload["source"], "none")
        self.assertIn("message", payload)

    def test_empty_log_is_unavailable_and_does_not_raise(self) -> None:
        self.log_path.write_text("", encoding="utf-8")
        payload = live_session.read_live_session()
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["available"])
        self.assertEqual(payload["source"], "none")
        self.assertEqual(payload["message"], "log exists but is empty")

    def test_blank_lines_only_is_treated_as_empty(self) -> None:
        self.log_path.write_text("\n\n   \n", encoding="utf-8")
        payload = live_session.read_live_session()
        self.assertFalse(payload["available"])
        self.assertEqual(payload["source"], "none")

    def test_missing_log_gives_empty_run_list(self) -> None:
        result = live_session.list_runs()
        self.assertTrue(result["ok"])
        self.assertEqual(result["runs"], [])

    # -- a real run -----------------------------------------------------

    def test_single_real_run_is_available_with_regions_and_loops(self) -> None:
        run_id = write_run_with_activity(self.log_path)
        payload = live_session.read_live_session()

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["available"])
        self.assertEqual(payload["source"], "this_session")
        self.assertEqual(payload["total_runs_on_disk"], 1)

        window = payload["window"]
        self.assertEqual(window["run_id"], run_id)
        self.assertEqual(window["record_count"], payload["total_records_on_disk"])
        self.assertIsInstance(window["last_event_ts"], float)

        labels = {region["label"] for region in window["regions"]}
        self.assertIn("ground-truth", labels)
        self.assertIn("draft", labels)

        self.assertEqual(len(window["loops"]), 1)
        loop = window["loops"][0]
        self.assertEqual(loop["loop_id"], "loop-probe")
        self.assertEqual(loop["iteration"], 1)
        # Still `bound`: write_run_with_activity deliberately does not unbind,
        # because that is what a live session genuinely looks like on disk at
        # the moment the app reads the log.
        self.assertEqual(loop["status"], "bound")
        # The closures are the isolation claim, computed not asserted.
        self.assertTrue(loop["write_closure"])
        self.assertTrue(set(loop["write_closure"]).issubset(set(loop["read_closure"])))
        # The reference region the loop was never bound to must not be
        # writable from inside the loop's scope.
        reference_ids = [r["scw_id"] for r in window["regions"] if r["label"] == "ground-truth"]
        self.assertNotIn(reference_ids[0], loop["write_closure"])

        self.assertEqual(window["bridges"], [])

    def test_single_clean_run_reports_chain_intact(self) -> None:
        write_run_with_activity(self.log_path)
        payload = live_session.read_live_session()
        self.assertTrue(payload["chain_intact"])

    # -- damaged logs: the whole point of the module ---------------------

    def test_tampered_payload_reports_chain_broken_but_still_returns_a_window(self) -> None:
        """A digest that no longer matches its body must degrade, not explode."""
        write_run_with_activity(self.log_path)
        records = list(iter_records(self.log_path))
        target = next(i for i, r in enumerate(records) if r["type"] == "scw.write")
        records[target]["payload"]["data"] = "EDITED AFTER THE FACT"
        rewrite_lines(self.log_path, records)

        payload = live_session.read_live_session()

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["available"])
        self.assertFalse(payload["chain_intact"])
        # Usable, not merely non-crashing.
        self.assertTrue(payload["window"]["regions"])
        self.assertEqual(len(payload["window"]["loops"]), 1)

    def test_duplicated_record_breaks_the_chain_without_raising(self) -> None:
        """A double-flush by a concurrent writer produces a seq gap."""
        write_run_with_activity(self.log_path)
        records = list(iter_records(self.log_path))
        target = next(i for i, r in enumerate(records) if r["type"] == "scw.write")
        records.insert(target + 1, dict(records[target]))
        rewrite_lines(self.log_path, records)

        payload = live_session.read_live_session()

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["available"])
        self.assertFalse(payload["chain_intact"])
        self.assertTrue(payload["window"]["regions"])

    # -- run selection --------------------------------------------------

    def test_idle_newest_run_falls_back_to_the_last_run_that_worked(self) -> None:
        busy_run = write_run_with_activity(self.log_path)
        idle_run = write_run_without_activity(self.log_path)
        self.assertNotEqual(busy_run, idle_run)

        payload = live_session.read_live_session()

        self.assertTrue(payload["available"])
        self.assertEqual(payload["source"], "last_recorded")
        self.assertEqual(payload["window"]["run_id"], busy_run)
        self.assertEqual(payload["total_runs_on_disk"], 2)
        self.assertTrue(payload["window"]["loops"])

    def test_newest_run_with_activity_wins_over_older_ones(self) -> None:
        write_run_with_activity(self.log_path, loop_id="loop-old")
        newest = write_run_with_activity(self.log_path, loop_id="loop-new")

        payload = live_session.read_live_session()

        self.assertEqual(payload["source"], "this_session")
        self.assertEqual(payload["window"]["run_id"], newest)
        self.assertEqual([l["loop_id"] for l in payload["window"]["loops"]], ["loop-new"])

    def test_only_idle_runs_anywhere_is_reported_honestly(self) -> None:
        write_run_without_activity(self.log_path)
        write_run_without_activity(self.log_path)

        payload = live_session.read_live_session()

        # There is a run and it replays, so it is available -- but it is the
        # caller's own empty run, correctly labeled, not a borrowed one.
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["source"], "this_session")
        self.assertEqual(payload["window"]["regions"], [])
        self.assertEqual(payload["window"]["loops"], [])

    # -- list_runs ------------------------------------------------------

    def test_list_runs_is_newest_first_and_flags_activity(self) -> None:
        busy = write_run_with_activity(self.log_path)
        idle = write_run_without_activity(self.log_path)

        result = live_session.list_runs()

        self.assertTrue(result["ok"])
        self.assertEqual([r["run_id"] for r in result["runs"]], [idle, busy])
        self.assertFalse(result["runs"][0]["has_activity"])
        self.assertTrue(result["runs"][1]["has_activity"])
        self.assertEqual(result["runs"][0]["record_count"], 1)
        self.assertGreater(result["runs"][1]["record_count"], 1)
        for row in result["runs"]:
            self.assertLessEqual(row["first_ts"], row["last_ts"])

    def test_list_runs_limit_keeps_the_most_recent(self) -> None:
        write_run_with_activity(self.log_path, loop_id="loop-a")
        write_run_with_activity(self.log_path, loop_id="loop-b")
        newest = write_run_with_activity(self.log_path, loop_id="loop-c")

        result = live_session.list_runs(limit=2)

        self.assertEqual(len(result["runs"]), 2)
        self.assertEqual(result["runs"][0]["run_id"], newest)

    def test_list_runs_does_not_verify_the_chain(self) -> None:
        """A picker over a damaged log still has to render."""
        write_run_with_activity(self.log_path)
        records = list(iter_records(self.log_path))
        records[-1]["payload"] = {"mangled": True}
        rewrite_lines(self.log_path, records)

        result = live_session.list_runs()
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["runs"]), 1)

    # -- a defect this test file records rather than hides ---------------

    def test_tokens_field_is_always_none_because_inspect_has_no_such_key(self) -> None:
        """DEFECT: `_window_payload` reads a key `inspect()` never returns.

        `live_session._window_payload` does
        `window.inspect(include_content=False).get("tokens")`, but
        `ContextWindow.inspect()` returns `window`/`regions`/`loops`/`cache`/
        ... and no top-level `tokens`. The field is therefore permanently
        None -- the token accounting is under `["window"]["used_tokens"]` and
        `["cache"]`. Asserted so the day it is fixed, this test fails loudly
        instead of the bug being re-frozen.
        """
        write_run_with_activity(self.log_path)
        payload = live_session.read_live_session()
        self.assertIn("tokens", payload["window"])
        self.assertIsNone(payload["window"]["tokens"])

        from scw_runtime.replay import replay_file

        window = replay_file(self.log_path, verify=False)
        self.assertNotIn("tokens", window.inspect(include_content=False))
        self.assertGreater(window.inspect(include_content=False)["window"]["used_tokens"], 0)


# ---------------------------------------------------------------------------
# anthropic_client
# ---------------------------------------------------------------------------


class AnthropicClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="maxey0-anthropic-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def isolated(self, **kwargs):
        return load_isolated_client(self.tmp / f"case-{next(_counter)}", **kwargs)

    # -- the copy is the real code --------------------------------------

    def test_isolated_copy_is_the_real_source(self) -> None:
        module = self.isolated()
        self.assertEqual(
            Path(module.__file__).read_bytes(),
            REAL_CLIENT.read_bytes(),
            "the isolated copy has drifted from server/maxey0_studio/anthropic_client.py",
        )
        self.assertEqual(module.API_URL, "https://api.anthropic.com/v1/messages")
        self.assertEqual(module.API_VERSION, "2023-06-01")

    # -- configuration --------------------------------------------------

    def test_not_configured_with_no_env_var_and_no_dotenv(self) -> None:
        module = self.isolated()
        with env_vars(ANTHROPIC_API_KEY=None):
            self.assertFalse(module.is_configured())
            status = module.key_status()
        self.assertEqual(
            status, {"configured": False, "source": None, "model": module.DEFAULT_MODEL}
        )
        self.assertNotIn("key_preview", status)

    def test_configured_when_env_var_is_set(self) -> None:
        module = self.isolated()
        with env_vars(ANTHROPIC_API_KEY=FAKE_KEY):
            self.assertTrue(module.is_configured())

    def test_blank_env_var_does_not_count_as_configured(self) -> None:
        module = self.isolated()
        with env_vars(ANTHROPIC_API_KEY=""):
            self.assertFalse(module.is_configured())

    def test_key_status_masks_the_key_and_reports_env(self) -> None:
        module = self.isolated()
        with env_vars(ANTHROPIC_API_KEY=FAKE_KEY):
            status = module.key_status()

        self.assertTrue(status["configured"])
        self.assertEqual(status["source"], "env")
        preview = status["key_preview"]
        self.assertNotEqual(preview, FAKE_KEY)
        self.assertNotIn(FAKE_KEY, preview)
        self.assertIn("...", preview)
        self.assertTrue(preview.startswith(FAKE_KEY[:7]))
        self.assertTrue(preview.endswith(FAKE_KEY[-4:]))
        # The masked middle must actually be missing, not merely shortened.
        self.assertNotIn(FAKE_KEY[7:-4], preview)

    def test_short_key_is_fully_masked(self) -> None:
        module = self.isolated()
        with env_vars(ANTHROPIC_API_KEY="short-key"):
            self.assertEqual(module.key_status()["key_preview"], "***")

    # -- .env pickup -----------------------------------------------------

    def test_dotenv_beside_server_is_picked_up_and_reported_as_dotenv(self) -> None:
        module = self.isolated(
            dotenv_text=f"# comment\n\nANTHROPIC_API_KEY={FAKE_DOTENV_KEY}\n",
            dotenv_at="server",
        )
        with env_vars(ANTHROPIC_API_KEY=None):
            self.assertTrue(module.is_configured())
            status = module.key_status()

        self.assertEqual(status["source"], "dotenv")
        self.assertTrue(status["key_preview"].startswith(FAKE_DOTENV_KEY[:7]))
        self.assertNotIn(FAKE_DOTENV_KEY, status["key_preview"])

    def test_dotenv_at_repo_root_is_also_picked_up(self) -> None:
        module = self.isolated(
            dotenv_text=f'ANTHROPIC_API_KEY="{FAKE_DOTENV_KEY}"\n', dotenv_at="root"
        )
        with env_vars(ANTHROPIC_API_KEY=None):
            self.assertEqual(module.key_status()["source"], "dotenv")

    def test_dotenv_quotes_and_unrelated_lines_are_handled(self) -> None:
        module = self.isolated(
            dotenv_text=(
                "# leading comment\n"
                "OTHER_THING=ignored\n"
                "malformed line with no equals\n"
                f"ANTHROPIC_API_KEY = '{FAKE_DOTENV_KEY}' \n"
            )
        )
        with env_vars(ANTHROPIC_API_KEY=None):
            self.assertTrue(module.is_configured())

    def test_env_var_takes_precedence_over_dotenv(self) -> None:
        module = self.isolated(dotenv_text=f"ANTHROPIC_API_KEY={FAKE_DOTENV_KEY}\n")
        with env_vars(ANTHROPIC_API_KEY=FAKE_KEY):
            status = module.key_status()
            captured = {}

            def fake_urlopen(request, timeout=None):
                captured["key"] = request.get_header("X-api-key")
                return FakeResponse({"content": [{"type": "text", "text": "ok"}]})

            with mock.patch("urllib.request.urlopen", fake_urlopen):
                module.complete("sys", "user")

        self.assertEqual(status["source"], "env")
        self.assertTrue(status["key_preview"].startswith(FAKE_KEY[:7]))
        # Precedence has to hold on the wire, not only in the status dict.
        self.assertEqual(captured["key"], FAKE_KEY)

    # -- model selection -------------------------------------------------

    def test_default_model_when_override_is_unset(self) -> None:
        with env_vars(MAXEY0_MODEL=None, MAXEY0_ANTHROPIC_MODEL=None):
            module = self.isolated()
        self.assertEqual(module.DEFAULT_MODEL, "claude-sonnet-5")

    def test_the_canonical_variable_is_honoured(self) -> None:
        """0.7.0 renamed the variable to match the rest of the lexicon."""
        with env_vars(MAXEY0_MODEL="claude-canonical-1",
                      MAXEY0_ANTHROPIC_MODEL=None):
            module = self.isolated()
        self.assertEqual(module.DEFAULT_MODEL, "claude-canonical-1")

    def test_the_old_variable_still_works(self) -> None:
        """Renaming a tool is a clean break this release makes on purpose.

        Silently breaking a variable someone already exported into their shell
        is not the same thing, so the 0.6.0 name is still honored.
        """
        with env_vars(MAXEY0_MODEL=None,
                      MAXEY0_ANTHROPIC_MODEL="claude-legacy-1"):
            module = self.isolated()
        self.assertEqual(module.DEFAULT_MODEL, "claude-legacy-1")

    def test_the_canonical_variable_wins_when_both_are_set(self) -> None:
        with env_vars(MAXEY0_MODEL="claude-canonical-1",
                      MAXEY0_ANTHROPIC_MODEL="claude-legacy-1"):
            module = self.isolated()
        self.assertEqual(module.DEFAULT_MODEL, "claude-canonical-1")

    def test_no_model_family_other_than_the_documented_default(self) -> None:
        """The product hard-codes exactly one model id, and it is a default.

        Asserted rather than assumed: a model silently added to the runtime is
        a choice made on the operator's behalf, and this is where that would be
        caught.
        """
        source = (pathlib.Path(__file__).resolve().parents[1]
                  / "server").rglob("*.py")
        offenders = []
        for path in source:
            if "vendor" in path.parts or "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="replace").lower()
            for family in ("haiku", "claude-3", "claude-opus"):
                if family in text:
                    offenders.append(f"{path.name}: {family}")
        self.assertEqual(offenders, [])

    def test_default_model_honours_the_override(self) -> None:
        with env_vars(MAXEY0_ANTHROPIC_MODEL="claude-test-model-9"):
            module = self.isolated()
            with env_vars(ANTHROPIC_API_KEY=FAKE_KEY):
                status = module.key_status()
        self.assertEqual(module.DEFAULT_MODEL, "claude-test-model-9")
        self.assertEqual(status["model"], "claude-test-model-9")

    def test_model_override_is_read_at_import_not_at_call(self) -> None:
        """DEFECT-ish asymmetry, recorded deliberately.

        The API key is resolved on every call (`_api_key()`), but the model is
        frozen into `DEFAULT_MODEL` at import. So a `.env` or a late
        `os.environ` assignment changes the key and silently does not change
        the model. Recording it so the inconsistency is a decision rather than
        an accident.
        """
        with env_vars(MAXEY0_MODEL=None, MAXEY0_ANTHROPIC_MODEL=None):
            module = self.isolated()
        with env_vars(MAXEY0_ANTHROPIC_MODEL="claude-set-too-late"):
            self.assertEqual(module.DEFAULT_MODEL, "claude-sonnet-5")
            with env_vars(ANTHROPIC_API_KEY=FAKE_KEY):
                self.assertEqual(module.key_status()["model"], "claude-sonnet-5")

    def test_dotenv_only_supplies_the_key_never_the_model(self) -> None:
        with env_vars(MAXEY0_MODEL=None, MAXEY0_ANTHROPIC_MODEL=None):
            module = self.isolated(
                dotenv_text=(
                    f"ANTHROPIC_API_KEY={FAKE_DOTENV_KEY}\n"
                    "MAXEY0_ANTHROPIC_MODEL=claude-from-dotenv\n"
                )
            )
        with env_vars(ANTHROPIC_API_KEY=None):
            self.assertTrue(module.is_configured())
            self.assertEqual(module.key_status()["model"], "claude-sonnet-5")

    # -- complete(): refusal without a key -------------------------------

    def test_complete_raises_without_a_key_and_never_opens_a_socket(self) -> None:
        module = self.isolated()
        with env_vars(ANTHROPIC_API_KEY=None):
            with mock.patch("urllib.request.urlopen") as opened:
                with self.assertRaises(module.AnthropicError) as caught:
                    module.complete("system", "user")
            opened.assert_not_called()
        self.assertIn("ANTHROPIC_API_KEY", str(caught.exception))
        self.assertIsInstance(caught.exception, RuntimeError)

    # -- complete(): request shaping, no network -------------------------

    def test_complete_builds_the_documented_request(self) -> None:
        module = self.isolated()
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["request"] = request
            captured["timeout"] = timeout
            return FakeResponse(
                {"content": [{"type": "text", "text": "hello "}, {"type": "text", "text": "world"}]}
            )

        with env_vars(ANTHROPIC_API_KEY=FAKE_KEY, MAXEY0_MODEL=None,
                      MAXEY0_ANTHROPIC_MODEL=None):
            with mock.patch("urllib.request.urlopen", fake_urlopen):
                text = module.complete("be terse", "count the loops", max_tokens=64)

        self.assertEqual(text, "hello world")

        request = captured["request"]
        self.assertEqual(request.full_url, module.API_URL)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(captured["timeout"], 60)

        headers = {k.lower(): v for k, v in request.headers.items()}
        self.assertEqual(headers["x-api-key"], FAKE_KEY)
        self.assertEqual(headers["anthropic-version"], module.API_VERSION)
        self.assertEqual(headers["content-type"], "application/json")

        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["model"], module.DEFAULT_MODEL)
        self.assertEqual(body["max_tokens"], 64)
        self.assertEqual(body["system"], "be terse")
        self.assertEqual(body["messages"], [{"role": "user", "content": "count the loops"}])

    def test_explicit_model_argument_overrides_the_default(self) -> None:
        module = self.isolated()
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse({"content": [{"type": "text", "text": "ok"}]})

        with env_vars(ANTHROPIC_API_KEY=FAKE_KEY):
            with mock.patch("urllib.request.urlopen", fake_urlopen):
                module.complete("s", "u", model="claude-explicit-1")

        self.assertEqual(captured["body"]["model"], "claude-explicit-1")

    def test_non_text_blocks_are_skipped_when_joining_the_reply(self) -> None:
        module = self.isolated()
        payload = {
            "content": [
                {"type": "thinking", "thinking": "should not appear"},
                {"type": "text", "text": "kept"},
            ]
        }
        with env_vars(ANTHROPIC_API_KEY=FAKE_KEY):
            with mock.patch("urllib.request.urlopen", lambda r, timeout=None: FakeResponse(payload)):
                self.assertEqual(module.complete("s", "u"), "kept")

    def test_response_with_no_text_raises(self) -> None:
        module = self.isolated()
        payload = {"content": [{"type": "tool_use", "name": "x"}]}
        with env_vars(ANTHROPIC_API_KEY=FAKE_KEY):
            with mock.patch("urllib.request.urlopen", lambda r, timeout=None: FakeResponse(payload)):
                with self.assertRaises(module.AnthropicError):
                    module.complete("s", "u")

    # -- complete(): error translation -----------------------------------

    def test_http_error_becomes_anthropic_error_with_the_body(self) -> None:
        module = self.isolated()
        error = urllib.error.HTTPError(
            module.API_URL,
            401,
            "Unauthorized",
            email.message.Message(),
            io.BytesIO(b'{"error":{"message":"invalid x-api-key"}}'),
        )

        def raise_http(request, timeout=None):
            raise error

        with env_vars(ANTHROPIC_API_KEY=FAKE_KEY):
            with mock.patch("urllib.request.urlopen", raise_http):
                with self.assertRaises(module.AnthropicError) as caught:
                    module.complete("s", "u")

        message = str(caught.exception)
        self.assertIn("HTTP 401", message)
        self.assertIn("invalid x-api-key", message)
        # The key itself must not be echoed back into the error text.
        self.assertNotIn(FAKE_KEY, message)

    def test_network_error_becomes_anthropic_error(self) -> None:
        module = self.isolated()

        def raise_url(request, timeout=None):
            raise urllib.error.URLError("name or service not known")

        with env_vars(ANTHROPIC_API_KEY=FAKE_KEY):
            with mock.patch("urllib.request.urlopen", raise_url):
                with self.assertRaises(module.AnthropicError) as caught:
                    module.complete("s", "u")

        self.assertIn("network error", str(caught.exception))

    def test_http_error_body_is_truncated(self) -> None:
        module = self.isolated()
        error = urllib.error.HTTPError(
            module.API_URL, 500, "Server Error",
            email.message.Message(), io.BytesIO(b"x" * 5000),
        )

        def raise_http(request, timeout=None):
            raise error

        with env_vars(ANTHROPIC_API_KEY=FAKE_KEY):
            with mock.patch("urllib.request.urlopen", raise_http):
                with self.assertRaises(module.AnthropicError) as caught:
                    module.complete("s", "u")

        self.assertLess(len(str(caught.exception)), 600)


class RealModuleSmokeTests(unittest.TestCase):
    """The installed module, not a copy -- the import path the app uses."""

    def test_real_module_imports_and_exposes_its_api(self) -> None:
        from maxey0_studio import anthropic_client

        for name in ("API_URL", "API_VERSION", "DEFAULT_MODEL", "AnthropicError",
                     "is_configured", "key_status", "complete"):
            self.assertTrue(hasattr(anthropic_client, name), name)
        self.assertTrue(issubclass(anthropic_client.AnthropicError, RuntimeError))

    def test_real_module_is_configured_when_the_env_var_is_set(self) -> None:
        from maxey0_studio import anthropic_client

        with env_vars(ANTHROPIC_API_KEY=FAKE_KEY):
            self.assertTrue(anthropic_client.is_configured())
            status = anthropic_client.key_status()
        self.assertEqual(status["source"], "env")
        self.assertNotIn(FAKE_KEY, status["key_preview"])

    @unittest.skipIf(
        (SERVER / ".env").exists() or (REPO / ".env").exists(),
        "a real .env is present in this checkout; the unconfigured path cannot be observed",
    )
    def test_real_module_refuses_to_complete_without_a_key(self) -> None:
        from maxey0_studio import anthropic_client

        with env_vars(ANTHROPIC_API_KEY=None):
            self.assertFalse(anthropic_client.is_configured())
            with mock.patch("urllib.request.urlopen") as opened:
                with self.assertRaises(anthropic_client.AnthropicError):
                    anthropic_client.complete("s", "u")
            opened.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
