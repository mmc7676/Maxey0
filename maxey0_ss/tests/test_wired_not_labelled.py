"""One test per mechanism that existed and was connected to nothing.

This codebase's recurring defect has a shape: something is built, documented,
sometimes tested in isolation, and then wired into no call path — a field, a
flag, a config key or a list of rules that nothing consults. It is hard to see
because everything about it looks finished, and the tests that cover it pass.

Its corollary is worse: a metric that reads as success because the failure
produced no error. `cache.status` published a live-looking metrics block that
was *structurally incapable* of being non-zero, because nothing ever wrote to
the cache it described.

So these tests do not check that the mechanisms exist. They check that the
mechanisms are *reached* — that a reader runs, that a number moves, that a
decision comes from the thing named in the decision.
"""
from __future__ import annotations

import json
import os
from unittest import mock

import pytest

from maxey0_ss.auth.config import AuthConfig
from maxey0_ss.cache import CacheConfig, SemanticPlane
from maxey0_ss.execution.router import ExecutionRouter
from maxey0_ss.gating.semantic import (
    DisabledSemanticGate,
    UnimplementedSemanticGate,
    select_semantic_gate,
)
from maxey0_ss.models import SCWSpec, SkillRecord
from maxey0_ss import mcp_surface
from maxey0_ss.mcp_surface import (
    MAX_ATTESTATION_LIMIT,
    _clamp_limit,
    build_surface,
)


def tool(surface, name):
    for t in surface.tools:
        if t.name == name:
            return t
    raise AssertionError(f"no such tool: {name}")


# ---------------------------------------------------------------------------
# 1 - the cache had no write path
# ---------------------------------------------------------------------------


class TestCacheIsWired:
    def test_metrics_move_when_a_cacheable_tool_is_called(self):
        """Before 0.2.0 every one of these was pinned at zero forever."""
        surface = build_surface()
        health = tool(surface, "maxey0-ss.health")

        assert len(surface.app_cache) == 0
        first = health.handler({})
        assert surface.app_cache.metrics.writes == 1
        assert surface.app_cache.metrics.misses == 1
        assert len(surface.app_cache) == 1

        second = health.handler({})
        assert second == first
        assert surface.app_cache.metrics.hits == 1

    def test_cache_status_reports_what_actually_happened(self):
        surface = build_surface()
        tool(surface, "maxey0-ss.distribution").handler({})
        tool(surface, "maxey0-ss.distribution").handler({})
        status = tool(surface, "maxey0-ss.cache.status").handler({})
        metrics = status["application_cache"]["metrics"]
        assert metrics["hits"] == 1
        assert metrics["writes"] == 1
        assert metrics["hit_rate"] > 0

    def test_never_cache_tools_get_no_wrapper(self):
        """`scw.describe` reads live state; a cached answer would be a bug."""
        surface = build_surface()
        tool(surface, "maxey0-ss.scw.describe").handler({})
        tool(surface, "maxey0-ss.scw.describe").handler({})
        assert len(surface.app_cache) == 0
        assert surface.app_cache.metrics.writes == 0

    def test_a_bypassed_cache_records_bypasses_rather_than_silently_working(self):
        with mock.patch.dict(os.environ, {"MAXEY0_CACHE_BYPASS": "1"}):
            surface = build_surface()
        tool(surface, "maxey0-ss.health").handler({})
        assert surface.app_cache.metrics.bypasses > 0
        assert len(surface.app_cache) == 0

    def test_cache_status_policy_is_derived_not_written_down(self):
        """It used to return the literal 300000. Change the config, change the report."""
        with mock.patch.dict(
            os.environ, {"MAXEY0_CACHE_TTL_MS_PROTOCOL": "12345"}
        ):
            surface = build_surface()
        policy = tool(surface, "maxey0-ss.cache.status").handler({})["policy"]
        assert policy["default_ttl_ms"] == 12345
        assert policy["ttl_ms_by_plane"][SemanticPlane.PROTOCOL.value] == 12345

    def test_closing_an_scw_can_actually_drop_entries(self):
        """`invalidate_scw` always returned 0, because nothing was ever stored."""
        surface = build_surface()
        cache = surface.app_cache
        from maxey0_ss.cache import Namespace

        view = cache.view(Namespace(SemanticPlane.CONTEXT, "SCW7"))
        view.put("anything", value={"x": 1})
        assert len(cache) == 1
        assert cache.invalidate_scw("SCW7") == 1
        assert cache.metrics.invalidations == 1


