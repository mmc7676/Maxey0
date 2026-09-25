from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .identity import validate_scw_id, validate_scw_reference
from typing import Any


# `RegionKind` was removed in 0.2.0 along with `SCWSpec.region_kinds`, the only
# thing that ever held one. It declared exactly the five names that
# `server/vendor/scw_runtime/model.py:REGION_TYPES` declares —
# ("reference", "durable", "episodic", "working", "scratchpad") — and that one
# is load-bearing: the Context plane runtime builds, types and gates real
# regions with it. This was a second vocabulary for the same concept, consumed
# by nothing, and two spellings of one vocabulary can only ever drift apart.
# The region vocabulary lives in `scw_runtime.model.REGION_TYPES`.


@dataclass(frozen=True)
class SemanticAddress:
    topic: str
    concept: str
    skill: str
    region: str

    def key(self) -> str:
        return f"{self.topic}/{self.concept}/{self.skill}/{self.region}"


@dataclass
class ContextNode:
    id: str
    kind: str
    name: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MCPServerRecord:
    id: str
    endpoint: str
    name: str
    capabilities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillRecord:
    id: str
    name: str
    concept: str
    topic: str
    gate_id: str
    mcp_servers: list[str] = field(default_factory=list)
    embedding: list[float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SCWSpec:
    """The declared contract for one window.

    Two fields were removed in 0.2.0 after an audit found neither had a reader:

    ``isolation: bool = True`` was echoed by ``scw.describe`` and consulted
    nowhere. It read as a containment control and was not one — containment
    here is enforced structurally, by chartering in ``ContextService`` and by
    the provider's ``can_read``/``can_write``, and there is no mode in which it
    is switched off. ``DEFAULT_CONSTITUTION["isolation"] = "fail-closed"``
    already carries the real declaration. A boolean that looks like a safety
    switch, defaults to the safe value and controls nothing is worse than no
    switch: it invites somebody to believe setting it False did something.

    ``region_kinds: list[RegionKind]`` was a *required positional* read by
    nothing. Of nine construction sites, five passed ``list(RegionKind)`` and
    four passed ``[]``, with no behavioral difference between them, and
    ``ContextService.instantiate`` creates no regions from it. Wiring it would
    have meant inventing a region subsystem inside ``maxey0_ss`` to consume it.

    ``drift_threshold`` stayed, and gained the reader it always declared: it is
    the default threshold for ``maxey0-ss.scw.drift``, which anchors and
    inspects through ``SemanticRuntime``. It was the one of the four that was
    never a label — it is the documented input to a complete engine that simply
    had no caller.
    """

    id: str
    parent_id: str | None
    concept: str
    skills: list[str]
    constitution: dict[str, Any] = field(default_factory=dict)
    drift_threshold: float = 0.15

    def __post_init__(self) -> None:
        # The identifier reaches addresses, cache namespaces and attestations.
        # Rejecting it here is the only place that catches all three.
        validate_scw_id(self.id)
        if self.parent_id is not None:
            validate_scw_id(self.parent_id)
        if self.parent_id == self.id:
            raise ValueError(f"SCW {self.id} cannot be its own parent")


@dataclass
class SCWInstance:
    id: str
    spec_id: str
    owner: str
    runtime_id: str
    address: SemanticAddress
    readable: set[str] = field(default_factory=set)
    writable: set[str] = field(default_factory=set)
    state: dict[str, Any] = field(default_factory=dict)
    open: bool = True


@dataclass
class AgentSpec:
    id: str
    role: str
    scw_id: str
    capabilities: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # An agent is bound to a window; an unbindable identifier is not a window.
        validate_scw_reference(self.scw_id)


@dataclass
class LoopSpec:
    id: str
    name: str
    agents: list[str]
    max_iterations: int = 1
    state: str = "created"


@dataclass
class GateDecision:
    allowed: bool
    gate_id: str
    reason: str
    score: float
    semantic_distance: float
    source: str


@dataclass
class DriftRecord:
    scw_id: str
    baseline: list[float]
    current: list[float]
    distance: float
    threshold: float
    drifted: bool
    correction: str | None = None
