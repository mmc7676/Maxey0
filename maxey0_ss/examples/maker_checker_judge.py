from __future__ import annotations

from maxey0_ss.models import AgentSpec, LoopSpec, MCPServerRecord, SCWSpec, SkillRecord
from maxey0_ss.system import SuperSpaceSystem


def build_demo() -> SuperSpaceSystem:
    system = SuperSpaceSystem()
    system.register_mcp(MCPServerRecord("mcp.security", "stdio://security", "Security MCP", ["threat-modeling", "security-review"]))
    system.register_skill(SkillRecord("skill.threat-modeling", "Threat Modeling", "security", "software-engineering", "gate.threat-modeling", ["mcp.security"], [1.0, 0.0, 0.0]))
    system.create_scw(SCWSpec("SCW0", None, "security", ["skill.threat-modeling"]))
    system.create_scw(SCWSpec("SCW1", "SCW0", "security", ["skill.threat-modeling"]))
    system.create_scw(SCWSpec("SCW2", "SCW0", "security", ["skill.threat-modeling"]))
    system.create_scw(SCWSpec("SCW3", "SCW0", "security", ["skill.threat-modeling"]))
    system.add_agent(AgentSpec("Maxey1", "maker", "SCW1"))
    system.add_agent(AgentSpec("Maxey2", "checker", "SCW2"))
    system.add_agent(AgentSpec("Maxey3", "judge", "SCW3"))
    system.add_loop(LoopSpec("maker-checker-judge", "Maker → Checker → Judge", ["Maxey1", "Maxey2", "Maxey3"], 1))
    return system


def run_demo() -> dict:
    system = build_demo()
    scw1 = system.scw_runtime.start("SCW1", "Maxey1")
    scw2 = system.scw_runtime.start("SCW2", "Maxey2")
    scw3 = system.scw_runtime.start("SCW3", "Maxey3")
    system.drift_runtime.anchor(scw2.id, [1.0, 0.0, 0.0])
    drift = system.drift_runtime.inspect(scw2.id, [0.98, 0.02, 0.0], 0.15)
    return {"snapshot": system.snapshot(), "instances": [scw1.id, scw2.id, scw3.id], "drift": drift.__dict__}


if __name__ == "__main__":
    import json
    print(json.dumps(run_demo(), indent=2, sort_keys=True))
