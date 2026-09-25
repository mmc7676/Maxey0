"""The three product planes.

Maxey0 is three planes, each a separately installable connector with its own
MCP server, its own commands, and its own skills:

    maxey0-context    holds bytes and refuses reads
    maxey0-loops      decides who should act, and in what shape
    maxey0-observe    records what happened, and refuses what left scope

Each is useful alone. The Observatory can see the other two — it reads their
files — and neither of the other two can see it. That asymmetry is the design:
a boundary you can see through is not a boundary, so the resolution is to make
the boundary itself the thing that is observable, from outside.

`catalog.py` is the single source of truth for what exists. The plane modules
register from it, `menu.py` renders from it, and `scripts/check_lexicon.py`
enforces it.
"""

from __future__ import annotations

__all__ = ["bootstrap", "catalog", "menu"]
