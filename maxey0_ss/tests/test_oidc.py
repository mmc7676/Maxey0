"""OIDC verification, against tokens signed with a real key in-test.

`MAXEY0_AUTH_MODE=oidc` refused with -32004/501 through 0.2.x. These tests are
what make it safe to stop refusing, so they are written to attack the verifier
rather than to demonstrate it: every classic JWT failure has a test that asserts
the token is *rejected*, and the happy path is one test among many.

The key is generated here and the token is signed here, so the signature path
runs for real. A verifier tested only against a stubbed `verify` proves nothing
about whether it verifies.
"""
from __future__ import annotations

import base64
import hashlib
import http.client
import json
import os
import threading
import time
import urllib.error
from unittest import mock

import pytest

from maxey0_ss.auth.config import AuthConfig
from maxey0_ss.auth.oidc import (
    JWKSCache,
    OIDCError,
    OIDCVerifier,
    SUPPORTED_ALGORITHMS,
)
from maxey0_ss.auth.policy import AuthError, Authorizer
from maxey0_ss.auth.roles import PRECEDENCE, ROLES

ISSUER = "https://issuer.example.invalid"
AUDIENCE = "maxey0-ss"
JWKS_URL = f"{ISSUER}/.well-known/jwks.json"
KID = "test-key-1"