# ---------------------------------------------------------------------------
# 2 - the four declared fields with no reader
# ---------------------------------------------------------------------------


class TestModelFieldsHaveReaders:
    def test_isolation_and_region_kinds_are_gone(self):
        spec = SCWSpec("SCW1", None, "Concept", [])
        assert not hasattr(spec, "isolation")
        assert not hasattr(spec, "region_kinds")

    def test_the_region_vocabulary_is_not_duplicated(self):
        import maxey0_ss.models as models

        assert not hasattr(models, "RegionKind"), (
            "RegionKind duplicated scw_runtime.model.REGION_TYPES, which is the "
            "one the Context plane runtime actually builds regions with"
        )

    def test_scw_describe_no_longer_echoes_a_field_nothing_reads(self):
        surface = build_surface()
        tool(surface, "maxey0-ss.scw.create").handler(
            {"scw_id": "SCW5", "task": "t"}
        )
        described = tool(surface, "maxey0-ss.scw.describe").handler({})
        spec = described["specifications"]["SCW5"]
        assert "isolation" not in spec
        assert "drift_threshold" in spec

    def test_drift_threshold_is_the_default_the_drift_tool_uses(self):
        """The field was the declared input to an engine with no caller."""
        surface = build_surface()
        tool(surface, "maxey0-ss.scw.create").handler(
            {"scw_id": "SCW6", "task": "t"}
        )
        drift = tool(surface, "maxey0-ss.scw.drift")
        drift.handler({"scw_id": "SCW6", "vector": [1.0, 0.0], "anchor": True})
        record = drift.handler({"scw_id": "SCW6", "vector": [0.0, 1.0]})
        assert record["threshold_source"] == "spec"
        assert record["threshold"] == 0.15
        assert record["drifted"] is True
        assert record["distance"] == pytest.approx(1.0)

    def test_an_unanchored_window_is_refused_not_answered(self):
        surface = build_surface()
        tool(surface, "maxey0-ss.scw.create").handler(
            {"scw_id": "SCW8", "task": "t"}
        )
        out = tool(surface, "maxey0-ss.scw.drift").handler(
            {"scw_id": "SCW8", "vector": [1.0, 0.0]}
        )
        assert out["anchored"] is False
        assert out["drifted"] is None

    def test_an_explicit_threshold_says_it_overrode_the_spec(self):
        surface = build_surface()
        tool(surface, "maxey0-ss.scw.create").handler(
            {"scw_id": "SCW9", "task": "t"}
        )
        drift = tool(surface, "maxey0-ss.scw.drift")
        drift.handler({"scw_id": "SCW9", "vector": [1.0, 0.0], "anchor": True})
        record = drift.handler(
            {"scw_id": "SCW9", "vector": [0.0, 1.0], "threshold": 0.9}
        )
        assert record["threshold_source"] == "argument"
        assert record["threshold"] == 0.9

    def test_skill_embedding_reaches_the_router(self):
        """It was written by the API and read by nothing, one import away."""
        near = SkillRecord("a", "Alpha", "c", "t", "gate.a", [], [1.0, 0.0])
        far = SkillRecord("b", "Beta", "c", "t", "gate.b", [], [0.0, 1.0])
        decision = ExecutionRouter().choose_skill(
            {"embedding": [1.0, 0.0]}, [near, far], {"minimum_score": 0.0}
        )
        assert decision.gate_id == "gate.a"
        assert decision.source == "semantic"

    def test_the_router_does_not_claim_semantic_when_it_matched_a_keyword(self):
        """It returned reason "semantic match" for a pure string comparison."""
        plain = SkillRecord("a", "Threat Modeling", "c", "t", "gate.a", [])
        decision = ExecutionRouter().choose_skill(
            {"skill": "threat", "concept": "c", "topic": "t"}, [plain], {}
        )
        assert decision.allowed
        assert decision.source == "lexical"
        assert "semantic" not in decision.reason.split("no semantic")[0].lower()

    def test_a_mismatched_embedding_dimension_falls_back_rather_than_raising(self):
        odd = SkillRecord("a", "Alpha", "c", "t", "gate.a", [], [1.0, 0.0, 0.0])
        decision = ExecutionRouter().choose_skill(
            {"embedding": [1.0, 0.0], "concept": "c", "topic": "t"}, [odd], {}
        )
        assert decision.source == "lexical"


