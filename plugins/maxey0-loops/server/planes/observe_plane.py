"""The Observatory plane — the Gate, the evidence, and the Studio.

This plane records what actually happened and refuses what left scope. It is
the plane with visibility into the other two, and it has that visibility
without authority over either: it reads the Context plane's ledger and the
Gate's journal as files, and replays the former when it needs structure rather
than a record list.

Installed alone it is still a complete instrument. The Gate is a hook, resident
at every tool call in every session; it attributes each call to the role that
made it and, in `enforce`, refuses the ones reaching outside that role's
declared scope. No window and no library are required for that to be true and
useful — which is the whole of what "global workspace semantics" buys you.

It installs inert. The default mode is `observe`, so it records and blocks
nothing until a policy is declared and `enforce` is set.
"""

from __future__ import annotations

from typing import Any

from . import bootstrap, catalog

bootstrap.prepare()

CONNECTOR = "maxey0-observe"

INSTRUCTIONS = """\
Evidence about what agents actually did, and the Gate that produced it.

The Gate sits at every tool call. A tool call is the only moment an agent
running in a delegated context has to ask its host for something, so it is the
only place an outside observer can stand. Between two tool calls a subagent is
a sealed box.

Three modes. `observe` is not a weaker `enforce`: it is the only way to measure
how often a role *attempts* to leave its partition, which is a property of the
formation rather than of the enforcement.

Two rules that are never broken. A broken gate must never break a session. A
gate that fails open must say so — silently allowing a call it could not
evaluate would manufacture containment out of a malfunction.

Read every figure the way this plane reports it. `contained` and `held` are
three-valued, and **null is not zero**: it means the quantity was never
established. `claimable` is false whenever any residue exists — an unattributed
call, a fail-open, a lost record — because a run with residue has a hole
exactly where the containment claim would go. Report `claimable` verbatim and
name the residue rather than averaging it away.

This plane reads the Context plane's ledger from disk. When there is no ledger,
it says so, and that establishes nothing in either direction.\
"""

_TOOL_SOURCES = {
    "observe_events": "observe_events",
    "observe_attempts": "observe_attempts",
    "observe_traces": "observe_traces",
    "observe_gate_mode": "observe_gate_mode",
    "observe_gate_policy": "observe_gate_policy",
    "observe_gate_activity": "observe_gate_activity",
    "observe_isolation_level": "observe_isolation_level",
    "observe_studio": "observe_studio",
}


def build() -> Any:
    """Construct this plane's MCP server with its 8 tools."""
    from mcp.server.fastmcp import FastMCP

    from . import observe_impl

    mcp = FastMCP(CONNECTOR, instructions=INSTRUCTIONS)
    for tool in catalog.OBSERVE:
        fn = getattr(observe_impl, _TOOL_SOURCES[tool.name])
        bootstrap.register(mcp, tool, fn)
    return mcp


def main() -> None:
    bootstrap.require_mcp(CONNECTOR)
    build().run()
