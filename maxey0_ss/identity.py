"""SCW identifier invariant.

An SCW identifier is the literal ``SCW`` followed by digits: ``SCW0``, ``SCW1``,
``SCW42``. Nothing else.

This was an unwritten rule, and unwritten rules do not hold. ``SCWSpec`` accepted
any string, so ``SCW-MAKER`` and ``SCW-JUDGE`` were constructed without
complaint. The identifier is not cosmetic — it propagates into three places that
each assume it is well-formed:

- enforceable addresses  ``scw://topic/concept/skill/region/<scw_id>``
- cache namespaces       ``<plane>/<scw_id>/<digest>``
- attestations           ``agent_scw`` and ``target_scw``

A malformed identifier therefore produces a malformed address, a cache partition
that cannot be invalidated by ``invalidate_scw``, and evidence that names
something the address space cannot express. Rejecting it at construction is the
only place that catches all three.

Instances add a runtime suffix — ``SCW0@runtime-a`` — because one specification
may be instantiated more than once. That form is accepted where an instance is
expected, and nowhere else.
"""
from __future__ import annotations

import re

#: A specification identifier. Digits only after the prefix. Used with
#: fullmatch and an explicit [0-9] class: with `^...$` and `\d`, "SCW8\n"
#: passed (`$` matches before a trailing newline) and so did Arabic-Indic
#: digits (`\d` is any Unicode digit) -- ids that print like SCW8 but are
#: different keys in every map they reach.
SCW_ID_PATTERN = re.compile(r"SCW[0-9]{1,9}")

#: An instantiated window: a specification identifier plus a runtime suffix.
SCW_INSTANCE_PATTERN = re.compile(r"SCW[0-9]{1,9}@[A-Za-z0-9._:-]{1,128}")

#: The runtime half on its own, so a composed id always matches the pattern above.
RUNTIME_ID_PATTERN = re.compile(r"[A-Za-z0-9._:-]{1,128}")

#: How instance identifiers are composed. Kept here so the separator has one home.
INSTANCE_SEPARATOR = "@"


class InvalidSCWIdentifier(ValueError):
    """Raised when an identifier does not match the SCW invariant."""

    def __init__(self, value: object, expected: str) -> None:
        super().__init__(
            f"invalid SCW identifier {value!r}: expected {expected}. "
            f"SCW identifiers are the literal 'SCW' followed by digits."
        )
        self.value = value


def is_scw_id(value: object) -> bool:
    return isinstance(value, str) and bool(SCW_ID_PATTERN.fullmatch(value))


def is_scw_instance_id(value: object) -> bool:
    return isinstance(value, str) and bool(SCW_INSTANCE_PATTERN.fullmatch(value))


def validate_scw_id(value: object) -> str:
    """Return the identifier, or raise. Use wherever a specification is named."""
    if not is_scw_id(value):
        raise InvalidSCWIdentifier(value, "SCW followed by digits, e.g. SCW0")
    return value  # type: ignore[return-value]


def validate_scw_reference(value: object) -> str:
    """Accept a specification or an instantiated window.

    Containment decisions and cache invalidation both address instances, so they
    need the wider form; specifications do not.
    """
    if is_scw_id(value) or is_scw_instance_id(value):
        return value  # type: ignore[return-value]
    raise InvalidSCWIdentifier(value, "SCW<digits> or SCW<digits>@<runtime>")


def spec_id_of(reference: str) -> str:
    """The specification an identifier belongs to, instance or not."""
    return validate_scw_reference(reference).split(INSTANCE_SEPARATOR, 1)[0]


def instance_id(spec_id: str, runtime_id: str) -> str:
    """Compose an instance identifier, validating the specification half."""
    if not isinstance(runtime_id, str) or not RUNTIME_ID_PATTERN.fullmatch(runtime_id):
        raise InvalidSCWIdentifier(runtime_id, "a runtime identifier of [A-Za-z0-9._:-]{1,128}")
    return f"{validate_scw_id(spec_id)}{INSTANCE_SEPARATOR}{runtime_id}"
