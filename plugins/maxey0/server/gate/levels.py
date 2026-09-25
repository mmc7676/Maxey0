"""The isolation ladder — what a run's partitioning is actually worth.

The architectural primitive is not "a second runtime". It is an **independent
state-transition boundary**, and a second runtime is one implementation of it.
Getting that distinction right matters, because a partition can be real in four
quite different senses and only the strongest of them supports the claims people
want to make:

    L0  none        no SCW. A skill is additional context and nothing separates
                    anything from anything.
    L1  logical     one runtime, distinct context objects. Maxey0 tracks and
                    constructs separate contextual states, but nothing prevents
                    the underlying runtime from carrying state between them.
                    **Logical isolation, not hard isolation.**
    L2  execution   each role runs in its own execution context, so the SCWs
                    establish genuinely separate state. This is where a
                    maker/checker/judge formation starts to mean something.
    L3  observed    L2, plus every crossing is recorded and reintegration into
                    SCW0 is controlled — SCW0 receives *specified outputs*
                    rather than becoming another shared scratchpad.

The reason to make this a first-class, recorded property rather than a design
note: **a level must be earned from evidence, never asserted.** An operator can
declare L3 and get L1 — three roles dispatched into one shared context with the
partition existing only in the prompt. Nothing in the runtime would notice, and
every containment number would still be computed and reported.

So this module does two things. It defines the ladder, and it *assesses* a run
against it: given the window and the gate's records, which level does the
recorded evidence actually support? Where the answer is lower than what was
declared, the shortfall is named. That is the difference between a system that
measures isolation and one that takes credit for it.

The correspondence to the four experiment conditions is deliberate and exact:

    Experiment A — shared context ................ L0
    Experiment B — logical SCWs .................. L1
    Experiment C — separate runtimes ............. L2
    Experiment D — controlled reintegration ...... L3

so "which level did this condition actually achieve" is the measurement, and
"at what point does logical isolation cease to be sufficient" is the question
the experiment exists to answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

#: Ordered weakest to strongest. The integer is meaningful — levels compare.
LEVELS: dict[str, int] = {
    "L0_none": 0,
    "L1_logical": 1,
    "L2_execution": 2,
    "L3_observed": 3,
}

LEVEL_NAMES: tuple[str, ...] = tuple(LEVELS)

#: What each level does and does not license a report to say. Written as claims
#: rather than descriptions, because the point of the ladder is to bound what
#: may be asserted.
GUARANTEES: dict[str, dict[str, str]] = {
    "L0_none": {
        "guarantees": "nothing; every role shares one context",
        "may_claim": "that a formation ran",
        "may_not_claim": "any form of containment, disjointness, or independence",
    },
    "L1_logical": {
        "guarantees": "distinct context objects were constructed and tracked",
        "may_claim": "that the roles were given different material",
        "may_not_claim": "that the roles could not reach each other's material — "
                         "one runtime carried all of them, so isolation here is "
                         "representational, not enforced",
    },
    "L2_execution": {
        "guarantees": "each role ran in its own execution context with its own state",
        "may_claim": "that the roles did not share working state, and that "
                     "region access was enforced for calls that went through the runtime",
        "may_not_claim": "that no information crossed by another channel unless the "
                         "gate observed those channels too",
    },
    "L3_observed": {
        "guarantees": "L2, plus every intercepted crossing is recorded, and "
                      "reintegration was measured to carry only the declared outputs",
        "may_claim": "contained, attributable, replayable — subject to the residue",
        "may_not_claim": "representational independence; enforced information "
                         "access is not proven independence of the learned "
                         "representations, and no amount of telemetry changes that",
    },
}


def rank(level: str) -> int:
    return LEVELS.get(level, -1)


def at_least(level: str, minimum: str) -> bool:
    return rank(level) >= rank(minimum)


@dataclass
class LevelAssessment:
    """What was declared, what the evidence supports, and why they differ."""

    declared: Optional[str]
    evidenced: str
    holds: bool
    reasons: list[str] = field(default_factory=list)
    shortfall: list[str] = field(default_factory=list)
    signals: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        out = {
            "declared": self.declared,
            "evidenced": self.evidenced,
            "holds": self.holds,
            "reasons": self.reasons,
            "shortfall": self.shortfall,
            "signals": self.signals,
            "guarantees": GUARANTEES.get(self.evidenced, {}),
        }
        if self.declared and not self.holds:
            out["note"] = (
                f"declared {self.declared} but the recorded evidence supports only "
                f"{self.evidenced}; report the evidenced level, not the declared one"
            )
        return out


def assess(
    loops: Iterable[dict],
    gate_records: Iterable[dict],
    declared: Optional[str] = None,
    reintegration_declared_only: Optional[bool] = None,
    damaged: int = 0,
) -> LevelAssessment:
    """Which level the recorded evidence supports.

    ``loops`` is the window's bound roles (each with ``loop_id``, ``scw_id`` and
    its read closure). ``gate_records`` is the gate journal. Both are evidence
    the run produced, not configuration it declared — which is the whole point.

    The tests, in order, each of which can only *lower* the result:

    **L1 requires distinct contexts.** Two roles bound to the same region are
    one role wearing two names, and the runtime's own disjointness proof already
    says so. If every role shares a region, the run is L0.

    **L2 requires separate execution contexts.** The evidence for that is the
    gate seeing tool calls from at least one distinct delegated actor -- an
    actor the gate observed is an execution context the runtime actually
    created. If none was observed, no separate context is evidenced and the run
    is L1 at best, whatever the prompt described.

    **L3 requires observation.** Every actor that ran must have been attributed
    to a role, and there must be no residue — a fail-open, a lost record or an
    unattributable call is a hole exactly where the evidence would go.
    """
    loops = list(loops)
    records = list(gate_records)
    reasons: list[str] = []
    shortfall: list[str] = []

    regions = [lp.get("scw_id") for lp in loops if lp.get("scw_id")]
    distinct_regions = len(set(regions))
    bound_roles = len(loops)

    # Only actors that belong to a dispatched role count as evidence of a
    # separate execution context; ambient host activity is not the formation.
    actors = {
        (r.get("payload") or {}).get("actor_ref")
        for r in records
        if (r.get("payload") or {}).get("actor_ref")
        and (r.get("payload") or {}).get("reason_code") != "ambient_actor"
    }
    attributed_roles = {
        (r.get("payload") or {}).get("loop_id")
        for r in records
        if (r.get("payload") or {}).get("loop_id")
    }
    unattributed = sum(
        1 for r in records
        if r.get("type") in ("gate.allowed", "gate.denied", "gate.observed")
        and not (r.get("payload") or {}).get("attributed")
        and (r.get("payload") or {}).get("reason_code")
        not in ("host_actor", "ambient_actor")
    )
    residue = sum(1 for r in records
                  if r.get("type") in ("gate.fail_open", "gate.error"))
    unlocked = sum(1 for r in records if r.get("seq") is None)

    signals = {
        "bound_roles": bound_roles,
        "distinct_regions": distinct_regions,
        "delegated_actors_observed": len(actors),
        "roles_attributed": sorted(x for x in attributed_roles if x),
        "unattributed_calls": unattributed,
        "gate_residue": residue,
        "unchained_records": unlocked,
        "damaged_records": damaged,
        "gate_records": len(records),
    }

    # --- L1: were there distinct contexts at all? -------------------------
    if bound_roles == 0:
        return LevelAssessment(
            declared, "L0_none", declared is None or declared == "L0_none",
            reasons=["no loop was bound; nothing partitioned anything"],
            shortfall=[] if declared in (None, "L0_none") else
            ["no bound loop exists, so no level above L0 can be evidenced"],
            signals=signals,
        )
    if distinct_regions <= 1 and bound_roles > 1:
        return LevelAssessment(
            declared, "L0_none", declared in (None, "L0_none"),
            reasons=[f"{bound_roles} roles are bound across {distinct_regions} "
                     f"region(s); the roles do not have distinct contexts"],
            shortfall=["roles must be bound to distinct regions before any "
                       "isolation claim is meaningful"],
            signals=signals,
        )
    reasons.append(f"{bound_roles} role(s) bound across {distinct_regions} distinct region(s)")
    level = "L1_logical"

    # --- L2: did the roles actually run somewhere separate? ---------------
    if len(actors) == 0:
        shortfall.append(
            "no delegated actor was observed by the gate; without one, separate "
            "execution contexts are not evidenced and isolation at this level is "
            "representational rather than enforced"
        )
        return LevelAssessment(declared, level,
                               at_least(level, declared) if declared else True,
                               reasons, shortfall, signals)

    reasons.append(f"{len(actors)} distinct delegated actor(s) observed making tool calls")
    level = "L2_execution"

    # --- L3: was every crossing observed, and was reintegration controlled? --
    if unattributed:
        shortfall.append(
            f"{unattributed} intercepted call(s) could not be attributed to a bound "
            f"role; those establish nothing about any role's containment"
        )
    if residue:
        shortfall.append(
            f"{residue} call(s) the gate could not evaluate were allowed through "
            f"(fail-open); a containment figure over this run is incomplete"
        )
    if unlocked:
        shortfall.append(
            f"{unlocked} record(s) hold no place in the hash chain and cannot be "
            f"replayed as evidence"
        )
    if damaged:
        shortfall.append(
            f"{damaged} record(s) were lost to unparseable lines; those crossings "
            f"were observed and then not kept"
        )
    if reintegration_declared_only is None:
        # Unmeasured is not a pass. L3 asserts that reintegration carried only
        # the declared outputs; awarding it to a run where that was never
        # checked would state as fact the one thing nobody looked at.
        shortfall.append(
            "reintegration was not measured; whether only declared outputs "
            "crossed back is unevidenced"
        )
    if reintegration_declared_only is False:
        shortfall.append(
            "reintegration carried material beyond the declared outputs; SCW0 became "
            "another shared scratchpad, which is multi-agent prompting rather than "
            "context-partitioned computation"
        )

    if not shortfall:
        level = "L3_observed"
        reasons.append("every intercepted call in the records supplied was attributed "
                       "and evaluated, with no residue")

    holds = True if declared is None else at_least(level, declared)
    return LevelAssessment(declared, level, holds, reasons, shortfall, signals)


def describe(level: str) -> dict:
    """The ladder entry for one level, for a report or a UI."""
    return {"level": level, "rank": rank(level), **GUARANTEES.get(level, {})}


def ladder() -> list[dict]:
    return [describe(name) for name in LEVEL_NAMES]
