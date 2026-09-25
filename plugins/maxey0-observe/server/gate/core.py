"""The decision itself — host-agnostic, pure, and cheap.

:func:`decide` takes a normalized :class:`~server.gate.protocol.ToolEvent`, the
:class:`~server.gate.protocol.Policy` of whatever role it was attributed to, and
the gate mode, and returns a :class:`~server.gate.protocol.Decision`. It imports
nothing from any host, touches no filesystem, opens no socket, and holds no
state, so it is testable by construction and portable by default.

Two rules govern everything here, and they are in tension on purpose.

**A broken gate must never break a session.** A malformed event, an unknown
tool, a policy that will not parse — none of these may stop an agent from
working.

**A gate that fails open must say so.** Letting a call through because the gate
could not evaluate it is *not* the same as letting it through because it was in
scope, and the returned verdict distinguishes them (``fail_open`` vs ``allow``).
Any containment figure computed over a window containing fail-opens carries them
as residue. This is the same discipline the runtime already applies to
three-valued ``contained``: an absence of evidence is never reported as evidence.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from .protocol import (
    Decision,
    GateMode,
    Policy,
    ToolEvent,
    command_matches,
    normalize_path,
    path_matches,
)

#: Which argument of which tool names the thing being reached. Keyed by tool
#: name; the value is the ordered list of `tool_input` keys to try. A tool
#: absent from this map is not silently allowed — it is classified as `opaque`
#: and handled explicitly below, because "we do not know what this tool
#: touches" is a fact worth recording rather than a reason to wave it through.
#: Keys that name a path, in the order they should be tried. Used both by the
#: per-tool maps and by the fallback scan for tools this map has never heard of.
PATH_KEYS: tuple[str, ...] = (
    "file_path", "filePath", "notebook_path", "notebookPath", "path",
    "filename", "file", "target_file", "targetFile", "abs_path", "absPath",
    "directory", "dir",
)

FILE_READ_TOOLS: dict[str, tuple[str, ...]] = {
    # Claude Code
    "Read": ("file_path",), "NotebookRead": ("notebook_path", "file_path"),
    "Glob": ("path",), "Grep": ("path",), "LS": ("path",),
    # other hosts: names differ, the reach does not. A gate that only knew one
    # host's vocabulary would classify every other host's file read as `opaque`
    # and wave it through.
    "read_file": PATH_KEYS, "readFile": PATH_KEYS, "read": PATH_KEYS,
    "view_file": PATH_KEYS, "list_dir": PATH_KEYS, "list_directory": PATH_KEYS,
    "glob_file_search": PATH_KEYS, "grep_search": PATH_KEYS,
    "codebase_search": PATH_KEYS, "file_search": PATH_KEYS,
    "str_replace_editor": PATH_KEYS,
}

FILE_WRITE_TOOLS: dict[str, tuple[str, ...]] = {
    "Write": ("file_path",), "Edit": ("file_path",), "MultiEdit": ("file_path",),
    "NotebookEdit": ("notebook_path", "file_path"),
    "write_file": PATH_KEYS, "writeFile": PATH_KEYS, "write": PATH_KEYS,
    "edit_file": PATH_KEYS, "apply_patch": PATH_KEYS, "create_file": PATH_KEYS,
    "search_replace": PATH_KEYS, "delete_file": PATH_KEYS,
}

SHELL_TOOLS: tuple[str, ...] = (
    "Bash", "PowerShell", "Shell",
    "shell", "run_terminal_cmd", "execute_bash", "run_command", "terminal",
    "exec_command", "local_shell",
)

#: Tools that leave the machine. A role working from rendered material has no
#: business reaching the network, and when one does it is the single most
#: informative thing the gate can record: material entering the partition from
#: outside it is exactly what the partition was supposed to control.
EGRESS_TOOLS: tuple[str, ...] = ("WebFetch", "WebSearch", "ToolSearch")

#: Delegation. A bound role spawning its own subagent creates a control-flow
#: child the window does not know about, which is the R2 failure the
#: disjointness proof already refuses for judges. Recorded, always.
DELEGATION_TOOLS: tuple[str, ...] = ("Agent", "Task")


def classify(tool: str) -> str:
    """What kind of reach a tool has. Used for grouping, not for deciding."""
    if tool in FILE_READ_TOOLS:
        return "file_read"
    if tool in FILE_WRITE_TOOLS:
        return "file_write"
    if tool in SHELL_TOOLS:
        return "shell"
    if tool in EGRESS_TOOLS:
        return "egress"
    if tool in DELEGATION_TOOLS:
        return "delegation"
    if tool.startswith("mcp__"):
        return "mcp"
    return "opaque"


#: File tools that search a tree rather than open one file. Their path
#: argument is optional and, when absent, the host searches the working
#: directory. Treating "no path" as "names nothing" let `Grep{pattern: KEY}`
#: sweep the whole repo from a role confined to docs/, reported as fail_open.
SEARCH_TOOLS: frozenset[str] = frozenset({
    "Glob", "Grep", "LS", "list_dir", "list_directory", "glob_file_search",
    "grep_search", "codebase_search", "file_search",
})

_GLOB_CHARS = ("*", "?", "[")


def _glob_prefix(pattern: str) -> str:
    """The literal leading directories of a glob, before its first wildcard."""
    parts = pattern.replace("\\", "/").split("/")
    literal: list[str] = []
    for part in parts:
        if any(ch in part for ch in _GLOB_CHARS):
            break
        literal.append(part)
    if len(literal) == len(parts):  # no wildcard: the last part may be a file
        literal = literal[:-1] or literal
    prefix = "/".join(literal)
    # "/**/x" keeps its root; a bare drive "C:" needs its separator back.
    if pattern.startswith("/") and not prefix:
        return "/"
    return prefix + "/" if prefix.endswith(":") else prefix


def _first_present(data: dict[str, Any], keys: tuple[str, ...]) -> Optional[str]:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def resource_of(event: ToolEvent) -> Optional[str]:
    """The thing this call reaches, as a string, or None if it names nothing.

    File tools fall back to the full ``PATH_KEYS`` set after their own declared
    keys. Without that, a host sending a known tool under a variant argument
    name (``filePath`` rather than ``file_path``) produced no resource, skipped
    the path check entirely, and fell through to the blanket allow — so the
    same read was refused or permitted depending only on the host's spelling,
    and the permitted one was recorded as `in_scope`.
    """
    kind = classify(event.tool)
    data = event.tool_input or {}
    if kind == "file_read":
        found = (_first_present(data, FILE_READ_TOOLS[event.tool])
                 or _first_present(data, PATH_KEYS))
        if not found and event.tool in SEARCH_TOOLS:
            # No path means "search where I stand", so that is what is reached.
            return event.cwd or None
        return found
    if kind == "file_write":
        return (_first_present(data, FILE_WRITE_TOOLS[event.tool])
                or _first_present(data, PATH_KEYS))
    if kind == "shell":
        return _first_present(data, ("command", "script"))
    if kind == "egress":
        return _first_present(data, ("url", "query", "prompt"))
    if kind == "delegation":
        return _first_present(data, ("subagent_type", "description"))
    if kind == "mcp":
        return _first_present(data, ("scw_id", "loop_id", "region", "path"))
    return None


def decide(
    event: ToolEvent,
    policy: Optional[Policy],
    mode: GateMode = "observe",
    attributed: bool = False,
) -> Decision:
    """Allow or refuse one tool call.

    ``attributed`` is passed in rather than inferred, because attribution is the
    adapter's job and its *failure* has to reach this function intact. A call the
    gate could not tie to a role is never denied — refusing on a guess would be
    worse than the hole it was trying to close — but it is never counted as
    contained either.
    """
    kind = classify(event.tool)
    resource = resource_of(event)

    def result(verdict: str, code: str, message: str = "", hint: str = "") -> Decision:
        return Decision(
            verdict=verdict,  # type: ignore[arg-type]
            reason_code=code,
            message=message,
            hint=hint,
            loop_id=policy.loop_id if policy else None,
            attributed=attributed,
            mode=mode,
            resource=resource,
        )

    if mode == "off":
        return result("observe_only", "mode_off",
                      "the gate is off; this call was neither checked nor recorded as checked")

    # What makes a call governable is that attribution resolved it to a bound
    # role -- NOT that the host announced a subagent.
    #
    # This distinction is load-bearing for portability and was got wrong once.
    # `actor_ref` is populated only by Claude Code and the Claude Agent SDK; on
    # Codex, Cursor, Gemini CLI, Copilot CLI, Cline and OpenHands it is always
    # absent. Keying on it meant every call on those hosts was classified as
    # "the unbound host" and silently exempted, so the gate enforced nothing
    # anywhere except Claude Code while reporting that it had run.
    #
    # Attribution, by contrast, has a portable resolver: a per-role working
    # directory. So the question is whether a role was resolved, and the two
    # unresolved cases are distinguished only for the record.
    if not attributed:
        if event.from_subagent is False:
            # The host reports actors and did not name one: this is the
            # orchestrator itself. Refusing it would break the thing that
            # builds the partition.
            return result(
                "observe_only", "host_actor",
                "call came from the unbound host, which no role policy governs")
        return result(
            "observe_only", "unattributed",
            "this call could not be tied to a bound role, so no policy governs it",
            hint="declare a per-role working directory at dispatch so calls can be "
                 "attributed on hosts that do not report actor identity; until then "
                 "this call is residue and establishes nothing about any role's scope",
        )

    # --- the gate's own control plane --------------------------------------
    # A role must not be able to widen or switch off the thing governing it.
    # Without this, a role granted tools=None (or the maxey0 MCP tools) called
    # observe_gate_mode{mode: off} and was recorded as `in_scope` while it
    # disabled enforcement for every later call. Refused in every mode but
    # off, whatever the policy grants, because no policy can grant it.
    if _is_gate_control(event, kind, resource):
        return result(
            "deny", "gate_control_denied",
            f"{event.tool} changes the gate's own mode, policy or state; a governed "
            f"role cannot do that",
            hint="gate mode and policy are set by the host/orchestrator, not by a "
                 "role the gate is governing",
        )

    if policy is None:
        return result(
            "observe_only", "no_policy",
            f"the call was attributed to a role, but no gate policy is declared for it "
            f"(actor {event.actor_ref!r}, kind {event.actor_kind!r})",
            hint="declare one with declare_gate_policy(loop_id=...) before dispatching "
                 "the role, or the role's reach outside the window is unmeasured",
        )

    # --- tool grants ------------------------------------------------------
    if event.tool in policy.denied_tools:
        return _maybe_deny(
            result, mode,
            "tool_not_granted",
            f"role {policy.loop_id!r} is denied the {event.tool} tool",
            hint="remove the tool from denied_tools if this role legitimately needs it",
        )
    if policy.tools is not None and event.tool not in policy.tools:
        return _maybe_deny(
            result, mode,
            "tool_not_granted",
            f"role {policy.loop_id!r} was granted {sorted(policy.tools)} and "
            f"{event.tool} is not among them",
            hint=f"add {event.tool!r} to the role's declared tools if it is in scope",
        )

    # --- filesystem -------------------------------------------------------
    # A file tool that names nothing recognizable is NOT in scope — it is
    # unevaluated, and saying `allow / in_scope` about it would report an
    # unchecked read as a contained one. Fail open, and say that is what
    # happened.
    if kind == "file_read" and not resource and event.tool in SEARCH_TOOLS:
        # A search with no path and no known cwd reaches an unknown tree. That
        # is not an unrecognized argument (below): the reach is real and
        # unbounded, so enforce refuses it rather than failing open.
        return _maybe_deny(
            result, mode,
            "path_undeterminable",
            f"{event.tool} named no path and the working directory is unknown, "
            f"so its reach cannot be checked against role {policy.loop_id!r}'s scope",
            hint="pass an explicit path inside the role's declared read scope",
        )

    if kind in ("file_read", "file_write") and not resource:
        return result(
            "fail_open", "gate_error",
            f"{event.tool} named no recognizable path in {sorted((event.tool_input or {}))}; "
            f"the call was not evaluated",
            hint="the gate does not know this tool's path argument; add it to "
                 "PATH_KEYS so calls like this can be checked",
        )

    if kind == "file_read" and resource:
        # A glob's pattern is a second path: `Glob{path: docs, pattern:
        # "C:/Users/**/.env"}` or `"../**"` reaches outside `path` entirely,
        # so its literal prefix is checked too, relative to the search root.
        pattern = (event.tool_input or {}).get("pattern")
        if event.tool in SEARCH_TOOLS and event.tool != "Grep" and isinstance(pattern, str):
            prefix = _glob_prefix(pattern)
            escapes = (os.path.isabs(prefix) or prefix.startswith("/")
                       or ".." in prefix.replace("\\", "/").split("/"))
            if prefix and escapes:
                base = normalize_path(resource, event.cwd)
                if not path_matches(prefix, policy.read_paths, base):
                    return _maybe_deny(
                        result, mode,
                        "path_outside_scope",
                        f"{event.tool} pattern {pattern!r} reaches outside role "
                        f"{policy.loop_id!r}'s declared read scope",
                        hint="keep glob patterns relative to a path inside the read scope",
                    )
        if path_matches(resource, policy.read_paths, event.cwd):
            return result("allow", "in_scope", f"{resource} is inside the declared read scope")
        return _maybe_deny(
            result, mode,
            "path_outside_scope",
            f"{resource} is outside role {policy.loop_id!r}'s declared read scope",
            hint="a role bound to a partition works from what render_window gave it; "
                 "if this path is genuinely in scope, declare it in read_paths",
        )

    if kind == "file_write" and resource:
        if path_matches(resource, policy.write_paths, event.cwd):
            return result("allow", "in_scope", f"{resource} is inside the declared write scope")
        return _maybe_deny(
            result, mode,
            "path_outside_scope",
            f"{resource} is outside role {policy.loop_id!r}'s declared write scope",
            hint="a role publishes through its declared exposure region, not by writing "
                 "files; add the path to write_paths only if the role really owns it",
        )

    # --- shell ------------------------------------------------------------
    if kind == "shell" and resource:
        if command_matches(resource, policy.bash_allow):
            return result("allow", "in_scope", "the command matches the role's bash_allow")
        return _maybe_deny(
            result, mode,
            "command_not_granted",
            f"role {policy.loop_id!r} is not permitted to run: {resource[:200]}",
            hint="a shell is a general-purpose escape from every path check above it; "
                 "grant it narrowly through bash_allow or not at all",
        )

    # --- a tool this map has never seen -----------------------------------
    # Do not wave it through just because the name is unfamiliar. Hosts differ
    # in tool vocabulary and new tools appear constantly, so if an unknown
    # tool's arguments contain something path-shaped, check it as a read. This
    # is the difference between a gate that governs a host it was written for
    # and one that governs a host it was not.
    if kind == "opaque":
        candidate = _first_present(event.tool_input or {}, PATH_KEYS)
        if candidate and looks_like_path(candidate):
            if path_matches(candidate, policy.read_paths, event.cwd):
                return result("allow", "in_scope",
                              f"{candidate} is inside the declared read scope")
            return _maybe_deny(
                result, mode,
                "path_outside_scope",
                f"{event.tool} names {candidate}, which is outside role "
                f"{policy.loop_id!r}'s declared read scope",
                hint=f"{event.tool} is not a tool this gate knows; it was checked "
                     f"as a filesystem read because its arguments name a path",
            )

    # --- everything else --------------------------------------------------
    # Egress, delegation, MCP calls and opaque tools naming no path are
    # recorded but not refused on a path basis, because there is no path to
    # check. They are still governed by the tool grants above, which is the
    # honest lever: if a role should not reach the network, do not grant it
    # WebFetch.
    return result(
        "allow", "in_scope",
        f"{event.tool} ({kind}) is granted to this role and names no path to check",
    )


def looks_like_path(value: str) -> bool:
    """Whether a string is plausibly a filesystem path.

    Deliberately loose, and the bias is stated because it is easy to get
    backwards: a false positive costs one wasted policy check against a string
    that was never a path, while a false negative is an **unchecked file
    read**. An earlier version required a separator, which meant a bare
    relative name like ``secrets.env`` — a real file, resolvable against the
    working directory — was not treated as a path at all and fell through to
    the blanket allow.
    """
    if not value or len(value) > 4096:
        return False
    if any(ch in value for ch in "\n\r\t"):
        return False
    if ("/" in value or "\\" in value
            or value.startswith("~") or value.startswith(".")):
        return True
    # A bare filename resolves against cwd and is therefore still a path.
    # Require no spaces and a plausible length so ordinary prose arguments
    # (a query, a commit message) are not dragged through path matching.
    return " " not in value and len(value) <= 256


#: Tool-name suffixes that change the gate itself. Matched as suffixes so
#: every host's MCP prefix (mcp__maxey0-observe__, mcp__maxey0-ss__maxey0-ss_)
#: is covered without enumerating server names.
GATE_CONTROL_SUFFIXES: tuple[str, ...] = (
    "observe_gate_mode", "observe_gate_policy",
    "gate_set_mode", "gate_set_policy", "gate_declare_isolation",
)


def _is_gate_control(event: ToolEvent, kind: str, resource: Optional[str]) -> bool:
    """Whether this call would change the gate's mode, policy or journal."""
    name = event.tool.replace(".", "_")
    if any(name.endswith(suffix) for suffix in GATE_CONTROL_SUFFIXES):
        return True
    if kind != "file_write" or not resource:
        return False
    # The same change made by editing the files directly: policy-*.json and
    # actors-*.json live in state_dir(), and the journal is the evidence.
    from .attribution import state_dir
    from .journal import journal_path

    target = normalize_path(resource, event.cwd)
    state = normalize_path(str(state_dir()))
    journal = normalize_path(str(journal_path()))
    return target == state or target.startswith(state.rstrip("/\\") + "/") \
        or target.startswith(state.rstrip("/\\") + os.sep) \
        or target == journal or target.startswith(journal + ".")


def _maybe_deny(result, mode: GateMode, code: str, message: str, hint: str = "") -> Decision:
    """Refuse in ``enforce``; record the same finding in ``observe``.

    The message and hint are identical either way. That is deliberate: the only
    difference between the two modes should be whether the call proceeded, so a
    run in ``observe`` can be read as "here is what enforcement would have
    refused" without re-deriving anything.
    """
    if mode == "enforce":
        return result("deny", code, message, hint)
    return result("observe_only", code, message, hint)
