from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

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


@dataclass(frozen=True)
class RootBounds:
    """The root constitution's ceiling, as configured. None is unbounded."""

    reach: frozenset[str] | None = None
    max_depth: int | None = None
    max_children: int | None = None

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "RootBounds":
        """Read MAXEY0_ROOT_REACH, MAXEY0_MAX_DEPTH and MAXEY0_MAX_CHILDREN.

        The root was only ever bounded by passing `root_reach` in code, which
        no shipped entry point did, so a deployment had no way to set a ceiling
        at all. A malformed value raises rather than falling back to
        unbounded: a typo in a limit must not silently remove the limit.
        """
        env = os.environ if environ is None else environ
        reach = None
        raw = env.get("MAXEY0_ROOT_REACH", "").strip()
        if raw:
            ids = [part.strip() for part in raw.split(",")]
            if not all(ids):
                raise ValueError("MAXEY0_ROOT_REACH has an empty SCW id")
            reach = frozenset(ids)
        return cls(reach, _positive_int(env, "MAXEY0_MAX_DEPTH"),
                   _positive_int(env, "MAXEY0_MAX_CHILDREN"))

    def as_dict(self) -> dict:
        return {
            "reach": sorted(self.reach) if self.reach is not None else None,
            "max_depth": self.max_depth,
            "max_children": self.max_children,
        }


def _positive_int(env: Mapping[str, str], name: str) -> int | None:
    raw = env.get(name, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} must be a positive integer, got {raw!r}") from None
    if value < 1:
        raise ValueError(f"{name} must be a positive integer, got {raw!r}")
    return value


class SuperSpaceSystem:
    """Top-level Maxey0-SuperSpace orchestration surface.

    Context and execution remain separate graphs. SCW instances are the
    controlled intersection. The system is deliberately harness-neutral.
    """

    def __init__(self, *, root_bounds: RootBounds | None = None) -> None:
        self.root_bounds = root_bounds if root_bounds is not None else RootBounds.from_env()
        self.context = ContextService(
            root_reach=self.root_bounds.reach,
            max_depth=self.root_bounds.max_depth,
            max_children=self.root_bounds.max_children,
        )
        self.directory = MCPDirectory(self.context.graph)
        self.execution = ExecutionGraph()
        self.router = ExecutionRouter()
        self.observatory = Observatory()
        self.scw_runtime = SCWRuntime("scw-runtime-0", self.context)
        # On the containment log, so anchors and inspections appear in the
        # same chain `evidence.attestations` publishes.
        self.drift_runtime = DriftRuntime(log=self.context.isolation.log)
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
