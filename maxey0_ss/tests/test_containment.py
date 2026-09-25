"""Containment: enforcement is swappable, and its evidence is falsifiable.

The property under test is the one the product claims — that containment holds
independently of model behavior, and that anyone can check it held without
being given the engine that enforced it.
"""
import pytest

from maxey0_ss.containment import (
    GENESIS,
    AttestationLog,
    ContainmentError,
    ContainmentProvider,
    Operation,
    StructuralContainment,
    UnknownContainmentProvider,
    containment_provider,
)
from maxey0_ss.models import SCWInstance, SemanticAddress


def instance(scw_id: str, readable=(), writable=()) -> SCWInstance:
    return SCWInstance(
        id=scw_id, spec_id=scw_id, owner="test", runtime_id="rt",
        address=SemanticAddress("maxey0", "test", "containment", scw_id),
        readable=set(readable), writable=set(writable),
    )


def controller(*instances: SCWInstance) -> StructuralContainment:
    c = StructuralContainment()
    for i in instances:
        c.register(i)
    return c


# --- the seam ---------------------------------------------------------------


def test_the_default_provider_satisfies_the_protocol():
    assert isinstance(containment_provider(), ContainmentProvider)


def test_an_unavailable_provider_is_refused_not_downgraded(monkeypatch):
    """Falling back would mean believing you run a stricter engine than you do."""
    monkeypatch.setenv("MAXEY0_CONTAINMENT_PROVIDER", "semantic-premium")
    with pytest.raises(UnknownContainmentProvider, match="not available"):
        containment_provider()


def test_every_decision_names_the_provider_that_made_it():
    c = controller(instance("SCW0"))
    assert c.decide(Operation.READ, "SCW0", "SCW1").provider == "structural"


# --- enforcement ------------------------------------------------------------


def test_a_window_may_always_reach_itself():
    assert controller(instance("SCW0")).can_read("SCW0", "SCW0")


def test_an_undeclared_target_is_refused():
    c = controller(instance("SCW0"), instance("SCW1"))
    assert not c.can_read("SCW0", "SCW1")


def test_a_declared_target_is_allowed():
    c = controller(instance("SCW0", readable={"SCW1"}), instance("SCW1"))
    assert c.can_read("SCW0", "SCW1")


def test_an_unregistered_agent_fails_closed():
    """No declared reach means no reach, not unrestricted reach."""
    decision = controller().decide(Operation.READ, "GHOST", "SCW0")
    assert not decision.allowed
    assert "not registered" in decision.reason


def test_reading_is_not_writing():
    c = controller(instance("SCW0", readable={"SCW1"}), instance("SCW1"))
    assert c.can_read("SCW0", "SCW1")
    assert not c.can_write("SCW0", "SCW1")


def test_a_bridge_widens_reach_and_is_recorded():
    c = controller(instance("SCW0"), instance("SCW1"))
    assert not c.can_read("SCW0", "SCW1")
    c.open_bridge("SCW0", "SCW1")
    assert c.can_read("SCW0", "SCW1")
    assert any(e.decision.operation is Operation.BRIDGE for e in c.log.entries())


def test_disjoint_private_regions_are_reported_disjoint():
    c = controller(instance("SCW0"), instance("SCW1"))
    assert c.assert_private_disjoint("SCW0", "SCW1")


def test_require_read_raises_on_refusal():
    with pytest.raises(ContainmentError, match="denied"):
        controller(instance("SCW0"), instance("SCW1")).require_read("SCW0", "SCW1")


# --- evidence ---------------------------------------------------------------


def test_every_decision_is_recorded():
    c = controller(instance("SCW0", readable={"SCW1"}), instance("SCW1"))
    c.can_read("SCW0", "SCW1")
    c.can_write("SCW0", "SCW1")
    assert len(c.log) == 2


def test_an_empty_log_starts_at_genesis():
    assert AttestationLog().head == GENESIS


def test_the_chain_verifies():
    c = controller(instance("SCW0"), instance("SCW1"))
    for _ in range(5):
        c.can_read("SCW0", "SCW1")
    assert c.log.verify().ok


def test_an_edited_record_breaks_the_chain():
    """The evidence must not be quietly rewritable."""
    c = controller(instance("SCW0"), instance("SCW1"))
    c.can_read("SCW0", "SCW1")
    c.can_read("SCW0", "SCW1")
    records = c.log.export()
    records[0]["allowed"] = True  # flip a denial into an approval
    result = AttestationLog.verify_records(records)
    assert not result.ok
    assert result.broken_at == 0
    assert "edited" in result.reason


def test_a_deleted_record_breaks_the_chain():
    """Chaining on prev_digest is what makes omission detectable."""
    c = controller(instance("SCW0"), instance("SCW1"))
    for _ in range(3):
        c.can_read("SCW0", "SCW1")
    records = c.log.export()
    del records[1]
    result = AttestationLog.verify_records(records)
    assert not result.ok
    assert "removed, reordered, or inserted" in result.reason


def test_reordered_records_break_the_chain():
    c = controller(instance("SCW0"), instance("SCW1"))
    for _ in range(3):
        c.can_read("SCW0", "SCW1")
    records = c.log.export()
    records[0], records[1] = records[1], records[0]
    assert not AttestationLog.verify_records(records).ok


def test_evidence_verifies_with_no_provider_present():
    """The point of the split: check the claim without the engine."""
    c = controller(instance("SCW0"), instance("SCW1"))
    c.can_read("SCW0", "SCW1")
    exported = c.log.export()
    del c  # the engine is gone; the evidence still stands on its own
    assert AttestationLog.verify_records(exported).ok


def test_denials_are_isolatable():
    c = controller(instance("SCW0", readable={"SCW1"}), instance("SCW1"))
    c.can_read("SCW0", "SCW1")   # allowed
    c.can_read("SCW1", "SCW0")   # denied
    denials = c.log.denials()
    assert len(denials) == 1
    assert denials[0]["agent_scw"] == "SCW1"


def test_the_summary_discloses_no_mechanism():
    c = controller(instance("SCW0"), instance("SCW1"))
    c.can_read("SCW0", "SCW1")
    summary = c.log.summary()
    assert summary["entries"] == 1
    assert summary["denied"] == 1
    assert summary["chain_intact"] is True
    assert summary["providers"] == ["structural"]
    # A reason explains the outcome; it must not carry the rule that produced it.
    assert "readable" not in repr(summary)
