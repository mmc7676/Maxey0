from __future__ import annotations

from typing import Any

from ..models import SCWInstance, SCWSpec
from ..containment import ContainmentProvider, containment_provider
from ..containment.attestation import AttestationLog
from ..containment.hierarchy import (
    Constitution,
    ConstitutionTree,
    ConstitutionViolation,
    DenialBreaker,
)
from ..identity import instance_id
from .graph import ContextGraph


class SpecificationExists(ValueError):
    """An SCW specification with this id is already registered.

    A ValueError so existing callers that caught the MCP tool's plain
    ValueError keep working; its own type so HTTP can map it to 409.
    """


class ContextService:
    #: The root every parentless spec is chartered under, and the ceiling the
    #: whole address space inherits from.
    ROOT_SCW = "SCW0"

    def __init__(
        self,
        graph: ContextGraph | None = None,
        isolation: ContainmentProvider | None = None,
        *,
        root_reach: set[str] | None = None,
        denial_threshold: int = 64,
    ) -> None:
        self.graph = graph or ContextGraph()
        # The hierarchy and the breaker have to be attached to the provider the
        # running system uses, or the reach ceiling, the spawn caps and the
        # refusal limit are inert for every SCW the MCP surface and the HTTP API
        # create. Building them here is what makes SCWSpec.parent_id load-bearing
        # rather than a stored field nothing reads.
        log = AttestationLog()
        self.tree = ConstitutionTree()
        self.breaker = DenialBreaker(log, threshold=denial_threshold)
        self.isolation = isolation or containment_provider(
            log=log, tree=self.tree, breaker=self.breaker
        )
        # An unbounded root is the honest default for an embedded process: it
        # makes the induction true and vacuous, and a deployment wanting a real
        # ceiling passes root_reach. What matters is the grant is recorded.
        root = Constitution(reach=frozenset(root_reach) if root_reach is not None else None)
        charter_root = getattr(self.isolation, "charter_root", None)
        if charter_root is not None:
            charter_root(self.ROOT_SCW, root)
        else:
            self.tree.charter_root(self.ROOT_SCW, root)
        self.instances: dict[str, SCWInstance] = {}
        self.audit: list[dict[str, Any]] = []

    def create_spec(self, spec: SCWSpec) -> SCWSpec:
        """Register a spec and charter it under its declared parent.

        `parent_id` was validated at construction and then read by nothing, so
        the hierarchy existed only as a field. Chartering here connects the
        declared tree to the enforcement path.
        """
        # The duplicate check lives here so every transport gets it. Only the
        # MCP tool had one; the REST routes overwrote an existing spec's
        # concept, skills and parent while the constitution tree kept the old
        # parent, so describe reported a hierarchy containment did not enforce.
        if spec.id in self.graph.scw_specs:
            raise SpecificationExists(f"SCW specification already exists: {spec.id}")
        # Everything that can refuse runs before anything is stored. Registering
        # first meant a refused create (unchartered parent, non-string concept)
        # left the spec in scw_specs with no charter, and the id could never be
        # used again: every retry was "already exists" and there is no delete.
        if not isinstance(spec.concept, str):
            raise TypeError(f"{spec.id} concept must be a string")
        if not isinstance(spec.skills, (list, tuple)) or not all(isinstance(s, str) for s in spec.skills):
            raise TypeError(f"{spec.id} skills must be a list of strings")
        parent = spec.parent_id or self.ROOT_SCW
        needs_charter = spec.id != self.ROOT_SCW and not self.tree.is_chartered(spec.id)
        if needs_charter and not self.tree.is_chartered(parent):
            raise ConstitutionViolation(
                f"{spec.id} declares parent {parent}, which is not chartered; "
                f"create the parent spec first"
            )
        if needs_charter:
            # Charter before registering: the charter itself can still refuse
            # (a constitution that forbids the child), and that too must leave
            # nothing behind.
            charter = getattr(self.isolation, "charter", None)
            if charter is not None:
                charter(spec.id, parent)
            else:
                self.tree.charter(spec.id, parent)
        self.graph.add_scw_spec(spec)
        self._event(
            "scw.spec.create", spec.id,
            {"concept": spec.concept, "skills": spec.skills, "parent": parent},
        )
        return spec

    def instantiate(self, spec_id: str, owner: str, runtime_id: str, address_region: str | None = None) -> SCWInstance:
        spec = self.graph.scw_specs[spec_id]
        region = address_region or spec.id
        skill = spec.skills[0] if spec.skills else "none"
        address = self.graph.address_for_skill(skill, region) if skill != "none" else __import__("maxey0_ss.models", fromlist=["SemanticAddress"]).SemanticAddress("", spec.concept, "", region)
        instance = SCWInstance(instance_id(spec.id, runtime_id), spec.id, owner, runtime_id, address)
        instance.readable.add(instance.id)
        instance.writable.add(instance.id)
        # Register with containment first: it can refuse (unchartered spec,
        # reach beyond the charter), and a window stored before that refusal
        # stayed listed as open in describe/snapshot although containment
        # never admitted it.
        self.isolation.register(instance)
        self.instances[instance.id] = instance
        self._event("scw.instantiate", instance.id, {"runtime": runtime_id, "owner": owner, "address": address.key()})
        return instance

    def close(self, instance_id: str) -> None:
        """Close a window and revoke its reach.

        Closing used to flip a display flag: the instance stayed registered with
        the provider and no decision path read `open`, so a closed window still
        passed reads and writes and still accepted admitted context. Revocation
        is what makes the close mean something.
        """
        instance = self.instances[instance_id]
        instance.open = False
        instance.readable.clear()
        instance.writable.clear()
        revoke = getattr(self.isolation, "revoke", None)
        if revoke is not None:
            revoke(instance_id)
        self._event("scw.close", instance_id, {"revoked": True})

    def admit(self, source: str, target: str, payload: Any) -> None:
        instance = self.instances.get(target)
        if instance is not None and not instance.open:
            raise PermissionError(f"SCW {target} is closed and cannot admit context")
        if not self.isolation.can_read(target, source):
            raise PermissionError(f"SCW {target} cannot read {source}")
        self.instances[target].state.setdefault("admitted", []).append(payload)
        self._event("context.admit", target, {"source": source})

    def snapshot(self) -> dict:
        return {
            "graph": self.graph.graph.to_dict(),
            "scw_instances": {k: {"owner": v.owner, "runtime": v.runtime_id, "address": v.address.key(), "open": v.open} for k, v in self.instances.items()},
            "audit": list(self.audit),
        }


    def _event(self, kind: str, actor: str, data: dict[str, Any]) -> None:
        self.audit.append({"type": kind, "actor": actor, "data": data})
