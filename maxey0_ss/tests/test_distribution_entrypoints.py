"""Every distribution target must tell users a command that actually serves.

`python -m maxey0_ss.mcp_public_server` and `python -m maxey0_ss.a2a_server`
were published as install commands and exited without serving (neither module
has an entry point), and the harness targets said `pip install
maxey0-superspace[...]`, which needs a PyPI release that does not exist.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

from fastapi.testclient import TestClient

from maxey0_ss.api.app import create_app
from maxey0_ss.distribution import registry

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"]


def _targets():
    return [v for v in vars(registry).values() if isinstance(v, registry.Target)] + list(
        getattr(registry, "HARNESSES", ()))


def test_server_targets_name_a_real_console_script():
    for target in (registry.MCP_HTTP, registry.A2A_AGENT):
        assert target.install in SCRIPTS, target.install


def test_no_target_installs_from_pypi():
    for target in _targets():
        if "pip install" in target.install:
            assert "git+" in target.install, target.install


def test_the_standard_agent_card_path_is_served():
    client = TestClient(create_app())
    for path in ("/.well-known/agent-card.json", "/.well-known/maxey0-agent.json"):
        assert client.get(path).status_code == 200, path
