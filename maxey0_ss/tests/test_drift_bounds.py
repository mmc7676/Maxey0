"""Drift must fail closed on bad numbers, and its record must stay bounded.

A NaN distance compares False against any threshold, so a NaN vector or
threshold reported a drifted window as healthy, and over HTTP the NaN record
was stored before the JSON encoder refused it. Separately, every inspection
kept two full vectors in an unbounded list reachable with scw.read alone.
"""
from __future__ import annotations

import math

import pytest

from maxey0_ss.mcp_surface import build_surface
from maxey0_ss.semantic.math import cosine_distance
from maxey0_ss.semantic.runtime import MAX_DIMENSION, MAX_RECORDS, SemanticRuntime


def tool(surface, name):
    return next(t for t in surface.tools if t.name == name)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_a_non_finite_current_vector_is_refused_and_not_recorded(bad):
    rt = SemanticRuntime()
    rt.anchor("SCW1", [1.0, 0.0])
    with pytest.raises(ValueError):
        rt.inspect("SCW1", [bad, 0.0], 0.15)
    assert len(rt.records) == 0


@pytest.mark.parametrize("bad", [math.nan, math.inf, -0.1, 2.5, "0.1", True])
def test_a_bad_threshold_is_refused(bad):
    rt = SemanticRuntime()
    rt.anchor("SCW1", [1.0, 0.0])
    with pytest.raises(ValueError):
        rt.inspect("SCW1", [0.0, 1.0], bad)
    assert len(rt.records) == 0


@pytest.mark.parametrize("bad", [[math.nan, 0.0], ["a", "b"], [], [True], [0.0] * (MAX_DIMENSION + 1)])
def test_a_bad_baseline_is_never_stored(bad):
    rt = SemanticRuntime()
    with pytest.raises(ValueError):
        rt.anchor("SCW1", bad)
    assert "SCW1" not in rt.baselines


def test_magnitude_does_not_break_the_distance():
    assert cosine_distance([1.0, 0.0], [1e200, 0.0]) == pytest.approx(0.0)
    assert cosine_distance([1e-200, 0.0], [1e-200, 0.0]) == pytest.approx(0.0)


def test_records_are_bounded():
    rt = SemanticRuntime()
    rt.anchor("SCW1", [1.0, 0.0])
    for _ in range(MAX_RECORDS + 50):
        rt.inspect("SCW1", [0.0, 1.0], 0.15)
    assert len(rt.records) == MAX_RECORDS


def test_the_mcp_tool_refuses_nan_before_anchoring():
    surface = build_surface()
    tool(surface, "maxey0-ss.scw.create").handler({"scw_id": "SCW4", "task": "t"})
    drift = tool(surface, "maxey0-ss.scw.drift")
    with pytest.raises(ValueError):
        drift.handler({"scw_id": "SCW4", "vector": ["nan", 0], "anchor": True})
    drift.handler({"scw_id": "SCW4", "vector": [1.0, 0.0], "anchor": True})
    with pytest.raises(ValueError):
        drift.handler({"scw_id": "SCW4", "vector": [0.0, 1.0], "threshold": "nan"})
