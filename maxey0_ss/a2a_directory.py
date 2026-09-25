from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class A2AAgentRecord:
    id: str
    name: str
    endpoint: str
    capabilities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class A2ADirectory:
    """Directory of A2A peers and the Maxey0 host entry point."""

    def __init__(self) -> None:
        self.agents: dict[str, A2AAgentRecord] = {}

    def register(self, agent: A2AAgentRecord) -> None:
        self.agents[agent.id] = agent

    def search(self, capability: str | None = None) -> list[A2AAgentRecord]:
        if not capability:
            return sorted(self.agents.values(), key=lambda x: x.id)
        q = capability.lower()
        return sorted(
            [a for a in self.agents.values() if any(q in c.lower() for c in a.capabilities)],
            key=lambda x: x.id,
        )

    def describe(self) -> list[dict[str, Any]]:
        return [a.__dict__ for a in self.search()]
