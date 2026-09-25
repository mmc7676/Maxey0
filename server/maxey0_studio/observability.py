"""A typed projection of the SCW event log.

The log already records everything a containment question needs. What it does
not do is answer questions in the shape people ask them. This module is that
shape: it groups raw event types into a handful of named kinds, and answers
the one question an external experiment actually has —

    did role X attempt to reach region Y, and what happened?

— from recorded runtime events, without injecting a probe into the run. That
matters because a probe measures what a model *says* about its access; these
events record what the runtime *did* about it. Those are different claims, and
only the second one survives the model changing its mind.

Everything here is a pure read over records. Nothing mutates the window, and
nothing writes to the log — asking a question must not alter the evidence.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

#: Raw event types grouped into the kinds a consumer reasons in. A type in no
#: group is still returned by `project()`; it is classified as "other" rather
#: than dropped, so a runtime that grows a new event type stays observable
#: before this map is updated.
KINDS: dict[str, tuple[str, ...]] = {
    "access":      ("scw.read", "scw.write", "window.render", "prompt.render"),
    "refusal":     ("scw.denied",),
    "scope":       ("loop.bind", "loop.unbind", "window.seal", "window.init",
                    "window.reset", "scw.create", "scw.close", "scw.purge"),
    "bridge":      ("bridge.open", "bridge.close", "promote"),
    "utilization": ("loop.tick", "scw.evict"),
    "audit":       ("criterion.pin", "criterion.unpin", "evidence.attest",
                    "partition.check"),
    "routing":     ("route.hit", "route.fallback_skill", "route.fallback_agent"),
}

_KIND_OF: dict[str, str] = {
    event_type: kind for kind, types in KINDS.items() for event_type in types
}


def classify(event_type: str) -> str:
    """Which kind an event type belongs to. Unmapped types are `other`."""
    return _KIND_OF.get(event_type, "other")


def actor_loop(record: dict) -> Optional[str]:
    """The loop a record is attributed to, or None for the unbound host.

    Reads the actor string first and falls back to the payload, because a
    refusal names the loop that was refused in `payload.loop_id` even when the
    scope could not be resolved to an actor.
    """
    actor = record.get("actor") or ""
    if isinstance(actor, str) and actor.startswith("loop:"):
        return actor.split(":", 1)[1]
    payload = record.get("payload") or {}
    got = payload.get("loop_id")
    return got if isinstance(got, str) else None


def region_of(record: dict) -> Optional[str]:
    """The region a record concerns, if it concerns exactly one."""
    payload = record.get("payload") or {}
    for key in ("scw_id", "to_scw_id", "region", "target"):
        got = payload.get(key)
        if isinstance(got, str):
            return got
    return None


def _view(record: dict) -> dict:
    """One record, flattened to the fields a consumer reads."""
    payload = record.get("payload") or {}
    out = {
        "seq": record.get("seq"),
        "ts": record.get("ts"),
        "kind": classify(record.get("type", "")),
        "type": record.get("type"),
        "actor": record.get("actor"),
        "loop_id": actor_loop(record),
        "scw_id": region_of(record),
    }
    if record.get("type") == "scw.denied":
        out.update({
            "op": payload.get("op"),
            "reason": payload.get("reason"),
            "hint": payload.get("hint"),
            "allowed": False,
        })
    elif out["kind"] == "access":
        out["allowed"] = True
    return out


def project(
    records: Iterable[dict],
    kinds: Optional[Iterable[str]] = None,
    loop_id: Optional[str] = None,
    scw_id: Optional[str] = None,
    since_seq: int = 0,
    limit: int = 200,
) -> dict:
    """Filter and flatten the stream.

    `kinds` names groups (`access`, `refusal`, …), not raw event types, so a
    caller does not have to know the runtime's type vocabulary to ask a
    question about it.
    """
    wanted = set(kinds) if kinds else None
    if wanted:
        unknown = sorted(wanted - set(KINDS) - {"other"})
        if unknown:
            return {"ok": False, "error": "unknown_kind", "unknown": unknown,
                    "known": sorted(KINDS)}

    rows: list[dict] = []
    scanned = 0
    for record in records:
        if (record.get("seq") or 0) < since_seq:
            continue
        scanned += 1
        view = _view(record)
        if wanted and view["kind"] not in wanted:
            continue
        if loop_id is not None and view["loop_id"] != loop_id:
            continue
        if scw_id is not None and view["scw_id"] != scw_id:
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
        "filters": {"kinds": sorted(wanted) if wanted else None,
                    "loop_id": loop_id, "scw_id": scw_id,
                    "since_seq": since_seq, "limit": limit},
    }


def attempts(records: Iterable[dict], loop_id: Optional[str] = None,
             scw_id: Optional[str] = None) -> dict:
    """Every attempt to reach a region, and what the runtime did about it.

    This is the containment question asked from the log rather than from the
    agent. `allowed` are accesses the runtime performed; `denied` are the ones
    it refused, each carrying the reason and the hint it gave.

    `contained` is deliberately three-valued. True/False mean the runtime
    allowed or refused every attempt; **None means no attempt was recorded at
    all**, which is not the same as containment holding — nothing was tried, so
    nothing was established. Reporting that as `True` would manufacture
    evidence out of an absence.
    """
    allowed: list[dict] = []
    denied: list[dict] = []
    for record in records:
        view = _view(record)
        if view["kind"] not in ("access", "refusal"):
            continue
        if loop_id is not None and view["loop_id"] != loop_id:
            continue
        if scw_id is not None and view["scw_id"] != scw_id:
            continue
        (denied if view["kind"] == "refusal" else allowed).append(view)

    total = len(allowed) + len(denied)
    return {
        "ok": True,
        "query": {"loop_id": loop_id, "scw_id": scw_id},
        "attempts": total,
        "allowed": allowed,
        "denied": denied,
        "allowed_count": len(allowed),
        "denied_count": len(denied),
        "contained": None if total == 0 else (len(allowed) == 0),
        "note": ("no access attempt was recorded for this query; that is an "
                 "absence of evidence, not evidence of containment"
                 if total == 0 else ""),
    }


def summary(records: Iterable[dict]) -> dict:
    """Counts per kind and per event type, plus who was refused what."""
    materialized = list(records)
    by_kind: dict[str, int] = {}
    by_type: dict[str, int] = {}
    refusals_by_loop: dict[str, int] = {}
    regions_refused: dict[str, int] = {}

    for record in materialized:
        event_type = record.get("type", "")
        kind = classify(event_type)
        by_kind[kind] = by_kind.get(kind, 0) + 1
        by_type[event_type] = by_type.get(event_type, 0) + 1
        if event_type == "scw.denied":
            who = actor_loop(record) or "(host)"
            refusals_by_loop[who] = refusals_by_loop.get(who, 0) + 1
            where = region_of(record)
            if where:
                regions_refused[where] = regions_refused.get(where, 0) + 1

    return {
        "ok": True,
        "events": len(materialized),
        "by_kind": dict(sorted(by_kind.items())),
        "by_type": dict(sorted(by_type.items())),
        "refusals_by_loop": dict(sorted(refusals_by_loop.items(),
                                        key=lambda kv: -kv[1])),
        "regions_refused": dict(sorted(regions_refused.items(),
                                       key=lambda kv: -kv[1])),
        "kinds": sorted(KINDS),
    }
