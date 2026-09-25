"""The hierarchy invariant: nothing beneath an SCW can reach outside it.

`SCWSpec.parent_id` recorded a tree that no enforcement path read. Reach was
declared per instance, so a child could name what its parent could not, and a
bridge could grant what no charter granted. These tests fix the shape of the
constraint that now holds, including the two places it used to leak: bridges,
and re-declaration after chartering.
"""
import pytest

from maxey0_ss.containment import Operation, StructuralContainment
from maxey0_ss.containment.attestation import AttestationLog
from maxey0_ss.containment.hierarchy import (
    Constitution,
    ConstitutionTree,
    ConstitutionViolation,
    DenialBreaker,
    bounded,
)
from maxey0_ss.models import SCWInstance, SemanticAddress


def address(scw_id: str) -> SemanticAddress:
    return SemanticAddress("maxey0", "context", "observation", scw_id)


def instance(scw_id: str, readable=(), writable=()) -> SCWInstance:
    return SCWInstance(
        id=scw_id, spec_id=scw_id.split("@")[0], owner="Maxey0", runtime_id="rt",
        address=address(scw_id.split("@")[0]),
        readable=set(readable), writable=set(writable),
    )


# --- derivation --------------------------------------------------------------


def test_a_child_inherits_the_parent_constitution_when_it_asks_for_nothing():
    parent = bounded({"SCW1", "SCW2"})
    assert parent.derive(None) is parent


def test_a_child_may_narrow_its_inherited_reach():
    parent = bounded({"SCW1", "SCW2", "SCW3"})
    child = parent.derive(Constitution(reach=frozenset({"SCW1"})))
    assert child.reach == frozenset({"SCW1"})


def test_a_child_cannot_widen_its_inherited_reach():
    """The core refusal. Previously this was not checked anywhere."""
    parent = bounded({"SCW1"})
    with pytest.raises(ConstitutionViolation, match="exceeds parent"):
        parent.derive(Constitution(reach=frozenset({"SCW1", "SCW9"})))


def test_widening_is_refused_rather_than_clamped():
    """Clamping would hide the attempt; the refusal is the evidence."""
    parent = bounded({"SCW1"})
    with pytest.raises(ConstitutionViolation) as e:
        parent.derive(Constitution(reach=frozenset({"SCW9"})))
    assert "SCW9" in str(e.value)


def test_a_child_cannot_request_unbounded_reach_under_a_bounded_parent():
    with pytest.raises(ConstitutionViolation, match="unbounded reach"):
        bounded({"SCW1"}).derive(Constitution(reach=None))


def test_a_child_cannot_be_bridgeable_under_a_parent_that_is_not():
    parent = Constitution(reach=frozenset({"SCW1"}), bridgeable=False)
    with pytest.raises(ConstitutionViolation, match="bridgeable"):
        parent.derive(Constitution(reach=frozenset({"SCW1"}), bridgeable=True))


@pytest.mark.parametrize(
    "parent_cap,child_cap,expected", [(3, 5, 3), (5, 3, 3), (None, 4, 4), (4, None, 4), (None, None, None)]
)
def test_caps_take_the_stricter_of_the_two(parent_cap, child_cap, expected):
    parent = Constitution(reach=frozenset({"SCW1"}), max_depth=parent_cap)
    child = parent.derive(Constitution(reach=frozenset({"SCW1"}), max_depth=child_cap))
    assert child.max_depth == expected


# --- the induction -----------------------------------------------------------


def test_reach_narrows_monotonically_down_a_chain():
    """The invariant, stated as induction: every descendant is inside the root."""
    tree = ConstitutionTree()
    tree.charter_root("SCW0", bounded({"SCW1", "SCW2", "SCW3"}))
    tree.charter("SCW1", "SCW0", Constitution(reach=frozenset({"SCW2", "SCW3"})))
    tree.charter("SCW2", "SCW1", Constitution(reach=frozenset({"SCW3"})))
    tree.charter("SCW3", "SCW2", Constitution(reach=frozenset()))

    root_reach = tree.constitution_of("SCW0").reach
    for scw in ("SCW1", "SCW2", "SCW3"):
        assert tree.constitution_of(scw).reach <= root_reach


def test_no_descendant_can_reach_outside_the_root_however_deep():
    tree = ConstitutionTree()
    tree.charter_root("SCW0", bounded({"SCW1", "SCW2"}))
    parent = "SCW0"
    for n in range(1, 6):
        child = f"SCW{n}"
        tree.charter(child, parent)
        parent = child
    for n in range(1, 6):
        assert not tree.permits(f"SCW{n}", "SCW99")