# ---------------------------------------------------------------------------
# 3 - the semantic gate
# ---------------------------------------------------------------------------


class TestGateInspectConsultsTheGate:
    def test_gate_inspect_reports_the_provider_it_actually_used(self):
        surface = build_surface(semantic_gate=DisabledSemanticGate())
        out = tool(surface, "maxey0-ss.gate.inspect").handler(
            {"scw_address": "scw://topic/concept/skill/region/SCW0"}
        )
        assert out["allowed"] is True
        assert out["semantic_provider"] == "disabled"
        # GateDecision's fields had no producer anything read.
        for field in ("gate_id", "reason", "score", "semantic_distance", "source"):
            assert field in out

    def test_a_configured_provider_is_reported_not_overwritten_with_disabled(self):
        """A deployment naming a provider was told "disabled" regardless."""
        surface = build_surface(semantic_gate=UnimplementedSemanticGate("acme"))
        out = tool(surface, "maxey0-ss.gate.inspect").handler(
            {"scw_address": "scw://topic/concept/skill/region/SCW0"}
        )
        assert out["semantic_provider"] == "acme"
        assert out["allowed"] is False

    def test_an_unimplemented_provider_fails_closed(self):
        """The one direction a gate must never fail."""
        gate = select_semantic_gate("acme-policy-service")
        decision = gate.evaluate(address="scw://SCW0/a/b/c", capability="x", metadata={})
        assert decision.allowed is False
        assert "acme-policy-service" in decision.reason
        assert "not implemented" in decision.reason

    def test_inert_provider_names_select_the_disabled_gate(self, subtests):
        for name in ("", "disabled", "none", "off", "FALSE", "0", None):
            with subtests.test(provider=name):
                if name is None:
                    continue
                assert isinstance(select_semantic_gate(name), DisabledSemanticGate)

    def test_the_provider_key_in_credentials_has_a_reader(self, tmp_path):
        """`semantic_gate.provider` reached no code that acted on it."""
        with mock.patch.dict(
            os.environ, {"MAXEY0_SEMANTIC_GATE_PROVIDER": "acme"}
        ):
            from maxey0_ss import settings as settings_mod

            resolved = settings_mod.Settings.load(warn=False)
            provider = resolved.providers["semantic_gate"].settings[
                "MAXEY0_SEMANTIC_GATE_PROVIDER"
            ]
            gate = select_semantic_gate(provider)
        assert isinstance(gate, UnimplementedSemanticGate)
        assert gate.name == "acme"

    def test_a_bad_address_says_which_stage_refused_it(self):
        surface = build_surface()
        out = tool(surface, "maxey0-ss.gate.inspect").handler({"scw_address": "nope"})
        assert out["allowed"] is False
        assert out["stage"] == "address"


# ---------------------------------------------------------------------------
# 4 - credentials sections with no reader
# ---------------------------------------------------------------------------


