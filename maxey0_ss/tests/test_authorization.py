"""Authorization: the public endpoint must not be world-writable.

Finding that motivated these tests: with auth disabled and an origin reachable
from the edge, `scw.create`, `scw.close` and the gate-mode writes were callable
by anyone who could resolve the hostname.
"""
import pytest
from fastapi.testclient import TestClient

from maxey0_ss.api.app import create_app
from maxey0_ss.auth.policy import (
    ANONYMOUS,
    GATE_WRITE,
    OBSERVE_READ,
    SCW_CREATE,
    AuthError,
    Authorizer,
    Principal,
)
from maxey0_ss.mcp_surface import build_surface

V = "2026-07-28"


def call(client, tool, args=None, auth=None):
    headers = {"MCP-Protocol-Version": V, "Mcp-Method": "tools/call", "Mcp-Name": tool}
    if auth:
        headers["Authorization"] = auth
    return client.post(
        "/mcp",
        headers=headers,
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
              "params": {"name": tool, "arguments": args or {}}},
    )


# --- capability declarations ------------------------------------------------


def test_no_state_changing_tool_is_public():
    """The core invariant. A public tool may not mutate anything."""
    mutating = {
        "maxey0-ss.scw.create", "maxey0-ss.scw.close",
        "maxey0-ss.gate.set_mode", "maxey0-ss.gate.set_policy",
        "maxey0-ss.gate.declare_isolation",
    }
    for tool in build_surface().tools:
        if tool.name in mutating:
            assert tool.capability is not None, f"{tool.name} is world-callable"


def test_gate_writes_are_admin_only(subtests):
    """No non-admin role holds gate.write, so these are admin-only by construction."""
    for role in ("public", "viewer", "operator", "builder"):
        with subtests.test(role=role):
            assert not Principal(role=role).may(GATE_WRITE)
    assert Principal(role="admin").may(GATE_WRITE)


def test_observability_requires_a_capability():
    observe = [t for t in build_surface().tools if t.name.startswith("maxey0-ss.observe.")]
    assert observe, "observability plane is not exposed at all"
    assert all(t.capability == OBSERVE_READ for t in observe)


def test_the_public_tier_is_read_only_metadata():
    public = [t.name for t in build_surface().tools if t.capability is None]
    assert "maxey0-ss.health" in public
    assert "maxey0-ss.scw.create" not in public
    assert not any(n.startswith("maxey0-ss.gate.set") for n in public)


# --- principals -------------------------------------------------------------


def test_local_deployment_stays_admin(monkeypatch):
    """A developer machine must keep working exactly as before."""
    monkeypatch.delenv("MAXEY0_PUBLIC", raising=False)
    monkeypatch.setenv("MAXEY0_AUTH_MODE", "disabled")
    assert Authorizer().principal(None).role == "admin"


def test_a_public_deployment_without_auth_is_anonymous(monkeypatch):
    """Fail closed: internet-reachable and unconfigured means public tools only."""
    monkeypatch.setenv("MAXEY0_PUBLIC", "1")
    monkeypatch.setenv("MAXEY0_AUTH_MODE", "disabled")
    principal = Authorizer().principal(None)
    assert principal.role == "public"
    assert principal.may(None)
    assert not principal.may(SCW_CREATE)
    assert not principal.may(OBSERVE_READ)


def test_bearer_mode_requires_credentials(monkeypatch):
    monkeypatch.setenv("MAXEY0_AUTH_MODE", "bearer")
    with pytest.raises(AuthError) as e:
        Authorizer().principal(None)
    assert e.value.status == 401


def test_bearer_mode_rejects_an_unknown_token(monkeypatch):
    monkeypatch.setenv("MAXEY0_AUTH_MODE", "bearer")
    monkeypatch.setenv("MAXEY0_MCP_TOKENS", "good:operator")
    with pytest.raises(AuthError):
        Authorizer().principal("Bearer wrong")
    assert Authorizer().principal("Bearer good").role == "operator"


def test_a_shared_default_token_is_not_an_admin(monkeypatch):
    """One shared secret must not be able to turn the gate off."""
    monkeypatch.setenv("MAXEY0_AUTH_MODE", "bearer")
    monkeypatch.delenv("MAXEY0_MCP_TOKENS", raising=False)
    monkeypatch.setenv("MAXEY0_MCP_DEFAULT_BEARER_TOKEN", "shared")
    principal = Authorizer().principal("Bearer shared")
    assert principal.role == "operator"
    assert not principal.may(GATE_WRITE)


