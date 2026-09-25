"""The Cloudflare edge catalog is generated, and must not fall behind the core.

`workers/mcp-edge/src/generated/` is produced by `scripts/export_mcp_surface.py`
from `maxey0_ss.mcp_surface`. If someone adds a tool in Python and forgets to
re-export, the edge would advertise a stale catalog to every remote client.
These tests make that a failure rather than a silent divergence.
"""
import hashlib
import json
import pathlib

import pytest

from maxey0_ss.mcp_surface import (
    SERVER_NAME,
    SUPER_SPACE_URI,
    build_surface,
    super_space_artifact,
    super_space_html,
)

GENERATED = pathlib.Path(__file__).resolve().parents[2] / "workers" / "mcp-edge" / "src" / "generated"
SURFACE_JSON = GENERATED / "surface.json"
APP_HTML = GENERATED / "super-space.html"

pytestmark = pytest.mark.skipif(
    not SURFACE_JSON.exists(),
    reason="edge catalog not exported; run scripts/export_mcp_surface.py",
)


@pytest.fixture(scope="module")
def exported() -> dict:
    return json.loads(SURFACE_JSON.read_text(encoding="utf-8"))


def test_edge_advertises_exactly_the_python_tools(exported):
    assert [t["name"] for t in exported["tools"]] == [t.name for t in build_surface().tools]


def test_edge_tool_schemas_match_python(exported):
    py = {t.name: t.input_schema for t in build_surface().tools}
    for tool in exported["tools"]:
        assert tool["inputSchema"] == py[tool["name"]], tool["name"]


def test_edge_preserves_app_tool_linkage(exported):
    tool = next(t for t in exported["tools"] if t["name"] == "maxey0-ss.super_space")
    assert tool["_meta"]["ui"]["resourceUri"] == SUPER_SPACE_URI


def test_edge_advertises_exactly_the_python_resources(exported):
    assert [r["uri"] for r in exported["resources"]] == [r.uri for r in build_surface().resources]


def test_edge_identity_matches_the_core(exported):
    assert exported["serverName"] == SERVER_NAME
    assert exported["protocolVersion"] == "2026-07-28"


def test_edge_app_artifact_is_byte_identical_to_the_origin():
    """A remote client and a local client must receive the same App bytes.

    Exported with newline="" on purpose: Python's default newline translation
    rewrites LF to CRLF on Windows and silently changes the artifact identity.
    """
    edge_bytes = APP_HTML.read_bytes()
    assert hashlib.sha256(edge_bytes).hexdigest() == super_space_artifact()["sha256"]
    assert edge_bytes == super_space_html().encode("utf-8")


def test_edge_does_not_ship_a_stub(exported):
    assert exported["artifact"]["kind"] == "built"
