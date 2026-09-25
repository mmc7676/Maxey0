"""Where declared gate policy lives, and how the hot path reads it.

A policy is *declared* by the host through an MCP tool, which is the auditable
act: it writes a `gate.policy` record so the declaration is evidence rather than
a claim. This module holds the derived cache that declaration produces, because
a hook runs on every tool call and cannot replay a log to answer one question.

Derived, never authoritative. Everything here can be rebuilt from the journal,
and if the cache is missing the gate reports `no_policy` — which is an honest
"this role's reach is unmeasured", not a silent allow.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional

from .attribution import _write_json, locked, state_dir
from .protocol import GATE_MODES, GateMode, Policy

DEFAULT_MODE: GateMode = "observe"


def _policy_path(session_ref: Optional[str]) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_ref or "nosession")[:120]
    return state_dir() / f"policy-{safe}.json"


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _write(path: Path, payload: dict) -> bool:
    # Same unique-temp atomic write as the bindings file; a shared `.tmp` name
    # raced between concurrent hook processes. See attribution._write_json.
    return _write_json(path, payload)


def set_mode(session_ref: Optional[str], mode: GateMode) -> dict:
    if mode not in GATE_MODES:
        raise ValueError(f"mode must be one of {GATE_MODES}")
    path = _policy_path(session_ref)
    # Cross-process: set_mode and declare both rewrite the same file, and two
    # hooks or tools doing so at once dropped whichever wrote first.
    with locked(path):
        state = _read(path)
        state["mode"] = mode
        persisted = _write(path, state)
    return {"mode": mode, "session_ref": session_ref, "persisted": persisted}


def get_mode(session_ref: Optional[str]) -> GateMode:
    """The gate's mode for this session.

    Resolution order, and the fallback to the default file is load-bearing:

    1. ``MAXEY0_GATE_MODE`` — the environment wins, so an experiment condition
       can pin a mode for a whole run without depending on the agent under test
       having declared anything.
    2. the mode stored for *this* session id.
    3. the mode stored with no session id at all.
    4. ``observe``.

    Step 3 exists because of a failure observed in practice. A session id is
    minted by the host when the session starts, so an operator configuring the
    gate beforehand has no session to key on and necessarily writes the
    no-session file. Without this fallback that declaration was silently
    ignored: the hook looked up the real session id, found nothing, and ran in
    `observe` — so a gate configured to enforce quietly enforced nothing, which
    is the worst possible failure for a component whose entire job is to be
    trustworthy about what it stopped.
    """
    override = os.environ.get("MAXEY0_GATE_MODE")
    if override in GATE_MODES:
        return override  # type: ignore[return-value]
    stored = _read(_policy_path(session_ref)).get("mode")
    if stored in GATE_MODES:
        return stored  # type: ignore[return-value]
    if session_ref is not None:
        default = _read(_policy_path(None)).get("mode")
        if default in GATE_MODES:
            return default  # type: ignore[return-value]
    return DEFAULT_MODE


def declare(session_ref: Optional[str], policy: Policy) -> dict:
    path = _policy_path(session_ref)
    with locked(path):
        state = _read(path)
        state.setdefault("roles", {})[policy.loop_id] = policy.to_dict()
        _write(path, state)
    return policy.to_dict()


def _pinned() -> dict:
    """A policy set pinned for a whole run, independent of session id.

    An experiment condition has to fix a role's scope before the run starts,
    and a session id does not exist until Claude Code mints one. `MAXEY0_GATE_POLICY`
    names a JSON file of the same shape as the per-session cache, and it is
    consulted only when the session cache has nothing for the role — so a
    session-specific declaration always wins over a run-wide default, and the
    default can never silently widen a role that declared its own scope.
    """
    path = os.environ.get("MAXEY0_GATE_POLICY")
    if not path:
        return {}
    return _read(Path(path))


def get(session_ref: Optional[str], loop_id: Optional[str]) -> Optional[Policy]:
    """The policy governing ``loop_id``, most specific declaration first.

    1. declared for *this* session id
    2. pinned for the run via ``MAXEY0_GATE_POLICY``
    3. declared with no session id at all

    Step 3 mirrors :func:`get_mode`: an operator configuring the gate before a
    session exists has no session id to key on, and without this fallback the
    declaration was silently ignored and every call reported ``no_policy``.
    A more specific declaration always wins, so the default can never widen a
    role that declared its own scope for this session.
    """
    if not loop_id:
        return None
    raw = _read(_policy_path(session_ref)).get("roles", {}).get(loop_id)
    if not raw:
        raw = _pinned().get("roles", {}).get(loop_id)
    if not raw and session_ref is not None:
        raw = _read(_policy_path(None)).get("roles", {}).get(loop_id)
    if not raw:
        return None
    try:
        return Policy.from_dict(raw)
    except Exception:  # noqa: BLE001 - a malformed policy is no policy
        return None


def all_policies(session_ref: Optional[str]) -> dict:
    state = _read(_policy_path(session_ref))
    return {"mode": get_mode(session_ref), "roles": state.get("roles", {})}


def clear(session_ref: Optional[str]) -> None:
    _write(_policy_path(session_ref), {})
