"""The session-based Streamable HTTP transport at /mcp/session.

Claude Code and Claude Desktop's remote-connector UI open a session
(`initialize`/`initialized`, `Mcp-Session-Id`) that the stateless /mcp
transport refuses by design (see test_mcp_2026_updated.py). This is the same
shared surface — same tools, same Authorizer policy — over the transport those
hosts actually speak. The handshake itself is SDK machinery (streamable_http);
what's specific to this module and worth asserting here is that tool calls
resolve to the *shared* surface, and that the per-request auth this module
adds (stdio has none; this transport is reachable over a public tunnel and
must not be weaker than the stateless one) actually gates them.
"""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from maxey0_ss.api.app import create_app

SSE_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def _initialize(client: TestClient, req_id: int = 1):
    return client.post(
        "/mcp/session",
        headers=SSE_HEADERS,
        json={
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        },
    )


def _sse_json(response) -> dict:
    """The SDK answers a POST with one SSE `message` event; pull its JSON out."""
    for line in response.text.splitlines():
        if line.startswith("data: "):
            return json.loads(line[len("data: "):])
    raise AssertionError(f"no SSE data line in response: {response.text!r}")


def _open_session(client: TestClient) -> str:
    init = _initialize(client)
    assert init.status_code == 200, init.text
    session_id = init.headers.get("mcp-session-id")
    assert session_id
    return session_id


def _call_tool(client: TestClient, session_id: str, name: str, arguments: dict, req_id: int = 2):
    return client.post(
        "/mcp/session",
        headers={**SSE_HEADERS, "mcp-session-id": session_id},
        json={"jsonrpc": "2.0", "id": req_id, "method": "tools/call", "params": {"name": name, "arguments": arguments}},
    )


def test_initialize_opens_a_real_session_with_a_handshake():
    """Unlike /mcp, this transport answers initialize instead of -32601."""
    with TestClient(create_app()) as c:
        r = _initialize(c)
        assert r.status_code == 200
        assert r.headers.get("mcp-session-id")
        body = _sse_json(r)
        assert body["result"]["serverInfo"] == {"name": "Maxey0-SuperSpace", "version": "0.3.0"}


def test_tool_call_reaches_the_same_shared_surface_as_the_stateless_transport():
    with TestClient(create_app()) as c:
        session_id = _open_session(c)
        r = _call_tool(c, session_id, "maxey0-ss.health", {})
        assert r.status_code == 200
        body = _sse_json(r)
        assert body["result"]["structuredContent"]["ok"] is True
        assert body["result"]["structuredContent"]["mcp_protocol"] == "2026-07-28"


def test_unknown_session_id_is_refused_not_silently_admitted():
    with TestClient(create_app()) as c:
        r = _call_tool(c, "not-a-real-session", "maxey0-ss.health", {})
        assert r.status_code == 404


def test_gated_tool_still_requires_an_explicit_scw_address():
    """Same admission rule as stdio and the stateless transport — parity, not a looser path.

    The SDK's Server.call_tool() validates arguments against inputSchema before
    this module's handler ever runs, so a missing required property is refused
    at that layer — a soft CallToolResult(isError=True), not a JSON-RPC error;
    see the note in mcp_stdio_server.build_server about what this handler can
    and cannot produce.
    """
    with TestClient(create_app()) as c:
        session_id = _open_session(c)
        r = _call_tool(c, session_id, "maxey0-ss.scw.observe_host_window", {"segments": []})
        assert r.status_code == 200
        body = _sse_json(r)
        result = body["result"]
        assert result["isError"] is True
        assert "scw_address" in result["content"][0]["text"]


def test_bearer_mode_refuses_a_tool_call_with_no_token(monkeypatch):
    """The one thing stdio's principal resolver could never do: actually refuse.

    stdio has no Authorization header to read, so it falls back to local trust.
    This transport crosses a public tunnel the same as /mcp, so it must not be
    reachable under weaker conditions — MAXEY0_AUTH_MODE=bearer refuses it.
    """
    monkeypatch.setenv("MAXEY0_AUTH_MODE", "bearer")
    monkeypatch.setenv("MAXEY0_MCP_TOKENS", "s3cr3t:operator")
    with TestClient(create_app()) as c:
        session_id = _open_session(c)
        r = _call_tool(c, session_id, "maxey0-ss.health", {})
        assert r.status_code == 200  # transport-level 200; the refusal is inside a soft tool result
        body = _sse_json(r)
        result = body["result"]
        assert result["isError"] is True
        assert "Bearer credentials required" in result["content"][0]["text"]


def test_bearer_mode_accepts_a_valid_token_per_request():
    import os

    os.environ["MAXEY0_AUTH_MODE"] = "bearer"
    os.environ["MAXEY0_MCP_TOKENS"] = "s3cr3t:operator"
    try:
        with TestClient(create_app()) as c:
            session_id = _open_session(c)
            r = c.post(
                "/mcp/session",
                headers={**SSE_HEADERS, "mcp-session-id": session_id, "Authorization": "Bearer s3cr3t"},
                json={
                    "jsonrpc": "2.0", "id": 2, "method": "tools/call",
                    "params": {"name": "maxey0-ss.health", "arguments": {}},
                },
            )
            assert r.status_code == 200
            body = _sse_json(r)
            assert body["result"]["structuredContent"]["ok"] is True
    finally:
        os.environ.pop("MAXEY0_AUTH_MODE", None)
        os.environ.pop("MAXEY0_MCP_TOKENS", None)


def test_operator_token_cannot_reach_admin_only_capability():
    """Same role/capability table as every other transport — no shortcut here."""
    import os

    os.environ["MAXEY0_AUTH_MODE"] = "bearer"
    os.environ["MAXEY0_MCP_TOKENS"] = "s3cr3t:operator"
    try:
        with TestClient(create_app()) as c:
            session_id = _open_session(c)
            r = c.post(
                "/mcp/session",
                headers={**SSE_HEADERS, "mcp-session-id": session_id, "Authorization": "Bearer s3cr3t"},
                json={
                    "jsonrpc": "2.0", "id": 2, "method": "tools/call",
                    "params": {"name": "maxey0-ss.gate.set_mode", "arguments": {"mode": "enforce"}},
                },
            )
            assert r.status_code == 200
            body = _sse_json(r)
            result = body["result"]
            assert result["isError"] is True
            assert "does not hold it" in result["content"][0]["text"]
    finally:
        os.environ.pop("MAXEY0_AUTH_MODE", None)
        os.environ.pop("MAXEY0_MCP_TOKENS", None)
