"""Request caps, and the process shape the rate limiter depends on.

A body cap, the session transport's own caps, uvicorn's proxy handling, the
scheme it used to restore, and the generated API docs a public origin served.
Each is small; each is a place where the limiter could be right and the
deployment still wrong.
"""
from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from maxey0_ss.api.app import create_app
from maxey0_ss.ratelimit import (
    RateLimitConfig,
    RateLimiter,
    RateLimitMiddleware,
    session_manager_caps,
)

V = "2026-07-28"
SSE = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}

LIMIT_VARS = (
    "MAXEY0_RATE_LIMIT_ENABLED", "MAXEY0_RATE_LIMIT_IP_PER_MIN",
    "MAXEY0_RATE_LIMIT_PRINCIPAL_PER_MIN", "MAXEY0_RATE_LIMIT_SESSION_OPEN_PER_MIN",
    "MAXEY0_RATE_LIMIT_AUTH_FAILURES_PER_HOUR", "MAXEY0_RATE_LIMIT_MAX_KEYS",
    "MAXEY0_TRUSTED_PROXY_IPS", "MAXEY0_MAX_REQUEST_BYTES", "MAXEY0_SESSION_MAX",
    "MAXEY0_SESSION_IDLE_TIMEOUT_S", "MAXEY0_PUBLIC", "MAXEY0_AUTH_MODE",
)


@pytest.fixture
def env(monkeypatch):
    for name in LIMIT_VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def mcp_post(client, body: bytes | None = None, *, json_body=None, **kwargs):
    headers = {"MCP-Protocol-Version": V, "Mcp-Method": "tools/call",
               "Mcp-Name": "maxey0-ss.health", "Content-Type": "application/json"}
    if json_body is not None:
        body = json.dumps(json_body).encode()
    return client.post("/mcp", headers=headers, content=body, **kwargs)


def health_call(padding: str = "") -> dict:
    return {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "maxey0-ss.health", "arguments": {"pad": padding}}}


# ---------------------------------------------------------------------------
# body cap, over the wire
# ---------------------------------------------------------------------------


class TestBodyCap:
    def _client(self, env, cap=512):
        env.setenv("MAXEY0_RATE_LIMIT_ENABLED", "1")
        env.setenv("MAXEY0_MAX_REQUEST_BYTES", str(cap))
        return TestClient(create_app())

    def test_an_oversized_mcp_body_is_a_json_rpc_413(self, env):
        client = self._client(env)
        response = mcp_post(client, json_body=health_call("x" * 600))
        assert response.status_code == 413
        assert response.json() == {
            "jsonrpc": "2.0", "id": None,
            "error": {"code": -32600, "message": "Request body too large",
                      "data": {"limit_bytes": 512}},
        }

    def test_an_oversized_rest_body_is_a_detail_413(self, env):
        client = self._client(env)
        response = client.post("/v1/context/observe/host-window",
                               json={"segments": ["x" * 600]})
        assert response.status_code == 413
        assert response.json() == {"detail": "request body too large", "limit_bytes": 512}

    def test_a_body_under_the_cap_reaches_the_handler_intact(self, env):
        client = self._client(env)
        response = mcp_post(client, json_body=health_call("x" * 100))
        assert response.status_code == 200
        assert response.json()["result"]["structuredContent"]["ok"] is True

    def test_a_chunked_body_with_no_length_is_capped_too(self, env):
        client = self._client(env)
        payload = json.dumps(health_call("x" * 600)).encode()

        def chunks():
            for i in range(0, len(payload), 100):
                yield payload[i:i + 100]

        response = mcp_post(client, chunks())
        assert response.status_code == 413

    def test_the_session_transport_is_capped_before_the_sdk(self, env):
        client = self._client(env)
        with client:
            response = client.post("/mcp/session/", headers=SSE, json={
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                           "clientInfo": {"name": "x" * 600, "version": "0"}}})
        assert response.status_code == 413
        assert response.json()["error"]["code"] == -32600

    def test_a_session_can_still_be_deleted(self, env):
        client = self._client(env)
        with client:
            opened = client.post("/mcp/session/", headers=SSE, json={
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                           "clientInfo": {"name": "t", "version": "0"}}})
            session_id = opened.headers["mcp-session-id"]
            deleted = client.delete("/mcp/session/", headers={**SSE, "mcp-session-id": session_id})
            assert deleted.status_code == 200
            gone = client.post("/mcp/session/", headers={**SSE, "mcp-session-id": session_id},
                               json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            assert gone.status_code == 404


# ---------------------------------------------------------------------------
# body cap, at the ASGI boundary
# ---------------------------------------------------------------------------


def run(coro):
    return asyncio.run(coro)


class Recorder:
    """A downstream app that reads everything it is given."""

    def __init__(self) -> None:
        self.received: list[dict] = []
        self.called = False

    async def __call__(self, scope, receive, send):
        self.called = True
        if scope["method"] in ("POST", "PUT", "PATCH"):
            while True:
                message = await receive()
                self.received.append(message)
                if not message.get("more_body"):
                    break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})


