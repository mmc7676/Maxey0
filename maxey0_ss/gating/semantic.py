"""The semantic gate: the provider boundary in front of every SCW-bound tool.

Both transports consult a provider on every tool that `requires_scw`
(`mcp_2026.build_router` and `mcp_stdio_server.build_server`), deny on a false
decision, and return the decision itself as error data. That path was already
real. What was missing was everything either side of it:

- **Nothing chose a provider from configuration.** Both transports defaulted to
  :class:`DisabledSemanticGate` and `config/credentials.json`'s
  `semantic_gate.provider` key — which `settings.py` goes to some length to
  read, with a comment explaining a bug that made the fallback unreachable —
  reached no code that acted on it. :func:`select_semantic_gate` is that reader.

- **`maxey0-ss.gate.inspect` did not use the gate.** It parsed the address and
  returned a dict literal containing `"allowed": True` and
  `"semantic_provider": "disabled"` as hardcoded strings. The one tool whose
  entire purpose is to report what the gate would decide was the one place that
  never asked it, so a deployment with a provider configured got `"disabled"`
  reported back regardless of what it had configured.

**A named-but-unimplemented provider fails closed.** This is the load-bearing
decision in this module. A deployment that sets
`MAXEY0_SEMANTIC_GATE_PROVIDER=acme` is asking for *more* restriction than the
default, and the one thing a gate must never do is answer a request for more
restriction by quietly applying less. Returning `DisabledSemanticGate` there —
allow-everything, while `deployment` reports the socket as configured — is the
precise fail-open this architecture exists to refuse. So an unrecognized
provider denies, loudly, naming itself in the reason.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from ..models import GateDecision


class SemanticGateProvider(Protocol):
    def evaluate(self, *, address: str, capability: str, metadata: dict[str, Any]) -> GateDecision: ...


#: Provider names that mean "no semantic provider", not "a provider called
#: this". Kept in step with `settings.ProviderSocket.INERT_VALUES`, which is
#: what decides whether the socket reports itself configured; the two answering
#: differently would mean `deployment` says "configured" while the gate says
#: "disabled" about the same string.
INERT_PROVIDERS = frozenset({"", "disabled", "none", "off", "false", "0"})


@dataclass(frozen=True)
class DisabledSemanticGate:
    """Public/default gate: structural address validation only.

    A null object behind a Protocol, which is a real pattern rather than a
    stub — provided the call site goes through it, which both transports and
    (since 0.2.0) `gate.inspect` do. A paid/private semantic provider
    implements the same interface and adds embeddings, graph inference, policy
    models, or external evaluation.
    """

    name: str = "disabled"

    def evaluate(self, *, address: str, capability: str, metadata: dict[str, Any]) -> GateDecision:
        return GateDecision(
            True, "address",
            "semantic provider disabled; structural SCW gate passed",
            1.0, 0.0, "address",
        )


@dataclass(frozen=True)
class UnimplementedSemanticGate:
    """A provider was named in configuration and this build has no code for it.

    Denies. See the module docstring: the alternative is to answer a request
    for stricter gating by applying none, while `maxey0-ss.deployment` reports
    the socket as `configured`. That combination — a security control reported
    as present and behaving as absent — is the exact defect this codebase keeps
    producing, and a gate is the worst place to produce it.
    """

    name: str

    def evaluate(self, *, address: str, capability: str, metadata: dict[str, Any]) -> GateDecision:
        return GateDecision(
            False, "unimplemented-provider",
            f"semantic gate provider {self.name!r} is configured but not "
            f"implemented in this build, so it cannot evaluate this request. "
            f"Refusing rather than passing it: a configured gate that allows "
            f"everything is worse than no gate. Supply a provider, or set "
            f"MAXEY0_SEMANTIC_GATE_PROVIDER=disabled to accept structural "
            f"address validation only.",
            0.0, 1.0, "configuration",
        )


#: Providers this build can actually run, by name.
IMPLEMENTED: dict[str, type] = {}


def select_semantic_gate(provider: str | None = None) -> SemanticGateProvider:
    """The gate this deployment configured.

    `provider` defaults to whatever `settings` resolved from the environment or
    `config/credentials.json` — which is what gives `semantic_gate.provider` a
    reader for the first time.
    """
    if provider is None:
        from ..settings import settings as _settings
        socket = _settings().providers.get("semantic_gate")
        provider = (socket.settings.get("MAXEY0_SEMANTIC_GATE_PROVIDER", "")
                    if socket else "")
    name = (provider or "").strip()
    if name.lower() in INERT_PROVIDERS:
        return DisabledSemanticGate()
    implementation = IMPLEMENTED.get(name.lower())
    if implementation is not None:  # pragma: no cover - none ship today
        return implementation()
    return UnimplementedSemanticGate(name)
