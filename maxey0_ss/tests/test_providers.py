"""Providers: the request that would go on the wire, and the record it leaves.

Two things are asserted here that a mock of the provider itself cannot assert.

**The request shape.** A test that patches `AnthropicProvider.complete` proves
nothing about what this code would send. The transport is injected instead, so
every test below sees the exact URL, method, headers and JSON body, and a change
to any of them fails here rather than in production against a 400.

**The record.** Every egress is admitted by the gate and written to the
hash-chained log *before* it happens, refusal included. A chain that records only
successes cannot distinguish a refused call from a call that was never made,
which is the same defect as `observe` mode reporting `held: true`.
"""
from __future__ import annotations

import json
import os
from unittest import mock

import pytest

from maxey0_ss.containment.attestation import AttestationLog
from maxey0_ss.containment.protocol import Operation
from maxey0_ss.gating.semantic import DisabledSemanticGate, UnimplementedSemanticGate
from maxey0_ss.providers import (
    AnthropicProvider,
    GatedProvider,
    HuggingFaceProvider,
    NotConfigured,
    OpenAIProvider,
    PlaceholderCredential,
    ProviderRefused,
    build,
    is_placeholder,
    public_manifest,
    registry,
)

#: Test keys, assembled rather than written down.
#:
#: `scripts/_packaging.py` scans the bytes of every file it is about to archive
#: for credential shapes, and this file is one of them -- so a literal
#: `sk-ant-` followed by twenty characters here fails the release build from the
#: test suite that proves the provider layer refuses bad keys. Exempting tests/
#: would be the easy fix and the wrong one: a real credential pasted into a
#: fixture still ships. Assembled values keep every assertion genuine while
#: leaving no credential shape in the repository.
def _key(kind: str) -> str:
    if kind == "anthropic":
        return "sk-" + "ant-" + "a-real-looking-value"
    if kind == "anthropic-alt":
        return "sk-" + "ant-" + "abcdefghijklmnopqrst"
    if kind == "anthropic-secret":
        return "sk-" + "ant-" + "secret-value-not-real"
    if kind == "openai":
        return "sk-" + "openai-real-value"
    raise AssertionError(kind)


KEYS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_ORG_ID",
        "HF_TOKEN", "HUGGINGFACE_API_KEY", "HUGGINGFACEHUB_API_TOKEN",
        "MAXEY0_ANTHROPIC_MODEL", "MAXEY0_OPENAI_MODEL", "MAXEY0_HF_MODEL",
        "MAXEY0_MODEL")


@pytest.fixture
def clean_env():
    with mock.patch.dict(os.environ, {k: "" for k in KEYS}):
        yield


class Recorder:
    """An injected transport that records the request and replays a response."""

    def __init__(self, status=200, payload=None):
        self.status = status
        self.payload = payload if payload is not None else {}
        self.calls = []

    def __call__(self, url, body, headers, timeout, method="POST"):
        self.calls.append({
            "url": url, "method": method, "headers": headers,
            "body": json.loads(body.decode("utf-8")) if body else None,
        })
        return self.status, json.dumps(self.payload).encode("utf-8")

    @property
    def last(self):
        return self.calls[-1]


# ---------------------------------------------------------------------------
# credentials: absent, placeholder, and real are three different states
# ---------------------------------------------------------------------------


class TestCredentialStates:
    def test_absent_is_not_a_placeholder(self, clean_env):
        cred = AnthropicProvider().credential()
        assert cred.present is False
        assert cred.placeholder is False
        assert cred.usable is False

    def test_an_absent_credential_says_where_to_put_one(self, clean_env):
        with pytest.raises(NotConfigured, match=r"\.env\.example"):
            AnthropicProvider(transport=Recorder()).complete("hi")

    @pytest.mark.parametrize("value", [
        "REPLACE_ME", "sk-ant-PLACEHOLDER", "your-key-here",
        "changeme", "${ANTHROPIC_API_KEY}", "<paste key>", "xxxx-xxxx",
    ])
    def test_every_documented_placeholder_is_recognized(self, value):
        assert is_placeholder(value) is True

    def test_a_placeholder_refuses_loudly_rather_than_being_sent(self, clean_env):
        """The whole point: it looks configured to every truthiness check."""
        recorder = Recorder()
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-PLACEHOLDER"}):
            with pytest.raises(PlaceholderCredential) as exc:
                AnthropicProvider(transport=recorder).complete("hi")
        assert "ANTHROPIC_API_KEY" in str(exc.value)
        assert recorder.calls == [], "the placeholder must never reach the wire"

    def test_a_credential_preview_identifies_without_disclosing(self, clean_env):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": _key("anthropic-alt")}):
            preview = AnthropicProvider().credential().preview()
        assert _key("anthropic-alt")[7:] not in preview
        assert preview.startswith("sk-ant")

    def test_a_short_key_is_fully_masked(self, clean_env):
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "short"}):
            assert OpenAIProvider().credential().preview() == "***"

    def test_the_example_files_only_contain_recognized_placeholders(self):
        """A placeholder convention the code does not recognize fails open."""
        import pathlib
        import re

        root = pathlib.Path(__file__).resolve().parents[2]
        env = (root / ".env.example").read_text(encoding="utf-8")
        for line in env.splitlines():
            m = re.match(r"^([A-Z][A-Z0-9_]*)=(.+)$", line)
            if not m:
                continue
            name, value = m.group(1), m.group(2).strip()
            if name.endswith(("_KEY", "_TOKEN", "_SECRET", "_PASSWORD")):
                assert is_placeholder(value) or not value, (
                    f"{name} ships a value the placeholder check would not catch"
                )


