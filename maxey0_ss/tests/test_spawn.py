"""The spawn algebra, checked against the run it was derived from.

The last case pins the algorithm to the actual three-agent run recorded in
examples/chartered_run_evidence.json. If the rules drift from what was really
dispatched, that test fails — which is the difference between a formula and a
description of one.
"""
import pytest

from maxey0_ss.execution.spawn import (
    ROLES,
    Shape,
    Task,
    effort,
    max_formation,
    needs_window,
    plan,
    shape,
    supplied_cost,
    terminates,
)


# --- the window predicate G(T) ----------------------------------------------


def test_no_downstream_need_means_no_window():
    assert not needs_window(Task("rename a local variable"))


@pytest.mark.parametrize("flag", ["encapsulation", "observability", "irreversible"])
def test_any_one_condition_forces_a_window(flag):
    assert needs_window(Task("t", **{flag: True}))


# --- the effort function E = V / M ------------------------------------------


def test_a_deterministic_check_collapses_effort_however_high_the_stakes():
    """The failure this prevents: ultracode spent on git plumbing."""
    assert effort(Task("strip commit trailers", checkability=1.0, stakes=1.0)) == 0.0


def test_an_unverifiable_judgement_raises_effort_to_meet_the_stakes():
    assert effort(Task("is this architecture right", checkability=0.1, stakes=0.9)) > 4.0


def test_effort_rises_as_checkability_falls():
    weights = [effort(Task("t", checkability=m, stakes=0.5)) for m in (0.9, 0.5, 0.1)]
    assert weights == sorted(weights)


def test_stakes_and_checkability_are_bounded():
    with pytest.raises(ValueError, match="must lie in"):
        Task("t", checkability=1.5)


# --- the shape function σ(T) -------------------------------------------------


def test_trivial_checkable_work_gets_no_agent():
    assert shape(Task("count the trailers", trivial=True, checkability=1.0)) is Shape.INLINE


def test_checkable_work_gets_one_agent():
    assert shape(Task("run the migration", checkability=1.0, stakes=0.8)) is Shape.SINGLE


def test_an_unverifiable_judgement_gets_the_full_loop():
    assert shape(Task("adjudicate the design", checkability=0.1, stakes=0.9)) is Shape.LOOP


def test_encapsulation_forces_a_partition_regardless_of_checkability():
    """Isolation is not an effort question."""
    t = Task("two consumers", checkability=1.0, stakes=0.0, encapsulation=True)
    assert effort(t) == 0.0
    assert shape(t) is Shape.PAIR


def test_an_irreversible_task_escalates_to_a_judge():
    modest = Task("publish it", checkability=0.5, stakes=0.6, irreversible=True)
    assert shape(modest) is Shape.LOOP


def test_trivial_does_not_override_a_downstream_need():
    assert shape(Task("t", trivial=True, observability=True)) is not Shape.INLINE


def test_every_shape_declares_its_roles():
    assert all(s in ROLES for s in Shape)
    assert ROLES[Shape.LOOP] == ("maker", "checker", "judge")


# --- the bound ---------------------------------------------------------------


def test_an_uncapped_formation_has_no_bound():
    assert max_formation(None, None, None) == float("inf")
    assert not terminates(None, None, None)


def test_a_total_cap_alone_bounds_everything():
    assert max_formation(None, None, 4) == 5.0
    assert terminates(None, None, 4)


def test_the_geometric_bound_is_exact():
    """B=3, D=2 -> 1 + 3 + 9 = 13."""
    assert max_formation(3, 2, None) == 13.0


def test_a_linear_chain_is_bounded_by_depth():
    assert max_formation(1, 5, None) == 6.0


def test_the_strictest_cap_governs():
    assert max_formation(3, 2, 4) == 5.0


def test_depth_without_breadth_does_not_terminate():
    """A shallow tree of unbounded width is still unbounded."""
    assert not terminates(None, 2, None)


# --- the descent -------------------------------------------------------------


def test_a_plan_with_no_issues_is_just_the_formation():
    p = plan(Task("audit", checkability=0.1, stakes=0.9))
    assert p.size() == 3 and p.max_depth() == 0


