from __future__ import annotations

from ..models import MCPServerRecord, SkillRecord
from .graph import ContextGraph


class MCPDirectory:
    """Semantic MCP directory stored as Context-plane state."""

    def __init__(self, context: ContextGraph) -> None:
        self.context = context

    def register(self, server: MCPServerRecord) -> None:
        self.context.register_mcp(server)

    def servers_for_skill(self, skill_id: str) -> list[MCPServerRecord]:
        skill = self.context.skills[skill_id]
        return [self.context.mcp[s] for s in skill.mcp_servers if s in self.context.mcp]

    def search(self, query: str) -> list[MCPServerRecord]:
        q = query.lower()
        return sorted(
            [s for s in self.context.mcp.values() if q in s.name.lower() or any(q in c.lower() for c in s.capabilities)],
            key=lambda s: s.id,
        )