def middleware(app, cap=64):
    limiter = RateLimiter(RateLimitConfig(enabled=True, max_request_bytes=cap))
    return RateLimitMiddleware(app, limiter=limiter), limiter


def http_scope(method, *headers, path="/v1/anything"):
    return {"type": "http", "method": method, "path": path, "client": ("198.51.100.1", 1),
            "headers": [(k.encode(), v.encode()) for k, v in headers]}


async def collect(mw, scope, messages):
    sent: list[dict] = []
    queue = list(messages)

    async def receive():
        if not queue:
            raise AssertionError("receive called past the end of the request")
        return queue.pop(0)

    async def send(message):
        sent.append(message)

    await mw(scope, receive, send)
    return sent


class TestCredentialResolutionOffTheLoop:
    def test_the_authorizer_runs_in_a_worker_thread(self):
        """An OIDC verifier may fetch a key set over the network. Resolved
        inline, that fetch stalled the event loop, and every other request on
        the process with it."""
        import threading
        from types import SimpleNamespace

        seen: dict = {}

        class Authorizer:
            mode = "bearer"

            def principal(self, authorization):
                seen["thread"] = threading.get_ident()
                return SimpleNamespace(authenticated=True, role="viewer", subject="s")

        async def go():
            seen["loop"] = threading.get_ident()
            limiter = RateLimiter(RateLimitConfig(enabled=True))
            mw = RateLimitMiddleware(Recorder(), limiter=limiter, authorizer=Authorizer())
            return await collect(mw, http_scope("GET", ("authorization", "Bearer x")), [])

        sent = run(go())
        assert sent[0]["status"] == 200
        assert seen["thread"] != seen["loop"]