class TestCredentialsSectionsAreRead:
    CREDS = {
        "mcp": {"default_bearer_token": "TOKEN_FROM_FILE"},
        "oauth": {
            "client_id": "CLIENT_FROM_FILE",
            "client_secret": "SECRET_FROM_FILE",
            "issuer": "https://issuer.example.invalid",
            "jwks_url": "https://issuer.example.invalid/jwks",
        },
        "a2a": {"shared_secret": "A2A_FROM_FILE"},
    }

    def _clean_env(self):
        return mock.patch.dict(
            os.environ,
            {k: "" for k in (
                "MAXEY0_JWT_ISSUER", "MAXEY0_JWT_AUDIENCE", "MAXEY0_JWKS_URL",
                "MAXEY0_OAUTH_CLIENT_ID", "MAXEY0_OAUTH_CLIENT_SECRET",
                "MAXEY0_MCP_DEFAULT_BEARER_TOKEN", "MAXEY0_A2A_SHARED_SECRET",
            )},
        )

    def test_the_oauth_section_is_read(self):
        with self._clean_env():
            cfg = AuthConfig.load(self.CREDS)
        assert cfg.client_id == "CLIENT_FROM_FILE"
        assert cfg.client_secret == "SECRET_FROM_FILE"
        assert cfg.issuer == "https://issuer.example.invalid"
        assert cfg.jwks_url == "https://issuer.example.invalid/jwks"

    def test_the_mcp_section_is_read(self):
        with self._clean_env():
            cfg = AuthConfig.load(self.CREDS)
        assert cfg.default_bearer_token == "TOKEN_FROM_FILE"

    def test_the_environment_wins_over_the_file(self):
        with mock.patch.dict(
            os.environ, {"MAXEY0_OAUTH_CLIENT_ID": "CLIENT_FROM_ENV"}
        ):
            cfg = AuthConfig.load(self.CREDS)
        assert cfg.client_id == "CLIENT_FROM_ENV"
        assert ("client_id", "env") in cfg.sources

    def test_the_manifest_names_the_source_without_naming_the_value(self):
        with self._clean_env():
            manifest = AuthConfig.load(self.CREDS).public_manifest()
        blob = json.dumps(manifest)
        assert "credentials" in manifest["sources"]
        for secret in ("SECRET_FROM_FILE", "TOKEN_FROM_FILE", "A2A_FROM_FILE"):
            assert secret not in blob

    def test_oidc_credentials_under_an_unimplemented_mode_are_reported_inert(self):
        """"configured" alone could not distinguish this from "nothing set"."""
        with self._clean_env():
            manifest = AuthConfig.load(self.CREDS).public_manifest()
        assert manifest["mode"] == "disabled"
        assert manifest["mode_implemented"] is True
        assert "client_secret" in manifest["inert"]

    def test_no_credential_value_ever_reaches_the_auth_manifest_tool(self):
        surface = build_surface()
        blob = json.dumps(tool(surface, "maxey0-ss.auth.manifest").handler({}))
        assert "credential_values_exposed" in blob
        assert '"values"' not in blob

    def test_a_credentials_file_token_actually_authenticates(self):
        """It was loaded, reported, and then rejected at the door.

        `_bearer_tokens()` read `MAXEY0_MCP_DEFAULT_BEARER_TOKEN` from the
        environment directly, so a token supplied in `config/credentials.json`
        produced a config that said it was configured and an authorizer that
        refused it. Authentication failing for a credential the system says it
        accepted is worse than one that is plainly absent.
        """
        from maxey0_ss.auth.policy import Authorizer

        with mock.patch.dict(
            os.environ,
            {"MAXEY0_AUTH_MODE": "bearer", "MAXEY0_MCP_DEFAULT_BEARER_TOKEN": "",
             "MAXEY0_MCP_TOKENS": ""},
        ):
            authz = Authorizer(AuthConfig.load(self.CREDS))
            principal = authz.principal("Bearer TOKEN_FROM_FILE")
        assert principal.authenticated is True
        assert principal.role == "operator"  # never admin from a shared secret


class TestDeploymentPostureIsReported:
    """The single fact the deployment checklist turns on."""

    def _manifest(self, **env):
        base = {"MAXEY0_AUTH_MODE": "disabled", "MAXEY0_PUBLIC": ""}
        with mock.patch.dict(os.environ, {**base, **env}):
            return tool(build_surface(), "maxey0-ss.auth.manifest").handler({})

    def test_admin_open_is_reported_when_every_caller_is_admin(self):
        manifest = self._manifest()
        assert manifest["admin_open"] is True
        assert manifest["enforced"] is False
        assert manifest["anonymous_role"] == "admin"
        assert "MAXEY0_PUBLIC=1" in manifest["warning"]

    def test_setting_public_closes_it(self):
        manifest = self._manifest(MAXEY0_PUBLIC="1")
        assert manifest["admin_open"] is False
        assert manifest["enforced"] is True
        assert manifest["anonymous_role"] == "public"
        assert "warning" not in manifest

    def test_bearer_mode_closes_it_too(self):
        manifest = self._manifest(MAXEY0_AUTH_MODE="bearer")
        assert manifest["admin_open"] is False
        assert manifest["enforced"] is True

    def test_the_manifest_is_the_authorizers_not_the_configs(self):
        """`Authorizer.manifest()` had one caller in the repo, and it was a test."""
        manifest = self._manifest()
        for key in ("public_deployment", "enforced", "admin_open",
                    "oidc_implemented", "anonymous_role"):
            assert key in manifest, (
                f"{key} is computed by Authorizer.manifest() and must reach the "
                f"auth.manifest tool"
            )


