"""Capability-based admission for the Maxey0 MCP surface.

Every tool declares the capability it requires. A tool with `capability=None` is
public; anything else needs a principal that holds it. This is what stops
`scw.create` and the gate-mode writes being world-callable the moment an origin
is reachable from the edge.

Modes, from `MAXEY0_AUTH_MODE`:

``disabled`` (default)
    Trusted local deployment — stdio on a developer machine, or the API bound to
    localhost. Every request is admin. This is the historical behavior and is
    kept so a local install keeps working.

``bearer``
    `Authorization: Bearer <token>` matched against configured tokens, each
    mapped to a role. `MAXEY0_MCP_TOKEN_HASHES` holds per-caller tokens as
    SHA-256 digests with a label (`scripts/mint_token.py` mints them);
    `MAXEY0_MCP_TOKENS` and the default bearer token are still accepted in
    plaintext so an existing deployment keeps working. A malformed entry
    refuses every request with -32004/501, naming the variable and the entry —
    it is not skipped.

``oidc``
    `Authorization: Bearer <JWT>` verified against a configured issuer, audience
    and JWKS. Every trust decision comes from configuration rather than from the
    token: an attacker chooses `iss`, so a verifier that fetches keys from the
    issuer the token names verifies tokens minted by anybody. See
    `maxey0_ss.auth.oidc`. Misconfiguration refuses with -32004/501 and names
    the missing variable — it does not fall back to a weaker mode.

Any other value — a typo included — refuses every request with -32004/501. It
used to fall through to ``disabled``, so a misspelt ``bearer`` on a deployment
without ``MAXEY0_PUBLIC=1`` made every caller admin.

Fail-closed switch: set ``MAXEY0_PUBLIC=1`` on any deployment reachable from the
internet. With it set, ``disabled`` no longer grants admin; unauthenticated
callers get the public capability set only.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
from dataclasses import dataclass

from .config import AuthConfig, normalize_mode
from .roles import ROLES, allowed

#: Capability required to read observability. Everything about what agents did.
OBSERVE_READ = "observe"
#: Capability required to read application state (SCW specs and instances).
SCW_READ = "scw.read"
#: Capability required to create an SCW specification.
SCW_CREATE = "scw.create"
#: Capability required to close an instantiated SCW.
SCW_ADMIT = "scw.admit"
#: Capability required to CHANGE the gate. Admin only by construction: no role
#: in `roles.ROLES` holds it except admin's wildcard. Turning the gate off is
#: the single most destructive operation on this surface.
GATE_WRITE = "gate.write"

#: Raised when `oidc` is selected and cannot be configured. It is deliberately
#: not a fallback: a deployment that asked for OIDC and silently got `bearer`
#: -- or worse, `disabled` -- would be a deployment that believes it has
#: identity-provider-backed auth and has a shared secret, or nothing.
OIDC_MISCONFIGURED = (
    "MAXEY0_AUTH_MODE=oidc is declared but not configured. This refuses rather "
    "than falling back to a weaker mode, because a deployment that asked for "
    "OIDC and silently got bearer would believe it had identity-provider-backed "
    "authorization when it had a shared secret."
)

#: Raised in `bearer` mode while any token entry is invalid. Same stance as
#: `OIDC_MISCONFIGURED`: serving from the entries that did parse is a guess
#: about what the operator meant.
BEARER_MISCONFIGURED = (
    "MAXEY0_AUTH_MODE=bearer is declared but its token configuration is "
    "invalid. Every request is refused rather than served from the entries "
    "that parsed: a skipped entry is a caller locked out without a word, and a "
    "repeated one is a caller whose role depends on which copy was read."
)

#: Per-caller tokens, stored as `sha256:<64 lowercase hex>:<role>:<label>`.
TOKEN_HASHES_VAR = "MAXEY0_MCP_TOKEN_HASHES"
#: Plaintext `token:role` pairs. Accepted so existing deployments keep working.
PLAINTEXT_TOKENS_VAR = "MAXEY0_MCP_TOKENS"
#: One shared plaintext token, mapped to `operator`.
DEFAULT_TOKEN_VAR = "MAXEY0_MCP_DEFAULT_BEARER_TOKEN"

#: What a hashed token's label may be. It becomes `Principal.subject`, so it is
#: restricted to characters that are safe in a log line and a file name.
LABEL_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,64}")
_HEX_DIGEST = re.compile(r"[0-9a-f]{64}")
#: What a digest looks like when it is pasted where a token belongs: bare, or
#: with the `sha256:` prefix, in either case. Case-insensitive because the
#: mistake is copying a value, and an upper-cased copy is still that mistake.
_DIGEST_SHAPED = re.compile(r"(?:sha256:)?[0-9a-f]{64}", re.IGNORECASE)

#: The placeholders `.env.example` ships (`<BEARER_TOKEN>`, `<API_KEY>`) and the
#: older REPLACE_ME family. Deliberately narrower than providers' is_placeholder,
#: which also matches `xxxx` -- a string a real random token can contain, and a
#: false match here would lock a real user out.
_PLACEHOLDER_SECRET = re.compile(r"^<[A-Za-z0-9_]+>$|replace[_-]?me|placeholder|changeme",
                                 re.IGNORECASE)


def is_placeholder_secret(value: str | None) -> bool:
    """A credential still set to a template value. Never a working secret."""
    return bool(value and _PLACEHOLDER_SECRET.search(value.strip()))


class AuthError(PermissionError):
    """Raised when a principal may not invoke a capability."""

    def __init__(self, message: str, *, code: int = -32002, status: int = 403) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class Principal:
    """Who is calling, and what they may do."""

    role: str
    subject: str = "anonymous"
    authenticated: bool = False

    def may(self, capability: str | None) -> bool:
        if capability is None:
            return True  # public tool
        return allowed(self.role, capability)


#: Unauthenticated caller on a public deployment. Public tools only.
ANONYMOUS = Principal(role="public", subject="anonymous", authenticated=False)
#: Trusted local caller.
LOCAL_ADMIN = Principal(role="admin", subject="local", authenticated=True)


# ---------------------------------------------------------------------------
# bearer tokens
# ---------------------------------------------------------------------------


def _sha256(token: str) -> bytes:
    # surrogatepass: lossless for any `str`, so no two distinct tokens encode
    # to the same bytes and no header value can make hashing raise.
    return hashlib.sha256(token.encode("utf-8", "surrogatepass")).digest()


def token_digest(token: str) -> str:
    """Hex SHA-256 of a bearer token, as `MAXEY0_MCP_TOKEN_HASHES` stores it.

    A fast hash rather than a password hash on purpose. A minted token carries
    256 bits of randomness, so there is no dictionary for scrypt or argon2 to
    slow down, and a verifier that spent tens of milliseconds per request on a
    deliberately slow hash would hand every unauthenticated caller a
    denial-of-service lever. What the digest buys is that a leaked `.env` is no
    longer a working credential.
    """
    return _sha256(token).hex()


def token_hash_entry(token: str, role: str, label: str) -> str:
    """The `MAXEY0_MCP_TOKEN_HASHES` entry for a token. The format, in one place."""
    return f"sha256:{token_digest(token)}:{role}:{label}"


@dataclass(frozen=True)
class BearerCredential:
    """One accepted token, by digest. The token itself is not retained."""

    digest: bytes
    role: str
    #: Never token material: `bearer:<label>`, `bearer:default`, or
    #: `bearer:sha256:<12 hex>` for a plaintext entry. It used to be the first
    #: six characters of the token, which put a sixth of a short token into
    #: every log line and attestation that recorded who called.
    subject: str
    hashed: bool


def _entries(raw: str) -> list[tuple[int, str]]:
    """(position counting from 1, entry) for each non-empty comma-separated entry.

    Positions count empty entries too, so the number in an error is where the
    entry sits in the variable, not where it sits among the ones that parsed.
    """
    return [(i, e.strip()) for i, e in enumerate(raw.split(","), 1) if e.strip()]


@dataclass(frozen=True)
class BearerTokens:
    """Every bearer credential this deployment accepts, parsed once.

    Plaintext entries are digested at parse time, so matching is the same
    operation for every source: hash what was presented, compare it against
    every configured digest with `hmac.compare_digest`, and never stop early.
    The dictionary lookup this replaced answered in time that depended on the
    presented token's hash and on how much of it matched a stored key.

    `errors` name a variable and an entry position and never the entry: the
    message reaches unauthenticated callers as the body of the 501.
    """

    credentials: tuple[BearerCredential, ...] = ()
    errors: tuple[str, ...] = ()

    @classmethod
    def load(cls, default_token: str = "") -> "BearerTokens":
        credentials: list[BearerCredential] = []
        errors: list[str] = []
        seen: dict[bytes, str] = {}
        labels: dict[str, int] = {}
        role_names = ", ".join(sorted(ROLES))

        for index, entry in _entries(os.getenv(TOKEN_HASHES_VAR, "")):
            where = f"{TOKEN_HASHES_VAR} entry {index}"
            parts = [p.strip() for p in entry.split(":")]
            if len(parts) != 4 or parts[0] != "sha256":
                errors.append(f"{where} is not sha256:<64 lowercase hex>:<role>:<label>")
                continue
            _, digest_hex, role, label = parts
            if not _HEX_DIGEST.fullmatch(digest_hex):
                errors.append(f"{where}: the digest is not 64 lowercase hex characters")
                continue
            if role not in ROLES:
                errors.append(f"{where}: the role is not one of {role_names}")
                continue
            if not LABEL_PATTERN.fullmatch(label):
                errors.append(f"{where}: the label is not 1-64 of A-Z a-z 0-9 . _ -")
                continue
            if label in labels:
                errors.append(f"{where} repeats the label of entry {labels[label]}")
                continue
            digest = bytes.fromhex(digest_hex)
            if digest in seen:
                errors.append(f"{where} repeats the digest of {seen[digest]}")
                continue
            labels[label], seen[digest] = index, where
            credentials.append(BearerCredential(digest, role, f"bearer:{label}", True))

        for index, entry in _entries(os.getenv(PLAINTEXT_TOKENS_VAR, "")):
            where = f"{PLAINTEXT_TOKENS_VAR} entry {index}"
            # rpartition: a role never contains ':', a token might.
            token, sep, role = (p.strip() for p in entry.rpartition(":"))
            if not sep or not token or not role:
                errors.append(f"{where} is not <token>:<role>")
                continue
            if role not in ROLES:
                # It used to be accepted as-is: a principal holding a role no
                # table defines, authenticated and able to do nothing, with no
                # indication the entry was wrong.
                errors.append(f"{where}: the role is not one of {role_names}")
                continue
            if is_placeholder_secret(token):
                errors.append(f"{where} is still the {token!r} placeholder from "
                              f".env.example; put a real token there or remove the entry")
                continue
            if _DIGEST_SHAPED.fullmatch(token):
                # A digest pasted into the plaintext variable -- the move to
                # hashes done in the wrong variable -- used to be accepted as a
                # token. The digest, the value meant to be safe to leak, then
                # became the working credential.
                errors.append(f"{where} is a sha256 digest, not a token; digests "
                              f"belong in {TOKEN_HASHES_VAR} as "
                              f"sha256:<64 lowercase hex>:<role>:<label>")
                continue
            digest = _sha256(token)
            if digest in seen:
                errors.append(f"{where} is the same token as {seen[digest]}")
                continue
            seen[digest] = where
            credentials.append(BearerCredential(
                digest, role, f"bearer:sha256:{digest.hex()[:12]}", False))

        if default_token and is_placeholder_secret(default_token):
            # Left as shipped in .env.example. Accepting it would make the
            # literal text `<BEARER_TOKEN>` a working operator credential that
            # anyone who has read the example file could send.
            errors.append(f"{DEFAULT_TOKEN_VAR} is still the {default_token!r} placeholder "
                          f"from .env.example; set a real token or leave it empty")
        elif default_token:
            digest = _sha256(default_token)
            # An explicit entry for the same token keeps its role, as it did
            # when this was `mapping.setdefault(default, "operator")`.
            if digest not in seen:
                credentials.append(
                    BearerCredential(digest, "operator", "bearer:default", False))
        return cls(tuple(credentials), tuple(errors))

    @property
    def hashed(self) -> int:
        return sum(1 for c in self.credentials if c.hashed)

    @property
    def plaintext(self) -> int:
        return len(self.credentials) - self.hashed

    @property
    def storage(self) -> str:
        if self.hashed and self.plaintext:
            return "mixed"
        if self.hashed:
            return "hashed"
        return "plaintext" if self.plaintext else "none"

    def match(self, token: str) -> BearerCredential | None:
        presented = _sha256(token)
        found: BearerCredential | None = None
        for credential in self.credentials:
            # compare_digest runs for every entry; `found is None` is evaluated
            # after it, so a match does not shorten the loop.
            if hmac.compare_digest(presented, credential.digest) and found is None:
                found = credential
        return found


def _bearer_credential(authorization: str | None) -> str:
    """The token from an `Authorization: Bearer` header, or a 401.

    `Bearer ` with nothing after it raised IndexError out of `split(None, 1)[1]`
    in both bearer and oidc mode: a 500 for a malformed header.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthError("Bearer credentials required", code=-32001, status=401)
    parts = authorization.split(None, 1)
    token = parts[1].strip() if len(parts) == 2 else ""
    if not token:
        raise AuthError("Bearer credentials required", code=-32001, status=401)
    return token


