"""OpenAI Responses API, with Chat Completions as the compatibility path.

`/v1/responses` is the current surface and the one this provider speaks.
`/v1/chat/completions` is kept because every OpenAI-compatible endpoint that is
not OpenAI — vLLM, Together, Groq, an Azure deployment, a local llama.cpp
server — implements that one and not the other. `OPENAI_BASE_URL` points at any
of them, which is why the base URL is configuration rather than a constant.
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

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-5"
DEFAULT_MAX_TOKENS = 1024


class OpenAIProvider:
    capabilities = ProviderCapabilities(
        name="openai",
        operations=("responses.create", "chat.completions.create"),
        implemented=True,
        endpoint=DEFAULT_BASE_URL,
        credential_env=("OPENAI_API_KEY",),
    )

    def __init__(
        self,
        *,
        transport: Transport | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self._transport = transport or urllib_transport
        self._base_url = (
            base_url or os.environ.get("OPENAI_BASE_URL") or DEFAULT_BASE_URL
        ).rstrip("/")
        self._timeout = timeout

    # -- credential ---------------------------------------------------------

    def credential(self) -> Credential:
        env = (os.environ.get("OPENAI_API_KEY") or "").strip()
        if env:
            return Credential("OPENAI_API_KEY", env, "env")
        from ..settings import load_credentials_file

        block = load_credentials_file().get("openai") or {}
        value = str(block.get("api_key") or "").strip()
        return Credential("OPENAI_API_KEY", value, "credentials" if value else "unset")

    def default_model(self) -> str:
        return os.environ.get("MAXEY0_OPENAI_MODEL") or DEFAULT_MODEL

    def organization(self) -> str:
        return (os.environ.get("OPENAI_ORG_ID") or "").strip()

    # -- call ---------------------------------------------------------------

    def describe_call(
        self, prompt: str, *, model: str | None = None, scw_id: str | None = None, **kw: Any
    ) -> ProviderCall:
        chosen = model or self.default_model()
        return ProviderCall(
            provider="openai",
            operation="responses.create",
            model=chosen,
            scw_id=scw_id,
            payload_digest=payload_digest("openai", chosen, prompt, kw),
            metadata={"endpoint": f"{self._base_url}/responses"},
        )

    def _post(self, path: str, body: dict[str, Any]) -> tuple[dict[str, Any], int]:
        key = self.credential().require("openai")
        headers = {"content-type": "application/json", "authorization": f"Bearer {key}"}
        org = self.organization()
        if org:
            headers["openai-organization"] = org
        started = now_ms()
        status, raw = self._transport(
            f"{self._base_url}{path}",
            json.dumps(body).encode("utf-8"),
            headers,
            self._timeout,
            "POST",
        )
        return decode_json(status, raw, "openai"), now_ms() - started

    def complete(
        self,
        prompt: str,
        *,
        model: str | None = None,
        system: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float | None = None,
    ) -> ProviderResult:
        """The Responses API."""
        chosen = model or self.default_model()
        body: dict[str, Any] = {
            "model": chosen,
            "input": prompt,
            "max_output_tokens": max_tokens,
        }
        if system:
            body["instructions"] = system
        if temperature is not None:
            body["temperature"] = temperature

        parsed, latency = self._post("/responses", body)
        return ProviderResult(
            provider="openai",
            operation="responses.create",
            text=_responses_text(parsed),
            model=parsed.get("model", chosen),
            usage=_usage(parsed.get("usage") or {}, "input_tokens", "output_tokens"),
            latency_ms=latency,
            raw=parsed,
        )

    def chat(
        self,
        prompt: str,
        *,
        model: str | None = None,
        system: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float | None = None,
    ) -> ProviderResult:
        """Chat Completions — the shape every OpenAI-compatible endpoint speaks."""
        chosen = model or self.default_model()
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        body: dict[str, Any] = {
            "model": chosen,
            "messages": messages,
            "max_completion_tokens": max_tokens,
        }
        if temperature is not None:
            body["temperature"] = temperature

        parsed, latency = self._post("/chat/completions", body)
        choices = parsed.get("choices") or []
        text = (choices[0].get("message") or {}).get("content", "") if choices else ""
        return ProviderResult(
            provider="openai",
            operation="chat.completions.create",
            text=text or "",
            model=parsed.get("model", chosen),
            usage=_usage(parsed.get("usage") or {}, "prompt_tokens", "completion_tokens"),
            latency_ms=latency,
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
            "endpoint": self._base_url,
            # A non-default base URL means an OpenAI-compatible endpoint that is
            # not OpenAI, which changes who is receiving the prompt. Reported.
            "endpoint_is_default": self._base_url == DEFAULT_BASE_URL,
            "organization_set": bool(self.organization()),
            "values_exposed": False,
        }


def _responses_text(parsed: dict[str, Any]) -> str:
    """Text out of a Responses payload, whichever shape it arrived in.

    `output_text` is the convenience field and is not always present; the
    structured `output` array always is. Reading only the convenience field
    returns "" for a perfectly good response, which reads as a refusal.
    """
    direct = parsed.get("output_text")
    if isinstance(direct, str) and direct:
        return direct
    if isinstance(direct, list) and direct:
        return "".join(str(part) for part in direct)
    chunks: list[str] = []
    for item in parsed.get("output") or []:
        for block in item.get("content") or []:
            if block.get("type") in {"output_text", "text"}:
                chunks.append(block.get("text", ""))
    return "".join(chunks)


def _usage(usage: dict[str, Any], in_key: str, out_key: str) -> dict[str, int]:
    return {
        "input_tokens": int(usage.get(in_key, 0) or 0),
        "output_tokens": int(usage.get(out_key, 0) or 0),
    }
