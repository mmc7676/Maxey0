"""Unit tests for the SCW enforcement core (`server/vendor/scw_runtime`).

Plain `unittest` from the standard library, so the suite runs with zero
install: `python -m unittest discover -s tests -v` from the repo root.
`python -m pytest tests/` also collects these, because pytest picks up
`unittest.TestCase` subclasses automatically.

Every assertion below is about behavior that exists in the vendored runtime
today. Where the runtime's public surface differs from the MCP tool name that
wraps it, the test targets the runtime method: `scope_closure` is
`ContextWindow.read_closure` / `.write_closure`, and `check_disjointness` is
`ContextWindow.disjointness`.
"""

import copy
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server" / "vendor"))

from scw_runtime import (  # noqa: E402
    BudgetExceeded,
    ChainBroken,
    ContextWindow,
    DisjointnessViolation,
    HarnessViolation,
    IsolationViolation,
    PolicyViolation,
    preset_for,
    replay,
    split_runs,
    verify_records,
)
from scw_runtime import tokens as tok  # noqa: E402


def events(window, event_type):
    """Every record of one type currently in the window's log."""
    return [r for r in window.log.records if r["type"] == event_type]


def region_state(region):
    """A comparable snapshot of everything a write would move."""
    return {
        "entry_ids": [e.entry_id for e in region.entries],
        "data": [e.data for e in region.entries],
        "own_tokens": region.own_tokens,
        "revision": region.revision,
        "evicted_tokens": region.evicted_tokens,
    }


class RegionPolicyTests(unittest.TestCase):
    """create_scw installs the preset policy that belongs to the region type."""

    def test_create_scw_applies_the_type_preset(self):
        """Defends: a region's wall is decided by its declared type, not by the
        caller remembering to pass a policy. `scratchpad` and `reference` are
        the two ends of the preset table and must arrive fully configured."""
        window = ContextWindow(name="presets")

        pad = window.create_scw("Scratchpad", "scratchpad")
        self.assertEqual(pad.policy.to_dict(), preset_for("scratchpad").to_dict())
        self.assertEqual(pad.policy.mutability, "volatile")
        self.assertEqual(pad.policy.token_budget, 2048)
        self.assertTrue(pad.policy.reset_each_tick)
        self.assertTrue(pad.policy.purge_on_close)
        self.assertFalse(pad.policy.bridgeable)

        ref = window.create_scw("Task spec", "reference")
        self.assertEqual(ref.policy.to_dict(), preset_for("reference").to_dict())
        self.assertEqual(ref.policy.mutability, "readonly")
        self.assertEqual(ref.policy.eviction, "reject")
        self.assertTrue(ref.policy.versioned)
        self.assertEqual(ref.policy.cache, "always")

        # The preset is what was written to the log, not a value derived later.
        created = events(window, "scw.create")
        by_id = {r["payload"]["scw_id"]: r["payload"] for r in created}
        self.assertEqual(by_id[pad.scw_id]["policy"], pad.policy.to_dict())
        self.assertEqual(by_id[ref.scw_id]["region_type"], "reference")

    def test_explicit_overrides_win_over_the_preset(self):
        """Defends: presets are a starting point, not a ceiling — an explicit
        policy field overrides exactly that field and leaves the rest alone."""
        window = ContextWindow(name="overrides")
        region = window.create_scw(
            "Bounded notes", "episodic", policy={"token_budget": 64, "eviction": "reject"}
        )
        self.assertEqual(region.policy.token_budget, 64)
        self.assertEqual(region.policy.eviction, "reject")
        # untouched preset fields survive
        self.assertEqual(region.policy.mutability, "durable")
        self.assertTrue(region.policy.versioned)


