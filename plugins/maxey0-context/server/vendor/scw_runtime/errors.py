"""Error types for the SCW runtime.

Every error carries a machine-readable ``code`` so that MCP tool responses and
the event stream can express failure without relying on prose matching.
"""

from __future__ import annotations


class SCWError(Exception):
    """Base class for all runtime errors."""

    code = "scw_error"

    def __init__(self, message: str, **detail: object) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail

    def to_dict(self) -> dict:
        return {"ok": False, "error": self.code, "message": self.message, **self.detail}


class UnknownRegion(SCWError):
    code = "unknown_region"


class UnknownLoop(SCWError):
    code = "unknown_loop"


class UnknownBridge(SCWError):
    code = "unknown_bridge"


class UnknownPrompt(SCWError):
    code = "unknown_prompt"


class UnknownHarness(SCWError):
    code = "unknown_harness"


class IsolationViolation(SCWError):
    """A bound scope tried to touch a region outside its assigned SCW.

    This is the enforcement point that makes SCW boundaries structural rather
    than conventional. It is raised *before* any state is mutated.
    """

    code = "isolation_violation"


class PolicyViolation(SCWError):
    """The operation is legal for the scope but forbidden by the region policy."""

    code = "policy_violation"


class BudgetExceeded(SCWError):
    code = "budget_exceeded"


class RegionClosed(SCWError):
    code = "region_closed"


class LoopExhausted(SCWError):
    code = "loop_exhausted"


class DuplicateId(SCWError):
    code = "duplicate_id"


class PromptViolation(SCWError):
    """A prompt-layer rule was broken: a bound loop tried to author or revise
    a prompt, an unknown variable was bound, or a locked prompt was revised.

    This is the prompt-layer analogue of :class:`PolicyViolation`: legal for
    nobody bound, forbidden for anybody bound — a loop can never rewrite its
    own instructions, with or without a bridge, because prompts do not
    participate in the bridge/scope model at all.
    """

    code = "prompt_violation"


class HarnessViolation(SCWError):
    """A harness-layer rule was broken: an undeclared skill was called under
    ``strict_skills``, an action requiring approval ran without it, or a loop
    bound to a ``maker_checker`` harness tried to approve its own work.
    """

    code = "harness_violation"


class CriterionViolation(SCWError):
    """A pinned acceptance criterion moved, or the loop being graded can
    reach it.

    A frozen yardstick that the graded party can edit is not frozen. This
    covers both halves: the criterion's bytes changed since it was pinned
    (drift, whoever caused it), and the criterion sits inside the write
    closure of the loop it is grading (reachability).
    """

    code = "criterion_violation"


class AttestationViolation(SCWError):
    """A verdict lacked the evidence its declared verification level claims,
    or the evidence offered was stale, reused, or another loop's.

    Levels 1–3 of the ladder assert that something *ran* — an assertion, a
    linter, a test suite. This error is what makes that assertion cost
    something to state.
    """

    code = "attestation_violation"


class NestingViolation(SCWError):
    """A loop tree rule was broken: a cycle, an over-deep nesting, a child
    outside its parent's partition, or a multiplicative ceiling exceeded."""

    code = "nesting_violation"


class DisjointnessViolation(HarnessViolation):
    """A verdict was supplied by a judge whose context is not provably
    separate from the maker's.

    Subclasses :class:`HarnessViolation` because it is only ever raised by a
    harness's declared ``verification_policy`` — so a caller already handling
    harness refusals keeps working, and one that wants to distinguish the
    partition failure specifically can catch this instead.

    This is the partition layer's sharpest refusal, and the reason it exists
    is causal rather than stylistic: the failure the literature documents is
    not "the same agent approved itself" but "the generator and the judge
    shared context". Naming a different actor does not break a shared
    context; having a disjoint reachable set does. So this error is raised
    when the *graph* says the judge could see what the maker wrote, whatever
    the two are called.
    """

    code = "disjointness_violation"


class ChainBroken(SCWError):
    """The event log's hash chain does not validate."""

    code = "chain_broken"
