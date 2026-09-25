"""Reusable scaffolding for live, partitioned multi-role experiments.

Extracted and parameterized from `scw_paper_loop.py` (not modified — that
file remains the validated reference run this kit generalizes away from).
Every function here is paper-agnostic: no SECTION_IDS, no CONCESSIONS, no
hardcoded run directory. A caller supplies a run directory and window
constructor kwargs; everything else is identical in behavior to the
original functions this was extracted from.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from scw_runtime import ContextWindow, EventLog, replay
from scw_runtime import partition
from scw_runtime.privacy import redact  # nothing user-typed reaches disk unredacted


def resolve_data_files(args: dict[str, Any], *, run_dir: Path) -> dict[str, Any]:
    """Expand `data_file` (a path relative to run_dir) into `data`."""
    args = dict(args)
    src = args.pop("data_file", None)
    if src is not None:
        args["data"] = (run_dir / src).read_text(encoding="utf-8")
    return args


def rebuild(
    ops: list[dict[str, Any]],
    *,
    window_kwargs: dict[str, Any],
    run_dir: Path,
    run_id: str,
    log_path: Optional[Path] = None,
) -> ContextWindow:
    """Re-execute every op from empty against a deterministic clock."""
    tick = iter(range(10 ** 6))
    log = EventLog(path=str(log_path) if log_path else None,
                    clock=lambda: float(next(tick)), run_id=run_id)
    window = ContextWindow(event_log=log, **window_kwargs)
    for index, op in enumerate(ops):
        name, args = op["op"], resolve_data_files(op.get("args", {}), run_dir=run_dir)
        if name == "note":
            continue
        method = getattr(window, name, None)
        if method is None:
            raise SystemExit(f"op {index} names no runtime method: {name!r}")
        try:
            method(**args)
        except Exception as exc:  # noqa: BLE001 - refusals are data here
            if op.get("expect_refusal"):
                op["refusal"] = f"{type(exc).__name__}: {exc}"
                continue
            raise SystemExit(f"op {index} ({name}) failed: {type(exc).__name__}: {exc}") from exc
        else:
            if op.get("expect_refusal"):
                raise SystemExit(f"op {index} ({name}) was expected to be refused and was not")
    if log_path:
        log.close()
    return window


def load_ops(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_ops(path: Path, ops: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(redact(ops), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def materialize(
    ops: list[dict[str, Any]],
    *,
    window_kwargs: dict[str, Any],
    run_dir: Path,
    run_id: str,
    log_path: Path,
) -> ContextWindow:
    """Rebuild, persist the log, and assert the log replays to the same window."""
    if log_path.exists():
        log_path.unlink()
    window = rebuild(ops, window_kwargs=window_kwargs, run_dir=run_dir,
                      run_id=run_id, log_path=log_path)
    window.log.verify()
    rebuilt = replay(window.log.records)
    live = window.inspect(include_content=True, loop_id=None)
    if rebuilt.inspect(include_content=True, loop_id=None) != live:
        raise SystemExit("replay of the event log did not reconstruct the window")
    return window


def containment_report(window: ContextWindow) -> dict[str, Any]:
    """Whether any scope reached outside its partition, and who may judge whom.

    Verbatim port of scw_paper_loop.py's containment_report — this function
    was already paper-agnostic (it operates purely on window.regions and
    window.loops), so no parameterization was needed.
    """
    everything = set(window.regions)
    private = {scw_id for scw_id, region in window.regions.items()
               if not region.policy.bridgeable}

    breaches = []
    reachable_by_someone: set[str] = set()
    for loop_id in sorted(window.loops):
        reach = partition.read_closure(window, loop_id)
        reachable_by_someone |= reach
        own = window.loops[loop_id].scw_id
        trespass = sorted((reach & private) - {own})
        if trespass:
            breaches.append({"loop": loop_id, "reached": trespass})

    cases = []
    for loop_id in sorted(window.loops):
        writes = partition.write_closure(window, loop_id)
        published = {s for s in writes if s not in private}
        if not published:
            continue
        exposes = set(getattr(window.loops[loop_id], "exposes", []) or [])
        admissible, refused = [], {}
        for candidate in sorted(window.loops):
            if candidate == loop_id:
                continue
            report = window.disjointness(loop_id, candidate)
            if report["disjoint"]:
                admissible.append(candidate)
            else:
                refused[candidate] = report["failed"]
        cases.append({
            "maker": loop_id,
            "write_closure": sorted(writes),
            "published_writes": sorted(published),
            "exposes": sorted(exposes),
            "confined_to_handoff": published <= exposes,
            "admissible_judges": admissible,
            "refused_judges": refused,
        })

    widest = max((len(partition.read_closure(window, lid)) for lid in window.loops), default=0)
    verdict = (
        f"{len(private)}/{len(everything)} regions refuse all grants; "
        f"the widest scope reads {widest}/{len(everything)}; "
        f"{len(breaches)} containment breaches"
    )
    return {
        "bound_holds": not breaches,
        "breaches": breaches,
        "private_regions": sorted(private),
        "regions_no_scope_can_read": sorted(everything - reachable_by_someone),
        "widest_read_closure": widest,
        "verdict": verdict,
        "cases": cases,
    }


def access_matrix(window: ContextWindow) -> dict[str, Any]:
    """Empirically probe every (loop, region) pair with a real ``read``.

    Verbatim port of scw_paper_loop.py's access_matrix.
    """
    rows: dict[str, dict[str, bool]] = {}
    disagreements = []
    for loop_id in sorted(window.loops):
        closure = partition.read_closure(window, loop_id)
        row: dict[str, bool] = {}
        for scw_id in sorted(window.regions):
            try:
                window.read(scw_id, loop_id=loop_id)
            except Exception:  # noqa: BLE001 - a refusal is the datum
                row[scw_id] = False
            else:
                row[scw_id] = True
            if row[scw_id] != (scw_id in closure):
                disagreements.append({"loop": loop_id, "region": scw_id,
                                       "call": row[scw_id], "closure": scw_id in closure})
        rows[loop_id] = row
    granted = sum(sum(1 for v in row.values() if v) for row in rows.values())
    total = len(rows) * len(window.regions) if rows else 0
    return {
        "matrix": rows,
        "granted": granted,
        "refused": total - granted,
        "cells": total,
        "closure_disagreements": disagreements,
    }


def cost_model(window: ContextWindow, *, corpus_region_ids: Optional[list[str]] = None) -> dict[str, Any]:
    """What the partition costs, against what replicating the window would.

    Generalized from scw_paper_loop.py's cost_model: `corpus_region_ids` (an
    optional list of region ids treated as "the corpus" for the per-loop
    diagnostic breakdown) replaces the hardcoded SECTION_IDS/CONCESSIONS.
    The core flat-vs-partitioned computation does not depend on it.
    """
    corpus_region_ids = corpus_region_ids or []
    whole = window.render(loop_id=None, commit=False)["tokens"]
    per_loop = {}
    for loop_id in sorted(window.loops):
        result = window.render(loop_id=loop_id, commit=False)
        reach = partition.read_closure(window, loop_id)
        corpus = sorted(s for s in reach if s in corpus_region_ids)
        per_loop[loop_id] = {
            "tokens": result["tokens"],
            "segments": len(result["segments"]),
            "elided_regions": len(result["elided"]),
            "corpus_sections": corpus,
        }
    partitioned = sum(v["tokens"] for v in per_loop.values())
    flat = whole * len(per_loop)
    return {
        "per_loop": per_loop,
        "totals": {
            "window_tokens": whole,
            "scopes": len(per_loop),
            "flat_tokens": flat,
            "partitioned_tokens": partitioned,
            "reduction_ratio": round(flat / partitioned, 3) if partitioned else None,
        },
    }
