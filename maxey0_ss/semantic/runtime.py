from __future__ import annotations

import hashlib
import json
import math
from collections import deque
from typing import TYPE_CHECKING

from ..models import DriftRecord
from .math import drift, superposition

if TYPE_CHECKING:  # the containment package imports nothing from here
    from ..containment.attestation import AttestationLog

#: Recorded as the deciding provider on every drift attestation.
DRIFT_PROVIDER = "semantic-runtime"


class UnanchoredWindow(RuntimeError):
    """Drift was inspected on a window that was never anchored.

    Raised rather than answered, because the alternative answers wrongly: with
    no baseline there is nothing to measure against, and adopting the current
    vector reports distance 0.0 on a window that may have drifted arbitrarily
    far. A caller that wants the old behavior anchors first, which is a
    decision rather than an accident.
    """


#: Largest vector accepted. Uncapped, one caller could anchor a 400k-element
#: baseline and every inspection kept another full copy in `records`.
MAX_DIMENSION = 4096
#: Records kept. Each holds two vectors, and inspection needs only scw.read, so
#: an unbounded list let any reader grow the process until it ran out of memory.
MAX_RECORDS = 256


def validate_vector(vector: object) -> list[float]:
    """A non-empty list of finite numbers within the dimension cap, or ValueError.

    Checked here, not only at a transport, so no caller can store a baseline
    that every later inspection then fails on (strings, NaN, inf).
    """
    if not isinstance(vector, (list, tuple)) or not vector:
        raise ValueError("vector must be a non-empty list of numbers")
    if len(vector) > MAX_DIMENSION:
        raise ValueError(f"vector dimension {len(vector)} exceeds {MAX_DIMENSION}")
    out: list[float] = []
    for value in vector:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("vector must contain only numbers")
        value = float(value)
        if not math.isfinite(value):
            raise ValueError("vector must contain only finite numbers")
        out.append(value)
    return out


def validate_threshold(threshold: object) -> float:
    """A finite threshold in [0, 2], the range of a cosine distance."""
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise ValueError("threshold must be a number")
    threshold = float(threshold)
    if not math.isfinite(threshold) or not 0.0 <= threshold <= 2.0:
        raise ValueError("threshold must be a finite number in [0, 2]")
    return threshold


def vector_digest(vector: list[float]) -> str:
    """SHA-256 of a validated vector's canonical JSON.

    What the attestation chain carries instead of the vector. The chain is
    published through `evidence.attestations`, and an embedding is derived
    from the content it describes, so recording it would publish that content
    in a recoverable form. A digest still lets an auditor match a record to a
    vector they already hold.
    """
    return hashlib.sha256(
        json.dumps(vector, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class SemanticRuntime:
    """Second runtime: observes semantic state, detects drift, and proposes correction."""

    def __init__(self, log: "AttestationLog | None" = None) -> None:
        self.baselines: dict[str, list[float]] = {}
        self.records: deque[DriftRecord] = deque(maxlen=MAX_RECORDS)
        #: Where anchors and inspections are attested. Anchoring decides what
        #: every later measurement is judged against, so a re-anchor that made
        #: a drifted window read as healthy used to leave no trace outside the
        #: bounded, in-memory `records`; on the chain it is tamper-evident.
        self.log = log

    def _attest(self, kind: str, scw_id: str, metadata: dict) -> None:
        if self.log is None:
            return
        # Imported here: containment -> context -> semantic would otherwise be
        # a cycle at import time for callers that import this module first.
        from ..containment.protocol import ContainmentDecision, Operation

        self.log.record(ContainmentDecision(
            allowed=True,
            operation=Operation.READ if kind == "inspect" else Operation.WRITE,
            agent_scw=scw_id,
            target_scw=scw_id,
            reason=f"drift {kind}",
            provider=DRIFT_PROVIDER,
            metadata={"kind": f"semantic.drift.{kind}", "scw_id": scw_id, **metadata},
        ))

    def anchor(self, scw_id: str, vector: list[float]) -> None:
        vector = validate_vector(vector)
        self.baselines[scw_id] = vector
        self._attest("anchor", scw_id, {
            "vector_sha256": vector_digest(vector), "dimension": len(vector),
        })

    def inspect(self, scw_id: str, current: list[float], threshold: float) -> DriftRecord:
        """Measure drift against the anchored baseline.

        `setdefault` used to install `current` as the baseline on a miss, so an
        un-anchored window always reported distance 0.0 and drifted=False —
        and each inspection silently re-pinned the baseline to wherever the
        window had already drifted to. The failure was invisible, because the
        record echoed a baseline equal to the current vector, which reads as a
        healthy window.
        """
        if scw_id not in self.baselines:
            raise UnanchoredWindow(
                f"{scw_id} has no anchored baseline; anchor() it before inspecting "
                f"drift, or there is nothing to measure against"
            )
        baseline = self.baselines[scw_id]
        current = validate_vector(current)
        threshold = validate_threshold(threshold)
        distance, drifted = drift(baseline, current, threshold)
        correction = "re-anchor-and-reroute" if drifted else None
        record = DriftRecord(scw_id, baseline, current, distance, threshold, drifted, correction)
        self.records.append(record)
        self._attest("inspect", scw_id, {
            "baseline_sha256": vector_digest(baseline),
            "vector_sha256": vector_digest(current),
            "distance": distance, "threshold": threshold,
            "drifted": drifted, "correction": correction,
        })
        return record

    def maintain_superposition(self, states: list[list[float]], weights: list[float]) -> list[float]:
        return superposition(states, weights)

    def correct(self, scw_id: str, vector: list[float]) -> None:
        # Replaces the baseline exactly as anchor() does, so it is attested
        # the same way; otherwise it was the unrecorded way to re-anchor.
        vector = validate_vector(vector)
        self.baselines[scw_id] = vector
        self._attest("correct", scw_id, {
            "vector_sha256": vector_digest(vector), "dimension": len(vector),
        })
