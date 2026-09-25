"""Token accounting.

The runtime needs a token count for every region so that the window map is
sized honestly and cache economics are expressed in the unit that is actually
billed. Exactness matters less than *stability*: the same text must always
produce the same count, or replay and the cache ledger drift.

Three backends, in preference order:

1. A tokenizer installed by the host via :func:`set_tokenizer` (use this to
   plug in the exact tokenizer of the model you are targeting).
2. ``tiktoken`` (``cl100k_base``) if it is importable.
3. A deterministic heuristic that is within a few percent on English prose,
   code, and JSON.

The heuristic is the default so the package has zero required dependencies.
Whichever backend is live is reported by :func:`tokenizer_name` and is stamped
into the event log header, so a replayed log always states how its numbers were
produced.
"""

from __future__ import annotations

import re
from typing import Callable, Optional

_custom: Optional[Callable[[str], int]] = None
_custom_name: str = ""
_tiktoken_encoding = None
_tiktoken_tried = False

# Splits text into token-ish units: words, numbers, and individual symbols.
_ATOM = re.compile(r"[A-Za-z]+|\d+|\s+|[^\sA-Za-z\d]")


def set_tokenizer(fn: Optional[Callable[[str], int]], name: str = "custom") -> None:
    """Install (or clear, with ``None``) a host-supplied tokenizer."""
    global _custom, _custom_name
    _custom = fn
    _custom_name = name if fn is not None else ""


def _load_tiktoken():
    global _tiktoken_encoding, _tiktoken_tried
    if _tiktoken_tried:
        return _tiktoken_encoding
    _tiktoken_tried = True
    try:  # pragma: no cover - depends on optional extra
        import tiktoken

        _tiktoken_encoding = tiktoken.get_encoding("cl100k_base")
    except Exception:
        _tiktoken_encoding = None
    return _tiktoken_encoding


def _heuristic(text: str) -> int:
    """Deterministic estimate.

    Long alphabetic runs are split at roughly four characters per token, digit
    runs at three, runs of whitespace collapse into at most one token, and
    punctuation costs one each. This tracks BPE behavior closely enough for
    budgeting while never depending on a model-specific vocabulary.
    """
    total = 0
    for atom in _ATOM.findall(text):
        first = atom[0]
        if first.isspace():
            total += 0 if len(atom) == 1 and first == " " else 1
        elif first.isdigit():
            total += max(1, (len(atom) + 2) // 3)
        elif first.isalpha():
            total += max(1, (len(atom) + 3) // 4)
        else:
            total += 1
    return total


def count_tokens(text: str) -> int:
    """Return the token cost of ``text`` under the active backend."""
    if not text:
        return 0
    if _custom is not None:
        return int(_custom(text))
    enc = _load_tiktoken()
    if enc is not None:  # pragma: no cover - depends on optional extra
        return len(enc.encode(text))
    return _heuristic(text)


def tokenizer_name() -> str:
    """Identify the active backend, for stamping into the event log."""
    if _custom is not None:
        return _custom_name or "custom"
    if _load_tiktoken() is not None:  # pragma: no cover - optional extra
        return "tiktoken:cl100k_base"
    return "heuristic:v1"