def _unknown_mode(mode: str) -> str:
    shown = repr(mode) if len(mode) <= 40 else repr(mode[:37] + "...")
    return (
        f"MAXEY0_AUTH_MODE={shown} is not a mode this build implements "
        f"({', '.join(sorted(AuthConfig.IMPLEMENTED_MODES))}). Every request is "
        f"refused rather than read as the default, because a misspelt mode that "
        f"fell through to `disabled` made every caller admin on a deployment "
        f"without MAXEY0_PUBLIC=1."
    )


def is_public_deployment() -> bool:
    return os.getenv("MAXEY0_PUBLIC", "").strip().lower() in {"1", "true", "yes", "on"}


class Authorizer:
    """Resolves a request's credentials to a `Principal`."""

    def __init__(self, config: AuthConfig | None = None) -> None:
        # `load` rather than `from_env`: credentials supplied in
        # config/credentials.json's `mcp` and `oauth` sections had no reader at
        # all before 0.2.0, so an operator who followed the documented setup
        # configured nothing and was not told.
        self.config = config or AuthConfig.load()
        self.public_deployment = is_public_deployment()
        self._verifier = None
        self._tokens: BearerTokens | None = None

    @property
    def mode(self) -> str:
        return normalize_mode(self.config.mode)

    @property
    def mode_implemented(self) -> bool:
        return self.mode in AuthConfig.IMPLEMENTED_MODES

    def tokens(self) -> BearerTokens:
        """The bearer credentials, parsed on first use and kept.

        Once per `Authorizer` rather than once per request, which is also once
        per request's worth of SHA-256 over every plaintext entry. Lazily, like
        `verifier()`, so building an `Authorizer` for a mode that uses no
        tokens never parses them.

        `config` carries the resolved default token, which matters because
        `AuthConfig.load` accepts it from `config/credentials.json` as well as
        from the environment. Reading `MAXEY0_MCP_DEFAULT_BEARER_TOKEN` directly
        meant a token supplied in the credentials file was loaded, reported, and
        then rejected at the door.
        """
        if self._tokens is None:
            default = (self.config.default_bearer_token
                       or os.getenv(DEFAULT_TOKEN_VAR, "")).strip()
            self._tokens = BearerTokens.load(default)
        return self._tokens

    def principal(self, authorization: str | None) -> Principal:
        mode = self.mode

        if not self.mode_implemented:
            raise AuthError(_unknown_mode(mode), code=-32004, status=501)

        if mode == "oidc":
            return self._oidc_principal(authorization)

        if mode == "bearer":
            return self._bearer_principal(authorization)

        # disabled
        if self.public_deployment:
            # Reachable from the internet with no auth configured: public tools
            # only. Refusing here is the difference between an open surface and
            # a read-only one.
            return ANONYMOUS
        return LOCAL_ADMIN

    # -- bearer -------------------------------------------------------------

    def _bearer_principal(self, authorization: str | None) -> Principal:
        tokens = self.tokens()
        if tokens.errors:
            raise AuthError(f"{BEARER_MISCONFIGURED} {'; '.join(tokens.errors)}.",
                            code=-32004, status=501)
        credential = tokens.match(_bearer_credential(authorization))
        if credential is None:
            raise AuthError("Invalid bearer credentials", code=-32001, status=401)
        return Principal(role=credential.role, subject=credential.subject,
                         authenticated=True)

    # -- oidc ---------------------------------------------------------------

    def verifier(self):
        """The configured verifier, built once.

        Built lazily rather than in `__init__` so that constructing an
        `Authorizer` on a deployment that does not use OIDC never touches
        identity-provider configuration, and so a configuration error surfaces
        on the first authenticated request with a message naming the variable,
        rather than at import.
        """
        if self._verifier is None:
            from .oidc import OIDCError, OIDCVerifier

            try:
                self._verifier = OIDCVerifier.from_config(self.config)
            except OIDCError as exc:
                raise AuthError(f"{OIDC_MISCONFIGURED} {exc}",
                                code=-32004, status=501) from exc
        return self._verifier

    def _oidc_principal(self, authorization: str | None) -> Principal:
        from .oidc import OIDCError

        verifier = self.verifier()
        token = _bearer_credential(authorization)
        try:
            verified = verifier.verify(token)
        except OIDCError as exc:
            # The reason is safe to return: it never carries the token, and a
            # caller debugging an audience mismatch against a silent 401 is a
            # caller who opens a support ticket instead.
            raise AuthError(f"Invalid bearer credentials: {exc}",
                            code=-32001, status=401) from exc
        role = verified.role(default="viewer", claim=self.config.role_claim or None)
        if role not in ROLES:
            # An unknown role is not an error in the token, it is a mapping the
            # deployment has not made. Falling back to `viewer` rather than
            # refusing keeps a new group from locking everyone out; falling back
            # to anything wider would be the opposite mistake.
            role = "viewer"
        return Principal(role=role, subject=verified.subject, authenticated=True)

    def authorize(self, principal: Principal, capability: str | None, tool_name: str) -> None:
        if principal.may(capability):
            return
        raise AuthError(
            f"{tool_name} requires capability {capability!r}; "
            f"role {principal.role!r} does not hold it",
            code=-32002,
            status=403,
        )

    @property
    def admin_open(self) -> bool:
        """Every caller, authenticated or not, is admin on this deployment.

        True exactly when `MAXEY0_AUTH_MODE=disabled` and `MAXEY0_PUBLIC` is
        unset. That is the correct default for stdio on a developer machine and
        a critical finding on anything internet-reachable: the edge adapter
        performs no authorization by design and forwards `authorization`
        verbatim, so composed with an admin-open origin it is unauthenticated
        admin over the internet.

        It was computable before 0.2.0 and computed nowhere. `Authorizer.
        manifest()` had one caller, a test, while `maxey0-ss.auth.manifest`
        returned `AuthConfig.public_manifest()`, which does not contain it — so
        the single fact the deployment checklist turns on could not be read from
        the surface that exists to report it.
        """
        return self.mode == "disabled" and not self.public_deployment

    def manifest(self) -> dict[str, object]:
        base = self.config.public_manifest()
        base["public_deployment"] = self.public_deployment
        base["enforced"] = self.mode != "disabled" or self.public_deployment
        base["oidc_implemented"] = True
        base["admin_open"] = self.admin_open
        base["anonymous_role"] = (
            ANONYMOUS.role if (self.public_deployment or self.mode != "disabled")
            else LOCAL_ADMIN.role
        )
        # Counts only. `auth.manifest` is a public tool, so a label (who can
        # call) or a digest (an offline guessing target for a weak token) here
        # would make `credential_values_exposed: false` a lie.
        tokens = self.tokens()
        base["token_storage"] = tokens.storage
        base["bearer_tokens"] = {"hashed": tokens.hashed, "plaintext": tokens.plaintext}
        base["token_config_errors"] = len(tokens.errors)

        warnings: list[str] = []
        if self.admin_open:
            warnings.append(
                "MAXEY0_AUTH_MODE=disabled and MAXEY0_PUBLIC is unset, so every "
                "caller is admin. Correct for a trusted local deployment. On "
                "anything internet-reachable set MAXEY0_PUBLIC=1, which drops "
                "unauthenticated callers to public tools only, or configure "
                "MAXEY0_AUTH_MODE=bearer."
            )
        if not self.mode_implemented:
            warnings.append(
                "MAXEY0_AUTH_MODE names no mode this build implements, so every "
                "request is refused with -32004/501. Set it to disabled, bearer "
                "or oidc."
            )
        if self.mode == "bearer" and tokens.errors:
            warnings.append(
                f"{len(tokens.errors)} bearer token entr"
                f"{'y is' if len(tokens.errors) == 1 else 'ies are'} invalid, so "
                f"every request is refused with -32004/501. The refusal names "
                f"each variable and entry."
            )
        if self.public_deployment and tokens.plaintext:
            # A warning, not a refusal: the plaintext forms are how every
            # deployment before hashed tokens was configured, and refusing them
            # would take those deployments down on upgrade.
            warnings.append(
                f"{tokens.plaintext} bearer token(s) on this public deployment "
                f"are stored in plaintext ({PLAINTEXT_TOKENS_VAR} or "
                f"{DEFAULT_TOKEN_VAR}), so a leaked copy of the environment is "
                f"a working credential. Mint hashed tokens with "
                f"scripts/mint_token.py, move them to {TOKEN_HASHES_VAR}, and "
                f"remove the plaintext entries."
            )
        if warnings:
            base["warning"] = " ".join(warnings)
        return base
