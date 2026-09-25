"""Observatory-plane tools — evidence about a run, read from disk.

This plane records what actually happened and refuses what left scope. It is
the plane with visibility into the other two, and it gets that visibility
without sharing a process with either:

    the Context plane's ledger   `~/.scw/events.jsonl`, hash-chained JSONL
    the Gate's journal           `~/.scw/gate.jsonl`, separately chained

Both are files. So the Observatory reads the Context plane's ledger from disk
and, where it needs structure rather than a record list, **replays** it into a
window — the same reduction `tests/test_scw_runtime.py` asserts reconstructs an
identical object. That gives it the region graph, every scope, and every
closure, while leaving it structurally unable to write any of them. Full
visibility into the other two planes, no authority over either, and neither of
them has to be running.

It is also useful with no Context plane and no library at all. The Gate is a
hook: it stands at every tool call in every session, attributes each one to the
role that made it, and can refuse the ones reaching outside that role's
declared scope. That is global workspace semantics, and it works whether or not
anything has ever been partitioned.

Two rules the Gate does not break, and this module inherits both. A broken gate
must never break a session. A gate that fails open must say so — every
fail-open is recorded as such, and any containment figure computed over a
window containing fail-opens is reported with that residue attached, because a
run with residue has a hole exactly where the evidence would go.
"""

from __future__ import annotations

import os

try:  # observe/gate tools show paths to callers: never the username
    from gate.privacy import shorten_home
except ImportError:  # pragma: no cover
    def shorten_home(text: str) -> str:  # type: ignore[misc]
        # Degraded, never raw: still hide the current user's home.
        home = os.path.expanduser("~")
        return text.replace(home, "~") if home and home != "~" else text

from typing import Optional

from . import bootstrap

bootstrap.prepare()

from gate import journal as gate_journal
from gate import levels as gate_levels
from gate import store as gate_store
from gate.protocol import GATE_MODES, Policy
from maxey0_studio import gate_view as gv
from maxey0_studio import observability as obs
from maxey0_studio import traces as tr

from . import bootstrap
from .catalog import VIEWS as _VIEWS

STUDIO_PORT = int(os.environ.get("MAXEY0_STUDIO_PORT", 7676))


def _gate_session() -> Optional[str]:
    """Which session's gate state to act on.

    The Gate keys its state by the host's session id, which an MCP server does
    not receive. `MAXEY0_GATE_SESSION` pins it when a run needs a known key;
    otherwise the run-wide default file is used, which is the same one the hook
    falls back to.
    """
    return os.environ.get("MAXEY0_GATE_SESSION")


def _replayed_window():
    """Reconstruct the Context plane's window from its ledger.

    Returns `(window, status)`. The window is `None` when there is no ledger to
    replay or the chain will not fold — and that is reported as a named cause
    rather than as an empty result, because "no evidence was recorded" and
    "the evidence says nothing happened" are different claims and the product
    refuses to collapse them.
    """
    from scw_runtime.replay import replay_file

    path = bootstrap.ledger_path()
    if not path.exists():
        return None, {
            "ledger": shorten_home(str(path)), "present": False,
            "note": "No ledger at this path. Nothing about the Context plane "
                    "can be established from it, in either direction.",
        }
    try:
        window = replay_file(path)
    except Exception as exc:  # the Observatory must never take a session down
        return None, {
            "ledger": shorten_home(str(path)), "present": True, "replayed": False,
            "error": type(exc).__name__, "message": str(exc),
            "note": "The ledger exists but would not replay. Treat every "
                    "figure derived from it as unestablished, not as zero.",
        }
    return window, {"ledger": shorten_home(str(path)), "present": True, "replayed": True}


# ---------------------------------------------------------------------------
# the event stream — the Context plane's ledger, as a typed projection
# ---------------------------------------------------------------------------

def observe_events(
    kinds: Optional[list[str]] = None,
    role: Optional[str] = None,
    region: Optional[str] = None,
    since_seq: int = 0,
    limit: int = 200,
) -> dict:
    """The Context plane's ledger as a typed, queryable stream.

    `kinds` filters by group rather than by raw event type: access, refusal,
    scope, bridge, utilization, audit, routing. Omit every filter for a summary
    of what the run has done so far.

    Read from the ledger file, so this answers for the Context plane whether or
    not that connector is installed or running.
    """
    records, status = bootstrap.read_ledger()
    if not status["present"]:
        return {"ok": True, "available": False, **status}
    if kinds is None and role is None and region is None and since_seq == 0:
        return {"ok": True, "available": True, **status, **obs.summary(records)}
    return {
        "ok": True, "available": True, **status,
        **obs.project(records, kinds=kinds, loop_id=role, scw_id=region,
                      since_seq=since_seq, limit=limit),
    }


