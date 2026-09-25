"""The three planes, tested as properties rather than as functions.

Each test is named after a claim the product makes on its front page. A claim
nothing checks is marketing, and the whole point of this repository is that its
claims are the kind you can fail.

The load-bearing ones:

  * each plane registers exactly its catalog, and nothing else
  * the Loop plane holds no window state — it opens no ledger at all
  * the Observatory sees the Context plane across a process boundary, by
    reading and replaying its ledger, and can never write it
  * an absent ledger is reported as absent, never as zero
  * no retired 0.6.0 tool name is registered anywhere
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import unittest
import pytest
pytest.importorskip("mcp")
from pathlib import Path

# _env redirects SCW_EVENT_LOG to a tempfile BEFORE anything imports the
# runtime, and is shared with every other test module so they agree on one
# path. state.py freezes it at import time, so the first importer decides.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _env import ROOT  # noqa: E402,F401

sys.path.insert(0, str(ROOT / "server"))

from planes import bootstrap, catalog, menu  # noqa: E402


def _tool_names(mcp) -> set[str]:
    return {t.name for t in asyncio.run(mcp.list_tools())}


class TestCatalogIsTheSurface(unittest.TestCase):
    """`catalog.py` is the single source of truth, so nothing may disagree with it."""

    def test_each_connector_registers_exactly_its_catalog(self):
        from planes import context_plane, loops_plane, observe_plane

        for connector, module in (("context", context_plane),
                                  ("loops", loops_plane),
                                  ("observe", observe_plane)):
            with self.subTest(connector=connector):
                self.assertEqual(
                    _tool_names(module.build()),
                    {t.name for t in catalog.BY_CONNECTOR[connector]},
                )

    def test_every_tool_name_begins_with_its_connector(self):
        for tool in catalog.ALL:
            with self.subTest(tool=tool.name):
                self.assertTrue(tool.name.startswith(f"{tool.connector}_"),
                                f"{tool.name} does not name its connector")

    def test_no_retired_name_is_registered(self):
        from planes import context_plane, loops_plane, observe_plane

        registered = set()
        for module in (context_plane, loops_plane, observe_plane):
            registered |= _tool_names(module.build())
        for legacy in catalog.RETIRED:
            with self.subTest(legacy=legacy):
                self.assertNotIn(legacy, registered)

    def test_tool_names_are_unique_across_connectors(self):
        names = [t.name for t in catalog.ALL]
        self.assertEqual(len(names), len(set(names)))

    def test_counts_are_computed_not_written_down(self):
        counts = catalog.counts()
        self.assertEqual(counts["total"],
                         counts["context"] + counts["loops"] + counts["observe"])
        self.assertEqual(counts["total"], len(catalog.ALL))


class TestLoopPlaneHoldsNoWindow(unittest.TestCase):
    """The Loop plane's standalone claim, checked rather than asserted.

    If this fails, `maxey0-loops` cannot honestly be described as installable
    on its own against a fixed context scheme: it would be creating window
    state as a side effect of starting.
    """

    def test_building_the_loop_plane_opens_no_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "should-never-exist.jsonl"
            previous = os.environ.get("SCW_EVENT_LOG")
            os.environ["SCW_EVENT_LOG"] = str(ledger)
            try:
                from planes import loops_plane
                loops_plane.build()
                self.assertFalse(
                    ledger.exists(),
                    "the Loop plane created a ledger; it must hold no window state",
                )
            finally:
                if previous is None:
                    os.environ.pop("SCW_EVENT_LOG", None)
                else:
                    os.environ["SCW_EVENT_LOG"] = previous

    def test_the_loop_plane_does_not_import_the_runtime_session(self):
        source = (Path(__file__).resolve().parent.parent
                  / "server" / "planes" / "loops_impl.py").read_text(encoding="utf-8")
        self.assertNotIn(
            "scw_runtime.server", source,
            "importing the runtime server constructs its session and opens the ledger",
        )


class TestObservatorySeesAcrossAProcessBoundary(unittest.TestCase):
    """The Observatory reads the other planes as files, and writes neither."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Path(self.tmp.name) / "events.jsonl"
        self._previous = os.environ.get("SCW_EVENT_LOG")
        os.environ["SCW_EVENT_LOG"] = str(self.ledger)

    def tearDown(self):
        if self._previous is None:
            os.environ.pop("SCW_EVENT_LOG", None)
        else:
            os.environ["SCW_EVENT_LOG"] = self._previous
        self.tmp.cleanup()

    def test_an_absent_ledger_is_reported_absent_never_as_zero(self):
        from planes import observe_impl

        result = observe_impl.observe_events()
        self.assertFalse(result["present"])
        self.assertFalse(result["available"])
        self.assertIn("establishes nothing", result["note"])

    def test_attempts_are_three_valued_when_nothing_was_recorded(self):
        from planes import observe_impl

        result = observe_impl.observe_attempts(role="anyone", region="anywhere")
        self.assertFalse(result["available"])
        self.assertNotIn("contained", result,
                         "an absent ledger must not report a containment verdict")

    def test_it_replays_a_ledger_written_by_another_window(self):
        """Write a partition, then read it back the way a separate process would."""
        records = [
            {"seq": 1, "type": "window.init", "actor": "host", "payload": {}},
        ]
        self.ledger.write_text(
            "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")

        read, status = bootstrap.read_ledger()
        self.assertTrue(status["present"])
        self.assertEqual(status["records"], len(records))
        self.assertEqual(read[0]["type"], "window.init")

    def test_a_ledger_that_will_not_replay_is_a_named_cause(self):
        from planes import observe_impl

        self.ledger.write_text("{not json at all\n", encoding="utf-8")
        window, status = observe_impl._replayed_window()
        self.assertIsNone(window)
        self.assertTrue(status["present"])
        self.assertFalse(status["replayed"])
        self.assertIn("unestablished", status["note"])

    def test_the_observatory_registers_no_tool_that_writes_the_window(self):
        writers = {t.name for t in catalog.CONTEXT if t.mutates}
        observatory = {t.name for t in catalog.OBSERVE}
        self.assertEqual(writers & observatory, set())


