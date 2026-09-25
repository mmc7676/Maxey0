"""Constitutional hierarchy: a child SCW cannot exceed its parent.

`SCWSpec.parent_id` recorded a tree that no enforcement path consulted. Reach
was declared per instance, so a child could name a target its parent could not
reach, and a bridge could grant what the constitution never granted. The tree
was structure for display; it constrained nothing.

This module makes the tree load-bearing. Every SCW is chartered under a parent,
its constitution is *derived* from the parent's, and derivation can only narrow.
The invariant that follows by induction is the one that matters:

    reach(descendant) is a subset of reach(root), for every descendant.

Containment of an entire spawned formation therefore reduces to the reach
granted at the root. That is what makes SCW0 meaningful rather than decorative:
nothing beneath it can reach outside it, however deep it spawns.

Three things are enforced, because reach alone is not containment:

  - **Reach** — a child may narrow its inherited reach, never widen it, and a
    bridge may not exceed the constitution either.
  - **Extent** — depth, direct children and total descendants are capped, so a
    formation cannot exhaust the host by spawning within its rights.
  - **Persistence** — a breaker reads the attestation chain back and stops an
    instance that keeps attempting refused crossings.

Widening is *refused*, never clamped. Silently reducing a request to what the
parent allows would hide the attempt; refusing it produces a decision, and the
decision is evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from ..identity import validate_scw_reference
from .attestation import AttestationLog
from .protocol import ContainmentDecision, Operation

#: Reach value meaning "not constrained by a parent". Only a root may hold it.
UNBOUNDED: frozenset[str] | None = None


class ConstitutionViolation(RuntimeError):
    """A charter, bridge or registration asked for more than the parent holds.

    Carries the decision so the refusal is auditable rather than only raised.
    """

    def __init__(self, message: str, decision: ContainmentDecision | None = None) -> None:
        super().__init__(message)
        self.decision = decision


@dataclass(frozen=True)
class Constitution:
    """What an SCW may do, and how far it may spawn.

    `reach` is the set of SCW identifiers this window may name at all. `None`
    means unbounded, which only a root may hold — a chartered child always
    inherits a concrete set, because its parent has one or is itself the root
    that granted one.
    """

    reach: frozenset[str] | None = UNBOUNDED
    #: None means inherit. A plain ``True`` default would read every request
    #: that merely narrows reach as also asking to become bridgeable, and be
    #: refused under a parent that is not.
    bridgeable: bool | None = None
    max_depth: int | None = None
    max_children: int | None = None
    max_descendants: int | None = None

    @property
    def is_bridgeable(self) -> bool:
        """Resolved value. An unset constitution is bridgeable."""
        return True if self.bridgeable is None else self.bridgeable

    def permits(self, target: str) -> bool:
        return self.reach is None or target in self.reach

    def derive(self, requested: "Constitution | None" = None) -> "Constitution":
        """Return the child constitution, refusing anything wider than this one.

        A child that requests nothing inherits the parent unchanged. A child
        that requests a narrower reach or tighter caps gets what it asked for.
        A child that requests anything wider is refused.
        """
        if requested is None:
            return self

        if requested.reach is None:
            if self.reach is not None:
                raise ConstitutionViolation(
                    "a child cannot request unbounded reach under a bounded parent"
                )
            reach = None
        elif self.reach is None:
            reach = frozenset(requested.reach)
        else:
            excess = frozenset(requested.reach) - self.reach
            if excess:
                raise ConstitutionViolation(
                    f"child reach exceeds parent by {sorted(excess)}; "
                    f"a child may narrow inherited reach, never widen it"
                )
            reach = frozenset(requested.reach)

        if requested.bridgeable is None:
            bridgeable = self.is_bridgeable
        elif requested.bridgeable and not self.is_bridgeable:
            raise ConstitutionViolation(
                "a child cannot be bridgeable under a parent that is not"
            )
        else:
            bridgeable = requested.bridgeable

        return Constitution(
            reach=reach,
            bridgeable=bridgeable,
            max_depth=_tighter(self.max_depth, requested.max_depth),
            max_children=_tighter(self.max_children, requested.max_children),
            max_descendants=_tighter(self.max_descendants, requested.max_descendants),
        )


def _tighter(parent: int | None, child: int | None) -> int | None:
    """The stricter of two caps. Absent means unconstrained, so the other wins."""
    if parent is None:
        return child
    if child is None:
        return parent
    return min(parent, child)


def _intersect(parent: Constitution, child: Constitution) -> Constitution:
    """Clip an existing grant to what the parent now allows.

    Distinct from `derive`, and deliberately so. `derive` refuses a widening
    *request* at charter time, because a refusal there is a decision worth
    recording. This handles an existing grant the parent has since revoked —
    where refusing would leave the tree in the inconsistent state the revocation
    was meant to remove. Clipping is the only outcome that restores the
    invariant, so it clips.
    """
    if parent.reach is None:
        reach = child.reach
    elif child.reach is None:
        reach = parent.reach
    else:
        reach = child.reach & parent.reach
    return Constitution(
        reach=reach,
        bridgeable=child.is_bridgeable and parent.is_bridgeable,
        max_depth=_tighter(parent.max_depth, child.max_depth),
        max_children=_tighter(parent.max_children, child.max_children),
        max_descendants=_tighter(parent.max_descendants, child.max_descendants),
    )


@dataclass
class _Node:
    scw_id: str
    parent_id: str | None
    constitution: Constitution
    depth: int
    children: list[str] = field(default_factory=list)


class ConstitutionTree:
    """The chartered SCW hierarchy, and the only authority on reach.

    Kept separate from the containment provider so that a deployment may swap
    the enforcement engine without losing the hierarchy, and so the invariant
    can be tested on its own.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, _Node] = {}

    # -- construction -------------------------------------------------------

    def charter_root(self, scw_id: str, constitution: Constitution | None = None) -> Constitution:
        """Register the root of a formation. Its constitution bounds everything below."""
        validate_scw_reference(scw_id)
        if scw_id in self._nodes:
            raise ConstitutionViolation(f"{scw_id} is already chartered")
        granted = constitution if constitution is not None else Constitution()
        self._nodes[scw_id] = _Node(scw_id, None, granted, depth=0)
        return granted

    def charter(
        self, scw_id: str, parent_id: str, requested: Constitution | None = None
    ) -> Constitution:
        """Charter a child under a parent, deriving and capping its constitution."""
        validate_scw_reference(scw_id)
        validate_scw_reference(parent_id)
        if scw_id == parent_id:
            raise ConstitutionViolation(f"{scw_id} cannot be its own parent")
        if scw_id in self._nodes:
            raise ConstitutionViolation(f"{scw_id} is already chartered")

        parent = self._nodes.get(parent_id)
        if parent is None:
            # Fail closed: an unchartered parent grants nothing, so nothing derives.
            raise ConstitutionViolation(
                f"parent {parent_id} is not chartered; a child cannot derive from an "
                f"absent constitution"
            )

        depth = parent.depth + 1
        limit = parent.constitution.max_depth
        if limit is not None and depth > limit:
            raise ConstitutionViolation(
                f"{scw_id} would sit at depth {depth}, past the inherited cap of {limit}"
            )

        cap = parent.constitution.max_children
        if cap is not None and len(parent.children) >= cap:
            raise ConstitutionViolation(
                f"{parent_id} already holds its limit of {cap} direct children"
            )

        # A descendant cap bounds the whole subtree of whoever set it, so every
        # ancestor holding one is checked against its own subtree. Testing only
        # the immediate parent would let a chain grow without limit: each new
        # node has no descendants of its own at the moment it charters a child.
        for ancestor in [parent_id, *self.ancestors(parent_id)]:
            node = self._nodes.get(ancestor)
            if node is None:
                continue
            total = node.constitution.max_descendants
            if total is not None and self.descendant_count(ancestor) >= total:
                raise ConstitutionViolation(
                    f"{ancestor} already holds its limit of {total} descendants"
                )

        granted = parent.constitution.derive(requested)
        self._nodes[scw_id] = _Node(scw_id, parent_id, granted, depth=depth)
        parent.children.append(scw_id)
        return granted

    # -- queries ------------------------------------------------------------

    def is_chartered(self, scw_id: str) -> bool:
        return scw_id in self._nodes

    def constitution_of(self, scw_id: str) -> Constitution | None:
        node = self._nodes.get(scw_id)
        return node.constitution if node else None

    def depth_of(self, scw_id: str) -> int | None:
        node = self._nodes.get(scw_id)
        return node.depth if node else None

    def parent_of(self, scw_id: str) -> str | None:
        node = self._nodes.get(scw_id)
        return node.parent_id if node else None

    def children_of(self, scw_id: str) -> list[str]:
        node = self._nodes.get(scw_id)
        return list(node.children) if node else []

    def ancestors(self, scw_id: str) -> list[str]:
        out: list[str] = []
        node = self._nodes.get(scw_id)
        while node is not None and node.parent_id is not None:
            out.append(node.parent_id)
            node = self._nodes.get(node.parent_id)
        return out

    def descendants(self, scw_id: str) -> list[str]:
        node = self._nodes.get(scw_id)
        if node is None:
            return []
        out: list[str] = []
        stack = list(node.children)
        while stack:
            current = stack.pop()
            out.append(current)
            stack.extend(self.children_of(current))
        return out

    def descendant_count(self, scw_id: str) -> int:
        return len(self.descendants(scw_id))

    def root_of(self, scw_id: str) -> str | None:
        if scw_id not in self._nodes:
            return None
        chain = self.ancestors(scw_id)
        return chain[-1] if chain else scw_id

    def permits(self, scw_id: str, target: str) -> bool:
        """Whether the chartered constitution lets `scw_id` name `target` at all.

        An unchartered SCW permits nothing. That is the fail-closed direction:
        a window nobody granted reach to has none.
        """
        node = self._nodes.get(scw_id)
        if node is None:
            return False
        if target == scw_id:
            return True
        return node.constitution.permits(target)

    def narrow(self, scw_id: str, requested: Constitution) -> Constitution:
        """Re-derive an SCW's constitution, and re-derive every descendant's.

        Narrowing one node alone would break the invariant this class exists to
        hold. A child chartered while the parent was wide keeps the wide reach,
        so after `narrow()` the subtree could name what the root no longer can —
        exactly the state an operator tightening a root in response to an
        incident would believe they had prevented.

        Each descendant is therefore re-derived against its updated parent.
        Re-derivation only narrows, so a descendant already inside the new
        bound is unchanged and one outside it is clipped to the intersection.
        """
        node = self._nodes.get(scw_id)
        if node is None:
            raise ConstitutionViolation(f"{scw_id} is not chartered")
        node.constitution = node.constitution.derive(requested)
        self._reseat(scw_id)
        return node.constitution

    def _reseat(self, scw_id: str) -> None:
        """Re-derive the subtree under `scw_id` against its parents, top down.

        Breadth-first so a node is always re-derived after its parent, and the
        intersection cascades the whole way down rather than one level.
        """
        queue = list(self._nodes[scw_id].children)
        while queue:
            current = queue.pop(0)
            child = self._nodes[current]
            parent = self._nodes[child.parent_id].constitution
            child.constitution = _intersect(parent, child.constitution)
            queue.extend(child.children)


