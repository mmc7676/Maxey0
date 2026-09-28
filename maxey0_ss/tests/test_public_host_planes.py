"""A public deployment does not serve the host's journals unless it opts in.

Without this rule, a public origin behind a tunnel with MAXEY0_PUBLIC=1 and
bearer auth answered `observe.gate_activity` with the last hundred entries of
its host's Gate journal and `observe.events` with the host's ledger, absolute
local paths included -- to a shared operator token. `gate.set_mode` writes the
same fallback policy file the host's own gate hook enforces from.

Every test here points the plane at `tmp_path` (SCW_HOME, SCW_EVENT_LOG,
MAXEY0_GATE_LOG, MAXEY0_GATE_STATE), so nothing reads or writes the real
~/.scw.
"""
from __future__ import annotations

import json
import pathlib
import re
import types
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from maxey0_ss.api.app import create_app
from maxey0_ss.mcp_surface import build_surface
from maxey0_ss.observability import bridge
from gate.privacy import shorten_home  # importable once bridge put server/ on the path
from maxey0_ss.observability.bridge import (
    HOST_INDEPENDENT,
    HOST_STATE_READS,
    HOST_STATE_WRITES,
    PUBLIC_HOST_PLANES,
)

REPO = pathlib.Path(__file__).resolve().parents[2]
V = "2026-07-28"

#: One valid call per host-state tool.
READ_CALLS: dict[str, dict] = {
    "maxey0-ss.observe.events": {},
    "maxey0-ss.observe.attempts": {"role": "maker"},
    "maxey0-ss.observe.traces": {},
    "maxey0-ss.observe.gate_activity": {},
    "maxey0-ss.observe.gate_mode": {},
    "maxey0-ss.observe.isolation_level": {},
    "maxey0-ss.gate.declare_isolation": {"declared": "L1_logical"},
}
WRITE_CALLS: dict[str, dict] = {
    "maxey0-ss.gate.set_mode": {"mode": "off"},
    "maxey0-ss.gate.set_policy": {"role": "maker", "read_paths": ["/"]},
}

#: Variables the plane reads that would otherwise point at the real host, or
#: pin a mode the tests below assert on.
_HOST_VARS = ("MAXEY0_PUBLIC", PUBLIC_HOST_PLANES, "MAXEY0_GATE_MODE",
              "MAXEY0_GATE_POLICY", "MAXEY0_GATE_SESSION")

#: A Windows drive path or a POSIX home/temp path, anywhere in a payload.
_ABSOLUTE_PATH = re.compile(r"[A-Za-z]:[\\/]|(?<![\w.])/(?:home|Users|tmp|var|root)/")


@dataclass
class Host:
    root: pathlib.Path
    ledger: pathlib.Path
    journal: pathlib.Path
    policy: pathlib.Path

    def snapshot(self) -> dict[str, bytes]:
        return {str(p): p.read_bytes() for p in sorted(self.root.rglob("*")) if p.is_file()}


def _point_plane_at(monkeypatch, root: pathlib.Path) -> Host:
    for name in _HOST_VARS:
        monkeypatch.delenv(name, raising=False)
    host = Host(root, root / "events.jsonl", root / "gate.jsonl",
                root / "gate" / "policy-nosession.json")
    monkeypatch.setenv("SCW_HOME", str(root))
    monkeypatch.setenv("SCW_EVENT_LOG", str(host.ledger))
    monkeypatch.setenv("MAXEY0_GATE_LOG", str(host.journal))
    monkeypatch.setenv("MAXEY0_GATE_STATE", str(host.policy.parent))
    return host


@pytest.fixture
def host(tmp_path, monkeypatch) -> Host:
    """A stand-in for the origin's home: a seeded ledger, journal and policy file."""
    h = _point_plane_at(monkeypatch, tmp_path / "scw")
    bridge._impl()  # puts server/ and its vendored runtime on sys.path
    from gate import journal as gate_journal
    from scw_runtime.events import EventLog

    log = EventLog(h.ledger)
    log.emit("window.init", "host", {"budget": 2048})
    log.emit("scw.read", "maker", {"scw_id": "R1"})
    log.close()
    gate_journal.emit("gate.attempt", {"tool": "Read"}, actor="maker", path=h.journal)
    h.policy.parent.mkdir(parents=True, exist_ok=True)
    h.policy.write_text(json.dumps({"mode": "enforce", "roles": {}}), encoding="utf-8")
    return h


@pytest.fixture(scope="module")
def tools() -> dict:
    return {t.name: t for t in build_surface().tools}


def _public(monkeypatch, opt_in: str | None = None) -> None:
    monkeypatch.setenv("MAXEY0_PUBLIC", "1")
    if opt_in is None:
        monkeypatch.delenv(PUBLIC_HOST_PLANES, raising=False)
    else:
        monkeypatch.setenv(PUBLIC_HOST_PLANES, opt_in)


def _assert_discloses_nothing(result: dict, host: Host) -> None:
    text = json.dumps(result)
    assert str(host.root) not in text
    assert str(pathlib.Path.home()) not in text
    assert not _ABSOLUTE_PATH.search(text), text
    for key in ("path", "ledger", "context_ledger", "recent", "by_role", "mode"):
        assert key not in result


