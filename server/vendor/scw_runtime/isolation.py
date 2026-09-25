"""Scope resolution and isolation enforcement.

This module is the wall. Every read, write, and promotion in the runtime is
funnelled through :meth:`Scope.check` before any state changes, so that
"region A cannot see region B" is a property of the tool layer rather than a
convention the model is asked to respect.

The rule, in one sentence: a bound scope may touch its own region, that
region's subtree if it bound with ``descend``, and any region for which an
explicit, unexpired bridge grants the requested operation — and nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from .model import Bridge

if TYPE_CHECKING:  # pragma: no cover
    from .window import ContextWindow

ORCHESTRATOR = "orchestrator"


@dataclass
class Decision:
    """The outcome of an access check."""

    allowed: bool
    via: str  # "scope" | "descend" | "orchestrator" | bridge id
    reason: str = ""
    hint: str = ""

    def to_dict(self) -> dict:
        out = {"allowed": self.allowed, "via": self.via}
        if self.reason:
            out["reason"] = self.reason
        if self.hint:
            out["hint"] = self.hint
        return out


@dataclass
class Scope:
    """The set of regions a caller may reach, and by what authority."""

    actor: str
    loop_id: Optional[str]
    root: Optional[str]
    reachable: set[str] = field(default_factory=set)
    descend_reachable: set[str] = field(default_factory=set)
    bridges: list[Bridge] = field(default_factory=list)
    unbound_denied: bool = False

    def check(self, op: str, scw_id: str) -> Decision:
        """Decide whether ``op`` (``read``/``write``) may touch ``scw_id``."""
        if self.unbound_denied:
            return Decision(
                False,
                via="none",
                reason="strict_scope is on and the caller supplied no loop_id",
                hint="Call bind_scope(loop_id, scw_id) first, then pass loop_id to this tool.",
            )
        if self.loop_id is None:
            # Unbound orchestrator access. Permitted by default but always
            # recorded, so an audit can tell scoped work from privileged work.
            return Decision(True, via=ORCHESTRATOR)
        if scw_id == self.root:
            return Decision(True, via="scope")
        if scw_id in self.descend_reachable:
            return Decision(True, via="descend")
        for bridge in self.bridges:
            if bridge.to_scw_id == scw_id and bridge.grants(op):
                return Decision(True, via=bridge.bridge_id)
        return Decision(
            False,
            via="none",
            reason=(
                f"loop {self.loop_id!r} is bound to {self.root!r}; "
                f"{scw_id!r} is outside its scope and no bridge grants {op!r}"
            ),
            hint=(
                f"open_bridge(from_scw_id={self.root!r}, to_scw_id={scw_id!r}, "
                f"mode={op!r}, reason=...) — or bind the loop to a common ancestor."
            ),
        )


def descendants(window: "ContextWindow", scw_id: str) -> set[str]:
    """All regions beneath ``scw_id``, exclusive of itself."""
    out: set[str] = set()
    stack = list(window.regions[scw_id].children)
    while stack:
        current = stack.pop()
        if current in out:
            continue
        out.add(current)
        stack.extend(window.regions[current].children)
    return out


def resolve_scope(window: "ContextWindow", loop_id: Optional[str]) -> Scope:
    """Build the caller's scope from the current window state."""
    if loop_id is None:
        return Scope(
            actor=ORCHESTRATOR,
            loop_id=None,
            root=None,
            unbound_denied=window.strict_scope,
        )

    loop = window.loops.get(loop_id)
    if loop is None or loop.status != "bound":
        # An unknown or released loop gets an empty scope rather than an
        # exception, so the denial is logged like any other refusal.
        return Scope(
            actor=f"loop:{loop_id}",
            loop_id=loop_id,
            root=None,
            unbound_denied=False,
        )

    scope = Scope(actor=f"loop:{loop_id}", loop_id=loop_id, root=loop.scw_id)
    scope.reachable = {loop.scw_id}
    if loop.descend and loop.scw_id in window.regions:
        scope.descend_reachable = descendants(window, loop.scw_id)
        scope.reachable |= scope.descend_reachable
    holders = scope.reachable
    scope.bridges = [
        b
        for b in window.bridges.values()
        if b.status == "open" and b.from_scw_id in holders
    ]
    return scope