class TestBodyCapAtTheBoundary:
    def test_a_declared_length_over_the_cap_is_refused_unread(self):
        app = Recorder()
        mw, limiter = middleware(app)

        async def go():
            sent: list[dict] = []

            async def receive():
                raise AssertionError("the body was read")

            async def send(message):
                sent.append(message)

            await mw(http_scope("POST", ("content-length", "65")), receive, send)
            return sent

        sent = run(go())
        assert sent[0]["status"] == 413
        assert app.called is False
        assert limiter.report(public_deployment=False)["counters"]["request_too_large"] == 1

    def test_split_body_is_reassembled_and_replayed_once(self):
        app = Recorder()
        mw, _ = middleware(app)
        sent = run(collect(mw, http_scope("POST"), [
            {"type": "http.request", "body": b"abc", "more_body": True},
            {"type": "http.request", "body": b"def", "more_body": False},
        ]))
        assert sent[0]["status"] == 200
        assert app.received == [{"type": "http.request", "body": b"abcdef", "more_body": False}]

    def test_after_the_replay_receive_is_the_real_channel(self):
        """The session transport listens for the disconnect that ends its SSE
        response; a replay that swallowed it would hold the stream open."""
        seen: list[dict] = []

        async def app(scope, receive, send):
            seen.append(await receive())
            seen.append(await receive())
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        mw, _ = middleware(app)
        run(collect(mw, http_scope("POST"), [
            {"type": "http.request", "body": b"{}", "more_body": False},
            {"type": "http.disconnect"},
        ]))
        assert seen == [{"type": "http.request", "body": b"{}", "more_body": False},
                        {"type": "http.disconnect"}]

    def test_get_and_delete_are_passed_through_unread(self, subtests):
        for method in ("GET", "DELETE"):
            with subtests.test(method=method):
                app = Recorder()
                mw, _ = middleware(app)
                # No messages at all: the middleware must not call receive.
                sent = run(collect(mw, http_scope(method, path="/mcp/session/"), []))
                assert app.called and sent[0]["status"] == 200

    def test_a_client_that_disconnects_mid_body_gets_nothing(self):
        app = Recorder()
        mw, _ = middleware(app)
        sent = run(collect(mw, http_scope("POST"), [
            {"type": "http.request", "body": b"abc", "more_body": True},
            {"type": "http.disconnect"},
        ]))
        assert sent == [] and app.called is False


# ---------------------------------------------------------------------------
# disabled
# ---------------------------------------------------------------------------


class TestDisabled:
    def test_the_local_default_never_refuses(self, env):
        """The existing suites hammer one app from one client. Off by default
        off a public deployment, so they measure what they always measured."""
        client = TestClient(create_app())
        for _ in range(250):
            assert client.get("/health").status_code == 200
        for _ in range(250):
            assert mcp_post(client, json_body=health_call()).status_code == 200
        big = mcp_post(client, json_body=health_call("x" * 2_000_000))
        assert big.status_code == 200
        counters = client.app.state.maxey0_surface.rate_limiter.report(
            public_deployment=False)["counters"]
        assert counters["limited"] == {"ip": 0, "principal": 0, "session_open": 0,
                                       "auth_failures": 0}

    def test_forced_off_is_off_on_a_public_deployment_too(self, env):
        env.setenv("MAXEY0_PUBLIC", "1")
        env.setenv("MAXEY0_RATE_LIMIT_ENABLED", "off")
        env.setenv("MAXEY0_RATE_LIMIT_IP_PER_MIN", "1")
        client = TestClient(create_app())
        assert all(client.get("/health").status_code == 200 for _ in range(20))


# ---------------------------------------------------------------------------
# the session transport's own caps
# ---------------------------------------------------------------------------