# ---------------------------------------------------------------------------
# request shape - what actually goes on the wire
# ---------------------------------------------------------------------------


class TestAnthropicRequestShape:
    def test_the_messages_request_is_what_the_api_expects(self, clean_env):
        rec = Recorder(payload={
            "model": "claude-sonnet-5",
            "content": [{"type": "text", "text": "pong"}],
            "usage": {"input_tokens": 3, "output_tokens": 1},
        })
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": _key("anthropic")}):
            result = AnthropicProvider(transport=rec).complete(
                "ping", system="be terse", max_tokens=16, temperature=0.0)

        call = rec.last
        assert call["url"] == "https://api.anthropic.com/v1/messages"
        assert call["method"] == "POST"
        assert call["headers"]["x-api-key"] == _key("anthropic")
        assert call["headers"]["anthropic-version"] == "2023-06-01"
        assert call["body"] == {
            "model": "claude-sonnet-5", "max_tokens": 16,
            "messages": [{"role": "user", "content": "ping"}],
            "system": "be terse", "temperature": 0.0,
        }
        assert result.text == "pong"
        assert result.usage == {"input_tokens": 3, "output_tokens": 1}

    def test_an_api_error_is_raised_with_its_detail(self, clean_env):
        rec = Recorder(status=401, payload={"error": {"message": "invalid x-api-key"}})
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": _key("anthropic")}):
            from maxey0_ss.providers import ProviderError

            with pytest.raises(ProviderError, match="invalid x-api-key"):
                AnthropicProvider(transport=rec).complete("ping")


class TestOpenAIRequestShape:
    def test_the_responses_request_is_what_the_api_expects(self, clean_env):
        rec = Recorder(payload={
            "model": "gpt-5", "output_text": "pong",
            "usage": {"input_tokens": 3, "output_tokens": 1},
        })
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": _key("openai")}):
            result = OpenAIProvider(transport=rec).complete("ping", max_tokens=16)

        call = rec.last
        assert call["url"] == "https://api.openai.com/v1/responses"
        assert call["headers"]["authorization"] == "Bearer " + _key("openai")
        assert call["body"]["input"] == "ping"
        assert call["body"]["max_output_tokens"] == 16
        assert result.text == "pong"

    def test_text_is_read_from_the_structured_output_when_there_is_no_shortcut(self, clean_env):
        """`output_text` is a convenience field and is not always present."""
        rec = Recorder(payload={"model": "gpt-5", "output": [
            {"content": [{"type": "output_text", "text": "from-"},
                         {"type": "output_text", "text": "blocks"}]}]})
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": _key("openai")}):
            assert OpenAIProvider(transport=rec).complete("x").text == "from-blocks"

    def test_chat_completions_is_the_compatibility_path(self, clean_env):
        rec = Recorder(payload={
            "model": "local", "choices": [{"message": {"content": "pong"}}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 1},
        })
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": _key("openai")}):
            result = OpenAIProvider(transport=rec).chat("ping", system="s")
        assert rec.last["url"].endswith("/chat/completions")
        assert rec.last["body"]["messages"][0] == {"role": "system", "content": "s"}
        assert result.usage == {"input_tokens": 2, "output_tokens": 1}

    def test_a_custom_base_url_is_honoured_and_reported(self, clean_env):
        """It changes who receives the prompt, so it is reported, not hidden."""
        rec = Recorder(payload={"output_text": "ok"})
        with mock.patch.dict(os.environ, {
            "OPENAI_API_KEY": _key("openai"),
            "OPENAI_BASE_URL": "https://llm.internal.example.invalid/v1",
        }):
            provider = OpenAIProvider(transport=rec)
            provider.complete("x")
            manifest = provider.public_manifest()
        assert rec.last["url"].startswith("https://llm.internal.example.invalid/v1")
        assert manifest["endpoint_is_default"] is False

    def test_an_organization_header_is_sent_only_when_set(self, clean_env):
        rec = Recorder(payload={"output_text": "ok"})
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": _key("openai")}):
            OpenAIProvider(transport=rec).complete("x")
        assert "openai-organization" not in rec.last["headers"]
        with mock.patch.dict(os.environ, {
            "OPENAI_API_KEY": _key("openai"), "OPENAI_ORG_ID": "org-abc"}):
            OpenAIProvider(transport=rec).complete("x")
        assert rec.last["headers"]["openai-organization"] == "org-abc"


