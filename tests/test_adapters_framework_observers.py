"""Framework observers record digests into the containment log, never content."""
from __future__ import annotations

import json
import sys
import types
from types import SimpleNamespace

import pytest

from maxey0_ss.adapters.harnesses import langchain as lc
from maxey0_ss.adapters.harnesses import openai_agents as oa
from maxey0_ss.adapters.harnesses.observe import OBSERVED_REASON, FrameworkRecorder
from maxey0_ss.containment.attestation import AttestationLog

SECRET = "my private prompt 12345"


@pytest.fixture
def fake_langchain(monkeypatch):
    core = types.ModuleType("langchain_core")
    cb = types.ModuleType("langchain_core.callbacks")

    class BaseCallbackHandler:
        def __init__(self) -> None:
            pass

    cb.BaseCallbackHandler = BaseCallbackHandler
    core.callbacks = cb
    monkeypatch.setitem(sys.modules, "langchain_core", core)
    monkeypatch.setitem(sys.modules, "langchain_core.callbacks", cb)


@pytest.fixture
def fake_agents(monkeypatch):
    agents = types.ModuleType("agents")
    tracing = types.ModuleType("agents.tracing")

    class TracingProcessor:
        pass

    registered = []
    tracing.TracingProcessor = TracingProcessor
    agents.tracing = tracing
    agents.add_trace_processor = registered.append
    monkeypatch.setitem(sys.modules, "agents", agents)
    monkeypatch.setitem(sys.modules, "agents.tracing", tracing)
    return registered


def _no_content(log: AttestationLog) -> None:
    assert SECRET not in json.dumps(log.export())
    assert log.verify().ok


def test_langchain_handler_records_all_events(fake_langchain):
    log = AttestationLog()
    h = lc.LangChainAdapter().callback_handler(log, "SCW3")
    h.on_chat_model_start({"name": "chat"}, [[SimpleNamespace(content=SECRET)]])
    h.on_llm_end(SimpleNamespace(generations=[[SimpleNamespace(text=SECRET)]]))
    h.on_tool_start({"name": "search"}, SECRET)
    h.on_tool_end(SECRET, name="search")
    h.on_llm_error(ValueError(SECRET))
    h.on_tool_error(RuntimeError(SECRET))
    recs = log.export()
    assert [r["metadata"]["kind"] for r in recs] == [
        "llm.start", "llm.end", "tool.start", "tool.end", "llm.error", "tool.error"]
    assert all(r["agent_scw"] == "SCW3" and r["reason"] == OBSERVED_REASON and r["allowed"] for r in recs)
    assert recs[2]["metadata"]["name"] == "search"
    assert recs[2]["metadata"]["input"]["chars"] == len(SECRET)
    _no_content(log)


def test_openai_processor_records_generation_and_function(fake_agents):
    log = AttestationLog()
    proc = oa.OpenAIAgentsAdapter().install_trace_processor(log, "SCW4")
    assert fake_agents == [proc]
    proc.on_span_end(SimpleNamespace(span_data=SimpleNamespace(type="generation", model="gpt", input=[SECRET], output=[SECRET]), error=None))
    proc.on_span_end(SimpleNamespace(span_data=SimpleNamespace(type="function", name="calc", input=SECRET, output=SECRET), error={"message": SECRET}))
    proc.on_span_end(SimpleNamespace(span_data=SimpleNamespace(type="agent"), error=None))
    recs = log.export()
    assert [(r["metadata"]["kind"], r["metadata"]["name"]) for r in recs] == [
        ("llm.end", "gpt"), ("tool.end", "calc"), ("tool.error", "calc")]
    _no_content(log)


def test_missing_frameworks_fail_cleanly(monkeypatch):
    monkeypatch.setitem(sys.modules, "langchain_core", None)
    monkeypatch.setitem(sys.modules, "langchain_core.callbacks", None)
    monkeypatch.setitem(sys.modules, "agents", None)
    monkeypatch.setitem(sys.modules, "agents.tracing", None)
    with pytest.raises(RuntimeError, match="optional"):
        lc.make_callback_handler(AttestationLog(), "SCW1")
    with pytest.raises(RuntimeError, match="optional"):
        oa.OpenAIAgentsAdapter().install_trace_processor(AttestationLog(), "SCW1")


def test_recorder_fails_closed_on_bad_target():
    with pytest.raises(TypeError):
        FrameworkRecorder(object(), scw_id="SCW1", harness="x")
    with pytest.raises(ValueError):
        FrameworkRecorder(AttestationLog(), scw_id="", harness="x")


def test_recorder_accepts_system_log():
    log = AttestationLog()
    system = SimpleNamespace(context=SimpleNamespace(isolation=SimpleNamespace(log=log)))
    FrameworkRecorder(system, scw_id="SCW1", harness="x").record("tool.end", "t", output="o")
    assert len(log) == 1
