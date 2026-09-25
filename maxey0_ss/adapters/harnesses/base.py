from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ...models import AgentSpec
from ...system import SuperSpaceSystem


@dataclass(frozen=True)
class HarnessCapabilities:
    name: str
    superspace_host: bool = True
    a2a_agent: bool = True
    mcp_client: bool = True
    notes: tuple[str, ...] = ()

    @property
    def maxey0_host(self) -> bool:
        """Compatibility alias; use superspace_host."""
        return self.superspace_host


@dataclass
class HarnessBinding:
    harness: str
    agent_id: str
    scw_id: str
    metadata: dict[str, Any] = field(default_factory=dict)


class HarnessAdapter(Protocol):
    capabilities: HarnessCapabilities

    def bind_agent(self, system: SuperSpaceSystem, agent: AgentSpec) -> HarnessBinding: ...

    def build_a2a_request(self, sender: str, task: str, **kwargs: Any) -> dict[str, Any]: ...


def a2a_request(sender: str, task: str, **kwargs: Any) -> dict[str, Any]:
    return {"sender": sender, "task": task, **kwargs}

