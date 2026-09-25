"""Pinned acceptance criteria, and verdicts that carry evidence.

Two constructs, one purpose: to make a claim about something that happened
*outside* the window cost something to state inside it.

**The criterion.** A loop is supposed to be scored against a frozen yardstick
so that rounds are comparable and so that "fix the code" cannot quietly become
"edit the test". Freezing it has two halves, and a runtime that does only the
first is not freezing anything:

1. *Reachability* — the graded loop must not be able to write the region
   holding the criterion. That half the region model already gives, and
   :func:`scw_runtime.partition.disjointness` rule R5 checks it.
2. *Drift* — the criterion's bytes must not change while the loop is being
   scored against them. A read-only region stops the loop from editing it and
   does nothing at all about the *host* rewriting it mid-run, which is the
   commoner and quieter version of the same failure. Pinning records the
   region's signature at bind and re-checks it at every tick, so the yardstick
   moving is an event rather than a mystery.

**The evidence.** ``loop_tick(verified=True)`` is a boolean, and a boolean is
exactly as expensive to assert when a test suite passed as when nothing ran.
Levels 1–3 of the verification ladder all claim that something executed — an
assertion, a linter, a deploy. An :class:`Attestation` makes that claim
specific: a command, an exit code, a digest of the output, bound to the loop
that ran it and to the window bytes it describes, single-use, and in the log.

**What this is not.** The runtime cannot execute a shell command, cannot
observe one, and cannot verify that a digest is of that command's real output.
An attestation remains an assertion by the caller. What changes is that the
assertion is specific rather than boolean, cannot be recycled across
iterations, cannot be borrowed from another loop, goes stale when the window
it describes moves underneath it, and is permanently in a hash-chained log. A
caller determined to lie must now lie in detail, repeatedly, and on the
record. That is a real difference from a bare ``True``, and it is emphatically
not interception — see ``docs/SPEC.md`` §11 and the paper's limitations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

#: What an attestation is evidence *of*.
#:
#: ``command``  — something ran: a command string, optionally argv, an exit
#:                code, and a digest of its output. The ladder's levels 1–3.
#: ``artifact`` — a file or blob exists with this digest: a golden output, a
#:                coverage report, a build product.
#: ``rubric``   — a model judged against a named, pinned criterion and
#:                returned a score. Level 4.
#: ``human``    — a named person approved. Level 5.
ATTESTATION_KINDS = ("command", "artifact", "rubric", "human")


@dataclass
class Criterion:
    """A region frozen as the yardstick a loop is graded against."""

    criterion_id: str
    scw_id: str
    label: str
    signature: str
    pinned_seq: int
    pinned_tick: int
    status: str = "pinned"  # pinned | released
    drift_detected: int = 0

    def to_dict(self) -> dict:
        return {
            "criterion_id": self.criterion_id,
            "scw_id": self.scw_id,
            "label": self.label,
            "signature": self.signature,
            "pinned_seq": self.pinned_seq,
            "pinned_tick": self.pinned_tick,
            "status": self.status,
            "drift_detected": self.drift_detected,
        }


@dataclass
class Attestation:
    """Evidence offered in support of one verdict.

    ``scope_signature`` is the fingerprint of the attesting loop's bound
    region at the moment the evidence was recorded. A tick that cites this
    attestation re-checks it: if the loop has rewritten its own work since the
    check ran, the evidence no longer describes the thing being graded, and
    the verdict is refused rather than quietly accepted. That single field is
    what stops "run the tests, then change the code, then claim the pass".
    """

    evidence_id: str
    loop_id: str
    kind: str
    attested_seq: int
    attested_tick: int
    scope_signature: str
    command: Optional[str] = None
    argv: tuple[str, ...] = ()
    exit_code: Optional[int] = None
    output_sha256: Optional[str] = None
    output_bytes: Optional[int] = None
    artifact_sha256: Optional[str] = None
    criterion_id: Optional[str] = None
    score: Optional[float] = None
    approver: Optional[str] = None
    note: str = ""
    consumed_by_tick: Optional[int] = None

    @property
    def consumed(self) -> bool:
        return self.consumed_by_tick is not None

    def passes(self) -> bool:
        """Whether the evidence itself reads as a pass.

        A command attestation with a non-zero exit code is evidence of
        *failure*; citing it in support of ``verified=True`` is the
        contradiction this catches.
        """
        if self.kind == "command":
            return self.exit_code == 0
        return True

    def to_dict(self) -> dict:
        return {
            "evidence_id": self.evidence_id,
            "loop_id": self.loop_id,
            "kind": self.kind,
            "command": self.command,
            "argv": list(self.argv),
            "exit_code": self.exit_code,
            "output_sha256": self.output_sha256,
            "output_bytes": self.output_bytes,
            "artifact_sha256": self.artifact_sha256,
            "criterion_id": self.criterion_id,
            "score": self.score,
            "approver": self.approver,
            "note": self.note,
            "attested_seq": self.attested_seq,
            "attested_tick": self.attested_tick,
            "scope_signature": self.scope_signature,
            "consumed_by_tick": self.consumed_by_tick,
        }


def validate_kind(kind: str, **fields: object) -> None:
    """Refuse an attestation that does not carry what its kind claims.

    An empty attestation of the right shape would be worse than none: it would
    satisfy an evidence policy while proving nothing, which is the failure
    mode the policy exists to prevent.
    """
    if kind not in ATTESTATION_KINDS:
        raise ValueError(f"kind must be one of {ATTESTATION_KINDS}")
    if kind == "command" and not fields.get("command"):
        raise ValueError("kind='command' requires command=<the command that ran>")
    if kind == "command" and fields.get("exit_code") is None:
        raise ValueError("kind='command' requires exit_code=<its exit status>")
    if kind == "artifact" and not fields.get("artifact_sha256"):
        raise ValueError("kind='artifact' requires artifact_sha256=<digest of the artifact>")
    if kind == "rubric" and not fields.get("criterion_id"):
        raise ValueError(
            "kind='rubric' requires criterion_id=<the pinned criterion scored against>"
        )
    if kind == "human" and not fields.get("approver"):
        raise ValueError("kind='human' requires approver=<who signed off>")
