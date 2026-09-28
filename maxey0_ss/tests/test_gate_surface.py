"""The Gate control surface has to be callable.

`gate.store` takes `session_ref` as its first positional argument; observe_impl
passed the value first and `session=` as a keyword, so every Gate read and write
raised TypeError. The tools were declared, registered, documented and listed in
the menu, and not one of them could be invoked. Nothing exercised them, in five
byte-identical copies.

Every call below runs against a throwaway SCW home. Until 0.3.0 it did not:
`observe_gate_mode('observe')`, then `('enforce')`, then
`observe_gate_policy('maker')` wrote the real `~/.scw/gate/policy-nosession.json`
-- the no-session fallback file the developer's own Claude Code gate hook
enforces from. One test run left their gate forced to `enforce` with an empty
`maker` scope declared, whatever they had configured before, and nothing
reported it.
"""
import json
import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
COPIES = [REPO / "server"] + sorted(REPO.glob("plugins/*/server"))

#: Variables that pin the Gate's answer rather than locate its state. Cleared so
#: an exported `MAXEY0_GATE_MODE` cannot turn the round-trip test into a
#: `mode_pinned` refusal, and `MAXEY0_GATE_SESSION` / `MAXEY0_GATE_POLICY`
#: cannot redirect reads to some other session's file or a run-wide policy.
_CLEARED = ("MAXEY0_GATE_MODE", "MAXEY0_GATE_SESSION", "MAXEY0_GATE_POLICY")


def _point_gate_at(mp: pytest.MonkeyPatch, home: pathlib.Path) -> None:
    """Aim every path the Gate and the Observatory resolve at ``home``.

    `gate.attribution.state_dir` reads MAXEY0_GATE_STATE then SCW_HOME,
    `gate.journal.journal_path` reads MAXEY0_GATE_LOG then SCW_HOME, and the
    ledger (`planes.bootstrap.ledger_path`, `gate.journal._runtime_anchor`)
    reads SCW_EVENT_LOG. All of them fall back to `Path.home() / ".scw"`, so
    HOME and USERPROFILE (what `Path.home()` consults on POSIX and on Windows)
    are redirected too: a state path added later that forgets SCW_HOME still
    lands here rather than in the developer's profile.

    Each of those is resolved per call, not at import, which is why the
    redirect still holds when another test module imported
    `planes.observe_impl` first and it is served from `sys.modules`.
    """
    for name in _CLEARED:
        mp.delenv(name, raising=False)
    mp.setenv("SCW_HOME", str(home))
    mp.setenv("MAXEY0_GATE_STATE", str(home / "gate"))
    mp.setenv("MAXEY0_GATE_LOG", str(home / "gate.jsonl"))
    mp.setenv("SCW_EVENT_LOG", str(home / "events.jsonl"))
    mp.setenv("HOME", str(home))
    mp.setenv("USERPROFILE", str(home))


@pytest.fixture(scope="module")
def gate_home(tmp_path_factory):
    """One SCW home for the module, with the environment restored afterwards.

    Module-scoped because `observe_impl` is, and the redirect has to be in
    place before that import runs, not only once the first test starts.
    """
    home = tmp_path_factory.mktemp("scw-home")
    with pytest.MonkeyPatch.context() as mp:
        _point_gate_at(mp, home)
        yield home


@pytest.fixture(autouse=True)
def _gate_stays_in_gate_home(gate_home, monkeypatch):
    """Re-assert the redirect for each test.

    The root `conftest.py` deletes, per test, every key the local `.env`
    declares. Should that file ever carry SCW_HOME or a MAXEY0_GATE_* path, the
    module-level redirect would be deleted for the duration of each test and
    the calls would fall back to the real home. Function-scoped autouse
    fixtures in this module run after the conftest's, so this one wins.
    """
    _point_gate_at(monkeypatch, gate_home)


@pytest.fixture(scope="module")
def observe_impl(gate_home):
    sys.path.insert(0, str(REPO / "server"))
    try:
        from planes import observe_impl as module
        yield module
    finally:
        sys.path.remove(str(REPO / "server"))


def test_every_gate_path_resolves_inside_the_throwaway_home(observe_impl, gate_home):
    """The redirect is checked, not trusted: a missed variable fails here."""
    assert observe_impl.gate_store._policy_path(None) == (
        gate_home / "gate" / "policy-nosession.json")
    assert observe_impl.gate_journal.journal_path() == gate_home / "gate.jsonl"
    assert observe_impl.bootstrap.ledger_path() == gate_home / "events.jsonl"


def test_gate_writes_land_in_the_throwaway_home(observe_impl, gate_home):
    observe_impl.observe_gate_mode("observe")
    observe_impl.observe_gate_policy("maker")
    written = json.loads(
        (gate_home / "gate" / "policy-nosession.json").read_text(encoding="utf-8"))
    assert written["mode"] == "observe"
    assert "maker" in written["roles"]


def test_reading_the_gate_mode_does_not_raise(observe_impl):
    result = observe_impl.observe_gate_mode()
    assert result["ok"] is True
    assert result["mode"] in result["modes"]


def test_setting_the_gate_mode_round_trips(observe_impl):
    try:
        assert observe_impl.observe_gate_mode("observe")["mode"] == "observe"
        assert observe_impl.observe_gate_mode()["mode"] == "observe"
    finally:
        observe_impl.observe_gate_mode("enforce")
    assert observe_impl.observe_gate_mode()["mode"] == "enforce"


def test_reading_a_role_policy_does_not_raise(observe_impl):
    result = observe_impl.observe_gate_policy("maker")
    assert result["ok"] is True and result["role"] == "maker"


def test_the_isolation_ladder_is_readable(observe_impl):
    result = observe_impl.observe_isolation_level()
    assert result["ok"] is True and result["ladder"]


def test_no_copy_still_passes_session_as_a_keyword():
    """The defect shipped in five vendored trees; a fix in one is not a fix."""
    offenders = []
    for root in COPIES:
        path = root / "planes" / "observe_impl.py"
        if not path.exists():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "gate_store." in line and "session=" in line:
                offenders.append(f"{path.relative_to(REPO)}:{number}")
    assert not offenders, f"gate_store called with session= in: {offenders}"


def test_every_copy_of_observe_impl_is_identical():
    """Divergence between the vendored trees is how one fix becomes four bugs."""
    bodies = {}
    for root in COPIES:
        path = root / "planes" / "observe_impl.py"
        if path.exists():
            bodies[str(path.relative_to(REPO))] = path.read_text(encoding="utf-8")
    assert len(set(bodies.values())) == 1, f"copies diverge: {sorted(bodies)}"
