"""Origin rate limiting: who a client is, what it costs, and what is reported.

Before this, nothing at the origin counted anything. A caller could guess
bearer tokens as fast as the tunnel carried them, open sessions until the
process ran out of memory, and the edge -- which performs no authorization by
design -- forwarded all of it. These tests pin the limiter's parts in
isolation (buckets, the trust rule for CF-Connecting-IP, configuration) and
then over the wire, against a fresh app per case, because the limiter's state
is per app.
"""
from __future__ import annotations

import importlib
import json
import threading
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from maxey0_ss.api.app import create_app
from maxey0_ss.auth.policy import token_hash_entry
from maxey0_ss.examples.maker_checker_judge import build_demo
from maxey0_ss.ratelimit import (
    AUTH_FAILURES,
    RATE_LIMITED_CODE,
    RateLimitConfig,
    RateLimiter,
    TokenBuckets,
)

V = "2026-07-28"
SSE = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}

LIMIT_VARS = (
    "MAXEY0_RATE_LIMIT_ENABLED", "MAXEY0_RATE_LIMIT_IP_PER_MIN",
    "MAXEY0_RATE_LIMIT_PRINCIPAL_PER_MIN", "MAXEY0_RATE_LIMIT_SESSION_OPEN_PER_MIN",
    "MAXEY0_RATE_LIMIT_AUTH_FAILURES_PER_HOUR", "MAXEY0_RATE_LIMIT_MAX_KEYS",
    "MAXEY0_TRUSTED_PROXY_IPS", "MAXEY0_MAX_REQUEST_BYTES", "MAXEY0_SESSION_MAX",
    "MAXEY0_SESSION_IDLE_TIMEOUT_S",
)
AUTH_VARS = ("MAXEY0_PUBLIC", "MAXEY0_AUTH_MODE", "MAXEY0_MCP_TOKENS",
             "MAXEY0_MCP_TOKEN_HASHES", "MAXEY0_MCP_DEFAULT_BEARER_TOKEN")


@pytest.fixture
def env(monkeypatch):
    """Code defaults for every variable these tests turn."""
    for name in LIMIT_VARS + AUTH_VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def configure(env, **values):
    for name, value in values.items():
        env.setenv(name, str(value))


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def scope(peer, *headers):
    return {"type": "http", "client": (peer, 5000) if peer else None,
            "headers": [(k.encode(), v.encode()) for k, v in headers]}


