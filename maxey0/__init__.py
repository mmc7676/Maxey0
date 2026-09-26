"""Maxey0-SuperSpace, imported by its short name.

``pip install maxey0`` installs two import packages. ``maxey0`` is this one: a
short front door. ``maxey0_ss`` is the implementation, and everything here is
imported from it, so the two cannot disagree::

    import maxey0
    from maxey0 import scw

    scw.create("SCW1", task="Summarize the Q3 filings", concept="Finance")
    scw.describe()["specifications"]["SCW1"]

``maxey0.scw`` runs the same handlers as the ``maxey0-ss.scw.*`` MCP tools.
Anything this package does not wrap is still reachable through ``maxey0_ss``.
"""

from maxey0_ss import SuperSpaceSystem, __version__
from maxey0_ss.models import SCWSpec

from . import scw

__all__ = ["SCWSpec", "SuperSpaceSystem", "__version__", "scw"]
