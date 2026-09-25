from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Plane:
    name: str
    purpose: str
    owner: str


CONTEXT = Plane("context", "semantic address space, SCW definitions, gates, MCP directory", "Maxey0")
EXECUTION = Plane("execution", "agents, loops, routing, coordination and execution state", "host/harness + Maxey0")
ENGINEERING = Plane("engineering", "telemetry, provenance, replay, drift analysis and tuning", "Maxey0")

PLANES = {p.name: p for p in (CONTEXT, EXECUTION, ENGINEERING)}
