"""The seam: no provider egress that an outside observer cannot see.

A tool call is already gated and attested. A provider call was not, and that is
the larger hole of the two: a tool call stays inside this process, while a
provider call sends a prompt to a third party. The moment an agent reaches
outside its window is the moment worth watching, and until now the only one of
those this system watched was the one that did not leave the building.

:class:`GatedProvider` wraps any provider so that every call:

1. is **described before it happens** — :meth:`describe_call` builds a
   :class:`ProviderCall` carrying the provider, the operation, the model, the
   SCW it belongs to, and a *digest* of the payload;
2. is **admitted** by the same `SemanticGateProvider` that admits tool calls,
   and refused with a `GateDecision` if that provider says no;
3. **lands in the hash-chained attestation log either way**, so a refusal is
   evidence rather than an absence.

The prompt is digested, never recorded. The containment record is published —
`maxey0-ss.evidence.attestations` serves it to anybody holding the observe
capability — and a published record that carried prompts would be a published
record of user data. The digest is enough to prove two calls were the same call
and not enough to read either.

**A refusal is recorded before it is raised.** Writing the attestation only on
the success path would produce a chain in which refused egress is
indistinguishable from egress that never happened, which is precisely the
failure mode `observe` mode reporting `held: true` had.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..containment.attestation import AttestationLog
from ..containment.protocol import ContainmentDecision, Operation
from ..gating.semantic import SemanticGateProvider, select_semantic_gate
from .base import ProviderCall, ProviderError, ProviderRefused, ProviderResult

#: The capability an egress is admitted against. Distinct from any tool
#: capability on purpose: "may call a model" is not "may read observability",
#: and a deployment should be able to grant one without the other.
EGRESS_CAPABILITY = "provider.egress"


@dataclass
class EgressRecord:
    """What was attested for one egress attempt."""

    call: ProviderCall
    allowed: bool
    reason: str
    digest: str


class GatedProvider:
    """Any provider, with the gate and the ledger in front of it.

    The wrapped provider is not modified and does not know it is wrapped. It
    can still be used directly, which is deliberate: this class is the
    *supported* path, and a test that reaches around it is a test that proves
    the unwrapped provider still works rather than one that accidentally
    bypasses containment.
    """

    def __init__(
        self,
        provider: Any,
        *,
        log: AttestationLog | None = None,
        gate: SemanticGateProvider | None = None,
        containment: Any = None,
        scw_id: str | None = None,
    ) -> None:
        self.provider = provider
        self.log = log if log is not None else AttestationLog()
        self.gate = gate or select_semantic_gate()
        #: The structural half. Optional only because a provider can be used
        #: standalone; when the surface builds one it always passes the running
        #: system's provider, so the supported path is never without it.
        self.containment = containment
        self.scw_id = scw_id

    # -- naming -------------------------------------------------------------

    @property
    def name(self) -> str:
        return self.provider.capabilities.name

    def _address(self, call: ProviderCall) -> str:
        """The address the gate decides about.

        An egress is addressed by where it came from, not by where it is going:
        the question a gate answers is "may *this window* reach outside", and
        the destination is metadata on that decision. An SCW-less caller gets
        the root window, which is the honest description of an egress that no
        window claimed.
        """
        scw = call.scw_id or self.scw_id or "SCW0"
        return f"scw://provider/{call.provider}/{call.operation}/egress/{scw}"

    # -- the seam -----------------------------------------------------------

    def admit(self, call: ProviderCall) -> EgressRecord:
        """Decide, record, and return the record. Never raises on refusal.

        Two decisions, in this order, and the order matters.

        **Structural first.** `ContainmentProvider.decide(EGRESS, ...)` answers
        whether this window may reach outside at all: is it registered, is it
        open, and has it been persistently refused. That last one is the
        `DenialBreaker`, and it only counts crossings it is shown — so egress
        that never reached `decide()` was egress the breaker could not count,
        which is exactly the hole this ordering closes. Until 0.3.0 this call
        did not exist: a closed window could send a prompt to a third party,
        and unlimited refused egress tripped nothing.

        **Semantic second.** Only if the structure allows it is there any point
        asking whether the *content* should go. Asking in the other order would
        send the payload to a policy service for a window that is not permitted
        to speak at all.
        """
        window = call.scw_id or self.scw_id or "SCW0"
        if self.containment is not None:
            try:
                structural = self.containment.decide(
                    Operation.EGRESS, window,
                    f"{call.provider}:{call.operation}",
                )
            except Exception as exc:  # a refusing provider raises rather than answers
                return EgressRecord(call=call, allowed=False,
                                    reason=f"containment refused: {exc}", digest="")
            if not structural.allowed:
                # Already recorded by the containment provider's own `_record`.
                return EgressRecord(call=call, allowed=False,
                                    reason=structural.reason, digest="")

        decision = self.gate.evaluate(
            address=self._address(call),
            capability=EGRESS_CAPABILITY,
            metadata=call.as_attestation(),
        )
        attestation = self.log.record(
            ContainmentDecision(
                allowed=bool(decision.allowed),
                operation=Operation.EGRESS,
                agent_scw=call.scw_id or self.scw_id or "SCW0",
                target_scw=f"{call.provider}:{call.operation}",
                reason=decision.reason,
                provider=getattr(self.gate, "name", type(self.gate).__name__),
                metadata=call.as_attestation(),
            )
        )
        return EgressRecord(
            call=call,
            allowed=bool(decision.allowed),
            reason=decision.reason,
            digest=getattr(attestation, "digest", ""),
        )

    def complete(self, prompt: str, **kwargs: Any) -> ProviderResult:
        """A completion, admitted and attested before a byte leaves."""
        call = self.provider.describe_call(
            prompt, scw_id=kwargs.get("scw_id", self.scw_id), **{
                k: v for k, v in kwargs.items() if k not in {"scw_id"}
            }
        )
        record = self.admit(call)
        if not record.allowed:
            raise ProviderRefused(
                f"egress to {call.provider}:{call.operation} was refused by the "
                f"gate: {record.reason}",
                record,
            )
        kwargs.pop("scw_id", None)
        result = self.provider.complete(prompt, **kwargs)
        self.log.record(
            ContainmentDecision(
                allowed=True,
                operation=Operation.EGRESS,
                agent_scw=call.scw_id or self.scw_id or "SCW0",
                target_scw=f"{call.provider}:{call.operation}",
                reason="egress completed",
                provider=getattr(self.gate, "name", type(self.gate).__name__),
                metadata={
                    "kind": "provider.egress.result",
                    "provider": call.provider,
                    "operation": call.operation,
                    "model": result.model,
                    "usage": dict(result.usage),
                    "latency_ms": result.latency_ms,
                    "payload_digest": call.payload_digest,
                },
            )
        )
        return result

    def hub_read(self, repo_id: str, *, repo_type: str = "dataset") -> dict[str, Any]:
        """A Hub retrieval, admitted and attested as a retrieval.

        Separate from :meth:`complete` because it is a different kind of event:
        no prompt leaves, so recording it as a completion would put "a prompt
        was sent to a third party" in the chain for an operation that sent none.
        """
        describe = getattr(self.provider, "describe_hub_read", None)
        if describe is None:
            raise ProviderError(f"{self.name} has no Hub read operation")
        call = describe(repo_id, repo_type=repo_type, scw_id=self.scw_id)
        record = self.admit(call)
        if not record.allowed:
            raise ProviderRefused(
                f"hub read of {repo_id} was refused by the gate: {record.reason}",
                record,
            )
        reader = getattr(self.provider, f"{repo_type}_info")
        return reader(repo_id)

    # -- reporting ----------------------------------------------------------

    def public_manifest(self) -> dict[str, Any]:
        base = dict(self.provider.public_manifest())
        base["gated"] = True
        base["egress_capability"] = EGRESS_CAPABILITY
        base["attested"] = True
        base["attestations"] = len(self.log)
        return base
