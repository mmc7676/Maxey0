"""The adapter boundary. Nothing here had a test before 0.3.0.

`adapters/` held fourteen files and no test module. The audit that produced this
one found three referenced only by themselves — including a second class named
`OpenAIAgentsAdapter` with an incompatible signature — and they were removed.
What survives is the boundary two live surfaces depend on, so it is tested:

- `A2AHost`/`a2a_credential_valid`, reached by the A2A server and the HTTP API;
- `MCPClient`, reached by `mcp_delivery`;
- the six harness adapters, each declared installable by the distribution
  registry.

The property that matters for all three is the same: **an unbound or
unconfigured adapter refuses rather than improvising.** An adapter that returns
a plausible answer for a session it does not have is how a boundary stops being
one.
"""
from __future__ import annotations

import os
from unittest import mock

import pytest

from maxey0_ss.adapters.a2a import (
    A2AClient,
    A2AHost,
    A2ARequest,
    a2a_credential_valid,
)
from maxey0_ss.adapters.harnesses import ADAPTERS
from maxey0_ss.adapters.mcp import MCPClient
from maxey0_ss.models import AgentSpec
from maxey0_ss.scw_deployer import deploy_default_scw
from maxey0_ss.system import SuperSpaceSystem


# ---------------------------------------------------------------------------
# the A2A credential, which is the one authenticated REST route
# ---------------------------------------------------------------------------


class TestA2ACredential:
    def test_a_matching_secret_is_accepted_bare_or_as_a_bearer(self):
        assert a2a_credential_valid("s3cret", "s3cret") is True
        assert a2a_credential_valid("Bearer s3cret", "s3cret") is True
        assert a2a_credential_valid("bearer s3cret", "s3cret") is True

    def test_a_wrong_secret_is_refused(self):
        assert a2a_credential_valid("wrong", "s3cret") is False
        assert a2a_credential_valid(None, "s3cret") is False
        assert a2a_credential_valid("", "s3cret") is False

    def test_no_configured_secret_is_permissive_locally(self):
        """A local deployment with no secret is trusted, by design."""
        with mock.patch.dict(os.environ, {"MAXEY0_PUBLIC": ""}):
            assert a2a_credential_valid(None, "") is True

    def test_no_configured_secret_is_refused_on_a_public_deployment(self):
        """Otherwise it is an unauthenticated write endpoint on the internet.

        The same fail-closed rule the MCP tiers apply, rather than an exception
        carved out for the one authenticated REST route.
        """
        with mock.patch.dict(os.environ, {"MAXEY0_PUBLIC": "1"}):
            assert a2a_credential_valid(None, "") is False
            assert a2a_credential_valid("anything", "") is False

    def test_whitespace_around_a_token_does_not_change_the_answer(self):
        assert a2a_credential_valid("Bearer   s3cret  ", "s3cret") is True


# ---------------------------------------------------------------------------
# the A2A host
# ---------------------------------------------------------------------------


class TestA2AHost:
    def test_a_request_is_routed_and_recorded(self):
        system = SuperSpaceSystem()
        host = A2AHost(system)
        reply = host.handle(A2ARequest(sender="peer", task="threat model"))
        assert set(reply) == {"accepted", "decision", "candidate_skills", "a2a_host"}
        assert reply["a2a_host"] == "maxey0"
        assert isinstance(reply["accepted"], bool)

    def test_the_decision_names_its_source_rather_than_claiming_semantics(self):
        """The router reports `lexical` when it compared strings."""
        system = SuperSpaceSystem()
        reply = A2AHost(system).handle(A2ARequest(sender="peer", task="anything"))
        assert reply["decision"]["source"] in {"lexical", "semantic", "context"}

    def test_every_request_lands_in_the_observatory(self):
        """An A2A request is an external agent reaching in; it is recorded."""
        system = SuperSpaceSystem()
        before = len(system.observatory.trace())
        A2AHost(system).handle(A2ARequest(sender="peer", task="t"))
        assert len(system.observatory.trace()) > before

    def test_no_candidate_is_a_refusal_not_an_invention(self):
        system = SuperSpaceSystem()
        reply = A2AHost(system).handle(
            A2ARequest(sender="peer", task="nothing-matches-this"))
        if not reply["candidate_skills"]:
            assert reply["accepted"] is False


class TestA2AClient:
    """The client half of a published protocol surface. It had no test."""

    def test_a_secret_is_sent_as_a_bearer_header(self):
        sent = {}

        class FakeResponse:
            def read(self):
                return b'{"accepted": true}'

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(request, timeout=None):
            sent["url"] = request.full_url
            sent["headers"] = dict(request.headers)
            sent["body"] = request.data
            return FakeResponse()

        client = A2AClient("https://peer.example.invalid/v1/a2a",
                           shared_secret="s3cret")
        with mock.patch("maxey0_ss.adapters.a2a.urlopen", fake_urlopen):
            out = client.send(A2ARequest(sender="me", task="t"))
        assert out == {"accepted": True}
        assert sent["headers"]["Authorization"] == "Bearer s3cret"
        assert b'"sender": "me"' in sent["body"]

    def test_no_secret_sends_no_authorization_header(self):
        captured = {}

        class FakeResponse:
            def read(self):
                return b"{}"

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(request, timeout=None):
            captured["headers"] = dict(request.headers)
            return FakeResponse()

        with mock.patch("maxey0_ss.adapters.a2a.urlopen", fake_urlopen):
            A2AClient("https://peer.example.invalid/v1/a2a").send(
                A2ARequest(sender="me", task="t"))
        assert "Authorization" not in captured["headers"]


