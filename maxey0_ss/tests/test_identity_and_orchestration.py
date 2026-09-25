"""Two invariants that were conventions rather than code.

1. An SCW identifier is `SCW` followed by digits. `SCWSpec("SCW-JUDGE", ...)`
   was constructed without complaint, and the malformed identifier then reached
   addresses, cache namespaces and attestations.
2. Work reaches an agent by being assigned to a loop. `run()` took no task, so
   nothing recorded what had been assigned, and a declared loop that never ran
   was indistinguishable from one that had.
"""
import pytest

from maxey0_ss.execution.loop import ExecutionGraph, OrchestrationError
from maxey0_ss.gating.address import EnforceableAddress
from maxey0_ss.identity import (
    InvalidSCWIdentifier,
    instance_id,
    spec_id_of,
    validate_scw_id,
    validate_scw_reference,
)
from maxey0_ss.models import AgentSpec, LoopSpec, SCWSpec


def spec(scw_id: str, parent: str | None = None) -> SCWSpec:
    return SCWSpec(scw_id, parent, "Concept", [])


# --- the identifier invariant ------------------------------------------------


@pytest.mark.parametrize("bad", ["SCW-JUDGE", "SCW-MAKER", "SCW_1", "scw0", "SCW", "JUDGE", "SCW1.0", "", "SCW 1"])
def test_a_malformed_identifier_is_refused(bad):
    with pytest.raises(InvalidSCWIdentifier):
        validate_scw_id(bad)


@pytest.mark.parametrize("good", ["SCW0", "SCW1", "SCW42", "SCW100"])
def test_a_well_formed_identifier_is_accepted(good):
    assert validate_scw_id(good) == good


def test_case_is_significant():
    """`scw0` and `SCW0` would be two cache namespaces for one window."""
    with pytest.raises(InvalidSCWIdentifier):
        validate_scw_id("scw0")


def test_a_spec_cannot_be_built_with_a_malformed_id():
    with pytest.raises(InvalidSCWIdentifier):
        spec("SCW-JUDGE")


def test_a_malformed_parent_is_refused():
    with pytest.raises(InvalidSCWIdentifier):
        spec("SCW1", "ROOT")


def test_a_spec_cannot_parent_itself():
    with pytest.raises(ValueError, match="cannot be its own parent"):
        spec("SCW1", "SCW1")


def test_an_agent_cannot_bind_to_a_malformed_window():
    with pytest.raises(InvalidSCWIdentifier):
        AgentSpec("Maxey1", "maker", "SCW-MAKER")


def test_an_enforceable_address_rejects_a_malformed_final_segment():
    with pytest.raises(InvalidSCWIdentifier):
        EnforceableAddress.parse("scw://maxey0/context/observation/host-window/SCW-JUDGE")


def test_an_enforceable_address_accepts_a_well_formed_one():
    address = EnforceableAddress.parse("scw://maxey0/context/observation/host-window/SCW0")
    assert address.scw_id == "SCW0"


# --- instances --------------------------------------------------------------


def test_instances_carry_a_runtime_suffix():
    assert instance_id("SCW0", "runtime-a") == "SCW0@runtime-a"


def test_an_instance_of_a_malformed_spec_cannot_be_composed():
    with pytest.raises(InvalidSCWIdentifier):
        instance_id("SCW-MAKER", "runtime-a")


def test_an_instance_reference_resolves_to_its_spec():
    assert spec_id_of("SCW3@runtime-b") == "SCW3"
    assert spec_id_of("SCW3") == "SCW3"


def test_references_accept_both_forms_and_nothing_else():
    validate_scw_reference("SCW0")
    validate_scw_reference("SCW0@rt")
    with pytest.raises(InvalidSCWIdentifier):
        validate_scw_reference("SCW-JUDGE@rt")


# --- orchestration ----------------------------------------------------------


