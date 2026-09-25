"""The Claude Code adapter: a hook process, once per tool call.

Registered by `hooks/hooks.json` on `PreToolUse`, `PostToolUse`, `SubagentStart`
and `SubagentStop`. Its whole job is to turn Claude Code's hook payload into a
:class:`~server.gate.protocol.ToolEvent`, ask :func:`server.gate.core.decide`,
record the outcome, and translate the decision back.

The payload shape below was captured from a live run rather than taken from
documentation, which explicitly declines to specify it. What arrives on stdin:

    session_id, prompt_id, transcript_path, cwd, permission_mode,
    hook_event_name, tool_name, tool_input, tool_use_id
    agent_id, agent_type          <- present ONLY for calls inside a subagent
    tool_response, duration_ms    <- PostToolUse
    agent_transcript_path,
    last_assistant_message        <- SubagentStop

and the observed ordering around a delegation is:

    PreToolUse(tool_name="Agent")   no agent_id, tool_input has prompt+subagent_type
    SubagentStart                   agent_id + agent_type   <- the binding moment
    PreToolUse(...)  x N            agent_id present        <- inside the subagent
    PostToolUse(...) x N
    SubagentStop                    agent_transcript_path
    PostToolUse(tool_name="Agent")

# The one rule this file must not break

**The gate never returns `permissionDecision: "allow"`.**

Returning `allow` would *skip the user's own permission prompt*, so a component
installed to restrict an agent would end up granting it access the user never
approved. The gate is a restrictor, never a granter. It returns `deny` when a
call is out of scope and stays silent otherwise, letting the host's normal
permission rules apply untouched. An in-scope call is recorded as allowed in the
journal; that is a statement about the gate's own check, not a grant.

# The second rule

A broken gate must never break a session, and a gate that fails open must say
so. Every exit path here is exit code 0. When the gate cannot evaluate a call it
writes a `gate.fail_open` record and lets the call through — visibly, so the
containment figure computed later carries it as residue instead of counting it
as contained.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

# The plugin is not installed as a package, so the hook has to find its own
# siblings. `server/` is two levels up from `server/gate/adapters/`.
_SERVER = Path(__file__).resolve().parents[2]
if str(_SERVER) not in sys.path:
    sys.path.insert(0, str(_SERVER))

from gate import attribution, journal, store  # noqa: E402
from gate.core import classify, decide  # noqa: E402
from gate.protocol import ToolEvent  # noqa: E402

HOST = "claude_code"

_PHASE = {
    "PreToolUse": "pre",
    "PostToolUse": "post",
    "SubagentStart": "actor_start",
    "SubagentStop": "actor_stop",
}

#: Cap on what we copy out of a tool payload into the journal. The journal is
#: evidence about *access*, not a second copy of the content accessed — and the
#: runtime log already showed what unbounded payloads do to a line-oriented file
#: (records over 8 KB, which is where torn writes begin).
_MAX_FIELD = 2_000


def _clip(value: Any) -> Any:
    if isinstance(value, str):
        return value[:_MAX_FIELD] + ("..." if len(value) > _MAX_FIELD else "")
    if isinstance(value, dict):
        return {k: _clip(v) for k, v in list(value.items())[:40]}
    if isinstance(value, list):
        return [_clip(v) for v in value[:20]]
    return value


def build_event(payload: dict) -> ToolEvent:
    phase = _PHASE.get(payload.get("hook_event_name", ""), "pre")
    response = payload.get("tool_response")
    return ToolEvent(
        phase=phase,  # type: ignore[arg-type]
        tool=payload.get("tool_name") or payload.get("hook_event_name", ""),
        tool_input=payload.get("tool_input") or {},
        tool_output=_clip(response) if isinstance(response, dict) else (
            {"text": _clip(response)} if response is not None else None),
        host=HOST,
        session_ref=payload.get("session_id"),
        actor_ref=payload.get("agent_id"),
        actor_kind=payload.get("agent_type"),
        call_ref=payload.get("tool_use_id"),
        turn_ref=payload.get("prompt_id"),
        cwd=payload.get("cwd"),
        transcript_ref=payload.get("transcript_path"),
        actor_transcript_ref=payload.get("agent_transcript_path"),
        duration_ms=payload.get("duration_ms"),
    )


def _record(event_type: str, event: ToolEvent, extra: dict) -> dict:
    body = {
        "tool": event.tool,
        "kind": classify(event.tool),
        "phase": event.phase,
        "host": event.host,
        "session_ref": event.session_ref,
        "actor_ref": event.actor_ref,
        "actor_kind": event.actor_kind,
        "call_ref": event.call_ref,
        "turn_ref": event.turn_ref,
        "cwd": event.cwd,
        "tool_input": _clip(event.tool_input),
        **extra,
    }
    if event.duration_ms is not None:
        body["duration_ms"] = event.duration_ms
    actor = f"loop:{extra.get('loop_id')}" if extra.get("loop_id") else "host"
    return journal.emit(event_type, body, actor=actor)


def handle_delegation(event: ToolEvent) -> None:
    """A main-loop `Agent` call: the orchestrator is dispatching a role.

    The role marker is read out of the prompt the orchestrator wrote. If there
    is none, nothing is declared — and the subagent's calls will resolve to
    `unattributed`, which is the correct outcome for a dispatch that never said
    who it was dispatching.
    """
    prompt = str((event.tool_input or {}).get("prompt") or "")
    description = str((event.tool_input or {}).get("description") or "")
    found = attribution.ROLE_MARKER.search(prompt) or attribution.ROLE_MARKER.search(description)
    if not found:
        return
    loop_id = found.group(1)
    declared = attribution.declare_dispatch(
        event.session_ref, loop_id,
        actor_kind=str((event.tool_input or {}).get("subagent_type") or "") or None,
        marker=loop_id,
    )
    if not declared.get("persisted", True):
        # A dispatch that did not reach the bindings file leaves its subagent
        # unattributed. Say so on the chain rather than lose it silently.
        journal.emit("gate.error", {"why": "dispatch_not_persisted", "loop_id": loop_id,
                                    "session_ref": event.session_ref})
    _record("gate.attempt", event, {"loop_id": loop_id, "dispatch": True,
                                    "note": "orchestrator declared a dispatch"})


def run(payload: dict) -> dict:
    """Evaluate one hook invocation. Returns the JSON the host should receive."""
    event = build_event(payload)
    mode = store.get_mode(event.session_ref)

    # --- lifecycle -------------------------------------------------------
    if event.phase == "actor_start":
        loop_id, how = attribution.resolve(
            event.session_ref, event.actor_ref, event.actor_kind,
            event.transcript_ref, event.actor_transcript_ref, event.cwd)
        if loop_id and not attribution.bind_actor(
                event.session_ref, event.actor_ref or "", loop_id, how):
            journal.emit("gate.error", {"why": "binding_not_persisted", "loop_id": loop_id,
                                        "session_ref": event.session_ref})
        _record("gate.actor_start", event, {"loop_id": loop_id, "attribution": how})
        return {}

    if event.phase == "actor_stop":
        loop_id, how = attribution.resolve(
            event.session_ref, event.actor_ref, event.actor_kind,
            event.transcript_ref, event.actor_transcript_ref, event.cwd)
        _record("gate.actor_stop", event, {"loop_id": loop_id, "attribution": how})
        return {}

    # --- the orchestrator dispatching a role -----------------------------
    if not event.from_subagent and classify(event.tool) == "delegation" and event.phase == "pre":
        handle_delegation(event)
        return {}

    # --- everything else --------------------------------------------------
    # cwd is passed here as the lifecycle calls and generic.py already do.
    # Without it resolve_by_cwd always saw None on tool calls, so a role given
    # its own working directory was never attributed by it.
    loop_id, how = attribution.resolve(
        event.session_ref, event.actor_ref, event.actor_kind,
        event.transcript_ref, event.actor_transcript_ref, event.cwd)
    attributed = loop_id is not None
    policy = store.get(event.session_ref, loop_id)
    decision = decide(event, policy, mode=mode, attributed=attributed)
    # An actor in a session where no role was ever dispatched is ambient host
    # activity, not residue. Recording it as `unattributed` made ordinary
    # subagent use permanently invalidate every containment figure.
    if not attributed and how == "ambient" and decision.reason_code == "unattributed":
        decision.reason_code = "ambient_actor"
        decision.message = ("no SCW role was dispatched in this session, so this "
                            "actor is not a partitioned role")
        decision.hint = ""

    event_type = {
        "allow": "gate.allowed",
        "deny": "gate.denied",
        "observe_only": "gate.observed",
        "fail_open": "gate.fail_open",
    }.get(decision.verdict, "gate.observed")

    written = _record(event_type, event, {
        "loop_id": loop_id,
        "attribution": how,
        "attributed": attributed,
        "verdict": decision.verdict,
        "reason_code": decision.reason_code,
        "message": decision.message,
        "hint": decision.hint,
        "mode": mode,
        "resource": decision.resource,
    })

    # A record the gate believed it wrote and did not is worse than none, so a
    # failed persist downgrades the outcome rather than being swallowed.
    if not written.get("persisted"):
        journal.emit("gate.error", {"why": "journal_write_failed",
                                    "error": written.get("write_error"),
                                    "tool": event.tool,
                                    "loop_id": loop_id})

    if decision.blocks and event.phase == "pre":
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f"[Maxey0 gate] {decision.message}"
                    + (f"\nHint: {decision.hint}" if decision.hint else "")
                ),
            }
        }

    # Silence otherwise. Never `allow`: see the module docstring.
    return {}


def main() -> int:
    try:
        raw = sys.stdin.read()
    except Exception:  # noqa: BLE001
        return 0
    if not raw.strip():
        return 0
    # A BOM on stdin is a real thing on Windows and json.loads will not eat it.
    try:
        payload = json.loads(raw.lstrip("﻿"))
    except Exception as exc:  # noqa: BLE001
        _fail_open("payload_unparseable", str(exc))
        return 0

    try:
        output = run(payload)
    except Exception as exc:  # noqa: BLE001 - a gate must never break a session
        _fail_open("gate_exception", f"{type(exc).__name__}: {exc}",
                   tool=payload.get("tool_name"),
                   actor_ref=payload.get("agent_id"))
        return 0

    if output:
        json.dump(output, sys.stdout)
    return 0


def _fail_open(why: str, detail: str, tool: Optional[str] = None,
               actor_ref: Optional[str] = None) -> None:
    """Let the call through, and make the fact that we did so evidence.

    This is the resolution of the tension between "never break a session" and
    "never fabricate containment": the call proceeds, and the run's own record
    says the gate did not evaluate it.
    """
    try:
        journal.emit("gate.fail_open", {
            "why": why, "detail": detail[:1000], "tool": tool,
            "actor_ref": actor_ref,
            "note": "the gate could not evaluate this call and allowed it; it is "
                    "residue and must not be counted as contained",
        })
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":
    raise SystemExit(main())
