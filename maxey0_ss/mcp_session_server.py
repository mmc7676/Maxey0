"""Session-based Streamable HTTP transport for hosts that still open a session.

`mcp_public_server.py` answers the stateless MCP 2026-07-28 surface: no
`initialize`/`initialized` handshake, no `Mcp-Session-Id`. Claude Code and
Claude Desktop's built-in remote-connector UI send `initialize` before
anything else and get `-32601 Method not found` in return — correct for
2026-07-28, but it means that transport cannot serve them remotely.
`mcp_stdio_server.py` already solves this over stdio, for a host that spawns
this process locally. This module is the same session-based protocol over
HTTP, for a host that can only reach a URL.

It defines no tools of its own. `build_server()` in `mcp_stdio_server` already
builds the session-based `Server` from the shared `mcp_surface` — this module
only supplies the one thing that differs from stdio: how a caller's identity
is resolved. stdio carries no credentials and assumes the process being
reachable at all implies local trust; this transport is reachable over the
public tunnel the same as `mcp_public_server`, so it reads the real
`Authorization` header on every request and applies the exact same
`Authorizer` policy — a tool must not be reachable here under weaker
conditions than it is through the stateless transport.
"""
from __future__ import annotations

from .auth.policy import Authorizer, Principal
from .mcp_stdio_server import build_server
from .mcp_surface import Surface, build_surface
from .ratelimit import RateLimitConfig, session_manager_caps
from .system import SuperSpaceSystem

TRANSPORT_NAME = "streamable-http"


def _session_principal(authorizer: Authorizer) -> Principal:
    """Read the current request's `Authorization` header and resolve it.

    The SDK's Streamable HTTP transport threads the live Starlette `Request`
    through `ServerMessageMetadata.request_context` for every message it
    delivers into the session, so this reads fresh per call rather than only
    at the `initialize` that opened the session — a client that changes or
    drops its token mid-session is re-evaluated, not grandfathered in.
    """
    from mcp.server.lowlevel.server import request_ctx

    try:
        ctx = request_ctx.get()
    except LookupError:
        return authorizer.principal(None)
    request = getattr(ctx, "request", None)
    header = request.headers.get("authorization") if request is not None else None
    return authorizer.principal(header)


def build_session_manager(
    system: SuperSpaceSystem | None = None,
    *,
    surface: Surface | None = None,
    authorizer: Authorizer | None = None,
):
    """Build the `StreamableHTTPSessionManager` wrapping the shared surface.

    Pass `surface` to share the one the caller already built for the stateless
    router rather than construct a second `Surface` (and its cache/task store)
    for the same process. Its Authorizer is used unless `authorizer` is passed.

    The session caps come from the surface's rate limiter. The SDK defaults
    are 10,000 sessions, 30 minutes idle and 4 MiB per request, and every open
    session holds a server task and its streams until it idles out: sized for
    a server farm, not for the one shared-cpu, 512 MB Machine fly.toml
    provisions. Which caps the installed SDK accepted is recorded on the
    limiter, so `auth.manifest` reports what was applied rather than what was
    asked for.

    Caller owns running it inside an ASGI lifespan (`async with manager.run()`)
    and mounting `manager.handle_request` at a path — see `api/app.py`.
    """
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

    surface = surface or build_surface(system)
    server = build_server(
        system, surface=surface, principal_resolver=_session_principal,
        transport_name=TRANSPORT_NAME, authorizer=authorizer,
    )
    limiter = surface.rate_limiter
    config = limiter.config if limiter is not None else RateLimitConfig.from_env()
    caps, report = session_manager_caps(config, StreamableHTTPSessionManager)
    if limiter is not None:
        limiter.session_caps = report
    return StreamableHTTPSessionManager(app=server, stateless=False, **caps)
