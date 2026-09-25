"""A parametrized loop-composition DSL, replacing one hand-written pattern module per
idea (maker_checker_judge.py, debate_peer.py, pipeline.py, nested.py were each a
separate ~130-line file duplicating the same create_scw/bind_scope/open_bridge
choreography). One HarnessSpec plus build_init_ops() below expresses all four, and any
future composition, without a new file.

Terminology, load-bearing for every op this module emits: an SCW is a "Structured
Context World" -- one bound partition instance (a region plus whichever loop(s), zero,
one, or many, are bound to it). "Context window" is the LLM's literal window, one per
session; conflating the two is exactly the confusion this rename exists to prevent,
since a single context window can hold zero, one, or many SCWs, and a real deployment
(multiple LLM providers x multiple agent harnesses) needs SCWs where only certain
provider/harness combinations can even reach a given world. The paper's title is
unaffected -- "window" names the whole address space; "world" names one bound instance
inside it.

A composition is a directed graph over roles. Each role either has its own dedicated
world (scw_sharing="dedicated") or shares one world with every other role in the
harness (scw_sharing="shared" -- this IS the flat/unpartitioned control condition, not
a separate thing to hand-author per pattern). Edges (reads_from) say which other
roles' declared exposure a role may read; the DSL turns that into open_bridge grants
under "dedicated" and turns it into nothing under "shared" (there is only one region,
already fully visible to everyone bound to it -- the absence of grants IS the flat
condition's structural signature, exactly as maker_checker_judge.py already encoded by
hand).

Nesting (parent_of) is a separate axis from sharing: a nested composition still picks
dedicated or shared worlds, but additionally chains bind_scope calls with
parent_loop_id so ceiling checks (NestingViolation, LoopExhausted) have real ancestry
to test against.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

Topology = Literal["star", "chain", "parallel", "nested"]
Sharing = Literal["dedicated", "shared"]


@dataclass(frozen=True)
class RoleDef:
    """One participant in a composition.

    reads_from: role_ids whose declared `exposes` this role is granted read access to
        (plus resource names -- see HarnessSpec.resources -- which every role may read
        unless excluded_resources says otherwise). This is the topology: a star has
        every checking role reading the one maker; a chain has role[i] reading only
        role[i-1]; parallel peers have empty reads_from until a synthesizer/judge role
        reads all of them.
    exposes: region names this role publishes for others to read. Usually one durable
        region ("patches", "plan", "proposal-a", ...).
    verification_level / max_iterations / goal: passed straight through to bind_scope.
    excluded_resources: resource names in HarnessSpec.resources this role does NOT
        get, even though resources are granted to everyone by default. This is how a
        structural (checker) role is denied the rubric while a grading (judge) role
        keeps it, without a bespoke per-pattern grant list.
    """

    role_id: str
    reads_from: frozenset[str] = frozenset()
    exposes: tuple[str, ...] = ()
    verification_level: int = 1
    max_iterations: int = 2
    goal: str = ""
    excluded_resources: frozenset[str] = frozenset()
    criterion_id: str | None = None
    # What this role's primary response IS, independent of whether it's the one role
    # (HarnessSpec.artifact_role) whose code becomes THE tested patch. Multiple roles
    # can produce "code" (three blind peers each propose a candidate fix); only one is
    # ever the artifact_role. "verdict" roles must answer in the VERDICT:/REASON:
    # format; "text" roles (a planner's strategy notes) are neither code nor a verdict
    # and are written raw with no parsing and no pytest.
    output_kind: Literal["code", "verdict", "text"] = "verdict"


@dataclass(frozen=True)
class HarnessSpec:
    """A full composition: everything needed to build_init_ops() for one experiment.

    harness_id: also the runtime create_harness harness_id and the ops.json namespace.
    resources: read-only reference regions (e.g. "target", "rubric") granted to every
        role by default, minus each role's excluded_resources.
    architecture / verification_policy: passed to create_harness, following the same
        scw-vs-flat pairing maker_checker_judge.py established --
        (architecture="maker_checker", verification_policy="disjoint") for scw,
        (same architecture, verification_policy="declared") for flat -- since the
        manipulation under test is the PARTITION, not the harness's own architecture
        tag, which stays constant across both arms of every comparison.
    parent_of: role_id -> parent role_id, for nested topologies. A role absent from
        this mapping (or the mapping is empty) is unnested.
    negative_controls: extra (from_role, to_role, mode) triples that MUST be refused
        -- e.g. a peer reading another peer's private pad, a role writing its own
        criterion. Auto-populated with the "one role reads another's dedicated pad
        outside its declared reads_from" cases; extend per-composition for anything
        domain-specific (e.g. "maker attempts to edit its own rubric").
    """

    harness_id: str
    topology: Topology
    roles: tuple[RoleDef, ...]
    resources: tuple[str, ...] = ()
    parent_of: dict[str, str] = field(default_factory=dict)
    iteration_budget: int = 16
    extra_negative_controls: tuple[tuple[str, str, str], ...] = ()
    # (criterion_id, resource_name, label) -- pinned ONLY under the scw condition,
    # matching the original hand-written pattern's choice: flat's verification_policy
    # is "declared", which does not use drift detection, so pinning there would be
    # inert ceremony rather than a real check. A role's RoleDef.criterion_id is only
    # honored on bind_scope when the harness also pins that criterion here.
    pin_criteria: tuple[tuple[str, str, str], ...] = ()
    # Which role's exposed output is literal replacement code for the fixture, i.e.
    # the one thing ingest can objectively pytest. Not every role produces one: a
    # planner writes a plan, a checker writes a verdict, a peer writes a candidate
    # that may or may not become "the" patch. Exactly one role per composition is the
    # artifact producer; ingest refuses to run pytest against anything else.
    artifact_role: str = ""

    def role(self, role_id: str) -> RoleDef:
        for r in self.roles:
            if r.role_id == role_id:
                return r
        raise KeyError(f"{self.harness_id}: no role {role_id!r}")


def _pad_id(role_id: str) -> str:
    return f"{role_id}-pad"


def _resource_id(name: str) -> str:
    return name  # resources are top-level regions, named directly


def build_init_ops(
    spec: HarnessSpec,
    condition: Literal["scw", "flat"],
    resource_data: dict[str, str],
) -> list[dict[str, Any]]:
    """The one function every experiment calls instead of a bespoke pattern module.

    resource_data maps each name in spec.resources to the literal text written into
    that region at init (e.g. {"target": "...", "rubric": "..."}).
    """
    ops: list[dict[str, Any]] = []
    add = lambda op, **kw: ops.append({"op": op, "args": kw})  # noqa: E731

    verification_policy = "disjoint" if condition == "scw" else "declared"
    add(
        "create_harness",
        label=f"{spec.harness_id} ({condition})",
        harness_id=spec.harness_id,
        architecture="maker_checker",
        verification_policy=verification_policy,
        evidence_policy="objective",
        iteration_budget=spec.iteration_budget,
    )

    if condition == "scw":
        # -- dedicated worlds: one region per resource, one scratch pad per role, one
        # durable region per DECLARED EXPOSURE. The exposure regions are what a role
        # actually publishes to (its pad is private scratch space, never readable by
        # anyone else, including the role's own downstream readers) -- so every name
        # appearing in any role.exposes must exist as its own durable region before
        # any bind_scope references it or any bridge grants read access to it.
        for name in spec.resources:
            add("create_scw", label=f"resource:{name}", region_type="reference", scw_id=_resource_id(name))
        exposed_regions = sorted({target for role in spec.roles for target in role.exposes})
        for target in exposed_regions:
            add("create_scw", label=f"handoff:{target}", region_type="durable", scw_id=target)
        # A nested role's pad must be created as a SUB-region of its parent's pad --
        # bind_scope's containment check (NestingViolation) requires the child loop's
        # bound region to be reachable from the parent's own bound region, not merely
        # coexist as another top-level region. Roles without a parent bind at the top
        # level, exactly as before.
        for role in spec.roles:
            parent_role_id = spec.parent_of.get(role.role_id)
            kw: dict[str, Any] = dict(label=f"{role.role_id} pad", region_type="scratchpad", scw_id=_pad_id(role.role_id))
            if parent_role_id:
                kw["parent_scw_id"] = _pad_id(parent_role_id)
            add("create_scw", **kw)
        for name, data in resource_data.items():
            add("write", scw_id=_resource_id(name), data=data)
        for criterion_id, resource_name, label in spec.pin_criteria:
            add("pin_criterion", scw_id=_resource_id(resource_name), criterion_id=criterion_id, label=label)
        for role in spec.roles:
            parent = spec.parent_of.get(role.role_id)
            kw: dict[str, Any] = dict(
                loop_id=role.role_id,
                scw_id=_pad_id(role.role_id),
                harness_id=spec.harness_id,
                trigger="manual",
                verification_level=role.verification_level,
                max_iterations=role.max_iterations,
                exposes=list(role.exposes),
                goal=role.goal or f"{role.role_id} completes its bound task",
            )
            if role.criterion_id:
                kw["criterion_id"] = role.criterion_id
            if parent:
                kw["parent_loop_id"] = parent
            add("bind_scope", **kw)
        # -- grants: resources (minus exclusions) + topology edges -------------------
        for role in spec.roles:
            for name in spec.resources:
                if name in role.excluded_resources:
                    continue
                add(
                    "open_bridge",
                    from_scw_id=_pad_id(role.role_id),
                    to_scw_id=_resource_id(name),
                    mode="read",
                    reason=f"{role.role_id} reads resource {name}",
                    loop_id=role.role_id,
                )
            for upstream_id in role.reads_from:
                upstream = spec.role(upstream_id)
                for target in upstream.exposes:
                    add(
                        "open_bridge",
                        from_scw_id=_pad_id(role.role_id),
                        to_scw_id=target,
                        mode="read",
                        reason=f"{role.role_id} reads {upstream_id}'s declared handoff",
                        loop_id=role.role_id,
                    )
            for target in role.exposes:
                add(
                    "open_bridge",
                    from_scw_id=_pad_id(role.role_id),
                    to_scw_id=target,
                    mode="write",
                    reason=f"{role.role_id} publishes its declared handoff surface",
                    loop_id=role.role_id,
                )
        # -- negative controls: pad privacy is a UNIVERSAL invariant in this DSL, not
        # conditional on the topology. reads_from only ever grants access to another
        # role's declared `exposes` regions (via the grant loop above); it never opens
        # a bridge to that role's raw pad. So every role, including one immediately
        # upstream in the topology, must still be refused if it tries to read another
        # role's pad directly -- that refusal is exactly what makes "declare an
        # exposes surface" a real requirement rather than a formality. Do not skip
        # role pairs connected by reads_from here; that would silently stop testing
        # the one invariant this whole partition design rests on.
        role_ids = [r.role_id for r in spec.roles]
        for role in spec.roles:
            for other_id in role_ids:
                if other_id == role.role_id:
                    continue
                ops.append({
                    "op": "open_bridge",
                    "expect_refusal": True,
                    "args": {
                        "from_scw_id": _pad_id(role.role_id),
                        "to_scw_id": _pad_id(other_id),
                        "mode": "read",
                        "loop_id": role.role_id,
                        "reason": f"negative control: {role.role_id} attempts to read {other_id}'s private pad",
                    },
                })
        for from_role, to_role, mode in spec.extra_negative_controls:
            ops.append({
                "op": "open_bridge",
                "expect_refusal": True,
                "args": {
                    "from_scw_id": _pad_id(from_role),
                    "to_scw_id": to_role,
                    "mode": mode,
                    "loop_id": from_role,
                    "reason": f"negative control: {from_role} attempts {mode} on {to_role}",
                },
            })

    else:  # flat
        add("create_scw", label="Flat shared world", region_type="durable", scw_id="flat-context")
        for data in resource_data.values():
            add("write", scw_id="flat-context", data=data)
        for role in spec.roles:
            parent = spec.parent_of.get(role.role_id)
            # No criterion_id here, deliberately: flat's verification_policy is
            # "declared", not "disjoint", so criterion drift detection is not part of
            # what this condition tests -- pinning one would be inert ceremony, and
            # the original hand-written pattern never did it either.
            kw = dict(
                loop_id=role.role_id,
                scw_id="flat-context",
                harness_id=spec.harness_id,
                trigger="manual",
                verification_level=role.verification_level,
                max_iterations=role.max_iterations,
                goal=f"{role.role_id} works from the shared flat world",
            )
            if parent:
                kw["parent_loop_id"] = parent
            add("bind_scope", **kw)
        # no grants to add: every role sees the whole shared region by construction --
        # the absence of a partition IS the flat condition, not a separate op to write.

    return ops


def declared_minimal_regions(spec: HarnessSpec, role_id: str) -> frozenset[str]:
    """What lib.probes.RoleSpec needs: the region set a role should legitimately
    reach under the SCW condition -- its own pad, its granted resources, and its
    upstream roles' exposed regions. Anything beyond this in a real read_closure is
    leakage."""
    role = spec.role(role_id)
    regions = {_pad_id(role_id)}
    regions.update(n for n in spec.resources if n not in role.excluded_resources)
    for upstream_id in role.reads_from:
        regions.update(spec.role(upstream_id).exposes)
    return frozenset(regions)