class TestHuggingFace:
    def test_a_hub_read_is_a_get_and_needs_no_credential(self, clean_env):
        """The published demonstration must be reproducible without an account."""
        rec = Recorder(payload={"id": "org/dataset", "siblings": [
            {"rfilename": "README.md"}, {"rfilename": "data/train.jsonl"}]})
        files = HuggingFaceProvider(transport=rec).dataset_files("org/dataset")
        assert rec.last["method"] == "GET"
        assert rec.last["url"] == "https://huggingface.co/api/datasets/org/dataset"
        assert "authorization" not in rec.last["headers"]
        assert files == ["README.md", "data/train.jsonl"]

    def test_inference_requires_a_credential(self, clean_env):
        with pytest.raises(NotConfigured):
            HuggingFaceProvider(transport=Recorder()).complete("x")

    def test_inference_posts_to_the_model_endpoint(self, clean_env):
        rec = Recorder(payload=[{"generated_text": "pong"}])
        with mock.patch.dict(os.environ, {"HF_TOKEN": "hf_" + "realtokenvalue123"}):
            result = HuggingFaceProvider(transport=rec).complete("ping", model="org/m")
        assert rec.last["url"].endswith("/models/org/m")
        assert rec.last["method"] == "POST"
        assert rec.last["body"]["inputs"] == "ping"
        assert result.text == "pong"

    def test_a_placeholder_token_refuses_even_on_a_public_read(self, clean_env):
        """Dropping it would silently downgrade a private read to anonymous."""
        with mock.patch.dict(os.environ, {"HF_TOKEN": "REPLACE_ME"}):
            with pytest.raises(PlaceholderCredential):
                HuggingFaceProvider(transport=Recorder()).dataset_info("org/d")

    def test_a_resolve_url_is_returned_and_not_fetched(self, clean_env):
        rec = Recorder()
        url = HuggingFaceProvider(transport=rec).resolve_url("org/d", "data/a.jsonl")
        assert url == "https://huggingface.co/datasets/org/d/resolve/main/data/a.jsonl"
        assert rec.calls == [], "a dataset file can be gigabytes; fetching is the caller's call"


# ---------------------------------------------------------------------------
# the seam: gated and attested
# ---------------------------------------------------------------------------