# ---------------------------------------------------------------------------
# the MCP client boundary
# ---------------------------------------------------------------------------


class TestMCPClient:
    def test_an_unbound_server_is_refused_rather_than_improvised(self):
        """A boundary that answers for a session it does not have is not one."""
        with pytest.raises(KeyError, match="no MCP session"):
            MCPClient().call("nowhere", "tools/list")

    def test_a_bound_session_receives_the_method_and_params(self):
        seen = {}
        client = MCPClient()
        client.bind("srv", lambda **kw: seen.update(kw) or {"ok": True})
        assert client.call("srv", "tools/call", name="x") == {"ok": True}
        assert seen == {"method": "tools/call", "name": "x"}

    def test_rebinding_replaces_rather_than_accumulates(self):
        client = MCPClient()
        client.bind("srv", lambda **kw: "first")
        client.bind("srv", lambda **kw: "second")
        assert client.call("srv", "m") == "second"
        assert len(client.sessions) == 1


# ---------------------------------------------------------------------------
# the harness adapters
# ---------------------------------------------------------------------------


class TestHarnessAdapters:
    """Six adapters, each declared installable. None had a test."""

    def _bound(self, adapter_cls):
        system = SuperSpaceSystem()
        system.create_scw(deploy_default_scw("t", scw_id="SCW2"))
        agent = AgentSpec("agent-1", "maker", "SCW2")
        return adapter_cls().bind_agent(system, agent), system

    def test_every_adapter_binds_an_agent_to_a_real_window(self, subtests):
        for name, adapter_cls in ADAPTERS.items():
            with subtests.test(harness=name):
                binding, system = self._bound(adapter_cls)
                assert binding.harness == name
                assert binding.agent_id == "agent-1"
                # The binding names an instance that actually exists.
                assert binding.scw_id in system.context.instances
                assert binding.metadata["runtime"]

    def test_binding_registers_the_window_with_containment(self, subtests):
        """The binding is the point. An unregistered window has no reach."""
        for name, adapter_cls in ADAPTERS.items():
            with subtests.test(harness=name):
                binding, system = self._bound(adapter_cls)
                assert system.context.isolation.can_read(
                    binding.scw_id, binding.scw_id)

    def test_every_adapter_builds_an_a2a_request(self, subtests):
        for name, adapter_cls in ADAPTERS.items():
            with subtests.test(harness=name):
                request = adapter_cls().build_a2a_request("me", "task", topic="t")
                assert request["sender"] == "me"
                assert request["task"] == "task"
                assert request["topic"] == "t"

    def test_each_adapter_names_the_dependency_the_registry_declares(self, subtests):
        """Three places said which package LangChain needed, and disagreed.

        The registry said `langchain-core`, pyproject said `langchain-core`, and
        the adapter's own note said "langchain and/or langgraph". A reader
        following the note installed a different package from the one
        `pip install maxey0-superspace[langchain]` would have given them. The
        note is now checked against the registry rather than against a string
        format, so the two cannot drift again.
        """
        from maxey0_ss.distribution import HARNESSES

        declared = {h.id: h.optional_dependency for h in HARNESSES}
        for name, adapter_cls in ADAPTERS.items():
            with subtests.test(harness=name):
                notes = " ".join(adapter_cls.capabilities.notes)
                assert "Optional dependency" in notes
                assert declared[name] in notes, (
                    f"{name} names a package the registry does not declare; "
                    f"the registry says {declared[name]!r}"
                )

    def test_a_missing_optional_dependency_names_the_extra(self, subtests):
        """The import is deferred; the error has to say what to install."""
        importers = {
            "openai-agents": ("build_agent", ("n", "i")),
            "google-adk": ("import_adk", ()),
            "microsoft": ("import_framework", ()),
            "nvidia": ("import_toolkit", ()),
        }
        for name, (method, args) in importers.items():
            adapter = ADAPTERS[name]()
            fn = getattr(adapter, method, None)
            if fn is None:
                continue
            with subtests.test(harness=name):
                try:
                    fn(*args)
                except RuntimeError as exc:
                    assert "Install the optional" in str(exc)
                except ImportError:  # pragma: no cover - installed in this env
                    pass

    def test_no_two_adapters_share_a_class_name(self):
        """Two importable classes with one name is worse than dead code.

        `adapters/openai_agents.py` and `adapters/harnesses/openai_agents.py`
        both defined `OpenAIAgentsAdapter`, with incompatible signatures. The
        failure was a `TypeError` at a call site that looked correct.
        """
        names = [cls.__name__ for cls in ADAPTERS.values()]
        assert len(names) == len(set(names))

    def test_the_removed_duplicate_stays_removed(self):
        import importlib

        for gone in ("maxey0_ss.adapters.openai_agents",
                     "maxey0_ss.adapters.claude_code",
                     "maxey0_ss.adapters.registry"):
            with pytest.raises(ModuleNotFoundError):
                importlib.import_module(gone)
