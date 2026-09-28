"""The production smoke test's failure classifier.

The script itself only runs against a live URL; what is testable here is that
each kind of failure is attributed to the right layer, because a smoke test
that blames the wrong hop sends the operator to the wrong place.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from smoke_production import classify  # noqa: E402


def test_success_is_not_a_failure():
    assert classify(200, {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}) is None


def test_each_layer_is_named():
    cases = {
        "network": (None, "connection refused"),
        "routing": (530, "error code: 1033"),
        "auth": (401, {"error": {"code": -32001, "message": "Invalid bearer credentials"}}),
        "authz": (403, {"error": {"code": -32002, "message": "requires capability 'scw.admit'"}}),
        "protocol": (200, "<html>challenge</html>"),
        "application": (200, {"result": {"isError": True,
                                         "content": [{"text": "Unknown SCW specification"}]}}),
    }
    for layer, (status, body) in cases.items():
        found = classify(status, body)
        assert found is not None and found[0] == layer, (layer, found)


def test_origin_unreachable_errors_from_the_edge_are_routing():
    for code in (-32011, -32012):
        found = classify(502 if code == -32011 else 504, {"error": {"code": code, "message": "x"}})
        assert found[0] == "routing"
