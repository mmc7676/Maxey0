from fastapi.testclient import TestClient

from maxey0_ss.api.app import create_app
from maxey0_ss.gating.address import EnforceableAddress


def headers(method, name=""):
    h = {"MCP-Protocol-Version": "2026-07-28", "Mcp-Method": method}
    if name:
        h["Mcp-Name"] = name
    return h


def test_explicit_address_round_trips():
    address = EnforceableAddress("maxey0", "context", "observation", "host-window", "SCW0")
    assert EnforceableAddress.parse(address.uri()) == address


def test_discover_advertises_extensions_as_map():
    c = TestClient(create_app())
    r = c.post("/mcp", headers=headers("server/discover"), json={"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": {}})
    ext = r.json()["result"]["capabilities"]["extensions"]
    assert "io.modelcontextprotocol/tasks" in ext
    assert "io.modelcontextprotocol/ui" in ext


def test_gated_tool_requires_explicit_scw_address():
    c = TestClient(create_app())
    r = c.post("/mcp", headers=headers("tools/call", "maxey0-ss.scw.observe_host_window"), json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "maxey0-ss.scw.observe_host_window", "arguments": {"segments": []}}})
    assert r.status_code == 403
    assert r.json()["error"]["message"] == "SCW address required"


def test_gated_tool_accepts_structural_address():
    c = TestClient(create_app())
    args = {"scw_address": "scw://maxey0/context/observation/host-window/SCW0", "segments": []}
    r = c.post("/mcp", headers=headers("tools/call", "maxey0-ss.scw.observe_host_window"), json={"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "maxey0-ss.scw.observe_host_window", "arguments": args}})
    assert r.status_code == 200
    assert r.json()["result"]["structuredContent"]["scope"] == "host-supplied"


def test_super_space_tool_declares_ui_resource():
    c = TestClient(create_app())
    r = c.post("/mcp", headers=headers("tools/list"), json={"jsonrpc": "2.0", "id": 4, "method": "tools/list", "params": {}})
    tool = next(x for x in r.json()["result"]["tools"] if x["name"] == "maxey0-ss.super_space")
    assert tool["_meta"]["ui"]["resourceUri"] == "ui://maxey0-ss/super-space.html"
