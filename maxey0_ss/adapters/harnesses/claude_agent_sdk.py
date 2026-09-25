from __future__ import annotations

from typing import Any

from ...models import AgentSpec
from ...system import SuperSpaceSystem
from .base import HarnessBinding, HarnessCapabilities, a2a_request


class ClaudeAgentSDKAdapter:
    capabilities = HarnessCapabilities(
        name="claude-agent-sdk",
        notes=("Optional dependency: claude-agent-sdk.", "Claude Agent SDK supplies execution; Maxey0 supplies semantic/context orchestration."),
    )

    def bind_agent(self, system: SuperSpaceSystem, agent: AgentSpec) -> HarnessBinding:
        instance = system.scw_runtime.start(agent.scw_id, agent.id)
        return HarnessBinding(self.capabilities.name, agent.id, instance.id, {"runtime": instance.runtime_id})

    def build_a2a_request(self, sender: str, task: str, **kwargs: Any) -> dict[str, Any]:
        return a2a_request(sender, task, **kwargs)

    def sdk_module(self) -> Any:
        try:
            import claude_agent_sdk
        except ImportError as exc:
            raise RuntimeError("Install the optional 'claude-agent-sdk' dependency to use the Claude Agent SDK adapter") from exc
        return claude_agent_sdk
    def bind_maxey0_agent(self, system: SuperSpaceSystem, agent: AgentSpec) -> HarnessBinding:
        """Deprecated compatibility alias; use bind_agent()."""
        return self.bind_agent(system, agent)

