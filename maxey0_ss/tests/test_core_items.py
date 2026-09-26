"""Cluster "core": evidence.verify truncation, shared attested drift, root
bounds from the environment, scw.start, and early-return provider tasks."""
from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

from maxey0_ss import mcp_surface
from maxey0_ss.api.app import create_app
from maxey0_ss.cache import NEVER_CACHE
from maxey0_ss.containment.hierarchy import ConstitutionViolation
from maxey0_ss.mcp_surface import build_surface
from maxey0_ss.system import RootBounds, SuperSpaceSystem
from maxey0_ss.tasks import owned_by


def _tool(surface, name):
    return next(t for t in surface.tools if t.name == name).handler


@pytest.fixture(autouse=True)
def _unbounded(monkeypatch):
    for name in ("MAXEY0_ROOT_REACH", "MAXEY0_MAX_DEPTH", "MAXEY0_MAX_CHILDREN"):
        monkeypatch.delenv(name, raising=False)


# (1) evidence.verify ---------------------------------------------------------

def _exported(surface):
    _tool(surface, "maxey0-ss.scw.create")({"scw_id": "SCW1", "task": "t"})
    _tool(surface, "maxey0-ss.scw.create")({"scw_id": "SCW2", "task": "t"})
    return _tool(surface, "maxey0-ss.evidence.attestations")({})


def test_verify_detects_truncation_with_expected_entries_and_head():
    surface = build_surface()
    out = _exported(surface)
    records = out["attestations"]
    assert len(records) >= 2
    verify = _tool(surface, "maxey0-ss.evidence.verify")
    full = verify({"records": records, "expected_entries": len(records), "expected_head": out["head"]})
    assert full["ok"] is True
    cut = records[:-1]
    assert verify({"records": cut})["ok"] is True  # a prefix alone verifies
    assert verify({"records": cut, "expected_entries": len(records)})["ok"] is False
    assert verify({"records": cut, "expected_head": out["head"]})["ok"] is False


@pytest.mark.parametrize("args", [
    {"expected_head": 5}, {"expected_entries": "3"}, {"expected_entries": True},
    {"expected_entries": -1},
])
def test_verify_rejects_badly_typed_expectations(args):
    surface = build_surface()
    records = _exported(surface)["attestations"]
    result = _tool(surface, "maxey0-ss.evidence.verify")({"records": records, **args})
    assert result["ok"] is False and "error" in result


# (2) + (3) drift: one store, attested ----------------------------------------

def test_mcp_and_rest_share_one_drift_store_and_it_is_attested():
    system = SuperSpaceSystem()
    app = create_app(system)
    surface = app.state.maxey0_surface
    assert surface.system.drift_runtime is system.drift_runtime
    _tool(surface, "maxey0-ss.scw.create")({"scw_id": "SCW1", "task": "t"})
    started = _tool(surface, "maxey0-ss.scw.start")({"scw_id": "SCW1"})
    iid = started["started"]
    client = TestClient(app)
    # Unanchored over REST: 409 with the MCP tool's fields.
    r = client.post(f"/v1/context/scws/{iid}/drift", json={"vector": [1, 0]})
    assert r.status_code == 409 and r.json()["detail"]["anchored"] is False
    assert client.post(f"/v1/context/scws/{iid}/anchor", json={"vector": [1, 0]}).status_code == 200
    assert iid in system.drift_runtime.baselines
    before = len(system.context.isolation.log)
    rec = _tool(surface, "maxey0-ss.scw.drift")  # MCP measures by spec id
    _tool(surface, "maxey0-ss.scw.drift")({"scw_id": "SCW1", "vector": [1, 0], "anchor": True})
    out = rec({"scw_id": "SCW1", "vector": [0, 1]})
    assert out["drifted"] is True
    entries = system.context.isolation.log.export()[before:]
    kinds = [e["metadata"]["kind"] for e in entries]
    assert kinds == ["semantic.drift.anchor", "semantic.drift.inspect"]
    inspect = entries[1]["metadata"]
    assert set(inspect) >= {"scw_id", "vector_sha256", "distance", "threshold", "drifted", "correction"}
    # Digests only: no raw vector anywhere in the published record.
    assert "[0.0,1.0]" not in str(entries).replace(" ", "")
    assert all(len(e["metadata"]["vector_sha256"]) == 64 for e in entries)


def test_semantic_runtime_without_a_log_still_works():
    from maxey0_ss.semantic.runtime import SemanticRuntime

    rt = SemanticRuntime()
    rt.anchor("SCW1", [1.0, 0.0])
    assert rt.inspect("SCW1", [1.0, 0.0], 0.1).drifted is False


# (7) root bounds -----------------------------------------------------------

def test_root_bounds_default_unbounded():
    bounds = RootBounds.from_env({})
    assert bounds == RootBounds()
    assert SuperSpaceSystem().context.root_constitution.reach is None


