"""Prefix-cache economics.

Structuring the window is the precondition for two separate wins. Addressable
regions make targeted loops possible; *stable* regions make caching possible.
This module measures the second one.

Prompt caches are prefix caches: the cache holds the longest unchanged run of
tokens starting at position zero, and the first byte that changes invalidates
everything after it. So a region's position matters as much as its contents. A
2 KB scratchpad that mutates every iteration costs 2 KB if it sits at the tail
and can cost 40 KB of re-processed prefix if it sits at the head.

:func:`compute_plan` reports, per iteration:

* how many tokens the prefix cache can actually serve,
* where the cache breakpoint falls (the last region in the stable prefix),
* how many tokens *would* be cacheable under an optimal layout, and
* the difference between those two — the tokens a reorder would recover.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence


@dataclass
class RegionCost:
    """One top-level region's contribution to the rendered window."""

    scw_id: str
    tokens: int
    signature: str
    cache_hint: str = "auto"


@dataclass
class Snapshot:
    """What the window looked like the last time it was billed."""

    order: list[str] = field(default_factory=list)
    signatures: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"order": list(self.order), "signatures": dict(self.signatures)}

    @classmethod
    def from_dict(cls, data: dict | None) -> "Snapshot":
        data = data or {}
        return cls(order=list(data.get("order", [])), signatures=dict(data.get("signatures", {})))


@dataclass
class CachePlan:
    """The result of pricing one render of the window."""

    order: list[str]
    total_tokens: int
    cached_tokens: int
    reprocessed_tokens: int
    breakpoint_index: int
    breakpoint_scw_id: Optional[str]
    dirty: list[str]
    stable: list[str]
    ideal_cached_tokens: int
    recoverable_tokens: int
    first_dirty_scw_id: Optional[str]

    @property
    def hit_ratio(self) -> float:
        return round(self.cached_tokens / self.total_tokens, 4) if self.total_tokens else 0.0

    def to_dict(self) -> dict:
        return {
            "order": list(self.order),
            "total_tokens": self.total_tokens,
            "cached_tokens": self.cached_tokens,
            "reprocessed_tokens": self.reprocessed_tokens,
            "cache_hit_ratio": self.hit_ratio,
            "breakpoint_index": self.breakpoint_index,
            "breakpoint_scw_id": self.breakpoint_scw_id,
            "first_dirty_scw_id": self.first_dirty_scw_id,
            "dirty": list(self.dirty),
            "stable": list(self.stable),
            "ideal_cached_tokens": self.ideal_cached_tokens,
            "recoverable_tokens": self.recoverable_tokens,
        }


def subtree_signature(pairs: Iterable[tuple[str, int]]) -> str:
    """Fingerprint a region subtree from ``(scw_id, revision)`` pairs.

    Any write, eviction, purge, child creation, or child removal bumps some
    revision inside the subtree, so the fingerprint changes exactly when the
    rendered bytes of that subtree can have changed.
    """
    joined = "|".join(f"{sid}@{rev}" for sid, rev in pairs)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]


def compute_plan(costs: Sequence[RegionCost], snapshot: Snapshot) -> CachePlan:
    """Price a render against the previous :class:`Snapshot`.

    A region counts as stable when its signature matches the snapshot *and* it
    occupies the same index it did before (an insertion shifts every later
    region's bytes, which breaks the cache regardless of content). Hints
    override: ``always`` forces stable, ``never`` forces dirty.
    """
    order = [c.scw_id for c in costs]
    total = sum(c.tokens for c in costs)

    def is_stable(index: int, cost: RegionCost) -> bool:
        if cost.cache_hint == "never":
            return False
        if cost.cache_hint == "always":
            return True
        if index >= len(snapshot.order) or snapshot.order[index] != cost.scw_id:
            return False
        return snapshot.signatures.get(cost.scw_id) == cost.signature

    def is_content_stable(cost: RegionCost) -> bool:
        """Stability ignoring position — used for the optimal-layout bound."""
        if cost.cache_hint == "never":
            return False
        if cost.cache_hint == "always":
            return True
        return snapshot.signatures.get(cost.scw_id) == cost.signature

    prefix = 0
    for index, cost in enumerate(costs):
        if not is_stable(index, cost):
            break
        prefix += 1

    cached = sum(c.tokens for c in costs[:prefix])
    stable_anywhere = [c for c in costs if is_content_stable(c)]
    ideal_cached = sum(c.tokens for c in stable_anywhere)
    dirty = [c.scw_id for c in costs if not is_content_stable(c)]
    first_dirty = next((c.scw_id for i, c in enumerate(costs) if not is_stable(i, c)), None)

    return CachePlan(
        order=order,
        total_tokens=total,
        cached_tokens=cached,
        reprocessed_tokens=total - cached,
        breakpoint_index=prefix,
        breakpoint_scw_id=costs[prefix - 1].scw_id if prefix else None,
        dirty=dirty,
        stable=[c.scw_id for c in stable_anywhere],
        ideal_cached_tokens=ideal_cached,
        recoverable_tokens=max(0, ideal_cached - cached),
        first_dirty_scw_id=first_dirty,
    )


def ordering_advisories(costs: Sequence[RegionCost], snapshot: Snapshot) -> list[dict]:
    """Name the regions whose position is costing tokens.

    For each region that will re-process this iteration, sum the tokens of the
    stable regions sitting *behind* it. Those tokens are re-billed purely
    because of layout, and moving the offending region later recovers them.
    """
    stable_flags = []
    for cost in costs:
        if cost.cache_hint == "never":
            stable_flags.append(False)
        elif cost.cache_hint == "always":
            stable_flags.append(True)
        else:
            stable_flags.append(snapshot.signatures.get(cost.scw_id) == cost.signature)

    advisories: list[dict] = []
    for index, cost in enumerate(costs):
        if stable_flags[index]:
            continue
        blocked = sum(c.tokens for c, stable in zip(costs[index + 1:], stable_flags[index + 1:]) if stable)
        if blocked <= 0:
            continue
        advisories.append(
            {
                "code": "cache.ordering",
                "severity": "warn" if blocked >= 1000 else "info",
                "scw_id": cost.scw_id,
                "tokens_blocked": blocked,
                "message": (
                    f"{cost.scw_id!r} mutates and sits at position {index}, "
                    f"invalidating {blocked} otherwise-cacheable tokens behind it"
                ),
                "remedy": f"raise the `order` of {cost.scw_id!r} so it renders after the stable regions",
            }
        )
    advisories.sort(key=lambda a: -a["tokens_blocked"])
    return advisories