def graph() -> ExecutionGraph:
    g = ExecutionGraph()
    g.add_agent(AgentSpec("Maxey1", "maker", "SCW1"))
    g.add_agent(AgentSpec("Maxey2", "checker", "SCW2"))
    g.add_agent(AgentSpec("Maxey3", "judge", "SCW3"))
    g.add_loop(LoopSpec("mcj", "Maker -> Checker -> Judge", ["Maxey1", "Maxey2", "Maxey3"], 1))
    return g


def handlers(record=None):
    def make(role):
        def handler(state):
            if record is not None:
                record.append((role, state["task"]))
            return {"role": role, "task": state["task"]}
        return handler
    return {"Maxey1": make("maker"), "Maxey2": make("checker"), "Maxey3": make("judge")}


def test_dispatch_requires_a_task():
    """An agent running without one is doing work nobody asked for."""
    with pytest.raises(OrchestrationError, match="requires a task"):
        graph().run("mcj", handlers())


def test_a_blank_task_is_not_a_task():
    with pytest.raises(OrchestrationError, match="requires a task"):
        graph().run("mcj", handlers(), task="   ")


def test_the_assignment_is_recorded():
    g = graph()
    g.run("mcj", handlers(), task="write the developer guide")
    assert g.assignments[0]["task"] == "write the developer guide"
    assert [e["type"] for e in g.events].count("loop.assign") == 1


def test_every_agent_receives_the_task_in_order():
    seen: list = []
    g = graph()
    g.run("mcj", handlers(seen), task="draft")
    assert [role for role, _ in seen] == ["maker", "checker", "judge"]
    assert all(task == "draft" for _, task in seen)


def test_outputs_are_keyed_by_agent_not_role():
    """Keying by role let two agents sharing one overwrite each other."""
    g = graph()
    state = g.run("mcj", handlers(), task="draft")
    assert sorted(state["outputs"]) == ["Maxey1", "Maxey2", "Maxey3"]
    assert state["by_role"] == {"maker": ["Maxey1"], "checker": ["Maxey2"], "judge": ["Maxey3"]}


def test_a_loop_with_two_agents_in_one_role_is_refused():
    """A formation with two makers is a different formation, not a typo."""
    g = ExecutionGraph()
    g.add_agent(AgentSpec("Maxey1", "maker", "SCW1"))
    g.add_agent(AgentSpec("Maxey2", "maker", "SCW2"))
    with pytest.raises(OrchestrationError, match="duplicate role"):
        g.add_loop(LoopSpec("twin", "Two makers", ["Maxey1", "Maxey2"], 1))


def test_a_partial_formation_does_not_start():
    """Failing halfway leaves some agents run and the record incomplete."""
    g = graph()
    partial = {"Maxey1": lambda s: {}}
    with pytest.raises(OrchestrationError, match="no handler"):
        g.run("mcj", partial, task="draft")
    assert not any(e["type"] == "agent.step" for e in g.events)
    assert g.loops["mcj"].state == "created"


def test_a_declared_loop_that_never_ran_is_detectable():
    g = graph()
    assert g.unrun_loops() == ["mcj"]
    assert not g.dispatched("mcj")
    g.run("mcj", handlers(), task="draft")
    assert g.unrun_loops() == []
    assert g.dispatched("mcj")


def test_a_failed_loop_is_not_left_running():
    """`running` for ever is indistinguishable from work still happening."""
    g = graph()
    broken = handlers()
    broken["Maxey2"] = lambda s: (_ for _ in ()).throw(RuntimeError("checker exploded"))
    with pytest.raises(RuntimeError):
        g.run("mcj", broken, task="draft")
    assert g.loops["mcj"].state == "failed"
    assert any(e["type"] == "loop.failed" for e in g.events)


def test_a_loop_with_no_agents_is_refused():
    g = ExecutionGraph()
    with pytest.raises(OrchestrationError, match="declares no agents"):
        g.add_loop(LoopSpec("empty", "nobody", [], 1))


def test_steps_record_the_window_each_agent_ran_in():
    g = graph()
    g.run("mcj", handlers(), task="draft")
    steps = [e for e in g.events if e["type"] == "agent.step"]
    assert [s["scw"] for s in steps] == ["SCW1", "SCW2", "SCW3"]
