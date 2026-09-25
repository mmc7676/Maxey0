"""Loop-plane tools — the library, the routing decision, and cross-window runs.

This plane decides **who should act and in what shape**. It holds no window
state whatsoever, and that is the point rather than an accident: with no live
window to keep, this connector can be installed on its own and used to route a
task to a pre-scoped formation against an entirely fixed context scheme, with
no enforcement engine present.

The split between the two routing tools is the sharpest instance of the plane
rule. `loops_route` scores a task and explains the decision, and binds nothing;
`context_route_bind` asks the same question and commits. One reads, the other
writes the window — so they live on different planes, and the names now say
which is which.

Cross-window runs live here because they are a **topology**, not a partition:
one genuinely separate model call per participant, zero shared token buffer, no
region to bind. Isolation there comes from what the operator puts in each
prompt, and `loops_crosswindow_report` checks it by grepping every dispatched
prompt for the other participants' markers — real leak detection over the
actual text, not an assertion that there was none.
"""

from __future__ import annotations

from typing import Optional

from . import bootstrap

bootstrap.prepare()

import maxey0_studio.state as st
from maxey0_studio import cross_window as cw

from .results import tool as _tool

_KNOWLEDGE: dict = {}


def knowledge() -> st.Knowledge:
    """The library, loaded once per process and cached.

    Read-only in every sense that matters: nothing on this plane mutates it,
    and nothing on this plane writes the ledger.
    """
    if "value" not in _KNOWLEDGE:
        _KNOWLEDGE["value"] = st.Knowledge.load()
    return _KNOWLEDGE["value"]


def maxey0_loops(concept: str = "", status: str = "", limit: int = 25) -> dict:
    """Browse the agentic loop library.

    Each entry is a real, hardened composition: its regions, roles and refusals
    were built against a live ContextWindow before it was written down (or, for
    a cross-window entry, its containment was checked against the actual
    dispatched prompts of a real run). Filter by `concept` (a Maxey0 concept id)
    and/or `status` (validated | partial | draft-unexecuted).
    """
    loops = knowledge().loops
    if concept:
        loops = [l for l in loops if concept in l.get("concept_tags", [])]
    if status:
        loops = [l for l in loops if l.get("status") == status]
    return {
        "count": len(loops),
        "loops": [
            {"id": l["id"], "title": l["title"], "status": l["status"],
             "provenance": l["provenance"], "execution_mode": l.get("execution_mode"),
             "concept_tags": l.get("concept_tags", []),
             "stages": len(l.get("agent_stages") or l.get("roles") or []),
             "reduction_ratio": l.get("hardening", {}).get("reduction_ratio"),
             "notes": l.get("notes", "")[:220]}
            for l in loops[:limit]
        ],
        "truncated": max(0, len(loops) - limit),
    }


def maxey0_concepts() -> dict:
    """The 16 Maxey0 concepts a task routes against, with their tag vocabularies."""
    k = knowledge()
    counts: dict[str, int] = {}
    for loop in k.loops:
        for c in loop.get("concept_tags", []):
            counts[c] = counts.get(c, 0) + 1
    return {
        "concepts": [
            {"id": c["id"], "title": c.get("title", c["id"]),
             "concept_type": c.get("concept_type", ""), "tags": c.get("tags", []),
             "loops": counts.get(c["id"], 0)}
            for c in k.concepts
        ],
        "counts": k.counts(),
    }


def maxey0_route(task: str) -> dict:
    """Score a task against the concept graph and report the routing decision:
    an existing hardened loop (not yet bound -- that needs `worlds`), a set of
    matching skills, or a set of matching agents. Read-only: this never binds
    anything. Use `route_task` from the `worlds` server to route AND bind in
    one call.
    """
    return {"ok": True, **st.route(task, knowledge())}


