"""Closures over the region graph, and the maker/judge disjointness proof.

:mod:`scw_runtime.isolation` answers one question at a time — *may this call
touch that region?* This module answers the question the first one cannot:
*what is the whole set of regions this loop could reach, and does it overlap
with another loop's?*

That second question is the one the reward-hacking literature actually poses.
The documented failure is not "the same agent approved itself"; it is that a
generator and a judge sharing context produces an inflated score, and the
mitigation is described as structural rather than exhortative. A runtime that
only compares two identifier strings implements the exhortation, not the
structure: rename the judge and the check passes while the shared context —
the thing that causes the failure — is untouched.

So the enforcement here is over the graph. A verdict is refused unless the
judge's **read closure** provably excludes the maker's **write closure**,
except for the regions the maker's host explicitly published as its handoff
surface.

Three definitions do the work.

**Read closure.** Every region a loop can obtain bytes from: its bound region,
that region's subtree when it bound with ``descend``, and — for each open
grant — the grant's target plus the part of that target's subtree a grant can
legitimately expose. That last clause is the subtle one and it is a fix, not a
flourish: a read renders a whole subtree, so a grant into a bridgeable parent
used to hand back the contents of children that had declared
``bridgeable=False``. A region that refuses grants must refuse them through
its parent too, or the declaration means nothing.

**Write closure.** Every region a loop can put bytes into: the same reachable
set minus anything read-only, plus grant targets that carry a write mode. Note
the asymmetry — a read grant exposes a subtree, a write grant exposes exactly
one region, because that is what :meth:`Scope.check` allows.

**Exposure.** ``Loop.exposes`` is the maker's declared handoff surface: the
regions a judge is *supposed* to see. It is host-authored at bind and cannot
be widened by the loop it constrains, which is the whole reason the proof is
worth anything — a party that can widen its own exposure set can satisfy any
disjointness rule vacuously.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from .isolation import descendants

if TYPE_CHECKING:  # pragma: no cover
    from .model import Loop
    from .window import ContextWindow


def record_exposure_ceiling(
    window: "ContextWindow", scw_id: str, exposed: "tuple[str, ...]"
) -> None:
    """Narrow a scope root's handoff-surface ceiling to ``exposed``.

    Called on every successful bind, and by :mod:`scw_runtime.replay` folding a
    ``loop.bind`` record, so the ceiling is derived state that reconstructs
    exactly from the log. Replay does not *enforce* it — a log records what
    happened, and re-refusing a binding that already succeeded would make a
    valid log unreplayable.

    Monotone by construction: the stored value is only ever replaced by the set
    just declared, and :meth:`ContextWindow.bind_scope` has already refused
    anything wider.
    """
    window.exposure_ceiling[scw_id] = tuple(exposed)


def grant_visible_subtree(window: "ContextWindow", root: str) -> set[str]:
    """``root`` plus the descendants a *grant* may legitimately expose.

    Descent stops at any region declaring ``bridgeable=False``: such a region
    is unreachable from outside "from anyone, ever", and being nested under a
    bridgeable parent does not change that. Its own subtree is excluded with
    it, since the only way to reach a grandchild is through the child.
    """
    visible = {root}
    stack = list(window.regions[root].children) if root in window.regions else []
    while stack:
        current = stack.pop()
        region = window.regions.get(current)
        if region is None or not region.policy.bridgeable:
            continue
        if current in visible:
            continue
        visible.add(current)
        stack.extend(region.children)
    return visible


def own_reachable(window: "ContextWindow", loop: "Loop") -> set[str]:
    """The loop's own partition: its bound region, plus its subtree if it
    bound with ``descend``. Nothing here is pruned — this is the loop's own
    territory, and a ``bridgeable=False`` child inside it is walled against
    *outsiders*, not against its owner."""
    if loop.scw_id not in window.regions:
        return set()
    out = {loop.scw_id}
    if loop.descend:
        out |= descendants(window, loop.scw_id)
    return out


def read_closure(window: "ContextWindow", loop_id: Optional[str]) -> set[str]:
    """Every region ``loop_id`` can obtain bytes from right now.

    ``None`` (the unbound host) reaches everything, which is exactly why
    ``strict_scope`` exists — see :meth:`ContextWindow.render`.
    """
    if loop_id is None:
        return set(window.regions)
    loop = window.loops.get(loop_id)
    if loop is None or loop.status != "bound":
        return set()
    out = own_reachable(window, loop)
    holders = set(out)
    for bridge in window.bridges.values():
        if bridge.status != "open" or not bridge.grants("read"):
            continue
        if bridge.from_scw_id in holders and bridge.to_scw_id in window.regions:
            out |= grant_visible_subtree(window, bridge.to_scw_id)
    return out


def write_closure(window: "ContextWindow", loop_id: Optional[str]) -> set[str]:
    """Every region ``loop_id`` can put bytes into right now.

    Read-only regions are excluded even when reachable: a bound loop is
    refused a write to them regardless of scope, which is what makes an
    acceptance criterion held in a ``reference`` region worth pinning.
    """
    if loop_id is None:
        return {
            scw_id
            for scw_id, region in window.regions.items()
            if region.lifecycle == "open"
        }
    loop = window.loops.get(loop_id)
    if loop is None or loop.status != "bound":
        return set()
    reachable = own_reachable(window, loop)
    out = set()
    for scw_id in reachable:
        region = window.regions[scw_id]
        if region.lifecycle == "open" and region.policy.mutability != "readonly":
            out.add(scw_id)
    for bridge in window.bridges.values():
        if bridge.status != "open" or not bridge.grants("write"):
            continue
        target = window.regions.get(bridge.to_scw_id)
        if bridge.from_scw_id not in reachable or target is None:
            continue
        # A write grant exposes exactly its target, never a subtree — that is
        # what Scope.check allows, and the closure must not claim more.
        if target.lifecycle == "open" and target.policy.mutability != "readonly":
            out.add(bridge.to_scw_id)
    return out


def loop_ancestors(window: "ContextWindow", loop_id: str) -> list[str]:
    """Root-first chain of loops above ``loop_id`` in the control-flow tree."""
    chain: list[str] = []
    seen = set()
    current = window.loops.get(loop_id)
    while current is not None and current.parent_loop_id is not None:
        parent = current.parent_loop_id
        if parent in seen:  # a cycle already in state; stop rather than hang
            break
        seen.add(parent)
        chain.append(parent)
        current = window.loops.get(parent)
    chain.reverse()
    return chain


def loop_descendants(window: "ContextWindow", loop_id: str) -> set[str]:
    """Every loop beneath ``loop_id`` in the control-flow tree."""
    out: set[str] = set()
    loop = window.loops.get(loop_id)
    stack = list(loop.child_loop_ids) if loop is not None else []
    while stack:
        current = stack.pop()
        if current in out:
            continue
        out.add(current)
        child = window.loops.get(current)
        if child is not None:
            stack.extend(child.child_loop_ids)
    return out


def disjointness(window: "ContextWindow", maker_id: str, judge_id: Optional[str]) -> dict:
    """Decide whether ``judge_id`` may grade ``maker_id``, and say why.

    Pure: mutates nothing, callable at any time, and returns the same report
    the refusal carries — so an operator can ask "would this verdict be
    accepted, and what exactly would I have to change?" before running the
    iteration rather than after it is refused.

    The five rules, weakest first. Each is a distinct way two roles can turn
    out to be one role wearing two names.
    """
    maker = window.loops.get(maker_id)
    rules: list[dict] = []

    def rule(code: str, ok: bool, detail: str, **extra: object) -> None:
        rules.append({"rule": code, "ok": ok, "detail": detail, **extra})

    # R1 — the judge is a real, currently bound, distinct actor.
    judge = window.loops.get(judge_id) if judge_id else None
    resolvable = judge is not None and judge.status == "bound"
    if judge_id is None or judge_id == maker_id:
        rule(
            "R1.identity",
            False,
            f"no distinct judge was named; the verdict is attributed to {maker_id!r} itself",
            judge=judge_id,
        )
    elif not resolvable:
        rule(
            "R1.identity",
            False,
            f"{judge_id!r} does not resolve to a currently bound loop, so it names nobody "
            f"the runtime can hold to a context boundary",
            judge=judge_id,
            known_bound=sorted(
                lid for lid, lp in window.loops.items() if lp.status == "bound"
            ),
        )
    else:
        rule("R1.identity", True, f"{judge_id!r} is a distinct, bound loop", judge=judge_id)

    if maker is None:
        rule("R0.maker", False, f"no loop {maker_id!r}")
        return _report(maker_id, judge_id, rules)

    # R2 — the judge is not inside the maker's control flow (or vice versa).
    if resolvable:
        below = judge_id in loop_descendants(window, maker_id)
        above = maker_id in loop_descendants(window, judge_id)
        rule(
            "R2.control_flow",
            not (below or above),
            (
                f"{judge_id!r} is a sub-loop of {maker_id!r}; a loop the maker spawned and "
                f"bounds is the maker grading itself with extra steps"
                if below
                else f"{maker_id!r} is a sub-loop of {judge_id!r}; the judge owns the maker's "
                f"control flow and its budget"
                if above
                else "neither loop is an ancestor of the other"
            ),
        )

        # R3 — not literally the same region.
        rule(
            "R3.distinct_root",
            judge.scw_id != maker.scw_id,
            (
                f"both loops are bound to region {maker.scw_id!r} — one context, two names"
                if judge.scw_id == maker.scw_id
                else f"maker is bound to {maker.scw_id!r}, judge to {judge.scw_id!r}"
            ),
        )

        # R4 — the actual overlap test.
        maker_writes = write_closure(window, maker_id)
        judge_reads = read_closure(window, judge_id)
        exposed = set(maker.exposes)
        overlap = (judge_reads & maker_writes) - exposed
        rule(
            "R4.exposure",
            not overlap,
            (
                f"the judge can read {sorted(overlap)}, which the maker can write and did not "
                f"declare as its handoff surface"
                if overlap
                else (
                    f"the judge's read closure meets the maker's write closure only inside the "
                    f"declared exposure {sorted(exposed & judge_reads & maker_writes)}"
                    if (exposed & judge_reads & maker_writes)
                    else "the judge's read closure and the maker's write closure are disjoint"
                )
            ),
            overlap=sorted(overlap),
            maker_write_closure=sorted(maker_writes),
            judge_read_closure=sorted(judge_reads),
            exposes=sorted(exposed),
        )

        # R5 — the maker cannot edit what it is graded against.
        if maker.criterion_id is not None:
            criterion = window.criteria.get(maker.criterion_id)
            reachable_criterion = (
                criterion is not None and criterion.scw_id in maker_writes
            )
            rule(
                "R5.criterion",
                not reachable_criterion,
                (
                    f"the maker can write region {criterion.scw_id!r}, which holds the "
                    f"criterion it is graded against"
                    if reachable_criterion
                    else f"criterion {maker.criterion_id!r} is outside the maker's write closure"
                ),
            )

    return _report(maker_id, judge_id, rules)


def _report(maker_id: str, judge_id: Optional[str], rules: list[dict]) -> dict:
    failed = [r for r in rules if not r["ok"]]
    return {
        "maker": maker_id,
        "judge": judge_id,
        "disjoint": not failed,
        "rules": rules,
        "failed": [r["rule"] for r in failed],
        "reason": failed[0]["detail"] if failed else "",
    }