class HostReadWriteTests(unittest.TestCase):
    """The unbound host can seed and read the window it is building."""

    def test_write_then_read_round_trips_for_the_unbound_host(self):
        """Defends: content written by the host comes back byte-identical, and
        the access is attributed to the orchestrator rather than to a loop."""
        window = ContextWindow(name="roundtrip")
        notes = window.create_scw("Findings", "episodic")

        result = window.write(notes.scw_id, "the pump failed at 03:12")
        self.assertEqual(result["scw_id"], notes.scw_id)
        self.assertEqual(result["via"], "orchestrator")
        self.assertEqual(result["tokens_written"], tok.count_tokens("the pump failed at 03:12"))

        out = window.read(notes.scw_id, include_children=False)
        self.assertEqual(out["content"], "the pump failed at 03:12")
        self.assertEqual(out["via"], "orchestrator")
        self.assertEqual([e["data"] for e in out["entries"]], ["the pump failed at 03:12"])

        # A keyed write renders as "key: data" and upserts in place.
        window.write(notes.scw_id, "v1", key="status")
        window.write(notes.scw_id, "v2", key="status")
        out = window.read(notes.scw_id, include_children=False)
        self.assertEqual(
            out["content"], "the pump failed at 03:12\nstatus: v2"
        )
        self.assertEqual(len(out["entries"]), 2)


class ScopeIsolationTests(unittest.TestCase):
    """The wall: a bound loop reaches its own region and nothing else."""

    def setUp(self):
        self.window = ContextWindow(name="isolation")
        self.pad_a = self.window.create_scw("Pad A", "scratchpad")
        self.pad_b = self.window.create_scw("Pad B", "scratchpad")
        self.window.bind_scope("alpha", self.pad_a.scw_id, max_iterations=3)
        self.window.bind_scope("beta", self.pad_b.scw_id, max_iterations=3)

    def test_bound_loop_can_read_and_write_its_own_scratchpad(self):
        """Defends: isolation is a boundary, not a lockout — the loop's own
        region is reachable for both operations, authorized `via` its scope."""
        result = self.window.write(self.pad_a.scw_id, "draft one", loop_id="alpha")
        self.assertEqual(result["via"], "scope")

        out = self.window.read(self.pad_a.scw_id, loop_id="alpha", include_children=False)
        self.assertEqual(out["content"], "draft one")
        self.assertEqual(out["via"], "scope")

        loop = self.window.loops["alpha"]
        self.assertEqual(loop.writes, 1)
        self.assertEqual(loop.reads, 1)
        self.assertEqual(loop.denials, 0)

    def test_bound_loop_is_refused_another_loops_region(self):
        """Defends: the central claim. A loop bound to Pad A cannot read Pad B,
        the refusal is an IsolationViolation carrying a usable message and hint,
        and the refusal is recorded in the log rather than swallowed."""
        self.window.write(self.pad_b.scw_id, "beta's private draft", loop_id="beta")
        before = region_state(self.window.regions[self.pad_b.scw_id])

        with self.assertRaises(IsolationViolation) as caught:
            self.window.read(self.pad_b.scw_id, loop_id="alpha")
        err = caught.exception

        self.assertEqual(err.code, "isolation_violation")
        self.assertIn("outside its scope", err.message)
        self.assertIn(self.pad_b.scw_id, err.message)
        self.assertIn("open_bridge(", err.detail["hint"])
        self.assertEqual(err.detail["loop_id"], "alpha")
        self.assertEqual(err.to_dict()["error"], "isolation_violation")

        denials = events(self.window, "scw.denied")
        self.assertEqual(len(denials), 1)
        self.assertEqual(denials[-1]["payload"]["op"], "read")
        self.assertEqual(denials[-1]["payload"]["loop_id"], "alpha")
        self.assertEqual(denials[-1]["payload"]["scope_root"], self.pad_a.scw_id)
        self.assertEqual(self.window.loops["alpha"].denials, 1)

        # A refused read leaves the target byte-identical.
        self.assertEqual(region_state(self.window.regions[self.pad_b.scw_id]), before)

    def test_bound_loop_is_refused_a_write_to_another_loops_region(self):
        """Defends: the same wall in the write direction — a loop cannot inject
        content into a region it does not hold, and nothing lands."""
        before = region_state(self.window.regions[self.pad_b.scw_id])
        with self.assertRaises(IsolationViolation):
            self.window.write(self.pad_b.scw_id, "smuggled", loop_id="alpha")
        self.assertEqual(region_state(self.window.regions[self.pad_b.scw_id]), before)

    def test_bound_loop_cannot_create_a_top_level_region(self):
        """Defends: escape-by-construction. A loop that could add a sibling
        region could build itself a partition outside its own, so creating a
        top-level region while bound is refused before anything is created."""
        roots_before = list(self.window.roots)
        region_count = len(self.window.regions)

        with self.assertRaises(IsolationViolation) as caught:
            self.window.create_scw("Escape hatch", "durable", loop_id="alpha")
        self.assertIn("cannot create top-level regions", caught.exception.message)

        self.assertEqual(self.window.roots, roots_before)
        self.assertEqual(len(self.window.regions), region_count)
        denials = events(self.window, "scw.denied")
        self.assertEqual(denials[-1]["payload"]["op"], "create")
        self.assertIsNone(denials[-1]["payload"]["scw_id"])

        # Nesting inside its own scope is the legal move, and it works.
        child = self.window.create_scw(
            "Sub-pad", "working", parent_scw_id=self.pad_a.scw_id, loop_id="alpha"
        )
        self.assertEqual(child.parent_id, self.pad_a.scw_id)
        self.assertNotIn(child.scw_id, self.window.roots)


