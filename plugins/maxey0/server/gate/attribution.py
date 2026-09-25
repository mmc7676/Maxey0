"""Tying a tool call back to a bound role — and admitting when it cannot be done.

The gate sees a host's actor identifier (for Claude Code, ``agent_id``). The
window knows SCW ``loop_id``s. Attribution is the map between them, and it is
the part of this design most able to produce a quietly wrong number, so it is
built to fail loudly instead.

Three resolvers, tried in order, cheapest first:

1. **A recorded binding.** ``SubagentStart`` fires before a delegated actor's
   first tool call and carries both ``agent_id`` and ``agent_type``. If the
   orchestrator declared a pending dispatch, the binding is written then and
   every later call is a dictionary lookup.

2. **The actor's own transcript.** Claude Code writes each subagent's turns to
   ``<transcript>/subagents/agent-<agent_id>.jsonl``, a path derivable from the
   session transcript and the actor id — verified against a live run, not
   assumed. The orchestrator embeds a role marker in the dispatched prompt, and
   the marker is read back from the first user message. This is what makes
   attribution safe under concurrency: it depends on nothing but the call's own
   identifiers, so N simultaneous actors of the same type resolve independently.

3. **The actor kind.** When one agent definition exists per role, ``agent_type``
   names the role outright. Cheapest of all, and ambiguous the moment two
   actors of the same type run at once — so it is tried last, and only when it
   resolves to exactly one *currently dispatched* role.

If none resolves, the call is recorded ``unattributed``. It is never guessed.
An unattributed call establishes nothing about any role's containment, and the
reports treat it as residue that weakens the claim rather than as a data point
to be averaged away.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

try:  # imported as `gate.journal` by hooks, or top-level by some tools
    from .privacy import shorten_home
except ImportError:  # pragma: no cover
    from privacy import shorten_home  # type: ignore[no-redef]

#: The marker an orchestrator embeds in a dispatched prompt so the role survives
#: the trip into a context the window cannot address. Deliberately ugly and
#: specific: it must never collide with prose a model might produce on its own.
ROLE_MARKER = re.compile(r"\[\[scw:role=([A-Za-z0-9_.:-]{1,120})\]\]")

#: How much of a subagent transcript to scan for the marker. The marker is
#: placed in the dispatched prompt, which is the first record, so this only has
#: to cover a large first message rather than the whole conversation.
_SCAN_BYTES = 256_000

_LOCK = threading.Lock()


def state_dir() -> Path:
    """Where the gate keeps its derived state.

    Derived, not authoritative: everything here can be rebuilt from the event
    log. It exists because a hook runs on every tool call and cannot afford to
    replay a log to answer one question.
    """
    root = os.environ.get("MAXEY0_GATE_STATE")
    path = Path(root) if root else Path(os.environ.get("SCW_HOME") or (Path.home() / ".scw")) / "gate"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _bindings_path(session_ref: Optional[str]) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_ref or "nosession")[:120]
    return state_dir() / f"actors-{safe}.json"


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — a corrupt cache is an empty cache
        return {}


def _write_json(path: Path, payload: dict) -> bool:
    """Atomically replace ``path``; True if the write landed.

    Each hook is its own process, so a fixed ``<file>.tmp`` name was shared by
    every concurrent hook: they overwrote each other's temp file and, on
    Windows, os.replace failed with PermissionError while another held the
    target. A unique temp per write, and a short retry on that Windows error,
    removes both. A write that still fails is reported, not swallowed, so a
    lost binding is visible to the caller instead of silently unattributed.
    """
    tmp: Optional[str] = None
    try:
        fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, indent=2))
        for attempt in range(50):
            try:
                os.replace(tmp, path)          # atomic on POSIX and Windows
                return True
            except PermissionError:
                if attempt == 49:
                    raise
                time.sleep(0.01)
    except Exception:  # noqa: BLE001 — losing a cache write must not break a call
        if tmp:
            try:
                os.unlink(tmp)
            except Exception:
                pass
    return False


@contextmanager
def locked(path: Path) -> Iterator[None]:
    """Hold a cross-process lock on ``path`` for one read-modify-write.

    ``_LOCK`` is a thread lock, and every tool call spawns its own hook
    process, so it serialized nothing: twelve parallel Agent dispatches kept
    one pending entry out of twelve. The journal's sidecar lock is the same
    primitive, reused rather than reinvented.
    """
    from .journal import _FileLock

    with _LOCK, _FileLock(path, timeout=5.0):
        yield


# ---------------------------------------------------------------------------
# pending dispatches and recorded bindings
# ---------------------------------------------------------------------------


def declare_dispatch(session_ref: Optional[str], loop_id: str,
                     actor_kind: Optional[str] = None,
                     marker: Optional[str] = None,
                     workdir: Optional[str] = None) -> dict:
    """Record that the orchestrator is about to dispatch ``loop_id``.

    Called from the ``Agent``-tool ``PreToolUse``, where the host has told us a
    delegation is starting but has not yet minted an ``agent_id``.

    ``workdir`` enables the one attribution mechanism that is portable across
    every host surveyed: give each role its own working directory and the
    working directory *becomes* the identity. See :func:`resolve`.
    """
    path = _bindings_path(session_ref)
    with locked(path):
        state = _read_json(path)
        pending = state.setdefault("pending", [])
        pending.append({"loop_id": loop_id, "actor_kind": actor_kind,
                        "marker": marker or loop_id,
                        # Persisted: never the username-bearing absolute path.
                        "workdir": shorten_home(workdir) if workdir else workdir})
        if workdir:
            state.setdefault("workdirs", {})[_norm_dir(workdir)] = loop_id
        persisted = _write_json(path, state)
        return {"pending": len(pending), "loop_id": loop_id, "workdir": workdir,
                "persisted": persisted}


def _norm_dir(path: str) -> str:
    normalized = os.path.normpath(os.path.abspath(os.path.expanduser(path)))
    normalized = normalized.replace("\\", "/").rstrip("/").lower() if os.name == "nt" \
        else normalized.rstrip("/")
    # Persisted as a key, so it must not carry the username. Both the store
    # and the lookup pass through here, so they still compare equal.
    return shorten_home(normalized)


def bind_actor(session_ref: Optional[str], actor_ref: str, loop_id: str,
               how: str) -> bool:
    """Record ``actor_ref`` -> ``loop_id`` so later calls are a lookup.

    Returns whether the binding was persisted.
    """
    path = _bindings_path(session_ref)
    with locked(path):
        state = _read_json(path)
        state.setdefault("bound", {})[actor_ref] = {"loop_id": loop_id, "how": how}
        state["pending"] = [
            entry for entry in state.get("pending", [])
            if entry.get("loop_id") != loop_id
        ]
        return _write_json(path, state)


def _loop_is_running(session_ref: Optional[str]) -> bool:
    """Whether any SCW role has been dispatched in this session.

    The discriminator between residue and ambient activity. If the orchestrator
    never declared a dispatch and no actor was ever bound, then whatever is
    making tool calls is not a partitioned role and no containment claim covers
    it. A session that has dispatched even one role is held to the stricter
    reading: an actor we cannot place is a hole in that run's evidence.
    """
    state = _read_json(_bindings_path(session_ref))
    return bool(state.get("pending")) or bool(state.get("bound"))


def bound_actors(session_ref: Optional[str]) -> dict:
    return _read_json(_bindings_path(session_ref)).get("bound", {})


def clear(session_ref: Optional[str]) -> None:
    _write_json(_bindings_path(session_ref), {})


# ---------------------------------------------------------------------------
# resolution
# ---------------------------------------------------------------------------


def derive_actor_transcript(transcript_ref: Optional[str],
                            actor_ref: Optional[str]) -> Optional[Path]:
    """Where the host writes this actor's own turns.

    Claude Code lays these out as ``<session>.jsonl`` alongside a directory
    ``<session>/subagents/agent-<agent_id>.jsonl``. Confirmed against a live
    run rather than inferred from documentation, which explicitly declines to
    specify the layout.
    """
    if not transcript_ref or not actor_ref:
        return None
    base = Path(transcript_ref)
    candidate = base.parent / base.stem / "subagents" / f"agent-{actor_ref}.jsonl"
    return candidate if candidate.exists() else None


def marker_in_transcript(path: Path) -> Optional[str]:
    """Read the role marker out of an actor's first message."""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            blob = fh.read(_SCAN_BYTES)
    except Exception:  # noqa: BLE001
        return None
    found = ROLE_MARKER.search(blob)
    return found.group(1) if found else None