def test_an_issue_expands_one_level_down():
    """The inward loop: an issue is a task, handled by the same function."""
    p = plan(
        Task("audit", checkability=0.1, stakes=0.9),
        issues={"audit:maker": [Task("scw is broken", checkability=1.0, stakes=0.5)]},
    )
    assert p.max_depth() == 1
    assert p.size() == 4


def test_the_descent_is_refused_past_the_depth_cap():
    p = plan(
        Task("audit", checkability=0.1, stakes=0.9),
        issues={"audit:maker": [Task("issue", checkability=1.0, stakes=0.5)]},
        depth=0,
    )
    assert p.max_depth() == 0
    assert any("depth" in reason for _, reason in p.refused)


def test_a_formation_cap_stops_expansion_and_says_so():
    p = plan(Task("audit", checkability=0.1, stakes=0.9), total=1)
    assert p.size() <= 2
    assert p.refused


def test_refusals_are_reported_rather_than_raised():
    """The caps are what is being evaluated, so dying at the first one is useless."""
    p = plan(Task("audit", checkability=0.1, stakes=0.9), breadth=2)
    assert p.size() == 2
    assert any("breadth" in reason for _, reason in p.refused)


def test_nested_issues_recurse():
    p = plan(
        Task("a", checkability=0.1, stakes=0.9),
        issues={
            "a:maker": [Task("b", checkability=0.1, stakes=0.9)],
            "b:maker": [Task("c", checkability=1.0, stakes=0.1)],
        },
        depth=4,
    )
    assert p.max_depth() == 2


# --- the cost ----------------------------------------------------------------


def test_shared_content_is_billed_once_per_role():
    c = supplied_cost(roles=3, per_role=0, shared=1000)
    assert c["supplied"] == 3000 and c["distinct"] == 1000
    assert c["duplicated"] == 2000


def test_private_content_is_not_duplication():
    c = supplied_cost(roles=3, per_role=500, shared=0)
    assert c["duplicated"] == 0


def test_the_shareable_amount_is_what_a_prefix_cache_could_reuse():
    assert supplied_cost(roles=3, per_role=100, shared=1000)["shareable"] == 2000


def test_a_single_role_shares_nothing_with_itself():
    assert supplied_cost(roles=1, per_role=100, shared=1000)["shareable"] == 0


# --- pinned to the recorded run ---------------------------------------------


def test_the_algebra_reproduces_the_run_that_was_actually_dispatched():
    """The chartered run: an unverifiable judgement, observable downstream.

    Recorded in examples/chartered_run_evidence.json — 3 roles, depth 0,
    15 attested crossings over 3 windows.
    """
    task = Task(
        "propose the minimal prompt-cache change",
        checkability=0.2,
        stakes=0.9,
        encapsulation=True,
        observability=True,
    )
    assert needs_window(task)
    assert shape(task) is Shape.LOOP
    p = plan(task, breadth=3, depth=2, total=3)
    assert [s.role for s in p.steps] == ["maker", "checker", "judge"]
    assert p.size() == 3
    assert not p.refused
    assert terminates(3, 2, 3)


# --- regressions from the code review ---------------------------------------


def test_the_formation_cap_bounds_nested_expansion():
    """result.size() read 0 for the whole expansion, so the cap never bound."""
    chain = {f"{n}:maker": [Task(chr(98 + i), checkability=0.1, stakes=0.9)]
             for i, n in enumerate("abcdef")}
    p = plan(Task("a", checkability=0.1, stakes=0.9), issues=chain, total=2, depth=10)
    assert p.size() <= 3
    assert any("formation cap" in reason for _, reason in p.refused)


def test_an_inline_task_reports_issues_it_cannot_carry():
    """Shape.INLINE has no roles, so its issues used to vanish silently."""
    p = plan(
        Task("triv", trivial=True, checkability=1.0),
        issues={"triv:maker": [Task("real issue", checkability=0.1, stakes=0.9)]},
    )
    assert p.size() == 0
    assert any("no role to carry" in reason for _, reason in p.refused)


def test_zero_roles_costs_nothing_rather_than_negative():
    assert supplied_cost(roles=0, per_role=0, shared=1000) == {
        "supplied": 0, "distinct": 0, "duplicated": 0, "shareable": 0,
    }


def test_negative_roles_is_refused():
    with pytest.raises(ValueError, match="must not be negative"):
        supplied_cost(roles=-1, per_role=0, shared=0)
