from __future__ import annotations

from .context.directory import MCPDirectory
from .context.service import ContextService
from .execution.loop import ExecutionGraph
from .execution.router import ExecutionRouter
from .models import AgentSpec, LoopSpec, MCPServerRecord, SCWSpec, SkillRecord
from .observability.service import Observatory
from .mcp_delivery import MCPDelivery
from .a2a_directory import A2ADirectory, A2AAgentRecord
from .runtimes.drift import DriftRuntime
from .runtimes.scw import SCWRuntime


class SuperSpaceSystem:
    """Top-level Maxey0-SuperSpace orchestration surface.

    Context and execution remain separate graphs. SCW instances are the
    controlled intersection. The system is deliberately harness-neutral.
    """

    def __init__(self) -> None:
        self.context = ContextService()
        self.directory = MCPDirectory(self.context.graph)
        self.execution = ExecutionGraph()
        self.router = ExecutionRouter()
        self.observatory = Observatory()
        self.scw_runtime = SCWRuntime("scw-runtime-0", self.context)
        self.drift_runtime = DriftRuntime()
        self.mcp_delivery = MCPDelivery(self.directory)
        self.a2a_directory = A2ADirectory()
        self.a2a_directory.register(A2AAgentRecord("maxey0-ss", "Maxey0-SuperSpace", "http://127.0.0.1:8765/v1/a2a/message", ["loop-routing", "semantic-context-routing", "scw-instantiation"]))

    def register_mcp(self, server: MCPServerRecord) -> None:
        self.directory.register(server)
        self.observatory.record("mcp.register", "maxey0-ss", server=server.id)

    def register_skill(self, skill: SkillRecord) -> None:
        self.context.graph.add_skill(skill)
        self.observatory.record("skill.register", "maxey0-ss", skill=skill.id, gate=skill.gate_id)

    def create_scw(self, spec: SCWSpec) -> None:
        self.context.create_spec(spec)
        self.observatory.record("scw.spec", "maxey0-ss", scw=spec.id, concept=spec.concept)

    def add_agent(self, agent: AgentSpec) -> None:
        self.execution.add_agent(agent)
        self.observatory.record("agent.register", "maxey0-ss", agent=agent.id, scw=agent.scw_id)

    def add_loop(self, loop: LoopSpec) -> None:
        self.execution.add_loop(loop)
        self.observatory.record("loop.register", "maxey0-ss", loop=loop.id, agents=loop.agents)

    def register_a2a_agent(self, agent: A2AAgentRecord) -> None:
        self.a2a_directory.register(agent)
        self.observatory.record("a2a.register", "maxey0-ss", agent=agent.id)

    def snapshot(self) -> dict:
        return {
            "context": self.context.snapshot(),
            "execution": self.execution.snapshot(),
            "observability": self.observatory.trace(),
            "a2a": self.a2a_directory.describe(),
            "semantic": {"baselines": self.drift_runtime.baselines, "records": [r.__dict__ for r in self.drift_runtime.records]},
        }
