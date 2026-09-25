"""`scw.drift` measures under scw.read and anchors under scw.admit.

Anchoring installs the baseline every later measurement is judged against, so
it is a write: a caller who may anchor can make a drifted window read as
healthy by re-anchoring it where it now is. REST's `/anchor` route already
demanded scw.admit. Over MCP the tool declared scw.read and nothing looked at
the arguments, so the operator role -- which the shared default bearer token
maps to -- could anchor. Both transports are checked here: stateless /mcp,
and the session path that stdio and /mcp/session share.
"""
from __future__ import annotations

import json

import anyio
import pytest
from fastapi.testclient import TestClient

from maxey0_ss.api.app import create_app
from maxey0_ss.auth.policy import SCW_ADMIT, SCW_READ, Principal
from maxey0_ss.mcp_2026 import Tool
from maxey0_ss.mcp_surface import build_surface

V = "2026-07-28"
DRIFT = "maxey0-ss.scw.drift"
TOKENS = "op-token-1:operator,bld-token-1:builder"
OPERATOR, BUILDER = "op-token-1", "bld-token-1"
SSE = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def _drift_tool() -> Tool:
    return next(t for t in build_surface().tools if t.name == DRIFT)


# --- the declaration --------------------------------------------------------


def test_the_catalog_still_declares_scw_read():
    """The declared tier is what the catalog and the distribution table report."""
    tool = _drift_tool()
    assert tool.capability == SCW_READ
    assert "scw.admit" in tool.description
    assert "scw.admit" in tool.input_schema["properties"]["anchor"]["description"]


@pytest.mark.parametrize("arguments, expected", [
    ({"scw_id": "S", "vector": [1.0]}, (SCW_READ,)),
    ({"scw_id": "S", "vector": [1.0], "anchor": False}, (SCW_READ,)),
    ({"scw_id": "S", "vector": [1.0], "anchor": True}, (SCW_READ, SCW_ADMIT)),
    # /mcp does not validate the schema, and the handler anchors on truthiness.
    ({"scw_id": "S", "vector": [1.0], "anchor": "no"}, (SCW_READ, SCW_ADMIT)),
    ([], (SCW_READ,)),
])
def test_anchoring_adds_scw_admit(arguments, expected):
    assert _drift_tool().required_capabilities(arguments) == expected


def test_a_tool_without_the_hook_needs_only_its_declared_capability():
    tool = Tool("t", "d", {"type": "object"}, lambda _a: None, capability="observe")
    assert tool.required_capabilities({"anchor": True}) == ("observe",)
    assert Tool("p", "d", {}, lambda _a: None).required_capabilities({}) == (None,)


def test_the_hook_can_only_add_to_the_declared_tier():
    """Both are authorized, so an argument hook cannot make a call cheaper."""
    tool = Tool("t", "d", {}, lambda _a: None, capability=SCW_ADMIT,
                argument_capability=lambda _a: SCW_READ)
    assert SCW_ADMIT in tool.required_capabilities({})


# --- stateless /mcp ---------------------------------------------------------


def _call(client, token, arguments, tool=DRIFT):
    return client.post(
        "/mcp",
        headers={"MCP-Protocol-Version": V, "Mcp-Method": "tools/call",
                 "Mcp-Name": tool, "Authorization": f"Bearer {token}"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
              "params": {"name": tool, "arguments": arguments}},
    )


@pytest.fixture
def bearer(monkeypatch):
    monkeypatch.delenv("MAXEY0_PUBLIC", raising=False)
    monkeypatch.setenv("MAXEY0_AUTH_MODE", "bearer")
    monkeypatch.setenv("MAXEY0_MCP_TOKENS", TOKENS)


@pytest.fixture
def client(bearer):
    c = TestClient(create_app())
    r = _call(c, BUILDER, {"scw_id": "SCW71", "task": "t"}, tool="maxey0-ss.scw.create")
    assert r.status_code == 200, r.text
    return c


def test_operator_can_measure(client):
    r = _call(client, OPERATOR, {"scw_id": "SCW71", "vector": [1.0, 0.0]})
    assert r.status_code == 200
    assert r.json()["result"]["structuredContent"]["anchored"] is False