class PolicyEnforcementTests(unittest.TestCase):
    """Region policy: read-only walls and token budgets."""

    def test_readonly_reference_region_refuses_a_bound_loops_write(self):
        """Defends: a `reference` region is seedable by the host and immutable
        to every bound loop, even one whose scope legitimately reaches it. The
        refusal is a PolicyViolation, not an IsolationViolation."""
        window = ContextWindow(name="readonly")
        work = window.create_scw("Work", "episodic")
        spec = window.create_scw(
            "Task spec", "reference", parent_scw_id=work.scw_id
        )
        window.write(spec.scw_id, "acceptance: the report must cite two sources")
        window.bind_scope("worker", work.scw_id, descend=True, max_iterations=2)

        before = region_state(window.regions[spec.scw_id])
        with self.assertRaises(PolicyViolation) as caught:
            window.write(spec.scw_id, "acceptance: whatever I produced", loop_id="worker")
        err = caught.exception
        self.assertEqual(err.code, "policy_violation")
        self.assertEqual(err.detail["mutability"], "readonly")
        self.assertIn("read-only", err.message)

        self.assertEqual(region_state(window.regions[spec.scw_id]), before)
        self.assertEqual(events(window, "scw.denied")[-1]["payload"]["op"], "write")
        # The scope did reach it — a read of the same region is allowed.
        self.assertEqual(
            window.read(spec.scw_id, loop_id="worker", include_children=False)["content"],
            "acceptance: the report must cite two sources",
        )

    def test_reject_budget_refuses_the_write_and_mutates_nothing(self):
        """Defends: `eviction='reject'` means refuse, not silently drop. The
        write raises BudgetExceeded and the region is byte-identical afterwards
        — a half-applied refusal would be a real containment bug."""
        window = ContextWindow(name="reject")
        seed = "alpha bravo"
        budget = tok.count_tokens(seed) + 1
        region = window.create_scw(
            "Capped", "episodic", policy={"token_budget": budget, "eviction": "reject"}
        )
        window.write(region.scw_id, seed)

        live = window.regions[region.scw_id]
        before = region_state(live)
        signature_before = window.signature(region.scw_id)
        oversized = "charlie delta echo foxtrot"
        self.assertGreater(before["own_tokens"] + tok.count_tokens(oversized), budget)

        with self.assertRaises(BudgetExceeded) as caught:
            window.write(region.scw_id, oversized)
        err = caught.exception
        self.assertEqual(err.code, "budget_exceeded")
        self.assertEqual(err.detail["budget"], budget)
        self.assertEqual(
            err.detail["would_be"], before["own_tokens"] + tok.count_tokens(oversized)
        )

        # Nothing moved: entries, ids, tokens, revision, rendered bytes.
        self.assertEqual(region_state(live), before)
        self.assertEqual(window.signature(region.scw_id), signature_before)
        self.assertEqual(len(live.entries), 1)
        self.assertEqual(live.entries[0].data, seed)
        self.assertEqual(live.evicted_tokens, 0)
        self.assertEqual(events(window, "scw.evict"), [])

        denial = events(window, "scw.denied")[-1]["payload"]
        self.assertEqual(denial["op"], "write")
        self.assertEqual(denial["budget"], budget)

    def test_fifo_budget_evicts_the_oldest_entry_instead_of_refusing(self):
        """Defends: the other half of the budget contract. Under `fifo` the
        write succeeds, the oldest entry is dropped, and the region lands back
        inside its budget."""
        window = ContextWindow(name="fifo")
        first, second, third = "alpha", "bravo", "charlie"
        budget = tok.count_tokens(first) + tok.count_tokens(second)
        region = window.create_scw(
            "Rolling", "episodic", policy={"token_budget": budget, "eviction": "fifo"}
        )
        window.write(region.scw_id, first)
        window.write(region.scw_id, second)
        live = window.regions[region.scw_id]
        oldest_id = live.entries[0].entry_id
        self.assertEqual(len(live.entries), 2)

        result = window.write(region.scw_id, third)

        self.assertIn(oldest_id, result["evicted"])
        remaining = [e.entry_id for e in live.entries]
        self.assertNotIn(oldest_id, remaining)
        self.assertIn(third, [e.data for e in live.entries])
        self.assertLessEqual(live.own_tokens, budget)
        self.assertGreater(live.evicted_tokens, 0)

        evictions = events(window, "scw.evict")
        self.assertEqual(evictions[-1]["payload"]["policy"], "fifo")
        self.assertEqual(evictions[-1]["payload"]["reason"], "budget")
        self.assertIn(oldest_id, evictions[-1]["payload"]["entry_ids"])


