"""What the gate may write to disk about the person using it.

Every hook event carries the user's working directory (usually
`C:\\Users\\<name>\\...` or `/Users/<name>/...`), transcript paths that embed the
same username, and raw tool inputs that can hold file contents, shell commands
or a pasted secret. The journal is plaintext on disk and is read back by
observe tools, so without this module a user's name, folder layout and any
secret they typed would be persisted indefinitely.

`redact` is applied once, at the point of writing, so the gate's decisions are
made on the real values and only the record is sanitized:

- a home directory is shortened to `~` (the current user's actual home, and any
  `C:\\Users\\<name>`, `/Users/<name>`, `/home/<name>` form);
- transcript paths are dropped entirely: they identify the user and the session
  and the journal never needs them;
- secret-shaped values are replaced with `[REDACTED:<kind>]`.

This file is duplicated byte-for-byte as `server/vendor/scw_runtime/privacy.py`
so the runtime ledger applies the same rules without importing the gate;
`tests/test_privacy.py` asserts the two copies are identical.
"""
from __future__ import annotations

import os
import re
from typing import Any

#: Keys whose values identify the user or session and are never persisted.
DROPPED_KEYS = frozenset({
    "transcript_path", "agent_transcript_path", "transcript_ref", "actor_transcript_ref",
})

_SECRETS = (
    ("anthropic-key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}")),
    ("openai-key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{20,}")),
    ("github-token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}")),
    ("aws-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}")),
    ("google-key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("hf-token", re.compile(r"\bhf_[A-Za-z0-9]{20,}")),
    ("maxey0-token", re.compile(r"\bm0ss_[A-Za-z0-9_\-]{20,}")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")),
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)")),
    ("bearer", re.compile(r"(?i)(?<=\bbearer\s)[A-Za-z0-9._~+/\-]{16,}=*")),
)
#: `password=...`, `"api_key": "..."`, `SECRET: ...` -- mask the value, keep the name.
_ASSIGNED = re.compile(
    r"(?i)\b([A-Za-z0-9_\-]*(?:password|passwd|secret|token|api[_\-]?key|access[_\-]?key|"
    r"private[_\-]?key|client[_\-]?secret|credential)[A-Za-z0-9_\-]*)"
    r"(\s*[\"']?\s*[:=]\s*[\"']?)([^\s\"',;&]{6,})"
)
_GENERIC_HOME = re.compile(
    r"(?i)\b[A-Z]:[\\/]{1,2}Users[\\/]{1,2}[^\\/\s\"':]+|/Users/[^/\s\"':]+|/home/[^/\s\"':]+"
)


def _home_forms() -> list[str]:
    home = os.path.expanduser("~")
    if not home or home == "~":
        return []
    forms = {home, home.replace("\\", "/"), home.replace("/", "\\"),
             home.replace("\\", "\\\\")}
    return sorted((f for f in forms if len(f) > 3), key=len, reverse=True)


def shorten_home(text: str) -> str:
    """Replace the user's home directory with `~`, whatever form it takes."""
    for form in _home_forms():
        text = re.sub(re.escape(form), "~", text, flags=re.IGNORECASE)
    return _GENERIC_HOME.sub("~", text)


def mask_secrets(text: str) -> str:
    for kind, rx in _SECRETS:
        text = rx.sub(f"[REDACTED:{kind}]", text)
    return _ASSIGNED.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED:assigned]", text)


def redact(value: Any) -> Any:
    """A copy of `value` that is safe to persist. Never mutates its input."""
    if isinstance(value, str):
        return mask_secrets(shorten_home(value))
    if isinstance(value, dict):
        return {
            (redact(k) if isinstance(k, str) else k): redact(v)
            for k, v in value.items() if not (isinstance(k, str) and k in DROPPED_KEYS)
        }
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    return value
