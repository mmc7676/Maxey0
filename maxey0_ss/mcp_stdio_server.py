"""Classic stdio MCP transport for Maxey0-SuperSpace.

MCP 2026-07-28 removed the ``initialize``/``initialized`` handshake for the
public adapter, so :mod:`maxey0_ss.mcp_public_server` answers ``server/discover``
over stateless HTTP and nothing else. Hosts that still open a session — Claude
Code and Claude Desktop among them — cannot speak to that surface.

This module serves the *same* surface over the session-based stdio protocol
those hosts do speak. It defines no tools of its own: every tool and resource
comes from :mod:`maxey0_ss.mcp_surface`, so the local and remote surfaces
cannot drift apart.

Run it directly::

    python -m maxey0_ss.mcp_stdio_server
"""
from __future__ import annotations

import json
from typing import Any, Callable

from .auth.policy import (
    ANONYMOUS,
    LOCAL_ADMIN,
    AuthError,
    Authorizer,
    Principal,
    is_public_deployment,
)
from .gating.address import EnforceableAddress
from .gating.semantic import SemanticGateProvider, select_semantic_gate
from .mcp_surface import SERVER_NAME, SERVER_VERSION, Surface, build_surface
from .system import SuperSpaceSystem
from .tasks import owned_by

#: Resolves who is calling, given the authorizer. Transport-specific: stdio
#: carries no credentials at all (see `_stdio_principal`); a session-based HTTP
#: transport has a real Authorization header to read instead.
PrincipalResolver = Callable[[Authorizer], Principal]

INSTRUCTIONS = (
    "Maxey0-SuperSpace. Explicit SCW (Structured Context Window) address space over the "
    "Maxey0 context, execution and engineering-observation planes. SCW identifiers such as "
    "SCW0 are application state, not server processes. Tools that read host context require "
    "an explicit enforceable SCW address."
)



def _stdio_principal(authorizer: Authorizer) -> Principal:
    """Resolve who a stdio caller is, given that stdio carries no credentials.

    A local stdio server is spawned by the host as a child process, so reaching
    it already implies local access — that is the same reasoning that makes
    `MAXEY0_AUTH_MODE=disabled` admit LOCAL_ADMIN. On a deployment that declares
    itself public, the anonymous tier applies instead and stdio serves only the
    public tools rather than refusing every call.
    """
    try:
        return authorizer.principal(None)
    except AuthError:
        return ANONYMOUS if is_public_deployment() else LOCAL_ADMIN

def build_server(
    system: SuperSpaceSystem | None = None,
    *,
    surface: Surface | None = None,
    semantic_gate: SemanticGateProvider | None = None,
    principal_resolver: PrincipalResolver | None = None,
    transport_name: str = "stdio",
    authorizer: Authorizer | None = None,
):
    """Build a session-based server over the shared Maxey0 MCP surface.

    Used directly for stdio (`principal_resolver=None`, the stdio-specific
    resolver below) and by :mod:`maxey0_ss.mcp_session_server` for the
    Streamable HTTP transport, which passes a resolver that reads the real
    `Authorization` header instead of assuming local trust. Tools and
    resources are defined once, here, for both.

    Pass `surface` to share one already built elsewhere (the process building
    both this and the stateless HTTP router should build it once) rather than
    have `build_surface` — and the cache/task store it constructs — run twice.

    The Authorizer is the surface's unless one is passed. The session
    transport shares an app with the stateless router and the /v1 middleware,
    and a transport resolving callers with an instance of its own can disagree
    with the one `auth.manifest` reports and the rate limiter charges.
    """
    import mcp.types as types
    from mcp.server.lowlevel import Server
    from mcp.server.lowlevel.helper_types import ReadResourceContents

    surface = surface or build_surface(system)
    # Same provider selection as the HTTP transport, so a tool cannot be
    # reached locally under weaker conditions than it is remotely.
    gate = semantic_gate or select_semantic_gate()
    authorizer = authorizer or surface.authorizer or Authorizer()
    resolve_principal: PrincipalResolver = principal_resolver or _stdio_principal
    tool_map = {t.name: t for t in surface.tools}
    resource_map = {r.uri: r for r in surface.resources}

    server = Server(SERVER_NAME, version=SERVER_VERSION, instructions=INSTRUCTIONS)

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        out: list[types.Tool] = []
        for tool in surface.tools:
            extra: dict[str, Any] = {"_meta": tool.meta} if tool.meta else {}
            out.append(
                types.Tool(
                    name=tool.name,
                    description=tool.description,
                    inputSchema=tool.input_schema,
                    **extra,
                )
            )
        return out

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        tool = tool_map.get(name)
        if tool is None:
            raise ValueError(f"Unknown tool: {name}")
        # Same capability rule as HTTP, resolved by whatever this transport's
        # `resolve_principal` decides a caller's credentials are. stdio carries
        # none — principal(None) raises under MAXEY0_AUTH_MODE=bearer, and it
        # raises before the capability is consulted, so bearer mode used to
        # disable stdio completely — public tools included — with no way for a
        # local client to present a token. A session-based HTTP transport
        # resolves a real Authorization header instead; see mcp_session_server.
        #
        # Server.call_tool()'s dispatcher catches every exception from this
        # handler (McpError included) and folds it into a soft
        # CallToolResult(isError=True) carrying only str(exc) — there is no
        # structured JSON-RPC error code available from inside this handler,
        # unlike the stateless HTTP transport's own response construction.
        try:
            principal = resolve_principal(authorizer)
            for capability in tool.required_capabilities(arguments):
                authorizer.authorize(principal, capability, tool.name)
        except AuthError as exc:
            raise ValueError(str(exc)) from exc
        # Same admission rule the HTTP transport applies, so a tool cannot be
        # reached locally under weaker conditions than it is remotely.
        if tool.requires_scw:
            try:
                parsed = EnforceableAddress.parse(arguments.get("scw_address") or "")
            except ValueError as exc:
                raise ValueError(f"SCW address required: {exc}") from exc
            decision = gate.evaluate(address=parsed.uri(), capability=name, metadata={"transport": transport_name})
            if not decision.allowed:
                raise ValueError(f"SCW semantic gate denied request: {decision.__dict__}")
        with owned_by(principal.subject):
            return tool.handler(arguments)

    @server.list_resources()
    async def list_resources() -> list[types.Resource]:
        out: list[types.Resource] = []
        for res in surface.resources:
            extra: dict[str, Any] = {"_meta": res.meta} if res.meta else {}
            out.append(
                types.Resource(
                    uri=res.uri,
                    name=res.name,
                    description=res.description,
                    mimeType=res.mime_type,
                    **extra,
                )
            )
        return out

    @server.read_resource()
    async def read_resource(uri) -> list[ReadResourceContents]:
        res = resource_map.get(str(uri))
        if res is None:
            raise ValueError(f"Unknown resource: {uri}")
        value = res.reader()
        text = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
        return [ReadResourceContents(content=text, mime_type=res.mime_type)]

    return server


async def _run() -> None:
    from mcp.server.stdio import stdio_server

    server = build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    import anyio

    anyio.run(_run)


if __name__ == "__main__":
    main()