class BridgeTests(unittest.TestCase):
    """Bridges are the only legitimate hole in a wall, and they close."""

    def test_open_bridge_permits_a_refused_read_and_close_bridge_refuses_it_again(self):
        """Defends: crossing a partition requires an explicit, logged grant, and
        revoking that grant restores the wall in the same call shape."""
        window = ContextWindow(name="bridges")
        pad = window.create_scw("Pad", "scratchpad")
        vault = window.create_scw("Vault", "durable")
        window.write(vault.scw_id, "the incident timeline")
        window.bind_scope("worker", pad.scw_id, max_iterations=5)

        with self.assertRaises(IsolationViolation):
            window.read(vault.scw_id, loop_id="worker")

        bridge = window.open_bridge(
            pad.scw_id, vault.scw_id, mode="read", reason="cite the timeline"
        )
        out = window.read(vault.scw_id, loop_id="worker", include_children=False)
        self.assertEqual(out["via"], bridge.bridge_id)
        self.assertEqual(out["content"], "the incident timeline")

        # A read grant is a read grant: writing through it is still refused.
        with self.assertRaises(IsolationViolation):
            window.write(vault.scw_id, "edited", loop_id="worker")

        closed = window.close_bridge(bridge.bridge_id)
        self.assertEqual(closed["status"], "closed")
        with self.assertRaises(IsolationViolation) as caught:
            window.read(vault.scw_id, loop_id="worker")
        self.assertIn("no bridge grants 'read'", caught.exception.message)

    def test_non_bridgeable_region_refuses_every_grant(self):
        """Defends: `bridgeable=False` means unreachable from outside full
        stop — the grant itself is refused, so there is nothing to revoke."""
        window = ContextWindow(name="unbridgeable")
        pad = window.create_scw("Pad", "scratchpad")
        private = window.create_scw("Private", "working")  # working preset: bridgeable=False
        self.assertFalse(private.policy.bridgeable)
        with self.assertRaises(PolicyViolation) as caught:
            window.open_bridge(pad.scw_id, private.scw_id, mode="read", reason="nope")
        self.assertIn("bridgeable=false", caught.exception.message)
        self.assertEqual(window.bridges, {})


