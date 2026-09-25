"""Expose the engineering-observation plane on the MCP surface.

Maxey0's observability is the part that makes a governed run auditable: what
each delegated role actually attempted, what the gate allowed, and which
isolation level the evidence supports. It was implemented in `server/planes/`
and reachable from no MCP transport we ship.

This module bridges those implementations onto the shared surface so all three
transports get them from one definition, and attaches the capability each one
requires.

Read and write are deliberately *separate tools*. `observe_gate_mode(mode=...)`
mutates when given an argument, and turning the gate off is the most
destructive operation on this surface, so it gets its own admin-only tool that
the catalog shows for what it is, rather than hiding inside a read behind a
per-argument capability. (`observe_isolation_level(declared=...)` persists
nothing; `gate.declare_isolation` is admin-only because of what it asserts, not
because it writes.)

Nearly every one of these tools answers from files on the machine the origin
runs on: the Context plane's ledger, the Gate's journal, and the Gate policy
file the host's own gate hook enforces from. Serving stdio on a laptop, that is
the point. Serving a public deployment from that same laptop, it handed the
maintainer's journals -- recent agent tool calls, ledger records, absolute
local paths -- to anyone holding the shared operator token, and let an admin
token rewrite the policy a local session enforces. So on a public deployment
those tools stay listed and stop touching the host unless
`MAXEY0_PUBLIC_HOST_PLANES` opts in; see `host_planes_enabled`.
"""
from __future__ import annotations

import os
import sys
import warnings
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from ..auth.policy import GATE_WRITE, OBSERVE_READ, is_public_deployment
from ..mcp_2026 import Tool

#: Where `server/` is looked for, in priority order. The source tree beside the
#: package comes first, so a checkout, an editable install and the Fly image
#: (/app) import exactly the tree they sit in, as they always have. An
#: installed wheel has no source tree -- the package's parent is site-packages
#: -- so it uses the copy setup.py writes into the package at build time.
_SOURCE_ROOT = Path(__file__).resolve().parents[2]
_BUNDLED_ROOT = Path(__file__).resolve().parents[1] / "_bundled"
#: What makes a `server/` usable here: the module `_impl` imports.
_PLANE = Path("server", "planes", "observe_impl.py")


def _plane_root() -> Path | None:
    for root in (_SOURCE_ROOT, _BUNDLED_ROOT):
        if (root / _PLANE).is_file():
            return root
    return None


#: The root whose `server/` the plane is imported from; None when there is no
#: copy at all (a partial checkout, or a package built without the bundle).
_ROOT: Path | None = _plane_root()

_NOT_FOUND = (
    "the engineering-observation plane was not found: there is no "
    "server/planes/observe_impl.py beside the maxey0_ss package (a source "
    "tree) or inside it under _bundled/ (an installed wheel), so the "
    "observe.* and gate.* tools are left off the surface"
)

#: The opt-in that lets a public deployment serve host-local plane state.
PUBLIC_HOST_PLANES = "MAXEY0_PUBLIC_HOST_PLANES"
_TRUTHY = frozenset({"1", "true", "yes", "on"})

# Every tool this module exposes, classified by what it does to the host. Read
# from `server/planes/observe_impl.py` and the `gate` package it calls, not
# from the tool names: `gate.declare_isolation` holds an admin capability and
# writes nothing, and the journal and policy-state readers create their
# directories as a side effect, so even the reads can write to the host.

#: Reads host-local state.
HOST_STATE_READS = frozenset({
    "maxey0-ss.observe.events",           # the Context plane ledger; returns its path
    "maxey0-ss.observe.attempts",         # the same ledger
    "maxey0-ss.observe.traces",           # the ledger and the Gate journal
    "maxey0-ss.observe.gate_activity",    # the Gate journal; returns its path
    "maxey0-ss.observe.gate_mode",        # the Gate policy file, and the env pin
    "maxey0-ss.observe.isolation_level",  # replays the ledger, reads the journal
    "maxey0-ss.gate.declare_isolation",   # the same read, compared to a claim
})
#: Writes host-local state: the policy file the host's gate hook enforces from,
#: including the no-session fallback every session inherits.
HOST_STATE_WRITES = frozenset({
    "maxey0-ss.gate.set_mode",
    "maxey0-ss.gate.set_policy",
})
#: Touches no host file. A loopback address and a start command, from config.
HOST_INDEPENDENT = frozenset({
    "maxey0-ss.observe.studio",
})