def test_an_unchartered_window_permits_nothing():
    """Fail closed: reach nobody granted is reach nobody has."""
    assert not ConstitutionTree().permits("SCW7", "SCW1")


def test_a_child_cannot_derive_from_an_absent_parent():
    with pytest.raises(ConstitutionViolation, match="not chartered"):
        ConstitutionTree().charter("SCW1", "SCW0")


def test_an_scw_cannot_be_chartered_twice():
    tree = ConstitutionTree()
    tree.charter_root("SCW0")
    tree.charter("SCW1", "SCW0")
    with pytest.raises(ConstitutionViolation, match="already chartered"):
        tree.charter("SCW1", "SCW0")


def test_narrowing_an_existing_charter_is_allowed_but_widening_is_not():
    tree = ConstitutionTree()
    tree.charter_root("SCW0", bounded({"SCW1", "SCW2"}))
    tree.charter("SCW1", "SCW0")
    tree.narrow("SCW1", Constitution(reach=frozenset({"SCW2"})))
    assert tree.constitution_of("SCW1").reach == frozenset({"SCW2"})
    with pytest.raises(ConstitutionViolation):
        tree.narrow("SCW1", Constitution(reach=frozenset({"SCW2", "SCW8"})))


# --- extent ------------------------------------------------------------------


def test_depth_is_capped():
    tree = ConstitutionTree()
    tree.charter_root("SCW0", bounded({"SCW1"}, max_depth=2))
    tree.charter("SCW1", "SCW0")
    tree.charter("SCW2", "SCW1")
    with pytest.raises(ConstitutionViolation, match="depth 3"):
        tree.charter("SCW3", "SCW2")


def test_direct_children_are_capped():
    tree = ConstitutionTree()
    tree.charter_root("SCW0", bounded({"SCW1"}, max_children=2))
    tree.charter("SCW1", "SCW0")
    tree.charter("SCW2", "SCW0")
    with pytest.raises(ConstitutionViolation, match="direct children"):
        tree.charter("SCW3", "SCW0")


def test_total_descendants_are_capped_across_the_whole_subtree():
    """A cap on direct children alone is escaped by spawning one level down."""
    tree = ConstitutionTree()
    tree.charter_root("SCW0", bounded({"SCW1"}, max_descendants=3))
    tree.charter("SCW1", "SCW0")
    tree.charter("SCW2", "SCW1")
    tree.charter("SCW3", "SCW2")
    with pytest.raises(ConstitutionViolation, match="descendants"):
        tree.charter("SCW4", "SCW3")


def test_a_formation_cannot_exhaust_the_host_while_staying_inside_its_reach():
    """Reach containment alone does not bound growth. This is why caps exist."""
    tree = ConstitutionTree()
    tree.charter_root("SCW0", bounded({"SCW1"}, max_descendants=4))
    chartered = 0
    for n in range(1, 40):
        try:
            tree.charter(f"SCW{n}", "SCW0")
            chartered += 1
        except ConstitutionViolation:
            break
    assert chartered == 4


# --- the provider ------------------------------------------------------------


def charted_provider():
    tree = ConstitutionTree()
    tree.charter_root("SCW0", bounded({"SCW1", "SCW2"}))
    tree.charter("SCW1", "SCW0", Constitution(reach=frozenset({"SCW2"})))
    tree.charter("SCW2", "SCW0", Constitution(reach=frozenset()))
    return StructuralContainment(tree=tree), tree


def test_a_declared_reach_beyond_the_charter_is_refused_at_registration():
    provider, _ = charted_provider()
    with pytest.raises(ConstitutionViolation, match="does not grant"):
        provider.register(instance("SCW2", readable={"SCW1"}))


def test_the_refusal_at_registration_is_attested():
    provider, _ = charted_provider()
    with pytest.raises(ConstitutionViolation):
        provider.register(instance("SCW2", readable={"SCW1"}))
    last = provider.log.entries()[-1].decision
    assert last.operation is Operation.SPAWN
    assert not last.allowed