class ClosureTests(unittest.TestCase):
    """The reachable set, as a set — what `scope_closure` reports."""

    def test_read_and_write_closures_report_exactly_the_reachable_set(self):
        """Defends: closures are computed over the region graph, so they include
        the bound subtree, widen with a read grant, and never claim write access
        a read grant did not give or a read-only policy forbids."""
        window = ContextWindow(name="closures")
        work = window.create_scw("Work", "episodic")
        notes = window.create_scw("Notes", "episodic", parent_scw_id=work.scw_id)
        vault = window.create_scw("Vault", "durable")
        facts = window.create_scw("Facts", "reference")
        window.bind_scope("worker", work.scw_id, descend=True, max_iterations=4)

        self.assertEqual(window.read_closure("worker"), {work.scw_id, notes.scw_id})
        self.assertEqual(window.write_closure("worker"), {work.scw_id, notes.scw_id})

        window.open_bridge(work.scw_id, vault.scw_id, mode="read", reason="reference")
        self.assertEqual(
            window.read_closure("worker"), {work.scw_id, notes.scw_id, vault.scw_id}
        )
        self.assertEqual(window.write_closure("worker"), {work.scw_id, notes.scw_id})

        window.open_bridge(work.scw_id, facts.scw_id, mode="read", reason="criterion")
        self.assertEqual(
            window.read_closure("worker"),
            {work.scw_id, notes.scw_id, vault.scw_id, facts.scw_id},
        )
        # A read-only region is never in a write closure, grant or no grant.
        self.assertEqual(window.write_closure("worker"), {work.scw_id, notes.scw_id})

        # A write grant exposes exactly its target, not that target's subtree.
        window.open_bridge(work.scw_id, vault.scw_id, mode="write", reason="handoff")
        self.assertEqual(
            window.write_closure("worker"), {work.scw_id, notes.scw_id, vault.scw_id}
        )

        # The unbound host reaches everything; an unknown loop reaches nothing.
        self.assertEqual(window.read_closure(None), set(window.regions))
        self.assertEqual(window.read_closure("nobody"), set())
        self.assertEqual(window.write_closure("nobody"), set())

    def test_a_released_loop_has_an_empty_closure(self):
        """Defends: unbinding actually releases — a loop's reachable set drops
        to nothing the moment its scope is released."""
        window = ContextWindow(name="released")
        pad = window.create_scw("Pad", "scratchpad")
        window.bind_scope("worker", pad.scw_id, max_iterations=1)
        self.assertEqual(window.read_closure("worker"), {pad.scw_id})
        window.unbind_scope("worker", terminal_state="no_op")
        self.assertEqual(window.read_closure("worker"), set())
        with self.assertRaises(IsolationViolation):
            window.write(pad.scw_id, "after release", loop_id="worker")


