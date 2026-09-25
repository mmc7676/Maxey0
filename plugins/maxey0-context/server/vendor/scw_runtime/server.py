"""MCP server exposing the SCW runtime.

Tool surface, grouped by what it is for — and by which of the four layers of
the prompt -> context -> harness -> loop progression (Macedo, arXiv:2607.00038)
it belongs to:

*Prompt*      ``create_prompt`` · ``revise_prompt`` · ``render_prompt``
*Structure*   ``create_scw`` · ``close_scw``                              (context)
*Content*     ``write`` · ``read``                                        (context)
*Harness*     ``create_harness`` · ``harness_call``
*Loops*       ``bind_scope`` · ``loop_tick`` · ``unbind_scope``           (loop)
*Crossing*    ``open_bridge`` · ``close_bridge`` · ``promote``            (context)
*Observation* ``inspect_window`` · ``render_window`` · ``reset_window``

Every tool returns a structured dict. Refusals come back as
``{"ok": false, "error": ..., "message": ..., "hint": ...}`` rather than as
opaque failures, because refusal is a normal, informative outcome here: a loop
discovering it cannot reach a region is the isolation model working, and the
hint tells the caller exactly which bridge would legitimize the access.

Run over stdio for Claude Code::

    python -m scw_runtime

The event log path comes from ``SCW_EVENT_LOG`` (default
``~/.scw/events.jsonl``); point the inspector at the same file.
"""

from __future__ import annotations

import functools
import json
import os
from pathlib import Path
from typing import Any, Callable, Optional

from mcp.server.fastmcp import FastMCP

from .errors import SCWError
from .events import EventLog
from .window import ContextWindow

DEFAULT_LOG = Path(os.environ.get("SCW_EVENT_LOG") or (Path.home() / ".scw" / "events.jsonl"))

mcp = FastMCP(
    "scw-runtime",
    instructions=(
        "Structured Context Windows: partition the context window into addressable, "
        "typed regions, bind a loop's execution scope to one region, and enforce "
        "isolation between regions at the tool layer. This covers all four layers of "
        "the prompt -> context -> harness -> loop progression: create_prompt declares "
        "the instruction, create_scw/write/read are the context, create_harness "
        "declares the environment and architecture, and bind_scope/loop_tick declare "
        "and price the loop.\n\n"
        "Typical order: reset_window -> create_prompt (if the instruction should be "
        "versioned) -> create_scw (one per tier) -> write reference material -> "
        "create_harness (skills, architecture) -> bind_scope(loop_id, scratchpad, "
        "prompt_id=..., harness_id=...) -> per iteration: write / read / render_prompt "
        "/ harness_call / loop_tick -> promote what survived -> unbind_scope -> "
        "close_scw.\n\n"
        "Call inspect_window whenever you want the region map, the token budget, the "
        "cache economics of the next iteration, and every prompt/harness declaration "
        "held to account. If a call is refused, read the 'hint' field: it names the "
        "bridge (or revision, or approval) that would make the access legal."
    ),
)


class _Session:
    """Holds the one live window this server process is managing."""

    def __init__(self) -> None:
        self.log_path: Path = DEFAULT_LOG
        self.window: ContextWindow = self._new_window()

    def _new_window(
        self,
        total_budget: Optional[int] = None,
        strict_scope: bool = False,
        log_content: bool = True,
        name: str = "window",
        host_only_bridges: bool = False,
        require_bounded_loops: bool = False,
        max_total_iterations: Optional[int] = None,
        max_loop_depth: Optional[int] = None,
        prev_run: Optional[dict] = None,
    ) -> ContextWindow:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        return ContextWindow(
            total_budget=total_budget,
            event_log=EventLog(path=self.log_path, prev_run=prev_run),
            strict_scope=strict_scope,
            log_content=log_content,
            name=name,
            host_only_bridges=host_only_bridges,
            require_bounded_loops=require_bounded_loops,
            max_total_iterations=max_total_iterations,
            max_loop_depth=max_loop_depth,
        )

    def reset(self, **kwargs: Any) -> ContextWindow:
        # Commit to the outgoing run before closing it, so the incoming run's
        # window.init can back-link to it and a deleted run becomes detectable.
        head = self.window.log.head()
        self.window.log.close()
        self.window = self._new_window(prev_run=head, **kwargs)
        return self.window


_session = _Session()


