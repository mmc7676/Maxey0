"""The harness layer: declared architecture, skills, and guardrails.

From Macedo (arXiv:2607.00038): "Harness engineering asked what environment,
tools and limits the agent has." The paper's operational anatomy names the
concrete pieces — named, tested skills; plugins and connectors that wire the
agent to real tools; a maker distinct from a checker when a judge is
involved; a sandboxed worktree; a budget ceiling; irreversible actions gated
behind human approval. None of that lived in the runtime before this module:
the MCP tool surface *was* a harness, but nothing declared its shape.

A :class:`HarnessProfile` makes that shape data instead of folklore, and one
piece of it is enforced rather than merely recorded: when a harness declares
`architecture="maker_checker"`, the runtime refuses a loop bound to it from
approving its own work at `loop_tick`. That is this layer's version of the
context layer's sharpest result — specification gaming refused as a type
error rather than discouraged by convention.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatch
from typing import Optional

ARCHITECTURES = ("solo", "maker_checker", "manager")
SANDBOXES = ("shared", "worktree", "none")

#: How hard the runtime holds a verdict to account, weakest first.
#:
#: ``declared``   — the verdict is data. ``verified_by`` is any string; the
#:                  runtime records it and flags a self-approval afterwards.
#:                  This is v0.2.0 behavior and remains the default for
#:                  ``solo`` and ``manager`` harnesses.
#: ``attributed`` — ``verified_by`` must name a *resolvable, currently bound,
#:                  distinct* loop. Closes the hole where passing any string
#:                  other than your own id defeats the check.
#: ``disjoint``   — attributed, **and** the judge's read closure must not
#:                  intersect the maker's write closure outside the maker's
#:                  declared ``exposes`` set, and the judge must not be a
#:                  control-flow descendant of the maker. This is the only
#:                  setting that enforces what the reward-hacking literature
#:                  actually identifies as causal: shared context, not a
#:                  shared name.
#:
#: A ``maker_checker`` harness defaults to ``disjoint``, because that is what
#: declaring the split is *for*. Declaring the architecture and then getting
#: only a string comparison was the gap this vocabulary closes.
VERIFICATION_POLICIES = ("declared", "attributed", "disjoint")

#: When a verdict must carry external evidence (see
#: :mod:`scw_runtime.attest`).
#:
#: ``none``      — a bare boolean verdict is accepted at every level.
#: ``objective`` — a *passing* verdict at a declared level of 1–3 must cite an
#:                 attestation: a command, an exit code, an output digest. The
#:                 objective zone is precisely the zone whose claim is that
#:                 something ran; this makes that claim cost something to
#:                 state.
#: ``all``       — every passing verdict must cite an attestation, including
#:                 levels 4–5, where the evidence is a rubric score or a named
#:                 human approver.
EVIDENCE_POLICIES = ("none", "objective", "all")


@dataclass
class Skill:
    """A named, reusable routine a loop is declared to call.

    The paper's positive principle: a loop with no reusable skills is little
    more than an unbounded retry around a raw model, whereas a loop that
    calls sharp, tested, named skills is a system that composes. `verified` records
    whether that skill has actually been proven, as opposed to merely named.
    """

    skill_id: str
    name: str
    description: str = ""
    verified: bool = False

    def to_dict(self) -> dict:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "description": self.description,
            "verified": self.verified,
        }


@dataclass
class HarnessProfile:
    """The declared environment, tools, and architecture a loop runs inside.

    Attributes
    ----------
    architecture:
        ``solo`` — one agent does everything. ``maker_checker`` — the
        producer and the verifier are distinct actors; a loop bound to a
        maker_checker harness cannot self-approve at `loop_tick` (enforced in
        :mod:`scw_runtime.window`). ``manager`` — an orchestrator delegates to
        helpers; declared for the record, not separately enforced here.
    skills:
        The named, reusable routines this harness makes available.
    strict_skills:
        When true, `harness_call` for a `skill_id` outside this set is
        refused rather than merely logged and flagged.
    tool_grants:
        Named external tools/connectors wired in (issue tracker, CI, a
        staging environment) — declared for audit, not independently
        enforced: the runtime cannot see what a shell call actually touches,
        only that the loop declared it was going to use one of these.
    sandbox:
        ``worktree`` — isolated execution environment per the paper's
        anatomy. ``shared`` — same environment as other loops. ``none`` —
        no isolation at all. Declarative; the runtime does not provision one.
    iteration_budget:
        A harness-wide ceiling across every loop bound to it, distinct from a
        single loop's own `max_iterations`.
    requires_approval:
        Named action patterns that must carry `approved=True` at
        `harness_call` — the family-D guardrail for irreversible actions.
    """

    harness_id: str
    label: str
    created_seq: int
    architecture: str = "solo"
    skills: dict[str, Skill] = field(default_factory=dict)
    strict_skills: bool = False
    tool_grants: tuple[str, ...] = ()
    sandbox: str = "shared"
    iteration_budget: Optional[int] = None
    requires_approval: tuple[str, ...] = ()
    verification_policy: Optional[str] = None
    evidence_policy: str = "none"

    calls: int = 0
    undeclared_calls: int = 0
    approvals_required: int = 0
    approvals_granted: int = 0
    iterations_run: int = 0

    def __post_init__(self) -> None:
        if self.verification_policy is None:
            # Declaring maker_checker *is* declaring that the two contexts are
            # separate. Defaulting it to anything weaker would leave the
            # architecture's name doing work its enforcement does not.
            self.verification_policy = (
                "disjoint" if self.architecture == "maker_checker" else "declared"
            )
        if self.verification_policy not in VERIFICATION_POLICIES:
            raise ValueError(f"verification_policy must be one of {VERIFICATION_POLICIES}")
        if self.evidence_policy not in EVIDENCE_POLICIES:
            raise ValueError(f"evidence_policy must be one of {EVIDENCE_POLICIES}")

    def approval_required_for(self, action: Optional[str]) -> bool:
        """Whether ``action`` matches a declared approval pattern.

        Entries are matched as :mod:`fnmatch` globs, not by string equality.
        They are documented everywhere as "action patterns", and an operator
        who writes ``deploy_*`` should get a gate that can fire rather than
        one that silently never does.
        """
        if action is None:
            return False
        return any(fnmatch(action, pattern) for pattern in self.requires_approval)

    def to_dict(self) -> dict:
        return {
            "harness_id": self.harness_id,
            "label": self.label,
            "architecture": self.architecture,
            "skills": [s.to_dict() for s in self.skills.values()],
            "strict_skills": self.strict_skills,
            "tool_grants": list(self.tool_grants),
            "sandbox": self.sandbox,
            "iteration_budget": self.iteration_budget,
            "requires_approval": list(self.requires_approval),
            "verification_policy": self.verification_policy,
            "evidence_policy": self.evidence_policy,
            "ledger": {
                "calls": self.calls,
                "undeclared_calls": self.undeclared_calls,
                "approvals_required": self.approvals_required,
                "approvals_granted": self.approvals_granted,
                "iterations_run": self.iterations_run,
            },
        }