class DisjointnessTests(unittest.TestCase):
    """A maker may not grade its own artifact, whatever the judge is called."""

    def test_disjointness_refuses_a_maker_judging_its_own_artifact(self):
        """Defends: the report refuses both shapes of self-judging — naming
        nobody (R1), and naming a distinct judge who can nonetheless read what
        the maker writes (R4). Renaming the judge does not break shared
        context; the graph does."""
        window = ContextWindow(name="disjointness")
        art = window.create_scw("Artifact", "episodic")
        review = window.create_scw("Review", "episodic")
        window.bind_scope("maker", art.scw_id, max_iterations=3)
        window.bind_scope("judge", review.scw_id, max_iterations=3)

        # R1: no distinct judge named.
        self_report = window.disjointness("maker", "maker")
        self.assertFalse(self_report["disjoint"])
        self.assertIn("R1.identity", self_report["failed"])
        self.assertIn("maker", self_report["reason"])
        self.assertFalse(window.disjointness("maker", None)["disjoint"])

        # A genuinely separate judge passes.
        clean = window.disjointness("maker", "judge")
        self.assertTrue(clean["disjoint"], clean["reason"])
        self.assertEqual(clean["failed"], [])

        # R4: give the judge a read grant into the maker's region and the same
        # pair of names now fails on the graph, not on the identifiers.
        window.open_bridge(review.scw_id, art.scw_id, mode="read", reason="grade it")
        shared = window.disjointness("maker", "judge")
        self.assertFalse(shared["disjoint"])
        self.assertIn("R4.exposure", shared["failed"])
        r4 = next(r for r in shared["rules"] if r["rule"] == "R4.exposure")
        self.assertEqual(r4["overlap"], [art.scw_id])
        self.assertIn(art.scw_id, r4["judge_read_closure"])
        self.assertIn(art.scw_id, r4["maker_write_closure"])

    def test_disjoint_harness_refuses_a_self_approving_tick_and_mutates_nothing(self):
        """Defends: the report is enforced, not merely advisory. A loop bound to
        a maker_checker harness that approves its own iteration is refused with
        DisjointnessViolation, the decision is logged as `partition.check`, and
        the iteration counter does not move."""
        window = ContextWindow(name="enforced")
        art = window.create_scw("Artifact", "episodic")
        harness = window.create_harness("Maker/checker", architecture="maker_checker")
        self.assertEqual(harness.verification_policy, "disjoint")
        window.bind_scope(
            "maker",
            art.scw_id,
            max_iterations=3,
            verification_level=4,
            harness_id=harness.harness_id,
        )
        window.write(art.scw_id, "the artifact", loop_id="maker")

        tick_before = window.tick
        iterations_before = window.total_iterations

        with self.assertRaises(DisjointnessViolation) as caught:
            window.loop_tick("maker", verified=True)
        err = caught.exception
        self.assertIsInstance(err, HarnessViolation)  # subclass, by design
        self.assertEqual(err.code, "disjointness_violation")
        self.assertIn("R1.identity", err.detail["failed"])
        self.assertIn("bind the judge", err.detail["hint"])

        checks = events(window, "partition.check")
        self.assertEqual(len(checks), 1)
        self.assertFalse(checks[-1]["payload"]["disjoint"])

        # A refused verdict leaves the window where it was found.
        self.assertEqual(window.tick, tick_before)
        self.assertEqual(window.total_iterations, iterations_before)
        loop = window.loops["maker"]
        self.assertEqual(loop.iteration, 0)
        self.assertEqual(loop.accepted, 0)
        self.assertEqual(loop.self_approved, 0)
        self.assertEqual(harness.iterations_run, 0)
        self.assertEqual(events(window, "loop.tick"), [])


