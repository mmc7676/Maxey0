"""The two transports must expose one surface.

`mcp_public_server` (2026-07-28 stateless HTTP) and `mcp_stdio_server` (classic
session stdio) are different protocols for the same Maxey0 tools. These tests
exist so a tool added for one cannot quietly go missing from the other.
"""
import hashlib
import json

from fastapi.testclient import TestClient

from maxey0_ss.api.app import create_app
from maxey0_ss.mcp_surface import (
    SUPER_SPACE_URI,
    build_surface,
    super_space_artifact,
    super_space_html,
)


def _http_tool_names():
    c = TestClient(create_app())
    r = c.post(
        "/mcp",
        headers={"MCP-Protocol-Version": "2026-07-28", "Mcp-Method": "tools/list"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    return [t["name"] for t in r.json()["result"]["tools"]]


def test_http_transport_serves_the_shared_surface():
    assert _http_tool_names() == [t.name for t in build_surface().tools]


def test_stdio_transport_serves_the_same_tools_as_http():
    from maxey0_ss.mcp_stdio_server import build_server

    build_server()  # must construct without a live host
    assert _http_tool_names() == [t.name for t in build_surface().tools]


def test_the_app_tool_is_linked_to_the_app_resource():
    surface = build_surface()
    tool = next(t for t in surface.tools if t.name == "maxey0-ss.super_space")
    assert tool.meta["ui"]["resourceUri"] == SUPER_SPACE_URI
    assert any(r.uri == SUPER_SPACE_URI for r in surface.resources)


def test_host_window_tool_requires_an_scw_address():
    surface = build_surface()
    tool = next(t for t in surface.tools if t.name == "maxey0-ss.scw.observe_host_window")
    assert tool.requires_scw is True
    assert "scw_address" in tool.input_schema["required"]


def test_artifact_identity_matches_the_bytes_actually_served():
    art = super_space_artifact()
    served = super_space_html().encode("utf-8")
    assert art["kind"] in {"built", "fallback-stub"}
    assert art["sha256"] == hashlib.sha256(served).hexdigest()
    assert art["uri"] == SUPER_SPACE_URI


def test_health_reports_the_artifact_it_is_serving():
    surface = build_surface()
    health = next(t for t in surface.tools if t.name == "maxey0-ss.health")
    payload = health.handler({})
    assert payload["mcp_protocol"] == "2026-07-28"
    assert payload["app_artifact"]["sha256"] == super_space_artifact()["sha256"]


def test_scw_identifiers_are_application_state_not_processes():
    """SCW0..SCWn are records in one graph, created in-process."""
    surface = build_surface()
    create = next(t for t in surface.tools if t.name == "maxey0-ss.scw.create")
    describe = next(t for t in surface.tools if t.name == "maxey0-ss.scw.describe")
    create.handler({"scw_id": "SCW0", "task": "root"})
    create.handler({"scw_id": "SCW1", "task": "child", "parent_id": "SCW0"})
    specs = describe.handler({})["specifications"]
    assert specs["SCW1"]["parent_id"] == "SCW0"
    assert json.dumps(specs)  # serializable, i.e. plain application state