class DenialBreaker:
    """Stops an instance that keeps attempting refused crossings.

    The attestation chain was write-only: every refusal was recorded and nothing
    read it back, so an agent could attempt a denied crossing without limit and
    the evidence only grew. This reads the chain and makes persistence itself a
    refusable condition.

    Containment bounds *what* can be reached. This bounds *how often* reaching
    can be attempted, which is the part a swarm exploits when every individual
    attempt is legitimately refused and nothing counts them.
    """

    #: Operations that represent an agent reaching across a boundary. A refused
    #: charter is a specification error made by whoever wrote the formation, not
    #: an agent probing one, so SPAWN is excluded — counting it would trip the
    #: breaker on a configuration mistake.
    #:
    #: EGRESS is here, and it was not when egress was added. That omission was
    #: the exact failure this class exists to prevent, in the one crossing that
    #: leaves the process: a window could be refused model egress without limit
    #: and nothing would count it, while the docstring above claimed persistence
    #: itself was refusable. A breaker that does not count the newest and most
    #: externally-visible crossing is a breaker with a hole in the direction
    #: that matters most.
    CROSSINGS = frozenset({
        Operation.READ, Operation.WRITE, Operation.BRIDGE, Operation.EGRESS,
    })

    def __init__(self, log: AttestationLog, threshold: int = 16) -> None:
        if threshold < 1:
            raise ValueError("threshold must be at least 1")
        self.log = log
        self.threshold = threshold
        self._counts: dict[str, int] = {}
        self._scanned = 0

    def _catch_up(self) -> None:
        """Fold new entries into the counts. The chain is append-only.

        Rescanning the whole log per check made the containment path quadratic
        in chain length; this visits each entry once over the life of the run.
        """
        entries = self.log.entries()
        for entry in entries[self._scanned:]:
            decision = entry.decision
            if not decision.allowed and decision.operation in self.CROSSINGS:
                self._counts[decision.agent_scw] = self._counts.get(decision.agent_scw, 0) + 1
        self._scanned = len(entries)

    def denials_by(self, agent_scw: str) -> int:
        self._catch_up()
        return self._counts.get(agent_scw, 0)

    def tripped(self, agent_scw: str) -> bool:
        return self.denials_by(agent_scw) >= self.threshold

    def check(self, agent_scw: str) -> None:
        count = self.denials_by(agent_scw)
        if count >= self.threshold:
            raise ConstitutionViolation(
                f"{agent_scw} has {count} refused crossings on the chain, at or past "
                f"the threshold of {self.threshold}; further attempts are refused"
            )


def bounded(reach: set[str] | frozenset[str], **caps: int | None) -> Constitution:
    """A concrete constitution, for the common case of granting an explicit set."""
    return Constitution(reach=frozenset(reach), **caps)


def narrowed(base: Constitution, reach: set[str] | frozenset[str]) -> Constitution:
    """`base` with a smaller reach, refusing if the set is not actually smaller."""
    return base.derive(replace(base, reach=frozenset(reach)))


__all__ = [
    "Constitution",
    "ConstitutionTree",
    "ConstitutionViolation",
    "DenialBreaker",
    "UNBOUNDED",
    "bounded",
    "narrowed",
]
