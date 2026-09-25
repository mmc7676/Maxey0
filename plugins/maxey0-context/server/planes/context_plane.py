"""The Context plane — Structured Context Windows, and the only writer of them.

This plane holds bytes and refuses reads. It owns the live window, the scopes
bound to it, the bridges across it, and the hash-chained ledger that records
every decision either way.

**Why this plane owns the assertions and the binding router.** The window is
process-local state. A tool in another process would act on a different window,
so every tool that touches the live window has to live here — including the
four containment assertions, which prove containment by performing a real read
through the real authorization path rather than by computing set membership,
and `context_route_bind`, which is the routing decision that actually commits.
The Loop plane keeps the routing decision that does not commit, and the
Observatory reads the resulting records from the ledger file.

Installed alone, this plane is a complete partitioned-context runtime: create
regions, bind roles, mint bridges, render scope-true prompts, and verify the
chain. Nothing here needs the loop library or the Gate.
"""

from __future__ import annotations

from typing import Any

from . import bootstrap, catalog

bootstrap.prepare()

CONNECTOR = "maxey0-context"

INSTRUCTIONS = """\
Structured Context Windows: partition the context window into addressable,
typed regions, bind a role's scope to one region, and enforce isolation at the
tool layer rather than by prompt wording.

Typical order:
  context_window_reset
  context_region_create   one per region type
  context_region_write    reference material, as the host, before binding
  context_criterion_pin   if anything will be graded
  context_harness_create  architecture="maker_checker" makes self-approval a refusal
  context_scope_bind      one role per region
  context_window_seal
then per iteration: context_region_write / context_region_read /
context_window_render / context_bridge_open / context_bridge_promote /
context_scope_tick, closing with context_scope_unbind.

Region types are policies, not labels: reference is read-only, durable and
episodic are writable and bridgeable, working and scratchpad are unbridgeable
by construction so there is no grant to mint.

A refusal is a normal, informative outcome. Read the `hint` field — it names
the bridge that would make the access legal. Never route around a refusal to
make an operation succeed; report it.

Bridges and scope are ingress: they decide what a role may reach. Before a
declared handoff region actually carries content, gate it with
context_admit(from_role, to_role, from_region, to_region, rule) — approve,
summarize, redact, or reject. Every outcome, including reject, is recorded;
context_assert_admitted(from_role, to_role) finds any handoff a scope permits
that no admission has ever governed.

To prove containment rather than assert it, use context_assert_cannot_read:
it attempts a real read and expects to be refused, and the refusal lands in
the ledger as a record that replay reproduces.\
"""


def build() -> Any:
    """Construct this plane's MCP server with its 32 tools."""
    from mcp.server.fastmcp import FastMCP  # noqa: PLC0415

    runtime = bootstrap.open_runtime()
    mcp = FastMCP(CONNECTOR, instructions=INSTRUCTIONS)

    # The vendored runtime implements 26 of these. `_tool` has already wrapped
    # each one so a refusal comes back structured rather than as an exception.
    for tool in catalog.CONTEXT:
        fn = _implementation(tool, runtime)
        bootstrap.register(mcp, tool, fn)

    return mcp


def _implementation(tool: catalog.Tool, runtime: Any) -> Any:
    """Resolve a catalog entry to the function that implements it."""
    legacy = tool.legacy
    if legacy is not None and hasattr(runtime, legacy):
        return getattr(runtime, legacy)

    # The four assertions, the concept-window builder, and every tool with no
    # 0.6.0 predecessor were declared here rather than in the vendored
    # runtime. A tool with a real predecessor keeps that name as `legacy`; one
    # with none resolves by its own suffix, so `legacy` is never pressed into
    # meaning "retired" for a name that was never live.
    from . import context_extras  # noqa: PLC0415

    attr = legacy or tool.name.removeprefix("context_")
    if hasattr(context_extras, attr):
        return getattr(context_extras, attr)
    raise KeyError(f"{tool.name} has no implementation")


def main() -> None:
    bootstrap.require_mcp(CONNECTOR)
    build().run()