def build_session(name="session"):
    """A real, mixed-traffic run: seeding, a bound loop, a refusal, a grant,
    a tick, a promotion, a purge on close. Used by the chain and replay tests
    so they assert over something with every record type that matters."""
    window = ContextWindow(total_budget=8000, name=name)

    spec = window.create_scw("Task spec", "reference")
    notes = window.create_scw("Findings", "episodic")
    pad = window.create_scw("Scratchpad", "scratchpad")
    sub = window.create_scw("Sub-pad", "working", parent_scw_id=pad.scw_id)

    window.write(spec.scw_id, "Summarize the incident reports.")
    window.write(notes.scw_id, "pump failed", key="f1")
    window.write(notes.scw_id, "valve stuck", key="f2")

    prompt = window.create_prompt("Refine", "Refine {{draft}} against {{rules}}.")
    harness = window.create_harness(
        "Solo dev",
        architecture="solo",
        skills=[{"name": "lint", "verified": True}],
        tool_grants=("ci",),
        sandbox="worktree",
    )

    window.bind_scope(
        "refine",
        pad.scw_id,
        descend=True,
        max_iterations=4,
        goal="tighten the draft",
        verification_level=1,
        prompt_id=prompt.prompt_id,
        harness_id=harness.harness_id,
    )

    window.write(pad.scw_id, "draft 1", loop_id="refine")
    window.write(sub.scw_id, "working note", loop_id="refine")
    window.render_prompt(prompt.prompt_id, {"draft": "draft 1"}, loop_id="refine")
    window.harness_call(harness.harness_id, "lint", loop_id="refine")

    try:  # a real refusal, recorded in the chain
        window.read(notes.scw_id, loop_id="refine")
    except IsolationViolation:
        pass

    read_bridge = window.open_bridge(
        pad.scw_id, notes.scw_id, mode="read", reason="cite findings", ttl_ticks=3
    )
    window.read(notes.scw_id, loop_id="refine")
    window.loop_tick("refine", note="iteration 1", verified=True)

    window.write(pad.scw_id, "draft 2", loop_id="refine")
    write_bridge = window.open_bridge(
        pad.scw_id, notes.scw_id, mode="write", reason="publish the draft", ttl_ticks=3
    )
    window.promote(pad.scw_id, notes.scw_id, loop_id="refine", mode="copy")
    window.loop_tick("refine", note="iteration 2", verified=False)

    window.close_bridge(read_bridge.bridge_id)
    window.close_bridge(write_bridge.bridge_id)
    window.unbind_scope("refine", terminal_state="success")
    window.close_scw(pad.scw_id, cascade=True)
    return window


class EventChainTests(unittest.TestCase):
    """The log is the window: hash-chained, complete, and tamper-evident."""

    def test_event_log_chain_verifies_over_a_real_session(self):
        """Defends: every record emitted during a real mixed run links to the
        one before it, so the audit trail is verifiable rather than decorative."""
        window = build_session("chain")
        window.log.verify()  # raises ChainBroken on any break
        verify_records(window.log.records)

        records = window.log.records
        self.assertEqual([r["seq"] for r in records], list(range(len(records))))
        self.assertEqual(records[0]["type"], "window.init")
        self.assertEqual(records[0]["prev"], "0" * 64)
        for earlier, later in zip(records, records[1:]):
            self.assertEqual(later["prev"], earlier["digest"])

        # The run actually exercised the enforcement paths it claims to.
        for kind in (
            "scw.create", "scw.write", "scw.read", "scw.denied", "scw.evict",
            "scw.close", "scw.purge", "loop.bind", "loop.tick", "loop.unbind",
            "bridge.open", "bridge.close", "promote", "prompt.create",
            "prompt.render", "harness.create", "harness.call",
        ):
            self.assertTrue(events(window, kind), f"no {kind} record in the session")

        head = window.log.head()
        self.assertEqual(head["run_id"], window.log.run_id)
        self.assertEqual(head["length"], len(records))
        self.assertEqual(head["digest"], records[-1]["digest"])

    def test_tampering_with_one_payload_breaks_the_chain(self):
        """Defends: tamper-evidence. Editing the content of a single record —
        the cheapest possible forgery — makes verify_records raise ChainBroken."""
        window = build_session("tamper")
        records = copy.deepcopy(window.log.records)
        verify_records(records)  # the copy is clean to begin with

        index = next(
            i for i, r in enumerate(records)
            if r["type"] == "scw.write" and r["payload"].get("data") == "draft 1"
        )
        records[index]["payload"]["data"] = "draft 1 (forged)"

        with self.assertRaises(ChainBroken) as caught:
            verify_records(records)
        err = caught.exception
        self.assertEqual(err.code, "chain_broken")
        self.assertIn("digest mismatch", err.message)
        self.assertEqual(err.detail["seq"], records[index]["seq"])

    def test_deleting_a_record_breaks_the_chain(self):
        """Defends: the chain detects removal as well as edits — dropping a
        record leaves a sequence gap that verify_records refuses."""
        records = copy.deepcopy(build_session("deletion").log.records)
        del records[4]
        with self.assertRaises(ChainBroken) as caught:
            verify_records(records)
        self.assertIn("sequence gap", caught.exception.message)


