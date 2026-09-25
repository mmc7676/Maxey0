"""The canonical catalog — one source of truth for the whole product.

Every name a user can type is declared here exactly once: the tool, the
connector that serves it, what it does, and the 0.6.0 name it replaced. The
connector servers register from this table, `loops_menu` renders from it,
`scripts/check_lexicon.py` enforces it, `scripts/generate_ui_types.py` emits the
TypeScript from it, and the documentation quotes it. A tool that is not in this
table does not exist; a tool in this table that no connector registers fails
validation.

THE ARCHITECTURE, AND WHY IT IS THREE PLANES
--------------------------------------------
Maxey0 is three planes, and it deliberately owns only two of them:

    Execution     the host's. Agents, agentic loops, LLM calls, tool calls,
                  working memory, generated output. Maxey0 adds NO capability
                  here. It constrains this plane and observes it, and that
                  restraint is the product: almost every other agent framework
                  competes by adding capability to exactly this plane.

    Context       Maxey0's. Concepts, Skills, SCWs, regions, scopes, admission
                  gates, routing, provenance. Everywhere else this is an
                  unstructured string assembled just before a call. Here it is
                  independently structured, routable, partitionable, and
                  addressable.

    Engineering   Maxey0's. The Gate, the hash-chained ledger, the three
                  correlated traces, the isolation ladder, the Studio. It
                  observes and tunes the other two.

PLANES ARE NOT CONNECTORS
-------------------------
A plane is what the system *is*. A connector is what *installs*. They are
different decompositions and the mapping is many-to-one:

    maxey0-context   -> Context plane      the state machinery (SCWs)
    maxey0-loops     -> Context plane      the semantic machinery (the library)
    maxey0-observe   -> Engineering plane  the Gate and the evidence
    (no connector)   -> Execution plane    owned by the host; the Gate stands
                                           at its boundary rather than inside it

WHAT DECIDES WHICH CONNECTOR A TOOL BELONGS TO
----------------------------------------------
The window is process-local state. A tool that reads or writes the live window
cannot live in a different process from the window, so the four containment
assertions sit on `maxey0-context` (they prove containment by performing a real
read through the real authorization path) and the Engineering plane reads the
resulting records from the ledger file instead.
"""

from __future__ import annotations

from typing import NamedTuple


class Tool(NamedTuple):
    """One entry in the product surface."""

    name: str
    connector: str
    group: str
    summary: str
    legacy: str | None
    mutates: bool


CONNECTORS: dict[str, dict[str, str]] = {
    "context": {
        "connector": "maxey0-context",
        "plane": "context",
        "title": "Context",
        "tagline": "Partition the window and enforce who reads what.",
        "owns": "Structured Context Windows: regions, scopes, bridges, grants, "
                "harnesses, ticks, and the hash-chained ledger.",
        "alone": "Partition a context window and enforce access without ever "
                 "routing a task or watching an agent.",
    },
    "loops": {
        "connector": "maxey0-loops",
        "plane": "context",
        "title": "Loop",
        "tagline": "Decide who should act, and in what shape.",
        "owns": "The library — 16 concepts, 83 skills, 67 agents, 84 hardened "
                "loops — plus routing and cross-window topologies.",
        "alone": "Route a task to a pre-scoped formation and run it against a "
                 "fixed context scheme, with no enforcement engine installed.",
    },
    "observe": {
        "connector": "maxey0-observe",
        "plane": "engineering",
        "title": "Observatory",
        "tagline": "Record what happened, and refuse what left scope.",
        "owns": "The Gate, the event stream, correlated traces, isolation "
                "levels, and the Studio.",
        "alone": "Attribute and refuse any delegated agent's tool calls — "
                 "global workspace semantics — with no window and no library.",
    },
}


