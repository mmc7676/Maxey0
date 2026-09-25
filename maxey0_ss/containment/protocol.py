"""The containment contract: what a provider must decide, and what it must emit.

Containment enforcement and containment *evidence* were the same code, which
forced a false choice — publish the enforcement and give away the mechanism, or
withhold it and make the claim unfalsifiable.

They are separated here. A `ContainmentProvider` decides; every decision becomes
an `Attestation` in a hash-chained log that a third party can verify without
possessing the provider. Which provider a deployment runs is configuration, not
a code fork, so what is published is a deployment choice rather than a rewrite.

A decision carries its reason and the identity of the provider that made it, so
the record answers *what* was attempted, *where*, *when*, and *by whom* without
disclosing *how* the answer was reached.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable


class Operation(str, Enum):
    """What was attempted across an SCW boundary."""

    READ = "read"
    WRITE = "write"
    DISJOINTNESS = "disjointness"
    BRIDGE = "bridge"
    #: Chartering a child SCW under a parent constitution. Recorded because it
    #: is the moment a formation grows, and an unbounded formation is the thing
    #: reach-checking alone does not prevent.
    SPAWN = "spawn"
    #: Reaching a third party — a model API, a dataset host — from inside a
    #: window. The other five operations cross a boundary *inside* this system;
    #: this one crosses the outermost boundary there is, and it was the only
    #: kind of reach the ledger did not record. A prompt leaving the process is
    #: a larger event than a read between two SCWs, and it was the unwatched one.
    EGRESS = "egress"


@dataclass(frozen=True)
class ContainmentDecision:
    """One allow/deny, with enough context to be audited later.

    `provider` names the engine that decided. `reason` is a short, stable string
    — it explains the outcome without describing the algorithm.
    """

    allowed: bool
    operation: Operation
    agent_scw: str
    target_scw: str
    reason: str
    provider: str
    #: Anything the decision is *about* that the five fields above cannot carry.
    #: An egress needs the model, the endpoint and a digest of the payload; a
    #: read between two SCWs needs none of that.
    #:
    #: Omitted from `as_dict` when empty, so every record written before this
    #: field existed digests to exactly the same value it always did. A field
    #: that silently rewrites historical digests would make every archived
    #: chain fail verification against the code that produced it.
    metadata: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        body: dict[str, object] = {
            "allowed": self.allowed,
            "operation": self.operation.value,
            "agent_scw": self.agent_scw,
            "target_scw": self.target_scw,
            "reason": self.reason,
            "provider": self.provider,
        }
        if self.metadata:
            # A copy, never the live dict. Handing out the stored object meant
            # a consumer redacting an exported record rewrote the decision in
            # the chain, and verify() then called the log tampered.
            body["metadata"] = copy.deepcopy(self.metadata)
        return body

    def __post_init__(self) -> None:
        # The caller's dict is shared too: changing it after record() changed
        # the stored decision. Frozen dataclass, so set through object.
        object.__setattr__(self, "metadata", copy.deepcopy(self.metadata))


@runtime_checkable
class ContainmentProvider(Protocol):
    """Decides whether one SCW may reach another.

    The default implementation is `containment.structural.StructuralContainment`.
    A deployment may substitute any provider satisfying this protocol — that is
    the seam that lets the enforcement engine stay private while the attestation
    format, the verifier, and the evidence tools remain public.
    """

    #: Stable identifier recorded in every attestation this provider produces.
    name: str

    def register(self, instance) -> None:
        """Make an SCW instance known to the provider."""

    def decide(self, operation: Operation, agent_scw: str, target_scw: str) -> ContainmentDecision:
        """Return the decision for one attempted crossing."""


class ContainmentError(RuntimeError):
    """Raised when a crossing is refused and the caller demanded success."""

    def __init__(self, decision: ContainmentDecision) -> None:
        super().__init__(
            f"{decision.operation.value} denied: {decision.agent_scw} -> "
            f"{decision.target_scw} ({decision.reason})"
        )
        self.decision = decision