# ---------------------------------------------------------------------------
# 5 - evidence disclosure limit
# ---------------------------------------------------------------------------


class TestAttestationLimitIsClamped:
    def test_a_negative_limit_does_not_invert_the_slice(self, subtests):
        """limit=-5 yielded records[5:] - more than the cap, not fewer."""
        for raw, expected in ((-5, 1), (-1, 1), (0, 200), (None, 200),
                              ("", 200), (10, 10), (10**9, MAX_ATTESTATION_LIMIT)):
            with subtests.test(limit=raw):
                assert _clamp_limit(raw) == expected

    def test_a_non_numeric_limit_falls_back_instead_of_raising(self, subtests):
        for raw in ("abc", [], {}, object(), True, False):
            with subtests.test(limit=raw):
                assert _clamp_limit(raw) == 200

    def test_a_float_limit_is_accepted_rather_than_crashing_the_tool(self):
        assert _clamp_limit(7.9) == 7

    def test_the_tool_honours_the_clamp(self):
        surface = build_surface()
        attest = tool(surface, "maxey0-ss.evidence.attestations")
        # Generate some records through the real containment path.
        create = tool(surface, "maxey0-ss.scw.create")
        for i in range(3):
            create.handler({"scw_id": f"SCW1{i}", "task": "t"})
        out = attest.handler({"limit": -5})
        assert len(out["attestations"]) <= 1


# ---------------------------------------------------------------------------
# 6 - the unauthenticated amplification path
# ---------------------------------------------------------------------------


class TestArtifactIsNotRehashedPerRequest:
    def test_repeated_calls_read_the_file_once(self):
        mcp_surface._ARTIFACT_MEMO.clear()
        real = mcp_surface.Path.read_bytes
        calls = {"n": 0}

        def counting(self, *a, **k):
            calls["n"] += 1
            return real(self, *a, **k)

        with mock.patch.object(mcp_surface.Path, "read_bytes", counting):
            first = mcp_surface.super_space_artifact()
            for _ in range(20):
                mcp_surface.super_space_artifact()
        assert calls["n"] == 1, (
            "health is public and uncapability-gated; it read ~470 KB and "
            "hashed it on every request"
        )
        assert first["kind"] in {"built", "fallback-stub"}

    def test_the_memo_does_not_hand_out_a_shared_mutable_dict(self):
        a = mcp_surface.super_space_artifact()
        a["kind"] = "tampered"
        assert mcp_surface.super_space_artifact()["kind"] != "tampered"


class TestTheDigestDescribesWhatIsServed:
    """`app.artifact.sha256` is what a verifier checks the received App against.

    It was the digest of `read_bytes()` while `resources/read` returned
    `read_text()`, which applies universal-newline translation. A bundle with
    five CRLF sequences hashed 475802 bytes and served 475797 — the server
    published a digest of bytes it did not send. It passed for months because
    the bundles happened to contain no CRLF, which makes it worse rather than
    better: a check that is correct by luck reads as evidence and measures
    nothing.
    """

    def test_the_digest_matches_the_bytes_that_go_on_the_wire(self):
        art = mcp_surface.super_space_artifact()
        served = mcp_surface.super_space_html().encode("utf-8")
        assert art["sha256"] == __import__("hashlib").sha256(served).hexdigest()
        assert art["bytes"] == len(served)

    def test_it_holds_for_a_bundle_containing_crlf(self, tmp_path):
        """The exact shape that broke it, constructed rather than waited for."""
        bundle = tmp_path / "mcp-app.html"
        bundle.write_bytes(b"<!doctype html>\r\n<p>a</p>\r\n<p>b</p>\n")
        with mock.patch.object(mcp_surface, "_APP_BUILT", bundle):
            mcp_surface._ARTIFACT_MEMO.clear()
            art = mcp_surface.super_space_artifact()
            served = mcp_surface.super_space_html().encode("utf-8")
        mcp_surface._ARTIFACT_MEMO.clear()
        assert art["bytes"] == len(served) == bundle.stat().st_size
        assert art["sha256"] == __import__("hashlib").sha256(served).hexdigest()

    def test_the_resource_reader_and_the_artifact_tool_agree(self):
        surface = build_surface()
        art = tool(surface, "maxey0-ss.app.artifact").handler({})
        resource = next(r for r in surface.resources if r.uri == art["uri"])
        assert len(resource.reader().encode("utf-8")) == art["bytes"]
