"""Read-only window onto *this machine's real SCW MCP activity*.

Every `mcp__Structured_Context_Windows__*` / `mcp__plugin_maxey0_worlds__*`
tool call a Claude Code session makes is handled by `scw_runtime.server`,
which keeps its own in-memory `ContextWindow` in its own OS process and
flushes every event to `SCW_EVENT_LOG` (default `~/.scw/events.jsonl`) as it
happens. That process and this one do not share memory -- there is no way
for an HTTP server to reach into another process's Python objects -- so this
module does the next most honest thing: it reads the exact same file that
process is writing, and replays it with the exact same reducer
(`scw_runtime.replay`) that produces "real" state everywhere else in this
codebase. What you get back is not a simulation of the live session; it is
the live session, reconstructed from its own durable log.

Two caveats, both surfaced in the payload rather than hidden:

1. This is observation-only. Writing into another process's window isn't
   something a second process can safely do without shared memory or a lock
   protocol neither process has -- so nothing here can dispatch work into
   *that* session. Use the Studio's own window (`state.Session`) for that.
2. If more than one Claude Code session has run on this machine, they may
   all append to the same default log file with no coordination between
   them. `scw_runtime.events.verify_records` catches exactly this (a broken
   hash chain across runs); we report it as `chain_intact: false` rather
   than crash, and fall back to per-run replay, which stays valid even when
   the whole-file chain does not.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from scw_runtime.events import iter_records, verify_records
from scw_runtime.errors import ChainBroken, SCWError
from scw_runtime.replay import replay, split_runs

LIVE_LOG = Path(os.environ.get("SCW_EVENT_LOG") or (Path.home() / ".scw" / "events.jsonl"))

# A run with only its window.init record (no scw.create/write/loop.bind etc.)
# is one that started and never did anything -- not worth surfacing as "the
# session", so read_live_session() skips past those when picking a run.
_TRIVIAL_TYPES = {"window.init", "window.seal", "window.reset"}


def _window_payload(window, run_id: str, record_count: int, ts_last: Optional[float]) -> dict:
    from scw_runtime import partition

    loops = []
    for loop_id, loop in sorted(window.loops.items()):
        loops.append({
            "loop_id": loop_id,
            "scw_id": loop.scw_id,
            "status": loop.status,
            "iteration": loop.iteration,
            "exposes": list(loop.exposes),
            "read_closure": sorted(partition.read_closure(window, loop_id)),
            "write_closure": sorted(partition.write_closure(window, loop_id)),
        })
    return {
        "run_id": run_id,
        "record_count": record_count,
        "last_event_ts": ts_last,
        "regions": window.region_map(include_content=False),
        "loops": loops,
        "bridges": [
            {"bridge_id": b.bridge_id, "from": b.from_scw_id, "to": b.to_scw_id,
             "mode": b.mode, "status": b.status}
            for b in window.bridges.values()
        ],
        "tokens": window.inspect(include_content=False).get("tokens"),
    }


def read_live_session() -> dict:
    """This machine's real SCW MCP activity, read straight off disk.

    Returns a dict with `available`, `source` ("this_session" | "last_recorded"
    | "none"), `chain_intact`, and -- when available -- a `window` payload
    shaped like the Studio's own snapshot (regions/loops/bridges/tokens).
    """
    if not LIVE_LOG.exists():
        return {"ok": True, "available": False, "source": "none",
                "log_path": str(LIVE_LOG),
                "message": "no SCW MCP activity recorded on this machine yet"}

    records = list(iter_records(LIVE_LOG))
    if not records:
        return {"ok": True, "available": False, "source": "none",
                "log_path": str(LIVE_LOG), "message": "log exists but is empty"}

    chain_intact = True
    try:
        verify_records(records)
    except ChainBroken:
        chain_intact = False

    runs = split_runs(records)
    runs = [r for r in runs if r]

    def has_activity(run: list[dict]) -> bool:
        return any(rec["type"] not in _TRIVIAL_TYPES for rec in run)

    current = runs[-1] if runs else []
    source = "this_session"
    chosen = current
    if not has_activity(current):
        # This process's own run hasn't done anything yet -- fall back to the
        # most recent run that did, clearly labeled as not the live one.
        prior = next((r for r in reversed(runs[:-1]) if has_activity(r)), None)
        if prior is not None:
            chosen = prior
            source = "last_recorded"
        else:
            source = "this_session"  # genuinely nothing anywhere yet

    if not chosen:
        return {"ok": True, "available": False, "source": "none",
                "log_path": str(LIVE_LOG), "chain_intact": chain_intact,
                "message": "no run with any activity found in the log"}

    run_id = chosen[0].get("run_id")
    try:
        window = replay(chosen, verify=False)
    except SCWError as exc:
        return {"ok": False, "available": False, "error": type(exc).__name__,
                "message": str(exc), "log_path": str(LIVE_LOG)}

    payload = _window_payload(window, run_id, len(chosen), chosen[-1].get("ts"))
    return {
        "ok": True,
        "available": True,
        "source": source,
        "chain_intact": chain_intact,
        "log_path": str(LIVE_LOG),
        "total_records_on_disk": len(records),
        "total_runs_on_disk": len(runs),
        "window": payload,
    }


def list_runs(limit: int = 20) -> dict:
    """Every run recorded in the live log, most recent first -- for a picker."""
    if not LIVE_LOG.exists():
        return {"ok": True, "runs": [], "log_path": str(LIVE_LOG)}
    records = list(iter_records(LIVE_LOG))
    runs = [r for r in split_runs(records) if r]
    out = []
    for run in reversed(runs[-limit:]):
        out.append({
            "run_id": run[0].get("run_id"),
            "record_count": len(run),
            "first_ts": run[0].get("ts"),
            "last_ts": run[-1].get("ts"),
            "has_activity": any(rec["type"] not in _TRIVIAL_TYPES for rec in run),
        })
    return {"ok": True, "runs": out, "log_path": str(LIVE_LOG)}