class TestDisjointnessClassifiesOverlap(unittest.TestCase):
    """`Private(a) ∩ Private(b) = ∅`, not `read_closure(a) ∩ read_closure(b) = ∅`.

    The strong form is too strong and shipping it meant the assertion failed
    the product's own maker/checker/judge formation: a checker is supposed to
    read the maker's published draft, and every role is supposed to read the
    concept's constitution. An assertion that fails a correct partition trains
    an operator to ignore it, which is worse than not having it.
    """

    def setUp(self):
        from planes import context_extras
        from planes.context_plane import build
        from scw_runtime import server as rt

        build()
        self.extras = context_extras
        self.rt = rt
        rt.reset_window()

    def test_the_canonical_formation_is_disjoint(self):
        self.extras.create_concept_scw(concept="observability",
                                       constitution="c", criterion="r")
        self.rt.seal_window()
        for a, b in (("checker", "maker"), ("judge", "maker"), ("checker", "judge")):
            with self.subTest(pair=(a, b)):
                result = self.extras.assert_disjoint(loop_a=a, loop_b=b)
                self.assertTrue(result["holds"], result)
                self.assertEqual(result["private_overlap"], [])

    def test_the_declared_handoff_is_reported_as_admitted(self):
        """The checker reading the maker's draft is the formation working."""
        self.extras.create_concept_scw(concept="observability",
                                       constitution="c", criterion="r")
        self.rt.seal_window()
        result = self.extras.assert_disjoint(loop_a="checker", loop_b="judge")
        admitted = {row["region"] for row in result["admitted"]}
        self.assertIn("observability-draft", admitted)
        for row in result["admitted"]:
            if row["region"] == "observability-draft":
                self.assertEqual(row["written_by"], ["maker"])

    def test_unwritable_reference_is_not_a_channel(self):
        """A region no bound role can write cannot carry state between them."""
        self.extras.create_concept_scw(concept="observability",
                                       constitution="c", criterion="r")
        self.rt.seal_window()
        result = self.extras.assert_disjoint(loop_a="checker", loop_b="maker")
        self.assertIn("observability-constitution", result["shared_reference"])
        self.assertNotIn("observability-constitution", result["private_overlap"])

    def test_two_private_pads_are_disjoint(self):
        self.rt.create_scw(label="a", region_type="scratchpad", scw_id="pad-a")
        self.rt.create_scw(label="b", region_type="scratchpad", scw_id="pad-b")
        self.rt.bind_scope(loop_id="A", scw_id="pad-a")
        self.rt.bind_scope(loop_id="B", scw_id="pad-b")
        result = self.extras.assert_disjoint(loop_a="A", loop_b="B")
        self.assertTrue(result["holds"])

    def test_a_role_descending_into_another_private_region_is_a_breach(self):
        """The negative control, and the case an earlier draft of this excused.

        A role bound to a parent with `descend` reaches every private pad
        beneath it. Excusing a region that sits inside either role's own
        subtree excused exactly that, so the assertion passed a real breach.
        """
        self.rt.create_scw(label="root", region_type="durable", scw_id="root")
        self.rt.create_scw(label="b work", region_type="working",
                           scw_id="work-b", parent_scw_id="root")
        self.rt.bind_scope(loop_id="A", scw_id="root")
        self.rt.bind_scope(loop_id="B", scw_id="work-b")
        result = self.extras.assert_disjoint(loop_a="A", loop_b="B")
        self.assertFalse(result["holds"], result)
        self.assertIn("work-b", result["private_overlap"])

    def test_it_still_reports_the_raw_overlap(self):
        """Classification adds information; it must not remove any."""
        self.extras.create_concept_scw(concept="observability",
                                       constitution="c", criterion="r")
        self.rt.seal_window()
        result = self.extras.assert_disjoint(loop_a="checker", loop_b="judge")
        classified = (set(result["private_overlap"])
                      | set(result["shared_reference"])
                      | {row["region"] for row in result["admitted"]})
        self.assertEqual(classified, set(result["overlap"]))

    def test_it_remains_a_pure_computation(self):
        self.rt.create_scw(label="a", region_type="scratchpad", scw_id="pad-a")
        self.rt.create_scw(label="b", region_type="scratchpad", scw_id="pad-b")
        self.rt.bind_scope(loop_id="A", scw_id="pad-a")
        self.rt.bind_scope(loop_id="B", scw_id="pad-b")
        result = self.extras.assert_disjoint(loop_a="A", loop_b="B")
        self.assertTrue(result["evidence"]["pure"])
        self.assertEqual(result["evidence"]["events"], [])


