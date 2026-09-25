"""Authorization and evidence on the MCP surface.

Three findings from the full-repo audit: the task branch consulted no
authorizer, bearer mode disabled the stdio transport entirely, and the two
evidence tools could never agree because the verifier assumed every record list
began at GENESIS.
"""
import pytest
from fastapi.testclient import TestClient

from maxey0_ss.api.app import create_app
from maxey0_ss.auth.policy import Authorizer
from maxey0_ss.containment import Operation
from maxey0_ss.mcp_stdio_server import _stdio_principal
from maxey0_ss.mcp_surface import build_surface
from maxey0_ss.system import SuperSpaceSystem

V = "2026-07-28"


def rpc(client, method, params, tool=None, auth=None):
    headers = {"MCP-Protocol-Version": V, "Mcp-Method": method,
               "Mcp-Name": tool or params.get("taskId", "")}
    if auth:
        headers["Authorization"] = auth
    return client.post("/mcp", headers=headers,
                       json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})


# --- the task branch is authorized ------------------------------------------


def test_tasks_get_is_refused_on_a_public_deployment(monkeypatch):
    """A task carries the terminal result of the tool that produced it."""
    monkeypatch.setenv("MAXEY0_PUBLIC", "1")
    monkeypatch.setenv("MAXEY0_AUTH_MODE", "disabled")
    response = rpc(TestClient(create_app()), "tasks/get", {"taskId": "t-1"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == -32002


@pytest.mark.parametrize("method", ["tasks/get", "tasks/update", "tasks/cancel"])
def test_every_task_method_is_gated(monkeypatch, method):
    monkeypatch.setenv("MAXEY0_PUBLIC", "1")
    monkeypatch.setenv("MAXEY0_AUTH_MODE", "disabled")
    assert rpc(TestClient(create_app()), method, {"taskId": "t-1"}).status_code == 403


def test_mcp_name_must_match_params_name_for_tools_call(monkeypatch):
    """The header is what intermediaries route and meter on."""
    monkeypatch.delenv("MAXEY0_PUBLIC", raising=False)
    monkeypatch.setenv("MAXEY0_AUTH_MODE", "disabled")
    client = TestClient(create_app())
    response = client.post(
        "/mcp",
        headers={"MCP-Protocol-Version": V, "Mcp-Method": "tools/call",
                 "Mcp-Name": "maxey0-ss.health"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
              "params": {"name": "maxey0-ss.deployment", "arguments": {}}},
    )
    assert response.status_code == 400
    assert "Mcp-Name must equal params.name" in response.json()["error"]["message"]


def test_agreeing_header_and_name_still_work(monkeypatch):
    monkeypatch.delenv("MAXEY0_PUBLIC", raising=False)
    monkeypatch.setenv("MAXEY0_AUTH_MODE", "disabled")
    client = TestClient(create_app())
    response = rpc(client, "tools/call",
                   {"name": "maxey0-ss.health", "arguments": {}}, tool="maxey0-ss.health")
    assert response.status_code == 200


# --- stdio stays usable ------------------------------------------------------


def test_bearer_mode_does_not_disable_stdio(monkeypatch):
    """principal(None) raised before the capability was ever consulted."""
    monkeypatch.delenv("MAXEY0_PUBLIC", raising=False)
    monkeypatch.setenv("MAXEY0_AUTH_MODE", "bearer")
    assert _stdio_principal(Authorizer()).role == "admin"


def test_a_public_stdio_deployment_is_anonymous(monkeypatch):
    monkeypatch.setenv("MAXEY0_PUBLIC", "1")
    monkeypatch.setenv("MAXEY0_AUTH_MODE", "bearer")
    assert _stdio_principal(Authorizer()).role == "public"


# --- the evidence tools agree ------------------------------------------------


def surface_with_a_denial():
    system = SuperSpaceSystem()
    system.context.isolation.decide(Operation.READ, "SCW1@rt", "SCW9@rt")
    return {t.name: t for t in build_surface(system).tools}


def test_an_exported_segment_verifies():
    """A slice was always reported broken: the verifier assumed GENESIS."""
    tools = surface_with_a_denial()
    exported = tools["maxey0-ss.evidence.attestations"].handler({"limit": 2})
    result = tools["maxey0-ss.evidence.verify"].handler({
        "records": exported["attestations"],
        "anchor_prev_digest": exported["anchor_prev_digest"],
        "start_seq": exported["start_seq"],
    })
    assert result["ok"] is True


def test_the_export_carries_its_own_anchor():
    exported = surface_with_a_denial()["maxey0-ss.evidence.attestations"].handler({"limit": 2})
    assert "anchor_prev_digest" in exported and "start_seq" in exported


def test_a_filtered_view_says_it_is_not_chain_verifiable():
    """Denials are not adjacent, so the view is a filter, not a segment."""
    exported = surface_with_a_denial()["maxey0-ss.evidence.attestations"].handler(
        {"denials_only": True}
    )
    assert exported["attestations"]
    assert exported["chain_verifiable"] is False


def test_public_verify_will_not_read_the_live_log():
    """It returned the entry count and head that evidence.summary gates."""
    result = surface_with_a_denial()["maxey0-ss.evidence.verify"].handler({})
    assert result["ok"] is False
    assert "records is required" in result["error"]
    assert "entries" not in result and "head" not in result


def test_a_tampered_segment_still_fails():
    tools = surface_with_a_denial()
    exported = tools["maxey0-ss.evidence.attestations"].handler({"limit": 3})
    records = [dict(r) for r in exported["attestations"]]
    records[-1]["reason"] = "edited after the fact"
    result = tools["maxey0-ss.evidence.verify"].handler({
        "records": records,
        "anchor_prev_digest": exported["anchor_prev_digest"],
        "start_seq": exported["start_seq"],
    })
    assert result["ok"] is False
