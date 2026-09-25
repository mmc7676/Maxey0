from __future__ import annotations

from .system import SuperSpaceSystem


def export(system: SuperSpaceSystem) -> dict:
    return {
        "context_plane": system.context.graph.graph.to_dict(),
        "execution_plane": system.execution.snapshot(),
        "semantic_runtime": {"baselines": system.drift_runtime.baselines, "records": [r.__dict__ for r in system.drift_runtime.records]},
        "observability": system.observatory.trace(),
    }