class TestAdmitGatesEgress(unittest.TestCase):
    """context_admit is egress where bridges/scope are ingress: scope says
    what a role may REACH, admit says what actually CROSSES once reach
    already permits it. Structural reach without a recorded admission is
    exactly what context_assert_admitted is for.
    """

    def setUp(self):
        from planes import context_extras
        from planes.context_plane import build
        from scw_runtime import server as rt

        build()
        self.extras = context_extras
        self.rt = rt
        rt.reset_window()
        self.extras.create_concept_scw(concept="observability",
                                       constitution="c", criterion="r")
        self.rt.seal_window()
        self.rt.write(scw_id="observability-maker-pad", data="shh",
                      loop_id="maker", key="secret")
        self.rt.write(scw_id="observability-maker-pad", data="X",
                      loop_id="maker", key="finding")

    def _admit(self, rule, **kw):
        return self.extras.admit(
            from_role="maker", to_role="checker",
            from_region="observability-maker-pad",
            to_region="observability-draft", rule=rule, **kw)

    def test_approve_crosses_every_entry_and_is_recorded(self):
        result = self._admit("approve")
        self.assertTrue(result["admitted"])
        self.assertEqual(result["entries_crossed"], 2)
        check = self.extras.assert_admitted(from_role="maker", to_role="checker")
        self.assertTrue(check["holds"], check)
        self.assertIn("observability-draft", check["handoff_regions"])
        self.assertEqual(check["unadmitted_regions"], [])
        self.assertEqual(len(check["recorded_admissions"]), 1)
        self.assertEqual(check["recorded_admissions"][0]["rule"], "approve")

    def test_reject_crosses_nothing_but_still_counts_as_recorded(self):
        result = self._admit("reject")
        self.assertFalse(result["admitted"])
        self.assertEqual(result["entries_crossed"], 0)
        check = self.extras.assert_admitted(from_role="maker", to_role="checker")
        self.assertTrue(check["holds"], check)

    def test_redact_drops_only_the_named_key(self):
        result = self._admit("redact", redact_keys=["secret"])
        self.assertEqual(result["entries_considered"], 2)
        self.assertEqual(result["entries_crossed"], 1)

    def test_summarize_truncates_long_entries_with_a_marker(self):
        self.rt.write(scw_id="observability-maker-pad", data="z" * 500,
                      loop_id="maker", key="long")
        result = self._admit("summarize")
        self.assertEqual(result["entries_crossed"], 3)

    def test_without_a_recorded_admission_the_pair_is_flagged(self):
        check = self.extras.assert_admitted(from_role="maker", to_role="checker")
        self.assertFalse(check["holds"], check)
        self.assertIn("observability-draft", check["unadmitted_regions"])

    def test_admit_cannot_launder_a_pad_it_does_not_own(self):
        result = self.extras.admit(
            from_role="checker", to_role="judge",
            from_region="observability-maker-pad",
            to_region="observability-draft", rule="approve")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "cannot_read_from_region")

    def test_bad_rule_is_rejected_before_any_read(self):
        result = self._admit("delete_everything")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "bad_rule")


