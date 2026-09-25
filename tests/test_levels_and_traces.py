"""One test per property of the isolation ladder and the trace correlation.

The properties:

    a level is earned, never asserted   declaring L3 and running L1 must report L1
    shared regions are not isolation    roles on one region are one role, twice named
    no delegated actor caps at L1       a partition that exists only in the prompt
                                        is representational, not enforced
    residue caps below L3               a fail-open or an unattributable call is a
                                        hole exactly where the evidence would go
    the join is causal, not clock-based two processes, two clocks; the anchor orders
    a role handed context that never    acted is a finding, not a blank row
    the merged view is not evidence     each chain is verified separately
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from gate import levels  # noqa: E402
from maxey0_studio import traces  # noqa: E402


def loop(loop_id: str, scw_id: str) -> dict:
    return {"loop_id": loop_id, "scw_id": scw_id, "status": "bound",
            "read_closure": [scw_id]}


def gate(event_type: str, loop_id=None, actor_ref=None, attributed=True,
         seq: int = 0, reason_code: str = "in_scope", tool: str = "Read",
         at_seq=None) -> dict:
    return {
        "type": event_type, "seq": seq, "ts": 1.0,
        "anchor": {"run_id": "r1", "at_seq": at_seq},
        "payload": {"loop_id": loop_id, "actor_ref": actor_ref,
                    "attributed": attributed, "reason_code": reason_code,
                    "tool": tool, "kind": "file_read"},
    }


class ALevelIsEarnedNotAsserted(unittest.TestCase):

    def test_declaring_l3_while_running_l1_reports_l1(self):
        """The failure this ladder exists to catch: a partition in the prompt only."""
        loops = [loop("maker", "pad-m"), loop("judge", "pad-j")]
        out = levels.assess(loops, [], declared="L3_observed")
        self.assertEqual(out.evidenced, "L1_logical")
        self.assertFalse(out.holds)
        self.assertTrue(any("no delegated actor" in s for s in out.shortfall))

    def test_roles_sharing_one_region_are_l0(self):
        loops = [loop("maker", "shared"), loop("checker", "shared"),
                 loop("judge", "shared")]
        out = levels.assess(loops, [], declared="L2_execution")
        self.assertEqual(out.evidenced, "L0_none")
        self.assertFalse(out.holds)

    def test_no_bound_loop_is_l0(self):
        out = levels.assess([], [])
        self.assertEqual(out.evidenced, "L0_none")

    def test_distinct_regions_plus_observed_actors_reaches_l2(self):
        loops = [loop("maker", "pad-m"), loop("judge", "pad-j")]
        records = [
            gate("gate.allowed", "maker", actor_ref="a1", seq=0),
            gate("gate.allowed", "judge", actor_ref="a2", seq=1),
        ]
        out = levels.assess(loops, records)
        # L2, not L3: reintegration was never measured, and L3 asserts that
        # only declared outputs crossed back.
        self.assertEqual(out.evidenced, "L2_execution")
        self.assertEqual(out.signals["delegated_actors_observed"], 2)

    def test_l3_requires_reintegration_to_have_been_measured(self):
        """Unmeasured is not a pass.

        L3's guarantee asserts reintegration carried only the declared outputs.
        Awarding it to a run where nobody checked would state as fact the one
        thing that was never looked at.
        """
        loops = [loop("maker", "pad-m"), loop("judge", "pad-j")]
        records = [gate("gate.allowed", "maker", actor_ref="a1", seq=0)]

        unmeasured = levels.assess(loops, records)
        self.assertEqual(unmeasured.evidenced, "L2_execution")
        self.assertTrue(any("reintegration was not measured" in s
                            for s in unmeasured.shortfall))

        measured = levels.assess(loops, records, reintegration_declared_only=True)
        self.assertEqual(measured.evidenced, "L3_observed")

    def test_a_lost_record_caps_below_l3(self):
        """A torn line is residue by GATE.md's own definition."""
        loops = [loop("maker", "pad-m"), loop("judge", "pad-j")]
        records = [gate("gate.allowed", "maker", actor_ref="a1", seq=0)]
        out = levels.assess(loops, records, reintegration_declared_only=True,
                            damaged=2)
        self.assertEqual(out.evidenced, "L2_execution")
        self.assertEqual(out.signals["damaged_records"], 2)
        self.assertTrue(any("lost to unparseable" in s for s in out.shortfall))

    def test_an_unattributed_call_caps_below_l3(self):
        loops = [loop("maker", "pad-m"), loop("judge", "pad-j")]
        records = [
            gate("gate.allowed", "maker", actor_ref="a1", seq=0),
            gate("gate.observed", None, actor_ref="a9", attributed=False,
                 seq=1, reason_code="unattributed"),
        ]
        out = levels.assess(loops, records)
        self.assertEqual(out.evidenced, "L2_execution")
        self.assertTrue(any("could not be attributed" in s for s in out.shortfall))

    def test_a_fail_open_caps_below_l3(self):
        loops = [loop("maker", "pad-m"), loop("judge", "pad-j")]
        records = [
            gate("gate.allowed", "maker", actor_ref="a1", seq=0),
            gate("gate.fail_open", "maker", actor_ref="a1", seq=1),
        ]
        out = levels.assess(loops, records)
        self.assertEqual(out.evidenced, "L2_execution")
        self.assertTrue(any("fail-open" in s for s in out.shortfall))

    def test_uncontrolled_reintegration_caps_below_l3(self):
        loops = [loop("maker", "pad-m"), loop("judge", "pad-j")]
        records = [gate("gate.allowed", "maker", actor_ref="a1", seq=0)]
        out = levels.assess(loops, records, reintegration_declared_only=False)
        self.assertEqual(out.evidenced, "L2_execution")
        self.assertTrue(any("shared scratchpad" in s for s in out.shortfall))

    def test_every_level_states_what_it_may_not_claim(self):
        """A level that only lists guarantees invites the overclaim."""
        for entry in levels.ladder():
            self.assertIn("may_not_claim", entry)
            self.assertTrue(entry["may_not_claim"])

    def test_l1_explicitly_refuses_the_hard_isolation_claim(self):
        self.assertIn("representational",
                      levels.GUARANTEES["L1_logical"]["may_not_claim"])

    def test_l3_still_refuses_representational_independence(self):
        self.assertIn("representational independence",
                      levels.GUARANTEES["L3_observed"]["may_not_claim"])


