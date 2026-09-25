"""Compatibility shim.

The enforcement logic moved to :mod:`maxey0_ss.containment`, where it sits
behind a provider interface and emits verifiable attestations. This module keeps
the original names importable so existing callers and harnesses do not break.

New code should import from `maxey0_ss.containment`.
"""
from __future__ import annotations

from ..containment import ContainmentError, StructuralContainment

#: Original name. `StructuralContainment` is the same enforcement, now recorded.
IsolationController = StructuralContainment

#: Original exception name.
IsolationError = ContainmentError

__all__ = ["IsolationController", "IsolationError"]
