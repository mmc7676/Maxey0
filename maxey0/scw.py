"""Structured Context Windows (SCWs) from Python.

Each function here is one of the ``maxey0-ss.scw.*`` MCP tools, called in this
process: it looks the tool up by name and runs its handler. A window created
here is validated, recorded and closed by the same code as one created over
MCP, and the result is the same dictionary the tool returns::

    from maxey0 import scw

    scw.create("SCW1", task="Summarize the Q3 filings", concept="Finance")
    scw.drift("SCW1", [0.12, 0.40, 0.33], anchor=True)  # install a baseline
    scw.drift("SCW1", [0.10, 0.42, 0.35])               # measure against it
    scw.describe()

All five share one server surface, built the first time any of them is
called. It lives in this process, so its windows last as long as the process
does. ``surface()`` returns it, for the tools this module does not wrap, and
``reset()`` discards it so the next call starts from nothing.

No capability check is made. The caller is this Python process, which can
already reach every object such a check would protect; the MCP transports are
where remote callers are authenticated.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from typing import Any

from maxey0_ss.mcp_surface import Surface, build_surface

__all__ = ["close", "create", "describe", "drift", "reset", "start", "surface"]

_NAMESPACE = "maxey0-ss.scw."
_lock = threading.Lock()
_surface: Surface | None = None


def surface() -> Surface:
    """The in-process surface these functions call, built on first use."""
    global _surface
    with _lock:
        if _surface is None:
            _surface = build_surface()
        return _surface


def reset() -> None:
    """Discard the surface and every window on it."""
    global _surface
    with _lock:
        _surface = None


def _call(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    name = _NAMESPACE + tool
    for candidate in surface().tools:
        if candidate.name == name:
            return candidate.handler(arguments)
    raise LookupError(f"{name} is not on this surface")


def create(
    scw_id: str,
    task: str,
    *,
    concept: str = "Task",
    parent_id: str | None = None,
) -> dict[str, Any]:
    """Create an SCW specification. Raises ValueError if ``scw_id`` exists."""
    arguments: dict[str, Any] = {"scw_id": scw_id, "task": task, "concept": concept}
    if parent_id is not None:
        arguments["parent_id"] = parent_id
    return _call("create", arguments)


def describe() -> dict[str, Any]:
    """Every specification and every instantiated SCW."""
    return _call("describe", {})


def start(scw_id: str) -> dict[str, Any]:
    """Instantiate a specification. Owned by "local"; raises if already running."""
    return _call("start", {"scw_id": scw_id})


def close(scw_id: str) -> dict[str, Any]:
    """Close an instantiated SCW. A specification alone reports ``closed: False``."""
    return _call("close", {"scw_id": scw_id})


def drift(
    scw_id: str,
    vector: Sequence[float],
    *,
    anchor: bool = False,
    threshold: float | None = None,
) -> dict[str, Any]:
    """Anchor a baseline (``anchor=True``) or measure drift against it.

    ``threshold`` defaults to the specification's ``drift_threshold``. Measuring
    a window with no baseline returns ``anchored: False`` rather than a
    distance, because there is nothing to measure against.
    """
    arguments: dict[str, Any] = {"scw_id": scw_id, "vector": list(vector)}
    if anchor:
        arguments["anchor"] = True
    if threshold is not None:
        arguments["threshold"] = threshold
    return _call("drift", arguments)
