"""A minimal Anthropic Messages API client -- stdlib only.

Deliberately not the `anthropic` pip package: this project's whole point is
zero install friction (see app.py's docstring), and all a single non-streaming
completion needs is one POST with a JSON body and an API-key header, which
`urllib.request` does natively. When ANTHROPIC_API_KEY is unset, every
dispatch in this app falls back to the timed simulation (mission.py) instead
of raising -- callers should check `is_configured()` first, not treat an
unset key as an error.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
#: The one model identifier in the product, and it is a default rather than a
#: choice made for you. Nothing else here names a model: the four role agents
#: are `model: inherit`, so a dispatched role runs on whatever the session runs
#: on, and this client is reached only from the Studio's Mission Control view
#: and only when the operator has set their own ANTHROPIC_API_KEY.
#:
#: `MAXEY0_ANTHROPIC_MODEL` is still honored. Renaming a tool is a clean break
#: this release makes on purpose; silently breaking a variable someone has
#: already exported into their shell is not the same thing.
DEFAULT_MODEL = (
    os.environ.get("MAXEY0_MODEL")
    or os.environ.get("MAXEY0_ANTHROPIC_MODEL")
    or "claude-sonnet-5"
)


class AnthropicError(RuntimeError):
    pass


def _load_dotenv_key() -> str | None:
    """A `.env` file next to the server, containing `ANTHROPIC_API_KEY=...`,
    with no python-dotenv dependency required."""
    candidates = [
        Path(__file__).resolve().parents[1] / ".env",
        Path(__file__).resolve().parents[2] / ".env",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                if key.strip() == "ANTHROPIC_API_KEY":
                    value = value.strip().strip('"').strip("'")
                    if value:
                        return value
        except OSError:
            continue
    return None


def _api_key() -> str | None:
    return os.environ.get("ANTHROPIC_API_KEY") or _load_dotenv_key()


def is_configured() -> bool:
    return bool(_api_key())


def key_status() -> dict:
    key = _api_key()
    if not key:
        return {"configured": False, "source": None, "model": DEFAULT_MODEL}
    source = "env" if os.environ.get("ANTHROPIC_API_KEY") else "dotenv"
    masked = f"{key[:7]}...{key[-4:]}" if len(key) > 14 else "***"
    return {"configured": True, "source": source, "key_preview": masked, "model": DEFAULT_MODEL}


def complete(system: str, user: str, max_tokens: int = 1024, model: str | None = None) -> str:
    key = _api_key()
    if not key:
        raise AnthropicError("ANTHROPIC_API_KEY is not configured")

    body = json.dumps({
        "model": model or DEFAULT_MODEL,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }).encode("utf-8")

    req = urllib.request.Request(
        API_URL, data=body, method="POST",
        headers={
            "content-type": "application/json",
            "x-api-key": key,
            "anthropic-version": API_VERSION,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AnthropicError(f"HTTP {exc.code}: {detail[:500]}") from exc
    except urllib.error.URLError as exc:
        raise AnthropicError(f"network error: {exc.reason}") from exc

    parts = payload.get("content", [])
    text = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
    if not text:
        raise AnthropicError(f"no text content in response: {payload}")
    return text
