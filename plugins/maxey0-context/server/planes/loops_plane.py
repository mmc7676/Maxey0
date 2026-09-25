"""The Loop plane — the library, the routing decision, and cross-window runs.

This plane decides who should act and in what shape. It holds no window state,
opens no ledger, and writes nothing to `~/.scw/`. That is what makes it the one
connector you can install entirely on its own and still get value from: routing
a task against 16 concepts, 83 skills, 67 agents and 84 hardened loops, and
running a cross-window topology, against an entirely fixed context scheme.

It is deliberately incapable of binding anything. `loops_route` scores a task
and explains the decision; committing that decision to a real partition is
`context_route_bind`, on the Context plane, because that call writes the
window. When the Context plane is not installed, `loops_route` still answers —
it just cannot be followed by a bind, and it says so.
"""

from __future__ import annotations

import importlib.util
from typing import Any

from . import bootstrap, catalog, menu

bootstrap.prepare()

CONNECTOR = "maxey0-loops"

INSTRUCTIONS = """\
The Maxey0 library and the routing decision over it: 16 concepts, 83 skills,
67 agents, and 84 agentic loops each carrying its real hardening record.

Start with `loops_route` on the task in plain language. Do not assume you are
in the right place because the task mentions a concept's vocabulary — a
coherent hit often names a different concept's formation, and a routing miss is
a real finding about library coverage rather than an error to hide.

Routing first is not a formality. One measured case: a documentation-audit task
routed to a pre-scoped four-agent formation at roughly 10,800 tokens; the same
task run as two improvised subagents with hand-written personas cost 253,481,
for a worse-scoped result.

`loops_route` binds nothing. To make the partition real, call
`context_route_bind` on the Context plane. If that connector is not installed,
say so rather than improvising a partition this plane cannot enforce.

`loops_menu` prints the whole product surface, rendered from the registry.\
"""

_TOOL_SOURCES = {
    "loops_menu": ("menu", "loops_menu"),
    "loops_concepts": ("impl", "maxey0_concepts"),
    "loops_skills": ("impl", "loops_skills"),
    "loops_agents": ("impl", "maxey0_agents"),
    "loops_catalog": ("impl", "maxey0_loops"),
    "loops_route": ("impl", "maxey0_route"),
    "loops_crosswindow_create": ("impl", "maxey0_cross_window_create"),
    "loops_crosswindow_status": ("impl", "maxey0_cross_window_status"),
    "loops_crosswindow_ingest": ("impl", "maxey0_cross_window_ingest"),
    "loops_crosswindow_report": ("impl", "maxey0_cross_window_report"),
}


def context_plane_installed() -> bool:
    """Whether a Context plane exists in this environment to bind into.

    Import-checked. The Loop plane works without one; it just cannot commit a
    routing decision, and every caller deserves to be told which of those two
    situations it is in.
    """
    try:
        return importlib.util.find_spec("scw_runtime.server") is not None
    except (ImportError, ValueError):
        return False


def build() -> Any:
    """Construct this plane's MCP server with its 10 tools."""
    from mcp.server.fastmcp import FastMCP

    from . import loops_impl

    mcp = FastMCP(CONNECTOR, instructions=INSTRUCTIONS)
    for tool in catalog.LOOPS:
        kind, attr = _TOOL_SOURCES[tool.name]
        fn = getattr(menu if kind == "menu" else loops_impl, attr)
        bootstrap.register(mcp, tool, fn)
    return mcp


def main() -> None:
    bootstrap.require_mcp(CONNECTOR)
    build().run()