def test_the_constitution_outranks_the_declared_read_set():
    """Declaring reach must not be the same as having it."""
    tree = ConstitutionTree()
    tree.charter_root("SCW0", bounded({"SCW1", "SCW2"}))
    tree.charter("SCW2", "SCW0", Constitution(reach=frozenset()))
    provider = StructuralContainment(tree=tree)
    sneaky = instance("SCW2")
    provider.instances["SCW2"] = sneaky      # bypass registration
    sneaky.readable.add("SCW1")              # widen after the fact
    decision = provider.decide(Operation.READ, "SCW2", "SCW1")
    assert not decision.allowed
    assert "chartered constitution" in decision.reason


def test_a_bridge_cannot_exceed_the_constitution():
    """The leak that made the hierarchy advisory."""
    provider, _ = charted_provider()
    provider.register(instance("SCW2"))
    with pytest.raises(ConstitutionViolation, match="does not grant"):
        provider.open_bridge("SCW2", "SCW1")


def test_a_bridge_inside_the_constitution_still_works():
    provider, _ = charted_provider()
    provider.register(instance("SCW1"))
    provider.open_bridge("SCW1", "SCW2")
    assert provider.decide(Operation.READ, "SCW1", "SCW2").allowed


def test_instances_resolve_against_a_charter_written_for_specs():
    provider, _ = charted_provider()
    provider.register(instance("SCW1@rt", readable={"SCW2@rt"}))
    assert provider.decide(Operation.READ, "SCW1@rt", "SCW2@rt").allowed
    assert not provider.decide(Operation.READ, "SCW1@rt", "SCW9@rt").allowed


def test_without_a_tree_the_provider_behaves_as_before():
    """Chartering is opt-in; an unchartered deployment must not break."""
    provider = StructuralContainment()
    provider.register(instance("SCW1", readable={"SCW2"}))
    assert provider.decide(Operation.READ, "SCW1", "SCW2").allowed


def test_chartering_without_a_tree_is_refused_rather_than_silently_useless():
    with pytest.raises(ConstitutionViolation, match="no constitution tree"):
        StructuralContainment().charter("SCW1", "SCW0")


def test_a_successful_charter_is_attested():
    tree = ConstitutionTree()
    tree.charter_root("SCW0", bounded({"SCW1"}))
    provider = StructuralContainment(tree=tree)
    provider.charter("SCW1", "SCW0")
    last = provider.log.entries()[-1].decision
    assert last.operation is Operation.SPAWN and last.allowed


# --- reading the chain back --------------------------------------------------


def test_the_breaker_counts_refusals_from_the_chain():
    log = AttestationLog()
    provider = StructuralContainment(log=log)
    breaker = DenialBreaker(log, threshold=3)
    provider.register(instance("SCW1"))
    for _ in range(3):
        provider.decide(Operation.READ, "SCW1", "SCW9")
    assert breaker.denials_by("SCW1") == 3
    assert breaker.tripped("SCW1")


def test_the_breaker_refuses_once_the_threshold_is_reached():
    """Persistence becomes refusable. Previously refusals were free and endless."""
    log = AttestationLog()
    breaker = DenialBreaker(log, threshold=2)
    provider = StructuralContainment(log=log, breaker=breaker)
    provider.register(instance("SCW1"))
    for _ in range(2):
        provider.decide(Operation.READ, "SCW1", "SCW9")
    with pytest.raises(ConstitutionViolation, match="refused crossings"):
        provider.open_bridge("SCW1", "SCW2")


def test_the_breaker_does_not_punish_a_window_that_stays_inside_its_reach():
    log = AttestationLog()
    breaker = DenialBreaker(log, threshold=2)
    provider = StructuralContainment(log=log, breaker=breaker)
    provider.register(instance("SCW1", readable={"SCW2"}))
    for _ in range(10):
        assert provider.decide(Operation.READ, "SCW1", "SCW2").allowed
    assert not breaker.tripped("SCW1")


def test_the_breaker_is_per_window_not_global():
    log = AttestationLog()
    breaker = DenialBreaker(log, threshold=2)
    provider = StructuralContainment(log=log, breaker=breaker)
    provider.register(instance("SCW1"))
    provider.register(instance("SCW2"))
    for _ in range(5):
        provider.decide(Operation.READ, "SCW1", "SCW9")
    assert breaker.tripped("SCW1")
    assert not breaker.tripped("SCW2")


