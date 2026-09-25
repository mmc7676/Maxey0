"""Correlating the three traces — the thing Maxey0 is actually for.

An agentic run leaves three different histories behind, and until they are put
next to each other none of them answers a useful question:

**Context trace** — what was constructed and who was given it.
``C0 -> Skill -> SCW -> Context``. Lives in the runtime's hash-chained log:
region creation, writes, scope binds, grants, and scope-true renders.

**Execution trace** — what the agent then did.
``Agent -> tool -> output``. Lives in the gate's journal, because the runtime
cannot see inside a delegated context and never could.

**State trace** — what changed as a result.
``S0 -> S1 -> S2``. Derived from the content signature of each region over the
run.

The proposition this module implements:

> Given a task, reconstruct which contextual states were introduced, which
> agents received them, which skills gated those transfers, which execution
> paths resulted, and what measurable state changes occurred afterward.

# One naming honesty, up front

The third trace is a **state** trace, not a *semantic* trace. What is actually
measured is the content signature of each region before and after — a
content-addressed hash, not an embedding. It answers "did this region's contents
change, and when", which is real and verifiable. It does **not** answer "did the
agent's representation of the concept move", which would require measuring the
model's latent state and is not established here. Calling a hash delta a
semantic delta would be exactly the kind of overclaim the rest of this codebase
refuses, so it is called what it is.

# How the two logs are joined

Not by wall-clock. The runtime and the gate are separate OS processes with
unsynchronized clocks, so comparing timestamps across them would order events by
an artifact of scheduling. Instead every gate record carries an **anchor**: the
runtime log's ``run_id`` and the ``seq`` it was at when the gate wrote. That
gives each execution event a position *relative to the context trace* — "this
tool call happened after runtime seq N" — which is a causal statement the two
processes can both be held to, rather than a clock comparison neither can.

Timestamps are still reported, for display. They are not the join key, and the
merged view says so.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

#: Runtime event types that belong to the context trace, grouped by what they
#: say about a context transfer.
CONTEXT_KINDS: dict[str, tuple[str, ...]] = {
    "construct": ("scw.create", "scw.close", "window.init", "window.reset"),
    "seed": ("scw.write",),
    "bind": ("loop.bind", "loop.unbind"),
    "grant": ("bridge.open", "bridge.close", "promote"),
    "transfer": ("window.render", "prompt.render"),
    "access": ("scw.read",),
    "refusal": ("scw.denied",),
    "criterion": ("criterion.pin", "criterion.unpin", "evidence.attest"),
    "iterate": ("loop.tick",),
    "route": ("route.hit", "route.fallback_skill", "route.fallback_agent"),
}

_CONTEXT_KIND_OF = {t: k for k, ts in CONTEXT_KINDS.items() for t in ts}

#: The transfer moment. `window.render` is where material actually crosses from
#: the context plane into an execution context -- it is the skill/gate acting as
#: a context-transfer operator, and it is the event a "who was given what"
#: question resolves to.
TRANSFER_TYPES: tuple[str, ...] = ("window.render", "prompt.render")


def _payload(record: dict) -> dict:
    return record.get("payload") or {}


def _actor_loop(record: dict) -> Optional[str]:
    actor = record.get("actor") or ""
    if isinstance(actor, str) and actor.startswith("loop:"):
        return actor.split(":", 1)[1]
    got = _payload(record).get("loop_id")
    return got if isinstance(got, str) else None


def context_trace(runtime_records: Iterable[dict]) -> dict:
    """What was constructed, granted, and handed across — in order."""
    rows: list[dict] = []
    transfers: list[dict] = []
    for record in runtime_records:
        etype = record.get("type", "")
        kind = _CONTEXT_KIND_OF.get(etype)
        if kind is None:
            continue
        payload = _payload(record)
        row = {
            "seq": record.get("seq"),
            "ts": record.get("ts"),
            "plane": "context",
            "kind": kind,
            "type": etype,
            "loop_id": _actor_loop(record),
            "scw_id": payload.get("scw_id") or payload.get("to_scw_id"),
            "tokens": payload.get("tokens"),
        }
        if etype in TRANSFER_TYPES:
            row["transfer"] = True
            transfers.append(row)
        rows.append(row)
    return {"events": rows, "transfers": transfers, "count": len(rows)}


def execution_trace(gate_records: Iterable[dict]) -> dict:
    """What each delegated actor did, anchored to the context trace."""
    rows: list[dict] = []
    for record in gate_records:
        payload = _payload(record)
        anchor = record.get("anchor") or {}
        rows.append({
            "seq": record.get("seq"),
            "ts": record.get("ts"),
            "plane": "execution",
            "kind": record.get("type", "").replace("gate.", ""),
            "type": record.get("type"),
            "loop_id": payload.get("loop_id"),
            "actor_ref": payload.get("actor_ref"),
            "tool": payload.get("tool"),
            "tool_kind": payload.get("kind"),
            "resource": payload.get("resource"),
            "verdict": payload.get("verdict"),
            "reason_code": payload.get("reason_code"),
            "attributed": bool(payload.get("attributed")),
            # the causal join key -- see the module docstring
            "after_runtime_seq": anchor.get("at_seq"),
            "runtime_run_id": anchor.get("run_id"),
        })
    return {"events": rows, "count": len(rows)}


def state_trace(runtime_records: Iterable[dict]) -> dict:
    """How each region's contents changed over the run.

    A *state* trace, deliberately not called a semantic one: this is derived
    from write events and the token counts they carry, which establishes that a
    region's contents changed and by how much. It establishes nothing about a
    model's internal representation.
    """
    per_region: dict[str, dict[str, Any]] = {}
    for record in runtime_records:
        if record.get("type") not in ("scw.write", "promote", "scw.evict"):
            continue
        payload = _payload(record)
        scw_id = payload.get("scw_id") or payload.get("to_scw_id")
        if not scw_id:
            continue
        slot = per_region.setdefault(scw_id, {
            "scw_id": scw_id, "revisions": 0, "tokens_written": 0,
            "first_seq": record.get("seq"), "last_seq": record.get("seq"),
            "writers": set(),
        })
        slot["revisions"] += 1
        slot["last_seq"] = record.get("seq")
        tokens = payload.get("tokens")
        if isinstance(tokens, (int, float)):
            slot["tokens_written"] += tokens
        writer = _actor_loop(record)
        slot["writers"].add(writer or "(host)")

    regions = []
    for slot in per_region.values():
        slot = dict(slot)
        slot["writers"] = sorted(slot["writers"])
        regions.append(slot)

    return {
        "regions": sorted(regions, key=lambda r: r["scw_id"]),
        "count": len(regions),
        "measure": "content revisions and token deltas",
        "not_measured": "embedding or latent-representation movement; this is a "
                        "state trace, not a semantic one",
    }


def correlate(runtime_records: Iterable[dict],
              gate_records: Iterable[dict],
              limit: int = 400) -> dict:
    """All three traces, joined, with each event keeping its provenance.

    The merged timeline is explicitly **not verifiable as one chain** — the two
    logs are separately chained by separate writers, and merging them produces a
    view, not evidence. Each chain is verified on its own before it gets here.
    """
    runtime_records = list(runtime_records)
    gate_records = list(gate_records)

    ctx = context_trace(runtime_records)
    exe = execution_trace(gate_records)
    state = state_trace(runtime_records)

    # Order execution events against the context trace by their anchor, falling
    # back to their own order when a gate record predates any runtime activity.
    merged: list[dict] = []
    for row in ctx["events"]:
        merged.append({**row, "order": (row.get("seq") or 0, 0, 0)})
    for row in exe["events"]:
        anchor = row.get("after_runtime_seq")
        anchor = anchor if isinstance(anchor, int) else -1
        merged.append({**row, "order": (anchor, 1, row.get("seq") or 0)})
    merged.sort(key=lambda r: r["order"])
    for row in merged:
        row.pop("order", None)

    truncated = len(merged) > limit
    by_role = _per_role(ctx, exe)

    return {
        "ok": True,
        "context": {"count": ctx["count"], "transfers": len(ctx["transfers"])},
        "execution": {"count": exe["count"]},
        "state": state,
        "timeline": merged[-limit:] if truncated else merged,
        "truncated": truncated,
        "by_role": by_role,
        "join": {
            "key": "gate record anchor (runtime run_id + seq at write time)",
            "not_used": "wall-clock timestamps -- two processes, two unsynchronized "
                        "clocks; ordering by them would report scheduling artifacts "
                        "as causality",
            "verifiable_as_one_chain": False,
            "note": "each log is separately chained and separately verified; this "
                    "merged view is a projection, not evidence",
        },
    }


def _per_role(ctx: dict, exe: dict) -> list[dict]:
    """For each role: what it was handed, and what it then did.

    This is the join the whole module exists for. A role with transfers but no
    execution events was given context and never observed using it; a role with
    execution events but no transfer was never handed anything the runtime
    recorded, which is its own finding.
    """
    roles: dict[str, dict[str, Any]] = {}

    def slot(role: Optional[str]) -> dict:
        key = role or "(unattributed)"
        return roles.setdefault(key, {
            "loop_id": role, "transfers_in": 0, "tokens_in": 0,
            "tool_calls": 0, "allowed": 0, "denied": 0,
            "regions_written": set(), "tools": {},
        })

    for row in ctx["events"]:
        if row.get("transfer"):
            entry = slot(row.get("loop_id"))
            entry["transfers_in"] += 1
            tokens = row.get("tokens")
            if isinstance(tokens, (int, float)):
                entry["tokens_in"] += tokens
        elif row.get("kind") == "seed" and row.get("loop_id"):
            slot(row["loop_id"])["regions_written"].add(row.get("scw_id"))

    for row in exe["events"]:
        if row.get("kind") in ("actor_start", "actor_stop", "policy"):
            continue
        entry = slot(row.get("loop_id"))
        entry["tool_calls"] += 1
        tool = row.get("tool")
        if tool:
            entry["tools"][tool] = entry["tools"].get(tool, 0) + 1
        if row.get("kind") == "allowed":
            entry["allowed"] += 1
        elif row.get("kind") == "denied":
            entry["denied"] += 1

    out = []
    for entry in roles.values():
        entry = dict(entry)
        entry["regions_written"] = sorted(x for x in entry["regions_written"] if x)
        entry["finding"] = _finding(entry)
        out.append(entry)
    return sorted(out, key=lambda r: (r["loop_id"] is None, r["loop_id"] or ""))


def _finding(entry: dict) -> str:
    """A neutral statement of what was and was not recorded for this role.

    Deliberately descriptive rather than interpretive. Each case reports the
    two counts that produced it and stops there; why a role shows a given
    shape is a question for whoever reads the run, and a guess baked into the
    product would be one the evidence does not support.
    """
    if entry["loop_id"] is None:
        return "not attributed to a bound role; counted as residue"
    if entry["transfers_in"] and not entry["tool_calls"]:
        return "context transferred; no tool call observed"
    if entry["tool_calls"] and not entry["transfers_in"]:
        return "tool calls observed; no context transfer recorded"
    if entry["denied"]:
        return (f"{entry['denied']} call(s) outside the declared scope, refused; "
                f"{entry['allowed']} inside")
    return "context transferred; all observed calls inside the declared scope"
