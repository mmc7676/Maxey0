from __future__ import annotations

import math


def cosine_distance(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise ValueError("vectors must have equal dimension")
    # A NaN distance compares False against any threshold, so a non-finite
    # input made drift fail open (drifted=False). Refuse it instead.
    if not all(math.isfinite(x) for x in a) or not all(math.isfinite(x) for x in b):
        raise ValueError("vectors must contain only finite numbers")
    # Scale by the largest magnitude first. Unscaled, [1e200, 0] overflowed its
    # norm to inf and [1e-200, 0] underflowed to 0, and both read as distance
    # 1.0 against a vector pointing the same way. Cosine is scale-invariant.
    sa = max((abs(x) for x in a), default=0.0)
    sb = max((abs(x) for x in b), default=0.0)
    if sa == 0 or sb == 0:
        return 1.0
    a = [x / sa for x in a]
    b = [x / sb for x in b]
    na = math.sqrt(math.fsum(x * x for x in a))
    nb = math.sqrt(math.fsum(x * x for x in b))
    result = 1.0 - math.fsum(x * y for x, y in zip(a, b)) / (na * nb)
    if not math.isfinite(result):
        raise ValueError("cosine distance is not finite")
    return result


def weighted_semantic_distance(a: dict[str, float], b: dict[str, float], weights: dict[str, float]) -> float:
    keys = set(a) | set(b)
    total = sum(weights.get(k, 1.0) for k in keys)
    if total == 0:
        return 0.0
    return sum(weights.get(k, 1.0) * abs(a.get(k, 0.0) - b.get(k, 0.0)) for k in keys) / total


def superposition(states: list[list[float]], weights: list[float]) -> list[float]:
    if not states or len(states) != len(weights):
        raise ValueError("states and weights must be non-empty and aligned")
    dimension = len(states[0])
    if any(len(s) != dimension for s in states):
        raise ValueError("all states must have equal dimension")
    total = sum(weights)
    if total == 0:
        raise ValueError("weights cannot sum to zero")
    return [sum(w * s[i] for w, s in zip(weights, states)) / total for i in range(dimension)]


def drift(baseline: list[float], current: list[float], threshold: float) -> tuple[float, bool]:
    # `d > nan` is always False: a NaN threshold would report every window
    # as not drifted, which is the one answer a drift check must not fail to.
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) \
            or not math.isfinite(threshold):
        raise ValueError("threshold must be a finite number")
    d = cosine_distance(baseline, current)
    return d, d > threshold