def test_the_chain_still_verifies_after_hierarchy_decisions():
    """Adding decision kinds must not break the evidence chain."""
    tree = ConstitutionTree()
    tree.charter_root("SCW0", bounded({"SCW1", "SCW2"}))
    provider = StructuralContainment(tree=tree)
    provider.charter("SCW1", "SCW0")
    provider.register(instance("SCW1", readable={"SCW2"}))
    provider.decide(Operation.READ, "SCW1", "SCW2")
    provider.decide(Operation.READ, "SCW1", "SCW9")
    assert provider.log.verify().ok


# --- regressions from the code review ---------------------------------------


def test_narrowing_a_root_reseats_every_descendant():
    """The invariant used to hold only until someone tightened a root."""
    tree = ConstitutionTree()
    tree.charter_root("SCW0", bounded({"SCW1", "SCW2", "SCW9"}))
    tree.charter("SCW1", "SCW0")
    tree.charter("SCW2", "SCW1")
    tree.narrow("SCW0", Constitution(reach=frozenset({"SCW1"})))
    root = tree.constitution_of("SCW0").reach
    for scw in ("SCW1", "SCW2"):
        assert tree.constitution_of(scw).reach <= root
    assert not tree.permits("SCW2", "SCW9")


def test_reseating_clips_rather_than_refusing():
    """A revoked grant must resolve, not leave the tree inconsistent."""
    tree = ConstitutionTree()
    tree.charter_root("SCW0", bounded({"SCW1", "SCW2"}))
    tree.charter("SCW1", "SCW0", Constitution(reach=frozenset({"SCW1", "SCW2"})))
    tree.narrow("SCW0", Constitution(reach=frozenset({"SCW1"})))
    assert tree.constitution_of("SCW1").reach == frozenset({"SCW1"})


def test_narrowing_cascades_through_several_generations():
    tree = ConstitutionTree()
    tree.charter_root("SCW0", bounded({"SCW1", "SCW2", "SCW3", "SCW9"}))
    parent = "SCW0"
    for n in (1, 2, 3):
        tree.charter(f"SCW{n}", parent)
        parent = f"SCW{n}"
    tree.narrow("SCW0", Constitution(reach=frozenset({"SCW1"})))
    assert all(not tree.permits(f"SCW{n}", "SCW9") for n in (1, 2, 3))


def test_a_child_narrowing_reach_inherits_bridgeable():
    """Requesting a narrower reach is not also a request to become bridgeable."""
    tree = ConstitutionTree()
    tree.charter_root("SCW0", Constitution(reach=frozenset({"SCW1"}), bridgeable=False))
    granted = tree.charter("SCW1", "SCW0", Constitution(reach=frozenset({"SCW1"})))
    assert granted.is_bridgeable is False


def test_asking_to_be_bridgeable_under_a_strict_parent_is_still_refused():
    tree = ConstitutionTree()
    tree.charter_root("SCW0", Constitution(reach=frozenset({"SCW1"}), bridgeable=False))
    with pytest.raises(ConstitutionViolation, match="bridgeable"):
        tree.charter("SCW1", "SCW0", Constitution(reach=frozenset({"SCW1"}), bridgeable=True))


def test_the_breaker_refuses_on_the_read_path_not_only_on_bridges():
    """Counting refusals without refusing left probing free on every call."""
    log = AttestationLog()
    breaker = DenialBreaker(log, threshold=2)
    provider = StructuralContainment(log=log, breaker=breaker)
    provider.register(instance("SCW1"))
    for _ in range(2):
        provider.decide(Operation.READ, "SCW1", "SCW9")
    decision = provider.decide(Operation.READ, "SCW1", "SCW9")
    assert not decision.allowed
    assert "persistent refused crossings" in decision.reason


def test_a_refused_charter_does_not_trip_the_breaker():
    """A specification error is not an agent probing a boundary."""
    tree = ConstitutionTree()
    tree.charter_root("SCW0", bounded({"SCW1"}))
    log = AttestationLog()
    breaker = DenialBreaker(log, threshold=2)
    provider = StructuralContainment(log=log, tree=tree, breaker=breaker)
    for name in ("SCW7", "SCW8", "SCW9"):
        with pytest.raises(ConstitutionViolation):
            provider.charter(name, "SCW0", Constitution(reach=frozenset({"SCW9"})))
    assert breaker.denials_by("SCW7") == 0


