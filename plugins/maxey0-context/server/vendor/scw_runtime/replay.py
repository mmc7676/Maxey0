"""Rebuild a window from its event log.

The event stream is meant to be a *complete* description of the runtime, not a
commentary on it. This module proves that: it reconstructs a
:class:`~scw_runtime.window.ContextWindow` from nothing but records, and
``tests/test_replay.py`` asserts the reconstruction is identical to the live
object that produced them.

That property is what makes the inspector UI trustworthy. The UI runs the same
reduction in JavaScript; if the log were lossy, the UI would be guessing.

Redacted logs (``log_content=False``) replay structure, sizes, policies, and
every access decision faithfully — only the region text is absent.
"""

from __future__ import annotations

import os
import re
from typing import Optional, Sequence

from .attest import Attestation, Criterion
from .cache import Snapshot
from .errors import SCWError
from .events import EventLog, iter_records, verify_records
from .harness import HarnessProfile, Skill
from .isolation import descendants
from .partition import record_exposure_ceiling
from .model import Bridge, Entry, Loop, Policy, Region
from .prompt import PromptRevision, PromptSpec
from .window import ContextWindow

_ENTRY_ID = re.compile(r"^e(\d+)$")
_BRIDGE_ID = re.compile(r"^br(\d+)$")
_CRITERION_ID = re.compile(r"^criterion-(\d+)$")
_EVIDENCE_ID = re.compile(r"^ev(\d+)$")


def split_runs(records: Sequence[dict]) -> "list[list[dict]]":
    """Partition a log into its constituent runs, in file order.

    A log file may hold several runs — ``reset_window`` appends a new one, and
    the default event-log path is a single file. Each run restarts the hash
    chain at genesis with ``seq`` 0.
    """
    runs: list[list[dict]] = []
    current_run: Optional[str] = None
    for record in records:
        run_id = record.get("run_id")
        if run_id != current_run or not runs:
            runs.append([])
            current_run = run_id
        runs[-1].append(record)
    return runs