# --- classification ---------------------------------------------------------


def test_every_bridge_tool_is_classified_exactly_once():
    names = {t.name for t in bridge.observability_tools()}
    assert names, "the observation plane is not exposed at all"
    assert HOST_STATE_READS | HOST_STATE_WRITES | HOST_INDEPENDENT == names
    assert not HOST_STATE_READS & HOST_STATE_WRITES
    assert not (HOST_STATE_READS | HOST_STATE_WRITES) & HOST_INDEPENDENT
    assert set(READ_CALLS) == HOST_STATE_READS
    assert set(WRITE_CALLS) == HOST_STATE_WRITES


def test_the_catalog_does_not_depend_on_where_the_origin_runs(monkeypatch):
    """Tools stay listed: the edge catalog and the documented counts are one list."""
    monkeypatch.delenv("MAXEY0_PUBLIC", raising=False)
    local = [(t.name, t.capability) for t in build_surface().tools]
    _public(monkeypatch)
    public = [(t.name, t.capability) for t in build_surface().tools]
    assert public == local


def test_only_the_bridge_reaches_the_plane_implementations():
    """The check lives in the bridge, so nothing else may import the planes.

    `/v1` is served from the in-process system, not from `server/planes`; if a
    route or a second tool table ever imported the plane directly it would be a
    door around the check, and this is where that shows up.
    """
    pattern = re.compile(r"^\s*(?:from|import)\s+planes\b|observe_impl", re.MULTILINE)
    offenders = [
        path.relative_to(REPO).as_posix()
        for path in (REPO / "maxey0_ss").rglob("*.py")
        if "tests" not in path.parts and "__pycache__" not in path.parts
        and pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == ["maxey0_ss/observability/bridge.py"]


# --- local deployment: unchanged -------------------------------------------


def test_a_local_deployment_serves_host_state_as_before(host, tools):
    events = tools["maxey0-ss.observe.events"].handler({})
    assert events["available"] is True
    assert events["ledger"] == shorten_home(str(host.ledger))  # shown without the username
    activity = tools["maxey0-ss.observe.gate_activity"].handler({})
    assert activity["available"] is True
    assert activity["path"] == shorten_home(str(host.journal))  # shown without the username
    assert tools["maxey0-ss.observe.gate_mode"].handler({})["mode"] == "enforce"
    for name, args in READ_CALLS.items():
        with_host = tools[name].handler(args)
        assert with_host.get("host_planes") != "disabled", name


def test_a_local_deployment_still_writes_the_gate_policy(host, tools):
    assert tools["maxey0-ss.gate.set_mode"].handler({"mode": "observe"})["ok"] is True
    assert json.loads(host.policy.read_text(encoding="utf-8"))["mode"] == "observe"
    tools["maxey0-ss.gate.set_policy"].handler({"role": "maker"})
    assert "maker" in json.loads(host.policy.read_text(encoding="utf-8"))["roles"]


def test_the_opt_in_is_not_an_opt_out_on_a_local_deployment(host, tools, monkeypatch):
    monkeypatch.setenv(PUBLIC_HOST_PLANES, "0")
    assert tools["maxey0-ss.observe.events"].handler({})["available"] is True


# --- public deployment, no opt-in ------------------------------------------


@pytest.mark.parametrize("name", sorted(READ_CALLS))
def test_a_public_read_answers_unavailable_and_names_the_variable(name, host, tools, monkeypatch):
    _public(monkeypatch)
    result = tools[name].handler(READ_CALLS[name])
    assert result["ok"] is True
    assert result["available"] is False
    assert result["host_planes"] == "disabled"
    assert result["opt_in"] == PUBLIC_HOST_PLANES
    assert PUBLIC_HOST_PLANES in result["reason"]
    _assert_discloses_nothing(result, host)


@pytest.mark.parametrize("name", sorted(WRITE_CALLS))
def test_a_public_write_refuses_and_writes_nothing(name, host, tools, monkeypatch):
    _public(monkeypatch)
    before = host.snapshot()
    result = tools[name].handler(WRITE_CALLS[name])
    assert result["ok"] is False
    assert result["refused"] is True
    assert result["error"] == "host_planes_disabled"
    assert PUBLIC_HOST_PLANES in result["reason"]
    _assert_discloses_nothing(result, host)
    assert host.snapshot() == before
    # The mode the host's own gate hook reads is still the one the host set.
    assert json.loads(host.policy.read_text(encoding="utf-8"))["mode"] == "enforce"


def test_public_reads_leave_the_host_files_untouched(host, tools, monkeypatch):
    _public(monkeypatch)
    before = host.snapshot()
    for name, args in READ_CALLS.items():
        tools[name].handler(args)
    assert host.snapshot() == before


def test_a_refused_call_does_not_even_create_the_state_directories(tmp_path, tools, monkeypatch):
    """The journal and policy readers mkdir their parents; a refusal must precede that."""
    absent = tmp_path / "never-created"
    _point_plane_at(monkeypatch, absent)
    _public(monkeypatch)
    for name, args in {**READ_CALLS, **WRITE_CALLS}.items():
        tools[name].handler(args)
    assert not absent.exists()


def test_the_check_runs_before_the_plane_function(monkeypatch):
    """Independent of what the plane does on disk: on public it is never called."""
    called: list[str] = []

    def spy(fn_name):
        def fn(**_kwargs):
            called.append(fn_name)
            return {"ok": True, "available": True}
        fn.__name__ = fn_name
        return fn

    fake = types.SimpleNamespace(**{n: spy(n) for n in (
        "observe_events", "observe_attempts", "observe_traces",
        "observe_gate_activity", "observe_gate_mode", "observe_isolation_level",
        "observe_studio", "observe_gate_policy",
    )})
    monkeypatch.setattr(bridge, "_impl", lambda: fake)
    tools = {t.name: t for t in bridge.observability_tools()}

    _public(monkeypatch)
    for name, args in {**READ_CALLS, **WRITE_CALLS}.items():
        tools[name].handler(args)
    assert called == []

    monkeypatch.delenv("MAXEY0_PUBLIC")
    for name, args in {**READ_CALLS, **WRITE_CALLS}.items():
        tools[name].handler(args)
    assert len(called) == len(READ_CALLS) + len(WRITE_CALLS)


def test_the_studio_touches_no_host_file_and_is_served_everywhere(host, tools, monkeypatch):
    _public(monkeypatch)
    studio = tools["maxey0-ss.observe.studio"].handler({})
    assert studio["url"].startswith("http://127.0.0.1:")


# --- public deployment, opted in -------------------------------------------


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", " TRUE "])
def test_the_opt_in_serves_host_state_again(value, host, tools, monkeypatch):
    _public(monkeypatch, value)
    events = tools["maxey0-ss.observe.events"].handler({})
    assert events["available"] is True and events["ledger"] == shorten_home(str(host.ledger))  # shown without the username
    activity = tools["maxey0-ss.observe.gate_activity"].handler({})
    assert activity["available"] is True and activity["path"] == shorten_home(str(host.journal))  # shown without the username
    assert tools["maxey0-ss.gate.set_mode"].handler({"mode": "observe"})["ok"] is True
    assert json.loads(host.policy.read_text(encoding="utf-8"))["mode"] == "observe"


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "enabled"])
def test_anything_else_leaves_it_off(value, host, tools, monkeypatch):
    _public(monkeypatch, value)
    assert tools["maxey0-ss.observe.events"].handler({})["available"] is False
    assert tools["maxey0-ss.gate.set_mode"].handler({"mode": "off"})["refused"] is True