@pytest.mark.parametrize("anchor", [True, "yes"])
def test_operator_cannot_anchor(client, anchor):
    r = _call(client, OPERATOR, {"scw_id": "SCW71", "vector": [1.0, 0.0], "anchor": anchor})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == -32002
    assert "scw.admit" in r.json()["error"]["message"]
    # Refused before the handler: the window is still un-anchored.
    measured = _call(client, OPERATOR, {"scw_id": "SCW71", "vector": [1.0, 0.0]})
    assert measured.json()["result"]["structuredContent"]["anchored"] is False


def test_builder_can_anchor_and_operator_then_measures(client):
    r = _call(client, BUILDER, {"scw_id": "SCW71", "vector": [1.0, 0.0], "anchor": True})
    assert r.status_code == 200
    assert r.json()["result"]["structuredContent"]["anchored"] is True
    measured = _call(client, OPERATOR, {"scw_id": "SCW71", "vector": [0.0, 1.0]})
    out = measured.json()["result"]["structuredContent"]
    assert out["anchored"] is True and out["drifted"] is True


def test_capability_is_checked_before_the_arguments_are(client):
    """A refused anchor on an unknown SCW is -32002, not the handler's ValueError."""
    r = _call(client, OPERATOR, {"scw_id": "SCW79", "vector": [1.0], "anchor": True})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == -32002


# --- the session path: /mcp/session and stdio -------------------------------


def _session_call(c, session_id, token, arguments, req_id):
    r = c.post(
        "/mcp/session",
        headers={**SSE, "mcp-session-id": session_id, "Authorization": f"Bearer {token}"},
        json={"jsonrpc": "2.0", "id": req_id, "method": "tools/call",
              "params": {"name": DRIFT, "arguments": arguments}},
    )
    assert r.status_code == 200
    data = next(line for line in r.text.splitlines() if line.startswith("data: "))
    return json.loads(data[len("data: "):])["result"]


def test_session_transport_applies_the_same_rule(bearer):
    with TestClient(create_app()) as c:
        init = c.post("/mcp/session", headers={**SSE, "Authorization": f"Bearer {BUILDER}"}, json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": "test", "version": "0"}},
        })
        sid = init.headers["mcp-session-id"]
        # The session transport serves this same surface object.
        create = next(t for t in c.app.state.maxey0_surface.tools if t.name == "maxey0-ss.scw.create")
        create.handler({"scw_id": "SCW72", "task": "t"})

        # The session SDK folds a handler exception into a soft tool error, so
        # the -32002 code is not on the wire here; the Authorizer's message is.
        denied = _session_call(c, sid, OPERATOR, {"scw_id": "SCW72", "vector": [1.0], "anchor": True}, 2)
        assert denied["isError"] is True
        assert "requires capability 'scw.admit'" in denied["content"][0]["text"]

        measured = _session_call(c, sid, OPERATOR, {"scw_id": "SCW72", "vector": [1.0]}, 3)
        assert measured.get("isError") is not True
        assert measured["structuredContent"]["anchored"] is False

        anchored = _session_call(c, sid, BUILDER, {"scw_id": "SCW72", "vector": [1.0], "anchor": True}, 4)
        assert anchored.get("isError") is not True
        assert anchored["structuredContent"]["anchored"] is True


def _stdio_call(role: str, arguments: dict):
    """Drive the stdio server's own tools/call handler as `role`."""
    import mcp.types as types

    from maxey0_ss.mcp_stdio_server import build_server

    surface = build_surface()
    next(t for t in surface.tools if t.name == "maxey0-ss.scw.create").handler(
        {"scw_id": "SCW73", "task": "t"})
    server = build_server(surface=surface, principal_resolver=lambda _a: Principal(role=role))
    handler = server.request_handlers[types.CallToolRequest]
    request = types.CallToolRequest(
        method="tools/call",
        params=types.CallToolRequestParams(name=DRIFT, arguments=arguments),
    )
    return anyio.run(handler, request).root


def test_stdio_refuses_an_operator_anchor():
    result = _stdio_call("operator", {"scw_id": "SCW73", "vector": [1.0], "anchor": True})
    assert result.isError is True
    assert "requires capability 'scw.admit'" in result.content[0].text


def test_stdio_lets_an_operator_measure_and_a_builder_anchor():
    measured = _stdio_call("operator", {"scw_id": "SCW73", "vector": [1.0]})
    assert not measured.isError
    assert measured.structuredContent["anchored"] is False
    anchored = _stdio_call("builder", {"scw_id": "SCW73", "vector": [1.0], "anchor": True})
    assert not anchored.isError
    assert anchored.structuredContent["anchored"] is True
