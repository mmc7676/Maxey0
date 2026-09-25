"""The Gate Protocol — a host-agnostic contract for intercepting a tool call.

The gate exists because of a measured gap. Through v0.5.0 the SCW runtime
recorded only what the *host orchestrator* did: bind a scope, create a region,
render scope-true material, write a response back, tick. Every action the
*agent* took — 63 `Read`s, 39 `Bash` commands, 6 `Grep`s in the transcripts on
the machine this was written on — happened inside a Claude Code subagent and
left no trace in the window. See docs/ARCHITECTURE.md for the counts.

A tool call is the one moment an agent running in a sealed subagent context has
to ask the host for something. That is the only place an outside observer can
stand. This module defines what happens there, in terms no particular host owns.

Three types carry the whole contract:

``ToolEvent``   what happened, normalized away from any host's payload shape
``Policy``      what the bound role was declared to be allowed
``Decision``    allow or refuse, and — always — why

The split matters for portability. :mod:`server.gate.core` consumes these three
and imports nothing host-specific, so a host adapter's entire job is to build a
``ToolEvent`` and translate a ``Decision`` back. A host that can block gets
enforcement; a host that can only watch gets ``observe`` and is *reported as*
observe-only. Neither is allowed to masquerade as the other, because a
containment number that cannot say which one produced it is not a measurement.
"""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass, field
from pathlib import PurePath
from typing import Any, Literal, Optional

#: Bumped when the wire shape of ToolEvent/Decision changes incompatibly. An
#: adapter records the version it spoke so a replayed run can be read with the
#: right expectations rather than the current ones.
PROTOCOL_VERSION = "1.0"

GateMode = Literal["enforce", "observe", "off"]

#: `observe` is not a weaker `enforce`. It is the only way to measure how often
#: an agent *attempts* to leave its partition, which is a property of the
#: formation rather than of the enforcement — and it is the experiment's most
#: informative cell. `off` exists so a control condition can be run without the
#: gate's own overhead appearing in the numbers.
GATE_MODES: tuple[GateMode, ...] = ("enforce", "observe", "off")

Verdict = Literal["allow", "deny", "observe_only", "fail_open"]

#: Why a call was allowed or refused. Kept as a closed vocabulary so a report
#: can group outcomes without parsing prose.
REASONS: dict[str, str] = {
    "in_scope": "the call stayed inside the role's declared scope",
    "no_policy": "no policy is declared for this actor",
    "unattributed": "the call could not be attributed to a bound role",
    "host_actor": "the call came from the unbound host, not a bound role",
    "path_outside_scope": "the path is outside the role's declared filesystem scope",
    "tool_not_granted": "the role was not granted this tool",
    "command_not_granted": "the shell command is not permitted by the role's policy",
    "region_outside_closure": "the region is outside the role's read/write closure",
    "gate_error": "the gate could not evaluate this call",
    "mode_observe": "the gate is in observe mode and blocks nothing",
    "mode_off": "the gate is off",
}