def maxey0_agents(concept: str = "", limit: int = 25) -> dict:
    """List deployed Maxey0 agents, optionally filtered to those assigned a
    skill under `concept`."""
    agents = knowledge().agents
    if concept:
        agents = [a for a in agents
                 if any(x.get("concept") == concept for x in a.get("assignments", []))]
    return {
        "count": len(agents),
        "agents": [
            {"registry_index": a["registry_index"], "name": a["name"],
             "specialization": a.get("specialization", ""),
             "provenance": a.get("provenance", "")}
            for a in agents[:limit]
        ],
        "truncated": max(0, len(agents) - limit),
    }

def loops_skills(concept: str = "", limit: int = 40) -> dict:
    """The 83 skills in the library, grouped by concept.

    Until 0.7.0 the skills were the one level of the library with no tool of
    its own: concepts, agents and loops were each browsable and the 83 skills
    between them were reachable only by reading the manifest. A user asking
    "what can this thing actually do" was being answered one level too coarse.

    Each entry carries the agents bound to it and the role each one plays, so
    a formation is visible before anything is routed or bound.
    """
    k = knowledge()
    skills = k.skills
    if concept:
        skills = [s for s in skills if s.get("concept") == concept]
    rows = []
    for s in skills[:limit]:
        agents = s.get("agents") or []
        rows.append({
            "id": s["id"],
            "title": s.get("title", s["id"]),
            "concept": s.get("concept", ""),
            "concept_type": s.get("concept_type", ""),
            "memory_tier": s.get("memory_tier", ""),
            "tags": s.get("tags", []),
            "description": (s.get("description") or "")[:220],
            "formation": [
                {"name": a.get("name", ""), "role": a.get("role", "")}
                for a in agents
            ],
        })
    by_concept: dict[str, int] = {}
    for s in k.skills:
        by_concept[s.get("concept", "")] = by_concept.get(s.get("concept", ""), 0) + 1
    return {
        "count": len(skills),
        "total": len(k.skills),
        "skills": rows,
        "truncated": max(0, len(skills) - limit),
        "by_concept": by_concept,
    }


@_tool
def maxey0_cross_window_create(loop_id: str) -> dict:
    """Plan a real cross-window run: one genuinely separate call per Maxey#/SCW#
    participant, zero shared token buffer between any two.

    This cannot dispatch the model calls itself -- a cross-window run has no
    single window to bind, so there is nothing for a Python function to call
    into. It returns the first pending call; the caller (you) dispatches it as
    one Agent-tool subagent using ONLY that call's prompt -- see
    /maxey0:cross-window for the exact loop. Known topologies:
    designer:01-horizontal-4way, designer:02-vertical-nesting,
    designer:03-fanin-scaling, designer:04-adversarial-embedded-canary,
    designer:05-multiround-persistence.
    """
    try:
        run = cw.CrossWindowRun.create(loop_id)
    except ValueError as exc:
        return {"ok": False, "error": "unknown_topology", "message": str(exc)}
    return {"run_id": run.run_id, **run.status()}


@_tool
def maxey0_cross_window_status(run_id: str) -> dict:
    """The next pending call in a cross-window run, or confirmation it's complete."""
    run = cw.CrossWindowRun.load(run_id)
    if run is None:
        return {"ok": False, "error": "unknown_run"}
    return run.status()


@_tool
def maxey0_cross_window_ingest(run_id: str, call_id: str, response: str) -> dict:
    """Record one participant's real response and splice it into whatever
    downstream call declared it may read this participant's output."""
    run = cw.CrossWindowRun.load(run_id)
    if run is None:
        return {"ok": False, "error": "unknown_run"}
    return run.ingest(call_id, response)


@_tool
def maxey0_cross_window_report(run_id: str) -> dict:
    """Structural containment for a cross-window run, checked mechanically:
    every participant's actual dispatched prompt is grepped for every other
    participant's private markers and response text it wasn't granted. Any
    hit is a named, real leak -- not an assumption that isolation held."""
    run = cw.CrossWindowRun.load(run_id)
    if run is None:
        return {"ok": False, "error": "unknown_run"}
    return run.report()
