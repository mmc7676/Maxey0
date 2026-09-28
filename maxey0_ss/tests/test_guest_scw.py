"""Guest access: anonymous callers use their own SCWs and nothing else.

MAXEY0_GUEST_SCW=1 lets a caller with no Authorization header create, start,
drift, describe and close SCWs on the stateless endpoint. Everything that
matters here is a boundary: off by default, a wrong token is never downgraded
to a guest, a guest never reaches a tool outside the SCW set (model egress
above all), one guest never sees or touches another's SCWs, and the caps hold.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from maxey0_ss.api.app import create_app
from maxey0_ss.mcp_2026 import MCP_VERSION
from maxey0_ss.mcp_surface import build_surface
from maxey0_ss.tasks import owned_by

TOKEN_HASH = "sha256:" + "a" * 64 + ":admin:ops"


def _call(client, name, arguments=None, token=None):
    headers = {"MCP-Protocol-Version": MCP_VERSION, "Mcp-Method": "tools/call",
               "Mcp-Name": name}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}}}
    return client.post("/mcp", json=body, headers=headers)


@pytest.fixture
def public_bearer(monkeypatch, tmp_path):
    monkeypatch.setenv("MAXEY0_PUBLIC", "1")
    monkeypatch.setenv("MAXEY0_AUTH_MODE", "bearer")
    monkeypatch.setenv("MAXEY0_MCP_TOKEN_HASHES", TOKEN_HASH)
    monkeypatch.delenv("MAXEY0_MCP_TOKENS", raising=False)
    monkeypatch.setenv("SCW_HOME", str(tmp_path / "scw"))
    for name in ("MAXEY0_GUEST_SCW", "MAXEY0_GUEST_SCW_PER_CLIENT", "MAXEY0_GUEST_SCW_TOTAL"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def _structured(response):
    body = response.json()
    assert "result" in body, body
    return body["result"]["structuredContent"]


def test_off_by_default_a_caller_without_a_token_is_refused(public_bearer):
    client = TestClient(create_app())
    response = _call(client, "maxey0-ss.scw.create", {"task": "t"})
    assert response.status_code == 401


def test_a_guest_runs_the_whole_lifecycle(public_bearer):
    public_bearer.setenv("MAXEY0_GUEST_SCW", "1")
    client = TestClient(create_app())
    created = _structured(_call(client, "maxey0-ss.scw.create", {"task": "summarize"}))
    scw_id = created["id"]
    assert scw_id.startswith("SCW") and scw_id[3:].isdigit()
    started = _structured(_call(client, "maxey0-ss.scw.start", {"scw_id": scw_id}))
    assert started["scw_id"] == scw_id and started["owner"].startswith("guest:")
    assert _structured(_call(client, "maxey0-ss.scw.drift",
                             {"scw_id": scw_id, "vector": [0.1, 0.2], "anchor": True}))["anchored"]
    measured = _structured(_call(client, "maxey0-ss.scw.drift",
                                 {"scw_id": scw_id, "vector": [0.1, 0.25]}))
    assert isinstance(measured["distance"], float)
    described = _structured(_call(client, "maxey0-ss.scw.describe"))
    assert list(described["specifications"]) == [scw_id]
    closed = _structured(_call(client, "maxey0-ss.scw.close", {"scw_id": started["started"]}))
    assert closed["closed"] == started["started"]


def test_a_guest_never_reaches_a_tool_outside_the_scw_set(public_bearer):
    public_bearer.setenv("MAXEY0_GUEST_SCW", "1")
    client = TestClient(create_app())
    for name, arguments in (
        ("maxey0-ss.provider.complete", {"provider": "anthropic", "prompt": "hi"}),
        ("maxey0-ss.evidence.attestations", {}),
        ("maxey0-ss.gate.set_mode", {"mode": "off"}),
    ):
        response = _call(client, name, arguments)
        assert response.status_code == 403, (name, response.json())
        assert response.json()["error"]["code"] == -32002


def test_public_tools_still_answer_a_guest(public_bearer):
    public_bearer.setenv("MAXEY0_GUEST_SCW", "1")
    client = TestClient(create_app())
    assert _call(client, "maxey0-ss.health").status_code == 200


def test_a_wrong_token_is_never_downgraded_to_a_guest(public_bearer):
    public_bearer.setenv("MAXEY0_GUEST_SCW", "1")
    client = TestClient(create_app())
    response = _call(client, "maxey0-ss.scw.create", {"task": "t"}, token="not-a-token")
    assert response.status_code == 401


def test_guests_see_and_touch_only_their_own_scws(public_bearer):
    public_bearer.setenv("MAXEY0_GUEST_SCW", "1")
    surface = build_surface()
    tools = {t.name: t.handler for t in surface.tools}
    with owned_by("guest:aaaa"):
        mine = tools["maxey0-ss.scw.create"]({"task": "a"})["id"]
        started = tools["maxey0-ss.scw.start"]({"scw_id": mine})["started"]
    with owned_by("guest:bbbb"):
        assert tools["maxey0-ss.scw.describe"]({}) == {"specifications": {}}
        for name, arguments in (
            ("maxey0-ss.scw.start", {"scw_id": mine}),
            ("maxey0-ss.scw.close", {"scw_id": started}),
            ("maxey0-ss.scw.drift", {"scw_id": mine, "vector": [1.0], "anchor": True}),
            ("maxey0-ss.scw.create", {"task": "b", "parent_id": mine}),
        ):
            with pytest.raises(ValueError, match="Unknown SCW"):
                tools[name](arguments)
    with owned_by("admin:ops"):
        # A token holder is unaffected: it sees every SCW, guests' included.
        assert mine in tools["maxey0-ss.scw.describe"]({})["specifications"]


def test_the_caps_hold(public_bearer):
    public_bearer.setenv("MAXEY0_GUEST_SCW", "1")
    public_bearer.setenv("MAXEY0_GUEST_SCW_PER_CLIENT", "2")
    public_bearer.setenv("MAXEY0_GUEST_SCW_TOTAL", "3")
    tools = {t.name: t.handler for t in build_surface().tools}
    with owned_by("guest:aaaa"):
        tools["maxey0-ss.scw.create"]({"task": "1"})
        tools["maxey0-ss.scw.create"]({"task": "2"})
        with pytest.raises(ValueError, match="guest limit reached"):
            tools["maxey0-ss.scw.create"]({"task": "3"})
    with owned_by("guest:bbbb"):
        tools["maxey0-ss.scw.create"]({"task": "4"})
        with pytest.raises(ValueError, match="capacity"):
            tools["maxey0-ss.scw.create"]({"task": "5"})


def test_a_malformed_cap_refuses_to_start(public_bearer):
    public_bearer.setenv("MAXEY0_GUEST_SCW_TOTAL", "lots")
    with pytest.raises(ValueError, match="MAXEY0_GUEST_SCW_TOTAL"):
        build_surface()
