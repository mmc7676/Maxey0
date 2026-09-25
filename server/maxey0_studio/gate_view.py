"""A typed projection of the gate stream — what the agents actually did.

`observability.py` projects the *runtime's* log: what the host orchestrator did
to the window. This module projects the *gate's* log: what each delegated actor
tried to do while it was running, and what happened to the attempt.

The two are deliberately separate files, separately chained, and separately
verified. They are never merged into one chain, because a chain over records
from two processes cannot verify — that was measured, not assumed, and it is
documented in `server/gate/journal.py`. What this module does instead is
present them side by side with each record's provenance intact, and mark the
combined view as unverifiable-by-construction so nobody mistakes it for one
chain.

# The three residues

A containment claim over this stream is weakened by three distinct absences,
and each is reported separately rather than folded into a rate:

``unattributed``   a role WAS dispatched and the gate could not tie this call
                   to it
``fail_open``      the gate could not evaluate the call and allowed it
``damaged``        a torn line; the record is simply gone

None of them is zero by default and none is counted as containment. A run with
residue has not established containment for the calls in it, and
:func:`containment` says so in words rather than leaving it to be inferred from
a denominator.

# What is NOT residue

``host``      the orchestrator's own calls. It builds the partition; no role
              policy was ever meant to govern it.
``ambient``   a delegated actor in a session where no SCW role was dispatched
              at all. Ordinary host activity, not a partitioned role — there is
              no containment claim for it to weaken.

Both were once counted as ``unattributed``, which meant any session that used a
subagent for unrelated work reported its containment as permanently
un-claimable. That is the opposite of informative: it made the residue signal
fire constantly and mean nothing.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

#: Gate event types grouped into the kinds a reader reasons in. Mirrors the
#: shape of `observability.KINDS` on purpose: a consumer that already knows how
#: to read one stream should not need a second vocabulary for the other.
KINDS: dict[str, tuple[str, ...]] = {
    "attempt":  ("gate.attempt",),
    "allowed":  ("gate.allowed",),
    "refusal":  ("gate.denied",),
    "observed": ("gate.observed",),
    "residue":  ("gate.fail_open", "gate.error"),
    "lifecycle": ("gate.actor_start", "gate.actor_stop"),
    "policy":   ("gate.policy",),
}

#: Reason codes that mean the call reached outside the role's declared scope.
#: Whether such a call was refused or allowed is what decides `held`.
OUT_OF_SCOPE_REASONS: frozenset[str] = frozenset({
    "path_outside_scope", "tool_not_granted",
    "command_not_granted", "region_outside_closure",
})

_KIND_OF: dict[str, str] = {
    event_type: kind for kind, types in KINDS.items() for event_type in types
}


def classify(event_type: str) -> str:
    """Which kind a gate event belongs to. Unmapped types are `other`.

    Unmapped is *returned*, never dropped — the same rule the runtime's
    projection follows, so a gate that grows a new event type stays visible
    before this map is updated.
    """
    return _KIND_OF.get(event_type, "other")


def _view(record: dict) -> dict:
    """One gate record, flattened to the fields a consumer reads."""
    payload = record.get("payload") or {}
    out = {
        "seq": record.get("seq"),
        "ts": record.get("ts"),
        "kind": classify(record.get("type", "")),
        "type": record.get("type"),
        "actor": record.get("actor"),
        "loop_id": payload.get("loop_id"),
        "attributed": bool(payload.get("attributed")),
        "attribution": payload.get("attribution"),
        "tool": payload.get("tool"),
        "tool_kind": payload.get("kind"),
        "resource": payload.get("resource"),
        "verdict": payload.get("verdict"),
        "reason_code": payload.get("reason_code"),
        "message": payload.get("message"),
        "hint": payload.get("hint"),
        "mode": payload.get("mode"),
        "actor_ref": payload.get("actor_ref"),
        "actor_kind": payload.get("actor_kind"),
        "call_ref": payload.get("call_ref"),
        "phase": payload.get("phase"),
        "writer": record.get("stream"),
        "locked": record.get("locked"),
    }
    if out["type"] == "gate.denied":
        out["allowed"] = False
    elif out["type"] == "gate.allowed":
        out["allowed"] = True
    return out


def project(
    records: Iterable[dict],
    kinds: Optional[Iterable[str]] = None,
    loop_id: Optional[str] = None,
    tool: Optional[str] = None,
    since_seq: int = 0,
    limit: int = 200,
) -> dict:
    """Filter and flatten the gate stream."""
    wanted = set(kinds) if kinds else None
    if wanted:
        unknown = sorted(wanted - set(KINDS) - {"other"})
        if unknown:
            return {"ok": False, "error": "unknown_kind", "unknown": unknown,
                    "known": sorted(KINDS)}

    rows: list[dict] = []
    scanned = 0
    for record in records:
        # A record written without the append lock carries seq=None on purpose
        # (see journal.emit). Coercing that to 0 filtered exactly the residue
        # the journal goes out of its way to preserve out of every incremental
        # view, so an unlocked write vanished from any tailing consumer.
        seq = record.get("seq")
        if seq is not None and seq < since_seq:
            continue
        scanned += 1
        view = _view(record)
        if wanted and view["kind"] not in wanted:
            continue
        if loop_id is not None and view["loop_id"] != loop_id:
            continue
        if tool is not None and view["tool"] != tool:
            continue
        rows.append(view)

    truncated = len(rows) > limit
    return {
        "ok": True,
        "events": rows[-limit:] if truncated else rows,
        "returned": min(len(rows), limit),
        "matched": len(rows),
        "scanned": scanned,
        "truncated": truncated,
        "filters": {"kinds": sorted(wanted) if wanted else None, "loop_id": loop_id,
                    "tool": tool, "since_seq": since_seq, "limit": limit},
    }


def by_role(records: Iterable[dict]) -> dict:
    """Per-role activity: what each bound role reached for, and what happened.

    This is the view the whole version exists to make possible. Before the gate
    there was nothing to put in it: the runtime's log recorded the host binding
    a partition and never recorded the agent doing anything inside it.
    """
    roles: dict[str, dict[str, Any]] = {}
    unattributed = 0
    for record in records:
        view = _view(record)
        if view["kind"] in ("lifecycle", "policy"):
            continue
        key = view["loop_id"]
        if key is None:
            # The unbound host is not an unattributed role -- it is the
            # orchestrator, which no policy governs and which was never
            # supposed to be attributed to anything. Keeping them apart
            # matters: one is residue that weakens a claim, the other is the
            # thing that built the partition.
            if view["reason_code"] == "host_actor":
                key = "(host)"
            elif view["reason_code"] == "ambient_actor":
                # An agent that was never dispatched as an SCW role. Shown, but
                # not counted against any containment claim -- there is none.
                key = "(ambient)"
            else:
                unattributed += 1
                key = "(unattributed)"
        slot = roles.setdefault(key, {
            "loop_id": None if key in ("(unattributed)", "(host)", "(ambient)") else key,
            "actor": key if key in ("(unattributed)", "(host)", "(ambient)") else None,
            "attempts": 0, "allowed": 0, "denied": 0, "observed": 0, "residue": 0,
            "tools": {}, "denied_examples": [], "attribution": {},
        })
        slot["attempts"] += 1
        if view["tool"]:
            slot["tools"][view["tool"]] = slot["tools"].get(view["tool"], 0) + 1
        # The host was never a candidate for attribution, so labeling its rows
        # "unattributed" reads as a failure to identify something that was
        # never in question.
        how = ({"(host)": "host", "(ambient)": "ambient"}.get(key)
               or view["attribution"])
        if how:
            slot["attribution"][how] = slot["attribution"].get(how, 0) + 1
        kind = view["kind"]
        if kind == "allowed":
            slot["allowed"] += 1
        elif kind == "refusal":
            slot["denied"] += 1
            if len(slot["denied_examples"]) < 5:
                slot["denied_examples"].append({
                    "tool": view["tool"], "resource": view["resource"],
                    "reason_code": view["reason_code"], "message": view["message"],
                    "hint": view["hint"],
                })
        elif kind == "residue":
            slot["residue"] += 1
        else:
            slot["observed"] += 1

    return {
        "ok": True,
        "roles": [roles[k] for k in sorted(roles)],
        "unattributed_calls": unattributed,
        "note": ("some calls could not be attributed to a bound role; they establish "
                 "nothing about any role's containment"
                 if unattributed else ""),
    }


def containment(records: Iterable[dict], damaged: int = 0) -> dict:
    """Did the gate hold, and what is the claim actually worth?

    ``held`` is three-valued for the same reason the runtime's ``contained``
    is: True and False mean every evaluated out-of-scope attempt was refused or
    some was not, and **None means nothing was evaluated**, which establishes
    nothing either way.

    ``claimable`` is the field a report should lead with. It is False whenever
    any residue exists, because a run that failed open, lost a record, or could
    not attribute a call has a hole in exactly the place a containment claim
    would go.
    """
    materialized = list(records)
    allowed = denied = observed = fail_open = errors = 0
    unattributed = violations = ambient = 0
    modes: dict[str, int] = {}

    for record in materialized:
        view = _view(record)
        kind = view["kind"]
        if kind in ("lifecycle", "policy"):
            continue
        if view["mode"]:
            modes[view["mode"]] = modes.get(view["mode"], 0) + 1
        # The unbound host's own calls are not residue. The orchestrator builds
        # the partition; it was never a bound role and no policy was ever meant
        # to govern it. Counting those made every clean run report
        # `claimable: false`, because a real run always contains the host's own
        # dispatch and tooling calls. `gate.levels.assess` excludes them for the
        # same reason, and the two must not disagree about what residue is.
        if (not view["attributed"]
                and view["type"] not in ("gate.attempt",)
                and view["reason_code"] not in ("host_actor", "ambient_actor")):
            unattributed += 1
        if view["reason_code"] == "ambient_actor":
            ambient += 1
        if kind == "allowed":
            allowed += 1
            # An out-of-scope call that was ALLOWED is the containment failure.
            # It happens in `observe` (which finds violations and permits them)
            # and would happen in `enforce` only if the boundary leaked. Without
            # counting these, `held` was a tautology: it was computed as
            # `denied > 0 or allowed == evaluated`, and since evaluated is
            # allowed + denied, one of those is always true. `held` could never
            # be False, so the gate could never report that containment failed.
            if view["reason_code"] in OUT_OF_SCOPE_REASONS:
                violations += 1
        elif kind == "refusal":
            denied += 1
        elif kind == "residue":
            if view["type"] == "gate.fail_open":
                fail_open += 1
            else:
                errors += 1
        else:
            observed += 1
            # `observe` mode is the shipped default: the Gate finds out-of-scope
            # calls and permits every one of them, recording `gate.observed`
            # rather than `gate.allowed`. Counting violations only in the
            # `allowed` branch therefore reported `violations: 0, held: true`
            # for exactly the runs where containment did not hold. A violation
            # is an out-of-scope call that was not blocked, whichever record
            # kind the mode happens to write.
            if view["reason_code"] in OUT_OF_SCOPE_REASONS:
                violations += 1

    evaluated = allowed + denied
    residue = fail_open + errors + unattributed + damaged

    if evaluated == 0:
        held: Optional[bool] = None
        note = ("no call was evaluated against a declared policy; that is an absence "
                "of evidence, not evidence of containment")
    else:
        # True  : every out-of-scope call the gate evaluated was refused
        # False : at least one was allowed through -- a containment failure,
        #         which is the normal and expected result under `observe`
        held = violations == 0
        note = ("" if held else
                f"{violations} out-of-scope call(s) were allowed through; under "
                f"`observe` that is the measurement working, under `enforce` it "
                f"is a containment failure")

    return {
        "ok": True,
        "held": held,
        "claimable": bool(evaluated) and residue == 0,
        "evaluated": evaluated,
        "violations": violations,
        "ambient_calls": ambient,
        "allowed": allowed,
        "denied": denied,
        "observed_only": observed,
        "modes": modes,
        "residue": {
            "total": residue,
            "fail_open": fail_open,
            "gate_errors": errors,
            "unattributed": unattributed,
            "damaged_records": damaged,
        },
        "note": note or (
            "residue is present: this run has calls the gate did not evaluate, could "
            "not attribute, or lost. A containment figure computed over it is "
            "incomplete and must be reported with the residue attached."
            if residue else
            "every intercepted call was attributed and evaluated"
        ),
    }


def summary(records: Iterable[dict], damaged: int = 0) -> dict:
    """Counts per kind and per type, plus the containment verdict."""
    materialized = list(records)
    by_kind: dict[str, int] = {}
    by_type: dict[str, int] = {}
    by_tool: dict[str, int] = {}
    for record in materialized:
        event_type = record.get("type", "")
        kind = classify(event_type)
        by_kind[kind] = by_kind.get(kind, 0) + 1
        by_type[event_type] = by_type.get(event_type, 0) + 1
        tool = (record.get("payload") or {}).get("tool")
        if tool:
            by_tool[tool] = by_tool.get(tool, 0) + 1

    return {
        "ok": True,
        "events": len(materialized),
        "by_kind": dict(sorted(by_kind.items())),
        "by_type": dict(sorted(by_type.items())),
        "by_tool": dict(sorted(by_tool.items(), key=lambda kv: -kv[1])),
        "kinds": sorted(KINDS),
        "containment": containment(materialized, damaged=damaged),
    }
