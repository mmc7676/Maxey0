from maxey0_ss.adapters.harnesses import ClaudeAgentSDKAdapter, GoogleADKAdapter, LangChainAdapter, OpenAIAgentsAdapter
from maxey0_ss.models import AgentSpec, MCPServerRecord, SCWSpec, SkillRecord
from maxey0_ss.system import SuperSpaceSystem


def build_system():
    system = SuperSpaceSystem()
    system.register_mcp(MCPServerRecord("mcp-sec", "stdio://security", "Security MCP", ["threat-modeling"]))
    system.register_skill(SkillRecord("threat-model", "Threat Modeling", "Security", "Engineering", "gate-security", ["mcp-sec"]))
    system.create_scw(SCWSpec("SCW2", None, "Security", ["threat-model"]))
    agent = AgentSpec("Maxey2", "checker", "SCW2")
    system.add_agent(agent)
    return system, agent


def test_all_harness_adapters_bind():
    system, agent = build_system()
    adapters = [ClaudeAgentSDKAdapter(), OpenAIAgentsAdapter(), LangChainAdapter(), GoogleADKAdapter()]
    bindings = [a.bind_maxey0_agent(system, agent) for a in adapters]
    assert {b.harness for b in bindings} == {"claude-agent-sdk", "openai-agents", "langchain", "google-adk"}
    assert all(b.scw_id == "SCW2@scw-runtime-0" for b in bindings)


def test_mcp_delivery_routes_registered_session():
    system, _ = build_system()
    system.mcp_delivery.client.bind("mcp-sec", lambda method, **params: {"method": method, "params": params})
    result = system.mcp_delivery.deliver("mcp-sec", "resources/read", uri="security://threat-model")
    assert result.delivered is True
    assert result.result["method"] == "resources/read"


def test_a2a_directory_contains_maxey0_host():
    system, _ = build_system()
    records = system.a2a_directory.search("semantic-context-routing")
    assert records and records[0].id == "maxey0-ss"


def test_distribution_surface_is_explicit():
    system, _ = build_system()
    snapshot = system.snapshot()
    assert "a2a" in snapshot
    assert snapshot["a2a"][0]["id"] == "maxey0-ss"