#: The three architectural planes. Maxey0 owns two of them; the restraint about
#: the third is the product's whole differentiation, so it is declared here
#: rather than left implicit in prose.
PLANES: dict[str, dict[str, str]] = {
    "execution": {
        "title": "Execution",
        "owner": "the host",
        "holds": "Agents, agentic loops, LLM calls, tool calls, working "
                 "memory, generated output.",
        "maxey0": "Adds no capability here. Constrains it at the tool call and "
                  "observes what crossed.",
        "connectors": "",
    },
    "context": {
        "title": "Context",
        "owner": "Maxey0",
        "holds": "Concepts, Skills, SCWs, regions, scopes, admission gates, "
                 "routing, provenance.",
        "maxey0": "Makes it independently structured, routable, partitionable "
                  "and addressable, instead of a string assembled before a call.",
        "connectors": "maxey0-context, maxey0-loops",
    },
    "engineering": {
        "title": "Engineering",
        "owner": "Maxey0",
        "holds": "The Gate, the hash-chained ledger, the three correlated "
                 "traces, the isolation ladder, the Studio.",
        "maxey0": "Observes and tunes the other two. Sees both; neither sees it.",
        "connectors": "maxey0-observe",
    },
}

# --------------------------------------------------------------------------
# maxey0-context — the live window. 32 tools.
# --------------------------------------------------------------------------
CONTEXT: tuple[Tool, ...] = (
    Tool("context_prompt_create", "context", "prompt",
         "Declare an instruction as versioned data rather than as prose.",
         "create_prompt", True),
    Tool("context_prompt_revise", "context", "prompt",
         "Edit a prompt, keeping the superseded version in history.",
         "revise_prompt", True),
    Tool("context_prompt_render", "context", "prompt",
         "Materialize a prompt against variable bindings.",
         "render_prompt", False),

    Tool("context_region_create", "context", "region",
         "Create one typed, budgeted, addressable region of the window.",
         "create_scw", True),
    Tool("context_region_close", "context", "region",
         "Seal a region, or destroy its content when purge_on_close is set.",
         "close_scw", True),
    Tool("context_region_write", "context", "region",
         "Write content into a region. Pass role and the call is scope-checked.",
         "write", True),
    Tool("context_region_read", "context", "region",
         "Read a region. Refused, with a hint, when the role's scope excludes it.",
         "read", False),

    Tool("context_harness_create", "context", "harness",
         "Declare the environment and architecture a loop runs under. "
         "maker_checker makes self-approval a refusal rather than a policy.",
         "create_harness", True),
    Tool("context_harness_call", "context", "harness",
         "Record a role invoking a named skill under a harness profile.",
         "harness_call", True),

    Tool("context_scope_bind", "context", "scope",
         "Bind a role's execution scope to one region and declare its spec.",
         "bind_scope", True),
    Tool("context_scope_unbind", "context", "scope",
         "Release a role's scope with a terminal state that has to be earned.",
         "unbind_scope", True),
    Tool("context_scope_closure", "context", "scope",
         "The computed set of regions a role can actually reach, read and write.",
         "scope_closure", False),
    Tool("context_scope_tick", "context", "scope",
         "Advance one iteration and price it. Call once per model call.",
         "loop_tick", True),

    Tool("context_bridge_open", "context", "bridge",
         "Mint an explicit, expiring grant across a region boundary.",
         "open_bridge", True),
    Tool("context_bridge_close", "context", "bridge",
         "Revoke a grant before its TTL expires.",
         "close_bridge", True),
    Tool("context_bridge_promote", "context", "bridge",
         "Move content across a region boundary with provenance attached.",
         "promote", True),

    Tool("context_criterion_pin", "context", "evidence",
         "Freeze the region a run will be graded against, before it runs.",
         "pin_criterion", True),
    Tool("context_criterion_repin", "context", "evidence",
         "Accept the criterion's current bytes as the new yardstick.",
         "repin_criterion", True),
    Tool("context_evidence_attest", "context", "evidence",
         "Record an external result for a forthcoming verdict.",
         "attest_evidence", True),

    Tool("context_window_inspect", "context", "window",
         "Region map, token accounting, cache economics, and advisories.",
         "inspect_window", False),
    Tool("context_window_render", "context", "window",
         "Materialize the window as prompt text. Scope-true for a bound role.",
         "render_window", False),
    Tool("context_window_disjointness", "context", "window",
         "Would this judge's verdict on this maker be accepted, and if not why.",
         "check_disjointness", False),
    Tool("context_window_seal", "context", "window",
         "End setup and close the privileged unbound path.",
         "seal_window", True),
    Tool("context_window_reset", "context", "window",
         "Tear the window down and start a fresh run. Destructive.",
         "reset_window", True),

    Tool("context_assert_can_read", "context", "assert",
         "Attempt a real read and expect it to be authorized.",
         "assert_can_read", True),
    Tool("context_assert_cannot_read", "context", "assert",
         "Attempt a real read and expect a refusal. Reports breach if it succeeds.",
         "assert_cannot_read", True),
    Tool("context_assert_scope_closed", "context", "assert",
         "The closure equals what was declared, computed over the region graph.",
         "assert_scope_closed", False),
    Tool("context_assert_disjoint", "context", "assert",
         "No private working space is shared. Overlap is classified: a pad "
         "both reach fails; a declared handoff and unwritable reference do not.",
         "assert_disjoint", False),

    Tool("context_route_bind", "context", "route",
         "Route a task and bind the matching loop's partition in this window.",
         "route_task", True),
    Tool("context_formation_build", "context", "route",
         "Build a maker/checker/judge partition from a named concept.",
         "create_concept_scw", True),

    Tool("context_admit", "context", "admit",
         "Gate a content handoff between two roles: approve, summarize, "
         "redact, or reject what crosses. Egress, where bridges are ingress.",
         None, True),
    Tool("context_assert_admitted", "context", "assert",
         "Every region from_role can write and to_role can read has a "
         "recorded context_admit decision naming the pair.",
         None, False),
)

