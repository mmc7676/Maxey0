"""One test per named invariant.

Several of these properties are already exercised inside broader tests. They
are split out here so a regression names the property it broke: "bridge TTL
expiry failed" is actionable in a way that "test_binding failed" is not.

Every assertion goes through the real `scw_runtime` enforcement path. Nothing
here mocks a region, a refusal, or a token budget.

EVENT LOG SAFETY: `state.py` freezes its event-log path at import time from
`SCW_EVENT_LOG`. `tests/_env.py` redirects it to a tempfile before anything
imports `maxey0_studio`; `TestEventLogIsolation` in test_studio.py asserts the
redirect actually took.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _env import ROOT, TMPDIR, VENDOR  # noqa: E402,F401

from maxey0_studio import experiment as exp_mod  # noqa: E402
from maxey0_studio import observability as obs  # noqa: E402
from maxey0_studio import state as st  # noqa: E402
from scw_runtime.errors import SCWError  # noqa: E402


class InvariantCase(unittest.TestCase):
    """A fresh window per test; these invariants are about state transitions."""

    def setUp(self) -> None:
        self.session = st.Session()
        self.window = self.session.window

    def two_roles(self):
        """A maker and a checker, each in its own unbridgeable scratchpad."""
        self.window.create_scw("Maker pad", "scratchpad", scw_id="mk-pad")
        self.window.create_scw("Checker pad", "scratchpad", scw_id="ck-pad")
        self.window.create_scw("Shared reference", "reference", scw_id="ref")
        self.window.write("ref", "the rubric", key="rubric")
        self.window.bind_scope("maker", "mk-pad", goal="make", trigger="manual",
                               verification_level=1, max_iterations=4)
        self.window.bind_scope("checker", "ck-pad", goal="check", trigger="manual",
                               verification_level=3, max_iterations=4)


# ---------------------------------------------------------------------------
# partition invariants
# ---------------------------------------------------------------------------
class TestScopeClosure(InvariantCase):
    def test_scope_closure_is_exactly_the_role_s_own_partition(self):
        self.two_roles()
        self.assertEqual(self.window.read_closure("maker"), {"mk-pad"})
        self.assertEqual(self.window.write_closure("maker"), {"mk-pad"})

    def test_an_unbound_host_reaches_everything(self):
        self.two_roles()
        self.assertIn("ck-pad", self.window.read_closure(None))
        self.assertIn("mk-pad", self.window.read_closure(None))


class TestDisjointness(InvariantCase):
    def test_two_roles_in_separate_pads_have_disjoint_read_closures(self):
        self.two_roles()
        self.assertEqual(
            self.window.read_closure("maker") & self.window.read_closure("checker"),
            set())

    def test_a_judge_bound_to_the_maker_s_own_region_is_refused(self):
        self.window.create_scw("Shared", "durable", scw_id="shared")
        self.window.bind_scope("m", "shared", goal="make", trigger="manual",
                               verification_level=1, max_iterations=2)
        self.window.bind_scope("j", "shared", goal="judge", trigger="manual",
                               verification_level=3, max_iterations=2)
        report = self.window.disjointness("m", "j")
        self.assertFalse(report["disjoint"])
        self.assertIn("R3.distinct_root", report["failed"])

    def test_a_loop_cannot_be_its_own_judge(self):
        self.two_roles()
        report = self.window.disjointness("maker", "maker")
        self.assertFalse(report["disjoint"])
        self.assertIn("R1.identity", report["failed"])


class TestRoleIsolation(InvariantCase):
    def test_a_role_is_refused_another_role_s_private_pad(self):
        self.two_roles()
        with self.assertRaises(SCWError) as caught:
            self.window.read("ck-pad", loop_id="maker")
        self.assertEqual(caught.exception.to_dict()["error"], "isolation_violation")

    def test_a_refusal_carries_a_hint_naming_what_would_make_it_legal(self):
        self.two_roles()
        with self.assertRaises(SCWError) as caught:
            self.window.read("ck-pad", loop_id="maker")
        self.assertIn("open_bridge", caught.exception.to_dict()["hint"])

    def test_a_refused_read_leaves_the_window_unchanged(self):
        self.two_roles()
        before = len(self.window.regions)
        with self.assertRaises(SCWError):
            self.window.read("ck-pad", loop_id="maker")
        self.assertEqual(len(self.window.regions), before)


class TestBridgeTTL(InvariantCase):
    def test_a_grant_opens_access_and_expiry_closes_it_again(self):
        self.two_roles()
        # Without a grant, the maker cannot reach the shared reference.
        with self.assertRaises(SCWError):
            self.window.read("ref", loop_id="maker")

        bridge = self.window.open_bridge("mk-pad", "ref", mode="read",
                                         reason="read the rubric",
                                         ttl_ticks=1, loop_id="maker")
        self.assertIn("ref", self.window.read_closure("maker"))
        self.window.read("ref", loop_id="maker")  # authorized now

        self.window.loop_tick("maker", note="burn the ttl")
        self.assertNotIn("ref", self.window.read_closure("maker"),
                         "a ttl_ticks=1 grant must not survive its own tick")
        with self.assertRaises(SCWError):
            self.window.read("ref", loop_id="maker")
        self.assertIsNotNone(bridge.bridge_id)

    def test_a_scratchpad_refuses_every_grant_by_policy(self):
        self.two_roles()
        with self.assertRaises(SCWError):
            self.window.open_bridge("mk-pad", "ck-pad", mode="read",
                                    reason="try to reach the other pad",
                                    ttl_ticks=1, loop_id="maker")


class TestSuccessStateVerification(InvariantCase):
    def test_success_is_refused_without_an_accepted_verification(self):
        self.two_roles()
        with self.assertRaises(SCWError):
            self.window.unbind_scope("maker", terminal_state="success")

    def test_an_honest_terminal_state_is_accepted(self):
        self.two_roles()
        result = self.window.unbind_scope("maker", terminal_state="no_op")
        self.assertTrue(result.get("ok", True))


# ---------------------------------------------------------------------------
# audit invariants
# ---------------------------------------------------------------------------
class TestAuditChain(InvariantCase):
    def test_the_hash_chain_verifies_over_every_event(self):
        self.two_roles()
        self.assertTrue(self.session.verify_chain()["verified"])

    def test_replay_reconstructs_an_identical_window(self):
        self.two_roles()
        self.assertTrue(self.session.verify_chain()["replay_identical"])

    def test_a_refusal_is_recorded_not_merely_raised(self):
        self.two_roles()
        with self.assertRaises(SCWError):
            self.window.read("ck-pad", loop_id="maker")
        denied = [r for r in self.window.log.records if r["type"] == "scw.denied"]
        self.assertTrue(denied, "a refusal must leave a scw.denied record")
        self.assertEqual(denied[-1]["payload"]["scw_id"], "ck-pad")


# ---------------------------------------------------------------------------
# observability invariants (0.4.0)
# ---------------------------------------------------------------------------
class TestObservability(InvariantCase):
    def test_every_event_type_the_runtime_emits_is_classified(self):
        """An unmapped type is `other`, never dropped."""
        self.two_roles()
        for record in self.window.log.records:
            self.assertIsInstance(obs.classify(record["type"]), str)

    def test_attempts_reports_a_denied_reach_with_its_reason(self):
        self.two_roles()
        with self.assertRaises(SCWError):
            self.window.read("ck-pad", loop_id="maker")
        result = obs.attempts(self.window.log.records,
                              loop_id="maker", scw_id="ck-pad")
        self.assertEqual(result["denied_count"], 1)
        self.assertEqual(result["allowed_count"], 0)
        self.assertTrue(result["contained"])
        self.assertTrue(result["denied"][0]["reason"])

    def test_no_attempt_reports_null_containment_not_true(self):
        """Absence of evidence is not evidence of containment."""
        self.two_roles()
        result = obs.attempts(self.window.log.records,
                              loop_id="checker", scw_id="mk-pad")
        self.assertEqual(result["attempts"], 0)
        self.assertIsNone(result["contained"])
        self.assertIn("absence of evidence", result["note"])

    def test_an_allowed_read_is_reported_as_uncontained(self):
        self.two_roles()
        self.window.read("mk-pad", loop_id="maker")
        result = obs.attempts(self.window.log.records,
                              loop_id="maker", scw_id="mk-pad")
        self.assertEqual(result["allowed_count"], 1)
        self.assertFalse(result["contained"])

    def test_an_unknown_kind_is_an_error_naming_the_known_ones(self):
        result = obs.project(self.window.log.records, kinds=["nonsense"])
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "unknown_kind")
        self.assertIn("refusal", result["known"])


# ---------------------------------------------------------------------------
# routing invariants (0.4.0)
# ---------------------------------------------------------------------------
class TestRoutingPrecedence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.k = st.Knowledge.load()

    def test_precedence_order_is_loop_then_skill_then_agent_then_manual(self):
        self.assertEqual(st.FORMATION_PRECEDENCE,
                         ("loop", "skill", "agent", "manual"))

    def test_a_loop_hit_stops_the_search_at_the_loop_level(self):
        result = st.route("promote working memory into the semantic tier", self.k)
        self.assertEqual(result["how"]["formation"], "loop")
        self.assertEqual(result["evidence"]["levels_tried"], ["loop"])

    def test_a_miss_records_why_each_level_did_not_answer(self):
        result = st.route("zzqx wibblefrotz gnarblewump", self.k)
        self.assertEqual(result["how"]["formation"], "manual")
        levels = {r["level"] for r in result["evidence"]["rejected_because"]}
        self.assertEqual(levels, {"loop", "skill", "agent"})

    def test_the_where_and_how_are_separately_addressable(self):
        result = st.route("promote working memory into the semantic tier", self.k)
        self.assertIsNotNone(result["where"]["scw"])
        self.assertTrue(result["where"]["regions"])
        self.assertIsNotNone(result["how"]["id"])

    def test_the_legacy_decision_shape_still_agrees_with_the_new_one(self):
        result = st.route("promote working memory into the semantic tier", self.k)
        self.assertEqual(result["decision"], "loop_hit")
        self.assertEqual(result["loop"]["id"], result["how"]["id"])


# ---------------------------------------------------------------------------
# experiment invariants (0.3.0 / 0.5.0)
# ---------------------------------------------------------------------------
class TestExperimentInvariants(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._real_dir = exp_mod.EXPERIMENTS_DIR
        exp_mod.EXPERIMENTS_DIR = TMPDIR / "runs"

    @classmethod
    def tearDownClass(cls):
        exp_mod.EXPERIMENTS_DIR = cls._real_dir

    def _spec(self, **over) -> dict:
        base = {
            "id": "invariant-workload",
            "objective": "Exercise the harness.",
            "probe": {"text": "say ONLY-MY-SCOPE if you cannot",
                      "sentinel": "ONLY-MY-SCOPE"},
            "tasks": [{"id": "t1", "title": "T1",
                       "task": "promote working memory into the semantic tier"}],
        }
        base.update(over)
        return base

    def test_prompt_integrity_the_dispatched_text_is_the_rendered_text(self):
        """No elided material may be reintroduced into a dispatched prompt."""
        session = st.Session()
        exp = exp_mod.Experiment.create(session, spec=self._spec())
        exp.materialize(session)
        for call in exp.doc["calls"]:
            reachable = set(call["reads_from"])
            for region_id in session.window.regions:
                if region_id in reachable:
                    continue
                contents = session.window.regions[region_id].entries
                for entry in contents:
                    if entry.data and len(entry.data) > 24:
                        self.assertNotIn(entry.data, call["prompt"])

    def test_ingestion_is_idempotent_per_call(self):
        session = st.Session()
        exp = exp_mod.Experiment.create(session, spec=self._spec())
        exp.materialize(session)
        call = exp.next_call()
        first = exp.ingest(session, call["call_id"], "one")
        second = exp.ingest(session, call["call_id"], "two")
        self.assertTrue(first["ok"])
        self.assertTrue(second["already_ingested"])
        stored = next(c for c in exp.doc["calls"] if c["call_id"] == call["call_id"])
        self.assertEqual(stored["response"], "one")

    def test_leakage_is_graded_only_on_the_spec_sentinel(self):
        session = st.Session()
        exp = exp_mod.Experiment.create(session, spec=self._spec())
        exp.materialize(session)
        self.assertEqual(exp._grade_probe("ONLY-MY-SCOPE"), "refused")
        self.assertEqual(exp._grade_probe("I cannot see it"), "disclosed_or_other")
        self.assertIsNone(exp._grade_probe(None))

    def test_token_accounting_uses_the_runtime_tokenizer(self):
        session = st.Session()
        exp = exp_mod.Experiment.create(session, spec=self._spec())
        exp.materialize(session)
        call = exp.next_call()
        exp.ingest(session, call["call_id"], "a response", probe_response="ONLY-MY-SCOPE")
        stored = next(c for c in exp.doc["calls"] if c["call_id"] == call["call_id"])
        self.assertGreater(stored["tokens"]["input"], 0)
        self.assertGreater(stored["tokens"]["output"], 0)
        self.assertEqual(
            stored["tokens"]["total"],
            stored["tokens"]["input"] + stored["tokens"]["output"]
            + stored["tokens"]["probe_output"])

    def test_null_handling_an_unmeasured_field_is_null_not_zero(self):
        session = st.Session()
        spec = self._spec()
        spec.pop("probe")
        exp = exp_mod.Experiment.create(session, spec=spec)
        exp.materialize(session)
        report = exp.report(session)
        for stats in report["per_condition"].values():
            self.assertIsNone(stats["leak_refusal_rate"])

    def test_underpowered_conditions_are_flagged_rather_than_rated(self):
        session = st.Session()
        exp = exp_mod.Experiment.create(session, spec=self._spec())
        exp.materialize(session)
        call = exp.next_call()
        exp.ingest(session, call["call_id"], "x", probe_response="ONLY-MY-SCOPE")
        report = exp.report(session)
        self.assertIn("underpowered", [r["kind"] for r in report["residue"]])

    def test_residue_reporting_names_every_unmeasured_quantity(self):
        session = st.Session()
        exp = exp_mod.Experiment.create(session, spec=self._spec())
        exp.materialize(session)
        report = exp.report(session)
        self.assertTrue(report["residue"])
        for item in report["residue"]:
            self.assertIn("kind", item)
            self.assertIn("detail", item)

    # -- 0.5.0 routing axis --------------------------------------------------
    def test_a_baseline_condition_without_a_baseline_loop_is_refused(self):
        """The control must not silently fall back to the routed formation."""
        with self.assertRaises(exp_mod.SpecError) as caught:
            exp_mod.normalize_spec(self._spec(conditions=[
                {"id": "ctl", "partition": "scw", "routing": "baseline"}]))
        self.assertIn("baseline_loop", str(caught.exception))

    def test_an_unknown_routing_value_is_refused(self):
        with self.assertRaises(exp_mod.SpecError):
            exp_mod.normalize_spec(self._spec(conditions=[
                {"id": "x", "partition": "scw", "routing": "vibes"}]))

    def test_formation_selection_follows_the_routing_axis(self):
        session = st.Session()
        spec = self._spec(
            conditions=[{"id": "m", "partition": "scw", "routing": "maxey0"},
                        {"id": "b", "partition": "scw", "routing": "baseline"}],
            tasks=[{"id": "t1", "title": "T1",
                    "task": "promote working memory into the semantic tier",
                    "baseline_loop": "battery:l3-pipeline"}])
        exp = exp_mod.Experiment.create(session, spec=spec)
        task = exp.doc["tasks"][0]
        self.assertEqual(exp._loop_for(task, "b"), "battery:l3-pipeline")
        self.assertEqual(exp._loop_for(task, "m"), task["routing"]["loop_id"])
        self.assertNotEqual(exp._loop_for(task, "m"), exp._loop_for(task, "b"))

    def test_routing_correctness_is_graded_against_the_declared_valid_set(self):
        session = st.Session()
        spec = self._spec(tasks=[{
            "id": "t1", "title": "T1",
            "task": "promote working memory into the semantic tier",
            "valid_loops": ["definitely-not-the-routed-one"]}])
        exp = exp_mod.Experiment.create(session, spec=spec)
        self.assertFalse(exp.doc["tasks"][0]["routing"]["correct"])
        report = exp.report(session)
        self.assertEqual(report["routing"]["reliability"], 0.0)

    def test_correctness_is_null_when_no_valid_set_was_declared(self):
        """Ungraded is not the same as wrong."""
        session = st.Session()
        exp = exp_mod.Experiment.create(session, spec=self._spec())
        self.assertIsNone(exp.doc["tasks"][0]["routing"]["correct"])
        report = exp.report(session)
        self.assertIsNone(report["routing"]["reliability"])
        self.assertIn("routing_correctness_ungraded",
                      [r["kind"] for r in report["residue"]])

    def test_a_delta_against_a_null_measurement_stays_null(self):
        """Never a difference against zero — that invents a measurement."""
        compared = exp_mod.Experiment._compare({
            "a": {"partition": "scw", "routing": "maxey0", "tokens": 100,
                  "verified_work": 1, "efficiency": 0.01,
                  "leak_refusal_rate": None, "mean_read_closure": 2.0},
            "b": {"partition": "flat", "routing": "maxey0", "tokens": 60,
                  "verified_work": 1, "efficiency": 0.016,
                  "leak_refusal_rate": 1.0, "mean_read_closure": 1.0},
        })
        deltas = compared["a_minus_b"]["deltas"]
        self.assertEqual(deltas["tokens"], 40)
        self.assertIsNone(deltas["leak_refusal_rate"])
        self.assertTrue(compared["a_minus_b"]["axes_differ"]["partition"])
        self.assertFalse(compared["a_minus_b"]["axes_differ"]["routing"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
