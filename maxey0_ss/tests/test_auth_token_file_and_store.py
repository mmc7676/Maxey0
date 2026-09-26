"""Cluster auth: token-file hot reload, sqlite rate-limit store, binding list."""
from __future__ import annotations

import os

import pytest

from maxey0_ss.auth import policy
from maxey0_ss.auth.config import AuthConfig
from maxey0_ss.auth.policy import AuthError, Authorizer, token_hash_entry
from maxey0_ss.ratelimit import RateLimitConfig, RateLimiter, SQLiteTokenBuckets


@pytest.fixture
def bearer_env(monkeypatch, tmp_path):
    for var in ("MAXEY0_MCP_TOKEN_HASHES", "MAXEY0_MCP_TOKENS",
                "MAXEY0_MCP_DEFAULT_BEARER_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("MAXEY0_AUTH_MODE", "bearer")
    path = tmp_path / "tokens"
    monkeypatch.setenv("MAXEY0_MCP_TOKEN_HASHES_FILE", str(path))
    return path


def _write(path, text, bump):
    path.write_text(text, encoding="utf-8")
    st = os.stat(path)
    os.utime(path, (st.st_atime, st.st_mtime + bump))


def _auth(bearer_env):
    auth = Authorizer(AuthConfig.load({}))
    auth._token_file_checked = -1e9  # make the first reload check immediate
    return auth


def _force_check(auth):
    auth._token_file_checked = -1e9


def test_file_tokens_accepted_with_comments(bearer_env):
    _write(bearer_env, "# ops\n" + token_hash_entry("tok-a", "viewer", "alice")
           + "  # alice\n\n", 0)
    auth = _auth(bearer_env)
    assert auth.principal("Bearer tok-a").subject == "bearer:alice"


def test_reload_swaps_table_on_mtime_change(bearer_env):
    _write(bearer_env, token_hash_entry("tok-a", "viewer", "alice") + "\n", 0)
    auth = _auth(bearer_env)
    auth.principal("Bearer tok-a")
    _write(bearer_env, token_hash_entry("tok-b", "operator", "bob") + "\n", 10)
    # Within the one-second window the old table still serves.
    auth._token_file_checked = policy.time.monotonic()
    assert auth.principal("Bearer tok-a").subject == "bearer:alice"
    _force_check(auth)
    assert auth.principal("Bearer tok-b").role == "operator"
    with pytest.raises(AuthError) as err:
        auth.principal("Bearer tok-a")
    assert err.value.status == 401


def test_malformed_reload_keeps_previous_table(bearer_env, caplog):
    _write(bearer_env, token_hash_entry("tok-a", "viewer", "alice") + "\n", 0)
    auth = _auth(bearer_env)
    auth.principal("Bearer tok-a")
    _write(bearer_env, "garbage\n", 10)
    _force_check(auth)
    with caplog.at_level("ERROR"):
        assert auth.principal("Bearer tok-a").subject == "bearer:alice"
    assert "keeping the previous token table" in caplog.text


def test_malformed_file_at_startup_fails_closed(bearer_env):
    _write(bearer_env, "garbage\n", 0)
    with pytest.raises(AuthError) as err:
        _auth(bearer_env).principal("Bearer anything")
    assert err.value.status == 501 and "line 1" in str(err.value)


def test_missing_file_at_startup_fails_closed_then_recovers(bearer_env):
    auth = _auth(bearer_env)
    with pytest.raises(AuthError) as err:
        auth.principal("Bearer tok-a")
    assert err.value.status == 501
    _write(bearer_env, token_hash_entry("tok-a", "viewer", "alice") + "\n", 0)
    _force_check(auth)
    assert auth.principal("Bearer tok-a").subject == "bearer:alice"


def test_label_repeated_across_env_and_file_is_an_error(bearer_env, monkeypatch):
    monkeypatch.setenv("MAXEY0_MCP_TOKEN_HASHES", token_hash_entry("x", "viewer", "alice"))
    _write(bearer_env, token_hash_entry("y", "viewer", "alice") + "\n", 0)
    with pytest.raises(AuthError) as err:
        _auth(bearer_env).principal("Bearer x")
    assert err.value.status == 501


def test_supported_binding_lists_only_implemented():
    manifest = AuthConfig.load({}).public_manifest()
    assert "deployment-secret-manager" not in manifest["supported_binding"]


# -- sqlite rate-limit store ------------------------------------------------


def test_store_config(monkeypatch, tmp_path):
    monkeypatch.delenv("MAXEY0_RATE_LIMIT_STORE", raising=False)
    assert RateLimitConfig.from_env().store == "memory"
    monkeypatch.setenv("MAXEY0_RATE_LIMIT_STORE", f"sqlite:{tmp_path / 'rl.db'}")
    assert RateLimitConfig.from_env().sqlite_path == str(tmp_path / "rl.db")
    monkeypatch.setenv("MAXEY0_RATE_LIMIT_STORE", "redis://x")
    config = RateLimitConfig.from_env()
    assert config.store == "memory" and "MAXEY0_RATE_LIMIT_STORE" in config.invalid


def test_sqlite_buckets_survive_restart(tmp_path):
    path = str(tmp_path / "rl.db")
    now = [1000.0]
    first = SQLiteTokenBuckets(path, "ip", 2, 60.0, 100, clock=lambda: now[0])
    assert first.check("k") == 0.0 and first.check("k") == 0.0
    assert first.check("k") > 0
    first.close()
    second = SQLiteTokenBuckets(path, "ip", 2, 60.0, 100, clock=lambda: now[0])
    assert second.check("k") > 0  # still exhausted after the "restart"
    assert second.check("k", consume=False) > 0
    assert second.check("unseen", consume=False) == 0.0 and len(second) == 1
    now[0] += 30.0  # refill one token
    assert second.check("k") == 0.0
    second.close()


def test_sqlite_buckets_evict_past_max_keys(tmp_path):
    now = [0.0]
    b = SQLiteTokenBuckets(str(tmp_path / "rl.db"), "ip", 5, 60.0, 2, clock=lambda: now[0])
    for key in ("a", "b", "c"):
        now[0] += 1
        b.check(key)
    assert len(b) == 2 and b.evictions == 1
    b.close()


def test_limiter_uses_sqlite_store(tmp_path):
    limiter = RateLimiter(RateLimitConfig(store=f"sqlite:{tmp_path / 'rl.db'}"))
    assert all(isinstance(b, SQLiteTokenBuckets) for b in limiter.buckets.values())
    report = limiter.report(public_deployment=False)
    assert report["scope"].startswith("per-host") and "rl.db" not in str(report)