# ---------------------------------------------------------------------------
# a real RSA key, generated once
# ---------------------------------------------------------------------------


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _int_b64u(value: int) -> str:
    return _b64u(value.to_bytes((value.bit_length() + 7) // 8, "big"))


class RSAKey:
    """A small RSA key pair. 1024-bit because this signs test fixtures.

    Generating one per test module rather than committing a private key: a PEM
    in the tree is a credential shape the packaging scanner would catch, and
    correctly.
    """

    def __init__(self) -> None:
        self.p, self.q = _prime(512), _prime(512)
        while self.p == self.q:
            self.q = _prime(512)
        self.n = self.p * self.q
        self.e = 65537
        phi = (self.p - 1) * (self.q - 1)
        self.d = pow(self.e, -1, phi)

    def jwk(self, *, alg: str = "RS256", kid: str = KID) -> dict:
        return {"kty": "RSA", "kid": kid, "alg": alg, "use": "sig",
                "n": _int_b64u(self.n), "e": _int_b64u(self.e)}

    def sign(self, signing_input: bytes, *, bits: str = "256") -> bytes:
        digest = {"256": hashlib.sha256, "384": hashlib.sha384,
                  "512": hashlib.sha512}[bits](signing_input).digest()
        prefix = {
            "256": bytes.fromhex("3031300d060960864801650304020105000420"),
            "384": bytes.fromhex("3041300d060960864801650304020205000430"),
            "512": bytes.fromhex("3051300d060960864801650304020305000440"),
        }[bits]
        size = (self.n.bit_length() + 7) // 8
        block = (b"\x00\x01" + b"\xff" * (size - len(prefix) - len(digest) - 3)
                 + b"\x00" + prefix + digest)
        return pow(int.from_bytes(block, "big"), self.d, self.n).to_bytes(size, "big")


def _prime(bits: int) -> int:
    import random

    while True:
        candidate = random.getrandbits(bits) | (1 << (bits - 1)) | 1
        if _probably_prime(candidate):
            return candidate


def _probably_prime(n: int, rounds: int = 24) -> bool:
    import random

    for small in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if n % small == 0:
            return n == small
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for _ in range(rounds):
        a = random.randrange(2, n - 1)
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


KEY = RSAKey()


def make_token(key: RSAKey = KEY, *, alg: str = "RS256", kid: str = KID,
               claims: dict | None = None, signature: bytes | None = None,
               header: dict | None = None) -> str:
    now = int(time.time())
    body = {
        "iss": ISSUER, "aud": AUDIENCE, "sub": "user-1",
        "exp": now + 600, "iat": now, "scope": "observe scw.read",
    }
    body.update(claims or {})
    head = {"alg": alg, "kid": kid, "typ": "JWT"}
    head.update(header or {})
    h = _b64u(json.dumps(head, separators=(",", ":")).encode())
    p = _b64u(json.dumps(body, separators=(",", ":")).encode())
    signing_input = f"{h}.{p}".encode("ascii")
    sig = signature if signature is not None else key.sign(signing_input, bits=alg[2:])
    return f"{h}.{p}.{_b64u(sig)}"


@pytest.fixture
def verifier():
    keyset = {"keys": [KEY.jwk()]}
    cache = JWKSCache(JWKS_URL, fetcher=lambda url: keyset)
    return OIDCVerifier(issuer=ISSUER, audience=AUDIENCE, jwks=cache)


# ---------------------------------------------------------------------------
# the happy path, once
# ---------------------------------------------------------------------------


class TestAValidTokenVerifies:
    def test_a_correctly_signed_token_is_accepted(self, verifier):
        verified = verifier.verify(make_token())
        assert verified.subject == "user-1"
        assert verified.issuer == ISSUER
        assert verified.key_id == KID
        assert verified.algorithm == "RS256"

    def test_scopes_are_parsed_from_the_space_delimited_claim(self, verifier):
        assert verifier.verify(make_token()).scopes == ("observe", "scw.read")

    def test_a_list_audience_containing_ours_is_accepted(self, verifier):
        token = make_token(claims={"aud": ["other-rp", AUDIENCE]})
        assert verifier.verify(token).subject == "user-1"

    def test_rs384_and_rs512_verify(self, subtests, verifier):
        for alg in ("RS384", "RS512"):
            with subtests.test(alg=alg):
                keyset = {"keys": [KEY.jwk(alg=alg)]}
                v = OIDCVerifier(ISSUER, AUDIENCE,
                                 JWKSCache(JWKS_URL, fetcher=lambda u: keyset))
                assert v.verify(make_token(alg=alg)).algorithm == alg


# ---------------------------------------------------------------------------
# every way it must refuse
# ---------------------------------------------------------------------------


class TestTheClassicAttacks:
    def test_alg_none_is_refused(self, verifier):
        """The oldest JWT failure: a verifier that believes the token's alg."""
        token = make_token(alg="none", signature=b"")
        with pytest.raises(OIDCError, match="not accepted"):
            verifier.verify(token)

    def test_hs256_is_refused(self, verifier):
        """Key confusion: signing with the public key as an HMAC secret."""
        import hmac

        head = _b64u(json.dumps({"alg": "HS256", "kid": KID}).encode())
        body = _b64u(json.dumps({"iss": ISSUER, "aud": AUDIENCE, "sub": "x",
                                 "exp": int(time.time()) + 60}).encode())
        secret = _int_b64u(KEY.n).encode()
        mac = hmac.new(secret, f"{head}.{body}".encode(), hashlib.sha256).digest()
        with pytest.raises(OIDCError, match="not accepted"):
            verifier.verify(f"{head}.{body}.{_b64u(mac)}")

    def test_a_token_from_another_issuer_is_refused_before_any_signature(self, verifier):
        """RFC 9207. An attacker chooses `iss`; the issuer comes from config."""
        token = make_token(claims={"iss": "https://evil.example.invalid"})
        with pytest.raises(OIDCError, match="RFC 9207"):
            verifier.verify(token)

    def test_a_token_for_another_audience_is_refused(self, verifier):
        """The confused deputy: a perfectly valid token for somebody else."""
        token = make_token(claims={"aud": "some-other-relying-party"})
        with pytest.raises(OIDCError, match="audience"):
            verifier.verify(token)

    def test_a_tampered_payload_is_refused(self, verifier):
        head, payload, sig = make_token().split(".")
        forged = json.loads(base64.urlsafe_b64decode(payload + "=="))
        forged["sub"] = "admin"
        swapped = _b64u(json.dumps(forged, separators=(",", ":")).encode())
        with pytest.raises(OIDCError, match="signature does not verify"):
            verifier.verify(f"{head}.{swapped}.{sig}")

    def test_a_signature_from_a_different_key_is_refused(self, verifier):
        other = RSAKey()
        with pytest.raises(OIDCError, match="signature does not verify"):
            verifier.verify(make_token(key=other))

    def test_an_expired_token_is_refused(self, verifier):
        token = make_token(claims={"exp": int(time.time()) - 3600})
        with pytest.raises(OIDCError, match="expired"):
            verifier.verify(token)

    def test_a_token_with_no_exp_is_refused(self, verifier):
        """A bearer with no expiry is a password."""
        token = make_token(claims={"exp": None})
        with pytest.raises(OIDCError, match="no exp"):
            verifier.verify(token)

    def test_a_not_yet_valid_token_is_refused(self, verifier):
        token = make_token(claims={"nbf": int(time.time()) + 3600})
        with pytest.raises(OIDCError, match="not valid yet"):
            verifier.verify(token)

    def test_a_token_with_no_sub_identifies_nobody(self, verifier):
        with pytest.raises(OIDCError, match="no sub"):
            verifier.verify(make_token(claims={"sub": ""}))

    def test_a_token_with_no_kid_selects_no_key(self, verifier):
        with pytest.raises(OIDCError, match="no kid"):
            verifier.verify(make_token(header={"kid": ""}))

    def test_an_unknown_kid_is_refused_after_one_refetch(self, verifier):
        # On a cold cache the first fetch is the refetch: a key set fetched
        # during this call is not fetched again. See TestKeySetRefresh.
        with pytest.raises(OIDCError, match="no key with kid"):
            verifier.verify(make_token(kid="not-a-key"))

    def test_a_header_algorithm_that_disagrees_with_the_key_is_refused(self):
        """The key decides, not the token."""
        keyset = {"keys": [KEY.jwk(alg="RS512")]}
        v = OIDCVerifier(ISSUER, AUDIENCE, JWKSCache(JWKS_URL, fetcher=lambda u: keyset))
        with pytest.raises(OIDCError, match="the key decides"):
            v.verify(make_token(alg="RS256"))

    def test_a_malformed_token_is_refused(self, subtests, verifier):
        for bad in ("", "a.b", "a.b.c.d", "not-a-token", "....."):
            with subtests.test(token=bad):
                with pytest.raises(OIDCError):
                    verifier.verify(bad)

    def test_a_non_json_payload_is_refused(self, verifier):
        head = _b64u(json.dumps({"alg": "RS256", "kid": KID}).encode())
        with pytest.raises(OIDCError, match="not valid JSON"):
            verifier.verify(f"{head}.{_b64u(b'not json')}.{_b64u(b'sig')}")

    def test_no_supported_algorithm_is_symmetric_or_none(self):
        """The set is the allowlist; this pins what is in it."""
        assert "none" not in SUPPORTED_ALGORITHMS
        assert not any(a.startswith("HS") for a in SUPPORTED_ALGORITHMS)


# ---------------------------------------------------------------------------
# the key set
# ---------------------------------------------------------------------------


class TestJWKSCache:
    def test_keys_are_fetched_once_and_reused(self):
        calls = []
        cache = JWKSCache(JWKS_URL, fetcher=lambda u: calls.append(u) or {"keys": [KEY.jwk()]})
        cache.key(KID)
        cache.key(KID)
        assert len(calls) == 1, "a fetch per request makes the IdP a hard dependency"

    def test_an_unknown_kid_refetches_once_because_that_is_a_rotation(self):
        calls = []

        def fetcher(url):
            calls.append(url)
            return {"keys": [KEY.jwk(kid="rotated" if len(calls) > 1 else KID)]}

        cache = JWKSCache(JWKS_URL, fetcher=fetcher)
        cache.key(KID)
        assert cache.key("rotated")["kid"] == "rotated"
        assert len(calls) == 2

    def test_an_empty_key_set_is_an_error_not_an_empty_success(self):
        cache = JWKSCache(JWKS_URL, fetcher=lambda u: {"keys": []})
        with pytest.raises(OIDCError, match="declares no keys"):
            cache.key(KID)

    def test_a_key_set_with_no_kid_is_refused(self):
        cache = JWKSCache(JWKS_URL, fetcher=lambda u: {"keys": [{"kty": "RSA"}]})
        with pytest.raises(OIDCError, match="no key with a kid"):
            cache.key(KID)


# ---------------------------------------------------------------------------
# configuration, and the refusal that is not a fallback
# ---------------------------------------------------------------------------


class TestConfiguration:
    ENV = ("MAXEY0_JWT_ISSUER", "MAXEY0_JWT_AUDIENCE", "MAXEY0_JWKS_URL",
           "MAXEY0_AUTH_MODE", "MAXEY0_OIDC_ROLE_CLAIM")

    def _env(self, **over):
        base = {k: "" for k in self.ENV}
        base.update(over)
        return mock.patch.dict(os.environ, base)

    def test_missing_configuration_names_every_missing_variable(self):
        with self._env(MAXEY0_AUTH_MODE="oidc"):
            with pytest.raises(OIDCError) as exc:
                OIDCVerifier.from_config(AuthConfig.load({}))
        for name in ("MAXEY0_JWT_ISSUER", "MAXEY0_JWT_AUDIENCE", "MAXEY0_JWKS_URL"):
            assert name in str(exc.value)

    def test_oidc_mode_refuses_rather_than_falling_back(self):
        """A deployment that asked for OIDC must not silently get bearer."""
        with self._env(MAXEY0_AUTH_MODE="oidc"):
            authz = Authorizer(AuthConfig.load({}))
            with pytest.raises(AuthError) as exc:
                authz.principal("Bearer anything")
        assert exc.value.status == 501
        assert exc.value.code == -32004
        assert "not fall" in str(exc.value) or "rather than falling back" in str(exc.value)

    def test_a_configured_authorizer_accepts_a_valid_token(self):
        with self._env(MAXEY0_AUTH_MODE="oidc", MAXEY0_JWT_ISSUER=ISSUER,
                       MAXEY0_JWT_AUDIENCE=AUDIENCE, MAXEY0_JWKS_URL=JWKS_URL):
            authz = Authorizer(AuthConfig.load({}))
            authz._verifier = OIDCVerifier(
                ISSUER, AUDIENCE,
                JWKSCache(JWKS_URL, fetcher=lambda u: {"keys": [KEY.jwk()]}))
            principal = authz.principal(f"Bearer {make_token()}")
        assert principal.authenticated is True
        assert principal.subject == "user-1"

    def test_a_missing_header_is_a_401_not_a_500(self):
        with self._env(MAXEY0_AUTH_MODE="oidc", MAXEY0_JWT_ISSUER=ISSUER,
                       MAXEY0_JWT_AUDIENCE=AUDIENCE, MAXEY0_JWKS_URL=JWKS_URL):
            authz = Authorizer(AuthConfig.load({}))
            authz._verifier = OIDCVerifier(
                ISSUER, AUDIENCE, JWKSCache(JWKS_URL, fetcher=lambda u: {"keys": [KEY.jwk()]}))
            with pytest.raises(AuthError) as exc:
                authz.principal(None)
        assert exc.value.status == 401

    def test_the_refusal_reason_is_returned_and_carries_no_token(self):
        """A caller debugging an audience mismatch against a silent 401 opens
        a support ticket instead."""
        with self._env(MAXEY0_AUTH_MODE="oidc", MAXEY0_JWT_ISSUER=ISSUER,
                       MAXEY0_JWT_AUDIENCE=AUDIENCE, MAXEY0_JWKS_URL=JWKS_URL):
            authz = Authorizer(AuthConfig.load({}))
            authz._verifier = OIDCVerifier(
                ISSUER, AUDIENCE, JWKSCache(JWKS_URL, fetcher=lambda u: {"keys": [KEY.jwk()]}))
            token = make_token(claims={"aud": "elsewhere"})
            with pytest.raises(AuthError) as exc:
                authz.principal(f"Bearer {token}")
        assert "audience" in str(exc.value)
        assert token not in str(exc.value)

    def test_the_role_claim_is_configured_not_guessed(self):
        """Providers disagree about where a role lives; a guess grants wrongly."""
        with self._env(MAXEY0_OIDC_ROLE_CLAIM="realm_access.roles"):
            verified = OIDCVerifier(
                ISSUER, AUDIENCE,
                JWKSCache(JWKS_URL, fetcher=lambda u: {"keys": [KEY.jwk()]}),
            ).verify(make_token(claims={"realm_access": {"roles": ["operator"]}}))
            assert verified.role() == "operator"

    def test_no_configured_role_claim_means_the_least_privilege_default(self):
        with self._env():
            verified = OIDCVerifier(
                ISSUER, AUDIENCE,
                JWKSCache(JWKS_URL, fetcher=lambda u: {"keys": [KEY.jwk()]}),
            ).verify(make_token(claims={"roles": ["admin"]}))
            assert verified.role() == "viewer", (
                "an unconfigured role claim must not be guessed into admin"
            )

    def test_an_unknown_role_falls_back_to_viewer_not_wider(self):
        with self._env(MAXEY0_AUTH_MODE="oidc", MAXEY0_JWT_ISSUER=ISSUER,
                       MAXEY0_JWT_AUDIENCE=AUDIENCE, MAXEY0_JWKS_URL=JWKS_URL,
                       MAXEY0_OIDC_ROLE_CLAIM="groups"):
            authz = Authorizer(AuthConfig.load({}))
            authz._verifier = OIDCVerifier(
                ISSUER, AUDIENCE, JWKSCache(JWKS_URL, fetcher=lambda u: {"keys": [KEY.jwk()]}))
            principal = authz.principal(
                f"Bearer {make_token(claims={'groups': ['not-a-maxey0-role']})}")
        assert principal.role == "viewer"

    def test_the_manifest_now_reports_oidc_as_implemented(self):
        with self._env():
            assert Authorizer(AuthConfig.load({})).manifest()["oidc_implemented"] is True

    def test_under_oidc_the_mode_itself_is_reported_implemented(self):
        """`IMPLEMENTED_MODES` still said {disabled, bearer} after oidc shipped,
        so an oidc deployment reported `mode_implemented: false`."""
        with self._env(MAXEY0_AUTH_MODE="oidc", MAXEY0_JWT_ISSUER=ISSUER,
                       MAXEY0_JWT_AUDIENCE=AUDIENCE, MAXEY0_JWKS_URL=JWKS_URL):
            manifest = Authorizer(AuthConfig.load({})).manifest()
        assert manifest["mode"] == "oidc"
        assert manifest["mode_implemented"] is True
        assert "warning" not in manifest

    def test_under_oidc_the_verifier_settings_are_not_reported_inert(self):
        """The issuer every token is bound to was listed as unused under oidc."""
        with self._env(MAXEY0_AUTH_MODE="oidc", MAXEY0_JWT_ISSUER=ISSUER,
                       MAXEY0_JWT_AUDIENCE=AUDIENCE, MAXEY0_JWKS_URL=JWKS_URL,
                       MAXEY0_OIDC_ROLE_CLAIM="groups",
                       MAXEY0_OAUTH_CLIENT_ID="client-id",
                       MAXEY0_OAUTH_CLIENT_SECRET=""):
            inert = AuthConfig.load({}).inert_credentials()
        assert inert == ["client_id"], "only the client half is unused under oidc"

    def test_outside_oidc_the_verifier_settings_are_inert(self, subtests):
        for mode in ("disabled", "bearer", "not-a-mode"):
            with subtests.test(mode=mode):
                with self._env(MAXEY0_AUTH_MODE=mode, MAXEY0_JWT_ISSUER=ISSUER,
                               MAXEY0_JWT_AUDIENCE=AUDIENCE,
                               MAXEY0_JWKS_URL=JWKS_URL,
                               MAXEY0_OIDC_ROLE_CLAIM="groups",
                               MAXEY0_OAUTH_CLIENT_ID="",
                               MAXEY0_OAUTH_CLIENT_SECRET=""):
                    inert = AuthConfig.load({}).inert_credentials()
                assert inert == ["audience", "issuer", "jwks_url", "role_claim"]

    def test_an_empty_bearer_header_is_a_401_not_a_500(self):
        """`Bearer ` with nothing after it raised IndexError out of the split."""
        with self._env(MAXEY0_AUTH_MODE="oidc", MAXEY0_JWT_ISSUER=ISSUER,
                       MAXEY0_JWT_AUDIENCE=AUDIENCE, MAXEY0_JWKS_URL=JWKS_URL):
            authz = Authorizer(AuthConfig.load({}))
            authz._verifier = OIDCVerifier(
                ISSUER, AUDIENCE, JWKSCache(JWKS_URL, fetcher=lambda u: {"keys": [KEY.jwk()]}))
            for header in ("Bearer ", "Bearer    ", "bearer\t"):
                with pytest.raises(AuthError) as exc:
                    authz.principal(header)
                assert exc.value.status == 401


# ---------------------------------------------------------------------------
# token-derived input fails as OIDCError, and only as OIDCError
# ---------------------------------------------------------------------------


def _signed(claims_json: bytes, *, kid: str = KID) -> str:
    """A correctly signed token over a payload given as raw JSON bytes.

    Raw bytes because the payloads under test -- `NaN`, a 400-digit integer --
    are exactly the ones `json.dumps` would not produce from a dict.
    """
    head = _b64u(json.dumps({"alg": "RS256", "kid": kid}).encode())
    body = _b64u(claims_json)
    return f"{head}.{body}.{_b64u(KEY.sign(f'{head}.{body}'.encode()))}"


def _claims_with(exp: str) -> bytes:
    return (b'{"iss":"%s","aud":"%s","sub":"u","exp":%s}'
            % (ISSUER.encode(), AUDIENCE.encode(), exp.encode()))


class TestOnlyOIDCErrorEscapes:
    """A token is attacker bytes. Anything but OIDCError from verify() is a 500."""

    def _counting(self):
        calls = []

        def fetcher(url):
            calls.append(url)
            return {"keys": [KEY.jwk()]}

        return calls, OIDCVerifier(ISSUER, AUDIENCE, JWKSCache(JWKS_URL, fetcher=fetcher))

    def test_a_malformed_signature_segment_is_an_oidc_error(self, subtests):
        """It was `binascii.Error`: one base64url character decodes to nothing."""
        calls, verifier = self._counting()
        head, payload, _ = make_token().split(".")
        for bad in ("A", "AAAAA", "A=", "====", "!!!!", "éééé", "a+b/"):
            with subtests.test(signature=bad):
                with pytest.raises(OIDCError):
                    verifier.verify(f"{head}.{payload}.{bad}")
        assert calls == [], "a token with an undecodable signature must not select a key"

    def test_a_malformed_header_or_payload_segment_is_an_oidc_error(self, subtests):
        _, verifier = self._counting()
        head, payload, sig = make_token().split(".")
        for token in (f"A.{payload}.{sig}", f"{head}.A.{sig}",
                      f"{head}=.{payload}.{sig}", f"{head}.{payload}é.{sig}"):
            with subtests.test(token=token[:12]):
                with pytest.raises(OIDCError):
                    verifier.verify(token)

    def test_a_deeply_nested_payload_is_an_oidc_error_not_a_recursion_error(self):
        _, verifier = self._counting()
        head = _b64u(json.dumps({"alg": "RS256", "kid": KID}).encode())
        with pytest.raises(OIDCError, match="not valid JSON"):
            verifier.verify(f"{head}.{_b64u(b'[' * 20000)}.{_b64u(b'sig')}")

    def test_a_non_finite_exp_does_not_mean_never_expires(self, subtests):
        """`NaN` compares false against every clock, so it passed the check."""
        _, verifier = self._counting()
        for exp in ("NaN", "Infinity", "1e400", "9" * 400, "true", '"soon"'):
            with subtests.test(exp=exp[:10]):
                with pytest.raises(OIDCError):
                    verifier.verify(_signed(_claims_with(exp)))

    def test_a_malformed_signature_is_a_401_through_the_authorizer(self):
        with mock.patch.dict(os.environ, {
            "MAXEY0_AUTH_MODE": "oidc", "MAXEY0_JWT_ISSUER": ISSUER,
            "MAXEY0_JWT_AUDIENCE": AUDIENCE, "MAXEY0_JWKS_URL": JWKS_URL,
        }):
            authz = Authorizer(AuthConfig.load({}))
            _, authz._verifier = self._counting()
            head, payload, _ = make_token().split(".")
            with pytest.raises(AuthError) as exc:
                authz.principal(f"Bearer {head}.{payload}.A")
        assert exc.value.status == 401
        assert exc.value.code == -32001

    def test_an_unusable_key_is_an_oidc_error(self, subtests):
        """Key material that parses but cannot be used is the provider's fault,
        and still a refusal rather than a 500."""
        for jwk in ({**KEY.jwk(), "n": "AA"}, {**KEY.jwk(), "n": 12345},
                    {**KEY.jwk(), "e": ""}):
            with subtests.test(jwk={k: jwk[k] for k in ("n", "e")}):
                v = OIDCVerifier(ISSUER, AUDIENCE,
                                 JWKSCache(JWKS_URL, fetcher=lambda u, j=jwk: {"keys": [j]}))
                with pytest.raises(OIDCError):
                    v.verify(make_token())


# ---------------------------------------------------------------------------
# the key set: throttled, TTL-refreshed, stale-tolerant, thread-safe
# ---------------------------------------------------------------------------


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


class Fetcher:
    """Counts fetches; raises `fail` instead of answering when it is set."""

    def __init__(self, kids=(KID,)) -> None:
        self.calls = 0
        self.kids = list(kids)
        self.fail: BaseException | None = None

    def __call__(self, url):
        self.calls += 1
        if self.fail is not None:
            raise self.fail
        return {"keys": [KEY.jwk(kid=k) for k in self.kids]}


def _cache(fetcher, clock) -> JWKSCache:
    return JWKSCache(JWKS_URL, fetcher=fetcher, clock=clock)


class TestKeySetRefresh:
    def test_unknown_kids_cannot_force_a_fetch_per_request(self):
        """Five unknown-kid requests were six synchronous fetches."""
        fetcher, clock = Fetcher(), Clock()
        cache = _cache(fetcher, clock)
        cache.key(KID)
        for i in range(50):
            clock.t += 0.5
            with pytest.raises(OIDCError, match="no key with kid"):
                cache.key(f"made-up-{i}")
        # One initial fetch, one forced refresh; the other 49 are throttled.
        # 50 * 0.5 s = 25 s < the 30 s interval.
        assert fetcher.calls == 2

    def test_the_throttle_reopens_after_the_interval(self):
        fetcher, clock = Fetcher(), Clock()
        cache = _cache(fetcher, clock)
        cache.key(KID)
        with pytest.raises(OIDCError):
            cache.key("made-up")
        assert fetcher.calls == 2
        clock.t += 30
        fetcher.kids.append("rotated")
        assert cache.key("rotated")["kid"] == "rotated"
        assert fetcher.calls == 3

    def test_unknown_kid_tokens_through_the_verifier_are_bounded_too(self):
        """The attacker's view: a valid issuer string and made-up kids."""
        fetcher, clock = Fetcher(), Clock()
        verifier = OIDCVerifier(ISSUER, AUDIENCE, _cache(fetcher, clock))
        for i in range(20):
            with pytest.raises(OIDCError):
                verifier.verify(make_token(kid=f"made-up-{i}"))
        assert fetcher.calls <= 2

    def test_the_throttled_refusal_says_why(self):
        fetcher, clock = Fetcher(), Clock()
        cache = _cache(fetcher, clock)
        cache.key(KID)
        with pytest.raises(OIDCError):
            cache.key("a")
        with pytest.raises(OIDCError, match="at most once every 30 s"):
            cache.key("b")

    def test_the_ttl_still_refreshes(self):
        fetcher, clock = Fetcher(), Clock()
        cache = _cache(fetcher, clock)
        cache.key(KID)
        clock.t += cache.ttl_s - 1
        cache.key(KID)
        assert fetcher.calls == 1
        clock.t += 1
        fetcher.kids = ["rotated"]
        assert cache.key("rotated")["kid"] == "rotated"
        assert fetcher.calls == 2
        with pytest.raises(OIDCError):
            cache.key(KID)  # rotated out, and the forced refresh agrees

    def test_a_failed_refresh_serves_the_last_good_key_set(self, subtests):
        """An identity-provider blip must not become an authorization outage."""
        failures = (
            OIDCError("simulated"), OSError("connection refused"),
            TimeoutError("timed out"), urllib.error.URLError("dns"),
            http.client.RemoteDisconnected("gone"), ValueError("bad json"),
        )
        for failure in failures:
            with subtests.test(failure=type(failure).__name__):
                fetcher, clock = Fetcher(), Clock()
                cache = _cache(fetcher, clock)
                cache.key(KID)
                clock.t += cache.ttl_s + 1
                fetcher.fail = failure
                assert cache.key(KID)["kid"] == KID
                assert fetcher.calls == 2

    def test_a_failing_provider_is_retried_with_backoff_not_per_request(self):
        fetcher, clock = Fetcher(), Clock()
        cache = _cache(fetcher, clock)
        cache.key(KID)
        clock.t += cache.ttl_s + 1
        fetcher.fail = OSError("down")
        for _ in range(10):
            clock.t += 1
            cache.key(KID)
        assert fetcher.calls == 2, "a failed refresh must not be retried every request"
        clock.t += 30
        cache.key(KID)
        assert fetcher.calls == 3
        fetcher.fail = None
        clock.t += 30
        cache.key(KID)
        assert fetcher.calls == 4
        clock.t += 1
        cache.key(KID)
        assert fetcher.calls == 4, "a successful refresh resets to the TTL"

    def test_staleness_is_bounded(self):
        """A key nobody could confirm for a day may have been revoked."""
        fetcher, clock = Fetcher(), Clock()
        cache = _cache(fetcher, clock)
        cache.key(KID)
        fetcher.fail = OSError("down")
        clock.t += cache.max_stale_s - 1
        assert cache.key(KID)["kid"] == KID
        clock.t += 60
        with pytest.raises(OIDCError, match="staleness bound"):
            cache.key(KID)

    def test_no_key_set_at_all_is_an_oidc_error_and_backs_off(self):
        fetcher, clock = Fetcher(), Clock()
        fetcher.fail = OSError("down")
        cache = _cache(fetcher, clock)
        for _ in range(5):
            with pytest.raises(OIDCError, match="could not fetch JWKS"):
                cache.key(KID)
        assert fetcher.calls == 1
        clock.t += 30
        fetcher.fail = None
        assert cache.key(KID)["kid"] == KID
        assert fetcher.calls == 2

    def test_concurrent_requests_share_one_fetch(self):
        calls = []

        def slow(url):
            calls.append(url)
            time.sleep(0.05)
            return {"keys": [KEY.jwk()]}

        cache = JWKSCache(JWKS_URL, fetcher=slow)
        barrier = threading.Barrier(16)
        errors = []

        def worker():
            barrier.wait()
            try:
                cache.key(KID)
            except Exception as exc:  # pragma: no cover - reported below
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(16)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        assert len(calls) == 1

    def test_one_cache_per_url_for_the_process(self):
        """`api/app.py` builds an Authorizer per /v1 request. Each one got its
        own empty cache, so each such request was a fetch."""
        url = "https://shared.example.invalid/jwks.json"
        config = AuthConfig(mode="oidc", issuer=ISSUER, audience=AUDIENCE, jwks_url=url)
        try:
            first = OIDCVerifier.from_config(config)
            second = OIDCVerifier.from_config(config)
            assert first.jwks is second.jwks
            assert first.jwks is JWKSCache.shared(url)
            injected = OIDCVerifier.from_config(config, fetcher=lambda u: {})
            assert injected.jwks is not first.jwks, "a test fetcher gets its own"
        finally:
            from maxey0_ss.auth import oidc

            oidc._SHARED_CACHES.pop(url, None)


class _Response:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self, limit: int = -1) -> bytes:
        return self.body if limit < 0 else self.body[:limit]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestRealFetchFailuresAreOIDCErrors:
    """Only URLError and JSONDecodeError were caught; the rest escaped as 500s."""

    def _fetch(self, effect):
        cache = JWKSCache(JWKS_URL)
        with mock.patch("maxey0_ss.auth.oidc.urllib.request.urlopen", side_effect=effect):
            return cache._fetch()

    def test_network_failures(self, subtests):
        for exc in (TimeoutError("read timed out"), ConnectionResetError("reset"),
                    http.client.RemoteDisconnected("closed"),
                    http.client.IncompleteRead(b"par"),
                    urllib.error.URLError("no route"),
                    urllib.error.HTTPError(JWKS_URL, 503, "unavailable", {}, None),
                    ValueError("unknown url type")):
            with subtests.test(exc=type(exc).__name__):
                with pytest.raises(OIDCError, match="could not fetch JWKS"):
                    self._fetch(exc)

    def test_bad_bodies(self, subtests):
        for body, reason in ((b"<html>", "not JSON"), (b"\xff\xfe\x00", "not JSON"),
                             (b"[1, 2]", "not a JSON object"),
                             (b"[" * 5000, "not JSON"),
                             (b" " * (1 << 20) + b"{}", "larger than")):
            with subtests.test(reason=reason, size=len(body)):
                with pytest.raises(OIDCError, match=reason):
                    self._fetch(lambda *a, b=body, **k: _Response(b))

    def test_a_good_body_parses(self):
        document = self._fetch(
            lambda *a, **k: _Response(json.dumps({"keys": [KEY.jwk()]}).encode()))
        assert document["keys"][0]["kid"] == KID


# ---------------------------------------------------------------------------
# role mapping: configured, exact-key first, order-independent
# ---------------------------------------------------------------------------


class TestRoleMapping:
    NAMESPACED = "https://example.invalid/roles"

    def _verified(self, claims):
        v = OIDCVerifier(ISSUER, AUDIENCE,
                         JWKSCache(JWKS_URL, fetcher=lambda u: {"keys": [KEY.jwk()]}))
        return v.verify(make_token(claims=claims))

    def test_every_role_has_a_precedence(self):
        """A role added to ROLES without a place in PRECEDENCE is never chosen."""
        assert sorted(PRECEDENCE) == sorted(ROLES)
        assert PRECEDENCE[0] == "admin" and PRECEDENCE[-1] == "viewer"

    def test_a_namespaced_url_claim_is_found_by_exact_name(self):
        """A dotted-path walk splits `example.invalid` and finds nothing."""
        verified = self._verified({self.NAMESPACED: ["builder"]})
        assert verified.role(claim=self.NAMESPACED) == "builder"

    def test_a_top_level_dotted_key_cannot_override_the_nested_claim(self):
        """Exact-key lookup is for namespaced URLs only. A token carrying a
        top-level claim literally named `realm_access.roles` used to override
        the nested roles the deployment configured."""
        verified = self._verified({"realm_access.roles": "admin",
                                   "realm_access": {"roles": ["viewer"]}})
        assert verified.role(claim="realm_access.roles") == "viewer"
        alone = self._verified({"realm_access.roles": "admin"})
        assert alone.role(claim="realm_access.roles") == "viewer"  # the default

    def test_the_dotted_path_still_reaches_nested_claims(self):
        verified = self._verified({"realm_access": {"roles": ["operator"]}})
        assert verified.role(claim="realm_access.roles") == "operator"

    def test_a_list_resolves_to_the_most_privileged_role_in_either_order(self, subtests):
        """It was `value[0]`: the same person was admin or viewer by list order."""
        for groups in (["viewer", "admin"], ["admin", "viewer"],
                       ["operator", "builder", "viewer"], ["builder", "operator"]):
            with subtests.test(groups=groups):
                expected = next(r for r in PRECEDENCE if r in groups)
                assert self._verified({"groups": groups}).role(claim="groups") == expected
                reversed_ = self._verified({"groups": list(reversed(groups))})
                assert reversed_.role(claim="groups") == expected

    def test_unknown_entries_are_ignored_not_chosen(self, subtests):
        cases = (
            (["superuser", "operator", "staff"], "operator"),
            (["superuser"], "viewer"),
            ([{"role": "admin"}, 7, None, "builder"], "builder"),
            ([], "viewer"),
            ("superuser", "viewer"),
            ({"admin": True}, "viewer"),
        )
        for value, expected in cases:
            with subtests.test(value=value):
                assert self._verified({"groups": value}).role(claim="groups") == expected

    def test_the_authorizer_reads_the_claim_from_auth_config(self):
        """`AuthConfig.role_claim`, so the credentials file can supply it."""
        creds = {"oauth": {"role_claim": self.NAMESPACED}}
        with mock.patch.dict(os.environ, {
            "MAXEY0_AUTH_MODE": "oidc", "MAXEY0_JWT_ISSUER": ISSUER,
            "MAXEY0_JWT_AUDIENCE": AUDIENCE, "MAXEY0_JWKS_URL": JWKS_URL,
            "MAXEY0_OIDC_ROLE_CLAIM": "",
        }):
            config = AuthConfig.load(creds)
            assert config.role_claim == self.NAMESPACED
            authz = Authorizer(config)
            authz._verifier = OIDCVerifier(
                ISSUER, AUDIENCE, JWKSCache(JWKS_URL, fetcher=lambda u: {"keys": [KEY.jwk()]}))
            principal = authz.principal(
                f"Bearer {make_token(claims={self.NAMESPACED: ['viewer', 'builder']})}")
        assert principal.role == "builder"

    def test_an_explicit_claim_overrides_the_environment(self):
        verified = self._verified({"roles": ["admin"], "groups": ["viewer"]})
        with mock.patch.dict(os.environ, {"MAXEY0_OIDC_ROLE_CLAIM": "roles"}):
            assert verified.role() == "admin"
            assert verified.role(claim="groups") == "viewer"
