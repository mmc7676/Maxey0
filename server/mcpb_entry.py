"""MCP entry point for the .mcpb bundle: all three planes on one instance.

Claude Code installs the three planes as three separate connectors, because
installing one without the others is a real choice there — the Context plane
without the library, the Observatory without either. An MCPB bundle declares
exactly one server, so this module presents the union instead.

It re-registers rather than re-implements. The functions registered here are
the same objects the plane servers register, under the same canonical names
from `planes/catalog.py`, so there is one implementation of each tool in this
codebase and not two that can drift.

**What the bundle cannot carry.** Claude Desktop declares an MCP server and
nothing else — `manifest.json` has no hooks field — and it does not dispatch
subagents. The Gate needs both: a hook to intercept a tool call, and delegated
agents whose calls there are to intercept. So `observe_gate_*` is absent here.
That is not an unfinished port; on a host that dispatches no roles there is
nothing to attribute, and shipping tools that would record an empty journal
would manufacture the appearance of evidence.

    python server/mcpb_entry.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from planes import bootstrap, catalog  # noqa: E402

bootstrap.prepare()

#: Gate tools need a host that runs hooks and dispatches subagents.
HOST_CANNOT_RUN = {
    "observe_gate_mode",
    "observe_gate_policy",
    "observe_gate_activity",
}


def build():
    """One FastMCP instance carrying every tool this host can honestly run."""
    from mcp.server.fastmcp import FastMCP

    from planes import context_plane, loops_impl, menu, observe_impl

    runtime = bootstrap.open_runtime()
    mcp = FastMCP(
        "maxey0",
        instructions=(
            "Maxey0 — three planes over one context window. The Context plane "
            "partitions the window and refuses reads outside a role's scope; "
            "the Loop plane routes a task to a pre-scoped formation; the "
            "Observatory reports what the evidence supports.\n\n"
            "The Gate is not available on this host: it needs a hook system "
            "and delegated subagents, and this host has neither. Containment "
            "here is a property of the window, not of the agents."
        ),
    )

    sources = {
        **{t.name: (context_plane._implementation, (t, runtime))
           for t in catalog.CONTEXT},
        "loops_menu": (getattr, (menu, "loops_menu")),
        "loops_concepts": (getattr, (loops_impl, "maxey0_concepts")),
        "loops_skills": (getattr, (loops_impl, "loops_skills")),
        "loops_agents": (getattr, (loops_impl, "maxey0_agents")),
        "loops_catalog": (getattr, (loops_impl, "maxey0_loops")),
        "loops_route": (getattr, (loops_impl, "maxey0_route")),
        "loops_crosswindow_create": (getattr, (loops_impl, "maxey0_cross_window_create")),
        "loops_crosswindow_status": (getattr, (loops_impl, "maxey0_cross_window_status")),
        "loops_crosswindow_ingest": (getattr, (loops_impl, "maxey0_cross_window_ingest")),
        "loops_crosswindow_report": (getattr, (loops_impl, "maxey0_cross_window_report")),
        **{t.name: (getattr, (observe_impl, t.name))
           for t in catalog.OBSERVE if t.name not in HOST_CANNOT_RUN},
    }

    for tool in catalog.ALL:
        if tool.name in HOST_CANNOT_RUN:
            continue
        call, args = sources[tool.name]
        bootstrap.register(mcp, tool, call(*args))

    return mcp


def main() -> None:
    bootstrap.require_mcp("The Maxey0 bundle")
    build().run()


if __name__ == "__main__":
    main()