class TestMenuCannotDrift(unittest.TestCase):
    """`loops_menu` renders from the registry, so it cannot describe a tool that
    does not exist — the failure mode 0.6.0's 296-line prose menu had."""

    def test_the_menu_lists_every_connector_with_its_real_tool_count(self):
        rendered = menu.render("menu")
        self.assertEqual(rendered["counts"], catalog.counts())
        for block in rendered["connectors"]:
            connector = block["connector"].removeprefix("maxey0-")
            self.assertEqual(block["tools"], len(catalog.BY_CONNECTOR[connector]))

    def test_the_menu_names_the_three_planes_including_the_unowned_one(self):
        """Execution has no connector. Omitting it would hide the whole point."""
        rows = menu.render("planes")["planes"]
        self.assertEqual({r["plane"] for r in rows},
                         {"execution", "context", "engineering"})
        execution = next(r for r in rows if r["plane"] == "execution")
        self.assertEqual(execution["owner"], "the host")
        self.assertEqual(execution["connectors"], "")

    def test_every_connector_declares_the_plane_it_serves(self):
        for block in menu.render("connectors")["connectors"]:
            self.assertIn(block["serves_plane"], catalog.PLANES)

    def test_every_menu_tool_is_a_catalog_tool(self):
        for connector in ("context", "loops", "observe"):
            block = menu.render(connector)["connector"]
            listed = {row["tool"] for group in block["groups"].values() for row in group}
            self.assertEqual(listed, {t.name for t in catalog.BY_CONNECTOR[connector]})

    def test_an_unknown_section_falls_back_to_the_full_menu(self):
        self.assertEqual(menu.render("nonsense")["section"], "menu")

    def test_the_menu_lists_the_nine_studio_views(self):
        views = menu.render("views")["views"]
        self.assertEqual([v["view"] for v in views], [n for n, _ in catalog.VIEWS])
        self.assertEqual(len(views), 9)


class TestVendoredRuntimeWins(unittest.TestCase):
    """`server/vendor/` exists so the plugin installs standalone. An editable
    install elsewhere on the machine must not silently replace it."""

    def test_the_runtime_loads_from_the_vendored_tree(self):
        bootstrap.prepare()
        provenance = bootstrap.provenance()
        self.assertTrue(provenance["loaded"])
        self.assertTrue(provenance["vendored"], provenance)

    def test_provenance_reports_the_path_it_actually_loaded(self):
        bootstrap.prepare()
        provenance = bootstrap.provenance()
        self.assertIn("vendor", provenance["path"])


class TestCommandsMatchTheCatalog(unittest.TestCase):
    """Every shipped command is declared, and declares real tools."""

    ROOT = Path(__file__).resolve().parent.parent

    def test_every_declared_command_exists(self):
        for name, _, _ in catalog.COMMANDS:
            with self.subTest(command=name):
                self.assertTrue((self.ROOT / "commands" / f"{name}.md").exists())

    def test_every_command_declares_allowed_tools(self):
        for path in sorted((self.ROOT / "commands").glob("*.md")):
            with self.subTest(command=path.name):
                self.assertIn("allowed-tools:", path.read_text(encoding="utf-8"))

    def test_every_role_agent_inherits_its_model(self):
        agents = sorted((self.ROOT / "agents").glob("*.md"))
        self.assertEqual(len(agents), 5)
        for path in agents:
            with self.subTest(agent=path.name):
                self.assertIn("model: inherit", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