def resolve_by_cwd(session_ref: Optional[str], cwd: Optional[str]) -> Optional[str]:
    """The role that owns this working directory, if one was declared.

    This is the only attribution mechanism that works on every host surveyed.
    A working directory is present in every one of their pre-tool payloads;
    nothing else identifying is. So giving each dispatched role its own
    directory — a worktree, a bind mount, or just a subdirectory — turns a
    field every host already sends into the role identity, with no host support
    at all.

    It also resolves *before* the call, which the transcript resolver cannot:
    a transcript names the role only once the actor has written to it, so it
    can reconcile a log but it cannot gate one.

    Matching is by containment, so a role that works inside its own directory
    is attributed for everything it touches beneath it. The longest match wins,
    so nesting a child role inside a parent's tree still resolves to the child.
    """
    if not cwd:
        return None
    target = _norm_dir(cwd)
    declared = _read_json(_bindings_path(session_ref)).get("workdirs", {})
    best: Optional[str] = None
    best_len = -1
    for directory, loop_id in declared.items():
        if (target == directory or target.startswith(directory + "/")) \
                and len(directory) > best_len:
            best, best_len = loop_id, len(directory)
    return best


def resolve(
    session_ref: Optional[str],
    actor_ref: Optional[str],
    actor_kind: Optional[str] = None,
    transcript_ref: Optional[str] = None,
    actor_transcript_ref: Optional[str] = None,
    cwd: Optional[str] = None,
) -> tuple[Optional[str], str]:
    """Map an actor to a ``loop_id``.

    Returns ``(loop_id, how)``. ``how`` names the resolver that answered, and is
    recorded with every event so a reader can weigh the attribution: a binding
    recorded at dispatch is stronger evidence than a guess from an actor type,
    and the report should be able to tell them apart.

    Two different "no role" outcomes, and keeping them apart matters:

    ``(None, "ambient")``       no SCW loop is running in this session at all —
                                nothing was ever dispatched as a role. The actor
                                is ordinary host activity, not a partitioned
                                role, so there is no containment claim for it to
                                weaken. Conflating this with residue made every
                                session that ever used a subagent permanently
                                un-claimable.
    ``(None, "unattributed")``  a dispatch WAS declared and this actor could not
                                be tied to it. That is real residue: a role ran
                                and we cannot say which.

    Neither is ever substituted with a plausible role.
    """
    # 1 — a binding already recorded for this actor
    if actor_ref is not None:
        entry = bound_actors(session_ref).get(actor_ref)
        if entry:
            return entry.get("loop_id"), entry.get("how", "bound")

    # 2 — the working directory.
    #
    # Tried BEFORE the actor-id path and before giving up, because it is the
    # only resolver that works on a host which never sends an actor id — which
    # is every host except Claude Code and the Claude Agent SDK. An earlier
    # version returned "host" immediately when `actor_ref` was None and so
    # never reached this branch, silently exempting every call on every other
    # host from every policy.
    #
    # This requires each role to have its OWN directory, distinct from the
    # orchestrator's; a role whose workdir is the project root would capture
    # the host's calls too.
    from_cwd = resolve_by_cwd(session_ref, cwd)
    if from_cwd:
        if actor_ref is not None:
            bind_actor(session_ref, actor_ref, from_cwd, "cwd")
        return from_cwd, "cwd"

    if actor_ref is None:
        # Nothing to look up and nothing declared this directory. On a host
        # that reports actors this is the orchestrator; on one that does not,
        # it is simply unknown. `core.decide` tells them apart using the
        # adapter's declared capability, not a guess made here.
        return None, ("unattributed" if _loop_is_running(session_ref) else "ambient")

    # 3 — the actor's own transcript, which depends on nothing shared
    path = Path(actor_transcript_ref) if actor_transcript_ref else None
    if path is None or not path.exists():
        path = derive_actor_transcript(transcript_ref, actor_ref)
    if path is not None:
        marker = marker_in_transcript(path)
        if marker:
            bind_actor(session_ref, actor_ref, marker, "transcript_marker")
            return marker, "transcript_marker"

    # 4 — the actor kind, only when it is unambiguous among pending dispatches
    if actor_kind:
        state = _read_json(_bindings_path(session_ref))
        matches = [entry for entry in state.get("pending", [])
                   if entry.get("actor_kind") == actor_kind]
        if len(matches) == 1:
            loop_id = matches[0]["loop_id"]
            bind_actor(session_ref, actor_ref, loop_id, "actor_kind")
            return loop_id, "actor_kind"
        if len(matches) > 1:
            # Ambiguous on purpose: two actors of one type are running and
            # nothing distinguishes them. Guessing here would attribute one
            # role's behavior to another, which is worse than not knowing.
            return None, "ambiguous_actor_kind"

    return None, ("unattributed" if _loop_is_running(session_ref) else "ambient")
