"""Low-severity defects from the deep review, one regression each.

Each of these was a caller-supplied value reaching code that trusted it: an
exported dict that aliased the chain, an id regex that accepted a newline, a
REST route with no duplicate check, bodies that became 500s, and an A2A caller
choosing its own admission bar.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from maxey0_ss.api.app import create_app
from maxey0_ss.containment.attestation import AttestationLog
from maxey0_ss.containment.protocol import ContainmentDecision, Operation
from maxey0_ss.context.service import SpecificationExists
from maxey0_ss.examples.maker_checker_judge import build_demo
from maxey0_ss.host_window import HostWindowObserver
from maxey0_ss.identity import InvalidSCWIdentifier, instance_id, is_scw_id, is_scw_instance_id
from maxey0_ss.models import SCWSpec
from maxey0_ss.system import SuperSpaceSystem


# --- #3 exported metadata is a copy ------------------------------------------


def _log_with_metadata(meta):
    log = AttestationLog()
    log.record(ContainmentDecision(True, Operation.READ, "SCW1", "SCW2", "r", "p", metadata=meta))
    return log


def test_mutating_an_exported_record_does_not_rewrite_the_chain():
    log = _log_with_metadata({"m": "a"})
    log.export()[-1]["metadata"]["m"] = "tampered"
    assert log.verify().ok is True


def test_mutating_the_callers_dict_after_record_does_not_rewrite_the_chain():
    meta = {"m": "a"}
    log = _log_with_metadata(meta)
    meta["m"] = "changed"
    assert log.verify().ok is True


# --- #6 identifiers ----------------------------------------------------------


@pytest.mark.parametrize("bad", ["SCW8\n", "SCW١٢", "SCW", "xSCW1", "SCW1234567890"])
def test_malformed_spec_ids_are_rejected(bad):
    assert not is_scw_id(bad)


def test_instance_ids_reject_a_trailing_newline_and_bad_runtime_ids():
    assert is_scw_instance_id("SCW1@rt-1")
    assert not is_scw_instance_id("SCW1@rt\n")
    with pytest.raises(InvalidSCWIdentifier):
        instance_id("SCW1", "rt/../x")


# --- #7 duplicates are refused on every transport ----------------------------


def test_create_spec_refuses_a_duplicate():
    context = SuperSpaceSystem().context
    context.create_spec(SCWSpec("SCW1", None, "Task", []))
    with pytest.raises(SpecificationExists):
        context.create_spec(SCWSpec("SCW1", None, "Other", []))
    assert context.graph.scw_specs["SCW1"].concept == "Task"


def test_rest_create_routes_answer_409_on_a_duplicate():
    client = TestClient(create_app(SuperSpaceSystem()))
    assert client.post("/v1/context/scws", json={"id": "SCW1", "concept": "Task"}).status_code == 200
    assert client.post("/v1/context/scws", json={"id": "SCW1", "concept": "Other"}).status_code == 409
    assert client.post("/v1/scw/default-deploy", json={"task": "t", "scw_id": "SCW1"}).status_code == 409


# --- #8 host-window segments -------------------------------------------------


@pytest.mark.parametrize("segments", [["x"], [{"start": "x"}], [{"metadata": "ab"}],
                                      [{"start": 1e400}], [{}] * 1001])
def test_malformed_segments_are_input_errors(segments):
    with pytest.raises(ValueError):
        HostWindowObserver().observe(segments)
    client = TestClient(create_app(SuperSpaceSystem()))
    assert client.post("/v1/context/observe/host-window",
                       json={"segments": segments if segments != [{"start": 1e400}] else [{"start": "1e400"}]}
                       ).status_code == 400


# --- #10 REST drift/anchor ---------------------------------------------------


def _drift_client():
    system = build_demo()
    instance = system.scw_runtime.start("SCW2", "Maxey2")
    return TestClient(create_app(system)), instance.id


def test_rest_drift_on_an_unanchored_window_is_409():
    client, sid = _drift_client()
    assert client.post(f"/v1/context/scws/{sid}/drift", json={"vector": [1, 0]}).status_code == 409


@pytest.mark.parametrize("body", [{}, {"vector": [1, 0], "threshold": "x"},
                                  {"vector": [1, 0], "threshold": None}])
def test_rest_drift_bad_input_is_400(body):
    client, sid = _drift_client()
    assert client.post(f"/v1/context/scws/{sid}/anchor", json={"vector": [1, 0]}).status_code == 200
    assert client.post(f"/v1/context/scws/{sid}/drift", json=body).status_code == 400


def test_rest_anchor_refuses_a_non_numeric_baseline():
    client, sid = _drift_client()
    assert client.post(f"/v1/context/scws/{sid}/anchor", json={"vector": ["a", "b"]}).status_code == 400
    assert client.post(f"/v1/context/scws/{sid}/drift", json={"vector": [1, 0]}).status_code == 409


# --- #12 A2A -----------------------------------------------------------------


def test_an_a2a_caller_cannot_lower_its_own_admission_bar():
    client = TestClient(create_app(build_demo()))
    r = client.post("/v1/a2a/message", json={
        "sender": "external", "task": "zzzz unrelated", "skill": "zzzz unrelated",
        "context": {"minimum_score": -1}})
    assert r.status_code == 200
    assert r.json()["accepted"] is False


@pytest.mark.parametrize("body", [
    {"sender": "e", "task": 123},
    {"sender": "e", "task": "t", "context": [1]},
    {"sender": "e", "task": "t", "bogus": 1},
])
def test_malformed_a2a_bodies_are_400(body):
    client = TestClient(create_app(build_demo()))
    assert client.post("/v1/a2a/message", json=body).status_code == 400