# --------------------------------------------------------------------------
# maxey0-loops — the library and the routing decision. No window state. 10 tools.
# --------------------------------------------------------------------------
LOOPS: tuple[Tool, ...] = (
    Tool("loops_menu", "loops", "surface",
         "The whole Maxey0 control surface, rendered from the registry.",
         None, False),
    Tool("loops_concepts", "loops", "library",
         "The 16 concepts, their tag vocabularies, and their loop coverage.",
         "maxey0_concepts", False),
    Tool("loops_skills", "loops", "library",
         "The 83 skills, grouped by concept, with the agents each one binds.",
         None, False),
    Tool("loops_agents", "loops", "library",
         "The 67 registry agents and their specializations.",
         "maxey0_agents", False),
    Tool("loops_catalog", "loops", "library",
         "The 84 hardened loops, filterable, each with its hardening record.",
         "maxey0_loops", False),
    Tool("loops_route", "loops", "route",
         "Score a task against the library and explain the decision. "
         "Binds nothing — use context_route_bind to commit.",
         "maxey0_route", False),

    Tool("loops_crosswindow_create", "loops", "crosswindow",
         "Plan a cross-window run over one of the five topologies.",
         "maxey0_cross_window_create", True),
    Tool("loops_crosswindow_status", "loops", "crosswindow",
         "The next pending call in a cross-window run.",
         "maxey0_cross_window_status", False),
    Tool("loops_crosswindow_ingest", "loops", "crosswindow",
         "Record one participant's real response and splice it downstream.",
         "maxey0_cross_window_ingest", True),
    Tool("loops_crosswindow_report", "loops", "crosswindow",
         "Grep every dispatched prompt for other participants' markers. "
         "Real leak detection, not an assertion that there was none.",
         "maxey0_cross_window_report", False),
)

