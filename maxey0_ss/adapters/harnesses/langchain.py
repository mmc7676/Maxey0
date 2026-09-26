from __future__ import annotations

from typing import Any

from ...models import AgentSpec
from ...system import SuperSpaceSystem
from .base import HarnessBinding, HarnessCapabilities, a2a_request


class LangChainAdapter:
    capabilities = HarnessCapabilities(
        name="langchain",
        notes=(
            "Optional dependency: langgraph, which pulls langchain-core.",
            "LangChain/LangGraph remain the execution harness; this layer "
            "owns the window, the gate and the record.",
            "callback_handler() records model and tool calls to the containment "
            "log (digests and lengths only). It observes; it does not gate.",
        ),
    )

    def bind_agent(self, system: SuperSpaceSystem, agent: AgentSpec) -> HarnessBinding:
        instance = system.scw_runtime.start(agent.scw_id, agent.id)
        return HarnessBinding(self.capabilities.name, agent.id, instance.id, {"runtime": instance.runtime_id})

    def build_a2a_request(self, sender: str, task: str, **kwargs: Any) -> dict[str, Any]:
        return a2a_request(sender, task, **kwargs)

    def import_langgraph(self) -> Any:
        try:
            import langgraph
        except ImportError as exc:
            raise RuntimeError("Install the optional 'langgraph' dependency to use the LangGraph adapter") from exc
        return langgraph
    def callback_handler(self, system: Any, scw_id: str) -> Any:
        """A LangChain callback handler that records calls into `scw_id`.

        Pass it as ``config={"callbacks": [handler]}``. It OBSERVES; it does
        not gate -- a call the handler records has already been made.
        """
        return make_callback_handler(system, scw_id)

    def bind_maxey0_agent(self, system: SuperSpaceSystem, agent: AgentSpec) -> HarnessBinding:
        """Deprecated compatibility alias; use bind_agent()."""
        return self.bind_agent(system, agent)



def make_callback_handler(system: Any, scw_id: str) -> Any:
    """Build a `BaseCallbackHandler` subclass instance, importing lazily.

    langchain-core is optional; importing it at module load would make every
    build that never uses LangChain pay for (or fail on) the dependency.
    """
    try:
        from langchain_core.callbacks import BaseCallbackHandler
    except ImportError as exc:
        raise RuntimeError(
            "Install the optional 'langgraph' (langchain-core) dependency to record LangChain calls"
        ) from exc
    from .observe import FrameworkRecorder

    recorder = FrameworkRecorder(system, scw_id=scw_id, harness="langchain")

    class SCWCallbackHandler(BaseCallbackHandler):
        """Records LangChain/LangGraph model and tool calls. Observes; does not gate."""

        def __init__(self) -> None:
            super().__init__()
            self.recorder = recorder

        @staticmethod
        def _name(serialized: Any, kwargs: dict[str, Any]) -> str:
            if isinstance(serialized, dict):
                name = serialized.get("name") or (serialized.get("id") or [None])[-1]
                if name:
                    return str(name)
            return str(kwargs.get("name") or "unknown")

        def on_chat_model_start(self, serialized, messages, **kwargs):
            msgs = [[getattr(m, "content", m) for m in batch] for batch in messages]
            self.recorder.record("llm.start", self._name(serialized, kwargs), prompt=msgs)

        def on_llm_start(self, serialized, prompts, **kwargs):
            self.recorder.record("llm.start", self._name(serialized, kwargs), prompt=prompts)

        def on_llm_end(self, response, **kwargs):
            gens = getattr(response, "generations", None) or []
            texts = [[getattr(g, "text", "") for g in batch] for batch in gens]
            self.recorder.record("llm.end", str(kwargs.get("name") or "llm"), output=texts)

        def on_llm_error(self, error, **kwargs):
            self.recorder.record("llm.error", type(error).__name__, error=str(error))

        def on_tool_start(self, serialized, input_str, **kwargs):
            self.recorder.record("tool.start", self._name(serialized, kwargs), input=input_str)

        def on_tool_end(self, output, **kwargs):
            self.recorder.record("tool.end", str(kwargs.get("name") or "tool"), output=output)

        def on_tool_error(self, error, **kwargs):
            self.recorder.record("tool.error", type(error).__name__, error=str(error))

    return SCWCallbackHandler()
