from __future__ import annotations

import math
from collections import deque

from ..models import DriftRecord
from .math import drift, superposition


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


class SemanticRuntime:
    """Second runtime: observes semantic state, detects drift, and proposes correction."""

    def __init__(self) -> None:
        self.baselines: dict[str, list[float]] = {}
        self.records: deque[DriftRecord] = deque(maxlen=MAX_RECORDS)

    def anchor(self, scw_id: str, vector: list[float]) -> None:
        self.baselines[scw_id] = validate_vector(vector)

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
        return record

    def maintain_superposition(self, states: list[list[float]], weights: list[float]) -> list[float]:
        return superposition(states, weights)

    def correct(self, scw_id: str, vector: list[float]) -> None:
        self.baselines[scw_id] = validate_vector(vector)