class ReplayTests(unittest.TestCase):
    """Replay proves the log is a complete description, not a commentary."""

    def test_replay_reconstructs_a_window_identical_to_the_live_one(self):
        """Defends: folding the event stream rebuilds the same window, content
        included. This is what makes the inspector UI trustworthy — it runs the
        same reduction over the same bytes."""
        live = build_session("replay")
        rebuilt = replay(live.log.records)

        self.assertEqual(
            rebuilt.inspect(include_content=True), live.inspect(include_content=True)
        )
        self.assertEqual(sorted(rebuilt.regions), sorted(live.regions))
        self.assertEqual(rebuilt.tick, live.tick)
        self.assertEqual(rebuilt.total_iterations, live.total_iterations)
        self.assertEqual(rebuilt.log.run_id, live.log.run_id)
        self.assertEqual(len(rebuilt.log.records), len(live.log.records))
        for scw_id in live.regions:
            self.assertEqual(rebuilt.footprint(scw_id), live.footprint(scw_id))
            self.assertEqual(rebuilt.signature(scw_id), live.signature(scw_id))

    def test_replay_of_a_redacted_log_keeps_structure_and_sizes(self):
        """Defends: `log_content=False` is a real privacy mode, not a broken
        one — structure, policies, sizes and access decisions still replay."""
        live = ContextWindow(name="redacted", log_content=False)
        notes = live.create_scw("Findings", "episodic")
        live.write(notes.scw_id, "sensitive detail")
        writes = events(live, "scw.write")
        self.assertNotIn("data", writes[-1]["payload"])
        self.assertIn("data_sha256", writes[-1]["payload"])

        rebuilt = replay(live.log.records)
        self.assertEqual(sorted(rebuilt.regions), sorted(live.regions))
        rebuilt_region = rebuilt.regions[notes.scw_id]
        live_region = live.regions[notes.scw_id]
        self.assertEqual(len(rebuilt_region.entries), len(live_region.entries))
        self.assertEqual(
            rebuilt_region.entries[0].tokens, live_region.entries[0].tokens
        )
        self.assertEqual(rebuilt_region.entries[0].data, "")  # bytes withheld

    def test_split_runs_separates_runs_and_replay_picks_the_last(self):
        """Defends: one log file may hold several runs. split_runs partitions
        them in file order, the chain still verifies across the seam, and
        replay defaults to the last run — the file's current state."""
        first = ContextWindow(name="run-one")
        first.create_scw("Only In Run One", "episodic")
        second = ContextWindow(name="run-two")
        second.create_scw("Only In Run Two", "durable")

        combined = list(first.log.records) + list(second.log.records)
        verify_records(combined)  # chains restart at genesis per run

        runs = split_runs(combined)
        self.assertEqual(len(runs), 2)
        self.assertEqual([r[0]["run_id"] for r in runs],
                         [first.log.run_id, second.log.run_id])
        self.assertEqual(runs[0], list(first.log.records))
        self.assertEqual(runs[1], list(second.log.records))
        self.assertNotEqual(first.log.run_id, second.log.run_id)

        default = replay(combined)
        self.assertEqual(default.log.run_id, second.log.run_id)
        self.assertEqual(default.name, "run-two")
        self.assertEqual(sorted(default.regions), sorted(second.regions))
        self.assertNotIn("only-in-run-one", default.regions)

        chosen = replay(combined, run_id=first.log.run_id)
        self.assertEqual(chosen.log.run_id, first.log.run_id)
        self.assertEqual(sorted(chosen.regions), sorted(first.regions))
        self.assertNotIn("only-in-run-two", chosen.regions)


if __name__ == "__main__":  # pragma: no cover
    unittest.main(verbosity=2)
