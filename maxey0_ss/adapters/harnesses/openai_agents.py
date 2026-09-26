from __future__ import annotations

from typing import Any

from ...models import AgentSpec
from ...runtimes.scw import SCWRuntime
from ...system import SuperSpaceSystem
from .base import HarnessBinding, HarnessCapabilities, a2a_request


class OpenAIAgentsAdapter:
    capabilities = HarnessCapabilities(
        name="openai-agents",
        notes=("Optional dependency: openai-agents.", "The SDK remains the execution harness; Maxey0 owns routing/context state.",
               "install_trace_processor() records generation and function spans to the "
               "containment log (digests and lengths only). It observes; it does not gate."),
    )

    def __init__(self, runtime: SCWRuntime | None = None) -> None:
        self.runtime = runtime

    def bind_agent(self, system: SuperSpaceSystem, agent: AgentSpec) -> HarnessBinding:
        runtime = self.runtime or system.scw_runtime
        instance = runtime.start(agent.scw_id, agent.id)
        return HarnessBinding(self.capabilities.name, agent.id, instance.id, {"runtime": instance.runtime_id})

    def build_a2a_request(self, sender: str, task: str, **kwargs: Any) -> dict[str, Any]:
        return a2a_request(sender, task, **kwargs)

    def build_agent(self, name: str, instructions: str, **kwargs: Any) -> Any:
        try:
            from agents import Agent
        except ImportError as exc:
            raise RuntimeError("Install the optional 'openai-agents' dependency to build an OpenAI agent") from exc
        return Agent(name=name, instructions=instructions, **kwargs)
    def install_trace_processor(self, system: Any, scw_id: str) -> Any:
        """Register an SCW trace processor via `agents.add_trace_processor`.

        Returns the processor. It OBSERVES; it does not gate -- spans are
        recorded when they end, after the call was made.
        """
        processor = make_trace_processor(system, scw_id)
        from agents import add_trace_processor

        add_trace_processor(processor)
        return processor

    def bind_maxey0_agent(self, system: SuperSpaceSystem, agent: AgentSpec) -> HarnessBinding:
        """Deprecated compatibility alias; use bind_agent()."""
        return self.bind_agent(system, agent)



def make_trace_processor(system: Any, scw_id: str) -> Any:
    """A `TracingProcessor` recording generation/function spans, imported lazily.

    Exposed so a caller managing its own processor list can use
    `agents.set_trace_processors` instead of `install_trace_processor`.
    """
    try:
        from agents.tracing import TracingProcessor
    except ImportError as exc:
        raise RuntimeError("Install the optional 'openai-agents' dependency to record agent spans") from exc
    from .observe import FrameworkRecorder

    recorder = FrameworkRecorder(system, scw_id=scw_id, harness="openai-agents")

    class SCWTraceProcessor(TracingProcessor):
        """Records generation and function spans. Observes; does not gate."""

        def __init__(self) -> None:
            self.recorder = recorder

        def on_trace_start(self, trace) -> None:
            pass

        def on_trace_end(self, trace) -> None:
            pass

        def on_span_start(self, span) -> None:
            pass

        def shutdown(self) -> None:
            pass

        def force_flush(self) -> None:
            pass

        def on_span_end(self, span) -> None:
            data = getattr(span, "span_data", None)
            kind = getattr(data, "type", "")
            if kind == "generation":
                name = str(getattr(data, "model", None) or "generation")
                self.recorder.record("llm.end", name,
                                     prompt=getattr(data, "input", None),
                                     output=getattr(data, "output", None))
            elif kind == "function":
                name = str(getattr(data, "name", None) or "function")
                self.recorder.record("tool.end", name,
                                     input=getattr(data, "input", None),
                                     output=getattr(data, "output", None))
            else:
                return
            error = getattr(span, "error", None)
            if error:
                prefix = "llm" if kind == "generation" else "tool"
                self.recorder.record(f"{prefix}.error", name, error=error)

    return SCWTraceProcessor()
