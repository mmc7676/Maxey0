"""Structured **Concept** Windows — the free tier's whole product.

The acronym does double duty on purpose. An SCW is a Structured Context Window,
and it is equally a Structured *Concept* Window, because the thing that makes a
loop's shared context coherent is that all its roles are working on one concept.

That is not wordplay. If a maker, a checker and a judge are all working on
concept X, then X **is** their shared context: the material they may all read,
that none of them may edit, and that the judge grades against. A maker
specialized in producing X, a checker specialized in checking X, and a judge
specialized in judging X are one formation precisely because X is common to all
three and private to none of them.

So a Concept SCW is built from a concept, not assembled by hand:

    concept
      +-- constitution   reference, readonly   what this concept is; everyone reads
      +-- criterion      reference, pinned     what the work is graded against
      +-- skills         reference, readonly   the gates this concept exposes
      +-- <role>-pad     scratchpad            private; bridgeable=false, always
      +-- <handoff>      durable               a role's declared exposure surface

# The vocabulary this implements

A **Skill** is a context-transfer operator from the context plane to the
execution plane. A **Concept** is a structured semantic region containing the
possible operators. An **SCW** is the bounded contextual state-space through
which those operators act on an agentic computation.

Those definitions are load-bearing here. The skills region is not documentation
the roles happen to be able to read — it is the declared set of transfers that
may legally happen, and `render_window` is where one actually occurs.

# What this deliberately does not do

It does not create a runtime. **An SCW is an architectural abstraction; an SCW
runtime is one implementation mechanism**, and conflating them was the error
this design corrected. What makes a partition real is an *independent
state-transition boundary*; a separate runtime is one way to get one, a
separate execution context (a dispatched subagent) is another, and which one a
run achieved is measured afterwards by `gate.levels`, not asserted here.

The free tier ships exactly one formation — maker / checker / judge — because
that is the smallest arrangement in which something must be verified by
something that did not produce it. The full loop library is a different product.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

#: The one formation the open release ships. Each entry declares the role's
#: position in the topology, not merely its name.
#:
#: `reads` names the OTHER roles whose declared handoff this role may read.
#: Note what is absent: no role ever reads another role's pad. A pad is
#: `bridgeable=False` by preset and stays that way, which is what makes
#: "declare an exposure surface" a requirement rather than a formality.
DEFAULT_FORMATION: tuple[dict[str, Any], ...] = (
    {
        "role": "maker",
        "goal": "produce the artifact this concept calls for",
        "exposes": ("draft",),
        "reads": (),
        "verification_level": 3,
    },
    {
        "role": "checker",
        "goal": "check the artifact against the concept, and say what is wrong",
        "exposes": ("review",),
        "reads": ("maker",),
        "verification_level": 3,
    },
    {
        "role": "judge",
        "goal": "grade the artifact against the pinned criterion and return a verdict",
        "exposes": ("verdict",),
        "reads": ("maker", "checker"),
        "verification_level": 4,
    },
)


class ConceptSCWError(ValueError):
    """The concept window could not be built as specified."""


def _slug(text: str) -> str:
    keep = [c if (c.isalnum() or c in "-_") else "-" for c in str(text).lower()]
    return "".join(keep).strip("-") or "concept"


def plan(concept_id: str,
         formation: Sequence[dict] = DEFAULT_FORMATION,
         criterion_text: str = "",
         skills: Sequence[str] = ()) -> dict:
    """The regions, binds and grants a concept window needs — as data.

    Returned before anything is built so it can be inspected, diffed, or
    refused. Every id is derived from the concept, so two concept windows never
    collide in one session.
    """
    base = _slug(concept_id)
    roles = [dict(r) for r in formation]
    if not roles:
        raise ConceptSCWError("a concept window needs at least one role")

    pad = {r["role"]: f"{base}-{_slug(r['role'])}-pad" for r in roles}
    handoffs: list[str] = []
    for role in roles:
        for target in role.get("exposes", ()):
            name = f"{base}-{_slug(target)}"
            if name not in handoffs:
                handoffs.append(name)

    regions = [
        {"scw_id": f"{base}-constitution", "label": f"{concept_id}: constitution",
         "region_type": "reference",
         "why": "what this concept is. Everyone reads it; nobody writes it."},
        {"scw_id": f"{base}-skills", "label": f"{concept_id}: skills",
         "region_type": "reference",
         "why": "the context-transfer operators this concept exposes"},
        {"scw_id": f"{base}-criterion", "label": f"{concept_id}: criterion",
         "region_type": "reference",
         "why": "what the work is graded against, frozen before the run"},
    ]
    regions += [
        {"scw_id": name, "label": f"{concept_id}: {name.rsplit('-', 1)[-1]}",
         "region_type": "durable",
         "why": "a declared handoff surface; the only way work crosses roles"}
        for name in handoffs
    ]
    regions += [
        {"scw_id": pad[r["role"]], "label": f"{r['role']} pad",
         "region_type": "scratchpad",
         "why": "private working space; bridgeable=false, never readable by "
                "another role however convenient"}
        for r in roles
    ]

    grants: list[dict] = []
    for role in roles:
        rid = role["role"]
        for shared in (f"{base}-constitution", f"{base}-skills"):
            grants.append({"from": pad[rid], "to": shared, "mode": "read",
                           "loop_id": rid,
                           "reason": f"{rid} reads the concept's {shared.rsplit('-', 1)[-1]}"})
        for target in role.get("exposes", ()):
            grants.append({"from": pad[rid], "to": f"{base}-{_slug(target)}",
                           "mode": "write", "loop_id": rid,
                           "reason": f"{rid} publishes its declared handoff"})
        for upstream in role.get("reads", ()):
            source = next((x for x in roles if x["role"] == upstream), None)
            if source is None:
                raise ConceptSCWError(
                    f"role {rid!r} declares reads_from {upstream!r}, which is not "
                    f"in this formation")
            for target in source.get("exposes", ()):
                grants.append({"from": pad[rid], "to": f"{base}-{_slug(target)}",
                               "mode": "read", "loop_id": rid,
                               "reason": f"{rid} reads {upstream}'s declared handoff"})

    # The judge is graded-against material, so it must reach the criterion --
    # and the maker must NOT be able to write it. The runtime enforces the
    # second half at loop_tick (R5), but the grant is only minted for roles
    # that actually judge.
    for role in roles:
        if role.get("verification_level", 0) >= 4:
            grants.append({"from": pad[role["role"]], "to": f"{base}-criterion",
                           "mode": "read", "loop_id": role["role"],
                           "reason": f"{role['role']} grades against the pinned criterion"})

    binds = [
        {"loop_id": r["role"], "scw_id": pad[r["role"]],
         "exposes": [f"{base}-{_slug(t)}" for t in r.get("exposes", ())],
         "goal": r.get("goal", ""),
         "verification_level": r.get("verification_level"),
         "criterion_id": f"{base}-criterion" if r.get("verification_level", 0) >= 4 else None}
        for r in roles
    ]

    return {
        "concept": concept_id,
        "base": base,
        "regions": regions,
        "binds": binds,
        "grants": grants,
        "criterion_region": f"{base}-criterion",
        "criterion_text": criterion_text,
        "skills": list(skills),
        "roles": [r["role"] for r in roles],
        "pads": pad,
        "handoffs": handoffs,
    }


def build(window, concept_id: str,
          formation: Sequence[dict] = DEFAULT_FORMATION,
          constitution: str = "",
          criterion_text: str = "",
          skills: Sequence[str] = (),
          max_iterations: int = 3) -> dict:
    """Build the concept window in ``window``.

    Order matters and is not cosmetic: regions before binds (a loop cannot bind
    to a region that does not exist), reference material seeded **as the host**
    before any role is bound (a bound loop cannot write a reference region, and
    that refusal is the point), and the criterion pinned before the judge binds
    to it.
    """
    spec = plan(concept_id, formation, criterion_text, skills)
    created, bound, granted, refused = [], [], [], []

    for region in spec["regions"]:
        try:
            window.create_scw(region["label"], region["region_type"],
                              scw_id=region["scw_id"])
            created.append(region["scw_id"])
        except Exception as exc:  # noqa: BLE001 - report, never half-build silently
            refused.append({"op": "create_scw", "scw_id": region["scw_id"],
                            "error": f"{type(exc).__name__}: {exc}"})

    # Host-seeded, before anyone is bound. `write` takes text, and `key` gives
    # the entry memory-block semantics so re-seeding upserts in place rather
    # than accumulating duplicates across iterations.
    if constitution:
        window.write(f"{spec['base']}-constitution", constitution,
                     key="constitution")
    if skills:
        window.write(f"{spec['base']}-skills", "\n".join(f"- {s}" for s in skills),
                     key="skills")
    if criterion_text:
        window.write(spec["criterion_region"], criterion_text, key="criterion")

    criterion_id = None
    if criterion_text:
        try:
            criterion = window.pin_criterion(spec["criterion_region"],
                                             label=f"{concept_id} acceptance")
            criterion_id = getattr(criterion, "criterion_id", None) or \
                getattr(criterion, "id", None)
        except Exception as exc:  # noqa: BLE001
            refused.append({"op": "pin_criterion", "error": f"{type(exc).__name__}: {exc}"})

    for bind in spec["binds"]:
        kwargs = {
            "loop_id": bind["loop_id"], "scw_id": bind["scw_id"],
            "max_iterations": max_iterations, "trigger": "manual",
            "goal": bind["goal"], "exposes": bind["exposes"],
        }
        if bind["verification_level"] is not None:
            kwargs["verification_level"] = bind["verification_level"]
        if bind["criterion_id"] and criterion_id:
            kwargs["criterion_id"] = criterion_id
        try:
            window.bind_scope(**kwargs)
            bound.append(bind["loop_id"])
        except Exception as exc:  # noqa: BLE001
            refused.append({"op": "bind_scope", "loop_id": bind["loop_id"],
                            "error": f"{type(exc).__name__}: {exc}"})

    for grant in spec["grants"]:
        try:
            window.open_bridge(grant["from"], grant["to"], mode=grant["mode"],
                               reason=grant["reason"], loop_id=grant["loop_id"])
            granted.append(f"{grant['from']} -{grant['mode']}-> {grant['to']}")
        except Exception as exc:  # noqa: BLE001
            # A refused grant is a result, not a failure to hide: it usually
            # means the target declared bridgeable=false, which is the pad
            # privacy invariant working.
            refused.append({"op": "open_bridge", "from": grant["from"],
                            "to": grant["to"], "mode": grant["mode"],
                            "error": f"{type(exc).__name__}: {exc}"})

    return {
        "ok": True,
        "concept": concept_id,
        "regions_created": created,
        "roles_bound": bound,
        "grants_opened": granted,
        "refused": refused,
        "criterion_id": criterion_id,
        "plan": spec,
        "next": [
            "declare_gate_policy(loop_id=<role>, read_paths=[], tools=[...]) for each role",
            "gate_mode('enforce') or leave it in observe",
            "render_window(loop_id=<role>) and dispatch with [[scw:role=<role>]] "
            "at the top of the prompt",
            "isolation_level(declared='L3_observed') afterwards to see what the "
            "evidence actually supports",
        ],
    }


def gate_policies(spec: dict, workdir_root: Optional[str] = None) -> list[dict]:
    """Suggested gate policy per role, derived from the plan.

    The default is deliberately closed: **no filesystem access at all**, and
    only the tools a role bound to a partition should need. A role in a concept
    window is supposed to work from what `render_window` gave it, so reaching
    the disk is a decision to make explicitly rather than a convenience to leave
    open.

    ``workdir_root`` sets a per-role working directory, which is the one
    attribution mechanism that works on hosts that do not report an actor id.
    """
    out = []
    for role in spec["roles"]:
        entry = {
            "loop_id": role,
            "read_paths": [],
            "write_paths": [],
            "tools": [],
            "bash_allow": [],
            "note": f"{role} in concept window {spec['concept']}: works only from "
                    f"rendered material",
        }
        if workdir_root:
            entry["workdir"] = f"{workdir_root.rstrip('/')}/{role}"
        out.append(entry)
    return out
