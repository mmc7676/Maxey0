"""Bearer tokens: hashed per-caller entries, fail-closed parsing, and minting.

The findings these tests hold shut:

- `Principal.subject` was `bearer:<first six characters of the token>`, so every
  log line and attestation that recorded who called carried a piece of the
  credential that called.
- Tokens were matched with `dict.get(token)`, whose timing depends on the
  presented value, and stored only in plaintext, so a leaked `.env` was a
  working credential.
- A `MAXEY0_MCP_TOKENS` entry with a role no table defines was accepted as-is:
  an authenticated principal that could do nothing, and no word about why.
- An unknown `MAXEY0_AUTH_MODE` -- `bearr` -- fell through to `disabled`, which
  on a deployment without `MAXEY0_PUBLIC=1` is admin for every caller.

Token-shaped values in this file are assembled at runtime. The packaging scanner
reads the bytes of every tracked file, this one included, and the test that
proves it catches a minted token must not itself be one.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import pathlib
import subprocess
import sys
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from maxey0_ss.auth import policy
from maxey0_ss.auth.config import AuthConfig
from maxey0_ss.auth.policy import (
    LOCAL_ADMIN,
    ANONYMOUS,
    AuthError,
    Authorizer,
    BearerTokens,
    token_hash_entry,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"

VARS = ("MAXEY0_MCP_TOKEN_HASHES", "MAXEY0_MCP_TOKENS",
        "MAXEY0_MCP_DEFAULT_BEARER_TOKEN", "MAXEY0_PUBLIC", "MAXEY0_AUTH_MODE")


def _token(tag: str) -> str:
    """A long random-looking token, built rather than written down."""
    return "tok" + "_" + hashlib.sha256(tag.encode()).hexdigest()[:40]


def _hex(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@pytest.fixture
def env(monkeypatch):
    """A bearer deployment with no tokens; each test adds the ones it needs."""
    for name in VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MAXEY0_AUTH_MODE", "bearer")
    return monkeypatch


def _authz() -> Authorizer:
    return Authorizer(AuthConfig.load({}))


# ---------------------------------------------------------------------------
# hashed entries
# ---------------------------------------------------------------------------


class TestHashedTokens:
    def test_a_hashed_entry_authenticates_as_its_label(self, env):
        token = _token("ci")
        env.setenv("MAXEY0_MCP_TOKEN_HASHES", token_hash_entry(token, "builder", "ci-runner"))
        principal = _authz().principal(f"Bearer {token}")
        assert principal.authenticated is True
        assert principal.role == "builder"
        assert principal.subject == "bearer:ci-runner"

    def test_the_entry_format_is_sha256_hex_role_label(self):
        token = _token("fmt")
        assert token_hash_entry(token, "viewer", "a.b_c-d") == (
            f"sha256:{_hex(token)}:viewer:a.b_c-d")

    def test_a_wrong_token_is_a_401(self, env):
        env.setenv("MAXEY0_MCP_TOKEN_HASHES",
                   token_hash_entry(_token("right"), "operator", "one"))
        with pytest.raises(AuthError) as exc:
            _authz().principal(f"Bearer {_token('wrong')}")
        assert (exc.value.code, exc.value.status) == (-32001, 401)

    def test_the_digest_itself_is_not_a_credential(self, env):
        """Presenting what the deployment stores must not authenticate."""
        token = _token("leak")
        env.setenv("MAXEY0_MCP_TOKEN_HASHES", token_hash_entry(token, "admin", "ops"))
        for presented in (_hex(token), f"sha256:{_hex(token)}"):
            with pytest.raises(AuthError):
                _authz().principal(f"Bearer {presented}")

    def test_several_entries_each_map_to_their_own_role(self, env):
        a, b = _token("a"), _token("b")
        env.setenv("MAXEY0_MCP_TOKEN_HASHES", ",".join((
            token_hash_entry(a, "viewer", "alice"),
            " " + token_hash_entry(b, "admin", "bob") + " ",
        )))
        authz = _authz()
        assert (authz.principal(f"Bearer {a}").role, authz.principal(f"Bearer {b}").role) \
            == ("viewer", "admin")
        assert authz.principal(f"Bearer {b}").subject == "bearer:bob"


# ---------------------------------------------------------------------------
# plaintext, kept for migration
# ---------------------------------------------------------------------------


class TestPlaintextTokens:
    def test_plaintext_entries_still_authenticate(self, env):
        token = _token("plain")
        env.setenv("MAXEY0_MCP_TOKENS", f"{token}:operator")
        principal = _authz().principal(f"Bearer {token}")
        assert principal.role == "operator"
        assert principal.subject == f"bearer:sha256:{_hex(token)[:12]}"

    def test_the_default_token_is_operator_and_named_default(self, env):
        token = _token("shared")
        env.setenv("MAXEY0_MCP_DEFAULT_BEARER_TOKEN", token)
        principal = _authz().principal(f"Bearer {token}")
        assert (principal.role, principal.subject) == ("operator", "bearer:default")

    def test_an_explicit_entry_for_the_default_token_keeps_its_role(self, env):
        """`mapping.setdefault(default, "operator")` semantics, kept."""
        token = _token("both")
        env.setenv("MAXEY0_MCP_TOKENS", f"{token}:builder")
        env.setenv("MAXEY0_MCP_DEFAULT_BEARER_TOKEN", token)
        authz = _authz()
        assert authz.principal(f"Bearer {token}").role == "builder"
        assert authz.tokens().plaintext == 1

    def test_whitespace_around_token_and_role_is_ignored(self, env):
        token = _token("spaced")
        env.setenv("MAXEY0_MCP_TOKENS", f"  {token} :  viewer  ,")
        assert _authz().principal(f"Bearer {token}").role == "viewer"

    def test_a_token_may_contain_a_colon_a_role_may_not(self, env):
        token = _token("x") + ":part"
        env.setenv("MAXEY0_MCP_TOKENS", f"{token}:operator")
        assert _authz().principal(f"Bearer {token}").role == "operator"

    def test_no_subject_carries_token_material(self, env, subtests):
        """It was `bearer:<first six characters>`."""
        hashed, plain, default = _token("h"), _token("p"), _token("d")
        env.setenv("MAXEY0_MCP_TOKEN_HASHES", token_hash_entry(hashed, "viewer", "svc"))
        env.setenv("MAXEY0_MCP_TOKENS", f"{plain}:viewer")
        env.setenv("MAXEY0_MCP_DEFAULT_BEARER_TOKEN", default)
        authz = _authz()
        for token in (hashed, plain, default):
            with subtests.test(token=token[:4]):
                subject = authz.principal(f"Bearer {token}").subject
                for width in (4, 6, 8):
                    assert token[:width] not in subject
                    assert token[-width:] not in subject


# ---------------------------------------------------------------------------
# constant time, all entries, parsed once
# ---------------------------------------------------------------------------


class TestMatching:
    def test_every_entry_is_compared_even_after_a_match(self, env):
        first, second, third = _token("1"), _token("2"), _token("3")
        env.setenv("MAXEY0_MCP_TOKEN_HASHES", token_hash_entry(first, "viewer", "one"))
        env.setenv("MAXEY0_MCP_TOKENS", f"{second}:viewer,{third}:viewer")
        env.setenv("MAXEY0_MCP_DEFAULT_BEARER_TOKEN", _token("4"))
        authz = _authz()
        authz.tokens()
        seen = []
        real = policy.hmac.compare_digest

        def spy(a, b):
            seen.append((len(a), len(b)))
            return real(a, b)

        with mock.patch.object(policy.hmac, "compare_digest", side_effect=spy):
            assert authz.principal(f"Bearer {first}").subject == "bearer:one"
        assert len(seen) == 4, "a match on the first entry must not skip the rest"
        assert set(seen) == {(32, 32)}, "plaintext entries are compared as digests too"

    def test_configuration_is_parsed_once_per_authorizer(self, env):
        token = _token("once")
        env.setenv("MAXEY0_MCP_TOKEN_HASHES", token_hash_entry(token, "viewer", "v"))
        authz = _authz()
        with mock.patch.object(BearerTokens, "load", wraps=BearerTokens.load) as load:
            for _ in range(5):
                authz.principal(f"Bearer {token}")
            authz.manifest()
        assert load.call_count == 1

    def test_the_environment_is_read_when_first_needed(self, env):
        """Lazily, like `verifier()`: set after construction, still seen."""
        authz = _authz()
        token = _token("late")
        env.setenv("MAXEY0_MCP_TOKENS", f"{token}:viewer")
        assert authz.principal(f"Bearer {token}").role == "viewer"

    def test_an_empty_bearer_header_is_a_401_not_a_500(self, env):
        env.setenv("MAXEY0_MCP_TOKENS", f"{_token('e')}:viewer")
        for header in ("Bearer ", "Bearer   ", "Basic abc", ""):
            with pytest.raises(AuthError) as exc:
                _authz().principal(header)
            assert exc.value.status == 401


# ---------------------------------------------------------------------------
# configuration errors fail closed
# ---------------------------------------------------------------------------


GOOD = _token("good")
HEX = _hex(_token("other"))

#: (variable, value, entry number the refusal must name, fragment of the reason)
MISCONFIGURED = (
    ("MAXEY0_MCP_TOKEN_HASHES", f"md5:{HEX}:viewer:a", 1, "sha256:<64"),
    ("MAXEY0_MCP_TOKEN_HASHES", f"sha256:{HEX[:40]}:viewer:a", 1, "64 lowercase hex"),
    ("MAXEY0_MCP_TOKEN_HASHES", f"sha256:{HEX.upper()}:viewer:a", 1, "64 lowercase hex"),
    ("MAXEY0_MCP_TOKEN_HASHES", f"sha256:{HEX}:superuser:a", 1, "role is not one of"),
    ("MAXEY0_MCP_TOKEN_HASHES", f"sha256:{HEX}:viewer:bad label", 1, "label"),
    ("MAXEY0_MCP_TOKEN_HASHES", f"sha256:{HEX}:viewer:" + "x" * 65, 1, "label"),
    ("MAXEY0_MCP_TOKEN_HASHES", f"sha256:{HEX}:viewer", 1, "sha256:<64"),
    ("MAXEY0_MCP_TOKEN_HASHES", f"sha256:{HEX}:viewer:a:extra", 1, "sha256:<64"),
    ("MAXEY0_MCP_TOKEN_HASHES",
     f"sha256:{HEX}:viewer:dup,sha256:{_hex('x' * 30)}:viewer:dup", 2, "label of entry 1"),
    ("MAXEY0_MCP_TOKEN_HASHES",
     f"sha256:{HEX}:viewer:a,,sha256:{HEX}:admin:b", 3, "digest of"),
    ("MAXEY0_MCP_TOKENS", "lonely-token", 1, "<token>:<role>"),
    ("MAXEY0_MCP_TOKENS", "tok:", 1, "<token>:<role>"),
    ("MAXEY0_MCP_TOKENS", ":viewer", 1, "<token>:<role>"),
    ("MAXEY0_MCP_TOKENS", "some-token:superuser", 1, "role is not one of"),
    ("MAXEY0_MCP_TOKENS", "some-token:Operator", 1, "role is not one of"),
    ("MAXEY0_MCP_TOKENS", "a-token:viewer,b-token:viewer,a-token:admin", 3, "same token as"),
    ("MAXEY0_MCP_TOKENS", f"sha256:{HEX}:viewer", 1, "belong in MAXEY0_MCP_TOKEN_HASHES"),
    ("MAXEY0_MCP_TOKENS", f"{HEX}:viewer", 1, "belong in MAXEY0_MCP_TOKEN_HASHES"),
    ("MAXEY0_MCP_TOKENS", f"SHA256:{HEX.upper()}:viewer", 1, "belong in MAXEY0_MCP_TOKEN_HASHES"),
)


class TestMisconfigurationFailsClosed:
    def test_every_invalid_entry_refuses_every_request(self, env, subtests):
        for variable, value, entry, reason in MISCONFIGURED:
            with subtests.test(variable=variable, value=value[:30]):
                env.delenv("MAXEY0_MCP_TOKEN_HASHES", raising=False)
                env.setenv("MAXEY0_MCP_TOKENS", f"{GOOD}:viewer")
                if variable == "MAXEY0_MCP_TOKENS":
                    env.setenv(variable, f"{GOOD}:viewer,{value}")
                    entry += 1
                else:
                    env.setenv(variable, value)
                authz = _authz()
                # A token that is itself configured correctly is refused too:
                # there is no serving from the entries that parsed.
                for header in (f"Bearer {GOOD}", None, "Bearer nonsense"):
                    with pytest.raises(AuthError) as exc:
                        authz.principal(header)
                    assert (exc.value.code, exc.value.status) == (-32004, 501)
                message = str(exc.value)
                assert f"{variable} entry {entry}" in message
                assert reason in message
                assert authz.manifest()["token_config_errors"] >= 1

    def test_a_digest_in_the_plaintext_variable_is_not_a_credential(self, env):
        """It used to be accepted as a token, so the digest -- the value meant
        to be safe to leak -- authenticated."""
        token = _token("half-migrated")
        env.delenv("MAXEY0_MCP_TOKEN_HASHES", raising=False)
        env.setenv("MAXEY0_MCP_TOKENS", f"sha256:{_hex(token)}:operator")
        for header in (f"Bearer sha256:{_hex(token)}", f"Bearer {token}"):
            with pytest.raises(AuthError) as exc:
                _authz().principal(header)
            assert (exc.value.code, exc.value.status) == (-32004, 501)
            assert "MAXEY0_MCP_TOKEN_HASHES" in str(exc.value)

    def test_the_refusal_never_echoes_an_entry(self, env):
        label, secret = "private-label", _token("never-echoed")
        env.setenv("MAXEY0_MCP_TOKEN_HASHES", f"sha256:{HEX}:superuser:{label}")
        env.setenv("MAXEY0_MCP_TOKENS", f"{secret}:superuser")
        with pytest.raises(AuthError) as exc:
            _authz().principal(f"Bearer {secret}")
        message = str(exc.value)
        for fragment in (label, secret, secret[:8], HEX, HEX[:12], "superuser"):
            assert fragment not in message
        assert "MAXEY0_MCP_TOKEN_HASHES entry 1" in message
        assert "MAXEY0_MCP_TOKENS entry 1" in message

    def test_a_plaintext_copy_of_a_hashed_token_is_a_repeat(self, env):
        """The migration step that is easy to half-finish, named in the refusal."""
        token = _token("migrating")
        env.setenv("MAXEY0_MCP_TOKEN_HASHES", token_hash_entry(token, "operator", "m"))
        env.setenv("MAXEY0_MCP_TOKENS", f"{token}:operator")
        with pytest.raises(AuthError) as exc:
            _authz().principal(f"Bearer {token}")
        assert exc.value.status == 501
        assert ("MAXEY0_MCP_TOKENS entry 1 is the same token as "
                "MAXEY0_MCP_TOKEN_HASHES entry 1") in str(exc.value)

    def test_invalid_entries_do_not_affect_other_modes(self, env):
        """Tokens are read only in bearer mode; the manifest still counts them."""
        env.setenv("MAXEY0_AUTH_MODE", "disabled")
        env.setenv("MAXEY0_MCP_TOKENS", "tok:superuser")
        authz = _authz()
        assert authz.principal(None) == LOCAL_ADMIN
        assert authz.manifest()["token_config_errors"] == 1


# ---------------------------------------------------------------------------
# unknown auth mode
# ---------------------------------------------------------------------------


class TestUnknownModeFailsClosed:
    def test_an_unknown_mode_refuses_every_request(self, env, subtests):
        for mode in ("bearr", "none", "off", "open", "admin", "jwt"):
            with subtests.test(mode=mode):
                env.setenv("MAXEY0_AUTH_MODE", mode)
                authz = _authz()
                for header in (None, "Bearer anything"):
                    with pytest.raises(AuthError) as exc:
                        authz.principal(header)
                    assert (exc.value.code, exc.value.status) == (-32004, 501)
                assert repr(mode) in str(exc.value)
                assert authz.admin_open is False

    def test_the_manifest_says_so(self, env):
        env.setenv("MAXEY0_AUTH_MODE", "bearr")
        manifest = _authz().manifest()
        assert manifest["mode_implemented"] is False
        assert manifest["admin_open"] is False
        assert manifest["enforced"] is True
        assert "every request is refused" in manifest["warning"]

    def test_case_and_whitespace_are_normalized_the_same_everywhere(self, env, subtests):
        """Config stripped, policy lower-cased: `Bearer` enforced bearer while the
        manifest said the mode was not implemented."""
        token = _token("norm")
        env.setenv("MAXEY0_MCP_TOKENS", f"{token}:viewer")
        for raw, mode in ((" Bearer ", "bearer"), ("BEARER", "bearer"),
                          ("Disabled", "disabled"), ("  ", "disabled"), ("", "disabled")):
            with subtests.test(raw=raw):
                env.setenv("MAXEY0_AUTH_MODE", raw)
                config = AuthConfig.load({})
                authz = Authorizer(config)
                assert config.mode == authz.mode == mode
                manifest = authz.manifest()
                assert manifest["mode"] == mode
                assert manifest["mode_implemented"] is True
                if mode == "bearer":
                    assert authz.principal(f"Bearer {token}").role == "viewer"
                    with pytest.raises(AuthError):
                        authz.principal(None)

    def test_a_directly_built_config_is_normalized_too(self):
        config = AuthConfig(mode=" OIDC ")
        assert config.mode_implemented is True
        assert config.public_manifest()["mode"] == "oidc"
        assert Authorizer(config).mode == "oidc"

    def test_over_the_wire_it_is_a_501(self, env):
        env.setenv("MAXEY0_AUTH_MODE", "bearr")
        from maxey0_ss.api.app import create_app

        client = TestClient(create_app())
        response = client.post(
            "/mcp",
            headers={"MCP-Protocol-Version": "2026-07-28", "Mcp-Method": "tools/call",
                     "Mcp-Name": "maxey0-ss.scw.create"},
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                  "params": {"name": "maxey0-ss.scw.create",
                             "arguments": {"scw_id": "SCW98", "task": "typo"}}},
        )
        assert response.status_code == 501
        assert response.json()["error"]["code"] == -32004
        assert "result" not in response.json()

    def test_stdio_keeps_its_local_trust(self, env):
        """stdio carries no credentials and is reached only by a local parent
        process, so `_stdio_principal` turns any refusal into LOCAL_ADMIN unless
        the deployment is public. Pinned so a change to that stance is a
        decision, not an accident."""
        from maxey0_ss.mcp_stdio_server import _stdio_principal

        env.setenv("MAXEY0_AUTH_MODE", "bearr")
        assert _stdio_principal(_authz()) == LOCAL_ADMIN
        env.setenv("MAXEY0_PUBLIC", "1")
        assert _stdio_principal(_authz()) == ANONYMOUS


# ---------------------------------------------------------------------------
# the manifest: counts, never values
# ---------------------------------------------------------------------------


class TestManifest:
    def _manifest(self, env, *, hashed=0, plaintext=0, default=False, public=False):
        entries = [token_hash_entry(_token(f"h{i}"), "viewer", f"label-{i}")
                   for i in range(hashed)]
        if entries:
            env.setenv("MAXEY0_MCP_TOKEN_HASHES", ",".join(entries))
        if plaintext:
            env.setenv("MAXEY0_MCP_TOKENS",
                       ",".join(f"{_token(f'p{i}')}:viewer" for i in range(plaintext)))
        if default:
            env.setenv("MAXEY0_MCP_DEFAULT_BEARER_TOKEN", _token("default"))
        if public:
            env.setenv("MAXEY0_PUBLIC", "1")
        return _authz().manifest()

    def test_token_storage_is_reported(self, env, subtests):
        cases = (
            ({}, "none", 0, 0),
            ({"hashed": 2}, "hashed", 2, 0),
            ({"plaintext": 1}, "plaintext", 0, 1),
            ({"default": True}, "plaintext", 0, 1),
            ({"hashed": 1, "plaintext": 2, "default": True}, "mixed", 1, 3),
        )
        for kwargs, storage, hashed, plaintext in cases:
            with subtests.test(**kwargs):
                for name in VARS[:3]:
                    env.delenv(name, raising=False)
                manifest = self._manifest(env, **kwargs)
                assert manifest["token_storage"] == storage
                assert manifest["bearer_tokens"] == {"hashed": hashed, "plaintext": plaintext}
                assert manifest["token_config_errors"] == 0

    def test_no_label_digest_or_token_reaches_the_manifest(self, env):
        manifest = self._manifest(env, hashed=2, plaintext=2, default=True, public=True)
        blob = json.dumps(manifest)
        assert manifest["credential_values_exposed"] is False
        for i in range(2):
            token = _token(f"h{i}")
            for fragment in (f"label-{i}", _hex(token), _hex(token)[:12], token):
                assert fragment not in blob
            plain = _token(f"p{i}")
            for fragment in (plain, _hex(plain)[:12]):
                assert fragment not in blob
        assert _token("default") not in blob

    def test_the_public_tool_carries_the_counts_and_nothing_else(self, env):
        from maxey0_ss.mcp_surface import build_surface

        token = _token("tool")
        env.setenv("MAXEY0_MCP_TOKEN_HASHES", token_hash_entry(token, "viewer", "tool-label"))
        surface = build_surface()
        manifest = next(t for t in surface.tools
                        if t.name == "maxey0-ss.auth.manifest").handler({})
        assert manifest["token_storage"] == "hashed"
        blob = json.dumps(manifest)
        assert "tool-label" not in blob and _hex(token)[:12] not in blob

    def test_plaintext_on_a_public_deployment_warns(self, env):
        manifest = self._manifest(env, plaintext=1, public=True)
        assert "scripts/mint_token.py" in manifest["warning"]
        assert "MAXEY0_MCP_TOKEN_HASHES" in manifest["warning"]

    def test_the_default_token_counts_as_plaintext_for_the_warning(self, env):
        assert "scripts/mint_token.py" in self._manifest(env, default=True, public=True)["warning"]

    def test_hashed_only_does_not_warn(self, env):
        assert "warning" not in self._manifest(env, hashed=1, public=True)

    def test_plaintext_off_the_internet_does_not_warn(self, env):
        assert "warning" not in self._manifest(env, plaintext=1)

    def test_a_plaintext_warning_does_not_refuse(self, env):
        """The live deployment runs a plaintext entry until it is migrated."""
        token = _token("live")
        env.setenv("MAXEY0_MCP_TOKENS", f"{token}:operator")
        env.setenv("MAXEY0_PUBLIC", "1")
        assert _authz().principal(f"Bearer {token}").role == "operator"

    def test_bearer_misconfiguration_warns_with_the_count(self, env):
        env.setenv("MAXEY0_MCP_TOKENS", "a:superuser,b:root")
        manifest = _authz().manifest()
        assert manifest["token_config_errors"] == 2
        assert "2 bearer token entries are invalid" in manifest["warning"]


# ---------------------------------------------------------------------------
# scripts/mint_token.py
# ---------------------------------------------------------------------------


@pytest.fixture
def mint():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    return importlib.import_module("mint_token")


class TestMintToken:
    def test_the_default_mode_prints_the_token_once_and_the_entry(self, mint, capsys, env):
        assert mint.main(["--role", "builder", "--label", "ci-runner"]) == 0
        out = capsys.readouterr()
        lines = out.out.splitlines()
        assert len(lines) == 4 and lines[0].startswith("#") and lines[2].startswith("#")
        token, entry = lines[1], lines[3]
        assert token.startswith("m0ss" + "_") and len(token) == 5 + 43
        assert entry == f"sha256:{_hex(token)}:builder:ci-runner"
        assert out.err == ""
        # The round trip: the entry authenticates the token it was minted with.
        env.setenv("MAXEY0_MCP_TOKEN_HASHES", entry)
        principal = _authz().principal(f"Bearer {token}")
        assert (principal.role, principal.subject) == ("builder", "bearer:ci-runner")

    def test_tokens_are_unique(self, mint):
        assert len({mint.mint() for _ in range(200)}) == 200

    def test_out_writes_the_token_and_prints_only_the_entry(self, mint, capsys, tmp_path):
        path = tmp_path / "caller.token"
        assert mint.main(["--role", "viewer", "--label", "dash", "--out", str(path)]) == 0
        token = path.read_text(encoding="utf-8").strip()
        out = capsys.readouterr()
        assert out.out == f"sha256:{_hex(token)}:viewer:dash\n"
        assert token not in out.out and token not in out.err

    def test_out_refuses_to_overwrite_without_force(self, mint, capsys, tmp_path):
        path = tmp_path / "caller.token"
        path.write_text("keep me\n", encoding="utf-8")
        assert mint.main(["--role", "viewer", "--label", "d", "--out", str(path)]) == 1
        assert path.read_text(encoding="utf-8") == "keep me\n"
        assert "--force" in capsys.readouterr().err
        assert mint.main(["--role", "viewer", "--label", "d", "--out", str(path),
                          "--force"]) == 0
        assert path.read_text(encoding="utf-8").startswith("m0ss" + "_")

    def test_out_refuses_a_path_inside_the_repository(self, mint, capsys):
        path = ROOT / "maxey0-mint-token-test.token"
        assert not path.exists()
        assert mint.main(["--role", "viewer", "--label", "d", "--out", str(path)]) == 1
        assert not path.exists()
        assert "inside the repository" in capsys.readouterr().err

    def test_from_file_hashes_an_existing_token(self, mint, capsys, tmp_path, env):
        existing = _token("issued-long-ago")
        source = tmp_path / "old.token"
        source.write_text(f"\n  {existing}  \n\n", encoding="utf-8")
        assert mint.main(["--role", "operator", "--label", "legacy",
                          "--from-file", str(source)]) == 0
        out = capsys.readouterr()
        assert out.out == f"sha256:{_hex(existing)}:operator:legacy\n"
        assert out.err == ""
        env.setenv("MAXEY0_MCP_TOKEN_HASHES", out.out.strip())
        assert _authz().principal(f"Bearer {existing}").subject == "bearer:legacy"

    def test_from_file_flags_a_short_token(self, mint, capsys, tmp_path):
        source = tmp_path / "weak.token"
        source.write_text("s3cr3t\n", encoding="utf-8")
        assert mint.main(["--role", "viewer", "--label", "w",
                          "--from-file", str(source)]) == 0
        assert "reversed by guessing" in capsys.readouterr().err

    def test_from_file_refuses_what_is_not_one_token(self, mint, capsys, tmp_path, subtests):
        cases = {"missing": None, "empty": "", "blank": "  \n\n",
                 "two-lines": "a-token\nb-token\n", "inner-space": "a token\n"}
        for name, body in cases.items():
            with subtests.test(case=name):
                path = tmp_path / f"{name}.token"
                if body is not None:
                    path.write_text(body, encoding="utf-8")
                assert mint.main(["--role", "viewer", "--label", "x",
                                  "--from-file", str(path)]) == 1
                assert capsys.readouterr().out == ""

    def test_arguments_are_validated(self, mint, capsys, tmp_path, subtests):
        for argv in (
            ["--label", "x"],
            ["--role", "viewer"],
            ["--role", "superuser", "--label", "x"],
            ["--role", "viewer", "--label", "has space"],
            ["--role", "viewer", "--label", "x" * 65],
            ["--role", "viewer", "--label", "a:b"],
            ["--role", "viewer", "--label", "x", "--force"],
            ["--role", "viewer", "--label", "x", "--out", str(tmp_path / "a"),
             "--from-file", str(tmp_path / "b")],
        ):
            with subtests.test(argv=argv):
                with pytest.raises(SystemExit) as exc:
                    mint.main(argv)
                assert exc.value.code == 2
                assert capsys.readouterr().out == ""

    def test_the_script_runs_standalone_and_prints_nothing_else(self, tmp_path):
        """Importing maxey0_ss loads .env; that must not reach stdout or stderr."""
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "mint_token.py"), "--role", "viewer",
             "--label", "standalone", "--out", str(tmp_path / "t.token")],
            capture_output=True, text=True, cwd=tmp_path, timeout=120,
        )
        assert result.returncode == 0, result.stderr
        token = (tmp_path / "t.token").read_text(encoding="utf-8").strip()
        assert result.stdout == f"sha256:{_hex(token)}:viewer:standalone\n"
        assert result.stderr.strip() == f"mint_token: token written to {tmp_path / 't.token'}"


# ---------------------------------------------------------------------------
# the packaging scanner knows the token shape, and not the digest shape
# ---------------------------------------------------------------------------


@pytest.fixture
def packaging():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    return importlib.import_module("_packaging")


class TestScanner:
    def test_a_minted_token_trips_the_scanner(self, packaging, mint, tmp_path):
        token = mint.mint()
        # The scanner skips values containing a placeholder marker ("fake",
        # "xxxx", ...), which 43 random characters very occasionally spell.
        while packaging._is_placeholder(token):  # pragma: no cover - rare
            token = mint.mint()
        planted = tmp_path / "notes.txt"
        planted.write_text(f"caller token: {token}\n", encoding="utf-8")
        found = packaging.scan_for_secrets([planted], tmp_path)
        assert found == ["notes.txt:1: Maxey0 bearer token"]

    def test_the_pattern_is_the_token_shape(self, packaging):
        pattern = dict(packaging.SECRET_PATTERNS)["Maxey0 bearer token"]
        prefix = "m0ss" + "_"
        assert pattern.search(prefix + "A1b2-C3d4_" * 3)
        assert not pattern.search(prefix + "short")
        assert not pattern.search("xm0ss" + "_" + "A" * 30)

    def test_a_hash_entry_trips_no_pattern(self, packaging, tmp_path):
        entry = token_hash_entry(_token("scan"), "operator", "ci-runner")
        planted = tmp_path / "deploy.env"
        planted.write_text(f"MAXEY0_MCP_TOKEN_HASHES={entry}\n{entry}\n", encoding="utf-8")
        assert packaging.scan_for_secrets([planted], tmp_path) == []
        for label, pattern in packaging.SECRET_PATTERNS:
            assert not pattern.search(entry), label

    def test_this_file_and_the_script_carry_no_credential_shape(self, packaging):
        files = [pathlib.Path(__file__), SCRIPTS / "mint_token.py"]
        assert packaging.scan_for_secrets(files, ROOT) == []