def _tool(fn: Callable[..., dict]) -> Callable[..., dict]:
    """Turn runtime errors into structured, actionable tool results."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> dict:
        try:
            result = fn(*args, **kwargs)
        except SCWError as exc:
            return exc.to_dict()
        except (ValueError, KeyError) as exc:
            return {"ok": False, "error": "bad_argument", "message": str(exc)}
        if isinstance(result, dict) and "ok" not in result:
            result = {"ok": True, **result}
        return result

    return wrapper


# ---------------------------------------------------------------------------
# prompt layer
# ---------------------------------------------------------------------------
@mcp.tool()
@_tool
def create_prompt(
    label: str,
    template: str,
    variables: Optional[list[str]] = None,
    prompt_id: Optional[str] = None,
    locked: bool = False,
) -> dict:
    """Declare a prompt-layer instruction artifact — "how to ask", held as data.

    `template` uses `{{slot}}` placeholders; `variables` defaults to whatever
    slots the template contains. Host-only: this tool has no `loop_id`
    parameter because a bound loop can never author a prompt, under any
    bridge — prompts sit outside the region/scope model entirely, so there is
    no grant that could legalize it. That is the structural answer to an
    agent rewriting its own instructions mid-run.

    Pass `locked=True` once the prompt should never be revised again.
    """
    spec = _session.window.create_prompt(
        label, template, variables=variables, prompt_id=prompt_id, locked=locked
    )
    return spec.to_dict()


@mcp.tool()
@_tool
def revise_prompt(
    prompt_id: str,
    template: str,
    variables: Optional[list[str]] = None,
    lock: bool = False,
) -> dict:
    """Edit a prompt, keeping the superseded version in its history.

    Refused if the prompt is `locked`. If a loop is currently bound with this
    prompt's earlier version, inspect_window will report `prompt.version_drift`
    until that loop is rebound — a prompt moving under a running loop is a
    fact worth surfacing, not something to hide.
    """
    spec = _session.window.revise_prompt(prompt_id, template, variables=variables, lock=lock)
    return spec.to_dict()


@mcp.tool()
@_tool
def render_prompt(
    prompt_id: str,
    bindings: Optional[dict[str, str]] = None,
    loop_id: Optional[str] = None,
) -> dict:
    """Materialize a prompt against variable bindings.

    Refused if `bindings` names a variable the prompt never declared — that is
    almost always a typo'd slot, caught before it silently renders as nothing.
    A declared variable with no binding is not an error: it renders empty and
    is listed in `unbound_variables`.
    """
    return _session.window.render_prompt(prompt_id, bindings=bindings, loop_id=loop_id)


# ---------------------------------------------------------------------------
# structure
# ---------------------------------------------------------------------------
@mcp.tool()
@_tool
def create_scw(
    label: str,
    region_type: str = "working",
    policy: Optional[dict] = None,
    parent_scw_id: Optional[str] = None,
    order: Optional[int] = None,
    scw_id: Optional[str] = None,
    loop_id: Optional[str] = None,
) -> dict:
    """Create an addressable region of the context window.

    region_type picks a policy preset:
      reference  read-only source material; only the unbound host may seed it
      durable    long-lived facts; LRU eviction; versioned
      episodic   session/run history; FIFO eviction; versioned
      working    task state for the current job; not bridgeable by default
      scratchpad volatile; 2048-token budget; cleared at every loop tick;
                 purged on close; not bridgeable

    Pass `policy` to override any preset field: mutability, eviction,
    token_budget, purge_on_close, bridgeable, versioned, reset_each_tick, cache.

    Regions render in `order`. The default order puts read-only and durable
    tiers first and the scratchpad last, because prompt caches are prefix
    caches and a region that mutates invalidates everything after it. Override
    `order` only if you mean to.

    Set `parent_scw_id` to nest a region inside another (an episodic container
    inside a durable tier, for instance). A loop bound to the parent reaches
    the whole subtree; a loop bound to a child cannot see upward.
    """
    region = _session.window.create_scw(
        label=label,
        region_type=region_type,
        policy=policy,
        parent_scw_id=parent_scw_id,
        order=order,
        scw_id=scw_id,
        loop_id=loop_id,
    )
    return {
        "scw_id": region.scw_id,
        "label": region.label,
        "region_type": region.region_type,
        "policy": region.policy.to_dict(),
        "order": region.order,
        "parent_id": region.parent_id,
    }


@mcp.tool()
@_tool
def close_scw(scw_id: str, loop_id: Optional[str] = None, cascade: bool = False) -> dict:
    """Close a region: seal it, or destroy its content if purge_on_close is set.

    Fails while a loop is still bound to the region, and while it has open
    children unless `cascade=True`. Any bridge touching the region is revoked.
    """
    return _session.window.close_scw(scw_id, loop_id=loop_id, cascade=cascade)


# ---------------------------------------------------------------------------
# content
# ---------------------------------------------------------------------------
@mcp.tool()
@_tool
def write(
    scw_id: str,
    data: str,
    loop_id: Optional[str] = None,
    mode: str = "append",
    key: Optional[str] = None,
) -> dict:
    """Write content into a region.

    Pass `loop_id` when writing from inside a bound loop; the write is then
    checked against that loop's scope. Omitting it writes as the unbound host,
    which can reach everything and is recorded as such.

    mode="append" adds an entry; mode="replace" clears the region first.
    Supplying `key` upserts that named slot in place — use it for memory blocks
    ("user_profile", "current_hypothesis") that should stay one entry across
    iterations rather than accumulating duplicates.

    The result includes `cache_impact`: how many otherwise-cacheable tokens
    this write just invalidated by sitting where it sits.
    """
    return _session.window.write(scw_id, data, loop_id=loop_id, mode=mode, key=key)


@mcp.tool()
@_tool
def read(scw_id: str, loop_id: Optional[str] = None, include_children: bool = True) -> dict:
    """Read a region's rendered content.

    Refused if the caller's scope does not reach it. The refusal names the
    bridge that would make it legal.
    """
    return _session.window.read(scw_id, loop_id=loop_id, include_children=include_children)


# ---------------------------------------------------------------------------
# harness layer
# ---------------------------------------------------------------------------
@mcp.tool()
@_tool
def create_harness(
    label: str,
    architecture: str = "solo",
    skills: Optional[list[dict]] = None,
    strict_skills: bool = False,
    tool_grants: Optional[list[str]] = None,
    sandbox: str = "shared",
    iteration_budget: Optional[int] = None,
    requires_approval: Optional[list[str]] = None,
    harness_id: Optional[str] = None,
    loop_id: Optional[str] = None,
    verification_policy: Optional[str] = None,
    evidence_policy: str = "none",
) -> dict:
    """Declare the environment, tools, and architecture a loop runs inside.

    architecture:
      solo           one agent does everything (the default)
      maker_checker  producer and verifier are distinct actors — and, by
                     default, distinct CONTEXTS: see verification_policy
      manager        an orchestrator delegates to helpers; declared for the
                     record, not separately enforced

    verification_policy — how hard a verdict is held to account:
      declared     verified_by is any string, recorded and flagged afterwards
                   (the default for solo/manager, and v0.2.0 behavior)
      attributed   verified_by must name a real, bound, distinct loop
      disjoint     attributed, AND the judge's read closure must provably
                   exclude this loop's write closure outside what `exposes`
                   published. This is the default for maker_checker, because
                   the failure the literature documents is shared *context*,
                   not a shared name — renaming the judge does not break it.

    evidence_policy — when a passing verdict must cite attest_evidence:
      none        never (default)
      objective   at declared verification_level 1-3 — the levels that claim
                  something actually ran
      all         at every level, including a rubric score or a human approver

    `requires_approval` entries are fnmatch globs, so `deploy_*` fires.

    `skills` is a list of `{"name": ..., "skill_id"?: ..., "description"?: ...,
    "verified"?: bool}` — the named, tested, reusable routines this harness
    makes available. Set `strict_skills=True` to have `harness_call` refuse a
    skill_id outside this set instead of merely logging and flagging it.

    `requires_approval` names action patterns that `harness_call` will refuse
    unless called again with `approved=True` — the guardrail for irreversible
    actions.

    Unlike prompts, a harness can be declared from inside a bound loop (pass
    `loop_id`) — a manager loop fanning out to helpers needs to describe their
    environment. The hazard harnesses guard against is a maker approving its
    own work, which is enforced at loop_tick, not who may describe the setup.
    """
    profile = _session.window.create_harness(
        label,
        architecture=architecture,
        skills=skills,
        strict_skills=strict_skills,
        tool_grants=tuple(tool_grants or ()),
        sandbox=sandbox,
        iteration_budget=iteration_budget,
        requires_approval=tuple(requires_approval or ()),
        harness_id=harness_id,
        loop_id=loop_id,
        verification_policy=verification_policy,
        evidence_policy=evidence_policy,
    )
    return profile.to_dict()


@mcp.tool()
@_tool
def harness_call(
    harness_id: str,
    skill_id: str,
    loop_id: Optional[str] = None,
    action: Optional[str] = None,
    approved: Optional[bool] = None,
) -> dict:
    """Record a loop invoking a named skill under a harness profile.

    Refused if `skill_id` is outside the harness's declared skills and the
    harness declares `strict_skills=True` — the harness-layer version of "a
    while-true wrapped around a stranger" becomes a structural refusal rather
    than a code smell. An undeclared call under a non-strict harness is
    counted, not refused, and surfaced by inspect_window's advisories.

    Refused if `action` names one of the harness's `requires_approval`
    patterns and `approved` is not `True` — call this again with
    `approved=True` once a human has signed off.
    """
    return _session.window.harness_call(
        harness_id, skill_id, loop_id=loop_id, action=action, approved=approved
    )


# ---------------------------------------------------------------------------
# loops
# ---------------------------------------------------------------------------
@mcp.tool()
@_tool
def bind_scope(
    loop_id: str,
    scw_id: str,
    descend: bool = True,
    max_iterations: Optional[int] = None,
    trigger: str = "manual",
    goal: Optional[str] = None,
    verification_level: Optional[int] = None,
    prompt_id: Optional[str] = None,
    harness_id: Optional[str] = None,
    exposes: Optional[list[str]] = None,
    criterion_id: Optional[str] = None,
    parent_loop_id: Optional[str] = None,
) -> dict:
    """Bind a loop's execution scope to one region, and declare its spec.

    This is the point of the whole runtime: from here on, every call carrying
    `loop_id` resolves against `scw_id` (plus its subtree when `descend`) and
    is refused anywhere else. The loop iterates against a named region instead
    of against the whole window, so sibling regions cannot be contaminated by
    it and cannot leak into it.

    `max_iterations` is a hard stop; loop_tick refuses to advance past it.

    This one call is where a loop declares its position in all four layers of
    the prompt -> context -> harness -> loop progression, rather than four
    separate claims that can drift apart:
      trigger             "manual" | "scheduled" | "event"           (loop)
      goal                what "done" means, in one sentence         (loop)
      verification_level  1 deterministic · 2 rule · 3 delayed field
                          truth · 4 model-as-judge · 5 human checkpoint (loop)
      prompt_id           id of a create_prompt artifact governing
                          this loop's instruction                   (prompt)
      harness_id          id of a create_harness profile governing
                          this loop's environment/architecture      (harness)

    Levels 1-2 are the autonomous zone. Declaring one is a claim the runtime
    checks: if you never supply a verdict to loop_tick, inspect_window reports
    `verification.overclaimed` rather than taking the claim at face value.
    Declaring `harness_id` against a harness with `architecture='maker_checker'`
    is a claim `loop_tick` enforces outright: under the default
    verification_policy='disjoint' this loop is refused, not merely flagged, if
    the judge it names can read what this loop wrote.

    Three further declarations shape the partition:
      exposes         regions this loop publishes to — the ONLY regions a
                      judge of it may also see. Host-authored here: a loop
                      cannot widen its own exposure, which is what stops the
                      disjointness proof being satisfied vacuously.
      criterion_id    a pinned acceptance criterion (see pin_criterion). Its
                      bytes are re-checked every tick, so the yardstick moving
                      mid-run is a refusal rather than a mystery.
      parent_loop_id  makes this a sub-loop. Cycles are refused, the child
                      must bind inside the parent's reach, and the ceiling is
                      the PRODUCT of the chain, because nesting multiplies.
    """
    loop = _session.window.bind_scope(
        loop_id,
        scw_id,
        descend=descend,
        max_iterations=max_iterations,
        trigger=trigger,
        goal=goal,
        verification_level=verification_level,
        prompt_id=prompt_id,
        harness_id=harness_id,
        exposes=exposes,
        criterion_id=criterion_id,
        parent_loop_id=parent_loop_id,
    )
    return loop.to_dict()


@mcp.tool()
@_tool
def loop_tick(
    loop_id: str,
    note: Optional[str] = None,
    verified: Optional[bool] = None,
    verified_by: Optional[str] = None,
    evidence_id: Optional[str] = None,
) -> dict:
    """Advance the loop one iteration. Call this once per model call.

    Record the iteration's verdict with `verified`: true if the check passed,
    false if it failed, omitted if no check ran. Name the judge with
    `verified_by`; leaving it unset records a self-approval, which at declared
    level 4-5 means the maker graded its own work.

    `verified_by` must name a real, currently bound, distinct loop whenever the
    harness declares verification_policy 'attributed' or 'disjoint' — naming a
    string that is not a loop is not a checker. Under 'disjoint' (the default
    for a maker_checker harness) the judge's read closure must also provably
    exclude this loop's write closure, except for what `exposes` published.
    Ask `check_disjointness(maker, judge)` first if you want the answer before
    the refusal.

    `evidence_id` cites an `attest_evidence` record. A harness with
    evidence_policy='objective' requires one for a passing verdict at declared
    level 1-3: those levels claim something *ran*, and this is what makes the
    claim specific, single-use, and stale if the work changes underneath it.

    The ledger turns this into `cost_per_accepted_change` — billed prompt
    tokens divided by iterations that passed. A loop that burns budget without
    producing accepted changes is broken even when it looks busy.

    A tick is the billing boundary. It prices the window against the state at
    the previous tick and returns `cache`:
      cached_tokens       served by the prefix cache
      reprocessed_tokens  re-paid this iteration
      recoverable_tokens  what an optimal region order would have saved
      breakpoint_scw_id   last region of the stable prefix — put your
                          cache_control marker after it

    It also clears every reset_each_tick region in scope (so the scratchpad
    starts each iteration clean) and expires any bridge whose ttl_ticks ran
    out.
    """
    return _session.window.loop_tick(
        loop_id, note=note, verified=verified, verified_by=verified_by,
        evidence_id=evidence_id,
    )


# ---------------------------------------------------------------------------
# the partition: criteria, evidence, and the disjointness proof
# ---------------------------------------------------------------------------
@mcp.tool()
@_tool
def pin_criterion(scw_id: str, criterion_id: Optional[str] = None, label: str = "") -> dict:
    """Freeze a region as the yardstick a loop is graded against.

    Records the region's content signature now, and re-checks it at every tick
    of any loop bound with this criterion_id. Making the region read-only stops
    the LOOP editing the yardstick; pinning is what catches the HOST rewriting
    it mid-run, which no region type can detect.

    Host-only: there is no loop_id parameter, on purpose. A yardstick the
    graded party can pin or release is not a yardstick.
    """
    return _session.window.pin_criterion(
        scw_id, criterion_id=criterion_id, label=label
    ).to_dict()


@mcp.tool()
@_tool
def repin_criterion(criterion_id: str) -> dict:
    """Accept the criterion's current bytes as the new yardstick.

    Deliberately not automatic: re-pinning restarts comparability, so rounds
    before and after are no longer measuring the same thing. That belongs in
    the log as an explicit act.
    """
    return _session.window.repin_criterion(criterion_id).to_dict()


@mcp.tool()
@_tool
def attest_evidence(
    loop_id: str,
    kind: str = "command",
    command: Optional[str] = None,
    exit_code: Optional[int] = None,
    output_sha256: Optional[str] = None,
    output_bytes: Optional[int] = None,
    artifact_sha256: Optional[str] = None,
    criterion_id: Optional[str] = None,
    score: Optional[float] = None,
    approver: Optional[str] = None,
    note: str = "",
) -> dict:
    """Record external evidence for a forthcoming verdict, and get an id for it.

    kind is one of:
      command   something ran — requires `command` and `exit_code`
      artifact  a blob exists — requires `artifact_sha256`
      rubric    a model scored against a pinned criterion — requires criterion_id
      human     a person signed off — requires `approver`

    The evidence is bound to this loop and to its region's signature right now.
    Citing it at loop_tick re-checks both, so it cannot be borrowed from
    another loop, replayed across iterations, or claimed after the loop has
    rewritten the work the check described.

    This is an assertion, not an interception: the runtime cannot run your
    command or verify your digest. What it adds is that the assertion is
    specific, single-use, scope-bound, and permanently in a hash-chained log.
    """
    return _session.window.attest_evidence(
        loop_id, kind=kind, command=command, exit_code=exit_code,
        output_sha256=output_sha256, output_bytes=output_bytes,
        artifact_sha256=artifact_sha256, criterion_id=criterion_id,
        score=score, approver=approver, note=note,
    ).to_dict()


@mcp.tool()
@_tool
def check_disjointness(maker_id: str, judge_id: str) -> dict:
    """Would this judge's verdict on this maker be accepted, and why not?

    Pure — mutates nothing — so ask it before running the iteration that would
    be refused. Returns the same report the refusal carries: five rules, which
    failed, and for the exposure rule the exact set of regions the judge can
    read that the maker can write.
    """
    return _session.window.disjointness(maker_id, judge_id)


@mcp.tool()
@_tool
def scope_closure(loop_id: Optional[str] = None) -> dict:
    """What this loop can read and what it can write, as sets.

    The audit surface for the partition: `read_closure` is every region it can
    obtain bytes from (its own subtree plus what its grants open, minus
    anything declaring bridgeable=false), `write_closure` is every region it
    can put bytes into.
    """
    return {
        "loop_id": loop_id,
        "read_closure": sorted(_session.window.read_closure(loop_id)),
        "write_closure": sorted(_session.window.write_closure(loop_id)),
    }


@mcp.tool()
@_tool
def seal_window() -> dict:
    """End setup: close the privileged unbound path for the rest of the run.

    Before this, an unattributed call is the host building the window. After
    it, every call must carry a loop_id. Call it once the regions exist and the
    read-only material is seeded.
    """
    return _session.window.seal()


@mcp.tool()
@_tool
def unbind_scope(loop_id: str, terminal_state: Optional[str] = None) -> dict:
    """Release a loop's scope, naming the state it ended in.

    terminal_state is one of: success, no_op, blocked, stalled, exhausted.

    One rule is enforced rather than trusted: `success` requires at least one
    accepted iteration. A loop that never passed a check, or that ran out of
    budget, cannot be closed as a success — an error is never a win.
    """
    return _session.window.unbind_scope(loop_id, terminal_state=terminal_state)


# ---------------------------------------------------------------------------
# crossing boundaries
# ---------------------------------------------------------------------------
@mcp.tool()
@_tool
def open_bridge(
    from_scw_id: str,
    to_scw_id: str,
    mode: str = "read",
    reason: str = "",
    ttl_ticks: Optional[int] = None,
    loop_id: Optional[str] = None,
) -> dict:
    """Mint an explicit cross-region grant — the only legal hole in a wall.

    mode is "read", "write", or "read_write". Give a `reason`: it lands in the
    audit trail. Pass `ttl_ticks` so the grant expires with the iteration that
    needed it — `ttl_ticks=1` dies at the end of the current iteration.

    Refused if the target region declares bridgeable=false. That is not an
    oversight to work around: an unbridgeable region is unreachable from
    outside by design.
    """
    bridge = _session.window.open_bridge(
        from_scw_id,
        to_scw_id,
        mode=mode,
        reason=reason,
        ttl_ticks=ttl_ticks,
        loop_id=loop_id,
    )
    return bridge.to_dict()


@mcp.tool()
@_tool
def close_bridge(bridge_id: str, loop_id: Optional[str] = None) -> dict:
    """Revoke a grant immediately, without waiting for its TTL.

    Close a bridge as soon as the crossing it authorized is done. A grant that
    outlives its purpose is how a partitioned window quietly becomes a flat
    one; the inspector flags long-lived grants for the same reason.
    """
    return _session.window.close_bridge(bridge_id, loop_id=loop_id)


@mcp.tool()
@_tool
def promote(
    from_scw_id: str,
    to_scw_id: str,
    keys: Optional[list[str]] = None,
    entry_ids: Optional[list[str]] = None,
    loop_id: Optional[str] = None,
    mode: str = "move",
) -> dict:
    """Move or copy content across a tier boundary, keeping provenance.

    This is how volatile work becomes durable at the end of an iteration:
    promote the conclusions out of the scratchpad into an episodic or durable
    region, then let the tick clear the rest.

    Needs read access to the source and write access to the destination, so a
    bound loop cannot launder scratchpad content into persistent memory unless
    a bridge says it may. Select with `keys` and/or `entry_ids`; with neither,
    everything in the source is promoted.
    """
    return _session.window.promote(
        from_scw_id,
        to_scw_id,
        keys=keys,
        entry_ids=entry_ids,
        loop_id=loop_id,
        mode=mode,
    )


# ---------------------------------------------------------------------------
# observation
# ---------------------------------------------------------------------------
@mcp.tool()
@_tool
def inspect_window(include_content: bool = False, loop_id: Optional[str] = None) -> dict:
    """Return the region map, token accounting, cache plan, and advisories.

    Use this to answer "where are my tokens going" and "what would the next
    iteration cost". `advisories` is the actionable part: it names the region
    whose position is invalidating a cacheable prefix, the budget about to
    start evicting, and any standing grant with no TTL.
    """
    return _session.window.inspect(include_content=include_content, loop_id=loop_id)


@mcp.tool()
@_tool
def render_window(
    loop_id: Optional[str] = None, commit: bool = True, scope: str = "caller"
) -> dict:
    """Materialize the window as prompt text.

    Returns the text, per-region token offsets, and `cache_breakpoint_after` —
    the region your prefix-cache marker belongs after. Pass `commit=false` to
    look without advancing the cache baseline.
    """
    return _session.window.render(loop_id=loop_id, commit=commit, scope=scope)


@mcp.tool()
@_tool
def reset_window(
    total_budget: Optional[int] = None,
    strict_scope: bool = False,
    log_content: bool = True,
    host_only_bridges: bool = False,
    name: str = "window",
    require_bounded_loops: bool = False,
    max_total_iterations: Optional[int] = None,
    max_loop_depth: Optional[int] = None,
) -> dict:
    """Tear down the current window and start a fresh run.

    `total_budget` sets the window-level token ceiling used for pressure
    advisories.

    `strict_scope=true` refuses any call that does not carry a loop_id, removing
    the privileged unbound path entirely — use it when isolation should be total
    rather than default-on-for-loops.

    `host_only_bridges=true` takes grant-minting away from loops, so the set of
    possible crossings is decided entirely outside them.

    `log_content=false` records structure, sizes, and every access decision but
    replaces region text with a hash, for logs you would rather not have contain
    the content.

    `require_bounded_loops=true` refuses any bind_scope that declares no
    max_iterations — an unbounded loop is the runaway anti-pattern with its
    brakes left as a comment. `max_total_iterations` caps the whole window
    across every loop; `max_loop_depth` caps sub-loop nesting.

    Note the phase distinction: leave `strict_scope` off here and call
    `seal_window()` once setup is done. The host has to be able to create
    regions and seed read-only material before there is any loop to attribute
    that work to.
    """
    window = _session.reset(
        total_budget=total_budget,
        strict_scope=strict_scope,
        log_content=log_content,
        host_only_bridges=host_only_bridges,
        name=name,
        require_bounded_loops=require_bounded_loops,
        max_total_iterations=max_total_iterations,
        max_loop_depth=max_loop_depth,
    )
    return {
        "run_id": window.log.run_id,
        "event_log": str(_session.log_path),
        "total_budget": total_budget,
        "strict_scope": strict_scope,
        "host_only_bridges": host_only_bridges,
        "log_content": log_content,
        "next": "create_scw one region per tier, then bind_scope your loop to the volatile one",
    }


# ---------------------------------------------------------------------------
# routing layer -- task -> Maxey0 concept -> an existing, hardened loop
# (bound live, for real) or a Maxey0 skill/agent fallback. Every decision is
# logged as a real event on this session's own window.
# ---------------------------------------------------------------------------
_MAXEY0_ROOT = Path(
    os.environ.get("MAXEY0_ROOT")
    or (Path(__file__).resolve().parents[3] / "Maxey0" / "Maxey0")
)
_DATASET_DIR = Path(__file__).resolve().parents[2] / "loops" / "dataset"
#: `MAXEY0_LOOPS` lets a packaged install (a plugin bundle, a container) point at
#: a vendored loops.json instead of the source checkout's, which is the only way
#: routing can work when this module ships without the repo around it.
_LOOPS_PATH = Path(
    os.environ.get("MAXEY0_LOOPS") or (_DATASET_DIR / "loops.json")
)
_route_counter = 0


@functools.lru_cache(maxsize=1)
def _maxey0_manifest() -> dict:
    return json.loads((_MAXEY0_ROOT / "manifest.json").read_text(encoding="utf-8"))


@functools.lru_cache(maxsize=1)
def _maxey0_registry() -> dict:
    # A bundled Maxey0 root may flatten registry.json up a level; accept both
    # rather than making the packager reproduce the repo's directory shape.
    for candidate in (_MAXEY0_ROOT / "registry" / "registry.json",
                      _MAXEY0_ROOT / "registry.json"):
        if candidate.exists():
            return json.loads(candidate.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"no registry.json under {_MAXEY0_ROOT}")


@functools.lru_cache(maxsize=1)
def _loop_dataset() -> tuple[dict, ...]:
    if not _LOOPS_PATH.exists():
        return ()
    return tuple(json.loads(_LOOPS_PATH.read_text(encoding="utf-8"))["loops"])


def _spec_from_record(record: dict):
    """Compile a dataset record into a bindable HarnessSpec.

    Built from the record itself rather than by importing
    ``loops/dataset/build.py``: that module needs openpyxl and the source
    spreadsheet, so depending on it made ``route_task`` fail in exactly the
    packaged installs this tool is most useful in. loops.json already carries
    the topology, so it is the contract.
    """
    import sys as _sys

    for extra in (str(_DATASET_DIR.parents[1]), str(_DATASET_DIR.parents[1] / "loops")):
        if extra not in _sys.path:
            _sys.path.insert(0, extra)
    from d4.harness_dsl import HarnessSpec, RoleDef  # noqa: PLC0415

    stages = record.get("agent_stages") or []
    roles: list = []
    if stages:
        for index, stage in enumerate(stages):
            role_id = f"stage{index}-{stage['agent_id'].lower()}"
            prior = frozenset()
            if index > 0:
                prior = frozenset(
                    {f"stage{index - 1}-{stages[index - 1]['agent_id'].lower()}"})
            roles.append(RoleDef(
                role_id=role_id, reads_from=prior, exposes=(f"{role_id}-out",),
                verification_level=1, max_iterations=2, output_kind="text",
                goal=f"{stage['agent_name']} ({stage['agent_id']}) performs its "
                     f"stage of {record['title']!r}"))
    else:
        named = record.get("roles") or record.get("hardening", {}).get("roles") or []
        for index, role_id in enumerate(named):
            prior = frozenset({named[index - 1]}) if index > 0 else frozenset()
            grading = "judge" in role_id or "check" in role_id
            roles.append(RoleDef(
                role_id=role_id, reads_from=prior, exposes=(f"{role_id}-out",),
                verification_level=3 if grading else 1, max_iterations=2,
                output_kind="verdict" if grading else "text",
                goal=f"{role_id} performs its role in {record['title']!r}"))

    if not roles:
        raise ValueError(f"record {record['id']!r} declares no roles to bind")

    return HarnessSpec(
        harness_id=record["id"].replace(":", "-"), topology="chain",
        roles=tuple(roles), resources=(),
        iteration_budget=max(16, len(roles) * 2),
        artifact_role=roles[-1].role_id)


def _score_concepts(task: str) -> list[dict]:
    """Same lexical formula as loops/dataset/build.py's top_concepts and the
    maxey0 MCP server's manifest tag scoring: exact word match = 2.0,
    substring = 0.5 -- so a route_task decision is comparable to what
    maxey0_route would have scored for the same task text."""
    import re as _re

    lowered = task.lower()
    scored = []
    for concept in _maxey0_manifest()["concepts"]:
        score = 0.0
        for tag in concept.get("tags", []):
            tag_l = tag.lower()
            if _re.search(rf"\b{_re.escape(tag_l)}\b", lowered):
                score += 2.0
            elif tag_l in lowered:
                score += 0.5
        if score > 0:
            scored.append({"concept": concept["id"], "score": score})
    scored.sort(key=lambda x: -x["score"])
    return scored


def _find_loop_hit(concept_ids: set) -> Optional[dict]:
    candidates = [
        record for record in _loop_dataset()
        if record.get("execution_mode") == "in-window"
        and record.get("status") == "validated"
        and concept_ids & set(record.get("concept_tags", []))
    ]
    if not candidates:
        return None

    def rank(record: dict) -> tuple:
        overlap = len(concept_ids & set(record.get("concept_tags", [])))
        roles = len(record.get("hardening", {}).get("roles", []))
        return (-overlap, roles)

    candidates.sort(key=rank)
    return candidates[0]


def _bind_loop_hit(record: dict, prefix: str) -> dict:
    """Build the winning record's regions/harness/role bindings for real, in
    THIS live session window -- not a throwaway one -- so the caller gets an
    already-bound loop_id per role back. Every id is prefixed so repeated
    calls in the same session never collide."""
    import sys as _sys

    for extra in (str(_DATASET_DIR.parents[1]), str(_DATASET_DIR.parents[1] / "loops")):
        if extra not in _sys.path:
            _sys.path.insert(0, extra)
    from d4.harness_dsl import build_init_ops  # noqa: PLC0415

    spec = _spec_from_record(record)
    ops = build_init_ops(spec, "scw", {})

    def remap(value: Optional[str]) -> Optional[str]:
        return f"{prefix}{value}" if value else value

    bound_loop_ids: list[str] = []
    for op in ops:
        args = dict(op.get("args", {}))
        for key in ("scw_id", "parent_scw_id", "from_scw_id", "to_scw_id", "harness_id"):
            if key in args:
                args[key] = remap(args[key])
        if "loop_id" in args:
            args["loop_id"] = remap(args["loop_id"])
        if "parent_loop_id" in args and args["parent_loop_id"]:
            args["parent_loop_id"] = remap(args["parent_loop_id"])
        if "exposes" in args and args["exposes"]:
            args["exposes"] = [remap(name) for name in args["exposes"]]
        method = getattr(_session.window, op["op"])
        try:
            method(**args)
        except Exception:
            if op.get("expect_refusal"):
                continue
            raise
        else:
            if op["op"] == "bind_scope":
                bound_loop_ids.append(args["loop_id"])

    return {
        "harness_id": remap(spec.harness_id),
        "bound_loop_ids": bound_loop_ids,
        "region_map": [r for r in _session.window.region_map() if r["scw_id"].startswith(prefix)],
    }


@mcp.tool()
@_tool
def route_task(task: str) -> dict:
    """Route a task through the same pipeline described in
    /agentic-loops/agentic-loops.md: score it against Maxey0's concepts,
    check loops.json for an existing, hardened loop that already matches --
    if found, bind its regions/harness/roles live, right now, in this window
    -- else fall back to matching Maxey0 skills, then agents. Every decision,
    hit or fallback, is logged as a real event (route.hit /
    route.fallback_skill / route.fallback_agent) on this session's own
    window, so repeated routing over time is itself an auditable trace."""
    if not (_MAXEY0_ROOT / "manifest.json").exists():
        return {
            "ok": False, "error": "maxey0_root_not_found",
            "message": f"no manifest.json under {_MAXEY0_ROOT} -- route_task needs the Maxey0-OKF "
                       "bundle to score concepts.",
            "hint": "set MAXEY0_ROOT to the Maxey0-OKF bundle directory (the one containing "
                    "manifest.json), or run this server from a checkout with Maxey0/Maxey0 as a "
                    "sibling of scw-runtime.",
        }

    global _route_counter
    _route_counter += 1
    prefix = f"route{_route_counter}-"

    concept_scores = _score_concepts(task)
    top_concepts = {c["concept"] for c in concept_scores[:3]}

    hit = _find_loop_hit(top_concepts) if top_concepts else None
    if hit is not None:
        bound = _bind_loop_hit(hit, prefix)
        _session.window.log.emit("route.hit", "route_task", {
            "task": task, "concept_scores": concept_scores, "loop_id": hit["id"],
            "loop_title": hit["title"], **bound,
        })
        return {"decision": "loop_hit", "concept_scores": concept_scores, "loop": hit, **bound}

    skill_scores = []
    if top_concepts:
        for skill in _maxey0_manifest()["skills"]:
            if skill["concept"] not in top_concepts:
                continue
            score = 1.0 + sum(1.0 for tag in skill.get("tags", []) if tag.lower() in task.lower())
            skill_scores.append({"skill": skill["id"], "concept": skill["concept"], "score": score})
        skill_scores.sort(key=lambda x: -x["score"])

    if skill_scores:
        _session.window.log.emit("route.fallback_skill", "route_task", {
            "task": task, "concept_scores": concept_scores, "skills": skill_scores[:5],
        })
        return {"decision": "fallback_skill", "concept_scores": concept_scores, "skills": skill_scores[:5]}

    import re as _re
    words = [w for w in _re.findall(r"[a-z]+", task.lower()) if len(w) > 3]
    agent_scores = []
    for agent in _maxey0_registry()["agents"]:
        text = f"{agent.get('specialization', '')} {agent.get('name', '')}".lower()
        score = sum(1.0 for word in words if word in text)
        if score > 0:
            agent_scores.append({"agent": agent["registry_index"], "name": agent["name"], "score": score})
    agent_scores.sort(key=lambda x: -x["score"])

    _session.window.log.emit("route.fallback_agent", "route_task", {
        "task": task, "concept_scores": concept_scores, "agents": agent_scores[:5],
    })
    return {"decision": "fallback_agent", "concept_scores": concept_scores, "agents": agent_scores[:5]}


# ---------------------------------------------------------------------------
# resources
# ---------------------------------------------------------------------------
@mcp.resource("scw://window")
def resource_window() -> str:
    """Current window state as JSON — regions, loops, bridges, cache, advisories."""
    return json.dumps(_session.window.inspect(), indent=2)


@mcp.resource("scw://render")
def resource_render() -> str:
    """The window materialized as prompt text, exactly as a model would see it."""
    return _session.window.render(commit=False)["text"]


@mcp.resource("scw://events")
def resource_events() -> str:
    """The raw hash-chained event log for this run (JSONL)."""
    return "\n".join(json.dumps(r, separators=(",", ":")) for r in _session.window.log.records)


def main() -> None:
    """Run the server over stdio."""
    mcp.run()


if __name__ == "__main__":  # pragma: no cover
    main()
