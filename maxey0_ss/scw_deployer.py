from __future__ import annotations

from typing import Any
from .models import SCWSpec

DEFAULT_CONSTITUTION = {
    "isolation": "fail-closed",
    "admission": "explicit",
    "routing": "addressed",
    "observability": "events+provenance+replay",
    "execution": "host-selected-harness",
}

def deploy_default_scw(task: str, scw_id: str = "SCW0", parent_id: str | None = None, concept: str = "Task") -> SCWSpec:
    """Create the default SCW contract used before an agentic loop runs."""
    return SCWSpec(
        id=scw_id,
        parent_id=parent_id,
        concept=concept,
        # No skill: the id this used to name is registered in no context
        # graph, so every SCW the default deployer produced raised KeyError
        # at instantiation. instantiate() handles an empty skill list.
        skills=[],
        constitution={**DEFAULT_CONSTITUTION, "task": task},
        drift_threshold=0.15,
    )