def replay(
    records: Sequence[dict], verify: bool = True, run_id: Optional[str] = None
) -> ContextWindow:
    """Fold an event sequence into a window.

    Parameters
    ----------
    records:
        Event records in emission order. May contain several runs; by default
        the **last** run is replayed, because that is the current state of the
        file. Folding several runs into one window used to produce duplicated
        roots, double-counted tokens, and a log sequence desynchronized from
        the records — all while ``verify_records`` passed, since each run's
        chain is individually valid.
    verify:
        Validate the hash chain before folding. Leave this on unless you are
        deliberately inspecting a damaged log.
    run_id:
        Replay this specific run instead of the last one.
    """
    records = list(records)
    if verify:
        verify_records(records)
    if not records:
        raise SCWError("empty event log")

    runs = split_runs(records)
    if run_id is not None:
        selected = [r for r in runs if r and r[0].get("run_id") == run_id]
        if not selected:
            raise SCWError(
                f"no run {run_id!r} in this log; found "
                f"{[r[0].get('run_id') for r in runs if r]}"
            )
        records = selected[-1]
    else:
        records = runs[-1]

    head = records[0]
    if head["type"] != "window.init":
        raise SCWError(f"log must start with window.init, found {head['type']!r}")
    init = head["payload"]

    window = ContextWindow(
        total_budget=init.get("total_budget"),
        event_log=EventLog(run_id=head.get("run_id")),
        strict_scope=bool(init.get("strict_scope", False)),
        log_content=bool(init.get("log_content", True)),
        name=init.get("name", "window"),
        emit_init=False,
        host_only_bridges=bool(init.get("host_only_bridges", False)),
        require_bounded_loops=bool(init.get("require_bounded_loops", False)),
        max_total_iterations=init.get("max_total_iterations"),
        max_loop_depth=init.get("max_loop_depth"),
    )

    max_entry = 0
    max_bridge = 0
    max_criterion = 0
    max_evidence = 0

    for record in records[1:]:
        seq = record["seq"]
        kind = record["type"]
        payload = record["payload"]

        if kind == "scw.create":
            region = Region(
                scw_id=payload["scw_id"],
                label=payload["label"],
                region_type=payload["region_type"],
                policy=Policy.from_dict(payload["policy"]),
                order=payload["order"],
                created_seq=seq,
                parent_id=payload.get("parent_id"),
            )
            window.regions[region.scw_id] = region
            if region.parent_id is None:
                window.roots.append(region.scw_id)
            else:
                parent = window.regions[region.parent_id]
                parent.children.append(region.scw_id)
                parent.revision += 1
                parent.last_mutation_seq = seq

        elif kind == "scw.write":
            region = window.regions[payload["scw_id"]]
            number = _ENTRY_ID.match(payload["entry_id"])
            if number:
                max_entry = max(max_entry, int(number.group(1)))
            entry = Entry(
                entry_id=payload["entry_id"],
                data=payload.get("data", ""),
                tokens=payload["tokens"],
                key=payload.get("key"),
                written_by=record["actor"],
                tick=payload.get("tick", 0),
                seq=seq,
            )
            if payload.get("mode") == "replace":
                if region.policy.versioned:
                    region.history.extend(region.entries)
                region.entries = [entry]
            elif payload.get("replaced_entry_id"):
                index = next(
                    i for i, e in enumerate(region.entries)
                    if e.entry_id == payload["replaced_entry_id"]
                )
                if region.policy.versioned:
                    region.history.append(region.entries[index])
                region.entries[index] = entry
            else:
                region.entries.append(entry)
            region.revision += 1
            region.last_mutation_seq = seq
            loop = window.loops.get(payload.get("loop_id"))
            if loop is not None:
                loop.writes += 1

        elif kind == "scw.evict":
            region = window.regions[payload["scw_id"]]
            dropped = set(payload["entry_ids"])
            kept = [e for e in region.entries if e.entry_id not in dropped]
            if region.policy.versioned:
                region.history.extend([e for e in region.entries if e.entry_id in dropped])
            region.entries = kept
            if payload.get("reason") == "budget":
                region.evicted_tokens += payload.get("tokens_freed", 0)
            region.revision += 1
            region.last_mutation_seq = seq

        elif kind == "scw.read":
            targets = [payload["scw_id"]]
            if payload.get("include_children", True):
                targets += sorted(descendants(window, payload["scw_id"]))
            for target_id in targets:
                region = window.regions[target_id]
                for entry in region.entries:
                    entry.last_read_seq = seq
                region.last_read_seq = seq
            loop = window.loops.get(payload.get("loop_id"))
            if loop is not None:
                loop.reads += 1

        elif kind == "scw.denied":
            loop = window.loops.get(payload.get("loop_id"))
            if loop is not None:
                loop.denials += 1

        elif kind == "scw.close":
            region = window.regions[payload["scw_id"]]
            region.lifecycle = payload["lifecycle"]
            region.revision += 1
            region.last_mutation_seq = seq

        elif kind == "scw.purge":
            region = window.regions[payload["scw_id"]]
            if region.policy.versioned:
                region.history.extend(region.entries)
            region.entries = []

        elif kind == "loop.bind":
            loop = Loop(
                loop_id=payload["loop_id"],
                scw_id=payload["scw_id"],
                descend=payload["descend"],
                bound_seq=seq,
                max_iterations=payload.get("max_iterations"),
                trigger=payload.get("trigger", "manual"),
                goal=payload.get("goal"),
                verification_level=payload.get("verification_level"),
                prompt_id=payload.get("prompt_id"),
                prompt_version_at_bind=payload.get("prompt_version_at_bind"),
                harness_id=payload.get("harness_id"),
                exposes=tuple(payload.get("exposes", ())),
                criterion_id=payload.get("criterion_id"),
                parent_loop_id=payload.get("parent_loop_id"),
                depth=payload.get("depth", 0),
                generation=payload.get("generation", 1),
                lifetime=dict(payload.get("lifetime") or {}),
            )
            window.loops[loop.loop_id] = loop
            parent = window.loops.get(loop.parent_loop_id) if loop.parent_loop_id else None
            if parent is not None and loop.loop_id not in parent.child_loop_ids:
                parent.child_loop_ids.append(loop.loop_id)
            window.iteration_boundary_seq = seq
            # Derived state, rebuilt rather than re-enforced: a log records a
            # binding that already succeeded. Mirror bind_scope's condition —
            # only disjoint-policy bindings move the ceiling.
            _h = window.harnesses.get(loop.harness_id) if loop.harness_id else None
            if _h is not None and _h.verification_policy == "disjoint":
                record_exposure_ceiling(window, loop.scw_id, loop.exposes)

        elif kind == "loop.tick":
            loop = window.loops[payload["loop_id"]]
            loop.iteration = payload["iteration"]
            loop.status = payload.get("status", loop.status)
            cache = payload.get("cache", {})
            loop.cached_tokens += cache.get("cached_tokens", 0)
            loop.reprocessed_tokens += cache.get("reprocessed_tokens", 0)
            loop.recoverable_tokens += cache.get("recoverable_tokens", 0)
            verified = payload.get("verified")
            if verified is True:
                loop.accepted += 1
                loop.unverified_streak = 0
            elif verified is False:
                loop.rejected += 1
                loop.unverified_streak += 1
            else:
                loop.unverified += 1
                loop.unverified_streak += 1
            if verified is True and payload.get("verified_by") == loop.loop_id:
                loop.self_approved += 1
            if loop.harness_id is not None:
                window.harnesses[loop.harness_id].iterations_run += 1
            consumed = payload.get("evidence_id")
            if consumed is not None:
                loop.attested += 1
                attestation = window.evidence.get(consumed)
                if attestation is not None:
                    attestation.consumed_by_tick = payload["tick"]
            window.total_iterations += 1
            window.tick = payload["tick"]
            window.last_tick_seq = seq
            window.iteration_boundary_seq = seq
            window._tick_snapshot = window._snapshot_now()

        elif kind == "loop.unbind":
            loop = window.loops[payload["loop_id"]]
            loop.status = "unbound"
            loop.terminal_state = payload.get("terminal_state")

        elif kind == "bridge.open":
            number = _BRIDGE_ID.match(payload["bridge_id"])
            if number:
                max_bridge = max(max_bridge, int(number.group(1)))
            window.bridges[payload["bridge_id"]] = Bridge(
                bridge_id=payload["bridge_id"],
                from_scw_id=payload["from_scw_id"],
                to_scw_id=payload["to_scw_id"],
                mode=payload["mode"],
                reason=payload.get("reason", ""),
                opened_seq=seq,
                opened_tick=payload["opened_tick"],
                ttl_ticks=payload.get("ttl_ticks"),
                owner_loop_id=payload.get("owner_loop_id") or payload.get("loop_id"),
            )

        elif kind == "bridge.close":
            bridge = window.bridges.get(payload["bridge_id"])
            if bridge is not None:
                bridge.status = payload.get("status", "closed")

        elif kind == "promote":
            source = window.regions[payload["from_scw_id"]]
            target = window.regions[payload["to_scw_id"]]
            for item in payload["entries"]:
                number = _ENTRY_ID.match(item["entry_id"])
                if number:
                    max_entry = max(max_entry, int(number.group(1)))
                origin = next(
                    (e for e in source.entries if e.entry_id == item["source_entry_id"]), None
                )
                target.entries.append(
                    Entry(
                        entry_id=item["entry_id"],
                        data=(origin.data if origin is not None else item.get("data") or ""),
                        tokens=item["tokens"],
                        key=item.get("key"),
                        written_by=record["actor"],
                        tick=payload.get("tick", 0),
                        seq=seq,
                        provenance={
                            "from_scw_id": payload["from_scw_id"],
                            "source_entry_id": item["source_entry_id"],
                            "source_tick": origin.tick if origin is not None else payload.get("tick", 0),
                            "loop_id": payload.get("loop_id"),
                            "promoted_at_seq": seq,
                            "via": payload.get("via"),
                        },
                    )
                )
                if payload.get("mode") == "move" and origin is not None:
                    source.entries.remove(origin)
                    if source.policy.versioned:
                        source.history.append(origin)
            target.revision += 1
            target.last_mutation_seq = seq
            if payload.get("mode") == "move":
                source.revision += 1
                source.last_mutation_seq = seq

        elif kind == "window.render":
            if payload.get("committed"):
                # Render baselines are per-caller, so the fold has to key them
                # the same way the live runtime does.
                viewer = payload.get("loop_id")
                costs = window._visible_costs(
                    window.read_closure(viewer) if viewer is not None else None
                )
                window._render_snapshots[viewer] = Snapshot(
                    order=[c.scw_id for c in costs],
                    signatures={c.scw_id: c.signature for c in costs},
                )

        elif kind == "prompt.create":
            window.prompts[payload["prompt_id"]] = PromptSpec(
                prompt_id=payload["prompt_id"],
                label=payload["label"],
                template=payload["template"],
                variables=tuple(payload.get("variables", ())),
                created_seq=seq,
                locked=payload.get("locked", False),
            )

        elif kind == "prompt.revise":
            spec = window.prompts[payload["prompt_id"]]
            spec.history.append(
                PromptRevision(version=spec.version, template=spec.template, revised_seq=seq)
            )
            spec.template = payload["template"]
            spec.variables = tuple(payload.get("variables", ()))
            spec.version = payload["version"]
            spec.locked = payload.get("locked", False)

        elif kind == "prompt.render":
            window.prompts[payload["prompt_id"]].render_count += 1

        elif kind == "harness.create":
            skills = {
                item["skill_id"]: Skill(
                    skill_id=item["skill_id"],
                    name=item["name"],
                    description=item.get("description", ""),
                    verified=bool(item.get("verified", False)),
                )
                for item in payload.get("skills", [])
            }
            window.harnesses[payload["harness_id"]] = HarnessProfile(
                harness_id=payload["harness_id"],
                label=payload["label"],
                created_seq=seq,
                architecture=payload.get("architecture", "solo"),
                skills=skills,
                strict_skills=payload.get("strict_skills", False),
                tool_grants=tuple(payload.get("tool_grants", ())),
                sandbox=payload.get("sandbox", "shared"),
                iteration_budget=payload.get("iteration_budget"),
                requires_approval=tuple(payload.get("requires_approval", ())),
                verification_policy=payload.get("verification_policy"),
                evidence_policy=payload.get("evidence_policy", "none"),
            )

        elif kind == "criterion.pin":
            number = _CRITERION_ID.match(payload["criterion_id"])
            if number:
                max_criterion = max(max_criterion, int(number.group(1)))
            existing = window.criteria.get(payload["criterion_id"])
            if existing is None:
                window.criteria[payload["criterion_id"]] = Criterion(
                    criterion_id=payload["criterion_id"],
                    scw_id=payload["scw_id"],
                    label=payload.get("label", ""),
                    signature=payload["signature"],
                    pinned_seq=seq,
                    pinned_tick=payload.get("pinned_tick", 0),
                    status=payload.get("status", "pinned"),
                    drift_detected=payload.get("drift_detected", 0),
                )
            else:  # a repin
                existing.signature = payload["signature"]
                existing.pinned_seq = seq
                existing.pinned_tick = payload.get("pinned_tick", 0)
                existing.status = payload.get("status", "pinned")
                existing.drift_detected = payload.get("drift_detected", existing.drift_detected)

        elif kind == "criterion.unpin":
            criterion = window.criteria.get(payload["criterion_id"])
            if criterion is not None:
                criterion.status = "released"

        elif kind == "evidence.attest":
            number = _EVIDENCE_ID.match(payload["evidence_id"])
            if number:
                max_evidence = max(max_evidence, int(number.group(1)))
            window.evidence[payload["evidence_id"]] = Attestation(
                evidence_id=payload["evidence_id"],
                loop_id=payload["loop_id"],
                kind=payload["kind"],
                attested_seq=seq,
                attested_tick=payload.get("attested_tick", 0),
                scope_signature=payload.get("scope_signature", ""),
                command=payload.get("command"),
                argv=tuple(payload.get("argv", ())),
                exit_code=payload.get("exit_code"),
                output_sha256=payload.get("output_sha256"),
                output_bytes=payload.get("output_bytes"),
                artifact_sha256=payload.get("artifact_sha256"),
                criterion_id=payload.get("criterion_id"),
                score=payload.get("score"),
                approver=payload.get("approver"),
                note=payload.get("note", ""),
            )

        elif kind == "partition.check":
            # A pure decision record: the disjointness report is derivable from
            # state, so replay needs only to have kept the state it was
            # computed over. Nothing to fold.
            continue

        elif kind == "harness.call":
            harness = window.harnesses[payload["harness_id"]]
            refused_reason = payload.get("refused_reason")
            if not payload.get("declared", True):
                harness.undeclared_calls += 1
            if payload.get("gated"):
                harness.approvals_required += 1
                if refused_reason is None:
                    harness.approvals_granted += 1
            if refused_reason is None:
                harness.calls += 1

        elif kind == "window.seal":
            window.strict_scope = True

        elif kind in ("window.init", "window.reset"):
            continue

    window._entry_seq = max_entry
    window._bridge_seq = max_bridge
    window._criterion_seq = max_criterion
    window._evidence_seq = max_evidence
    window.log.records = list(records)
    window.log._seq = len(records)
    if records:
        window.log._prev = records[-1]["digest"]
    return window


def replay_file(
    path: str | os.PathLike[str], verify: bool = True, run_id: Optional[str] = None
) -> ContextWindow:
    """Replay a JSONL log from disk. Defaults to the file's last run."""
    return replay(list(iter_records(path)), verify=verify, run_id=run_id)


def replay_prefix(
    records: Sequence[dict], upto: Optional[int] = None, verify: bool = False
) -> ContextWindow:
    """Replay only the first ``upto`` records — the step-through primitive.

    This is what a scrubbing timeline is: state as of event *n*.
    """
    sliced = list(records) if upto is None else list(records)[: upto + 1]
    return replay(sliced, verify=verify)
