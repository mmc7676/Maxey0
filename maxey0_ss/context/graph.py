from __future__ import annotations

from ..graph import DirectedGraph
from ..models import ContextNode, MCPServerRecord, SCWSpec, SemanticAddress, SkillRecord


class ContextGraph:
    """Hierarchical Topic -> Concept -> Skill -> Gate -> MCP context graph."""

    def __init__(self) -> None:
        self.graph = DirectedGraph()
        self.nodes: dict[str, ContextNode] = {}
        self.skills: dict[str, SkillRecord] = {}
        self.mcp: dict[str, MCPServerRecord] = {}
        self.scw_specs: dict[str, SCWSpec] = {}

    def add_topic(self, topic: str) -> None:
        self._node(topic, "topic", topic)

    def add_concept(self, topic: str, concept: str) -> None:
        self.add_topic(topic)
        self._node(concept, "concept", concept)
        self.graph.add_edge(topic, concept)

    def add_skill(self, record: SkillRecord) -> None:
        self.add_concept(record.topic, record.concept)
        self._node(record.id, "skill", record.name)
        self._node(record.gate_id, "gate", record.gate_id)
        self.graph.add_edge(record.concept, record.id)
        self.graph.add_edge(record.id, record.gate_id)
        for server_id in record.mcp_servers:
            self._node(server_id, "mcp_server", server_id)
            self.graph.add_edge(record.gate_id, server_id)
        self.skills[record.id] = record

    def register_mcp(self, record: MCPServerRecord) -> None:
        self.mcp[record.id] = record
        self._node(record.id, "mcp_server", record.name, endpoint=record.endpoint)

    def add_scw_spec(self, spec: SCWSpec) -> None:
        self.scw_specs[spec.id] = spec
        self._node(spec.id, "scw_spec", spec.id, concept=spec.concept)
        self.graph.add_edge(spec.concept, spec.id)
        for skill in spec.skills:
            self.graph.add_edge(skill, spec.id)

    def semantic_candidates(self, topic: str | None = None, concept: str | None = None, skill: str | None = None) -> list[SkillRecord]:
        candidates = list(self.skills.values())
        if topic:
            candidates = [s for s in candidates if s.topic == topic]
        if concept:
            candidates = [s for s in candidates if s.concept == concept]
        if skill:
            q = skill.lower()
            candidates.sort(key=lambda s: (0 if q in s.name.lower() or q in s.id.lower() else 1, s.id))
        return candidates

    def address_for_skill(self, skill_id: str, region: str) -> SemanticAddress:
        skill = self.skills[skill_id]
        return SemanticAddress(skill.topic, skill.concept, skill.id, region)

    def _node(self, node_id: str, kind: str, name: str, **metadata) -> None:
        self.nodes.setdefault(node_id, ContextNode(node_id, kind, name, metadata))
        self.graph.add_node(node_id, kind=kind, name=name, **metadata)
