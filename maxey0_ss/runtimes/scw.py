from __future__ import annotations

from ..context.service import ContextService


class SCWRuntime:
    """Runtime owner for instantiated SCWs. Can be embedded or process-isolated."""

    def __init__(self, runtime_id: str, context: ContextService) -> None:
        self.runtime_id = runtime_id
        self.context = context
        self.active: set[str] = set()

    def start(self, spec_id: str, owner: str):
        instance = self.context.instantiate(spec_id, owner, self.runtime_id)
        self.active.add(instance.id)
        return instance

    def stop(self, instance_id: str) -> None:
        self.context.close(instance_id)
        self.active.discard(instance_id)
