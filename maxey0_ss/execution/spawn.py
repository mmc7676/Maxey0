"""The spawn algebra: when to partition, when to spawn, and where it stops.

A formation that grows by spawning sub-formations needs three things decided
before it starts, or it is not an algorithm — it is a recursion with no base
case wearing an architecture diagram.

    1. SHAPE      what structure this task warrants
    2. DESCENT    what happens when a step hits an issue
    3. BOUND      why the whole thing terminates

Each is a function here, not a field a reader is expected to honor. The repo
already carries labels nothing reads — `topology` on every loop record has zero
readers — so a rule stated and not evaluated is the failure mode this module
exists to avoid.

Notation, for the record:

    C           the agent doing the work
    T           a task
    κ           a constitution (reach and caps), as in containment.hierarchy
    σ(T)        the shape function          -> ∅ | a | l | SCW⟨·⟩
    i           an issue encountered while executing a step
    d           depth below the root

    Run(T, d, κ):
        for each step s of σ(T):
            on issue i:  Run(i, d+1, κ.derive(reach(i)))   and resume s

The descent is the self-progressing part: an issue is itself a task, so the
same function handles it, one level down and under a *narrower* constitution.
Because derivation only narrows, induction gives the containment property for
the whole tree from the grant at the root.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Shape(str, Enum):
    """What structure a task warrants. The output of `shape()`."""

    #: Do it in the calling window. No agent, no partition.
    INLINE = "inline"
    #: One subagent. The check verifies; a second opinion adds cost, not information.
    SINGLE = "single"
    #: Maker and checker. The cheapest manufactured verification there is.
    PAIR = "pair"
    #: Maker, checker, judge. For claims nothing mechanical can settle.
    LOOP = "loop"


#: Roles dispatched for each shape, in order.
ROLES: dict[Shape, tuple[str, ...]] = {
    Shape.INLINE: (),
    Shape.SINGLE: ("maker",),
    Shape.PAIR: ("maker", "checker"),
    Shape.LOOP: ("maker", "checker", "judge"),
}


@dataclass(frozen=True)
class Task:
    """A unit of work, described by the two properties that decide its shape.

    `checkability` is M: 1.0 when a deterministic check exists (a test, an exit
    code, a count that is zero or is not), 0.0 when the output is a judgement no
    artifact can settle. `stakes` is V: what a wrong answer costs.
    """

    name: str
    checkability: float = 1.0
    stakes: float = 0.0
    #: Two or more consumers of context that must not see each other.
    encapsulation: bool = False
    #: Something downstream must later answer "why did this happen".
    observability: bool = False
    #: Produces an effect that cannot be undone.
    irreversible: bool = False
    #: Trivial enough that no agent is warranted at all.
    trivial: bool = False

    def __post_init__(self) -> None:
        for name in ("checkability", "stakes"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must lie in [0, 1], got {value}")


def needs_window(task: Task) -> bool:
    """G(T) — the SCW0 deployment predicate.

        G(T) = E(T) ∨ O(T) ∨ I(T)

    Encapsulation, observability, irreversibility. Any one forces a window; none
    of them makes a window overhead. The asymmetry that decides most real cases
    is that evidence cannot be produced after the fact — so where an effect is
    irreversible and anything might later ask why, there is nothing to compare.
    """
    return task.encapsulation or task.observability or task.irreversible


def effort(task: Task) -> float:
    """E ∝ V / M — what a wrong answer costs, over how checkable it is.

    A deterministic check collapses the requirement to nothing, however
    important the task feels. An unverifiable judgement raises it to meet the
    stakes, because verification has to be manufactured rather than found.
    """
    if task.checkability >= 1.0:
        return 0.0
    return task.stakes / max(task.checkability, 1e-9)


#: Effort above which a judge is warranted rather than a lone checker.
JUDGE_THRESHOLD = 4.0
#: Effort above which any second opinion is warranted at all.
CHECKER_THRESHOLD = 1.0


def shape(task: Task) -> Shape:
    """σ(T) — the structure this task warrants.

    Encapsulation is not an effort question. Two consumers that must not see
    each other need separate windows whatever the checkability, so it forces at
    least a pair regardless of E.
    """
    if task.trivial and not needs_window(task):
        return Shape.INLINE
    weight = effort(task)
    if task.irreversible and weight >= CHECKER_THRESHOLD:
        return Shape.LOOP
    if weight >= JUDGE_THRESHOLD:
        return Shape.LOOP
    if weight >= CHECKER_THRESHOLD or task.encapsulation:
        return Shape.PAIR
    return Shape.SINGLE


# --- the bound ---------------------------------------------------------------


def max_formation(breadth: int | None, depth: int | None, total: int | None) -> float:
    """The largest formation the caps permit, counting the root.

    A depth-`D` tree of branching factor `B` holds at most the geometric sum

        (B^(D+1) − 1) / (B − 1)

    and `total` caps it independently. The smallest of the three governs. An
    absent cap contributes infinity, which is why a formation with no caps has
    no bound — the honest answer rather than a large default.
    """
    limits: list[float] = []
    if total is not None:
        limits.append(float(total + 1))  # descendants, plus the root
    if breadth is not None and depth is not None:
        if breadth <= 1:
            limits.append(float(depth + 1))
        else:
            limits.append((breadth ** (depth + 1) - 1) / (breadth - 1))
    return min(limits) if limits else float("inf")


def terminates(breadth: int | None, depth: int | None, total: int | None) -> bool:
    """Whether the spawn recursion has a base case at all.

    Depth alone is enough: an unbounded-breadth tree of bounded depth is finite
    only if breadth is also bounded, but a total cap bounds everything.
    """
    return max_formation(breadth, depth, total) < float("inf")


# --- the descent -------------------------------------------------------------


@dataclass
class Step:
    """One dispatched role, and whatever it spawned to get unblocked."""

    task: str
    role: str
    depth: int
    issues: list["Step"] = field(default_factory=list)


@dataclass
class Plan:
    """The tree the algorithm would produce. Computed before anything is spent."""

    root: str
    steps: list[Step] = field(default_factory=list)
    refused: list[tuple[str, str]] = field(default_factory=list)

    def size(self) -> int:
        def count(steps: list[Step]) -> int:
            return sum(1 + count(s.issues) for s in steps)

        return count(self.steps)

    def max_depth(self) -> int:
        def deepest(steps: list[Step]) -> int:
            return max((max(s.depth, deepest(s.issues)) for s in steps), default=0)

        return deepest(self.steps)


def plan(
    task: Task,
    issues: dict[str, list[Task]] | None = None,
    *,
    breadth: int | None = None,
    depth: int | None = None,
    total: int | None = None,
) -> Plan:
    """Expand the recursion to a plan, refusing to exceed the caps.

    `issues` maps a task name to the issues its execution is expected to raise.
    Each issue is itself a task, shaped by the same function and expanded one
    level down — the inward loop, made explicit rather than described.

    Refusals are collected rather than raised. A plan that reports what it had
    to decline is more useful than one that dies at the first cap, because the
    caps are the thing being evaluated.
    """
    issues = issues or {}
    result = Plan(root=task.name)
    budget = max_formation(breadth, depth, total)
    # A running total, not result.size(). result.steps is assigned only after
    # the top-level expand returns, so reading it during expansion sees zero and
    # the cap never binds on anything nested.
    spent = 0

    def expand(current: Task, d: int) -> list[Step]:
        nonlocal spent
        if depth is not None and d > depth:
            result.refused.append((current.name, f"depth {d} exceeds cap {depth}"))
            return []
        chosen = shape(current)
        roles = ROLES[chosen]
        if not roles:
            # An inline task runs in the calling window, but an issue raised
            # under it is still an issue. Dropping it silently would hide the
            # descent this function exists to make explicit.
            pending = [i for key, group in issues.items()
                       if key.startswith(f"{current.name}:") for i in group]
            if pending:
                result.refused.append(
                    (current.name,
                     f"shape is {chosen.value}; {len(pending)} issue(s) have no role to carry them")
                )
            return []
        if breadth is not None and len(roles) > breadth:
            result.refused.append(
                (current.name, f"{len(roles)} roles exceed breadth cap {breadth}")
            )
            roles = roles[:breadth]
        steps: list[Step] = []
        for role in roles:
            if spent + 1 > budget:
                result.refused.append((current.name, f"formation cap {budget:.0f} reached"))
                break
            spent += 1
            step = Step(task=current.name, role=role, depth=d)
            for issue in issues.get(f"{current.name}:{role}", []):
                step.issues.extend(expand(issue, d + 1))
            steps.append(step)
        return steps

    result.steps = expand(task, 0)
    return result


# --- the cost ----------------------------------------------------------------


def supplied_cost(roles: int, per_role: int, shared: int) -> dict[str, int]:
    """What a formation pays for knowledge, and what the sharing would save.

        Cost = Σ_r Σ_α |α| · 1[allow(r, scw(α))]

    Every role pays for every artifact its charter grants it. `shared` is the
    part every role receives, which is the only part a prefix cache could ever
    reuse — and the part that is currently billed once per role.
    """
    if roles < 0:
        raise ValueError(f"roles must not be negative, got {roles}")
    if roles == 0:
        # Shape.INLINE dispatches nobody, so nothing is supplied and nothing is
        # duplicated. Computing distinct as `shared` here made duplication
        # negative.
        return {"supplied": 0, "distinct": 0, "duplicated": 0, "shareable": 0}
    total = roles * (per_role + shared)
    distinct = roles * per_role + shared
    return {
        "supplied": total,
        "distinct": distinct,
        "duplicated": total - distinct,
        "shareable": shared * (roles - 1) if roles > 1 else 0,
    }


__all__ = [
    "CHECKER_THRESHOLD",
    "JUDGE_THRESHOLD",
    "ROLES",
    "Plan",
    "Shape",
    "Step",
    "Task",
    "effort",
    "max_formation",
    "needs_window",
    "plan",
    "shape",
    "supplied_cost",
    "terminates",
]
