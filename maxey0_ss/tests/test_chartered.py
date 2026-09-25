"""A formation whose briefs are assembled by the gate rather than by trust.

The property under test is that an agent's input is *constructed* from its
charter. Not filtered afterwards, not requested politely — an artifact outside
a window's reach never enters that window's brief, so exceeding the charter is
not an action the agent is in a position to take.
"""
import pytest

from maxey0_ss.containment.hierarchy import ConstitutionViolation
from maxey0_ss.execution.chartered import CharteredFormation

TASK = "audit the loop catalog"


def formation() -> CharteredFormation:
    """Maker writes, checker reads the maker, judge reads both. Nothing else."""
    f = CharteredFormation("SCW0", reach={"SCW1", "SCW2", "SCW3"})
    f.charter("SCW1", reach=set())
    f.charter("SCW2", reach={"SCW1"})
    f.charter("SCW3", reach={"SCW1", "SCW2"})
    return f


# --- construction, not instruction -------------------------------------------


def test_an_agent_is_given_only_what_its_charter_grants():
    f = formation()
    f.deposit("SCW1", "draft", "the maker's draft")
    f.deposit("SCW2", "findings", "the checker's findings")

    checker = f.brief("SCW2", TASK)
    assert [a.name for a in checker.supplied] == ["draft", "findings"]


def test_content_outside_the_charter_never_enters_the_brief():
    """The maker cannot see the checker, so the text is absent from its input."""
    f = formation()
    f.deposit("SCW1", "draft", "the maker's draft")
    f.deposit("SCW2", "findings", "SECRET-CHECKER-TEXT")

    rendered = f.brief("SCW1", TASK).render()
    assert "SECRET-CHECKER-TEXT" not in rendered
    assert "the maker's draft" in rendered


def test_the_withheld_set_is_recorded_rather_than_merely_absent():
    """A refusal leaves no trace inside an agent, so it is recorded outside."""
    f = formation()
    f.deposit("SCW2", "findings", "checker text")
    maker = f.brief("SCW1", TASK)
    assert maker.supplied == []
    assert maker.withheld == [("SCW2", "findings")]


def test_the_judge_sees_both_upstream_windows():
    f = formation()
    f.deposit("SCW1", "draft", "d")
    f.deposit("SCW2", "findings", "c")
    f.deposit("SCW3", "verdict", "v")
    assert {a.name for a in f.brief("SCW3", TASK).supplied} == {"draft", "findings", "verdict"}


def test_reach_is_not_symmetric():
    """The checker reads the maker; the maker does not read the checker."""
    f = formation()
    f.deposit("SCW1", "draft", "d")
    f.deposit("SCW2", "findings", "c")
    assert len(f.brief("SCW2", TASK).supplied) == 2
    assert len(f.brief("SCW1", TASK).supplied) == 1


# --- the charter bounds the shape --------------------------------------------


def test_a_window_cannot_be_chartered_beyond_the_root():
    f = CharteredFormation("SCW0", reach={"SCW1"})
    with pytest.raises(ConstitutionViolation, match="exceeds parent"):
        f.charter("SCW1", reach={"SCW1", "SCW9"})


def test_a_nested_window_stays_inside_the_root():
    f = CharteredFormation("SCW0", reach={"SCW1", "SCW2"})
    f.charter("SCW1", reach={"SCW2"})
    with pytest.raises(ConstitutionViolation):
        f.charter("SCW2", reach={"SCW9"}, parent="SCW1")


def test_extent_caps_apply_to_a_formation():
    f = CharteredFormation("SCW0", reach={"SCW1", "SCW2", "SCW3"}, max_children=2)
    f.charter("SCW1", reach=set())
    f.charter("SCW2", reach=set())
    with pytest.raises(ConstitutionViolation, match="direct children"):
        f.charter("SCW3", reach=set())


# --- evidence ----------------------------------------------------------------


def test_every_artifact_is_a_separate_attested_decision():
    """One summary judgement would not show the shape of what was seen."""
    f = formation()
    f.deposit("SCW1", "draft", "d")
    f.deposit("SCW2", "findings", "c")
    before = len(f.crossings())
    f.brief("SCW1", TASK)
    assert len(f.crossings()) == before + 2


def test_the_chain_verifies_after_a_full_formation_run():
    f = formation()
    f.deposit("SCW1", "draft", "d")
    f.deposit("SCW2", "findings", "c")
    for scw in ("SCW1", "SCW2", "SCW3"):
        f.brief(scw, TASK)
    assert f.evidence()["verified"] is True


def test_denials_appear_in_the_chain_with_a_reason():
    f = formation()
    f.deposit("SCW2", "findings", "c")
    f.brief("SCW1", TASK)
    denied = [c for c in f.crossings() if not c["allowed"]]
    assert denied and all(c["reason"] for c in denied)


def test_the_evidence_counts_allowed_and_denied_separately():
    f = formation()
    f.deposit("SCW1", "draft", "d")
    f.deposit("SCW2", "findings", "c")
    f.brief("SCW1", TASK)
    ev = f.evidence()
    assert ev["allowed"] >= 1 and ev["denied"] >= 1


# --- accounting --------------------------------------------------------------


def test_duplication_is_reported_rather_than_hidden():
    """Content reaching three windows is paid for three times. Say so."""
    f = formation()
    f.deposit("SCW1", "draft", "x" * 4000)  # ~1000 tokens
    briefs = [f.brief(s, TASK) for s in ("SCW1", "SCW2", "SCW3")]
    acc = f.accounting(briefs)
    assert acc["distinct_tokens"] == 1000
    assert acc["supplied_tokens_total"] == 3000
    assert acc["duplicated_tokens"] == 2000


def test_withholding_reduces_what_is_paid_for():
    """Narrower reach is cheaper as well as safer."""
    f = formation()
    f.deposit("SCW2", "findings", "y" * 4000)
    wide = f.accounting([f.brief("SCW3", TASK)])
    narrow = f.accounting([f.brief("SCW1", TASK)])
    assert narrow["supplied_tokens_total"] == 0
    assert wide["supplied_tokens_total"] == 1000


# --- regressions from the code review ---------------------------------------


def test_depositing_the_same_name_twice_replaces_rather_than_duplicates():
    """A second artifact under one key was billed and then dropped from distinct."""
    f = formation()
    f.deposit("SCW1", "doc", "x" * 4000)
    f.deposit("SCW1", "doc", "y" * 4000)
    acc = f.accounting([f.brief("SCW1", TASK)])
    assert acc["supplied_tokens_total"] == 1000
    assert acc["duplicated_tokens"] == 0


def test_a_replaced_deposit_serves_the_new_content():
    f = formation()
    f.deposit("SCW1", "doc", "OLD")
    f.deposit("SCW1", "doc", "NEW")
    rendered = f.brief("SCW1", TASK).render()
    assert "NEW" in rendered and "OLD" not in rendered
