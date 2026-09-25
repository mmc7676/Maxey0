from __future__ import annotations

from typing import Any

from ...models import AgentSpec
from ...system import SuperSpaceSystem
from .base import HarnessBinding, HarnessCapabilities, a2a_request


class LangChainAdapter:
    capabilities = HarnessCapabilities(
        name="langchain",
        notes=(
            "Optional dependency: langgraph, which pulls langchain-core.",
            "LangChain/LangGraph remain the execution harness; this layer "
            "owns the window, the gate and the record.",
        ),
    )

    def bind_agent(self, system: SuperSpaceSystem, agent: AgentSpec) -> HarnessBinding:
        instance = system.scw_runtime.start(agent.scw_id, agent.id)
        return HarnessBinding(self.capabilities.name, agent.id, instance.id, {"runtime": instance.runtime_id})

    def build_a2a_request(self, sender: str, task: str, **kwargs: Any) -> dict[str, Any]:
        return a2a_request(sender, task, **kwargs)

    def import_langgraph(self) -> Any:
        try:
            import langgraph
        except ImportError as exc:
            raise RuntimeError("Install the optional 'langgraph' dependency to use the LangGraph adapter") from exc
        return langgraph
    def bind_maxey0_agent(self, system: SuperSpaceSystem, agent: AgentSpec) -> HarnessBinding:
        """Deprecated compatibility alias; use bind_agent()."""
        return self.bind_agent(system, agent)

