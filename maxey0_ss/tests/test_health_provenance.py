"""GET /health says what software answers, and nothing about where it runs."""
from __future__ import annotations

from fastapi.testclient import TestClient

from maxey0_ss import __version__
from maxey0_ss.api.app import create_app
from maxey0_ss.mcp_2026 import MCP_VERSION


def _health(monkeypatch, build=None):
    if build is None:
        monkeypatch.delenv("MAXEY0_BUILD_ID", raising=False)
    else:
        monkeypatch.setenv("MAXEY0_BUILD_ID", build)
    return TestClient(create_app()).get("/health").json()


def test_health_reports_version_and_protocol(monkeypatch):
    body = _health(monkeypatch)
    assert body == {"ok": True, "service": "maxey0-ss", "version": __version__,
                    "mcp_protocol": MCP_VERSION}


def test_health_reports_a_plain_build_id(monkeypatch):
    assert _health(monkeypatch, "8b105559dded")["build"] == "8b105559dded"


def test_health_never_echoes_anything_that_is_not_an_identifier(monkeypatch):
    for unsafe in ("/srv/builds/x", "http://10.0.0.5/x", "a b", "x" * 65):
        assert "build" not in _health(monkeypatch, unsafe), unsafe
