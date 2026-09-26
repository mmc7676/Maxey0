"""Where authorization gets its credentials from, and what it will admit to.

`config/credentials.example.json` is the tracked documentation of a file this
product asks operators to create. Two of its five sections — `mcp` and `oauth`
— had no reader anywhere in the codebase: `settings.py` reads `storage`,
`semantic_gate` and `a2a`, and `AuthConfig` read the environment only. An
operator who followed the documented setup and filled in
`oauth.client_secret` configured nothing, and nothing said so. That is the
worst instance of this codebase's recurring defect, because it is in a
security-shaped file: the failure mode is *believing you have authorization
configured*.

:meth:`AuthConfig.load` is that reader. Environment first, credentials file as
the fallback — the same precedence `Settings.load` uses, so the two cannot
disagree about which source wins.

The audit that found this proposed deleting the two sections instead. Deleting
is defensible and was the right call while `AuthConfig` had no file loader; it
is the wrong call now, because the sections describe exactly the credentials
this build already consumes from the environment. Reading them costs less than
explaining to an operator why the file documents keys it ignores.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


def normalize_mode(value: str | None) -> str:
    """`MAXEY0_AUTH_MODE` as both the config and the authorizer read it.

    One function, because the two used to disagree: `AuthConfig` stripped the
    value and `Authorizer` lower-cased it, so `Bearer` enforced bearer while
    the manifest reported `mode_implemented: false` for the same deployment.
    Empty means the documented default, `disabled`.
    """
    return (value or "").strip().lower() or "disabled"


@dataclass(frozen=True)
class AuthConfig:
    mode: str = "disabled"
    issuer: str = ""
    audience: str = ""
    jwks_url: str = ""
    client_id: str = ""
    client_secret: str = ""
    default_bearer_token: str = ""
    a2a_shared_secret: str = ""
    #: The claim an OIDC token carries its role in. Read here rather than by
    #: the verifier so it has the same env-then-credentials-file precedence as
    #: every other OIDC setting, and is reported as inert when mode is not oidc.
    role_claim: str = ""
    #: Where each populated setting came from: "env" or "credentials".
    #: Reported in aggregate by `public_manifest`; never with a value.
    sources: tuple[tuple[str, str], ...] = ()

    @classmethod
    def from_env(cls) -> "AuthConfig":
        """Environment only. Retained for callers that want no file access."""
        return cls._build(credentials={})

    @classmethod
    def load(cls, credentials: dict[str, Any] | None = None) -> "AuthConfig":
        """Environment, then `config/credentials.json`.

        The file is gitignored; only `credentials.example.json` is tracked, and
        `scripts/_packaging.py` refuses to put the real one in any archive.
        """
        if credentials is None:
            from ..settings import load_credentials_file

            credentials = load_credentials_file()
        return cls._build(credentials=credentials or {})

    @classmethod
    def _build(cls, *, credentials: dict[str, Any]) -> "AuthConfig":
        def section(name: str) -> dict[str, Any]:
            value = credentials.get(name)
            return value if isinstance(value, dict) else {}

        oauth, mcp = section("oauth"), section("mcp")
        a2a = section("a2a")
        sources: list[tuple[str, str]] = []

        def pick(field: str, env_var: str, fallback: Any) -> str:
            env_value = (os.getenv(env_var) or "").strip()
            if env_value:
                sources.append((field, "env"))
                return env_value
            file_value = str(fallback or "").strip()
            if file_value:
                sources.append((field, "credentials"))
            return file_value

        return cls(
            mode=normalize_mode(os.getenv("MAXEY0_AUTH_MODE")),
            issuer=pick("issuer", "MAXEY0_JWT_ISSUER", oauth.get("issuer")),
            audience=pick("audience", "MAXEY0_JWT_AUDIENCE", oauth.get("audience")),
            jwks_url=pick("jwks_url", "MAXEY0_JWKS_URL", oauth.get("jwks_url")),
            client_id=pick("client_id", "MAXEY0_OAUTH_CLIENT_ID", oauth.get("client_id")),
            client_secret=pick(
                "client_secret", "MAXEY0_OAUTH_CLIENT_SECRET", oauth.get("client_secret")
            ),
            default_bearer_token=pick(
                "default_bearer_token", "MAXEY0_MCP_DEFAULT_BEARER_TOKEN",
                mcp.get("default_bearer_token"),
            ),
            a2a_shared_secret=pick(
                "a2a_shared_secret", "MAXEY0_A2A_SHARED_SECRET", a2a.get("shared_secret")
            ),
            role_claim=pick(
                "role_claim", "MAXEY0_OIDC_ROLE_CLAIM", oauth.get("role_claim")
            ),
            sources=tuple(sources),
        )

    # -- reporting ----------------------------------------------------------

    #: Every mode this build enforces, and so every mode it accepts. `oidc`
    #: verifies bearer JWTs against a configured issuer, audience and key set
    #: (`auth.oidc`). Any other value is refused by `auth.policy` on every
    #: request rather than read as `disabled`: a misspelt `bearer` that fell
    #: through to the default would make every caller admin. Declared here so
    #: `implemented` is stated in one place and read everywhere.
    IMPLEMENTED_MODES = frozenset({"disabled", "bearer", "oidc"})

    #: Consumed by nothing in any mode. This build verifies tokens it is
    #: handed; it never obtains one, so it has no use for the client half.
    _NEVER_CONSUMED = frozenset({"client_id", "client_secret"})
    #: Consumed only when `mode` is oidc.
    _OIDC_ONLY = frozenset({"issuer", "audience", "jwks_url", "role_claim"})

    @property
    def oidc_configured(self) -> bool:
        return bool(self.issuer or self.jwks_url or self.client_id)

    @property
    def mode_implemented(self) -> bool:
        return normalize_mode(self.mode) in self.IMPLEMENTED_MODES

    def inert_credentials(self) -> list[str]:
        """Settings that are populated and will not be used by this build.

        The same `configured`/`implemented` split `settings.ProviderSocket`
        makes, applied to authorization. A credential supplied for a mode this
        build is not running is exactly the "looks configured, is not" state
        that `.env.example` warns about, and the operator should be told.

        This used to report OIDC fields only when the mode was implemented, and
        then all five of them -- so under `oidc` the issuer the verifier binds
        every token to was listed as unused, and under an unknown mode nothing
        was. The rule is now per field: the client half is inert everywhere,
        and the verifier's settings are inert unless the verifier runs.
        """
        inert = set(self._NEVER_CONSUMED)
        if normalize_mode(self.mode) != "oidc":
            inert |= self._OIDC_ONLY
        return sorted({field for field, _ in self.sources if field in inert})

    def public_manifest(self) -> dict:
        """Authorization shape. Never a credential value.

        `configured` alone used to be the whole answer, which could not
        distinguish "OIDC credentials are present and this build ignores them"
        from "nothing is configured". Both reported the same thing.
        """
        return {
            "mode": normalize_mode(self.mode),
            "mode_implemented": self.mode_implemented,
            "configured": bool(
                self.issuer or self.jwks_url or self.default_bearer_token
            ),
            "credential_values_exposed": False,
            "supported_binding": ["oidc", "oauth2"],
            "sources": sorted({source for _, source in self.sources}),
            "inert": self.inert_credentials(),
        }
