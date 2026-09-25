"""NVIDIA NeMo Agent Toolkit.

A NeMo workflow binds to a window like any other harness. NIM endpoints are
ordinary egress: they are a third party receiving a prompt, so they belong in
the attestation chain exactly as api.anthropic.com does — an endpoint being
self-hosted changes who operates it, not whether the prompt left this process.
"""
from __future__ import annotations

from typing import Any

from ...models import AgentSpec
from ...system import SuperSpaceSystem
from .base import HarnessBinding, HarnessCapabilities, a2a_request


class NvidiaNeMoAdapter:
    capabilities = HarnessCapabilities(
        name="nvidia",
        notes=(
            "Optional dependency: nvidia-nat.",
            "NIM endpoints are egress and are attested as egress.",
            "The toolkit remains the execution harness; this layer owns the "
            "window, the gate and the record.",
        ),
    )

    def bind_agent(self, system: SuperSpaceSystem, agent: AgentSpec) -> HarnessBinding:
        instance = system.scw_runtime.start(agent.scw_id, agent.id)
        return HarnessBinding(
            self.capabilities.name, agent.id, instance.id,
            {"runtime": instance.runtime_id},
        )

    def build_a2a_request(self, sender: str, task: str, **kwargs: Any) -> dict[str, Any]:
        return a2a_request(sender, task, **kwargs)

    def import_toolkit(self) -> Any:
        try:
            import nat
        except ImportError as exc:
            raise RuntimeError(
                "Install the optional 'nvidia-nat' dependency to use the NVIDIA "
                "NeMo Agent Toolkit adapter"
            ) from exc
        return nat