def test_excess_reach_is_attested_one_target_at_a_time():
    """A joined string in target_scw is not an SCW identifier."""
    tree = ConstitutionTree()
    tree.charter_root("SCW0", bounded({"SCW1", "SCW2"}))
    tree.charter("SCW1", "SCW0", Constitution(reach=frozenset()))
    provider = StructuralContainment(tree=tree)
    with pytest.raises(ConstitutionViolation):
        provider.register(instance("SCW1", readable={"SCW2", "SCW9"}))
    targets = [c["target_scw"] for c in
               [e.decision.as_dict() for e in provider.log.entries()] if not c["allowed"]]
    assert targets and all("," not in t for t in targets)


def test_the_root_grant_is_attested():
    """Every decision below it is bounded by this grant."""
    provider = StructuralContainment(tree=ConstitutionTree())
    provider.charter_root("SCW0", bounded({"SCW1"}))
    last = provider.log.entries()[-1].decision
    assert last.operation is Operation.SPAWN and last.allowed
    assert "SCW1" in last.reason


def test_narrowing_is_attested_with_the_descendant_count():
    provider = StructuralContainment(tree=ConstitutionTree())
    provider.charter_root("SCW0", bounded({"SCW1", "SCW2"}))
    provider.charter("SCW1", "SCW0")
    provider.narrow("SCW0", Constitution(reach=frozenset({"SCW1"})))
    last = provider.log.entries()[-1].decision
    assert "narrowed" in last.reason and "1 descendants" in last.reason


def test_the_breaker_visits_each_entry_once():
    """Rescanning the chain per check made containment quadratic."""
    log = AttestationLog()
    breaker = DenialBreaker(log, threshold=1000)
    provider = StructuralContainment(log=log, breaker=breaker)
    provider.register(instance("SCW1"))
    for _ in range(20):
        provider.decide(Operation.READ, "SCW1", "SCW9")
    assert breaker.denials_by("SCW1") == 20
    assert breaker._scanned == len(log.entries())


# --- truncation ---------------------------------------------------------------


def test_removing_entries_from_the_end_is_detected():
    """Any prefix of a valid chain is a valid chain; that is the blind spot."""
    log = AttestationLog()
    provider = StructuralContainment(log=log)
    provider.register(instance("SCW1"))
    for _ in range(5):
        provider.decide(Operation.READ, "SCW1", "SCW9")
    full = log.export()
    head, entries = log.head, len(log)

    truncated = full[:-2]
    assert AttestationLog.verify_records(truncated).ok, "a prefix verifies on its own"
    assert not AttestationLog.verify_records(
        truncated, expected_head=head, expected_entries=entries
    ).ok


def test_the_live_log_verify_pins_its_own_head_and_length():
    log = AttestationLog()
    provider = StructuralContainment(log=log)
    provider.register(instance("SCW1"))
    provider.decide(Operation.READ, "SCW1", "SCW9")
    assert log.verify().ok


def test_the_truncation_reason_names_what_happened():
    log = AttestationLog()
    provider = StructuralContainment(log=log)
    provider.register(instance("SCW1"))
    for _ in range(3):
        provider.decide(Operation.READ, "SCW1", "SCW9")
    result = AttestationLog.verify_records(
        log.export()[:-1], expected_head=log.head, expected_entries=len(log)
    )
    assert "removed from the end" in result.reason


def test_a_non_bridgeable_charter_refuses_bridges():
    """`bridgeable=False` was inherited and then read by nothing."""
    tree = ConstitutionTree()
    tree.charter_root("SCW0", Constitution(reach=frozenset({"SCW1", "SCW2"}), bridgeable=False))
    tree.charter("SCW1", "SCW0")
    provider = StructuralContainment(tree=tree)
    with pytest.raises(ConstitutionViolation, match="not bridgeable"):
        provider.open_bridge("SCW1", "SCW2")
    assert provider.bridges == {}
    last = provider.log.entries()[-1].decision
    assert last.operation is Operation.BRIDGE and not last.allowed
    assert last.reason == "constitution is not bridgeable"


def test_disjointness_counts_open_bridges():
    """A bridge to a window the other also reads is a shared context."""
    provider = StructuralContainment()
    provider.register(instance("SCW1"))
    provider.register(instance("SCW2", readable={"SCW3"}))
    provider.register(instance("SCW3"))
    assert provider.decide(Operation.DISJOINTNESS, "SCW1", "SCW2").allowed
    provider.open_bridge("SCW1", "SCW3")
    decision = provider.decide(Operation.DISJOINTNESS, "SCW1", "SCW2")
    assert not decision.allowed
    assert "SCW3" in decision.reason
