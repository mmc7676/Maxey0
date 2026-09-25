"""Hugging Face: model inference, and the Hub read path for datasets.

Two halves, because this provider is used for two different things.

**Inference** is a model provider like the other two — a prompt goes out, text
comes back, and the egress is gated and attested exactly as an Anthropic or
OpenAI call is.

**Hub reads** are how a dataset reaches this machine. That is not a model call
and must not be attested as one: it is a *retrieval*, it carries no prompt, and
conflating the two would put "we sent a prompt to a third party" records in the
chain for an operation that sent no prompt. `ProviderCall.operation` separates
them (`inference.text_generation` against `hub.dataset_info`), and the
attestation carries the repo id rather than a payload digest.

A Hub read of a *public* dataset needs no credential at all, and that case is
deliberately kept working: a consumer reading a public dataset should not need
an account to do it. `HF_TOKEN` is consulted when present and never required
for the Hub half.
"""
from __future__ import annotations

import json
import os
import urllib.parse
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

HUB_API = "https://huggingface.co/api"
INFERENCE_API = "https://api-inference.huggingface.co/models"
DEFAULT_MODEL = "meta-llama/Llama-3.3-70B-Instruct"


class HuggingFaceProvider:
    capabilities = ProviderCapabilities(
        name="huggingface",
        operations=(
            "inference.text_generation",
            "hub.dataset_info",
            "hub.dataset_files",
            "hub.model_info",
        ),
        implemented=True,
        endpoint=HUB_API,
        credential_env=("HF_TOKEN", "HUGGINGFACE_API_KEY",
                        "HUGGINGFACEHUB_API_TOKEN"),
    )

    def __init__(
        self,
        *,
        transport: Transport | None = None,
        hub_api: str = HUB_API,
        inference_api: str = INFERENCE_API,
        timeout: float = 60.0,
    ) -> None:
        self._transport = transport or urllib_transport
        self._hub = hub_api.rstrip("/")
        self._inference = inference_api.rstrip("/")
        self._timeout = timeout

    # -- credential ---------------------------------------------------------

    def credential(self) -> Credential:
        for var in ("HF_TOKEN", "HUGGINGFACE_API_KEY", "HUGGINGFACEHUB_API_TOKEN"):
            value = (os.environ.get(var) or "").strip()
            if value:
                return Credential("HF_TOKEN", value, "env")
        from ..settings import load_credentials_file

        block = load_credentials_file().get("huggingface") or {}
        value = str(block.get("token") or "").strip()
        return Credential("HF_TOKEN", value, "credentials" if value else "unset")

    def default_model(self) -> str:
        return os.environ.get("MAXEY0_HF_MODEL") or DEFAULT_MODEL

    def _headers(self, *, require: bool) -> dict[str, str]:
        """Authorization when we have it; a hard requirement only for inference.

        A public Hub read works unauthenticated, and demanding a token for it
        would lock out every consumer reading public data — which is most of
        them, and none of whom need an account to do it.
        """
        headers = {"content-type": "application/json"}
        cred = self.credential()
        if require:
            headers["authorization"] = f"Bearer {cred.require('huggingface')}"
        elif cred.usable:
            headers["authorization"] = f"Bearer {cred.value}"
        elif cred.placeholder:
            # Silently dropping it would send an unauthenticated request that
            # succeeds for public data and fails confusingly for private data.
            cred.require("huggingface")
        return headers

    # -- inference ----------------------------------------------------------

    def describe_call(
        self, prompt: str, *, model: str | None = None, scw_id: str | None = None, **kw: Any
    ) -> ProviderCall:
        chosen = model or self.default_model()
        return ProviderCall(
            provider="huggingface",
            operation="inference.text_generation",
            model=chosen,
            scw_id=scw_id,
            payload_digest=payload_digest("huggingface", chosen, prompt, kw),
            metadata={"endpoint": f"{self._inference}/{chosen}"},
        )

    def complete(
        self,
        prompt: str,
        *,
        model: str | None = None,
        max_tokens: int = 512,
        temperature: float | None = None,
    ) -> ProviderResult:
        chosen = model or self.default_model()
        parameters: dict[str, Any] = {"max_new_tokens": max_tokens, "return_full_text": False}
        if temperature is not None:
            parameters["temperature"] = temperature
        started = now_ms()
        status, raw = self._transport(
            f"{self._inference}/{chosen}",
            json.dumps({"inputs": prompt, "parameters": parameters}).encode("utf-8"),
            self._headers(require=True),
            self._timeout,
            "POST",
        )
        parsed = _decode_inference(status, raw)
        return ProviderResult(
            provider="huggingface",
            operation="inference.text_generation",
            text=parsed,
            model=chosen,
            latency_ms=now_ms() - started,
        )

    # -- hub ----------------------------------------------------------------

    def describe_hub_read(
        self, repo_id: str, *, repo_type: str = "dataset", scw_id: str | None = None
    ) -> ProviderCall:
        """A retrieval, not a completion. No prompt, so no payload digest."""
        return ProviderCall(
            provider="huggingface",
            operation=f"hub.{repo_type}_info",
            model=None,
            scw_id=scw_id,
            payload_digest="",
            metadata={"repo_id": repo_id, "repo_type": repo_type,
                      "endpoint": f"{self._hub}/{repo_type}s/{repo_id}"},
        )

    def _hub_get(self, path: str) -> dict[str, Any]:
        status, raw = self._transport(
            f"{self._hub}{path}", None, self._headers(require=False),
            self._timeout, "GET",
        )
        return decode_json(status, raw, "huggingface")

    def dataset_info(self, repo_id: str) -> dict[str, Any]:
        return self._hub_get(f"/datasets/{urllib.parse.quote(repo_id, safe='/')}")

    def model_info(self, repo_id: str) -> dict[str, Any]:
        return self._hub_get(f"/models/{urllib.parse.quote(repo_id, safe='/')}")

    def dataset_files(self, repo_id: str) -> list[str]:
        """Every file path in a dataset repo, so a caller can fetch one."""
        info = self.dataset_info(repo_id)
        siblings = info.get("siblings") or []
        return sorted(
            str(s.get("rfilename")) for s in siblings if s.get("rfilename")
        )

    def resolve_url(self, repo_id: str, filename: str, *, revision: str = "main") -> str:
        """The direct download URL for one file. Returned, never fetched here.

        Fetching is the caller's decision because a dataset file can be
        gigabytes, and a provider that silently downloads one is a provider that
        can fill a disk from inside a tool call.
        """
        quoted = urllib.parse.quote(repo_id, safe="/")
        name = urllib.parse.quote(filename, safe="/")
        return f"https://huggingface.co/datasets/{quoted}/resolve/{revision}/{name}"

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
            "endpoint": self._hub,
            # The distinction that matters: the Hub half works without a
            # credential, the inference half does not.
            "hub_reads_need_credential": False,
            "inference_needs_credential": True,
            "values_exposed": False,
        }


def _decode_inference(status: int, raw: bytes) -> str:
    """Text out of an inference response, whichever shape it arrived in."""
    parsed = json.loads(raw.decode("utf-8")) if raw else []
    if status >= 400:
        detail = parsed.get("error") if isinstance(parsed, dict) else parsed
        from .base import ProviderError

        raise ProviderError(f"huggingface returned {status}: {json.dumps(detail)[:400]}")
    if isinstance(parsed, list) and parsed:
        first = parsed[0]
        if isinstance(first, dict):
            return str(first.get("generated_text", ""))
        return str(first)
    if isinstance(parsed, dict):
        return str(parsed.get("generated_text", ""))
    return ""