# ---------------------------------------------------------------------------
# what happened
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolEvent:
    """One tool call, normalized.

    ``actor_ref`` is the *host's* identifier for whoever made the call — for
    Claude Code that is ``agent_id``, absent for the main loop. It is
    deliberately not the SCW ``loop_id``: mapping one to the other is
    attribution, it can fail, and a type that conflated them would make failure
    unrepresentable.
    """

    phase: Literal["pre", "post", "actor_start", "actor_stop"]
    tool: str
    tool_input: dict[str, Any] = field(default_factory=dict)
    tool_output: Optional[dict[str, Any]] = None

    # host identity
    host: str = "unknown"
    session_ref: Optional[str] = None
    actor_ref: Optional[str] = None          # None => the unbound host itself
    actor_kind: Optional[str] = None         # the host's name for the actor type
    call_ref: Optional[str] = None           # correlates pre with post
    turn_ref: Optional[str] = None
    cwd: Optional[str] = None
    transcript_ref: Optional[str] = None
    actor_transcript_ref: Optional[str] = None

    duration_ms: Optional[float] = None
    protocol_version: str = PROTOCOL_VERSION

    #: Whether this host puts an actor id on the tool event at all. True for
    #: Claude Code and the Claude Agent SDK, which populate ``agent_id`` for
    #: subagent calls and omit it for the main loop. **False for every other
    #: host surveyed** — Codex, Cursor, Gemini CLI, Copilot CLI, Cline and
    #: OpenHands all send tool events with no actor identity whatsoever.
    #:
    #: The flag exists so a missing ``actor_ref`` can be read correctly. Where
    #: the host does report actors, absence means "this was the host". Where it
    #: does not, absence means nothing at all, and treating it as "the host"
    #: would exempt every call on those hosts from every policy.
    host_reports_actors: bool = True

    @property
    def from_subagent(self) -> Optional[bool]:
        """Whether this call originated inside a delegated actor.

        Three-valued, for the same reason everything else here is: on a host
        that does not report actor identity, this is simply not knowable from
        the event, and ``None`` says so rather than guessing "no".
        """
        if self.actor_ref is not None:
            return True
        return False if self.host_reports_actors else None

    def to_dict(self) -> dict:
        return {
            "phase": self.phase,
            "tool": self.tool,
            "tool_input": self.tool_input,
            "tool_output": self.tool_output,
            "host": self.host,
            "session_ref": self.session_ref,
            "actor_ref": self.actor_ref,
            "actor_kind": self.actor_kind,
            "call_ref": self.call_ref,
            "turn_ref": self.turn_ref,
            "cwd": self.cwd,
            "duration_ms": self.duration_ms,
            "protocol_version": self.protocol_version,
        }


# ---------------------------------------------------------------------------
# what was declared
# ---------------------------------------------------------------------------


@dataclass
class Policy:
    """What one bound role is allowed to do outside the window.

    The SCW model knows *regions*. It has never known anything about the
    filesystem, which is exactly why a role bound to a 2 048-token scratchpad
    could read the whole disk and no measurement noticed. This type is the
    missing declaration, and it is host-authored: a role cannot widen its own
    policy, for the same reason ``Loop.exposes`` is host-authored — a party that
    can widen its own scope satisfies any containment rule vacuously.

    ``read_paths`` / ``write_paths`` are glob patterns matched against resolved
    absolute paths. An empty ``read_paths`` means *no filesystem read is in
    scope*, which is the correct default for a role that is supposed to work
    only from rendered material. It is not the same as ``None``, which means no
    policy was declared at all and the gate has nothing to check against.
    """

    loop_id: str
    read_paths: tuple[str, ...] = ()
    write_paths: tuple[str, ...] = ()
    tools: Optional[tuple[str, ...]] = None      # None => every tool permitted
    denied_tools: tuple[str, ...] = ()
    bash_allow: tuple[str, ...] = ()             # glob patterns over the command
    regions_read: tuple[str, ...] = ()           # mirror of the SCW read closure
    regions_write: tuple[str, ...] = ()
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "loop_id": self.loop_id,
            "read_paths": list(self.read_paths),
            "write_paths": list(self.write_paths),
            "tools": list(self.tools) if self.tools is not None else None,
            "denied_tools": list(self.denied_tools),
            "bash_allow": list(self.bash_allow),
            "regions_read": list(self.regions_read),
            "regions_write": list(self.regions_write),
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "Policy":
        tools = raw.get("tools")
        return cls(
            loop_id=raw["loop_id"],
            read_paths=tuple(raw.get("read_paths") or ()),
            write_paths=tuple(raw.get("write_paths") or ()),
            tools=tuple(tools) if tools is not None else None,
            denied_tools=tuple(raw.get("denied_tools") or ()),
            bash_allow=tuple(raw.get("bash_allow") or ()),
            regions_read=tuple(raw.get("regions_read") or ()),
            regions_write=tuple(raw.get("regions_write") or ()),
            note=raw.get("note", ""),
        )


# ---------------------------------------------------------------------------
# what the gate decided
# ---------------------------------------------------------------------------


