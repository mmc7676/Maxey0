"""The portable adapter: normalized ToolEvent in, Decision out, `exit 2` to deny.

This is the adapter for every host that is not Claude Code. It exists because
the architecture's portability claim has to be testable rather than asserted,
and because the survey of what other hosts actually offer produced a short,
firm answer.

Across the eight hook-capable coding agents surveyed — Claude Code, the Claude
Agent SDK, OpenAI Codex CLI, Cursor, Gemini CLI, GitHub Copilot CLI, Cline and
OpenHands — exactly five things are universal:

1. a pre-tool event delivered as JSON on stdin to a subprocess;
2. a payload carrying a session id, a working directory, a tool name and a
   tool-input object (under host-specific field names);
3. denial expressible through stdout JSON and/or **exit code 2**;
4. a human-readable reason returned to the model on denial;
5. a post-tool event.

Everything else differs. In particular **subagent identity on the tool event is
native only on Claude Code and the Agent SDK**; Codex has an open issue for it,
Cursor's is undocumented, Gemini CLI has no subagent lifecycle events at all,
and Copilot's `subagentStart` omits the id. So the protocol cannot depend on it.

`exit 2` is the most portable enforcement primitive that exists here — it means
deny on Claude Code, Codex, Cursor, Cline and OpenHands — so this adapter uses
it, and also emits the JSON decision for hosts that read one.

# Attribution without host support

`cwd` is the only identity-bearing field present in every host's payload. Give
each dispatched role its own working directory and that directory becomes the
role identity, resolved before the call, with no host cooperation at all. See
`gate.attribution.resolve_by_cwd`.

# Honest degradation

A host that cannot block is run in `observe` and **reported as observe-only**.
A host with no interception at all is not "observe-only": it is `off`, and a run
on it records the null and claims no containment. The ladder is declared per run
so a report can never present a level it did not have:

    H3  enforce + native per-actor attribution   Claude Code, Claude Agent SDK
    H2  enforce, attribution manufactured        Codex, Cursor, Gemini CLI,
                                                 Copilot CLI, OpenHands, Cline
    H1  observe only
    H0  no interception; claims nothing          Aider

These are HOST CAPABILITY levels: what the host is able to do. They are not the
isolation levels in `gate.levels` (L0-L3), which describe what a *run* achieved.
The two were once both spelled L0-L3, which was needlessly confusing in a
codebase this careful about saying exactly what is meant. `L*` is still accepted
here as a deprecated alias.

Usage:

    <host hook> | python -m gate.adapters.generic --host codex
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SERVER = Path(__file__).resolve().parents[2]
if str(_SERVER) not in sys.path:
    sys.path.insert(0, str(_SERVER))

from gate import attribution, journal, store  # noqa: E402
from gate.core import classify, decide  # noqa: E402
from gate.protocol import ToolEvent  # noqa: E402

#: Field aliases seen across hosts. Order matters: the first present wins.
ALIASES: dict[str, tuple[str, ...]] = {
    "session": ("session_id", "sessionId", "conversation_id", "conversationId",
                "thread_id"),
    "tool": ("tool_name", "toolName", "tool", "name"),
    "input": ("tool_input", "toolInput", "input", "arguments", "args",
              "parameters"),
    "output": ("tool_response", "toolResponse", "output", "result"),
    "cwd": ("cwd", "working_dir", "workingDir", "workspace_root", "workspaceRoot"),
    "actor": ("agent_id", "agentId", "subagent_id", "subagentId"),
    "actor_kind": ("agent_type", "agentType", "subagent_type", "subagentType"),
    "call": ("tool_use_id", "toolUseId", "call_id", "callId", "id"),
    "event": ("hook_event_name", "hookEventName", "event", "type"),
    "transcript": ("transcript_path", "transcriptPath"),
    "actor_transcript": ("agent_transcript_path", "agentTranscriptPath"),
}

_PHASES = {
    "pre": ("pre", "tool.pre", "pretooluse", "beforetool", "tool_call_before",
            "beforeshellexecution", "beforereadfile", "preToolUse".lower()),
    "post": ("post", "tool.post", "posttooluse", "aftertool", "tool_call_after"),
    "actor_start": ("subagentstart", "actor_start", "agent_start"),
    "actor_stop": ("subagentstop", "actor_stop", "agent_stop"),
}


def _pick(payload: dict, key: str):
    for alias in ALIASES[key]:
        if alias in payload and payload[alias] not in (None, ""):
            return payload[alias]
    return None


def _phase(raw) -> str:
    text = str(raw or "pre").strip().lower().replace("-", "").replace("_", "")
    for phase, names in _PHASES.items():
        if any(text == n.replace("_", "").replace("-", "") for n in names):
            return phase
    return "pre"


def build_event(payload: dict, host: str, level: str = "H2") -> ToolEvent:
    raw_input = _pick(payload, "input")
    output = _pick(payload, "output")
    return ToolEvent(
        # Only H3 hosts put an actor id on the tool event. Declaring that
        # honestly is what stops a missing id from being read as "the host",
        # which would exempt every call on an L2 host from every policy.
        host_reports_actors=(level == "H3"),
        phase=_phase(_pick(payload, "event")),  # type: ignore[arg-type]
        tool=str(_pick(payload, "tool") or ""),
        tool_input=raw_input if isinstance(raw_input, dict) else {"raw": raw_input},
        tool_output=output if isinstance(output, dict) else (
            {"text": output} if output is not None else None),
        host=host,
        session_ref=_pick(payload, "session"),
        actor_ref=_pick(payload, "actor"),
        actor_kind=_pick(payload, "actor_kind"),
        call_ref=_pick(payload, "call"),
        cwd=_pick(payload, "cwd"),
        transcript_ref=_pick(payload, "transcript"),
        actor_transcript_ref=_pick(payload, "actor_transcript"),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Portable Maxey0 gate adapter")
    parser.add_argument("--host", default="generic",
                        help="host name, recorded with every event")
    parser.add_argument("--level", default="H2",
                        choices=["H3", "H2", "H1", "H0", "L3", "L2", "L1", "L0"],
                        help="HOST CAPABILITY: what this host can actually do. "
                             "H3 enforce+native attribution, H2 enforce with "
                             "attribution manufactured, H1 observe only, H0 none. "
                             "Recorded so a report cannot present a capability it "
                             "did not have. L* is a deprecated alias. Distinct from "
                             "the isolation levels in gate.levels.")
    args = parser.parse_args(argv)
    # normalize the deprecated L* spelling onto H*
    args.level = "H" + args.level[1:] if args.level[0] == "L" else args.level

    try:
        raw = sys.stdin.read()
        payload = json.loads(raw.lstrip("﻿")) if raw.strip() else {}
    except Exception as exc:  # noqa: BLE001
        journal.emit("gate.fail_open", {"why": "payload_unparseable",
                                        "detail": str(exc)[:500],
                                        "host": args.host})
        return 0

    try:
        event = build_event(payload, args.host, args.level)
        mode = store.get_mode(event.session_ref)
        # A host that cannot block never runs in enforce, whatever is configured.
        if args.level in ("H1", "H0") and mode == "enforce":
            mode = "observe"

        loop_id, how = attribution.resolve(
            event.session_ref, event.actor_ref, event.actor_kind,
            event.transcript_ref, event.actor_transcript_ref, event.cwd)
        decision = decide(event, store.get(event.session_ref, loop_id),
                          mode=mode, attributed=loop_id is not None)

        journal.emit(
            {"allow": "gate.allowed", "deny": "gate.denied",
             "observe_only": "gate.observed",
             "fail_open": "gate.fail_open"}.get(decision.verdict, "gate.observed"),
            {"tool": event.tool, "kind": classify(event.tool), "host": args.host,
             "level": args.level, "phase": event.phase, "loop_id": loop_id,
             "attribution": how, "attributed": loop_id is not None,
             "verdict": decision.verdict, "reason_code": decision.reason_code,
             "message": decision.message, "hint": decision.hint,
             "mode": mode, "resource": decision.resource,
             "actor_ref": event.actor_ref, "cwd": event.cwd},
            actor=f"loop:{loop_id}" if loop_id else "host",
        )

        json.dump(decision.to_dict(), sys.stdout)
        # exit 2 is the portable deny. Hosts that read the JSON get the reason;
        # hosts that only read the exit code still refuse.
        return 2 if decision.blocks else 0
    except Exception as exc:  # noqa: BLE001 - never break the host
        journal.emit("gate.fail_open", {"why": "gate_exception",
                                        "detail": f"{type(exc).__name__}: {exc}"[:500],
                                        "host": args.host,
                                        "note": "the gate could not evaluate this call "
                                                "and allowed it; residue, not containment"})
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