# --------------------------------------------------------------------------
# maxey0-observe — evidence, read from disk. 8 tools.
# --------------------------------------------------------------------------
OBSERVE: tuple[Tool, ...] = (
    Tool("observe_events", "observe", "stream",
         "The Context plane's ledger as a typed, queryable stream.",
         "maxey0_observe", False),
    Tool("observe_attempts", "observe", "stream",
         "Did this role attempt this region, and what happened. "
         "contained is three-valued; null means nothing was attempted.",
         "maxey0_access_attempts", False),
    Tool("observe_traces", "observe", "stream",
         "The context, execution and state traces, correlated causally.",
         "maxey0_traces", False),

    Tool("observe_gate_mode", "observe", "gate",
         "Read or set the Gate: enforce, observe, or off.",
         "gate_mode", True),
    Tool("observe_gate_policy", "observe", "gate",
         "Declare what a bound role may reach outside the window.",
         "declare_gate_policy", True),
    Tool("observe_gate_activity", "observe", "gate",
         "What the delegated agents actually did, per role, from the journal.",
         "gate_activity", False),
    Tool("observe_isolation_level", "observe", "gate",
         "Which of L0-L3 the evidence supports, and the shortfall where it "
         "is below what was declared.",
         "isolation_level", False),

    Tool("observe_studio", "observe", "studio",
         "The Studio's address and start command.",
         "maxey0_studio", False),
)

ALL: tuple[Tool, ...] = CONTEXT + LOOPS + OBSERVE

BY_NAME: dict[str, Tool] = {t.name: t for t in ALL}
BY_CONNECTOR: dict[str, tuple[Tool, ...]] = {
    "context": CONTEXT,
    "loops": LOOPS,
    "observe": OBSERVE,
}

#: Every 0.6.0 name that no longer exists, mapped to what replaced it.
#: `scripts/check_lexicon.py` fails the build on any of these appearing
#: outside the migration tables in docs/LEXICON.md.
RETIRED: dict[str, str] = {
    t.legacy: t.name for t in ALL if t.legacy is not None
}

#: The nine Studio views, in the order the Studio presents them.
#:
#: Named here so every surface that lists them copies one table instead of
#: inventing its own -- `menu`, `observe.studio`, the generated UI catalog and
#: the lexicon check all read this. The Studio itself does not: its navigation
#: is hand-written HTML, because it is a stdlib-only server with no template
#: step. So the one surface that *is* these views is the one that could drift
#: from the table describing it, and it had -- Evidence and Gate were declared
#: in the opposite order to the order the Studio shows them, so
#: `observe.studio` reported a running order that did not exist.
#:
#: `tests/test_studio.py` now compares the nav, the sections and this table.
VIEWS: tuple[tuple[str, str], ...] = (
    ("Overview", "Route a task in plain language and watch the decision"),
    ("Mission Control", "Walk concept to skill to agent to dispatch against the live window"),
    ("Concepts", "The 16 concepts and their loop coverage"),
    ("Loops", "All 84, filterable, each with its hardening record"),
    ("Designer", "Compose a formation and harden it before it can be saved"),
    ("Window", "The region map, read through any role's scope"),
    ("Semantic", "Concepts, skills and agents placed in the anchor field, in 3D"),
    ("Evidence", "Containment assertions, the event stream, isolation level"),
    ("Gate", "What the delegated agents actually did, per role"),
)

#: The slash commands, and which plane ships each one.
COMMANDS: tuple[tuple[str, str, str], ...] = (
    ("menu", "loops", "The control surface — every command, tool and asset in one place"),
    ("doctor", "loops", "What is up, what is down, and what is missing"),
    ("window", "context", "Inspect or partition this session's window"),
    ("route", "loops", "Route a task and report the decision, binding nothing"),
    ("run", "context", "Route, bind, dispatch every role, close out"),
    ("crosswindow", "loops", "Run a cross-window topology"),
    ("gate", "observe", "Read or set gate mode; declare a role's reach outside the window"),
    ("assert", "context", "Test containment by attempting a real read"),
    ("studio", "observe", "Start the Studio and hand over its address"),
    ("scw-deploy", "context", "Create the default SCW and report its address, constitution and observability contract"),
)


def counts() -> dict[str, int]:
    """Tool counts per connector, plus the total. Never hand-write these."""
    out = {connector: len(tools) for connector, tools in BY_CONNECTOR.items()}
    out["total"] = len(ALL)
    return out