@dataclass
class Decision:
    """Allow or refuse, with the reason attached — always.

    ``fail_open`` is a distinct verdict rather than an ``allow`` with a flag,
    because the difference is the whole point of this version. An ``allow``
    means the gate evaluated the call and found it in scope. A ``fail_open``
    means the gate could not evaluate it and let it through anyway. Collapsing
    the two would manufacture containment out of a malfunction — precisely the
    error the gate exists to correct.

    ``attributed`` likewise: a decision about a call the gate could not tie to a
    role establishes nothing about that role, and any containment figure
    computed over such calls has to carry them as residue rather than average
    them away.
    """

    verdict: Verdict
    reason_code: str
    message: str = ""
    hint: str = ""
    loop_id: Optional[str] = None
    attributed: bool = False
    mode: GateMode = "observe"
    resource: Optional[str] = None
    protocol_version: str = PROTOCOL_VERSION

    @property
    def blocks(self) -> bool:
        return self.verdict == "deny"

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "reason_code": self.reason_code,
            "message": self.message,
            "hint": self.hint,
            "loop_id": self.loop_id,
            "attributed": self.attributed,
            "mode": self.mode,
            "resource": self.resource,
            "protocol_version": self.protocol_version,
        }


# ---------------------------------------------------------------------------
# path matching
# ---------------------------------------------------------------------------


def normalize_path(raw: str, cwd: Optional[str] = None) -> str:
    """Resolve a path the way a policy check has to see it.

    Relative paths resolve against ``cwd``; ``~`` expands; the result is
    absolutized and case-folded on Windows. Symlinks are deliberately **not**
    resolved: ``os.path.realpath`` would touch the filesystem on every tool
    call, and the gate has a latency budget measured in milliseconds. That is a
    real limitation with a real consequence — a symlink pointing out of scope
    defeats a path check — and it is recorded here rather than left for someone
    to discover.
    """
    if not raw:
        return ""
    expanded = os.path.expanduser(str(raw))
    if cwd and not os.path.isabs(expanded):
        expanded = os.path.join(cwd, expanded)
    normalized = os.path.normpath(os.path.abspath(expanded))
    return normalized.replace("\\", "/").lower() if os.name == "nt" else normalized


def path_matches(path: str, patterns: tuple[str, ...], cwd: Optional[str] = None) -> bool:
    """Whether ``path`` falls under any glob in ``patterns``.

    A pattern naming a directory matches everything beneath it, so a policy can
    say ``/repo/docs`` and mean the subtree without spelling out ``/**``.
    """
    if not patterns:
        return False
    target = normalize_path(path, cwd)
    if not target:
        return False
    for pattern in patterns:
        candidate = normalize_path(pattern, cwd)
        if not candidate:
            continue
        if fnmatch.fnmatch(target, candidate):
            return True
        # directory prefix: /repo/docs covers /repo/docs/a/b.md
        if target.startswith(candidate.rstrip("/") + "/"):
            return True
        if fnmatch.fnmatch(target, candidate.rstrip("/") + "/*"):
            return True
        try:
            if PurePath(target).match(candidate):
                return True
        except ValueError:  # malformed pattern is not a match, not a crash
            continue
    return False


#: Shell syntax that joins, substitutes or redirects commands. fnmatch's `*`
#: matches all of these, so without this check `git status*` also permitted
#: `git status; type .env` -- a narrow grant silently became a whole shell.
SHELL_CONTROL: tuple[str, ...] = (";", "&", "|", "`", "$(", ">", "<", "\n", "\r")


def command_matches(command: str, patterns: tuple[str, ...]) -> bool:
    """Whether a shell command is permitted by any glob in ``patterns``.

    A pattern describes one simple command. A command containing chaining,
    piping, substitution or redirection matches only a pattern that spells
    that same syntax out literally, so the operator has to have meant it.
    """
    if not patterns:
        return False
    stripped = (command or "").strip()
    present = [tok for tok in SHELL_CONTROL if tok in stripped]
    return any(
        fnmatch.fnmatch(stripped, pattern)
        and all(tok in pattern for tok in present)
        for pattern in patterns
    )