def test_oidc_refuses_rather_than_falling_back(monkeypatch):
    """OIDC is implemented at 0.3.0; MISconfigured OIDC still refuses.

    The refusal changed meaning rather than going away. It used to mean "this
    build cannot verify tokens". It now means "you asked for OIDC and did not
    say which issuer" -- and it is still a refusal, because a deployment that
    asked for identity-provider-backed authorization and silently got a shared
    secret, or nothing, is worse off than one that failed to start.
    """
    monkeypatch.setenv("MAXEY0_AUTH_MODE", "oidc")
    for name in ("MAXEY0_JWT_ISSUER", "MAXEY0_JWT_AUDIENCE", "MAXEY0_JWKS_URL"):
        monkeypatch.setenv(name, "")
    with pytest.raises(AuthError) as e:
        Authorizer().principal("Bearer anything")
    assert e.value.status == 501
    assert "not configured" in str(e.value)
    # It names what is missing, rather than only that something is.
    assert "MAXEY0_JWT_ISSUER" in str(e.value)


def test_misconfigured_oidc_does_not_degrade_to_bearer(monkeypatch):
    """The failure mode the refusal exists to prevent."""
    monkeypatch.setenv("MAXEY0_AUTH_MODE", "oidc")
    monkeypatch.setenv("MAXEY0_MCP_TOKENS", "sometoken:admin")
    for name in ("MAXEY0_JWT_ISSUER", "MAXEY0_JWT_AUDIENCE", "MAXEY0_JWKS_URL"):
        monkeypatch.setenv(name, "")
    with pytest.raises(AuthError):
        Authorizer().principal("Bearer sometoken")


def test_anonymous_holds_nothing_beyond_public():
    assert ANONYMOUS.may(None)
    for cap in (OBSERVE_READ, SCW_CREATE, GATE_WRITE):
        assert not ANONYMOUS.may(cap)


# --- over the wire ----------------------------------------------------------


def test_public_tools_work_unauthenticated(monkeypatch):
    monkeypatch.setenv("MAXEY0_PUBLIC", "1")
    monkeypatch.setenv("MAXEY0_AUTH_MODE", "disabled")
    c = TestClient(create_app())
    r = call(c, "maxey0-ss.health")
    assert r.status_code == 200
    assert r.json()["result"]["structuredContent"]["ok"] is True


def test_scw_create_is_refused_on_a_public_deployment(monkeypatch):
    monkeypatch.setenv("MAXEY0_PUBLIC", "1")
    monkeypatch.setenv("MAXEY0_AUTH_MODE", "disabled")
    c = TestClient(create_app())
    r = call(c, "maxey0-ss.scw.create", {"scw_id": "SCW99", "task": "unauthorized"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == -32002
    assert "result" not in r.json()


def test_gate_set_mode_is_refused_on_a_public_deployment(monkeypatch):
    """Turning the gate off must never be reachable anonymously."""
    monkeypatch.setenv("MAXEY0_PUBLIC", "1")
    monkeypatch.setenv("MAXEY0_AUTH_MODE", "disabled")
    c = TestClient(create_app())
    r = call(c, "maxey0-ss.gate.set_mode", {"mode": "off"})
    assert r.status_code == 403


def test_authorization_precedes_the_scw_gate(monkeypatch):
    """An unauthorized caller must not even reach the gate check."""
    monkeypatch.setenv("MAXEY0_PUBLIC", "1")
    monkeypatch.setenv("MAXEY0_AUTH_MODE", "disabled")
    c = TestClient(create_app())
    r = call(c, "maxey0-ss.scw.observe_host_window", {"scw_address": "malformed", "segments": []})
    assert r.status_code == 403
    # -32002 is "capability denied"; -32001 would mean it reached the SCW gate.
    assert r.json()["error"]["code"] == -32002


def test_the_manifest_says_whether_enforcement_is_on(monkeypatch):
    monkeypatch.setenv("MAXEY0_PUBLIC", "1")
    monkeypatch.setenv("MAXEY0_AUTH_MODE", "disabled")
    manifest = Authorizer().manifest()
    assert manifest["enforced"] is True
    assert manifest["oidc_implemented"] is True
    assert manifest["credential_values_exposed"] is False