class TheTracesCorrelate(unittest.TestCase):

    def _runtime(self):
        return [
            {"type": "scw.create", "seq": 0, "ts": 1.0, "actor": "orchestrator",
             "payload": {"scw_id": "pad-m"}},
            {"type": "scw.write", "seq": 1, "ts": 1.1, "actor": "orchestrator",
             "payload": {"scw_id": "ref", "tokens": 120}},
            {"type": "loop.bind", "seq": 2, "ts": 1.2, "actor": "orchestrator",
             "payload": {"loop_id": "maker", "scw_id": "pad-m"}},
            {"type": "window.render", "seq": 3, "ts": 1.3, "actor": "loop:maker",
             "payload": {"loop_id": "maker", "tokens": 900}},
        ]

    def test_a_render_is_the_transfer_moment(self):
        out = traces.context_trace(self._runtime())
        self.assertEqual(len(out["transfers"]), 1)
        self.assertEqual(out["transfers"][0]["loop_id"], "maker")

    def test_execution_events_order_by_anchor_not_clock(self):
        """Two processes, two clocks. The anchor is the causal key."""
        runtime = self._runtime()
        gate_records = [
            # ts says this came first; the anchor says it came after runtime seq 3
            gate("gate.allowed", "maker", actor_ref="a1", seq=0, at_seq=3),
        ]
        gate_records[0]["ts"] = 0.0
        out = traces.correlate(runtime, gate_records)
        kinds = [row["plane"] for row in out["timeline"]]
        self.assertEqual(kinds[-1], "execution")
        self.assertFalse(out["join"]["verifiable_as_one_chain"])
        self.assertIn("wall-clock", out["join"]["not_used"])

    def test_a_role_handed_context_that_never_acted_is_a_finding(self):
        out = traces.correlate(self._runtime(), [])
        maker = next(r for r in out["by_role"] if r["loop_id"] == "maker")
        self.assertEqual(maker["transfers_in"], 1)
        self.assertEqual(maker["tool_calls"], 0)
        self.assertIn("no tool call observed", maker["finding"])

    def test_a_role_acting_with_no_recorded_transfer_is_a_finding(self):
        out = traces.correlate([], [gate("gate.allowed", "ghost", actor_ref="a1")])
        ghost = next(r for r in out["by_role"] if r["loop_id"] == "ghost")
        self.assertIn("no context transfer recorded", ghost["finding"])

    def test_unattributed_calls_are_named_as_residue(self):
        records = [gate("gate.observed", None, actor_ref="a9", attributed=False,
                        reason_code="unattributed")]
        out = traces.correlate([], records)
        row = next(r for r in out["by_role"] if r["loop_id"] is None)
        self.assertIn("residue", row["finding"])

    def test_the_state_trace_says_it_is_not_semantic(self):
        """Calling a content hash a semantic delta would be the overclaim."""
        out = traces.state_trace(self._runtime())
        self.assertIn("not a semantic one", out["not_measured"])
        self.assertEqual(out["regions"][0]["scw_id"], "ref")
        self.assertEqual(out["regions"][0]["tokens_written"], 120)

    def test_a_denied_call_shows_up_in_the_role_join(self):
        records = [gate("gate.denied", "maker", actor_ref="a1",
                        reason_code="path_outside_scope")]
        out = traces.correlate(self._runtime(), records)
        maker = next(r for r in out["by_role"] if r["loop_id"] == "maker")
        self.assertEqual(maker["denied"], 1)
        self.assertIn("outside the declared scope", maker["finding"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