def observe_attempts(role: Optional[str] = None,
                     region: Optional[str] = None) -> dict:
    """Did this role attempt to reach this region, and what happened?

    The containment question answered from recorded events rather than by
    asking a model what it could see. `contained` is three-valued: true and
    false mean every attempt was refused or some was allowed; **null means no
    attempt was recorded**, which establishes nothing either way.

    This reads the Context plane's ledger, which records what the host did to
    the window. It cannot see what a delegated agent did inside its own
    context — that is what the Gate is for. Use `observe_gate_activity` for the
    agents' own tool calls.
    """
    records, status = bootstrap.read_ledger()
    if not status["present"]:
        return {"ok": True, "available": False, **status}
    return {"ok": True, "available": True, **status,
            **obs.attempts(records, loop_id=role, scw_id=region)}


def observe_traces(limit: int = 200) -> dict:
    """Correlate the context, execution and state traces for this run.

    Three histories that only answer a useful question together:

      context    what was constructed and who was handed it (the ledger)
      execution  what the agent then did (the Gate journal — the ledger cannot
                 see inside a delegated context)
      state      how each region's contents changed

    Returns a merged timeline plus a per-role join: what each role was given,
    what it then did, and a finding where those two disagree. A role handed
    context that made no observed call, and one that acted with no recorded
    transfer, are both worth knowing.

    The join key is each Gate record's anchor into the ledger, not a wall-clock
    comparison across two processes. The merged view is a projection, not
    evidence; each log is separately chained and separately verified.
    """
    runtime_records, status = bootstrap.read_ledger()
    gate_records = gate_journal.read_all()["records"]
    return {"ok": True, "context_ledger": status,
            **tr.correlate(runtime_records, gate_records, limit=limit)}


# ---------------------------------------------------------------------------
# the Gate
# ---------------------------------------------------------------------------
# The measured gap these close: through 0.5.0 the runtime recorded 41 scope
# binds, 96 region creations and 80 grants against ZERO read events, while the
# subagents those roles dispatched made 115 real tool calls that appear nowhere
# in the window. The partition governed regions; the agents reached the
# filesystem. See docs/ARCHITECTURE.md.
#
# A policy is declared HERE, by the host, before dispatch. It is deliberately
# not something a role can set for itself — a party that can widen its own
# scope satisfies any containment rule vacuously.

def observe_gate_policy(
    role: str,
    read_paths: Optional[list[str]] = None,
    write_paths: Optional[list[str]] = None,
    tools: Optional[list[str]] = None,
    bash_allow: Optional[list[str]] = None,
    note: str = "",
    workdir: Optional[str] = None,
) -> dict:
    """Declare what a bound role may reach **outside** the window.

    The partition governs regions. It has never governed the filesystem, the
    shell, or the network — which is how a role bound to a 2,048-token
    scratchpad could read the whole disk while every region stayed perfectly
    contained, and no measurement noticed.

    Default to `read_paths=[]` and a narrow `tools` list. A role in a
    partitioned loop is supposed to work from what `context_window_render` gave
    it; needing the repo is a decision to make explicitly and record, not a
    convenience to leave open. Never grant `bash_allow` unless the role
    genuinely needs a shell — a shell is a general-purpose escape from every
    path check above it.
    """
    policy = Policy(
        loop_id=role,
        read_paths=tuple(read_paths or []),
        write_paths=tuple(write_paths or []),
        tools=tuple(tools or []),
        bash_allow=tuple(bash_allow or []),
        note=note,
    )
    gate_store.declare(_gate_session(), policy)
    # `workdir` is the one attribution mechanism portable to hosts that report
    # no actor identity, and no shipped tool could pass it, so the cwd
    # resolver the docs describe could never be switched on. Declaring it
    # records the role's working directory for attribution.resolve_by_cwd.
    if workdir:
        from gate import attribution as gate_attribution

        gate_attribution.declare_dispatch(_gate_session(), role, workdir=workdir)
    return {"ok": True, "role": role, "policy": policy.to_dict(), "workdir": workdir,
            "mode": gate_store.get_mode(_gate_session()),
            "note": "declared by the host before dispatch; a role cannot widen "
                    "its own scope"}


