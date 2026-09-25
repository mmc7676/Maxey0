"""Microsoft Agent Framework — AutoGen and Semantic Kernel under one binding.

The two converged into `agent-framework`, and both reach this layer the same
way: a window is started for the agent, and every tool call and model egress the
harness makes is attributed to that window and recorded. Two adapters would have
been two names for one binding.
"""
from __future__ import annotations

from typing import Any

from ...models import AgentSpec
from ...system import SuperSpaceSystem
from .base import HarnessBinding, HarnessCapabilities, a2a_request


class MicrosoftAgentFrameworkAdapter:
    capabilities = HarnessCapabilities(
        name="microsoft",
        notes=(
            "Optional dependency: agent-framework.",
            "Covers AutoGen and Semantic Kernel, which converged on one package.",
            "The framework remains the execution harness; this layer owns the "
            "window, the gate and the record.",
        ),
    )

    def bind_agent(self, system: SuperSpaceSystem, agent: AgentSpec) -> HarnessBinding:
        instance = system.scw_runtime.start(agent.scw_id, agent.id)
        return HarnessBinding(
            self.capabilities.name, agent.id, instance.id,
            {"runtime": instance.runtime_id},
        )

    def build_a2a_request(self, sender: str, task: str, **kwargs: Any) -> dict[str, Any]:
        return a2a_request(sender, task, **kwargs)

    def import_framework(self) -> Any:
        try:
            import agent_framework
        except ImportError as exc:
            raise RuntimeError(
                "Install the optional 'agent-framework' dependency to use the "
                "Microsoft Agent Framework adapter"
            ) from exc
        return agent_framework