# --- over the wire ----------------------------------------------------------

_TOKENS = "op-token-1:operator,adm-token-1:admin"
SSE = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def _mcp(client, tool, args, token):
    return client.post(
        "/mcp",
        headers={"MCP-Protocol-Version": V, "Mcp-Method": "tools/call",
                 "Mcp-Name": tool, "Authorization": f"Bearer {token}"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
              "params": {"name": tool, "arguments": args}},
    )


def test_stateless_mcp_on_a_public_origin(host, monkeypatch):
    """The exact call from the finding: the shared operator token, gate_activity."""
    _public(monkeypatch)
    monkeypatch.setenv("MAXEY0_AUTH_MODE", "bearer")
    monkeypatch.setenv("MAXEY0_MCP_TOKENS", _TOKENS)
    client = TestClient(create_app())

    r = _mcp(client, "maxey0-ss.observe.gate_activity", {}, "op-token-1")
    assert r.status_code == 200
    result = r.json()["result"]["structuredContent"]
    assert result["available"] is False
    assert str(host.journal) not in r.text

    before = host.snapshot()
    r = _mcp(client, "maxey0-ss.gate.set_mode", {"mode": "off"}, "adm-token-1")
    assert r.status_code == 200
    assert r.json()["result"]["structuredContent"]["refused"] is True
    assert host.snapshot() == before

    # Authorization still comes first: the operator cannot reach the write at all.
    r = _mcp(client, "maxey0-ss.gate.set_mode", {"mode": "off"}, "op-token-1")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == -32002


def test_session_transport_on_a_public_origin(host, monkeypatch):
    _public(monkeypatch)
    monkeypatch.setenv("MAXEY0_AUTH_MODE", "bearer")
    monkeypatch.setenv("MAXEY0_MCP_TOKENS", _TOKENS)
    auth = {"Authorization": "Bearer op-token-1"}
    with TestClient(create_app()) as client:
        init = client.post("/mcp/session", headers={**SSE, **auth}, json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": "test", "version": "0"}},
        })
        session = init.headers["mcp-session-id"]
        r = client.post("/mcp/session", headers={**SSE, **auth, "mcp-session-id": session}, json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "maxey0-ss.observe.events", "arguments": {}},
        })
    data = next(json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: "))
    result = data["result"]["structuredContent"]
    assert result["available"] is False
    assert str(host.ledger) not in r.text