def observe_gate_mode(mode: Optional[str] = None) -> dict:
    """Read or set the Gate: `enforce`, `observe`, or `off`.

    `observe` is not a weaker `enforce`. It is the only way to measure how
    often a role *attempts* to leave its partition, which is a property of the
    formation rather than of the enforcement — and it is the most informative
    condition there is.

    Installs inert: the default is `observe`, so the plugin records but blocks
    nothing until a policy is declared and `enforce` is set.
    """
    session = _gate_session()
    if mode is None:
        return {"ok": True, "mode": gate_store.get_mode(session),
                "modes": list(GATE_MODES)}
    if mode not in GATE_MODES:
        return {"ok": False, "error": "unknown_mode", "modes": list(GATE_MODES)}
    pinned = os.environ.get("MAXEY0_GATE_MODE")
    if pinned:
        return {"ok": False, "error": "mode_pinned", "pinned_to": pinned,
                "message": "MAXEY0_GATE_MODE pins the mode for this process; "
                           "unset it to change the mode from a session"}
    gate_store.set_mode(session, mode)
    return {"ok": True, "mode": mode, "modes": list(GATE_MODES)}


def observe_gate_activity(role: Optional[str] = None,
                          kinds: Optional[list[str]] = None,
                          limit: int = 100) -> dict:
    """What the delegated agents actually did, per role.

    This is the stream the ledger cannot contain. The same honesty applies:
    `held` is three-valued and `claimable` is false whenever any residue
    exists, because a run that failed open, lost a record, or could not
    attribute a call has a hole exactly where the containment claim goes.
    """
    data = gate_journal.read_all()
    records = data["records"]
    if not records:
        return {"ok": True, "available": False, "path": data["path"],
                "message": "no agent tool call has been intercepted yet; the "
                           "Gate records nothing until a subagent runs"}
    return {
        "ok": True,
        "available": True,
        "path": data["path"],
        "chain": gate_journal.verify(records, damaged=data["damaged"]),
        "damaged": data["damaged"],
        "by_role": gv.by_role(records),
        "containment": gv.containment(records, damaged=data["damaged"]),
        "recent": gv.project(records, kinds=kinds, loop_id=role,
                             limit=limit)["events"],
    }


def observe_isolation_level(declared: Optional[str] = None) -> dict:
    """Which isolation level this run's evidence actually supports.

    The architectural primitive is not "a second runtime" — it is an
    independent state-transition boundary, and a partition can be real in four
    quite different senses:

        L0_none       no partition; a skill is just extra context
        L1_logical    distinct context objects, one runtime. Logical isolation,
                      NOT hard isolation
        L2_execution  each role ran in its own execution context
        L3_observed   L2 plus every crossing recorded and reintegration limited
                      to declared outputs

    A level must be EARNED from evidence, never asserted. Declare L3 and get L1
    — three roles dispatched into one shared context, the partition existing
    only in the prompt — and nothing else in the stack would notice. This is
    what notices: pass what you declared and it reports what the recorded
    evidence supports, naming the shortfall where they differ.

    The scope rows come from replaying the Context plane's ledger, so this
    answers across a process boundary and reports the ledger's own status when
    there is nothing to replay.
    """
    if declared is not None and declared not in gate_levels.LEVELS:
        return {"ok": False, "error": "unknown_level",
                "levels": list(gate_levels.LEVEL_NAMES)}

    window, ledger = _replayed_window()
    if window is None:
        rows: list[dict] = []
    else:
        rows = [
            {"loop_id": lid, "scw_id": lp.scw_id, "status": lp.status,
             "read_closure": sorted(window.read_closure(lid))}
            for lid, lp in window.loops.items()
        ]

    data = gate_journal.read_all()
    assessment = gate_levels.assess(rows, data["records"],
                                    declared=declared, damaged=data["damaged"])
    return {"ok": True, "ladder": gate_levels.ladder(),
            "context_ledger": ledger, **assessment.to_dict()}


# ---------------------------------------------------------------------------
# the Studio
# ---------------------------------------------------------------------------

def observe_studio() -> dict:
    """Where the Studio is, and how to start it.

    Reports the address; it does not launch the process. An MCP server that
    spawned a long-lived HTTP listener as a side effect of a tool call would be
    starting something the caller cannot see and cannot stop.
    """
    return {
        "ok": True,
        "url": f"http://127.0.0.1:{STUDIO_PORT}",
        "start": f"python server/run_studio.py --port {STUDIO_PORT}",
        "command": "/maxey0:studio",
        "views": [name for name, _ in _VIEWS],
        "note": "Loopback only, and no authentication. It renders the contents "
                "of live regions, so do not expose the port.",
    }