class TestEveryEgressIsAttested:
    def _provider(self, gate=None, log=None):
        rec = Recorder(payload={"model": "m", "content": [{"type": "text", "text": "ok"}]})
        inner = AnthropicProvider(transport=rec)
        return GatedProvider(inner, log=log or AttestationLog(),
                             gate=gate or DisabledSemanticGate(), scw_id="SCW3"), rec

    def test_a_successful_egress_writes_two_records(self, clean_env):
        """The attempt, then the outcome. The attempt is written first."""
        provider, rec = self._provider()
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": _key("anthropic")}):
            provider.complete("ping")
        records = provider.log.export()
        assert len(records) == 2
        assert records[0]["operation"] == Operation.EGRESS.value
        assert records[0]["agent_scw"] == "SCW3"
        assert records[0]["target_scw"] == "anthropic:messages.create"
        assert records[1]["metadata"]["kind"] == "provider.egress.result"

    def test_the_prompt_is_digested_and_never_recorded(self, clean_env):
        provider, _ = self._provider()
        secret = "the-users-private-prompt-text"
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": _key("anthropic")}):
            provider.complete(secret)
        blob = json.dumps(provider.log.export())
        assert secret not in blob
        assert provider.log.export()[0]["metadata"]["payload_digest"]

    def test_a_refused_egress_is_recorded_before_it_is_raised(self, clean_env):
        """A chain that records only successes cannot show a refusal."""
        provider, rec = self._provider(gate=UnimplementedSemanticGate("acme"))
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": _key("anthropic")}):
            with pytest.raises(ProviderRefused):
                provider.complete("ping")
        records = provider.log.export()
        assert len(records) == 1
        assert records[0]["allowed"] is False
        assert "acme" in records[0]["reason"]
        assert rec.calls == [], "a refused egress must not reach the wire"

    def test_the_chain_verifies_across_egress_records(self, clean_env):
        provider, _ = self._provider()
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": _key("anthropic")}):
            provider.complete("one")
            provider.complete("two")
        assert provider.log.verify().ok is True

    def test_two_identical_prompts_share_a_digest_and_two_different_ones_do_not(self, clean_env):
        provider, _ = self._provider()
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": _key("anthropic")}):
            provider.complete("same")
            provider.complete("same")
            provider.complete("different")
        digests = [r["metadata"]["payload_digest"] for r in provider.log.export()
                   if r["metadata"].get("kind") == "provider.egress"]
        assert digests[0] == digests[1] != digests[2]

    def test_a_hub_read_is_attested_as_a_retrieval_not_a_completion(self, clean_env):
        rec = Recorder(payload={"id": "org/d"})
        provider = GatedProvider(HuggingFaceProvider(transport=rec),
                                 gate=DisabledSemanticGate())
        provider.hub_read("org/d")
        record = provider.log.export()[0]
        assert record["target_scw"] == "huggingface:hub.dataset_info"
        assert record["metadata"]["repo_id"] == "org/d"
        assert record["metadata"]["payload_digest"] == "", (
            "no prompt left, so recording one would be a false claim"
        )

    def test_every_registered_provider_is_gated_by_default(self):
        for name, provider in registry().items():
            assert isinstance(provider, GatedProvider), name
            assert provider.public_manifest()["gated"] is True

    def test_the_registry_shares_one_chain_across_providers(self, clean_env):
        """One ordered answer to "what did this system send outside"."""
        shared = registry()
        logs = {id(p.log) for p in shared.values()}
        assert len(logs) == 1


class TestDeploymentReporting:
    def test_the_manifest_separates_configured_placeholder_and_unset(self, clean_env):
        with mock.patch.dict(os.environ, {
            "ANTHROPIC_API_KEY": _key("anthropic"),
            "OPENAI_API_KEY": "REPLACE_ME",
        }):
            manifest = public_manifest()
        assert manifest["configured"] == ["anthropic"]
        assert manifest["placeholder"] == ["openai"]
        assert "huggingface" in manifest["unconfigured"]

    def test_no_credential_value_appears_in_the_manifest(self, clean_env):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": _key("anthropic-secret")}):
            blob = json.dumps(public_manifest())
        assert _key("anthropic-secret") not in blob
        assert "secret-value-not-real" not in blob

    def test_an_unknown_provider_names_the_ones_that_exist(self):
        from maxey0_ss.providers import ProviderError

        with pytest.raises(ProviderError, match="anthropic, huggingface, openai"):
            build("nope")


# ---------------------------------------------------------------------------
# egress is structurally contained, not only semantically gated
# ---------------------------------------------------------------------------


