"""The default containment provider: structural SCW boundaries.

Decisions are made from the declared shape of the address space — what an SCW
instance lists as readable, writable, and bridged — and from nothing else. No
model is consulted, which is the property that makes containment checkable
rather than persuadable.

This is the provider a deployment gets when it configures none. It satisfies
`ContainmentProvider`, so a deployment that wants different enforcement
substitutes one without touching the attestation format, the verifier, or any
tool that reads them.
"""
from __future__ import annotations

from ..identity import spec_id_of
from ..models import SCWInstance
from .attestation import AttestationLog
from .hierarchy import Constitution, ConstitutionTree, ConstitutionViolation, DenialBreaker
from .protocol import ContainmentDecision, ContainmentError, Operation

#: Recorded in every attestation this provider produces.
PROVIDER_NAME = "structural"


class StructuralContainment:
    """Enforces SCW read/write boundaries independently of model behavior.

    When a `ConstitutionTree` is supplied, the chartered hierarchy is a ceiling
    over everything below: a declared read set, and an open bridge, are both
    refused where they exceed what the parent granted. Without one the provider
    behaves as it always did — reach is whatever each instance declares — which
    is why a formation that matters should be chartered.
    """

    name = PROVIDER_NAME

    def __init__(
        self,
        log: AttestationLog | None = None,
        tree: ConstitutionTree | None = None,
        breaker: DenialBreaker | None = None,
    ) -> None:
        self.instances: dict[str, SCWInstance] = {}
        self.bridges: dict[tuple[str, str], set[str]] = {}
        #: Every decision lands here. Supply a shared log to correlate providers.
        self.log = log if log is not None else AttestationLog()
        #: The chartered hierarchy, or None for unconstrained declaration.
        self.tree = tree
        #: Reads the chain back. Without it, refusals accumulate and bound nothing.
        self.breaker = breaker

    # -- registry -----------------------------------------------------------

    def register(self, instance: SCWInstance) -> None:
        """Make an instance known, refusing a declared reach beyond its charter."""
        if self.tree is not None:
            excess = sorted(
                target
                for target in (instance.readable | instance.writable)
                if not self._constitution_permits(instance.id, target)
            )
            if excess:
                # One decision per target. A joined string in `target_scw` would
                # put a value in the chain that is not an SCW identifier, which
                # is precisely what identity.py exists to keep out of it.
                decision = None
                for target in excess:
                    decision = self._record(
                        Operation.SPAWN, instance.id, target, False,
                        "declared reach exceeds the chartered constitution",
                    )
                raise ConstitutionViolation(
                    f"{instance.id} declares reach to {excess} that its constitution "
                    f"does not grant",
                    decision,
                )
        self.instances[instance.id] = instance

    def revoke(self, instance_id: str) -> None:
        """Deregister an instance and drop every bridge it holds.

        An unregistered agent fails closed in `_decide_read`, so deregistration
        is the revocation. Leaving the instance registered meant a closed window
        kept whatever reach it had.
        """
        self.instances.pop(instance_id, None)
        for key in [k for k in self.bridges if instance_id in k]:
            del self.bridges[key]
        self._record(Operation.SPAWN, instance_id, instance_id, True, "instance revoked")

    def charter(
        self, scw_id: str, parent_id: str, requested: Constitution | None = None
    ) -> Constitution:
        """Charter a child under a parent and attest the growth of the formation."""
        if self.tree is None:
            raise ConstitutionViolation(
                "this provider has no constitution tree; chartering would grant "
                "nothing and constrain nothing"
            )
        try:
            granted = self.tree.charter(scw_id, parent_id, requested)
        except ConstitutionViolation as exc:
            decision = self._record(
                Operation.SPAWN, scw_id, parent_id, False, "charter refused by the constitution"
            )
            raise ConstitutionViolation(str(exc), decision) from exc
        self._record(Operation.SPAWN, scw_id, parent_id, True, "chartered under the parent constitution")
        return granted

    def charter_root(
        self, scw_id: str, constitution: Constitution | None = None
    ) -> Constitution:
        """Grant the root constitution, and attest it.

        Every decision below this one is bounded by this grant, so a chain that
        does not record it cannot answer why a later crossing was allowed. The
        reach is written into the reason because the grant *is* the security
        decision — an unbounded root makes the induction true and vacuous.
        """
        if self.tree is None:
            raise ConstitutionViolation(
                "this provider has no constitution tree; a root grant would "
                "constrain nothing"
            )
        granted = self.tree.charter_root(scw_id, constitution)
        reach = "unbounded" if granted.reach is None else ",".join(sorted(granted.reach))
        self._record(Operation.SPAWN, scw_id, scw_id, True, f"root chartered with reach [{reach}]")
        return granted

    def narrow(self, scw_id: str, requested: Constitution) -> Constitution:
        """Tighten a constitution and re-seat its subtree, attesting the change."""
        if self.tree is None:
            raise ConstitutionViolation("this provider has no constitution tree")
        before = self.tree.descendants(scw_id)
        granted = self.tree.narrow(scw_id, requested)
        reach = "unbounded" if granted.reach is None else ",".join(sorted(granted.reach))
        self._record(
            Operation.SPAWN, scw_id, scw_id, True,
            f"constitution narrowed to [{reach}]; {len(before)} descendants re-seated",
        )
        return granted

    def _constitution_permits(self, agent: str, target: str) -> bool:
        """Whether the charter lets `agent` name `target`, by spec or instance id.

        Instances carry a runtime suffix (`SCW1@runtime`) while charters are
        usually written against spec identifiers, so both forms resolve.
        """
        if self.tree is None:
            return True
        for who in _forms(agent):
            if not self.tree.is_chartered(who):
                continue
            return any(self.tree.permits(who, what) for what in _forms(target))
        return False

    def open_bridge(self, source: str, target: str) -> None:
        """Declare an explicit crossing. Recorded, because it widens reach.

        A bridge cannot exceed the constitution. Allowing one would make the
        hierarchy advisory: any window could bridge to anything and the charter
        would describe a shape the runtime did not hold to.
        """
        if self.breaker is not None and self.breaker.tripped(source):
            # Record before raising. Going silent exactly when a window is
            # probing persistently would drop the evidence most worth having.
            decision = self._record(
                Operation.BRIDGE, source, target, False,
                "refused: persistent refused crossings on the chain",
            )
            raise ConstitutionViolation(
                f"{source} has persistent refused crossings on the chain; "
                f"further attempts are refused",
                decision,
            )
        # `bridgeable=False` was derived, inherited and then read by nothing, so
        # a charter that forbade bridges opened them anyway and attested them
        # as allowed. The source's own chartered form is the one that answers.
        if self.tree is not None:
            for who in _forms(source):
                if not self.tree.is_chartered(who):
                    continue
                constitution = self.tree.constitution_of(who)
                if constitution is not None and not constitution.is_bridgeable:
                    decision = self._record(
                        Operation.BRIDGE, source, target, False,
                        "constitution is not bridgeable",
                    )
                    raise ConstitutionViolation(
                        f"{source} cannot open bridges: its constitution is not bridgeable",
                        decision,
                    )
                break
        if self.tree is not None and not self._constitution_permits(source, target):
            decision = self._record(
                Operation.BRIDGE, source, target, False,
                "bridge target is outside the chartered constitution",
            )
            raise ConstitutionViolation(
                f"{source} cannot bridge to {target}: its constitution does not grant it",
                decision,
            )
        self.bridges.setdefault((source, target), set()).add(target)
        self._record(
            Operation.BRIDGE, source, target, True, "bridge declared between explicit addresses"
        )

    # -- decisions ----------------------------------------------------------

    def _record(
        self, operation: Operation, agent: str, target: str, allowed: bool, reason: str
    ) -> ContainmentDecision:
        decision = ContainmentDecision(
            allowed=allowed,
            operation=operation,
            agent_scw=agent,
            target_scw=target,
            reason=reason,
            provider=self.name,
        )
        self.log.record(decision)
        return decision

    def decide(self, operation: Operation, agent_scw: str, target_scw: str) -> ContainmentDecision:
        # The breaker bounds persistence, so it has to sit on the path agents
        # actually use. Counting refusals without refusing left repeated
        # probing free on every call except open_bridge.
        if self.breaker is not None and self.breaker.tripped(agent_scw):
            return self._record(
                operation, agent_scw, target_scw, False,
                "refused: persistent refused crossings on the chain",
            )
        if operation is Operation.READ:
            return self._decide_read(agent_scw, target_scw)
        if operation is Operation.WRITE:
            return self._decide_write(agent_scw, target_scw)
        if operation is Operation.DISJOINTNESS:
            return self._decide_disjoint(agent_scw, target_scw)
        if operation is Operation.EGRESS:
            return self._decide_egress(agent_scw, target_scw)
        return self._record(operation, agent_scw, target_scw, False, "unsupported operation")

    def _decide_egress(self, agent: str, target: str) -> ContainmentDecision:
        """May this window reach a third party at all.

        The target is outside this system — a model endpoint, a dataset host —
        so the constitution's `reach` cannot answer it. `reach` bounds which
        *windows* may be named, and folding external hostnames into that set
        would conflate two namespaces: `SCW3` and `api.anthropic.com` are not
        the same kind of name, and a charter that could not tell them apart
        would be a charter nobody could read.

        What containment answers here is the part it can: the window exists, it
        is open, and — via the breaker in `decide()` above — it is not one that
        has been persistently refused. Whether a *caller* may ask for egress at
        all is an authorization question, answered upstream by the capability
        on `provider.complete`; whether the *content* should go is the semantic
        gate's. Three questions, three answers, none of them pretending to be
        another.

        Before 0.3.0 this branch did not exist and egress never reached
        `decide()`, so a closed window could still send a prompt to a third
        party and no refusal was ever counted.
        """
        instance = self.instances.get(agent)
        if instance is None:
            # Fail closed, the same way an unregistered read does.
            return self._record(
                Operation.EGRESS, agent, target, False,
                "window is not registered",
            )
        if not getattr(instance, "open", True):
            return self._record(
                Operation.EGRESS, agent, target, False, "window is closed",
            )
        return self._record(
            Operation.EGRESS, agent, target, True, "window may reach outside",
        )

    def _decide_read(self, agent: str, target: str) -> ContainmentDecision:
        instance = self.instances.get(agent)
        if agent == target:
            # A window reads itself, but only while it is open and registered.
            # This shortcut used to run before any lookup, so a closed or
            # revoked window still passed its own reads.
            if instance is None:
                return self._record(
                    Operation.READ, agent, target, False,
                    "window is not registered",
                )
            if not getattr(instance, "open", True):
                return self._record(
                    Operation.READ, agent, target, False, "window is closed"
                )
            return self._record(Operation.READ, agent, target, True, "same window")
        if instance is None:
            # Fail closed: an unregistered agent has no declared reach.
            return self._record(Operation.READ, agent, target, False, "agent window is not registered")
        # The constitution is a ceiling, checked before the declared set and
        # before any bridge. A window cannot read past its charter by declaring
        # that it can, which is exactly what an unconsulted hierarchy allowed.
        if not getattr(instance, "open", True):
            return self._record(
                Operation.READ, agent, target, False, "agent window is closed"
            )
        if not self._constitution_permits(agent, target):
            return self._record(
                Operation.READ, agent, target, False,
                "target is outside the chartered constitution",
            )
        if target in instance.readable:
            return self._record(Operation.READ, agent, target, True, "target is in the declared read set")
        if target in self.bridges.get((agent, target), set()):
            return self._record(Operation.READ, agent, target, True, "an explicit bridge is open")
        return self._record(Operation.READ, agent, target, False, "target is outside the declared read set")

    def _decide_write(self, agent: str, target: str) -> ContainmentDecision:
        instance = self.instances.get(agent)
        if agent == target:
            # A window reads itself, but only while it is open and registered.
            # This shortcut used to run before any lookup, so a closed or
            # revoked window still passed its own reads.
            if instance is None:
                return self._record(
                    Operation.WRITE, agent, target, False,
                    "window is not registered",
                )
            if not getattr(instance, "open", True):
                return self._record(
                    Operation.WRITE, agent, target, False, "window is closed"
                )
            return self._record(Operation.WRITE, agent, target, True, "same window")
        if instance is None:
            return self._record(Operation.WRITE, agent, target, False, "agent window is not registered")
        if not getattr(instance, "open", True):
            return self._record(
                Operation.WRITE, agent, target, False, "agent window is closed"
            )
        if not self._constitution_permits(agent, target):
            return self._record(
                Operation.WRITE, agent, target, False,
                "target is outside the chartered constitution",
            )
        allowed = target in instance.writable
        return self._record(
            Operation.WRITE, agent, target, allowed,
            "target is in the declared write set" if allowed else "target is outside the declared write set",
        )

    def _decide_disjoint(self, a: str, b: str) -> ContainmentDecision:
        ia, ib = self.instances.get(a), self.instances.get(b)
        if ia is None or ib is None:
            return self._record(Operation.DISJOINTNESS, a, b, False, "one or both windows are not registered")
        # Masking with {a, b} asked only whether the two windows could see
        # each other, so two windows both holding a third in their read sets
        # were reported disjoint while sharing its context entirely.
        # Reach is what `_decide_read` would grant, so it includes open bridges.
        # Comparing declared read sets alone certified two windows disjoint
        # while a bridge let one read a window the other also reads.
        def reach(who: str, inst: SCWInstance) -> set[str]:
            bridged = {t for (src, _), targets in self.bridges.items()
                       if src == who for t in targets}
            return set(inst.readable) | {who} | bridged

        overlap = reach(a, ia) & reach(b, ib)
        return self._record(
            Operation.DISJOINTNESS, a, b, not overlap,
            "private regions do not overlap" if not overlap
            else f"private regions overlap on {sorted(overlap)}",
        )

    # -- convenience, preserving the original call shape --------------------

    def can_read(self, agent_scw: str, target_scw: str) -> bool:
        return self.decide(Operation.READ, agent_scw, target_scw).allowed

    def can_write(self, agent_scw: str, target_scw: str) -> bool:
        return self.decide(Operation.WRITE, agent_scw, target_scw).allowed

    def assert_private_disjoint(self, a: str, b: str) -> bool:
        return self.decide(Operation.DISJOINTNESS, a, b).allowed

    def require_read(self, agent_scw: str, target_scw: str) -> None:
        decision = self.decide(Operation.READ, agent_scw, target_scw)
        if not decision.allowed:
            raise ContainmentError(decision)


def _forms(reference: str) -> tuple[str, ...]:
    """An SCW reference as both its instance and spec identifier.

    Charters are written against specs (`SCW1`); instances carry a runtime
    suffix (`SCW1@runtime-a`). Resolving both means a charter constrains the
    instances of the window it chartered, which is the only reading that makes
    the hierarchy bite at runtime.
    """
    spec = spec_id_of(reference)
    return (reference,) if spec == reference else (reference, spec)