def host_planes_enabled() -> bool:
    """Whether host-state tools may touch this machine's filesystem.

    Always on a local deployment: stdio, or the API on localhost, is the owner
    reading their own machine, and that is unchanged. On a public deployment
    (`MAXEY0_PUBLIC`) only when `MAXEY0_PUBLIC_HOST_PLANES` says so, because a
    capability decides *who* may call a tool and cannot express *whose machine*
    it answers about. The shared bearer token maps to `operator`, which holds
    `observe`, so without this every holder of that token read the host.

    Read per call, like `is_public_deployment` itself, so a surface built
    before the environment was settled cannot hold a stale answer.
    """
    if not is_public_deployment():
        return True
    return os.getenv(PUBLIC_HOST_PLANES, "").strip().lower() in _TRUTHY


def _host_planes_disabled(tool: str, *, writes: bool) -> dict[str, Any]:
    """The answer a host-state tool gives on a public deployment that did not opt in.

    Static text only. It names the variable and nothing about the host -- no
    path, no home directory, no record count -- because the paths in the
    enabled answers are part of what was being disclosed.

    A read reports `available: false`, the plane's existing way of saying "no
    evidence here" as distinct from "the evidence is empty". A write refuses
    with `ok: false`, the shape `observe_gate_mode` already uses when the mode
    is pinned, rather than raising: this is a configuration answer, and
    -32603 "Tool execution failed" would send the caller looking for a bug.
    Either way nothing is read or written.
    """
    reason = (
        "This origin is a public deployment and does not serve the host-local "
        "Context plane ledger, Gate journal or Gate policy state. Set "
        f"{PUBLIC_HOST_PLANES}=1 on the origin to serve them to callers "
        "holding this tool's capability."
    )
    if writes:
        return {
            "ok": False, "refused": True, "error": "host_planes_disabled",
            "tool": tool, "opt_in": PUBLIC_HOST_PLANES,
            "reason": reason + " Nothing was written.",
        }
    return {
        "ok": True, "available": False, "host_planes": "disabled",
        "tool": tool, "opt_in": PUBLIC_HOST_PLANES, "reason": reason,
    }


def _contain(tool: Tool) -> Tool:
    """Put the host-state check in front of a tool's handler.

    The check wraps the handler itself rather than living in a transport, so
    stateless /mcp, the session transport and stdio all get it from the one
    `Tool` they share; `/v1` never reaches these plane functions at all.
    It runs before the plane function, which is what resolves paths and
    creates directories, so a refused call touches nothing.

    Fail closed on classification: a tool added here later is treated as a
    host read until somebody lists it in `HOST_INDEPENDENT` on purpose.
    """
    if tool.name in HOST_INDEPENDENT:
        return tool
    inner = tool.handler
    writes = tool.name in HOST_STATE_WRITES

    def handler(args: dict, *, _inner=inner, _name=tool.name, _writes=writes) -> Any:
        if host_planes_enabled():
            return _inner(args)
        return _host_planes_disabled(_name, writes=_writes)

    return replace(tool, handler=handler)


def _impl():
    """Import the plane implementation, adding `server/` to the path once."""
    if _ROOT is None:
        raise ImportError(_NOT_FOUND)
    for extra in (_ROOT / "server", _ROOT / "server" / "vendor"):
        if str(extra) not in sys.path:
            sys.path.insert(0, str(extra))
    from planes import observe_impl  # noqa: PLC0415

    return observe_impl


def unavailable_reason() -> str | None:
    """Why the plane cannot be imported, or None when it can.

    `observability_tools()` answers an unavailable plane with an empty list, by
    design. This is the same fact in words, so a surface that is ten tools
    short can say which copy was missing or which import failed.
    """
    try:
        _impl()
    except Exception as exc:  # noqa: BLE001 - reported, never swallowed
        return f"{type(exc).__name__}: {exc}"
    return None


def available() -> bool:
    return unavailable_reason() is None


def _guard(fn: Callable[..., Any]) -> Callable[[dict], Any]:
    """Adapt a keyword-argument plane function to the MCP `handler(args)` shape.

    Failures are reported rather than swallowed: the observation plane reads an
    append-only event log, and an unreadable log must not look like an empty one.
    """

    def handler(args: dict) -> Any:
        try:
            return fn(**{k: v for k, v in (args or {}).items() if v is not None})
        except Exception as exc:  # noqa: BLE001 - surfaced to the caller verbatim
            raise RuntimeError(f"{fn.__name__} failed: {type(exc).__name__}: {exc}") from exc

    return handler


_NO_ARGS: dict[str, Any] = {"type": "object", "properties": {}}