class TestSessionCaps:
    def test_configured_caps_reach_the_manager(self, env):
        env.setenv("MAXEY0_RATE_LIMIT_ENABLED", "1")
        env.setenv("MAXEY0_SESSION_MAX", "7")
        env.setenv("MAXEY0_SESSION_IDLE_TIMEOUT_S", "33")
        env.setenv("MAXEY0_MAX_REQUEST_BYTES", "2048")
        app = create_app()
        manager = app.state.session_manager
        assert (manager.max_sessions, manager.session_idle_timeout,
                manager.max_request_body_size) == (7, 33.0, 2048)
        caps = app.state.maxey0_surface.rate_limiter.report(
            public_deployment=False)["request_caps"]["session"]
        assert caps == {
            "max_sessions": {"variable": "MAXEY0_SESSION_MAX", "value": 7, "applied": True},
            "session_idle_timeout": {"variable": "MAXEY0_SESSION_IDLE_TIMEOUT_S",
                                     "value": 33.0, "applied": True},
            "max_request_body_size": {"variable": "MAXEY0_MAX_REQUEST_BYTES",
                                      "value": 2048, "applied": True},
        }

    def test_the_defaults_apply_when_enabled_with_nothing_set(self, env):
        env.setenv("MAXEY0_PUBLIC", "1")
        manager = create_app().state.session_manager
        assert (manager.max_sessions, manager.session_idle_timeout,
                manager.max_request_body_size) == (50, 600.0, 1048576)

    def test_disabled_leaves_the_sdk_defaults_and_says_so(self, env):
        import inspect

        from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

        sdk = inspect.signature(StreamableHTTPSessionManager.__init__).parameters
        app = create_app()
        manager = app.state.session_manager
        for name in ("max_sessions", "session_idle_timeout", "max_request_body_size"):
            assert getattr(manager, name) == sdk[name].default
        caps = app.state.maxey0_surface.rate_limiter.report(
            public_deployment=False)["request_caps"]["session"]
        assert all(c["applied"] is False and "off" in c["reason"] for c in caps.values())

    def test_a_cap_the_sdk_does_not_accept_is_reported_not_dropped(self):
        class OlderManager:
            def __init__(self, app, stateless=False, max_sessions=None):
                pass

        kwargs, report = session_manager_caps(RateLimitConfig(enabled=True), OlderManager)
        assert kwargs == {"max_sessions": 50}
        assert report["max_sessions"]["applied"] is True
        for name in ("session_idle_timeout", "max_request_body_size"):
            assert report[name]["applied"] is False
            assert "does not accept" in report[name]["reason"]


# ---------------------------------------------------------------------------
# process shape
# ---------------------------------------------------------------------------


class TestProcessShape:
    def test_public_server_turns_uvicorn_proxy_headers_off(self, monkeypatch):
        import maxey0_ss.public_server as public_server

        calls = []
        monkeypatch.setattr(public_server.uvicorn, "run",
                            lambda app, **kwargs: calls.append((app, kwargs)))
        public_server.main()
        assert len(calls) == 1
        app, kwargs = calls[0]
        assert app is public_server.app
        assert kwargs["proxy_headers"] is False

    def test_maxey0_ss_and_api_entry_points_turn_proxy_headers_off_too(self, monkeypatch):
        """`maxey0-ss` and `maxey0-ss-api` left uvicorn's X-Forwarded-For
        handling on while auth.manifest reported it off."""
        import uvicorn

        import maxey0_ss.__main__ as entry

        calls = []
        monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: calls.append(kwargs))
        entry.main()
        assert len(calls) == 1
        assert calls[0]["proxy_headers"] is False

    def test_the_scheme_survives_from_a_trusted_peer(self, env):
        """proxy_headers=False also stopped uvicorn setting the scheme, and the
        router's trailing-slash redirect is how the documented session URL
        reaches the mount. Applies with the limiter off, too."""
        app = create_app()
        tunnel = TestClient(app, client=("127.0.0.1", 1), follow_redirects=False)
        redirected = tunnel.post("/mcp/session", headers={"X-Forwarded-Proto": "https"})
        assert redirected.status_code == 307
        assert redirected.headers["location"].startswith("https://")

    def test_the_scheme_is_not_taken_from_anyone_else(self, env):
        app = create_app()
        stranger = TestClient(app, client=("198.51.100.4", 1), follow_redirects=False)
        redirected = stranger.post("/mcp/session", headers={"X-Forwarded-Proto": "https"})
        assert redirected.headers["location"].startswith("http://")

    def test_generated_docs_are_not_served_publicly(self, env, subtests):
        env.setenv("MAXEY0_PUBLIC", "1")
        client = TestClient(create_app())
        for path in ("/docs", "/redoc", "/openapi.json"):
            with subtests.test(path=path):
                assert client.get(path).status_code == 404

    def test_generated_docs_stay_for_local_development(self, env, subtests):
        client = TestClient(create_app())
        for path in ("/docs", "/redoc", "/openapi.json"):
            with subtests.test(path=path):
                assert client.get(path).status_code == 200
