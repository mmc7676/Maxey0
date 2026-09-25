"""What a model or dataset provider is, and what it must never be.

Three rules decide the shape of everything in this package.

**A credential is either real, absent, or a placeholder — and the three are not
the same thing.** Absent means "not configured", and the deployment surface
reports it as such. A placeholder means somebody copied `.env.example`, meant to
fill it in, and did not: it looks configured to every check that tests
truthiness, which is the failure mode this project exists to refuse. So
placeholders are recognized by name and raise :class:`PlaceholderCredential` at
the moment of use, loudly, naming the variable and the file it came from.

**`configured` and `implemented` are separate facts.** `settings.ProviderSocket`
already makes that split for storage and the semantic gate; model providers make
it here. A build can have credentials for a provider it cannot call, and the
gap is exactly what a deployer needs told.

**Every provider call is gated and attested.** The observability claim this
product makes is not a dashboard — it is that the one moment an agent reaches
outside its window is a moment an outside observer can stand at. An egress to
`api.anthropic.com` is such a moment. So a provider call is admitted by the same
`SemanticGateProvider` that admits a tool call, and lands in the same
hash-chained `AttestationLog`, with the prompt digested rather than stored. If
that wiring is absent the call does not happen; there is no unobserved path.

No provider here imports a vendor SDK. A non-streaming completion is one POST
with a JSON body and a header, which `urllib.request` does natively, and the
alternative is making every install of this package carry three SDKs and their
transitive dependency trees in order to reach an endpoint that has been stable
for years. `server/maxey0_studio/anthropic_client.py` made the same call for the
same reason.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from ..cache.identity import digest

#: Values that mean "this was never filled in". Matched case-insensitively as
#: a substring, because the point is to catch a copied template rather than to
#: validate a format.
#:
#: Kept in step with `.env.example` and `config/credentials.example.json` by
#: `tests/test_providers.py`, which reads those files and asserts every value
#: they ship is recognized here. A placeholder convention that the code does not
#: recognize is a placeholder convention that fails open.
PLACEHOLDER_MARKERS: tuple[str, ...] = (
    "replace_me", "placeholder", "changeme", "example.invalid",
    "your-", "your_", "xxxx", "<", "${",
)


class ProviderError(RuntimeError):
    """A provider could not answer. Never raised for a missing credential."""


class NotConfigured(ProviderError):
    """No credential at all. Distinct from a placeholder on purpose."""


class PlaceholderCredential(ProviderError):
    """A credential is present and is obviously a template value.

    The loudest failure in this package, deliberately. A deployment in this
    state passes every truthiness check, reports itself configured, and fails
    at the provider with whatever error that vendor returns for a bad key —
    which is how an operator ends up debugging the wrong system.
    """


class ProviderRefused(ProviderError):
    """The gate refused this egress. Carries the decision."""

    def __init__(self, message: str, decision: Any) -> None:
        super().__init__(message)
        self.decision = decision


def is_placeholder(value: str | None) -> bool:
    if not value or not value.strip():
        return False  # absent, not a placeholder
    lowered = value.strip().lower()
    return any(marker in lowered for marker in PLACEHOLDER_MARKERS)


@dataclass(frozen=True)
class Credential:
    """One secret, and where it came from. The value never leaves this object.

    `source` is reported; `value` is not, anywhere, ever. `preview` exists so an
    operator can confirm *which* key is loaded without the key being disclosed —
    the same reason `auth.manifest` reports `sources` and not values.
    """

    name: str
    value: str = ""
    source: str = "unset"

    @property
    def present(self) -> bool:
        return bool(self.value.strip())

    @property
    def placeholder(self) -> bool:
        return is_placeholder(self.value)

    @property
    def usable(self) -> bool:
        return self.present and not self.placeholder

    def require(self, provider: str) -> str:
        """The value, or the loudest possible explanation of why there is none."""
        if not self.present:
            raise NotConfigured(
                f"{provider} needs {self.name}, which is not set. Add it to .env "
                f"(see .env.example) or config/credentials.json, or call "
                f"maxey0-ss.deployment to see which sockets are configured."
            )
        if self.placeholder:
            raise PlaceholderCredential(
                f"{provider} was given the placeholder value from {self.source} "
                f"for {self.name}. That is the template, not a credential. This "
                f"refuses rather than sending it, because a template value looks "
                f"configured to every check that tests for truthiness, and the "
                f"vendor's 'invalid key' error would send you looking in the "
                f"wrong system. Replace {self.name} with a real value."
            )
        return self.value

    def preview(self) -> str:
        """Enough to identify the key, never enough to use it."""
        if not self.present:
            return ""
        if self.placeholder:
            return "<placeholder>"
        v = self.value.strip()
        return f"{v[:6]}…{v[-4:]}" if len(v) > 14 else "***"


@dataclass
class ProviderCall:
    """One egress, described before it happens.

    Described first so the gate has something to decide about and the
    attestation records the request rather than the outcome. A record written
    only on success cannot show a refusal.
    """

    provider: str
    operation: str
    model: str | None = None
    scw_id: str | None = None
    #: Digest, never the prompt. The containment record is published.
    payload_digest: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_attestation(self) -> dict[str, Any]:
        return {
            "kind": "provider.egress",
            "provider": self.provider,
            "operation": self.operation,
            "model": self.model,
            "scw_id": self.scw_id,
            "payload_digest": self.payload_digest,
            **self.metadata,
        }


@dataclass
class ProviderResult:
    """What came back, plus what it cost and how long it took."""

    provider: str
    operation: str
    text: str = ""
    model: str | None = None
    usage: dict[str, int] = field(default_factory=dict)
    latency_ms: int = 0
    raw: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "operation": self.operation,
            "model": self.model,
            "text": self.text,
            "usage": dict(self.usage),
            "latency_ms": self.latency_ms,
        }


#: A transport is (url, body, headers, timeout, method) -> (status, bytes).
#:
#: Injectable so the whole provider layer is exercised by tests without a
#: network or a key. A provider tested only behind a mock of itself is a
#: provider whose request shape is never checked; these tests assert the URL,
#: the headers, the method and the JSON body that would go on the wire.
#:
#: `method` is a parameter rather than a constant because the Hugging Face Hub
#: is read with GET and its inference endpoints are POSTed to, and a POST-only
#: transport would have meant a second, untested code path for the half of that
#: provider that reads datasets.
Transport = Callable[[str, bytes | None, dict[str, str], float, str], tuple[int, bytes]]


def urllib_transport(
    url: str,
    body: bytes | None,
    headers: dict[str, str],
    timeout: float,
    method: str = "POST",
) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:  # a real answer, just not a 2xx
        return exc.code, exc.read()
    except urllib.error.URLError as exc:
        raise ProviderError(f"could not reach {url}: {exc.reason}") from exc


@dataclass(frozen=True)
class ProviderCapabilities:
    """What this provider is for, and whether this build can actually call it."""

    name: str
    operations: tuple[str, ...]
    #: False when the code exists but no endpoint is wired. Never guessed.
    implemented: bool = True
    endpoint: str = ""
    credential_env: tuple[str, ...] = ()


class Provider(Protocol):
    capabilities: ProviderCapabilities

    def credential(self) -> Credential: ...

    def public_manifest(self) -> dict[str, Any]: ...


def payload_digest(*parts: Any) -> str:
    """A stable digest of a request. Prompts are digested, never recorded."""
    return digest(*parts)


def now_ms() -> int:
    return int(time.time() * 1000)


def decode_json(status: int, body: bytes, provider: str) -> dict[str, Any]:
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderError(
            f"{provider} returned {status} with a body that is not JSON: "
            f"{body[:200]!r}"
        ) from exc
    if status >= 400:
        detail = parsed.get("error") or parsed
        raise ProviderError(f"{provider} returned {status}: {json.dumps(detail)[:400]}")
    return parsed