@pytest.mark.parametrize("env", [
    {"MAXEY0_MAX_DEPTH": "0"}, {"MAXEY0_MAX_DEPTH": "x"}, {"MAXEY0_MAX_CHILDREN": "-2"},
    {"MAXEY0_ROOT_REACH": "SCW1,,SCW2"},
])
def test_root_bounds_fail_closed(env):
    with pytest.raises(ValueError):
        RootBounds.from_env(env)


def test_root_bounds_from_env_bind_the_tree_and_are_reported(monkeypatch):
    monkeypatch.setenv("MAXEY0_ROOT_REACH", "SCW0, SCW1")
    monkeypatch.setenv("MAXEY0_MAX_CHILDREN", "1")
    monkeypatch.setenv("MAXEY0_MAX_DEPTH", "3")
    surface = build_surface()
    root = surface.system.context.root_constitution
    assert root.reach == frozenset({"SCW0", "SCW1"})
    assert (root.max_depth, root.max_children) == (3, 1)
    report = _tool(surface, "maxey0-ss.deployment")({})["root_bounds"]
    assert report == {"reach": ["SCW0", "SCW1"], "max_depth": 3, "max_children": 1}
    create = _tool(surface, "maxey0-ss.scw.create")
    create({"scw_id": "SCW1", "task": "t"})
    with pytest.raises((ConstitutionViolation, ValueError)):
        create({"scw_id": "SCW2", "task": "t"})  # second child of the root


# (8) scw.start ---------------------------------------------------------------

def test_scw_start_owner_is_the_caller_and_duplicates_are_refused():
    surface = build_surface()
    _tool(surface, "maxey0-ss.scw.create")({"scw_id": "SCW1", "task": "t"})
    start = _tool(surface, "maxey0-ss.scw.start")
    with owned_by("alice"):
        out = start({"scw_id": "SCW1", "owner": "mallory"})
    assert out["owner"] == "alice"
    assert surface.system.context.instances[out["started"]].owner == "alice"
    with pytest.raises(ValueError, match="already running"):
        start({"scw_id": "SCW1"})
    with pytest.raises(ValueError):
        start({"scw_id": "SCW9"})
    assert "maxey0-ss.scw.start" in NEVER_CACHE
    tool = next(t for t in surface.tools if t.name == "maxey0-ss.scw.start")
    assert tool.capability == "scw.admit" or "admit" in str(tool.capability)


def test_scw_start_owner_falls_back_to_local():
    surface = build_surface()
    _tool(surface, "maxey0-ss.scw.create")({"scw_id": "SCW1", "task": "t"})
    assert _tool(surface, "maxey0-ss.scw.start")({"scw_id": "SCW1"})["owner"] == "local"


def test_rest_start_route():
    system = SuperSpaceSystem()
    client = TestClient(create_app(system))
    assert client.post("/v1/context/scws", json={"id": "SCW1", "concept": "c"}).status_code in (200, 201)
    assert client.post("/v1/context/scws/SCW9/start").status_code == 404
    r = client.post("/v1/context/scws/SCW1/start")
    assert r.status_code == 200, r.text
    assert r.json()["started"] in system.context.instances
    assert client.post("/v1/context/scws/SCW1/start").status_code == 409


def test_facade_start():
    from maxey0 import scw

    scw.reset()
    try:
        scw.create("SCW1", task="t")
        assert scw.start("SCW1")["owner"] == "local"
    finally:
        scw.reset()


# (11) early-return provider tasks --------------------------------------------

class _FakeResult:
    def as_dict(self):
        return {"text": "hi"}


class _FakeProvider:
    def __init__(self):
        self.release = threading.Event()

    def complete(self, prompt, **kwargs):
        assert self.release.wait(5)
        return _FakeResult()


def test_provider_complete_async_returns_a_working_handle(monkeypatch):
    fake = _FakeProvider()
    monkeypatch.setattr(mcp_surface, "provider_registry", lambda **_: {"anthropic": fake})
    surface = build_surface()
    complete = _tool(surface, "maxey0-ss.provider.complete")
    out = complete({"provider": "anthropic", "prompt": "p", "async": True})
    assert out["pending"] is True and out["task"]["status"] == "working"
    task_id = out["task"]["taskId"]
    fake.release.set()
    deadline = time.time() + 5
    while surface.tasks.get(task_id).status.value == "working" and time.time() < deadline:
        time.sleep(0.01)
    task = surface.tasks.get(task_id)
    assert task.status.value == "completed" and task.result == {"text": "hi"}


def test_provider_complete_default_is_still_synchronous(monkeypatch):
    fake = _FakeProvider()
    fake.release.set()
    monkeypatch.setattr(mcp_surface, "provider_registry", lambda **_: {"anthropic": fake})
    surface = build_surface()
    out = _tool(surface, "maxey0-ss.provider.complete")({"provider": "anthropic", "prompt": "p"})
    assert out["ok"] is True and out["task"]["status"] == "completed"
    with pytest.raises(ValueError):
        _tool(surface, "maxey0-ss.provider.complete")({"provider": "anthropic", "prompt": "p", "async": "yes"})
