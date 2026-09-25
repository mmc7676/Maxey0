"""MCP 2026-07-28 stateless Streamable HTTP transport.

The tools and resources are not defined here — they come from
:mod:`maxey0_ss.mcp_surface`, which every other transport also uses. This module
is only the HTTP adaptation of that surface.
"""
from __future__ import annotations

from .mcp_2026 import build_router
from .mcp_surface import SERVER_NAME, Surface, build_surface
from .system import SuperSpaceSystem


def create_public_router(system: SuperSpaceSystem | None = None, *, surface: Surface | None = None):
    """Build the HTTP router. Pass a `surface` to share one with the caller."""
    surface = surface or build_surface(system)
    return build_router(
        surface.tools,
        surface.resources,
        SERVER_NAME,
        cache=surface.cache,
        tasks=surface.tasks,
    )
