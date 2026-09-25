"""Anthropic Messages API.

One POST, one JSON body, one header. No vendor SDK — see `base`'s docstring.
"""
from __future__ import annotations

import json
import os
from typing import Any

from .base import (
    Credential,
    ProviderCall,
    ProviderCapabilities,
    ProviderResult,
    Transport,
    decode_json,
    now_ms,
    payload_digest,
    urllib_transport,
)

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"

#: Default model. A default, not a choice made for the operator: every call
#: takes `model=`, and `MAXEY0_ANTHROPIC_MODEL` overrides this one.
DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_MAX_TOKENS = 1024


class AnthropicProvider:
    capabilities = ProviderCapabilities(
        name="anthropic",
        operations=("messages.create",),
        implemented=True,
        endpoint=API_URL,
        credential_env=("ANTHROPIC_API_KEY",),
    )

    def __init__(
        self,
        *,
        transport: Transport | None = None,
        api_url: str = API_URL,
        timeout: float = 60.0,
    ) -> None:
        self._transport = transport or urllib_transport
        self._api_url = api_url
        self._timeout = timeout

    # -- credential ---------------------------------------------------------

    def credential(self) -> Credential:
        """Environment first, then `config/credentials.json`'s `anthropic` block."""
        env = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
        if env:
            return Credential("ANTHROPIC_API_KEY", env, "env")
        from ..settings import load_credentials_file

        block = load_credentials_file().get("anthropic") or {}
        value = str(block.get("api_key") or "").strip()
        return Credential(
            "ANTHROPIC_API_KEY", value, "credentials" if value else "unset"
        )

    def default_model(self) -> str:
        return (
            os.environ.get("MAXEY0_ANTHROPIC_MODEL")
            or os.environ.get("MAXEY0_MODEL")
            or DEFAULT_MODEL
        )

    # -- call ---------------------------------------------------------------

    def describe_call(
        self, prompt: str, *, model: str | None = None, scw_id: str | None = None, **kw: Any
    ) -> ProviderCall:
        """The egress, described before it happens, so the gate can refuse it."""
        return ProviderCall(
            provider="anthropic",
            operation="messages.create",
            model=model or self.default_model(),
            scw_id=scw_id,
            payload_digest=payload_digest("anthropic", model or self.default_model(), prompt, kw),
            metadata={"endpoint": self._api_url},
        )

    def complete(
        self,
        prompt: str,
        *,
        model: str | None = None,
        system: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float | None = None,
    ) -> ProviderResult:
        key = self.credential().require("anthropic")
        chosen = model or self.default_model()
        body: dict[str, Any] = {
            "model": chosen,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system
        if temperature is not None:
            body["temperature"] = temperature

        started = now_ms()
        status, raw = self._transport(
            self._api_url,
            json.dumps(body).encode("utf-8"),
            {
                "content-type": "application/json",
                "x-api-key": key,
                "anthropic-version": API_VERSION,
            },
            self._timeout,
            "POST",
        )
        parsed = decode_json(status, raw, "anthropic")
        text = "".join(
            block.get("text", "")
            for block in parsed.get("content", [])
            if block.get("type") == "text"
        )
        usage = parsed.get("usage") or {}
        return ProviderResult(
            provider="anthropic",
            operation="messages.create",
            text=text,
            model=parsed.get("model", chosen),
            usage={
                "input_tokens": int(usage.get("input_tokens", 0)),
                "output_tokens": int(usage.get("output_tokens", 0)),
            },
            latency_ms=now_ms() - started,
            raw=parsed,
        )

    # -- reporting ----------------------------------------------------------

    def public_manifest(self) -> dict[str, Any]:
        cred = self.credential()
        return {
            "name": self.capabilities.name,
            "operations": list(self.capabilities.operations),
            "implemented": self.capabilities.implemented,
            "configured": cred.usable,
            "credential_present": cred.present,
            "credential_is_placeholder": cred.placeholder,
            "credential_source": cred.source,
            "credential_preview": cred.preview(),
            "default_model": self.default_model(),
            "endpoint": self._api_url,
            "values_exposed": False,
        }
