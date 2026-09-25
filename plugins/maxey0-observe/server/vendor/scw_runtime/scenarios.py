"""The reference scenario: a grounded refinement loop over structured regions.

This is what ``scw demo`` runs and what ``examples/fixtures/demo.events.jsonl``
records. It is deliberately written to be read: it is the shortest honest
answer to "what does loop engineering on top of SCWs actually look like".

The window is laid out in tiers:

===============  ==========  =========================================
region           type        why it exists
===============  ==========  =========================================
turn-header      working     a 20-token "Turn N of 4" banner, placed
                             *first* on purpose — this is the layout
                             mistake the runtime is built to catch
system           reference   instructions; never changes
corpus           reference   retrieved material, with two nested chunks
memory           durable     keyed memory blocks the host maintains
run              episodic    the run's history, containing `critiques`
task             working     current task state, unbridgeable
pad              scratchpad  the loop's own region: volatile, 2 048-token
                             budget, cleared at every tick, purged on close
===============  ==========  =========================================

The loop is bound to ``pad``. Each iteration it drafts, discovers it cannot
read ``corpus`` from inside its scope, mints a one-iteration read bridge,
critiques its draft, promotes the critique into the episodic tier through a
second short-lived bridge, and ticks. The tick clears the pad and expires the
bridges, so the next iteration starts from the same clean state.

Along the way the log records all three kinds of refusal — out of scope, target
not bridgeable, and target read-only — because those are the events that prove
the walls are real.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .errors import IsolationViolation, PolicyViolation
from .events import EventLog
from .window import ContextWindow

ITERATIONS = 4
FORMATION_ITERATIONS = 2

SYSTEM_PROMPT = """\
You are an incident analyst. Work only from the retrieved corpus in scope.
Produce a summary that names: the trigger, the blast radius, the mitigation,
and the one change that would have prevented it. Cite chunk ids for every
claim. If the corpus does not support a claim, say so instead of inferring it.
Never speculate about individuals. Prefer the shortest phrasing that keeps the
causal chain intact.\
"""


def _chunk(chunk_id: str, subject: str, lines: int = 26) -> str:
    """Deterministic filler that reads like a retrieved document chunk."""
    body = [f"[{chunk_id}] {subject}"]
    for index in range(lines):
        body.append(
            f"{chunk_id}.{index:02d}  At T+{index * 3:>3}m the {subject} path reported "
            f"elevated latency on shard {index % 7}; retries climbed to "
            f"{40 + index * 3}/s and the queue depth held near {1200 + index * 90} "
            f"messages while the health check kept returning 200."
        )
    return "\n".join(body)


def retrieval_refine_loop(
    log_path: Optional[Path] = None,
    iterations: int = ITERATIONS,
    total_budget: int = 24_000,
    header_order: int = 5,
) -> ContextWindow:
    """Build the window, run the loop, return it. Emits the full event log.

    ``header_order`` is the whole experiment. At ``5`` the mutating banner
    renders before every stable region and no prefix survives an iteration; at
    ``60_000`` it renders last and the stable tiers stay cached. Nothing else
    about the run changes — same regions, same writes, same reads.
    """
    window = ContextWindow(
        total_budget=total_budget,
        event_log=EventLog(path=log_path) if log_path is not None else None,
        name="incident-summary",
    )

    # -- structure -------------------------------------------------------
    # `order=5` puts this banner ahead of every stable region. That is the
    # bug; the runtime will price it for us at every tick.
    window.create_scw("Turn header", "working", scw_id="turn-header", order=header_order)

    window.create_scw("System instructions", "reference", scw_id="system")
    corpus = window.create_scw("Retrieved corpus", "reference", scw_id="corpus")
    window.create_scw("Chunk A — checkout latency", "reference",
                      scw_id="corpus-a", parent_scw_id=corpus.scw_id)
    window.create_scw("Chunk B — queue saturation", "reference",
                      scw_id="corpus-b", parent_scw_id=corpus.scw_id)

    window.create_scw("Durable memory", "durable", scw_id="memory")
    run = window.create_scw("Run history", "episodic", scw_id="run")
    window.create_scw("Critiques", "episodic", scw_id="critiques", parent_scw_id=run.scw_id)
    window.create_scw("Task state", "working", scw_id="task")
    window.create_scw("Scratchpad", "scratchpad", scw_id="pad")

    # -- seed the read-only tier (host only; a loop cannot write here) ----
    window.write("system", SYSTEM_PROMPT)
    window.write("corpus-a", _chunk("A1", "checkout"))
    window.write("corpus-b", _chunk("B1", "queue"))
    window.write("task", "goal: one-paragraph incident summary, cited\nstatus: drafting")
    window.write("memory", "prefers terse output, no bullet lists", key="style")

    # -- bind the loop's execution scope to one region -------------------
    window.bind_scope("refine", "pad", descend=True, max_iterations=iterations)

    for iteration in range(1, iterations + 1):
        # The host rewrites the banner every turn. Twenty tokens, position 0.
        window.write(
            "turn-header",
            f"Turn {iteration} of {iterations} · task=incident-summary",
            mode="replace",
        )

        window.write(
            "pad",
            f"draft {iteration}: checkout latency rose first, queue saturation followed",
            key="draft",
            loop_id="refine",
        )

        if iteration == 1:
            # Three refusals, one per enforcement path. Each is logged.
            try:
                window.read("corpus", loop_id="refine")
            except IsolationViolation:
                pass  # out of scope: no bridge grants it
            try:
                window.open_bridge("pad", "task", mode="read",
                                   reason="peek at task state", loop_id="refine")
            except PolicyViolation:
                pass  # `task` is a working region: bridgeable=false
            try:
                window.open_bridge("pad", "system", mode="read_write",
                                   reason="edit instructions", loop_id="refine")
            except PolicyViolation:
                pass  # `system` is read-only: a write grant cannot exist

        # Legitimate crossing: one iteration of read access to the corpus.
        read_grant = window.open_bridge(
            "pad", "corpus", mode="read", reason="ground the draft in retrieved chunks",
            ttl_ticks=1, loop_id="refine",
        )
        window.read("corpus", loop_id="refine")

        window.write(
            "pad",
            f"critique {iteration}: claim 2 has no chunk id; tighten the causal chain",
            key="critique",
            loop_id="refine",
        )

        if iteration == 3:
            # Overrun the scratchpad budget on purpose: FIFO eviction fires and
            # the oldest entries are dropped rather than the window blowing up.
            window.write(
                "pad",
                "\n".join(f"trace {n:03d}: rejected rewrite candidate" for n in range(140)),
                loop_id="refine",
            )

        # Promotion: what survives the iteration crosses into the episodic
        # tier, through a grant that is closed as soon as it is used.
        write_grant = window.open_bridge(
            "pad", "critiques", mode="write", reason="promote surviving critique",
            ttl_ticks=1, loop_id="refine",
        )
        window.promote("pad", "critiques", keys=["critique"], loop_id="refine", mode="copy")
        window.close_bridge(write_grant.bridge_id, loop_id="refine")

        if iteration == 2:
            # The host updates a durable memory block mid-run. It sits ahead of
            # the episodic and working tiers, so it invalidates them too.
            window.write("memory", "incident class: cascading backpressure", key="finding")

        window.render(loop_id="refine")
        window.loop_tick("refine", note=f"iteration {iteration} complete")
        _ = read_grant  # expired by the tick above

    window.unbind_scope("refine")
    window.write("task", "status: complete", mode="replace")
    window.close_scw("pad")     # purge_on_close: the scratchpad is destroyed
    window.close_scw("task")    # sealed: content kept, no further writes
    return window


ACCEPTANCE_SPEC = """\
Acceptance criterion -- an implementer's patch is ACCEPTED when the checker's
verdict, graded against this spec alone, says so. The checker never receives
the implementer's scratch reasoning, only what the implementer chooses to
publish to `work`.\
"""


def three_agent_loop(
    log_path: Optional[Path] = None,
    max_iterations: int = FORMATION_ITERATIONS,
) -> ContextWindow:
    """The planner / implementer / checker formation.

    The maker/checker rule -- "the maker is not the checker" -- is enforced
    structurally here, not by convention: each role is bound to its own
    scratchpad (never readable by anyone else, `bridgeable=False` by the
    scratchpad preset), and only what a role explicitly promotes into its
    shared handoff region (``plan`` / ``work`` / ``findings``) is visible
    downstream. This mirrors :func:`retrieval_refine_loop`'s bind-to-pad,
    promote-via-bridge shape rather than binding a loop directly to a shared
    region, which is what makes "checker cannot read the implementer's
    reasoning" a wall instead of a request.

    ===========  ==========  =====================================
    region       type        why it exists
    ===========  ==========  =====================================
    spec         reference   acceptance criterion; no loop may write it
    plan         durable     planner's published strategy
    work         working     implementer's published patch (bridgeable
                              overridden true -- the default `working`
                              preset is unbridgeable, but the checker
                              must legitimately reach this one)
    findings     episodic    checker's published verdict
    pad-plan     scratchpad  planner's private reasoning
    pad-impl     scratchpad  implementer's private reasoning
    pad-check    scratchpad  checker's private reasoning
    ===========  ==========  =====================================

    Two refusals are demonstrated before any legitimate work happens: nobody
    can mint a write grant into ``spec`` (a reference region admits no write
    grant, regardless of who asks), and the checker cannot bridge into
    ``pad-impl`` (scratchpads are never bridgeable, so there is no grant to
    mint in the first place -- a :class:`PolicyViolation`, not merely a
    denied request).
    """
    window = ContextWindow(
        total_budget=24_000,
        event_log=EventLog(path=log_path) if log_path is not None else None,
        name="three-agent-loop",
    )

    # -- structure ---------------------------------------------------------
    window.create_scw("Acceptance spec", "reference", scw_id="spec")
    window.create_scw("Plan", "durable", scw_id="plan")
    window.create_scw("Work", "working", scw_id="work", policy={"bridgeable": True})
    window.create_scw("Findings", "episodic", scw_id="findings")
    window.create_scw("Planner pad", "scratchpad", scw_id="pad-plan")
    window.create_scw("Implementer pad", "scratchpad", scw_id="pad-impl")
    window.create_scw("Checker pad", "scratchpad", scw_id="pad-check")

    # Host-only write, before any bind_scope: the acceptance spec is seeded
    # once and never touched by a bound loop again.
    window.write("spec", ACCEPTANCE_SPEC)

    window.create_harness(
        "Planner/implementer/checker formation",
        architecture="maker_checker",
        harness_id="three-agent-loop",
        iteration_budget=16,
    )

    window.bind_scope(
        "planner", "pad-plan", max_iterations=max_iterations,
        harness_id="three-agent-loop", verification_level=2,
        goal="Plan a fix strategy in prose, without writing code",
    )
    window.bind_scope(
        "implementer", "pad-impl", max_iterations=max_iterations,
        harness_id="three-agent-loop", verification_level=1,
        goal="Implement the planner's strategy as a patch",
    )
    # The checker must still resolve as a currently-bound loop when it judges
    # the implementer's LAST iteration's verdict tick, which happens right
    # after the checker's own same-numbered tick -- so the checker (and the
    # planner, for the same reason on the boundary) gets one iteration of
    # headroom rather than exhausting on the very tick whose verdict is
    # about to reference it.
    window.bind_scope(
        "checker", "pad-check", max_iterations=max_iterations + 1,
        harness_id="three-agent-loop", verification_level=4,
        goal="Verify the implementer's patch against the acceptance spec",
    )

    accepted_any = False
    for iteration in range(1, max_iterations + 1):
        if iteration == 1:
            # -- the two structural refusals, demonstrated once ------------
            for role, pad in (
                ("planner", "pad-plan"), ("implementer", "pad-impl"), ("checker", "pad-check"),
            ):
                try:
                    window.open_bridge(pad, "spec", mode="write",
                                       reason=f"{role} attempts to edit the acceptance spec",
                                       loop_id=role)
                except PolicyViolation:
                    pass  # reference admits no write grant, for anyone
            try:
                window.open_bridge("pad-check", "pad-impl", mode="read",
                                   reason="checker attempts to read implementer's reasoning",
                                   loop_id="checker")
            except PolicyViolation:
                pass  # scratchpads are never bridgeable: no grant to mint

        # -- planner: draft, publish -------------------------------------
        window.write("pad-plan", f"strategy {iteration}: patch the off-by-one in the ledger totals",
                     key="draft", loop_id="planner")
        plan_grant = window.open_bridge("pad-plan", "plan", mode="write",
                                        reason="publish the plan", ttl_ticks=1, loop_id="planner")
        window.promote("pad-plan", "plan", keys=["draft"], loop_id="planner", mode="copy")
        window.close_bridge(plan_grant.bridge_id, loop_id="planner")
        window.render(loop_id="planner")
        window.loop_tick("planner", note=f"iteration {iteration}: plan published")

        # -- implementer: read spec + plan, implement, publish -----------
        spec_grant = window.open_bridge("pad-impl", "spec", mode="read",
                                        reason="read the acceptance spec", ttl_ticks=1,
                                        loop_id="implementer")
        window.read("spec", loop_id="implementer")
        window.close_bridge(spec_grant.bridge_id, loop_id="implementer")
        plan_read = window.open_bridge("pad-impl", "plan", mode="read",
                                       reason="read the planner's strategy", ttl_ticks=1,
                                       loop_id="implementer")
        window.read("plan", loop_id="implementer")
        window.close_bridge(plan_read.bridge_id, loop_id="implementer")
        window.write("pad-impl", f"reasoning {iteration}: totals loop should be range(n), not range(n-1)",
                     key="reasoning", loop_id="implementer")
        window.write("pad-impl", f"patch {iteration}: fix ledger.py totals loop bound", key="patch",
                     loop_id="implementer")
        work_grant = window.open_bridge("pad-impl", "work", mode="write",
                                        reason="publish the patch", ttl_ticks=1,
                                        loop_id="implementer")
        window.promote("pad-impl", "work", keys=["patch"], loop_id="implementer", mode="copy")
        window.close_bridge(work_grant.bridge_id, loop_id="implementer")

        # -- checker: read only the published patch, verdict, publish ----
        work_read = window.open_bridge("pad-check", "work", mode="read",
                                       reason="read the published patch", ttl_ticks=1,
                                       loop_id="checker")
        window.read("work", loop_id="checker")
        window.close_bridge(work_read.bridge_id, loop_id="checker")
        verified = iteration == max_iterations  # accept on the last pass
        window.write("pad-check",
                     f"verdict {iteration}: {'matches' if verified else 'does not yet match'} "
                     "acceptance spec R-1..R-4",
                     key="verdict", loop_id="checker")
        findings_grant = window.open_bridge("pad-check", "findings", mode="write",
                                            reason="publish the verdict", ttl_ticks=1,
                                            loop_id="checker")
        window.promote("pad-check", "findings", keys=["verdict"], loop_id="checker", mode="copy")
        window.close_bridge(findings_grant.bridge_id, loop_id="checker")
        window.render(loop_id="checker")
        window.loop_tick("checker", note=f"iteration {iteration}: reviewed implementer's patch")

        # The verdict lands on the implementer's own tick, disjointness-
        # checked against the checker's distinct, currently-bound loop --
        # this is the "type error, not a convention" the formation exists
        # to prove.
        window.render(loop_id="implementer")
        window.loop_tick(
            "implementer", note=f"iteration {iteration}: checker verdict recorded",
            verified=verified, verified_by="checker" if verified else None,
        )
        accepted_any = accepted_any or verified

    window.unbind_scope("implementer", terminal_state="success" if accepted_any else "exhausted")
    window.unbind_scope("checker", terminal_state="no_op")
    window.unbind_scope("planner", terminal_state="no_op")
    return window
