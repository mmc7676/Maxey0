"""One test per property a Structured Concept Window must have.

The properties:

    the concept is the shared context   every role reads it; no role writes it
    a pad is private, always            no grant reaches another role's pad, and
                                        an upstream role in the topology is no
                                        exception -- that is what makes
                                        declaring an exposure surface a real
                                        requirement rather than a formality
    work crosses only through handoffs  the checker sees the maker's `draft`,
                                        never the maker's reasoning
    the judge is provably disjoint      the runtime would accept its verdict
    the maker cannot edit its rubric    R5: the criterion is outside its write
                                        closure
    building creates no runtime         an SCW is an abstraction; what isolation
                                        a run achieved is measured afterwards
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server" / "vendor"))

import concept_scw as cscw  # noqa: E402
from scw_runtime.window import ContextWindow  # noqa: E402


def built(concept: str = "software-testing") -> tuple[ContextWindow, dict]:
    window = ContextWindow()
    result = cscw.build(
        window, concept,
        constitution="Verifying a program behaves as specified.",
        criterion_text="Every claim is named and cited.",
        skills=["unit-testing", "property-testing"],
    )
    return window, result


class TheConceptIsTheSharedContext(unittest.TestCase):

    def test_every_role_can_read_the_constitution(self):
        window, _ = built()
        for role in ("maker", "checker", "judge"):
            self.assertIn("software-testing-constitution",
                          window.read_closure(role), role)

    def test_no_role_can_write_the_constitution(self):
        """Readable by all, writable by none -- that is what makes it shared."""
        window, _ = built()
        for role in ("maker", "checker", "judge"):
            self.assertNotIn("software-testing-constitution",
                             window.write_closure(role), role)

    def test_every_role_can_read_the_skills_region(self):
        """Skills are the context-transfer operators the concept exposes."""
        window, _ = built()
        for role in ("maker", "checker", "judge"):
            self.assertIn("software-testing-skills", window.read_closure(role), role)


class APadIsPrivateAlways(unittest.TestCase):

    def test_no_role_reaches_another_roles_pad(self):
        window, _ = built()
        pads = {r: f"software-testing-{r}-pad" for r in ("maker", "checker", "judge")}
        for role in pads:
            closure = window.read_closure(role)
            for other, pad in pads.items():
                if other == role:
                    self.assertIn(pad, closure)
                else:
                    self.assertNotIn(pad, closure,
                                     f"{role} can reach {other}'s pad")

    def test_being_upstream_in_the_topology_is_no_exception(self):
        """The checker reads the maker's declared handoff, not its reasoning."""
        window, _ = built()
        checker = window.read_closure("checker")
        self.assertIn("software-testing-draft", checker)
        self.assertNotIn("software-testing-maker-pad", checker)


class WorkCrossesOnlyThroughHandoffs(unittest.TestCase):

    def test_the_maker_publishes_to_its_declared_surface(self):
        window, _ = built()
        self.assertIn("software-testing-draft", window.write_closure("maker"))

    def test_the_judge_reads_both_upstream_handoffs(self):
        window, _ = built()
        closure = window.read_closure("judge")
        self.assertIn("software-testing-draft", closure)
        self.assertIn("software-testing-review", closure)

    def test_a_role_cannot_write_another_roles_handoff(self):
        window, _ = built()
        self.assertNotIn("software-testing-review", window.write_closure("maker"))


class TheJudgeIsProvablyDisjoint(unittest.TestCase):

    def test_the_runtime_would_accept_the_judges_verdict_on_the_maker(self):
        window, _ = built()
        report = window.disjointness("maker", "judge")
        self.assertTrue(report["disjoint"], report["reason"])
        self.assertEqual(report["failed"], [])

    def test_the_maker_cannot_edit_what_it_is_graded_against(self):
        """R5. A party that can edit its own rubric satisfies it vacuously."""
        window, _ = built()
        self.assertNotIn("software-testing-criterion", window.write_closure("maker"))

    def test_a_role_is_not_disjoint_from_itself(self):
        window, _ = built()
        report = window.disjointness("maker", "maker")
        self.assertFalse(report["disjoint"])


class ThePlanIsInspectableBeforeAnythingIsBuilt(unittest.TestCase):

    def test_plan_names_every_region_bind_and_grant(self):
        spec = cscw.plan("memory")
        self.assertEqual(spec["roles"], ["maker", "checker", "judge"])
        self.assertTrue(any(r["scw_id"] == "memory-criterion" for r in spec["regions"]))
        self.assertTrue(all(g["mode"] in ("read", "write") for g in spec["grants"]))

    def test_ids_are_namespaced_by_concept_so_two_windows_never_collide(self):
        a = cscw.plan("memory")
        b = cscw.plan("evaluation")
        ids_a = {r["scw_id"] for r in a["regions"]}
        ids_b = {r["scw_id"] for r in b["regions"]}
        self.assertEqual(ids_a & ids_b, set())

    def test_a_role_reading_a_formation_member_that_does_not_exist_is_refused(self):
        bad = ({"role": "checker", "exposes": ("review",), "reads": ("ghost",)},)
        with self.assertRaises(cscw.ConceptSCWError):
            cscw.plan("x", formation=bad)

    def test_an_empty_formation_is_refused(self):
        with self.assertRaises(cscw.ConceptSCWError):
            cscw.plan("x", formation=())


class SuggestedGatePoliciesAreClosedByDefault(unittest.TestCase):

    def test_a_role_gets_no_filesystem_access_by_default(self):
        """A role works from what render_window gave it; the disk is a decision."""
        spec = cscw.plan("memory")
        for policy in cscw.gate_policies(spec):
            self.assertEqual(policy["read_paths"], [])
            self.assertEqual(policy["tools"], [])
            self.assertEqual(policy["bash_allow"], [])

    def test_a_workdir_root_gives_each_role_its_own_directory(self):
        """The one attribution mechanism portable to hosts with no actor id."""
        spec = cscw.plan("memory")
        policies = cscw.gate_policies(spec, workdir_root="/run/w")
        dirs = [p["workdir"] for p in policies]
        self.assertEqual(len(set(dirs)), len(dirs))
        self.assertIn("/run/w/maker", dirs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
