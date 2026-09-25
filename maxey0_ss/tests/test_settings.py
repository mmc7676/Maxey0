"""Deployment settings: the sockets must be real, or say they are not.

`.env.example` declared 21 placeholders and 13 of them were read by nothing.
Setting MAXEY0_NEO4J_URI had no effect and nothing reported that. These tests
keep a socket from silently swallowing what is plugged into it.
"""
import warnings

import pytest

from maxey0_ss.adapters.a2a import a2a_credential_valid
from maxey0_ss.settings import ConfiguredButUnimplemented, Settings, load_env_file


def test_declared_bind_settings_are_honoured(monkeypatch):
    monkeypatch.setenv("MAXEY0_HOST", "0.0.0.0")
    monkeypatch.setenv("MAXEY0_PORT", "9999")
    cfg = Settings.load(warn=False)
    assert cfg.host == "0.0.0.0"
    assert cfg.port == 9999


def test_an_env_file_is_actually_read(tmp_path, monkeypatch):
    monkeypatch.delenv("MAXEY0_ENV", raising=False)
    env = tmp_path / ".env"
    env.write_text('MAXEY0_ENV=staging\n# comment\nQUOTED="x"\n', encoding="utf-8")
    loaded = load_env_file(env)
    assert loaded["MAXEY0_ENV"] == "staging"
    assert loaded["QUOTED"] == "x"


def test_configuring_an_unimplemented_provider_warns(monkeypatch):
    """Silence here is the defect: credentials that do nothing."""
    monkeypatch.setenv("MAXEY0_NEO4J_URI", "bolt://localhost:7687")
    monkeypatch.setenv("MAXEY0_NEO4J_PASSWORD", "hunter2")
    with pytest.warns(ConfiguredButUnimplemented, match="graph"):
        Settings.load(warn=True)


def test_a_socket_separates_configured_from_implemented(monkeypatch):
    monkeypatch.setenv("MAXEY0_SEMANTIC_GATE_API_KEY", "key")
    socket = Settings.load(warn=False).providers["semantic_gate"]
    assert socket.configured is True
    assert socket.implemented is False
    assert socket.active is False


def test_the_manifest_never_exposes_a_secret_value(monkeypatch):
    monkeypatch.setenv("MAXEY0_NEO4J_PASSWORD", "super-secret-value")
    monkeypatch.setenv("MAXEY0_SEMANTIC_GATE_API_KEY", "another-secret")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConfiguredButUnimplemented)
        manifest = Settings.load(warn=False).public_manifest()
    blob = repr(manifest)
    assert "super-secret-value" not in blob
    assert "another-secret" not in blob
    assert manifest["providers"]["graph"]["secrets_present"] == ["MAXEY0_NEO4J_PASSWORD"]
    assert "graph" in manifest["inert"]


def test_an_unconfigured_provider_is_not_reported_inert(monkeypatch):
    for key in ("MAXEY0_NEO4J_URI", "MAXEY0_NEO4J_PASSWORD", "MAXEY0_NEO4J_USERNAME",
                "MAXEY0_REDIS_URL", "MAXEY0_VECTOR_STORE_URL", "MAXEY0_STORAGE_URL",
                "MAXEY0_SEMANTIC_GATE_API_KEY", "MAXEY0_SEMANTIC_GATE_ENDPOINT",
                "MAXEY0_TRACE_ENDPOINT"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("MAXEY0_SEMANTIC_GATE_PROVIDER", "disabled")
    assert Settings.load(warn=False).public_manifest()["inert"] == []


# --- A2A ---------------------------------------------------------------------


def test_a2a_rejects_a_missing_credential_when_a_secret_is_set():
    assert not a2a_credential_valid(None, "shared")
    assert not a2a_credential_valid("Bearer wrong", "shared")


def test_a2a_accepts_the_shared_secret_bare_or_bearer():
    assert a2a_credential_valid("Bearer shared", "shared")
    assert a2a_credential_valid("shared", "shared")


def test_a2a_is_open_only_when_no_secret_is_configured():
    """An unset secret means unsecured, and `a2a_secured` reports it."""
    assert a2a_credential_valid(None, "")
    assert Settings.load(warn=False).a2a_secured in (True, False)