def observability_tools() -> list[Tool]:
    """The engineering-observation plane, as MCP tools.

    Returns an empty list when the plane cannot be imported, so a partial
    checkout degrades to a smaller surface instead of failing to start. It
    warns when it does: an installed wheel that carried no `server/` lost
    these ten tools with nothing on stderr, which is where an MCP host collects
    a server's diagnostics.

    Every tool is listed on every deployment, so the catalog -- and the edge
    copy generated from it -- does not depend on where the origin runs.
    Whether a host-state tool answers is decided per call; see `_contain`.
    """
    try:
        o = _impl()
    except Exception as exc:  # noqa: BLE001 - degrade, but say why
        warnings.warn(
            f"maxey0-ss observe/gate tools unavailable: {type(exc).__name__}: {exc}",
            RuntimeWarning,
            stacklevel=2,
        )
        return []

    tools = [
        Tool(
            "maxey0-ss.observe.events",
            "The context plane's ledger as a typed, queryable stream.",
            {
                "type": "object",
                "properties": {
                    "kinds": {"type": "array", "items": {"type": "string"}},
                    "role": {"type": "string"},
                    "region": {"type": "string"},
                    "since_seq": {"type": "integer"},
                    "limit": {"type": "integer"},
                },
            },
            _guard(o.observe_events),
            capability=OBSERVE_READ,
        ),
        Tool(
            "maxey0-ss.observe.attempts",
            "Whether a role attempted a region, and whether containment held.",
            {"type": "object", "properties": {"role": {"type": "string"}, "region": {"type": "string"}}},
            _guard(o.observe_attempts),
            capability=OBSERVE_READ,
        ),
        Tool(
            "maxey0-ss.observe.traces",
            "Context, execution and state traces, correlated causally.",
            {"type": "object", "properties": {"limit": {"type": "integer"}}},
            _guard(o.observe_traces),
            capability=OBSERVE_READ,
        ),
        Tool(
            "maxey0-ss.observe.gate_activity",
            "What the delegated agents actually did, per role, from the journal.",
            {
                "type": "object",
                "properties": {
                    "role": {"type": "string"},
                    "kinds": {"type": "array", "items": {"type": "string"}},
                    "limit": {"type": "integer"},
                },
            },
            _guard(o.observe_gate_activity),
            capability=OBSERVE_READ,
        ),
        Tool(
            "maxey0-ss.observe.gate_mode",
            "Read the current Gate mode: enforce, observe, or off.",
            _NO_ARGS,
            lambda _args: _guard(o.observe_gate_mode)({}),
            capability=OBSERVE_READ,
        ),
        Tool(
            "maxey0-ss.observe.isolation_level",
            "Which of L0-L3 the evidence supports, and the shortfall where it does not.",
            _NO_ARGS,
            lambda _args: _guard(o.observe_isolation_level)({}),
            capability=OBSERVE_READ,
        ),
        Tool(
            "maxey0-ss.observe.studio",
            "The Studio's address and start command.",
            _NO_ARGS,
            _guard(o.observe_studio),
            capability=OBSERVE_READ,
        ),
        # --- writes. Admin only: no non-admin role holds GATE_WRITE. ---
        Tool(
            "maxey0-ss.gate.set_mode",
            "Set the Gate mode. Turning the Gate off removes containment enforcement.",
            {
                "type": "object",
                "properties": {"mode": {"type": "string", "enum": ["enforce", "observe", "off"]}},
                "required": ["mode"],
            },
            _guard(o.observe_gate_mode),
            capability=GATE_WRITE,
        ),
        Tool(
            "maxey0-ss.gate.set_policy",
            "Declare what a bound role may reach outside the window.",
            {
                "type": "object",
                "properties": {
                    "role": {"type": "string"},
                    "read_paths": {"type": "array", "items": {"type": "string"}},
                    "write_paths": {"type": "array", "items": {"type": "string"}},
                    "tools": {"type": "array", "items": {"type": "string"}},
                    "bash_allow": {"type": "array", "items": {"type": "string"}},
                    "note": {"type": "string"},
                },
                "required": ["role"],
            },
            _guard(o.observe_gate_policy),
            capability=GATE_WRITE,
        ),
        Tool(
            "maxey0-ss.gate.declare_isolation",
            "Declare the isolation level this deployment claims, for evidence comparison.",
            {"type": "object", "properties": {"declared": {"type": "string"}}, "required": ["declared"]},
            _guard(o.observe_isolation_level),
            capability=GATE_WRITE,
        ),
    ]
    return [_contain(tool) for tool in tools]
