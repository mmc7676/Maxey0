"""Structured tool results, without dragging in the runtime session.

The vendored runtime exposes a `_tool` decorator that turns an `SCWError` into
a structured refusal instead of an exception. It is the right behavior and the
Context plane uses it directly — but it lives in `scw_runtime.server`, and
importing that module constructs the runtime's session at module scope, which
creates `~/.scw/` and opens the ledger for append.

That is fine on the Context plane, which owns the ledger. It is wrong
everywhere else: the Loop plane's whole claim is that it holds no window state,
and a plane that opens a ledger merely to borrow a decorator has quietly made
that claim false. `scripts/validate_plugin.py` asserts the claim rather than
trusting it, and this module is what makes the assertion pass honestly.

`scw_runtime.errors` is safe to import — it defines exception types and
constructs nothing.
"""

from __future__ import annotations

import functools
from typing import Any, Callable

from scw_runtime.errors import SCWError


def tool(fn: Callable[..., dict]) -> Callable[..., dict]:
    """Turn runtime errors into structured, actionable tool results.

    Behaviorally identical to the runtime's own `_tool`: a refusal comes back
    as a dict carrying its message and hint, because refusal is a normal,
    informative outcome here rather than a failure.
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> dict:
        try:
            result = fn(*args, **kwargs)
        except SCWError as exc:
            return exc.to_dict()
        except (ValueError, KeyError) as exc:
            return {"ok": False, "error": "bad_argument", "message": str(exc)}
        if isinstance(result, dict) and "ok" not in result:
            result = {"ok": True, **result}
        return result

    return wrapper