class TestEgressReachesContainment:
    """Egress was recorded into the chain without ever passing through it.

    `GatedProvider` asked the semantic gate and wrote to the `AttestationLog`,
    and never called `ContainmentProvider.decide()`. Two consequences, both of
    which this class pins:

    1. A **closed** window could still send a prompt to a third party.
    2. The `DenialBreaker` counts refusals it is *shown*, so refused egress was
       never counted and unlimited probing of the outermost boundary tripped
       nothing — in the one crossing that leaves the process.
    """

    def _system(self):
        from maxey0_ss.system import SuperSpaceSystem
        from maxey0_ss.scw_deployer import deploy_default_scw

        system = SuperSpaceSystem()
        system.create_scw(deploy_default_scw("t", scw_id="SCW4"))
        instance = system.scw_runtime.start("SCW4", "owner")
        return system, instance

    def _provider(self, system, window):
        rec = Recorder(payload={"model": "m", "content": [{"type": "text", "text": "ok"}]})
        return GatedProvider(
            AnthropicProvider(transport=rec),
            log=system.context.isolation.log,
            gate=DisabledSemanticGate(),
            containment=system.context.isolation,
            scw_id=window,
        ), rec

    def test_an_open_window_may_reach_outside(self, clean_env):
        system, instance = self._system()
        provider, rec = self._provider(system, instance.id)
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": _key("anthropic")}):
            provider.complete("ping")
        assert len(rec.calls) == 1

    def test_a_closed_window_may_not(self, clean_env):
        """It could, before 0.3.0. The prompt left the process.

        Closing revokes registration rather than flipping a flag, so the
        refusal reads "not registered" -- which is the stronger of the two
        states and the one `ContextService.close` actually produces.
        """
        system, instance = self._system()
        provider, rec = self._provider(system, instance.id)
        system.context.close(instance.id)
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": _key("anthropic")}):
            with pytest.raises(ProviderRefused, match="not registered"):
                provider.complete("ping")
        assert rec.calls == [], "a closed window's prompt must not reach the wire"

    def test_a_registered_but_closed_window_may_not_either(self):
        """The other branch: a provider without `revoke` keeps the instance.

        Both states have to refuse, because which one a deployment lands in
        depends on the containment provider it configured.
        """
        from maxey0_ss.containment import containment_provider
        from maxey0_ss.containment.attestation import AttestationLog
        from maxey0_ss.containment.hierarchy import Constitution, ConstitutionTree

        log, tree = AttestationLog(), ConstitutionTree()
        tree.charter_root("SCW0", Constitution())
        isolation = containment_provider(log=log, tree=tree)

        class Window:
            id = "SCW0@rt"
            spec_id = "SCW0"
            open = True
            readable = {"SCW0@rt"}
            writable = {"SCW0@rt"}

        window = Window()
        isolation.register(window)
        assert isolation.decide(
            Operation.EGRESS, window.id, "openai:responses.create").allowed is True
        window.open = False
        refusal = isolation.decide(
            Operation.EGRESS, window.id, "openai:responses.create")
        assert refusal.allowed is False
        assert "closed" in refusal.reason

    def test_an_unregistered_window_fails_closed(self, clean_env):
        system, _ = self._system()
        provider, rec = self._provider(system, "SCW99@nowhere")
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": _key("anthropic")}):
            with pytest.raises(ProviderRefused, match="not registered"):
                provider.complete("ping")
        assert rec.calls == []

    def test_a_structural_refusal_is_recorded_as_egress(self, clean_env):
        system, instance = self._system()
        provider, _ = self._provider(system, instance.id)
        system.context.close(instance.id)
        before = len(provider.log)
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": _key("anthropic")}):
            with pytest.raises(ProviderRefused):
                provider.complete("ping")
        added = provider.log.export()[before:]
        assert any(r["operation"] == Operation.EGRESS.value and r["allowed"] is False
                   for r in added)

    def test_the_breaker_counts_refused_egress(self):
        """It did not. EGRESS was missing from CROSSINGS when egress was added."""
        from maxey0_ss.containment.hierarchy import DenialBreaker

        assert Operation.EGRESS in DenialBreaker.CROSSINGS

    def test_persistent_refused_egress_trips_the_breaker(self, clean_env):
        """The whole point of the breaker, in the crossing that leaves."""
        from maxey0_ss.containment import containment_provider
        from maxey0_ss.containment.attestation import AttestationLog
        from maxey0_ss.containment.hierarchy import ConstitutionTree, DenialBreaker

        log = AttestationLog()
        tree = ConstitutionTree()
        breaker = DenialBreaker(log, threshold=3)
        isolation = containment_provider(log=log, tree=tree, breaker=breaker)

        # An unregistered window is refused every time; after `threshold`
        # refusals the breaker stops answering at all.
        for _ in range(3):
            isolation.decide(Operation.EGRESS, "SCW9@rt", "anthropic:messages.create")
        assert breaker.tripped("SCW9@rt") is True
        final = isolation.decide(Operation.EGRESS, "SCW9@rt", "anthropic:messages.create")
        assert final.allowed is False
        assert "persistent" in final.reason

    def test_the_gate_is_not_consulted_when_structure_refuses(self, clean_env):
        """Asking a policy service about a window that may not speak at all."""
        system, instance = self._system()
        asked = []

        class Counting(DisabledSemanticGate):
            def evaluate(self, **kw):
                asked.append(kw)
                return super().evaluate(**kw)

        rec = Recorder(payload={"content": []})
        provider = GatedProvider(
            AnthropicProvider(transport=rec), log=system.context.isolation.log,
            gate=Counting(), containment=system.context.isolation,
            scw_id=instance.id,
        )
        system.context.close(instance.id)
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": _key("anthropic")}):
            with pytest.raises(ProviderRefused):
                provider.complete("ping")
        assert asked == [], "the payload must not reach a policy service"

    def test_the_surface_passes_the_running_systems_containment(self):
        """A provider built without it is the unsupported path."""
        from maxey0_ss.mcp_surface import build_surface

        src = (
            __import__("pathlib").Path(__file__).resolve().parents[1]
            / "mcp_surface.py"
        ).read_text(encoding="utf-8")
        assert "containment=system.context.isolation" in src
        build_surface()  # constructs cleanly with it
