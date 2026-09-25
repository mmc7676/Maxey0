from __future__ import annotations

from typing import Any

from ...models import AgentSpec
from ...runtimes.scw import SCWRuntime
from ...system import SuperSpaceSystem
from .base import HarnessBinding, HarnessCapabilities, a2a_request


class OpenAIAgentsAdapter:
    capabilities = HarnessCapabilities(
        name="openai-agents",
        notes=("Optional dependency: openai-agents.", "The SDK remains the execution harness; Maxey0 owns routing/context state."),
    )

    def __init__(self, runtime: SCWRuntime | None = None) -> None:
        self.runtime = runtime

    def bind_agent(self, system: SuperSpaceSystem, agent: AgentSpec) -> HarnessBinding:
        runtime = self.runtime or system.scw_runtime
        instance = runtime.start(agent.scw_id, agent.id)
        return HarnessBinding(self.capabilities.name, agent.id, instance.id, {"runtime": instance.runtime_id})

    def build_a2a_request(self, sender: str, task: str, **kwargs: Any) -> dict[str, Any]:
        return a2a_request(sender, task, **kwargs)

    def build_agent(self, name: str, instructions: str, **kwargs: Any) -> Any:
        try:
            from agents import Agent
        except ImportError as exc:
            raise RuntimeError("Install the optional 'openai-agents' dependency to build an OpenAI agent") from exc
        return Agent(name=name, instructions=instructions, **kwargs)
    def bind_maxey0_agent(self, system: SuperSpaceSystem, agent: AgentSpec) -> HarnessBinding:
        """Deprecated compatibility alias; use bind_agent()."""
        return self.bind_agent(system, agent)