def call(client, tool="maxey0-ss.health", auth=None, args=None):
    headers = {"MCP-Protocol-Version": V, "Mcp-Method": "tools/call", "Mcp-Name": tool}
    if auth:
        headers["Authorization"] = auth
    return client.post("/mcp", headers=headers, json={
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": tool, "arguments": args or {}}})


def initialize(client, path="/mcp/session/", auth=None):
    headers = dict(SSE)
    if auth:
        headers["Authorization"] = auth
    return client.post(path, headers=headers, json={
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                   "clientInfo": {"name": "test", "version": "0"}}})


def session_call(client, session_id, auth=None, tool="maxey0-ss.health"):
    headers = {**SSE, "mcp-session-id": session_id}
    if auth:
        headers["Authorization"] = auth
    return client.post("/mcp/session/", headers=headers, json={
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": tool, "arguments": {}}})


def sse_json(response) -> dict:
    for line in response.text.splitlines():
        if line.startswith("data: "):
            return json.loads(line[len("data: "):])
    raise AssertionError(f"no SSE data line: {response.text!r}")


def limiter_of(client) -> RateLimiter:
    return client.app.state.maxey0_surface.rate_limiter


def assert_rate_limited_rpc(response, limit):
    assert response.status_code == 429, response.text
    retry = response.headers["retry-after"]
    assert retry.isdigit() and int(retry) >= 1
    body = response.json()
    assert body["id"] is None
    assert body["error"]["code"] == RATE_LIMITED_CODE == -32005
    assert body["error"]["data"] == {"limit": limit, "retry_after_s": int(retry)}
    assert "result" not in body


# ---------------------------------------------------------------------------
# buckets
# ---------------------------------------------------------------------------


class TestTokenBuckets:
    def test_capacity_then_refill_with_the_wait_it_reports(self):
        clock = Clock()
        buckets = TokenBuckets(3, 60.0, 10, clock)
        assert [buckets.check("k") for _ in range(3)] == [0.0, 0.0, 0.0]
        # 3 per minute is one token every 20 s, and the answer says so.
        assert buckets.check("k") == pytest.approx(20.0)
        clock.advance(10)
        assert buckets.check("k") == pytest.approx(10.0)
        clock.advance(10)
        assert buckets.check("k") == 0.0
        assert buckets.check("k") > 0

    def test_refill_never_exceeds_capacity(self):
        clock = Clock()
        buckets = TokenBuckets(2, 60.0, 10, clock)
        buckets.check("k")
        clock.advance(3600)
        first, second, third = (buckets.check("k") for _ in range(3))
        assert (first, second) == (0.0, 0.0)
        assert third > 0

    def test_a_peek_neither_consumes_nor_inserts(self):
        buckets = TokenBuckets(1, 60.0, 10, Clock())
        for _ in range(5):
            assert buckets.check("unseen", consume=False) == 0.0
        assert len(buckets) == 0
        assert buckets.check("unseen") == 0.0
        assert buckets.check("unseen", consume=False) > 0

    def test_least_recently_seen_key_is_evicted_at_the_bound(self):
        buckets = TokenBuckets(1, 60.0, 2, Clock())
        buckets.check("a")
        buckets.check("b")
        buckets.check("a")          # touches `a`, so `b` is now the oldest
        buckets.check("c")
        assert len(buckets) == 2
        assert buckets.evictions == 1
        assert buckets.check("a", consume=False) > 0      # kept, still spent
        assert buckets.check("b", consume=False) == 0.0   # forgotten: full again

    def test_concurrent_callers_on_one_key_get_exactly_the_capacity(self):
        buckets = TokenBuckets(50, 60.0, 10, Clock())  # frozen clock: no refill
        threads, per_thread = 8, 25
        barrier = threading.Barrier(threads)
        admitted = []
        lock = threading.Lock()

        def worker():
            barrier.wait()
            mine = sum(1 for _ in range(per_thread) if buckets.check("k") == 0.0)
            with lock:
                admitted.append(mine)

        pool = [threading.Thread(target=worker) for _ in range(threads)]
        for t in pool:
            t.start()
        for t in pool:
            t.join()
        assert sum(admitted) == 50


# ---------------------------------------------------------------------------
# who is calling
# ---------------------------------------------------------------------------


class TestClientKey:
    def setup_method(self):
        self.limiter = RateLimiter(RateLimitConfig(enabled=True))

    def key(self, peer, *headers):
        return self.limiter.client_key(scope(peer, *headers))

    def test_the_header_is_ignored_from_an_untrusted_peer(self, subtests):
        spoof = ("cf-connecting-ip", "203.0.113.9")
        for peer in ("testclient", "198.51.100.7"):
            with subtests.test(peer=peer):
                assert self.key(peer, spoof) == peer

    def test_the_header_is_believed_from_loopback(self, subtests):
        for peer in ("127.0.0.1", "::1", "::ffff:127.0.0.1"):
            with subtests.test(peer=peer):
                assert self.key(peer, ("cf-connecting-ip", "203.0.113.9")) == "203.0.113.9"

    def test_a_malformed_header_falls_back_to_the_peer(self, subtests):
        for value in ("not-an-ip", "203.0.113.9, 198.51.100.1", "", "999.1.1.1"):
            with subtests.test(value=value):
                assert self.key("127.0.0.1", ("cf-connecting-ip", value)) == "127.0.0.1"

    def test_ipv6_clients_are_grouped_by_their_64(self):
        a = self.key("127.0.0.1", ("cf-connecting-ip", "2001:db8:1:2:3:4:5:6"))
        b = self.key("127.0.0.1", ("cf-connecting-ip", "2001:db8:1:2::9"))
        c = self.key("127.0.0.1", ("cf-connecting-ip", "2001:db8:1:3::9"))
        assert a == b == "2001:db8:1:2::/64"
        assert c != a
        assert self.key("2001:db8:9:9::1") == "2001:db8:9:9::/64"

    def test_ipv4_mapped_addresses_are_the_ipv4_address(self):
        assert self.key("::ffff:203.0.113.5") == "203.0.113.5"
        assert self.key("127.0.0.1", ("cf-connecting-ip", "::ffff:198.51.100.1")) == "198.51.100.1"

    def test_no_peer_at_all_is_still_a_key(self):
        assert self.key(None)

    def test_a_configured_cidr_is_trusted(self):
        limiter = RateLimiter(RateLimitConfig(enabled=True, trusted_proxies=("10.0.0.0/8",)))
        spoof = ("cf-connecting-ip", "203.0.113.9")
        assert limiter.client_key(scope("10.1.2.3", spoof)) == "203.0.113.9"
        assert limiter.client_key(scope("127.0.0.1", spoof)) == "127.0.0.1"


# ---------------------------------------------------------------------------
# configuration
# ---------------------------------------------------------------------------


class TestConfig:
    def test_empty_values_are_the_defaults(self, env):
        for name in LIMIT_VARS:
            env.setenv(name, "")
        config = RateLimitConfig.from_env()
        defaults = RateLimitConfig()
        assert config.as_dict() == {**defaults.as_dict(), "source": "auto"}
        assert config.invalid == ()

    def test_automatic_is_off_only_for_the_trusted_local_default(self, env, subtests):
        cases = (
            ({}, False),
            ({"MAXEY0_AUTH_MODE": "disabled"}, False),
            ({"MAXEY0_PUBLIC": "1"}, True),
            ({"MAXEY0_AUTH_MODE": "bearer"}, True),
            ({"MAXEY0_AUTH_MODE": "oidc"}, True),
            # A misspelt mode is not `disabled`, and refuses everything anyway.
            ({"MAXEY0_AUTH_MODE": "bearr"}, True),
        )
        for values, enabled in cases:
            with subtests.test(**values):
                for name in AUTH_VARS:
                    env.delenv(name, raising=False)
                configure(env, **values)
                config = RateLimitConfig.from_env()
                assert (config.enabled, config.source) == (enabled, "auto")

    def test_the_switch_overrides_the_posture(self, env, subtests):
        for raw, enabled in (("1", True), ("ON", True), (" yes ", True), ("true", True),
                             ("0", False), ("off", False), ("No", False), ("FALSE", False)):
            with subtests.test(raw=raw):
                configure(env, MAXEY0_PUBLIC="1", MAXEY0_RATE_LIMIT_ENABLED=raw)
                config = RateLimitConfig.from_env()
                assert (config.enabled, config.source) == (enabled, "env")

    def test_garbage_means_the_default_and_is_named(self, env):
        configure(
            env,
            MAXEY0_RATE_LIMIT_ENABLED="maybe",
            MAXEY0_RATE_LIMIT_IP_PER_MIN="lots",
            MAXEY0_RATE_LIMIT_PRINCIPAL_PER_MIN="0",
            MAXEY0_RATE_LIMIT_SESSION_OPEN_PER_MIN="-5",
            MAXEY0_RATE_LIMIT_AUTH_FAILURES_PER_HOUR="2.5",
            MAXEY0_TRUSTED_PROXY_IPS="127.0.0.1,not-an-ip",
            MAXEY0_SESSION_IDLE_TIMEOUT_S="inf",
            MAXEY0_MAX_REQUEST_BYTES="1MB",
        )
        config = RateLimitConfig.from_env()
        defaults = RateLimitConfig()
        assert config.enabled is False and config.source == "auto"
        assert config.ip_per_min == defaults.ip_per_min == 120
        assert config.principal_per_min == defaults.principal_per_min == 300
        assert config.session_open_per_min == defaults.session_open_per_min == 6
        assert config.auth_failures_per_hour == defaults.auth_failures_per_hour == 20
        # One bad entry is the default, not a shorter list.
        assert config.trusted_proxies == ("127.0.0.1/32", "::1/128")
        assert config.session_idle_timeout_s == 600.0
        assert config.max_request_bytes == 1048576
        assert set(config.invalid) == {
            "MAXEY0_RATE_LIMIT_ENABLED", "MAXEY0_RATE_LIMIT_IP_PER_MIN",
            "MAXEY0_RATE_LIMIT_PRINCIPAL_PER_MIN", "MAXEY0_RATE_LIMIT_SESSION_OPEN_PER_MIN",
            "MAXEY0_RATE_LIMIT_AUTH_FAILURES_PER_HOUR", "MAXEY0_TRUSTED_PROXY_IPS",
            "MAXEY0_SESSION_IDLE_TIMEOUT_S", "MAXEY0_MAX_REQUEST_BYTES",
        }

    def test_valid_values_are_read(self, env):
        configure(
            env,
            MAXEY0_RATE_LIMIT_ENABLED="1", MAXEY0_RATE_LIMIT_IP_PER_MIN="7",
            MAXEY0_RATE_LIMIT_MAX_KEYS="99", MAXEY0_TRUSTED_PROXY_IPS=" 10.0.0.1 , fd00::/8 ",
            MAXEY0_SESSION_IDLE_TIMEOUT_S="12.5", MAXEY0_SESSION_MAX="3",
        )
        config = RateLimitConfig.from_env()
        assert (config.ip_per_min, config.max_keys, config.session_max) == (7, 99, 3)
        assert config.trusted_proxies == ("10.0.0.1/32", "fd00::/8")
        assert config.session_idle_timeout_s == 12.5
        assert config.invalid == ()


# ---------------------------------------------------------------------------
# over the wire
# ---------------------------------------------------------------------------


class TestRefusals:
    def test_mcp_gets_429_with_retry_after_and_32005(self, env):
        configure(env, MAXEY0_RATE_LIMIT_ENABLED="1", MAXEY0_RATE_LIMIT_IP_PER_MIN="2")
        client = TestClient(create_app())
        assert call(client).status_code == 200
        assert call(client).status_code == 200
        assert_rate_limited_rpc(call(client), "ip")

    def test_the_session_transport_gets_the_same_json_rpc_refusal(self, env):
        configure(env, MAXEY0_RATE_LIMIT_ENABLED="1", MAXEY0_RATE_LIMIT_IP_PER_MIN="1")
        with TestClient(create_app()) as client:
            assert initialize(client).status_code == 200
            assert_rate_limited_rpc(initialize(client), "ip")

    def test_rest_and_health_get_a_detail_body(self, env, subtests):
        configure(env, MAXEY0_RATE_LIMIT_ENABLED="1", MAXEY0_RATE_LIMIT_IP_PER_MIN="1")
        for path in ("/health", "/v1/harnesses"):
            with subtests.test(path=path):
                client = TestClient(create_app())
                assert client.get(path).status_code == 200
                refused = client.get(path)
                assert refused.status_code == 429
                retry = int(refused.headers["retry-after"])
                assert retry >= 1
                assert refused.json() == {"detail": "rate limit exceeded",
                                          "limit": "ip", "retry_after_s": retry}

    def test_addresses_are_limited_separately(self, env):
        configure(env, MAXEY0_RATE_LIMIT_ENABLED="1", MAXEY0_RATE_LIMIT_IP_PER_MIN="1")
        app = create_app()
        first = TestClient(app, client=("198.51.100.1", 1))
        second = TestClient(app, client=("198.51.100.2", 1))
        assert first.get("/health").status_code == 200
        assert first.get("/health").status_code == 429
        assert second.get("/health").status_code == 200

    def test_a_spoofed_cf_connecting_ip_does_not_buy_a_fresh_bucket(self, env):
        configure(env, MAXEY0_RATE_LIMIT_ENABLED="1", MAXEY0_RATE_LIMIT_IP_PER_MIN="1")
        client = TestClient(create_app(), client=("198.51.100.9", 1))
        assert client.get("/health", headers={"CF-Connecting-IP": "203.0.113.1"}).status_code == 200
        assert client.get("/health", headers={"CF-Connecting-IP": "203.0.113.2"}).status_code == 429

    def test_the_tunnel_peer_is_split_by_cf_connecting_ip(self, env):
        configure(env, MAXEY0_RATE_LIMIT_ENABLED="1", MAXEY0_RATE_LIMIT_IP_PER_MIN="1")
        tunnel = TestClient(create_app(), client=("127.0.0.1", 1))
        assert tunnel.get("/health", headers={"CF-Connecting-IP": "203.0.113.1"}).status_code == 200
        assert tunnel.get("/health", headers={"CF-Connecting-IP": "203.0.113.2"}).status_code == 200
        assert tunnel.get("/health", headers={"CF-Connecting-IP": "203.0.113.1"}).status_code == 429


class TestPrincipalBudget:
    def test_one_token_is_one_budget_from_every_address(self, env):
        configure(env, MAXEY0_RATE_LIMIT_ENABLED="1", MAXEY0_RATE_LIMIT_PRINCIPAL_PER_MIN="3",
                  MAXEY0_AUTH_MODE="bearer", MAXEY0_MCP_TOKENS="tok-a:operator,tok-b:operator")
        app = create_app()
        first = TestClient(app, client=("198.51.100.1", 1))
        second = TestClient(app, client=("198.51.100.2", 1))
        assert call(first, auth="Bearer tok-a").status_code == 200
        assert call(first, auth="Bearer tok-a").status_code == 200
        assert call(second, auth="Bearer tok-a").status_code == 200
        assert_rate_limited_rpc(call(second, auth="Bearer tok-a"), "principal")
        # Another caller's budget is its own.
        assert call(second, auth="Bearer tok-b").status_code == 200

    def test_the_rest_surface_draws_on_the_same_budget(self, env):
        configure(env, MAXEY0_RATE_LIMIT_ENABLED="1", MAXEY0_RATE_LIMIT_PRINCIPAL_PER_MIN="2",
                  MAXEY0_AUTH_MODE="bearer", MAXEY0_MCP_TOKENS="tok-a:operator")
        client = TestClient(create_app())
        assert call(client, auth="Bearer tok-a").status_code == 200
        assert client.get("/v1/context/scws", headers={"Authorization": "Bearer tok-a"}).status_code == 200
        refused = client.get("/v1/context/scws", headers={"Authorization": "Bearer tok-a"})
        assert refused.status_code == 429
        assert refused.json()["limit"] == "principal"


class TestAuthFailureLockout:
    def _env(self, env, failures=3):
        configure(env, MAXEY0_RATE_LIMIT_ENABLED="1",
                  MAXEY0_RATE_LIMIT_AUTH_FAILURES_PER_HOUR=str(failures),
                  MAXEY0_AUTH_MODE="bearer", MAXEY0_MCP_TOKENS="good:viewer")

    def test_bad_bearers_lock_the_address_out_and_only_that_address(self, env):
        self._env(env)
        app = create_app()
        guesser = TestClient(app, client=("198.51.100.1", 1))
        bystander = TestClient(app, client=("198.51.100.2", 1))
        for _ in range(3):
            wrong = call(guesser, auth="Bearer wrong")
            # Downstream still answers with its own canonical refusal.
            assert wrong.status_code == 401
            assert wrong.json()["error"]["code"] == -32001
        assert_rate_limited_rpc(call(guesser, auth="Bearer wrong"), "auth_failures")
        assert_rate_limited_rpc(call(guesser), "auth_failures")
        assert call(bystander, auth="Bearer wrong").status_code == 401
        # Three from the guesser, one from the bystander, none while locked out.
        assert limiter_of(guesser).report(public_deployment=False)["counters"]["auth_failures_total"] == 4

    def test_a_missing_header_never_counts(self, env):
        self._env(env)
        client = TestClient(create_app())
        for _ in range(6):
            # bearer mode refuses a public tool without a token, and that is
            # not a failed credential -- none was presented.
            assert call(client).status_code == 401
        assert call(client, auth="Bearer good").status_code == 200
        assert limiter_of(client).report(public_deployment=False)["counters"]["auth_failures_total"] == 0

    def test_a_locked_out_address_gets_32005_never_32001_or_32002(self, env):
        self._env(env, failures=1)
        client = TestClient(create_app())
        assert call(client, auth="Bearer wrong").status_code == 401
        # Unlocked, these would be -32001 (no token, and a wrong one). A
        # lockout is decided before either is consulted.
        assert_rate_limited_rpc(call(client, "maxey0-ss.scw.create",
                                     args={"scw_id": "SCW9", "task": "t"}), "auth_failures")
        assert_rate_limited_rpc(call(client, "maxey0-ss.scw.create", auth="Bearer wrong",
                                     args={"scw_id": "SCW9", "task": "t"}), "auth_failures")

    def test_a_valid_token_sharing_a_locked_out_address_is_not_locked_out(self, env):
        """An address is shared -- a NAT, or every caller behind a trusted
        proxy that omits CF-Connecting-IP. With the lockout checked before the
        credential, anyone sharing it could lock a token holder out by sending
        bad bearers. A credential that authenticates now skips the lockout and
        draws on its own principal budget."""
        self._env(env, failures=3)
        app = create_app()
        # Both arrive from the tunnel's loopback peer with no CF-Connecting-IP:
        # one client key for the two of them.
        attacker = TestClient(app, client=("127.0.0.1", 1))
        holder = TestClient(app, client=("127.0.0.1", 2))
        for _ in range(20):
            call(attacker, auth="Bearer wrong")
        assert_rate_limited_rpc(call(attacker, auth="Bearer wrong"), "auth_failures")
        ok = call(holder, auth="Bearer good")
        assert ok.status_code == 200, ok.text
        # Past the lockout the call reaches authorization: -32002 (viewer lacks
        # scw.create), not -32005.
        refused = call(holder, "maxey0-ss.scw.create", auth="Bearer good",
                       args={"scw_id": "SCW9", "task": "t"})
        assert refused.json()["error"]["code"] == -32002
        counters = limiter_of(holder).report(public_deployment=False)["counters"]
        # Refusals made while locked out are not charged again.
        assert counters["auth_failures_total"] == 3
        assert counters["trusted_proxy_without_client_ip"] >= 23

    def test_degraded_keying_is_counted_only_without_a_usable_header(self, env):
        configure(env, MAXEY0_RATE_LIMIT_ENABLED="1")
        app = create_app()
        call(TestClient(app, client=("127.0.0.1", 1), headers={"CF-Connecting-IP": "203.0.113.5"}))
        call(TestClient(app, client=("198.51.100.9", 1)))  # untrusted peer: its own key
        call(TestClient(app, client=("127.0.0.1", 1), headers={"CF-Connecting-IP": "garbage"}))
        call(TestClient(app, client=("127.0.0.1", 1)))
        manifest = call(TestClient(app, client=("198.51.100.9", 1)), "maxey0-ss.auth.manifest")
        block = manifest.json()["result"]["structuredContent"]["rate_limit"]
        assert block["counters"]["trusted_proxy_without_client_ip"] == 2

    def test_a_bad_bearer_on_the_session_transport_counts(self, env):
        """That transport answers a refused credential with HTTP 200 and a soft
        isError result, so nothing downstream could count it by status."""
        self._env(env, failures=2)
        with TestClient(create_app()) as client:
            opened = initialize(client)
            assert opened.status_code == 200
            session_id = opened.headers["mcp-session-id"]
            for _ in range(2):
                soft = session_call(client, session_id, auth="Bearer wrong")
                assert soft.status_code == 200
                assert sse_json(soft)["result"]["isError"] is True
            assert_rate_limited_rpc(session_call(client, session_id, auth="Bearer wrong"),
                                    "auth_failures")

    def test_a_misconfigured_deployment_charges_nobody(self, env):
        """-32004 is the operator's error. Charging callers for it would keep
        them locked out after the operator fixed it."""
        configure(env, MAXEY0_RATE_LIMIT_ENABLED="1",
                  MAXEY0_RATE_LIMIT_AUTH_FAILURES_PER_HOUR="1", MAXEY0_AUTH_MODE="bearr")
        client = TestClient(create_app())
        for _ in range(3):
            assert call(client, auth="Bearer anything").status_code == 501
        assert limiter_of(client).report(public_deployment=False)["counters"]["auth_failures_total"] == 0


class TestA2A:
    SECRET = "-".join(["a2a", "fixture", "value"])

    def _client(self, env, monkeypatch):
        configure(env, MAXEY0_RATE_LIMIT_ENABLED="1",
                  MAXEY0_RATE_LIMIT_AUTH_FAILURES_PER_HOUR="2")
        # `maxey0_ss.api.app` as a dotted path resolves to the FastAPI instance
        # the package re-exports, not the module that defines `_settings`.
        module = importlib.import_module("maxey0_ss.api.app")
        monkeypatch.setattr(module, "_settings",
                            lambda: SimpleNamespace(a2a_shared_secret=self.SECRET))
        return TestClient(create_app(build_demo()))

    def _post(self, client, auth=None):
        headers = {"Authorization": auth} if auth else {}
        return client.post("/v1/a2a/message", headers=headers, json={
            "sender": "external", "task": "threat modeling", "concept": "security",
            "skill": "threat modeling", "context": {}})

    def test_a_valid_secret_is_not_counted_and_an_invalid_one_is(self, env, monkeypatch):
        client = self._client(env, monkeypatch)
        for _ in range(3):
            assert self._post(client, f"Bearer {self.SECRET}").status_code == 200
        assert self._post(client).status_code == 401  # no credential: not a guess
        counters = limiter_of(client).report(public_deployment=False)["counters"]
        assert counters["auth_failures_total"] == 0
        assert self._post(client, "Bearer wrong").status_code == 401
        assert self._post(client, "Bearer wrong").status_code == 401
        assert limiter_of(client).report(public_deployment=False)["counters"]["auth_failures_total"] == 2
        refused = self._post(client, f"Bearer {self.SECRET}")
        assert refused.status_code == 429
        assert refused.json()["limit"] == AUTH_FAILURES


class TestSessionOpens:
    def test_a_burst_of_opens_is_refused(self, env):
        configure(env, MAXEY0_RATE_LIMIT_ENABLED="1", MAXEY0_RATE_LIMIT_SESSION_OPEN_PER_MIN="2")
        with TestClient(create_app()) as client:
            first = initialize(client)
            assert first.status_code == 200
            assert initialize(client).status_code == 200
            assert_rate_limited_rpc(initialize(client), "session_open")
            # Using a session that is already open is not opening one.
            used = session_call(client, first.headers["mcp-session-id"])
            assert used.status_code == 200
            assert sse_json(used)["result"]["structuredContent"]["ok"] is True

    def test_the_unslashed_url_is_charged_once_not_twice(self, env):
        """`/mcp/session` answers 307 to `/mcp/session/`; only the second
        request reaches the session manager, so only it opens anything. If the
        unslashed path is ever served directly, this fails and the prefix in
        ratelimit.SESSION_PREFIX has to follow it."""
        configure(env, MAXEY0_RATE_LIMIT_ENABLED="1", MAXEY0_RATE_LIMIT_SESSION_OPEN_PER_MIN="1")
        with TestClient(create_app()) as client:
            assert initialize(client, path="/mcp/session").status_code == 200
            assert_rate_limited_rpc(initialize(client, path="/mcp/session"), "session_open")


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------


class TestReporting:
    def test_the_manifest_reports_counts_and_never_who(self, env):
        token, label, plain = "tok-" + "a" * 40, "ci-runner-label", "plain-" + "b" * 30
        configure(env, MAXEY0_RATE_LIMIT_ENABLED="1", MAXEY0_RATE_LIMIT_AUTH_FAILURES_PER_HOUR="50",
                  MAXEY0_AUTH_MODE="bearer",
                  MAXEY0_MCP_TOKEN_HASHES=token_hash_entry(token, "viewer", label),
                  MAXEY0_MCP_TOKENS=f"{plain}:operator")
        app = create_app()
        tunnel = TestClient(app, client=("127.0.0.1", 1),
                            headers={"CF-Connecting-IP": "203.0.113.77"})
        direct = TestClient(app, client=("198.51.100.66", 1))
        assert call(tunnel, auth=f"Bearer {token}").status_code == 200
        assert call(direct, auth=f"Bearer {plain}").status_code == 200
        assert call(direct, auth="Bearer guessed-wrong").status_code == 401
        manifest = call(tunnel, "maxey0-ss.auth.manifest", auth=f"Bearer {token}")
        assert manifest.status_code == 200
        body = manifest.json()["result"]["structuredContent"]
        block = body["rate_limit"]
        assert block["enabled"] is True and block["source"] == "env"
        assert block["enforced"] is True
        assert block["scope"] == "per-process, in-memory, resets on restart"
        assert block["client_ip"] == {"header": "CF-Connecting-IP",
                                      "trusted_proxy_count": 2,
                                      "uvicorn_proxy_headers": False}
        assert block["counters"]["auth_failures_total"] == 1
        assert block["counters"]["tracked_keys"]["ip"] == 2
        assert block["counters"]["tracked_keys"]["principal"] == 2
        assert set(block["counters"]["limited"]) == {"ip", "principal", "session_open",
                                                     "auth_failures"}
        blob = json.dumps(body)
        for secret in ("203.0.113.77", "198.51.100.66", "127.0.0.1", token, plain, label,
                       "bearer:", "guessed-wrong", "testclient"):
            assert secret not in blob, f"{secret!r} reached the public manifest"

    def test_a_public_deployment_with_the_limiter_off_is_warned_about(self, env):
        configure(env, MAXEY0_PUBLIC="1", MAXEY0_RATE_LIMIT_ENABLED="0")
        client = TestClient(create_app())
        block = call(client, "maxey0-ss.auth.manifest").json()["result"]["structuredContent"]["rate_limit"]
        assert block["enabled"] is False and block["source"] == "env"
        assert block["enforced"] is False
        assert "MAXEY0_RATE_LIMIT_ENABLED" in block["warning"]

    def test_the_local_default_is_off_and_not_warned_about(self, env):
        client = TestClient(create_app())
        block = call(client, "maxey0-ss.auth.manifest").json()["result"]["structuredContent"]["rate_limit"]
        assert (block["enabled"], block["source"], block["enforced"]) == (False, "auto", False)
        assert "warning" not in block

    def test_invalid_settings_are_named(self, env):
        configure(env, MAXEY0_PUBLIC="1", MAXEY0_RATE_LIMIT_IP_PER_MIN="fast")
        client = TestClient(create_app())
        block = call(client, "maxey0-ss.auth.manifest").json()["result"]["structuredContent"]["rate_limit"]
        assert block["invalid_settings"] == ["MAXEY0_RATE_LIMIT_IP_PER_MIN"]
        assert block["limits"]["ip_per_min"] == 120

    def test_the_deployment_tool_carries_a_summary(self, env):
        configure(env, MAXEY0_PUBLIC="1")
        client = TestClient(create_app())
        summary = call(client, "maxey0-ss.deployment").json()["result"]["structuredContent"]["rate_limit"]
        assert summary == {"enabled": True, "source": "auto", "enforced": True,
                           "scope": "per-process, in-memory, resets on restart",
                           "detail": "maxey0-ss.auth.manifest"}

    def test_limited_counts_move(self, env):
        configure(env, MAXEY0_RATE_LIMIT_ENABLED="1", MAXEY0_RATE_LIMIT_IP_PER_MIN="1")
        client = TestClient(create_app())
        client.get("/health")
        client.get("/health")
        client.get("/health")
        counters = limiter_of(client).report(public_deployment=False)["counters"]
        assert counters["limited"]["ip"] == 2

    def test_stdio_builds_the_limiter_and_says_it_enforces_nothing(self, env):
        from maxey0_ss.mcp_surface import build_surface

        configure(env, MAXEY0_PUBLIC="1")
        surface = build_surface()
        manifest = next(t for t in surface.tools if t.name == "maxey0-ss.auth.manifest").handler({})
        block = manifest["rate_limit"]
        assert block["enabled"] is True
        assert block["enforced"] is False
        assert all(cap["applied"] is False for cap in block["request_caps"]["session"].values())


class TestOneAuthorizer:
    def test_every_door_resolves_callers_with_the_surface_authorizer(self, env):
        configure(env, MAXEY0_AUTH_MODE="bearer", MAXEY0_MCP_TOKENS="tok:admin")
        app = create_app()
        authorizer = app.state.maxey0_surface.authorizer
        seen = []
        original = authorizer.principal

        def counting(header):
            seen.append(header)
            return original(header)

        authorizer.principal = counting
        with TestClient(app) as client:
            auth = {"Authorization": "Bearer tok"}
            assert client.get("/v1/context/scws", headers=auth).status_code == 200
            rest = len(seen)
            assert call(client, auth="Bearer tok").status_code == 200
            stateless = len(seen)
            session_id = initialize(client).headers["mcp-session-id"]
            before_session = len(seen)
            assert session_call(client, session_id, auth="Bearer tok").status_code == 200
        # /v1: the limiter and the capability middleware. /mcp: the limiter and
        # the router. /mcp/session: the limiter and the tool handler.
        assert rest >= 2
        assert stateless - rest >= 2
        assert len(seen) - before_session >= 2
