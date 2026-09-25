from maxey0_ss.auth.config import AuthConfig
from maxey0_ss.auth.roles import allowed
from maxey0_ss.cache.policy import CacheHint, MCPMetadataCache


def test_auth_manifest_does_not_expose_secret_values():
    cfg = AuthConfig(default_bearer_token="secret")
    out = cfg.public_manifest()
    assert "default_bearer_token" not in str(out)
    assert "credential_values_exposed" in out
    assert out["credential_values_exposed"] is False


def test_roles_are_capability_bound():
    assert allowed("viewer", "observe")
    assert not allowed("viewer", "mcp.call.write")
    assert allowed("admin", "anything")


def test_cache_expires_deterministically():
    cache = MCPMetadataCache()
    cache.put("k", {"v": 1}, CacheHint(1, "server"))
    entry = cache.entries["k"]
    assert entry.fresh(entry.created_ms)
    assert not entry.fresh(entry.created_ms + 2)
