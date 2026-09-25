"""The execution graph: agents, loops, and the orchestrator that dispatches them.

Work reaches an agent by being *assigned to a loop*. That was true by convention
and false in the code: `run()` took a loop and a set of handlers but no task, so
nothing recorded what had been assigned, and a loop could be declared and never
executed with nothing able to tell the difference.

Three properties are enforced here now:

1. **An assignment has a task.** `run()` requires one and records it, so the
   graph can answer "what was this loop asked to do" rather than only "which
   agents did it contain".
2. **Dispatch is complete or it does not start.** Handlers are checked for every
   agent before the first one runs. A loop that fails halfway used to be left in
   ``running`` for ever, which reads as "in progress" and is indistinguishable
   from work still happening.
3. **Declared is not the same as run.** `unrun_loops()` names the loops that were
   registered and never dispatched.
"""
from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any, Callable

from ..models import AgentSpec, LoopSpec


class OrchestrationError(RuntimeError):
    """Raised when a loop cannot be dispatched as specified."""


class ExecutionGraph:
    def __init__(self) -> None:
        self.agents: dict[str, AgentSpec] = {}
        self.loops: dict[str, LoopSpec] = {}
        self.events: list[dict] = []
        #: Every task ever assigned to a loop, in order.
        self.assignments: list[dict[str, Any]] = []

    # -- registration -------------------------------------------------------

    def add_agent(self, agent: AgentSpec) -> None:
        self.agents[agent.id] = agent
        self.events.append({"type": "agent.add", "agent": agent.id, "scw": agent.scw_id})

    def add_loop(self, loop: LoopSpec) -> None:
        if not loop.agents:
            raise OrchestrationError(f"loop {loop.id} declares no agents")
        for agent_id in loop.agents:
            if agent_id not in self.agents:
                raise KeyError(f"unknown agent {agent_id}")
        self.loops[loop.id] = loop

        roles = [self.agents[a].role for a in loop.agents if a in self.agents]
        duplicated = sorted({r for r in roles if roles.count(r) > 1})
        if duplicated:
            # A formation with two makers is a different formation, not a
            # naming accident; refusing it is cheaper than losing an output.
            raise OrchestrationError(
                f"loop {loop.id} declares duplicate role(s) {duplicated}; "
                f"each role in a formation must be held by one agent"
            )
        self.events.append({"type": "loop.add", "loop": loop.id, "agents": list(loop.agents)})

    # -- dispatch -----------------------------------------------------------

    def run(
        self,
        loop_id: str,
        handlers: dict[str, Callable[[dict], dict]],
        task: str | dict[str, Any] | None = None,
    ) -> dict:
        """Assign a task to a loop and dispatch it.

        `task` is required. An agent that runs without one is doing work nobody
        asked for, and the record cannot say otherwise afterwards.
        """
        loop = self.loops.get(loop_id)
        if loop is None:
            raise OrchestrationError(f"unknown loop {loop_id}")
        if task is None or (isinstance(task, str) and not task.strip()):
            raise OrchestrationError(
                f"loop {loop_id} requires a task. The orchestrator assigns work to a "
                f"loop; dispatching without one leaves no record of what was asked."
            )

        # Fail before the first agent rather than halfway through.
        missing = [a for a in loop.agents if a not in handlers]
        if missing:
            raise OrchestrationError(
                f"loop {loop_id} cannot dispatch: no handler for {missing}. "
                f"Refusing to run a partial formation."
            )

        assignment = {
            "loop_id": loop_id,
            "task": task,
            "agents": list(loop.agents),
            "assigned_ms": int(time.time() * 1000),
        }
        self.assignments.append(assignment)
        self.events.append({"type": "loop.assign", **assignment})

        loop.state = "running"
        state: dict[str, Any] = {
            "loop_id": loop_id,
            "task": task,
            "iteration": 0,
            "outputs": {},
            # role -> [agent_id], so a caller can still reach results by
            # role without the role being the identity of the result.
            "by_role": {},
        }
        try:
            for i in range(loop.max_iterations):
                state["iteration"] = i + 1
                for agent_id in loop.agents:
                    agent = self.agents[agent_id]
                    result = handlers[agent_id](state.copy())
                    # Keyed by agent, not by role. Two agents sharing a
                    # role overwrote each other and the loop reported a
                    # complete set of outputs with one silently gone.
                    state["outputs"][agent_id] = result
                    state["by_role"].setdefault(agent.role, []).append(agent_id)
                    self.events.append(
                        {
                            "type": "agent.step",
                            "agent": agent_id,
                            "role": agent.role,
                            "scw": agent.scw_id,
                            "iteration": i + 1,
                            "result": result,
                        }
                    )
        except Exception as exc:
            # A failed loop is not a running loop. Leaving it in "running" makes
            # an abandoned formation indistinguishable from an active one.
            loop.state = "failed"
            self.events.append({"type": "loop.failed", "loop": loop_id, "error": str(exc)})
            raise

        loop.state = "completed"
        self.events.append({"type": "loop.complete", "loop": loop_id, "iterations": loop.max_iterations})
        return state

    # -- reporting ----------------------------------------------------------

    def unrun_loops(self) -> list[str]:
        """Loops declared but never dispatched."""
        return sorted(lid for lid, loop in self.loops.items() if loop.state == "created")

    def assignments_for(self, loop_id: str) -> list[dict[str, Any]]:
        return [a for a in self.assignments if a["loop_id"] == loop_id]

    def dispatched(self, loop_id: str) -> bool:
        return bool(self.assignments_for(loop_id))

    def snapshot(self) -> dict:
        return {
            "agents": {k: asdict(v) for k, v in self.agents.items()},
            "loops": {k: asdict(v) for k, v in self.loops.items()},
            "events": list(self.events),
            "assignments": list(self.assignments),
            "unrun_loops": self.unrun_loops(),
        }
