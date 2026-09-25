"""The Gate — where an agent inside a partition becomes observable.

A tool call is the one moment an agent running in a sealed delegated context has
to ask its host for something, so it is the only place an outside observer can
stand. The gate stands there: it attributes each call to a bound SCW role,
records it, and — in `enforce` mode — refuses the ones that reach outside that
role's declared scope.

    protocol   the host-agnostic contract: ToolEvent, Policy, Decision
    core       the decision itself; pure, imports no host
    attribution  actor -> loop_id, and honest failure when it cannot be done
    journal    the gate's own hash-chained, lock-protected log
    store      declared policy and the gate mode
    adapters/  one per host; claude_code is the reference implementation

See `docs/ARCHITECTURE.md` for why this exists and `docs/GATE.md` for the
protocol.
"""

from .protocol import (  # noqa: F401
    GATE_MODES,
    PROTOCOL_VERSION,
    Decision,
    GateMode,
    Policy,
    ToolEvent,
)

__all__ = [
    "GATE_MODES",
    "PROTOCOL_VERSION",
    "Decision",
    "GateMode",
    "Policy",
    "ToolEvent",
]
