from maxey0_ss.adapters.a2a import A2AHost, A2ARequest
from maxey0_ss.examples.maker_checker_judge import build_demo
from maxey0_ss.semantic.math import cosine_distance, superposition


def test_semantic_distance_identity():
    assert cosine_distance([1, 0], [1, 0]) == 0.0


def test_superposition():
    assert superposition([[1, 0], [0, 1]], [1, 1]) == [0.5, 0.5]


def test_demo_graph_and_a2a():
    system = build_demo()
    result = A2AHost(system).handle(A2ARequest("external-agent", "threat modeling", concept="security", skill="threat modeling"))
    assert result["accepted"] is True
    assert "skill.threat-modeling" in result["candidate_skills"]
    assert system.observatory.verify()


def test_scw_instances_have_independent_runtime_identity():
    system = build_demo()
    a = system.scw_runtime.start("SCW1", "Maxey1")
    b = system.scw_runtime.start("SCW2", "Maxey2")
    assert a.id != b.id
    assert a.runtime_id == b.runtime_id == "scw-runtime-0"
    assert a.address.concept == b.address.concept == "security"
