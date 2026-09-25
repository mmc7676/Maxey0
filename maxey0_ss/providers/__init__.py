"""Model and dataset providers, behind one gated seam.

`maxey0_ss.providers.registry()` returns every provider this build can call,
each already wrapped by :class:`GatedProvider`. The wrapped form is the
supported one — an unwrapped provider is reachable, and reaching for it is how
an egress escapes the ledger.

Three providers ship: Anthropic, OpenAI and Hugging Face. All three are
code-complete against a real endpoint and exercised by tests that assert the URL,
the method, the headers and the JSON body that would go on the wire, using an
injected transport rather than a network. None imports a vendor SDK.
"""
from __future__ import annotations

from typing import Any

from .anthropic import AnthropicProvider
from .base import (
    Credential,
    NotConfigured,
    PlaceholderCredential,
    ProviderCall,
    ProviderCapabilities,
    ProviderError,
    ProviderRefused,
    ProviderResult,
    Transport,
    is_placeholder,
)
from .gated import EGRESS_CAPABILITY, EgressRecord, GatedProvider
from .huggingface import HuggingFaceProvider
from .openai import OpenAIProvider

#: name -> constructor. The one place a provider is registered.
PROVIDERS: dict[str, type] = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "huggingface": HuggingFaceProvider,
}


def build(name: str, **kwargs: Any) -> Any:
    """One unwrapped provider. Prefer :func:`gated`."""
    try:
        constructor = PROVIDERS[name]
    except KeyError:
        raise ProviderError(
            f"unknown provider {name!r}; this build has "
            f"{', '.join(sorted(PROVIDERS))}"
        ) from None
    return constructor(**kwargs)


def gated(name: str, *, log=None, gate=None, containment=None,
          scw_id: str | None = None, **kwargs: Any) -> GatedProvider:
    """One provider with containment, the gate and the ledger in front of it."""
    return GatedProvider(build(name, **kwargs), log=log, gate=gate,
                         containment=containment, scw_id=scw_id)


def registry(*, log=None, gate=None, containment=None,
             scw_id: str | None = None) -> dict[str, GatedProvider]:
    """Every provider, gated, sharing one attestation log.

    Sharing the log is the point: a deployment's egress record is one chain
    across every provider, so "what did this system send outside, and where"
    is a single ordered answer rather than three that have to be merged.
    """
    from ..containment.attestation import AttestationLog

    shared = log if log is not None else AttestationLog()
    return {
        name: gated(name, log=shared, gate=gate, containment=containment,
                    scw_id=scw_id)
        for name in PROVIDERS
    }


def public_manifest(*, log=None, gate=None, containment=None) -> dict[str, Any]:
    """Which providers are configured, which are callable, and which are inert.

    The same `configured`/`implemented` split `settings.ProviderSocket` makes
    for storage backends, applied to the three that actually send prompts.
    """
    providers = {
        name: p.public_manifest()
        for name, p in registry(log=log, gate=gate, containment=containment).items()
    }
    return {
        "providers": providers,
        "configured": sorted(n for n, m in providers.items() if m["configured"]),
        "placeholder": sorted(
            n for n, m in providers.items() if m["credential_is_placeholder"]
        ),
        "unconfigured": sorted(
            n for n, m in providers.items() if not m["credential_present"]
        ),
        "egress_capability": EGRESS_CAPABILITY,
        "values_exposed": False,
    }


__all__ = [
    "AnthropicProvider",
    "Credential",
    "EGRESS_CAPABILITY",
    "EgressRecord",
    "GatedProvider",
    "HuggingFaceProvider",
    "NotConfigured",
    "OpenAIProvider",
    "PROVIDERS",
    "PlaceholderCredential",
    "ProviderCall",
    "ProviderCapabilities",
    "ProviderError",
    "ProviderRefused",
    "ProviderResult",
    "Transport",
    "build",
    "gated",
    "is_placeholder",
    "public_manifest",
    "registry",
]
