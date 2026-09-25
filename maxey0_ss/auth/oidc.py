"""OIDC bearer verification: JWKS, signature, claims, and issuer binding.

`MAXEY0_AUTH_MODE=oidc` refused with -32004/501 through 0.2.x and said why:
2026-07-28 requires RFC 9207 issuer validation and credentials bound to the
issuing authorization server, and refusing is better than accepting a token
nobody verified. This is the verification that refusal was waiting for, on the
side of the exchange this server is actually on.

**What RFC 9207 is actually for, and what this borrows from it.** RFC 9207 is a
*client* rule. Without it, an attacker who controls one authorization server
the client trusts can take an authorization code issued by a *different* server
and redeem it at theirs -- the client cannot tell which server answered,
because the response does not say. RFC 9207 makes the server name itself in the
authorization response, and makes the client check it. This module is a
resource server and never sees an authorization response, so it does not
implement RFC 9207 as such. It applies the resource-server analogue of the same
binding: a token is only good for the issuer it was minted by *and* the
audience it was minted for, and both are checked against configuration rather
than against the token's own claims.

That last clause is the whole point. A verifier that reads `iss` out of the
token and then fetches that issuer's keys will happily verify a token minted by
anybody, because the attacker chooses `iss`. The issuer here comes from
`MAXEY0_JWT_ISSUER`, the keys come from `MAXEY0_JWKS_URL`, and a token whose
`iss` disagrees is refused before a signature is computed.

**No PyJWT, and no `cryptography` on the RSA path.** RS256/384/512 is
RSASSA-PKCS1-v1_5 over a base64url-encoded JSON header and payload. Verifying it
is the public operation `pow(s, e, n)` and a comparison against the expected
encoded block, which Python integers, `hashlib` and `hmac.compare_digest`
cover, and that path always runs here in pure Python whether or not
`cryptography` is installed: nothing on the verifying side is secret, so there
is no timing channel a maintained library would be closing. ES256/ES384 are
different -- they need point arithmetic on a named curve, which is delegated to
the optional `cryptography` package rather than written here. The alternative
to this split is a hard dependency on a crypto stack for every install of this
package, including the ones that never enable OIDC.

**`alg: none` is refused, and so is any algorithm the key does not declare.**
The classic JWT failure is a verifier that reads the algorithm out of the token
and believes it. The algorithm comes from the *key*, and the token's header has
to match it.

**Everything the token controls fails as `OIDCError`.** A token is
attacker-supplied bytes, and any other exception escaping `verify()` reaches
the transport as a 500 rather than a 401 -- a malformed signature segment did
exactly that, as `binascii.Error`, and so did a payload of nested brackets deep
enough to exhaust the JSON parser's recursion limit.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import http.client
import json
import math
import os
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

from .roles import PRECEDENCE, ROLES

#: Algorithms this verifier will compute. `none` is absent on purpose and
#: `HS*` is absent on purpose: a symmetric algorithm verified against a JWKS
#: public key is the key-confusion attack, where an attacker signs with the
#: public key as an HMAC secret.
SUPPORTED_ALGORITHMS = frozenset({"RS256", "RS384", "RS512", "ES256", "ES384"})

#: Seconds of clock skew tolerated on `exp` and `nbf`. Small on purpose: this
#: is the window in which an expired token still works.
DEFAULT_LEEWAY_S = 60

#: How long a fetched key set is reused. A rotation is picked up within this.
DEFAULT_JWKS_TTL_S = 300

#: Fewest seconds between two key-set fetches forced by an unknown `kid`, and
#: between retries after a failed fetch. The unknown-kid refetch exists for key
#: rotation, but the `kid` is chosen by whoever sends the token and the only
#: thing checked before it is the issuer string, which is public. Unthrottled,
#: every such request was a synchronous outbound fetch: five requests, six
#: fetches, and the identity provider's rate limit spent on our behalf by
#: anybody. A real rotation is still picked up within this interval.
DEFAULT_JWKS_MIN_REFRESH_INTERVAL_S = 30

#: Longest a last-good key set keeps being served while refreshes fail. An
#: identity-provider blip must not become an authorization outage -- the keys
#: that verified tokens a minute ago still verify them -- but a key set nobody
#: has been able to confirm for a day may hold a key the provider has since
#: revoked, so the grace period is bounded.
DEFAULT_JWKS_MAX_STALENESS_S = 24 * 60 * 60

#: Largest key-set document read. A JWKS is a few kilobytes; this bounds what a
#: misbehaving endpoint can make every verifier process hold in memory.
MAX_JWKS_BYTES = 1 << 20

#: One compact-JWS segment: base64url, unpadded (RFC 7515 section 2).
_SEGMENT = re.compile(r"[A-Za-z0-9_-]*")


class OIDCError(Exception):
    """Verification failed. The message is safe to log and never carries a token."""


def _b64url_decode(segment: str) -> bytes:
    pad = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + pad)


def _b64url_uint(value: str) -> int:
    return int.from_bytes(_b64url_decode(value), "big")


def _segment(value: str, what: str) -> bytes:
    """Decode one token segment, or raise `OIDCError`.

    Strict, because `base64.urlsafe_b64decode` is not: it silently discards
    characters outside the alphabet, and raises `binascii.Error` -- a
    `ValueError`, not an `OIDCError` -- on a length no encoder produces. The
    second is how a one-character signature segment escaped `verify()` as a 500.
    """
    if not _SEGMENT.fullmatch(value) or len(value) % 4 == 1:
        raise OIDCError(f"token {what} is not unpadded base64url")
    try:
        return _b64url_decode(value)
    except (ValueError, binascii.Error) as exc:  # pragma: no cover - regex-guarded
        raise OIDCError(f"token {what} is not base64url: {exc}") from exc


def _json_object(raw: bytes, what: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (ValueError, RecursionError) as exc:
        # ValueError covers JSONDecodeError and a non-UTF-8 body. RecursionError
        # is a few kilobytes of `[`: the parser recurses per nesting level.
        raise OIDCError(f"token {what} is not valid JSON: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise OIDCError("token header and payload must be JSON objects")
    return value


def _clip(value: Any, limit: int = 64) -> str:
    """`repr` of a token-supplied value, bounded, for an error message."""
    text = repr(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


# ---------------------------------------------------------------------------
# key material
# ---------------------------------------------------------------------------


@dataclass
class JWKSCache:
    """A key set, when it was fetched, and when the next fetch may happen.

    Cached because a verifier that fetches the key set per request turns every
    authenticated call into an outbound HTTP request to the identity provider,
    and turns that provider into a hard dependency of every request path.

    Three refresh rules, all under one lock so concurrent requests produce one
    fetch rather than one each:

    - **TTL.** A key set older than `ttl_s` is refetched on the next request.
    - **Unknown kid.** A `kid` not in the set triggers a refetch, because that
      is exactly what a key rotation looks like -- but at most once per
      `min_refresh_interval_s`, because the `kid` is attacker-chosen.
    - **Failure.** A failed fetch keeps the previous set and serves it for up to
      `max_stale_s` after it was last confirmed, and the next attempt waits
      `min_refresh_interval_s`. A failed TTL refresh used to fail the request
      even though the keys in hand still verified it, which turned a provider
      blip into an outage; retrying on every request would turn an outage
      into a flood.

    Times come from `clock`, `time.monotonic` unless a test injects one, so a
    wall-clock step cannot expire or resurrect a key set.
    """

    url: str
    ttl_s: int = DEFAULT_JWKS_TTL_S
    _keys: dict[str, dict[str, Any]] = field(default_factory=dict)
    _fetched_at: float = 0.0
    #: Injected in tests. Real fetches go through urllib.
    fetcher: Any = None
    min_refresh_interval_s: float = DEFAULT_JWKS_MIN_REFRESH_INTERVAL_S
    max_stale_s: float = DEFAULT_JWKS_MAX_STALENESS_S
    clock: Callable[[], float] | None = None
    _forced_at: float | None = field(default=None, init=False, repr=False)
    _failed_at: float | None = field(default=None, init=False, repr=False)
    _last_error: str = field(default="", init=False, repr=False)
    _lock: Any = field(default_factory=threading.Lock, init=False, repr=False,
                       compare=False)

    @classmethod
    def shared(cls, url: str) -> "JWKSCache":
        """The process's one cache for `url`.

        `api/app.py` builds an `Authorizer` per /v1 request, and each one built
        its own verifier with its own empty cache: every such request was a
        fresh fetch, and the refresh throttle would have throttled nothing.
        Sharing by URL makes the cache -- and its rate limit -- a property of
        the process rather than of whichever object happened to ask.
        """
        with _SHARED_LOCK:
            cache = _SHARED_CACHES.get(url)
            if cache is None:
                cache = _SHARED_CACHES[url] = cls(url)
            return cache

    def _now(self) -> float:
        return (self.clock or time.monotonic)()

    #: What a fetch can raise short of a bug: every `urllib`/socket failure is
    #: an `OSError` (`URLError`, `TimeoutError`, `ConnectionResetError`), a
    #: malformed or truncated response is an `http.client.HTTPException`, and an
    #: unusable URL is a `ValueError`.
    _FETCH_FAILURES = (OSError, http.client.HTTPException, ValueError)

    def _download(self) -> bytes:
        request = urllib.request.Request(
            self.url, headers={"accept": "application/json"}, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=10.0) as response:
                body = response.read(MAX_JWKS_BYTES + 1)
        except urllib.error.HTTPError as exc:
            raise OIDCError(f"could not fetch JWKS from {self.url}: HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise OIDCError(f"could not fetch JWKS from {self.url}: {exc.reason}") from exc
        except self._FETCH_FAILURES as exc:
            raise OIDCError(
                f"could not fetch JWKS from {self.url}: {type(exc).__name__}: {exc}"
            ) from exc
        if len(body) > MAX_JWKS_BYTES:
            raise OIDCError(f"JWKS at {self.url} is larger than {MAX_JWKS_BYTES} bytes")
        return body

    def _fetch(self) -> dict[str, Any]:
        """One fetch of the key-set document. Every failure is an `OIDCError`.

        Only `URLError` and `JSONDecodeError` were caught before, so a read
        timeout (`TimeoutError`), a dropped connection
        (`http.client.RemoteDisconnected`) or a body that was not UTF-8 escaped
        as whatever it was, through `verify()`, as a 500.
        """
        if self.fetcher is not None:
            try:
                document = self.fetcher(self.url)
            except OIDCError:
                raise
            except self._FETCH_FAILURES as exc:
                raise OIDCError(
                    f"could not fetch JWKS from {self.url}: {type(exc).__name__}: {exc}"
                ) from exc
        else:
            body = self._download()
            try:
                document = json.loads(body.decode("utf-8"))
            except (ValueError, RecursionError) as exc:
                raise OIDCError(
                    f"JWKS at {self.url} is not JSON: {type(exc).__name__}") from exc
        if not isinstance(document, dict):
            raise OIDCError(f"JWKS at {self.url} is not a JSON object")
        return document

    def _parse(self, document: dict[str, Any]) -> dict[str, dict[str, Any]]:
        keys = document.get("keys")
        if not isinstance(keys, list) or not keys:
            raise OIDCError(f"JWKS at {self.url} declares no keys")
        parsed = {
            str(k.get("kid")): k for k in keys
            if isinstance(k, dict) and k.get("kid")
        }
        if not parsed:
            raise OIDCError(f"JWKS at {self.url} has no key with a kid")
        return parsed

    def _refresh_locked(self, now: float) -> None:
        """Fetch and install a key set; the caller holds `_lock`.

        On failure the previous key set stays installed, the failure is
        recorded for backoff and for the error a caller eventually sees, and
        the `OIDCError` propagates.
        """
        try:
            keys = self._parse(self._fetch())
        except OIDCError as exc:
            self._failed_at, self._last_error = now, str(exc)
            raise
        self._keys, self._fetched_at = keys, now
        self._failed_at, self._last_error = None, ""

    def refresh(self) -> None:
        """Fetch now, ignoring TTL and throttle. Raises `OIDCError` on failure."""
        with self._lock:
            self._refresh_locked(self._now())

    def _backing_off(self, now: float) -> bool:
        return (self._failed_at is not None
                and now - self._failed_at < self.min_refresh_interval_s)

    def _usable(self, now: float) -> dict[str, dict[str, Any]]:
        if self._keys and now - self._fetched_at <= self.max_stale_s:
            return self._keys
        return {}

    def key(self, kid: str) -> dict[str, Any]:
        with self._lock:
            now = self._now()
            refreshed = False
            due = not self._keys or now - self._fetched_at >= self.ttl_s
            if due and not self._backing_off(now):
                try:
                    self._refresh_locked(now)
                    refreshed = True
                except OIDCError:
                    pass  # the last good set, if still within max_stale_s, serves
            throttled = False
            if kid not in self._usable(now) and not refreshed:
                # A rotation -- or a caller probing with made-up kids. A key set
                # fetched during this call is as fresh as a second fetch would
                # be, and one that just failed is not retried until the backoff
                # expires.
                recently = (self._forced_at is not None
                            and now - self._forced_at < self.min_refresh_interval_s)
                if recently:
                    throttled = True
                elif not self._backing_off(now):
                    self._forced_at = now
                    try:
                        self._refresh_locked(now)
                    except OIDCError:
                        pass
            usable = self._usable(now)
            if kid in usable:
                return usable[kid]
            raise self._missing(kid, now, usable, throttled)

    def _missing(self, kid: str, now: float, usable: dict[str, Any],
                 throttled: bool) -> OIDCError:
        if not usable:
            if self._keys:
                return OIDCError(
                    f"the key set from {self.url} was last confirmed "
                    f"{int(now - self._fetched_at)} s ago, past the "
                    f"{int(self.max_stale_s)} s staleness bound, and it could "
                    f"not be refreshed: {self._last_error or 'retry pending'}"
                )
            return OIDCError(
                self._last_error or f"no key set could be fetched from {self.url}")
        message = (f"no key with kid {_clip(kid)} in the key set at {self.url}; "
                   f"it has {sorted(usable)}")
        if throttled:
            message += (f"; an unknown kid refreshes the key set at most once "
                        f"every {int(self.min_refresh_interval_s)} s")
        if self._last_error:
            message += f"; the last refresh failed: {self._last_error}"
        return OIDCError(message)


_SHARED_CACHES: dict[str, JWKSCache] = {}
_SHARED_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# signature
# ---------------------------------------------------------------------------

_HASHES = {"256": hashlib.sha256, "384": hashlib.sha384, "512": hashlib.sha512}

#: DigestInfo prefixes for RSASSA-PKCS1-v1_5. Fixed by RFC 8017.
_DIGEST_INFO = {
    "sha256": bytes.fromhex("3031300d060960864801650304020105000420"),
    "sha384": bytes.fromhex("3041300d060960864801650304020205000430"),
    "sha512": bytes.fromhex("3051300d060960864801650304020305000440"),
}

#: Bytes per coordinate for each ES curve. A JWS ECDSA signature is exactly
#: r || s at this width (RFC 7518 section 3.4), not DER.
_EC_COORDINATE_BYTES = {"256": 32, "384": 48}


def _verify_rs(signing_input: bytes, signature: bytes, jwk: dict[str, Any], bits: str) -> bool:
    """RSASSA-PKCS1-v1_5, by reconstructing the expected block.

    `pow(s, e, n)` is the public operation; there is no secret here, so a
    non-constant-time implementation leaks nothing an attacker does not have.
    """
    try:
        n, e = _b64url_uint(jwk["n"]), _b64url_uint(jwk["e"])
    except (KeyError, ValueError, TypeError) as exc:
        raise OIDCError(f"RSA key is malformed: {exc}") from exc
    if n < 2 or e < 2:
        raise OIDCError("RSA key is malformed: modulus or exponent out of range")
    size = (n.bit_length() + 7) // 8
    if len(signature) != size:
        return False
    digest = _HASHES[bits](signing_input).digest()
    prefix = _DIGEST_INFO[f"sha{bits}"]
    expected = b"\x00\x01" + b"\xff" * (size - len(prefix) - len(digest) - 3) \
        + b"\x00" + prefix + digest
    recovered = pow(int.from_bytes(signature, "big"), e, n).to_bytes(size, "big")
    return _constant_time_equals(recovered, expected)


def _verify_es(signing_input: bytes, signature: bytes, jwk: dict[str, Any], bits: str) -> bool:
    """ECDSA. Delegated, because a hand-rolled curve implementation is worse.

    Unlike the RSA path this needs point arithmetic on a named curve, and an
    implementation written here would be both slower and more likely wrong than
    the one in `cryptography`. A deployment using ES* installs it; one using
    RS* -- which is what every major identity provider issues -- does not.
    """
    try:
        from cryptography.hazmat.primitives import hashes as _h
        from cryptography.hazmat.primitives.asymmetric import ec, utils
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise OIDCError(
            "ES256/ES384 verification needs the optional 'cryptography' "
            "package. Install it, or configure an RS256 issuer."
        ) from exc
    if len(signature) != 2 * _EC_COORDINATE_BYTES[bits]:
        return False
    curves = {"256": ec.SECP256R1(), "384": ec.SECP384R1()}
    try:
        numbers = ec.EllipticCurvePublicNumbers(
            _b64url_uint(jwk["x"]), _b64url_uint(jwk["y"]), curves[bits])
        public = numbers.public_key()
    except (KeyError, ValueError, TypeError) as exc:
        raise OIDCError(f"EC key is malformed: {exc}") from exc
    half = len(signature) // 2
    der = utils.encode_dss_signature(
        int.from_bytes(signature[:half], "big"),
        int.from_bytes(signature[half:], "big"))
    algorithm = {"256": _h.SHA256(), "384": _h.SHA384()}[bits]
    try:
        public.verify(der, signing_input, ec.ECDSA(algorithm))
    except Exception:
        return False
    return True


def _constant_time_equals(a: bytes, b: bytes) -> bool:
    return hmac.compare_digest(a, b)


# ---------------------------------------------------------------------------
# verification
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VerifiedToken:
    """A token that passed every check. Claims only; the token is not retained."""

    subject: str
    issuer: str
    audience: str
    claims: dict[str, Any]
    algorithm: str
    key_id: str

    @property
    def scopes(self) -> tuple[str, ...]:
        raw = self.claims.get("scope") or ""
        if isinstance(raw, str):
            return tuple(s for s in raw.split() if s)
        if isinstance(raw, list):
            return tuple(str(s) for s in raw)
        return ()

    def _claim(self, name: str) -> Any:
        """The configured claim: a namespaced URL by exact key, anything else
        as a dotted path.

        Exact for a name containing `://` because the claim names identity
        providers recommend for custom roles are namespaced URLs --
        `https://example.invalid/roles` -- and a dotted-path walk splits those
        at every `.` in the hostname and finds nothing. Only for those: an
        exact lookup tried first for every name let a top-level claim literally
        named `realm_access.roles` override the nested one the operator
        configured, and whoever can add a top-level claim is not necessarily
        whoever controls `realm_access`.
        """
        if "://" in name:
            return self.claims.get(name)
        value: Any = self.claims
        for part in name.split("."):
            if not isinstance(value, dict):
                return None
            value = value.get(part)
        return value

    def role(self, default: str = "viewer", claim: str | None = None) -> str:
        """The role this token asserts, from the claim a deployment nominates.

        Read from a *configured* claim name rather than a guessed one. Identity
        providers disagree about where a role lives -- `roles`, `groups`,
        `realm_access.roles`, a namespaced custom claim -- and a verifier that
        guesses will silently pick the wrong one and grant the wrong access.

        `claim` is `AuthConfig.role_claim`, passed by the authorizer. Without
        it, `MAXEY0_OIDC_ROLE_CLAIM` is read directly, which is what callers
        holding a bare `VerifiedToken` relied on before the setting moved into
        `AuthConfig`.

        A list resolves to the most privileged role in it that this build knows
        (`roles.PRECEDENCE`). It used to be `value[0]`, so the same token for
        the same person granted `viewer` or `admin` depending on the order the
        provider serialized a group list -- which providers do not promise.
        Unknown names are skipped rather than allowed to shadow a known one,
        and a claim naming no known role yields `default`.
        """
        name = (claim if claim is not None
                else os.environ.get("MAXEY0_OIDC_ROLE_CLAIM", "")).strip()
        if not name:
            return default
        value = self._claim(name)
        presented = [value] if isinstance(value, str) else (
            value if isinstance(value, list) else [])
        known = {v for v in presented if isinstance(v, str) and v in ROLES}
        for role in PRECEDENCE:
            if role in known:
                return role
        return default


@dataclass
class OIDCVerifier:
    """Verifies a bearer token against one configured issuer.

    Every trust decision comes from configuration, never from the token:

    - the **issuer** is `MAXEY0_JWT_ISSUER`, and a token claiming another is
      refused before any signature is computed;
    - the **keys** come from `MAXEY0_JWKS_URL`, not from an `iss`-derived
      discovery document, because an attacker chooses `iss`;
    - the **audience** is `MAXEY0_JWT_AUDIENCE`, and a token minted for another
      relying party is refused even when its signature is perfectly valid --
      the confused-deputy case. RFC 9207 closes the client-side counterpart of
      this (a response from the wrong authorization server); the audience check
      is how a resource server refuses a token that was never meant for it.
    """

    issuer: str
    audience: str
    jwks: JWKSCache
    leeway_s: int = DEFAULT_LEEWAY_S

    @classmethod
    def from_config(cls, config: Any, *, fetcher: Any = None) -> "OIDCVerifier":
        missing = [
            name for name, value in (
                ("MAXEY0_JWT_ISSUER", config.issuer),
                ("MAXEY0_JWT_AUDIENCE", config.audience),
                ("MAXEY0_JWKS_URL", config.jwks_url),
            ) if not value
        ]
        if missing:
            raise OIDCError(
                "MAXEY0_AUTH_MODE=oidc needs " + ", ".join(missing) +
                ". Without an issuer and an audience there is nothing to bind "
                "a token to, and without a key set there is nothing to verify "
                "it with."
            )
        return cls(
            issuer=config.issuer,
            audience=config.audience,
            jwks=(JWKSCache(config.jwks_url, fetcher=fetcher) if fetcher is not None
                  else JWKSCache.shared(config.jwks_url)),
        )

    def verify(self, token: str, *, now: float | None = None) -> VerifiedToken:
        """Every check, or `OIDCError`. No other exception leaves this method."""
        now = time.time() if now is None else now
        parts = token.strip().split(".")
        if len(parts) != 3:
            raise OIDCError("token is not a three-part JWS")
        header_b64, payload_b64, signature_b64 = parts

        header = _json_object(_segment(header_b64, "header"), "header")
        claims = _json_object(_segment(payload_b64, "payload"), "payload")

        algorithm = str(header.get("alg", ""))
        if algorithm not in SUPPORTED_ALGORITHMS:
            # Covers `none`, and covers HS* signed with the public key.
            raise OIDCError(
                f"algorithm {_clip(algorithm)} is not accepted; this verifier "
                f"computes {sorted(SUPPORTED_ALGORITHMS)}"
            )

        # Issuer before signature. The key set is ours, not the token's, so a
        # token from another issuer must not even select a key.
        if str(claims.get("iss", "")) != self.issuer:
            raise OIDCError(
                f"token issuer {_clip(claims.get('iss'))} is not the configured "
                f"issuer. This is the resource-server analogue of RFC 9207's "
                f"issuer binding, and it is checked against configuration "
                f"rather than against the token"
            )

        kid = str(header.get("kid", ""))
        if not kid:
            raise OIDCError("token header carries no kid, so no key selects it")
        signature = _segment(signature_b64, "signature")
        jwk = self.jwks.key(kid)

        # The algorithm comes from the key, not the token.
        key_alg = str(jwk.get("alg") or "")
        if key_alg and key_alg != algorithm:
            raise OIDCError(
                f"token declares {algorithm!r} but key {_clip(kid)} declares "
                f"{key_alg!r}; the key decides"
            )
        kty, bits = str(jwk.get("kty", "")), algorithm[2:]
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")

        try:
            if algorithm.startswith("RS"):
                if kty != "RSA":
                    raise OIDCError(f"key {_clip(kid)} is {kty!r}, not RSA")
                ok = _verify_rs(signing_input, signature, jwk, bits)
            else:
                if kty != "EC":
                    raise OIDCError(f"key {_clip(kid)} is {kty!r}, not EC")
                ok = _verify_es(signing_input, signature, jwk, bits)
        except OIDCError:
            raise
        except (ValueError, TypeError, ArithmeticError) as exc:
            # Key material from the identity provider that parsed but cannot be
            # used -- refused as a verification failure, not surfaced as a 500.
            raise OIDCError(
                f"signature could not be checked against key {_clip(kid)}: "
                f"{type(exc).__name__}"
            ) from exc
        if not ok:
            raise OIDCError("signature does not verify")

        self._check_claims(claims, now)
        return VerifiedToken(
            subject=str(claims.get("sub", "")),
            issuer=self.issuer,
            audience=self.audience,
            claims=claims,
            algorithm=algorithm,
            key_id=kid,
        )

    @staticmethod
    def _numeric_date(claims: dict[str, Any], name: str) -> float | None:
        """`exp`/`nbf` as a finite number, or None when absent.

        Finite matters: Python's JSON parser accepts `NaN` and `Infinity`, and
        every comparison against NaN is false, so `"exp": NaN` passed the
        expiry check forever.
        """
        value = claims.get(name)
        if value is None:
            return None
        if isinstance(value, bool):
            raise OIDCError(f"{name} is not a number")
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise OIDCError(f"{name} is not a number: {exc}") from exc
        if not math.isfinite(number):
            raise OIDCError(f"{name} is not a finite number")
        return number

    def _check_claims(self, claims: dict[str, Any], now: float) -> None:
        audience = claims.get("aud")
        accepted = (
            [audience] if isinstance(audience, str)
            else list(audience) if isinstance(audience, list) else []
        )
        if self.audience not in accepted:
            raise OIDCError(
                f"token audience {_clip(audience)} does not include the "
                f"configured audience; a token minted for another relying party "
                f"is not a token for this one, however valid its signature"
            )
        exp = self._numeric_date(claims, "exp")
        if exp is None:
            raise OIDCError("token carries no exp; a bearer with no expiry is a password")
        if now > exp + self.leeway_s:
            raise OIDCError("token has expired")
        nbf = self._numeric_date(claims, "nbf")
        if nbf is not None and now < nbf - self.leeway_s:
            raise OIDCError("token is not valid yet")
        if not claims.get("sub"):
            raise OIDCError("token carries no sub, so it identifies nobody")
