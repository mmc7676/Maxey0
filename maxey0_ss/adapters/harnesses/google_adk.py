from __future__ import annotations

from typing import Any

from ...models import AgentSpec
from ...system import SuperSpaceSystem
from .base import HarnessBinding, HarnessCapabilities, a2a_request


class GoogleADKAdapter:
    capabilities = HarnessCapabilities(
        name="google-adk",
        notes=("Optional dependency: google-adk.", "Google ADK remains the execution harness; Maxey0 remains the orchestration/context layer."),
    )

    def bind_agent(self, system: SuperSpaceSystem, agent: AgentSpec) -> HarnessBinding:
        instance = system.scw_runtime.start(agent.scw_id, agent.id)
        return HarnessBinding(self.capabilities.name, agent.id, instance.id, {"runtime": instance.runtime_id})

    def build_a2a_request(self, sender: str, task: str, **kwargs: Any) -> dict[str, Any]:
        return a2a_request(sender, task, **kwargs)

    def import_adk(self) -> Any:
        try:
            import google.adk
        except ImportError as exc:
            raise RuntimeError("Install the optional 'google-adk' dependency to use the Google ADK adapter") from exc
        return google.adk
    def bind_maxey0_agent(self, system: SuperSpaceSystem, agent: AgentSpec) -> HarnessBinding:
        """Deprecated compatibility alias; use bind_agent()."""
        return self.bind_agent(system, agent)

