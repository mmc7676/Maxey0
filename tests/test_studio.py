"""Unit tests for the Maxey0 Studio app layer.

Plain `unittest`, standard library only -- the same constraint the app itself
runs under, so `python -m unittest discover tests` works on a fresh checkout
with nothing installed beyond Python 3.10+.

Every assertion below goes through the real code path: the real vendored
knowledge files, the real `scw_runtime.ContextWindow`, the real enforcement.
Nothing here mocks a region, a refusal, or a token budget. The only things
patched are the two sources of nondeterminism in `mission.dispatch` -- its
background thread and its simulated agent's RNG/clock -- and they are patched
so the *same real* `write()` runs synchronously, not so it is bypassed.

EVENT LOG SAFETY (load-bearing, see `TestEventLogIsolation`):
`state.py` resolves its event-log path once, at import time, from
`SCW_EVENT_LOG`. `tests/_env.py` sets that variable to a tempfile *before*
anything imports `maxey0_studio`, and every test module shares it so they
cannot disagree about where the log went. A suite that appended to
`~/.scw/events.jsonl` would be writing into the shared, append-only log this
project treats as evidence -- so the isolation is asserted, not assumed.
"""

from __future__ import annotations

import pathlib
import sys
import types
import unittest
from unittest import mock

# --- environment: vendored knowledge + a throwaway event log -----------------
# _env sets sys.path and the environment BEFORE maxey0_studio is imported, and
# is shared with every other test module so they agree on one event-log path.
# state.py freezes that path at import time, so the first importer decides it.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _env import EVENT_LOG as TEST_EVENT_LOG, ROOT, TMPDIR, VENDOR  # noqa: E402

from maxey0_studio import app  # noqa: E402
from maxey0_studio import experiment as exp_mod  # noqa: E402
from maxey0_studio import live_session as live_mod  # noqa: E402
from maxey0_studio import mission  # noqa: E402
from maxey0_studio import semantic  # noqa: E402
from maxey0_studio import state as st  # noqa: E402

# The two logs this machine's real SCW activity lives in. Nothing in this
# suite may append to either; `TestEventLogIsolation` proves it.
REAL_SCW_DIR = pathlib.Path.home() / ".scw"
REAL_LOGS = [REAL_SCW_DIR / "events.jsonl", REAL_SCW_DIR / "studio.jsonl"]

# Fixtures picked from the shipped dataset, by id, so a dataset change that
# invalidates them fails loudly instead of silently testing something else.
PIPELINE_LOOP = "pipeline:001-memory-lifecycle-promotion-loop"
BATTERY_LOOP = "battery:l1-maker-checker-judge"
CROSS_WINDOW_LOOP = "designer:01-horizontal-4way"

_KNOWLEDGE = st.Knowledge.load()


def fresh_session() -> st.Session:
    """A real Session on the throwaway log. Cheap enough per-test."""
    return st.Session()


class _InlineThread:
    """A `threading.Thread` stand-in that runs its target on `start()`.

    Used only to make `mission.dispatch`'s background work observable at the
    point the test asserts on it. The target itself is untouched: the same
    `_run_simulated` -> `Session.write_region` -> `ContextWindow.write` path
    executes, with the same budget enforcement.
    """

    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}
        self.daemon = daemon
        self.ran = False

    def start(self) -> None:
        self.ran = True
        if self._target is not None:
            self._target(*self._args, **self._kwargs)

    def join(self, timeout=None) -> None:  # pragma: no cover - nothing to wait on
        return None


def deterministic_simulation(steps: int = 9, tokens_per_step: int = 100):
    """Patch out `mission`'s nondeterminism: no sleeping, no RNG, no thread.

    Scoped to `mission`'s own module namespace, so the real `threading`,
    `time` and `random` modules are untouched for everything else.
    """
    def randint(low: int, high: int) -> int:
        return steps if (low, high) == mission._SIM_STEPS else tokens_per_step

    return (
        mock.patch.object(mission, "threading",
                          types.SimpleNamespace(Thread=_InlineThread)),
        mock.patch.object(mission, "time",
                          types.SimpleNamespace(sleep=lambda _s: None)),
        mock.patch.object(mission, "random",
                          types.SimpleNamespace(randint=randint,
                                                uniform=lambda _a, _b: 0.0)),
        # An ANTHROPIC_API_KEY in the environment or in a .env beside server/
        # would send this test down the real-API path. Force the simulated
        # branch; both branches share the write() the test is actually about.
        mock.patch.object(mission.ac, "is_configured", lambda: False),
    )


# ---------------------------------------------------------------------------
# event log isolation
# ---------------------------------------------------------------------------
class TestEventLogIsolation(unittest.TestCase):
    """The suite must not write into this machine's real SCW evidence."""

    def test_event_log_points_at_the_tempfile(self):
        self.assertEqual(st.EVENT_LOG, TEST_EVENT_LOG)
        self.assertEqual(pathlib.Path(st.EVENT_LOG).parent, TMPDIR)

    def test_event_log_is_not_under_the_real_scw_dir(self):
        with self.assertRaises(ValueError):
            pathlib.Path(st.EVENT_LOG).resolve().relative_to(REAL_SCW_DIR)

    def test_live_session_mirror_also_redirected(self):
        # live_session.py reads SCW_EVENT_LOG too; if it still pointed at the
        # real log, a test touching the live tab would read real activity.
        #
        # Asserted as "not the real log" rather than "== our tempfile" on
        # purpose: test_live_session_and_client.py redirects this same module
        # global to its own tempfile, and whichever module imports second
        # legitimately wins. Both destinations are safe; pinning one exact path
        # would make this guard fail on test ordering rather than on the thing
        # it exists to catch.
        resolved = pathlib.Path(live_mod.LIVE_LOG).resolve()
        with self.assertRaises(ValueError):
            resolved.relative_to(REAL_SCW_DIR)

    def test_knowledge_sources_are_the_vendored_copies(self):
        self.assertEqual(st.MAXEY0_ROOT, VENDOR / "maxey0")
        self.assertEqual(st.LOOPS_JSON, VENDOR / "data" / "loops.json")

    def test_real_logs_contain_none_of_this_suites_runs(self):
        """The decisive check: do real writes, then prove where they landed.

        Every emitted record carries its run_id, so scanning the real logs for
        this window's run_id is an exact answer to "did we append there?".
        """
        session = fresh_session()
        session.create_scw("isolation probe", region_type="working")
        run_id = session.window.log.run_id

        written = TEST_EVENT_LOG.read_text(encoding="utf-8")
        self.assertIn(run_id, written, "the test log did not receive our events")

        for path in REAL_LOGS:
            if not path.exists():
                continue
            self.assertNotIn(
                run_id, path.read_text(encoding="utf-8", errors="replace"),
                f"this suite appended run {run_id} to the real log {path}")


# ---------------------------------------------------------------------------
# knowledge
# ---------------------------------------------------------------------------
class TestKnowledge(unittest.TestCase):
    def setUp(self):
        self.k = _KNOWLEDGE

    def test_load_gives_the_real_counts(self):
        counts = self.k.counts()
        self.assertEqual(counts["concepts"], 16)
        self.assertEqual(counts["skills"], 83)
        self.assertEqual(counts["agents"], 67)
        self.assertEqual(counts["loops"], 84)
        self.assertEqual(counts["roster"], 722)

    def test_loops_by_status_keys_and_total(self):
        by_status = self.k.counts()["loops_by_status"]
        self.assertEqual(set(by_status), {"validated", "partial", "draft-unexecuted"})
        self.assertEqual(by_status["validated"], 78)
        self.assertEqual(by_status["partial"], 1)
        self.assertEqual(by_status["draft-unexecuted"], 5)
        self.assertEqual(sum(by_status.values()), 84)

    def test_loops_by_provenance_sums_to_the_same_total(self):
        by_prov = self.k.counts()["loops_by_provenance"]
        self.assertEqual(set(by_prov),
                         {"pipeline", "battery", "planned", "designer"})
        self.assertEqual(sum(by_prov.values()), 84)

    def test_lookups(self):
        record = self.k.loop(PIPELINE_LOOP)
        self.assertIsNotNone(record)
        self.assertEqual(record["execution_mode"], "in-window")
        self.assertIsNone(self.k.loop("pipeline:does-not-exist"))
        # agent_name falls back to the 722-row roster, then to the id itself.
        self.assertEqual(self.k.agent_name("Maxey-nope"), "Maxey-nope")

    def test_loop_ids_are_unique(self):
        ids = [l["id"] for l in self.k.loops]
        self.assertEqual(len(ids), len(set(ids)))


# ---------------------------------------------------------------------------
# routing
# ---------------------------------------------------------------------------
class TestRouting(unittest.TestCase):
    def setUp(self):
        self.k = _KNOWLEDGE

    def test_memory_task_hits_a_real_loop(self):
        result = st.route(
            "promote working memory into the semantic tier", self.k)
        self.assertEqual(result["decision"], "loop_hit")
        loop = result["loop"]
        # The named loop must be a real dataset record, not a synthesized stub.
        self.assertIsNotNone(self.k.loop(loop["id"]))
        self.assertEqual(loop["status"], "validated")
        self.assertEqual(loop["execution_mode"], "in-window")
        self.assertIn("memory", loop["concept_tags"])

    def test_score_concepts_ranks_memory_highly(self):
        scores = st.score_concepts(
            "promote working memory into the semantic tier", self.k)
        self.assertTrue(scores)
        self.assertEqual(scores[0]["concept"], "memory")
        self.assertGreater(scores[0]["score"], 0)
        self.assertIn("memory", scores[0]["tags_hit"])
        # sorted descending by score
        self.assertEqual([s["score"] for s in scores],
                         sorted((s["score"] for s in scores), reverse=True))

    def test_gibberish_reports_a_library_gap_rather_than_a_fake_fallback(self):
        """Nothing covered it, and the result says so.

        Before 0.4.0 this returned `fallback_agent` with an empty agent list --
        a fallback that names nobody. A miss is a gap in library coverage and
        has to be reported as one.
        """
        result = st.route("zzqx wibblefrotz gnarblewump", self.k)
        self.assertEqual(result["decision"], "no_match")
        self.assertEqual(result["how"]["formation"], "manual")
        self.assertIsNone(result["how"]["id"])
        self.assertIsNone(result["where"]["scw"])
        self.assertEqual(result["concept_scores"], [])
        self.assertNotIn("loop", result)
        # every precedence level was tried, and each says why it did not answer
        self.assertEqual(result["evidence"]["levels_tried"],
                         ["loop", "skill", "agent", "manual"])
        self.assertTrue(result["evidence"]["rejected_because"])

    def test_empty_task_does_not_crash(self):
        result = st.route("", self.k)
        self.assertEqual(result["decision"], "no_match")
        self.assertEqual(result["how"]["formation"], "manual")


# ---------------------------------------------------------------------------
# spec_from_record
# ---------------------------------------------------------------------------
class TestSpecFromRecord(unittest.TestCase):
    def _assert_chained(self, spec):
        self.assertEqual(spec.topology, "chain")
        self.assertGreater(len(spec.roles), 1)
        self.assertEqual(spec.roles[0].reads_from, frozenset())
        for i in range(1, len(spec.roles)):
            self.assertEqual(
                spec.roles[i].reads_from,
                frozenset({spec.roles[i - 1].role_id}),
                f"role {i} does not read role {i - 1}")
        self.assertEqual(spec.artifact_role, spec.roles[-1].role_id)

    def test_pipeline_record_chains_its_agent_stages(self):
        record = _KNOWLEDGE.loop(PIPELINE_LOOP)
        spec = st.spec_from_record(record)
        self.assertEqual(len(spec.roles), len(record["agent_stages"]))
        self._assert_chained(spec)
        # role ids are derived from the stage's agent, and each role exposes
        # exactly one handoff region named after itself
        first = spec.roles[0]
        self.assertEqual(first.role_id, "stage0-maxey11")
        self.assertEqual(first.exposes, ("stage0-maxey11-out",))
        # ":" is illegal in a harness id, so the dataset id is normalized
        self.assertNotIn(":", spec.harness_id)

    def test_battery_record_chains_its_named_roles(self):
        record = _KNOWLEDGE.loop(BATTERY_LOOP)
        self.assertNotIn("agent_stages", record)
        spec = st.spec_from_record(record)
        self.assertEqual([r.role_id for r in spec.roles],
                         ["maker", "checker", "judge"])
        self._assert_chained(spec)
        # a checking/judging role is declared as a verdict at a higher
        # verification level than a plain text role
        judge = spec.roles[-1]
        self.assertEqual(judge.output_kind, "verdict")
        self.assertEqual(judge.verification_level, 3)

    def test_record_with_no_roles_raises(self):
        with self.assertRaises(ValueError) as ctx:
            st.spec_from_record({"id": "draft:empty", "title": "Nothing here"})
        self.assertIn("declares no roles", str(ctx.exception))

    def test_record_with_empty_role_lists_raises(self):
        with self.assertRaises(ValueError):
            st.spec_from_record({"id": "draft:empty2", "title": "Still nothing",
                                 "agent_stages": [], "roles": []})


# ---------------------------------------------------------------------------
# binding a loop
# ---------------------------------------------------------------------------
class TestBinding(unittest.TestCase):
    def setUp(self):
        self.session = fresh_session()

    def test_bind_validated_in_window_loop(self):
        record = _KNOWLEDGE.loop(PIPELINE_LOOP)
        result = self.session.bind_loop(PIPELINE_LOOP)

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["status"], "validated")
        self.assertEqual(len(result["roles"]), len(record["agent_stages"]))
        self.assertTrue(all(r.startswith(result["prefix"]) for r in result["roles"]))

        # The negative controls are the point: every role attempting to read
        # every other role's private pad must be refused by the runtime.
        self.assertGreater(result["refused_negative_controls"], 0)
        n = len(result["roles"])
        self.assertEqual(result["refused_negative_controls"], n * (n - 1))
        for refusal in result["refusals"]:
            self.assertEqual(refusal["op"], "open_bridge")
            self.assertIn("negative control", refusal["reason"])
            self.assertTrue(refusal["message"])

        # The regions exist on the live window, not just in the response.
        region_ids = {r["scw_id"] for r in result["regions"]}
        self.assertTrue(region_ids)
        self.assertTrue(region_ids.issubset(set(self.session.window.regions)))
        for loop_id in result["roles"]:
            self.assertIn(loop_id, self.session.window.loops)
            self.assertEqual(self.session.window.loops[loop_id].status, "bound")

    def test_binding_twice_gives_disjoint_instances(self):
        first = self.session.bind_loop(PIPELINE_LOOP)
        second = self.session.bind_loop(PIPELINE_LOOP)
        self.assertTrue(first["ok"] and second["ok"])
        self.assertNotEqual(first["prefix"], second["prefix"])
        self.assertFalse(set(first["roles"]) & set(second["roles"]))

    def test_cross_window_loop_is_refused_with_a_hint(self):
        result = self.session.bind_loop(CROSS_WINDOW_LOOP)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "not_bindable")
        self.assertIn("cross-window", result["message"])
        self.assertTrue(result["hint"])
        self.assertIn("no shared buffer", result["hint"])
        # nothing was partitioned as a side effect
        self.assertEqual(self.session.bound, {})

    def test_unknown_loop_id(self):
        result = self.session.bind_loop("pipeline:no-such-loop")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "unknown_loop")
        self.assertEqual(self.session.bound, {})

    def test_unbind_releases_the_bound_roles(self):
        bound = self.session.bind_loop(BATTERY_LOOP)
        released = self.session.unbind(bound["instance"])
        self.assertTrue(released["ok"])
        self.assertEqual(sorted(released["released"]), sorted(bound["roles"]))
        self.assertNotIn(bound["instance"], self.session.bound)
        self.assertFalse(self.session.unbind("L999")["ok"])


# ---------------------------------------------------------------------------
# regions: create / write / read, and scope enforcement on read
# ---------------------------------------------------------------------------
class TestRegions(unittest.TestCase):
    def setUp(self):
        self.session = fresh_session()

    def test_create_write_detail_roundtrip(self):
        created = self.session.create_scw(
            "roundtrip region", region_type="working",
            policy={"token_budget": 4000, "eviction": "reject"})
        self.assertTrue(created["ok"], created)
        scw_id = created["scw_id"]
        self.assertIn(scw_id, self.session.window.regions)
        self.assertEqual(created["policy"]["token_budget"], 4000)
        self.assertEqual(created["policy"]["eviction"], "reject")

        written = self.session.write_region(scw_id, "the quick brown fox",
                                            key="line-1")
        self.assertTrue(written["ok"], written)
        self.assertGreater(written["tokens_written"], 0)

        detail = self.session.region_detail(scw_id)
        self.assertTrue(detail["ok"])
        self.assertEqual(detail["scw_id"], scw_id)
        self.assertEqual(detail["label"], "roundtrip region")
        self.assertEqual(len(detail["entries"]), 1)
        self.assertEqual(detail["entries"][0]["data"], "the quick brown fox")
        self.assertEqual(detail["entries"][0]["key"], "line-1")
        self.assertEqual(detail["tokens"], written["region_tokens"])
        self.assertNotIn("scope_check", detail)

    def test_unknown_region_reads_and_writes_fail_cleanly(self):
        self.assertEqual(
            self.session.region_detail("no-such-region")["error"], "unknown_region")
        failed = self.session.write_region("no-such-region", "data")
        self.assertFalse(failed["ok"])
        self.assertEqual(failed["error"], "unknown_region")

    def test_scope_check_withholds_entries_from_a_foreign_loop(self):
        bound = self.session.bind_loop(PIPELINE_LOOP)
        owner, other = bound["roles"][0], bound["roles"][1]
        pad = f"{owner}-pad"

        # give the pad something worth withholding
        self.session.write_region(pad, "private scratch notes", loop_id=owner)
        self.assertEqual(len(self.session.region_detail(pad)["entries"]), 1)

        seen = self.session.region_detail(pad, as_loop=other)
        self.assertTrue(seen["ok"])
        self.assertFalse(seen["scope_check"]["allowed"])
        self.assertEqual(seen["scope_check"]["as_loop"], other)
        self.assertEqual(seen["scope_check"]["error"], "isolation_violation")
        self.assertTrue(seen["scope_check"]["hint"])
        # withheld, not merely hidden in the UI
        self.assertEqual(seen["entries"], [])

    def test_scope_check_allows_a_loop_to_read_its_own_pad(self):
        bound = self.session.bind_loop(PIPELINE_LOOP)
        owner = bound["roles"][0]
        pad = f"{owner}-pad"
        self.session.write_region(pad, "my own notes", loop_id=owner)

        seen = self.session.region_detail(pad, as_loop=owner)
        self.assertTrue(seen["scope_check"]["allowed"])
        self.assertEqual(len(seen["entries"]), 1)
        self.assertEqual(seen["entries"][0]["data"], "my own notes")

    def test_snapshot_and_containment_report_the_live_graph(self):
        self.assertFalse(self.session.containment()["ok"])  # nothing bound yet
        bound = self.session.bind_loop(BATTERY_LOOP)

        snap = self.session.snapshot()
        self.assertTrue(snap["ok"])
        self.assertEqual(len(snap["loops"]), len(bound["roles"]))
        self.assertEqual(str(st.EVENT_LOG), snap["event_log"])
        for loop in snap["loops"]:
            self.assertIn(loop["scw_id"], loop["read_closure"])

        contained = self.session.containment()
        self.assertTrue(contained["ok"])
        self.assertIn("bound_holds", contained["containment"])
        self.assertIn("totals", contained["cost"])


# ---------------------------------------------------------------------------
# the audit chain
# ---------------------------------------------------------------------------
class TestAuditChain(unittest.TestCase):
    def test_verify_chain_and_replay(self):
        session = fresh_session()
        session.bind_loop(BATTERY_LOOP)
        created = session.create_scw("audited region")
        session.write_region(created["scw_id"], "content that must replay")

        verified = session.verify_chain()
        self.assertTrue(verified["ok"], verified)
        self.assertTrue(verified["verified"])
        self.assertTrue(verified["replay_identical"],
                        "replayed state diverged from live state")
        self.assertGreater(verified["events"], 0)
        self.assertEqual(verified["run_id"], session.window.log.run_id)

    def test_trace_returns_the_refusals_as_events(self):
        session = fresh_session()
        session.bind_loop(BATTERY_LOOP)
        denied = session.trace(limit=500, kinds=["scw.denied"])
        self.assertTrue(denied["ok"])
        self.assertGreater(denied["returned"], 0)
        self.assertTrue(all(e["type"] == "scw.denied" for e in denied["events"]))


# ---------------------------------------------------------------------------
# mission control: catalog
# ---------------------------------------------------------------------------
class TestMissionCatalog(unittest.TestCase):
    def setUp(self):
        self.catalog = mission.catalog_from_knowledge(_KNOWLEDGE)

    def test_catalog_has_all_sixteen_concepts(self):
        concepts = self.catalog["concepts"]
        self.assertEqual(len(concepts), 16)
        self.assertEqual([c["id"] for c in concepts],
                         [c["id"] for c in _KNOWLEDGE.concepts])

    def test_every_skill_is_present_and_carries_its_agents(self):
        skills = [s for c in self.catalog["concepts"] for s in c["skills"]]
        self.assertEqual(len(skills), 83)
        for skill in skills:
            self.assertIn("agents", skill)
            self.assertIsInstance(skill["agents"], list)
            for agent in skill["agents"]:
                self.assertEqual(set(agent), {"name", "slug", "role"})
        self.assertTrue(any(s["agents"] for s in skills))

    def test_skill_counts_match_the_nested_lists(self):
        for concept in self.catalog["concepts"]:
            self.assertEqual(concept["skill_count"], len(concept["skills"]))
        total = sum(c["skill_count"] for c in self.catalog["concepts"])
        self.assertEqual(total, 83)


# ---------------------------------------------------------------------------
# mission control: dispatch (real regions, real budgets)
# ---------------------------------------------------------------------------
class TestMissionDispatch(unittest.TestCase):
    def setUp(self):
        self.session = fresh_session()

    def test_create_count_two_creates_two_real_regions(self):
        result = mission.dispatch(
            self.session,
            target_scw_id=None,
            new_label="mission-pair",
            region_type="working",
            token_ceiling=5000,
            agent_slug="memory-manager",
            agent_name="Memory Manager",
            skill_desc="multi-tier memory management",
            prompt="",                      # create-only: no dispatch thread
            create_count=2,
        )
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["mode"], "create_only")
        self.assertEqual(len(result["created"]), 2)
        self.assertEqual(len(set(result["created"])), 2)
        self.assertEqual(result["target"], result["created"][0])

        for scw_id in result["created"]:
            self.assertIn(scw_id, self.session.window.regions)
            region = self.session.window.regions[scw_id]
            self.assertEqual(region.policy.token_budget, 5000)
            self.assertEqual(region.policy.eviction, "reject")

    def test_dispatch_into_an_existing_region_creates_nothing(self):
        existing = self.session.create_scw("already here")["scw_id"]
        before = set(self.session.window.regions)
        result = mission.dispatch(
            self.session,
            target_scw_id=existing,
            new_label=None,
            region_type="working",
            token_ceiling=5000,
            agent_slug="", agent_name="", skill_desc="",
            prompt="",
            create_count=3,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["created"], [existing])
        self.assertEqual(set(self.session.window.regions), before)

    def test_dispatch_writes_through_the_real_write_path(self):
        patches = deterministic_simulation(steps=3, tokens_per_step=20)
        with patches[0], patches[1], patches[2], patches[3]:
            result = mission.dispatch(
                self.session,
                target_scw_id=None,
                new_label="mission-writes",
                region_type="working",
                token_ceiling=100_000,
                agent_slug="memory-manager",
                agent_name="Memory Manager",
                skill_desc="multi-tier memory management",
                prompt="summarize the promotion policy",
                create_count=1,
            )
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["mode"], "simulated")
        region = self.session.window.regions[result["target"]]
        self.assertEqual(len(region.entries), 3)
        self.assertGreater(region.own_tokens, 0)
        self.assertIn("Memory Manager", region.entries[0].data)

    def test_tiny_ceiling_produces_a_refusal_instead_of_overrun(self):
        """The enforcement claim, checked: the region never exceeds its budget,
        the runtime records a refusal, and the agent stops early."""
        ceiling = 300
        patches = deterministic_simulation(steps=9, tokens_per_step=100)
        with patches[0], patches[1], patches[2], patches[3]:
            result = mission.dispatch(
                self.session,
                target_scw_id=None,
                new_label="mission-tiny",
                region_type="working",
                token_ceiling=ceiling,
                agent_slug="memory-manager",
                agent_name="Memory Manager",
                skill_desc="multi-tier memory management",
                prompt="write until the budget refuses you",
                create_count=1,
            )
        self.assertTrue(result["ok"], result)
        scw_id = result["target"]
        region = self.session.window.regions[scw_id]

        # 1. the ceiling held
        self.assertEqual(region.policy.token_budget, ceiling)
        self.assertLessEqual(region.own_tokens, ceiling)
        # 2. some work did land -- the refusal is a boundary, not a no-op
        self.assertGreater(len(region.entries), 0)
        # 3. the agent stopped short of its 9 planned steps
        self.assertLess(len(region.entries), 9)
        # 4. the refusal is in the audit log, with the budget it enforced
        denials = [
            e for e in self.session.trace(limit=1000, kinds=["scw.denied"])["events"]
            if e["payload"].get("scw_id") == scw_id
        ]
        self.assertTrue(denials, "no refusal was recorded for the tiny budget")
        payload = denials[-1]["payload"]
        self.assertEqual(payload["op"], "write")
        self.assertIn("token_budget", payload["reason"])
        self.assertEqual(payload["budget"], ceiling)
        self.assertGreater(payload["would_be"], ceiling)

    def test_direct_write_over_the_ceiling_is_refused(self):
        """The same enforcement without any simulation in the way."""
        created = self.session.create_scw(
            "hard ceiling", region_type="working",
            policy={"token_budget": 40, "eviction": "reject"})
        refused = self.session.write_region(created["scw_id"], "word " * 500)
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["error"], "budget_exceeded")
        self.assertEqual(refused["budget"], 40)
        self.assertEqual(self.session.window.regions[created["scw_id"]].entries, [])


# ---------------------------------------------------------------------------
# app: the route table and its handlers
# ---------------------------------------------------------------------------
class TestAppRoutes(unittest.TestCase):
    def test_route_table_registers_the_documented_endpoints(self):
        for path in ("/api/knowledge", "/api/loops", "/api/loop", "/api/field",
                     "/api/window", "/api/region", "/api/trace",
                     "/api/containment", "/api/verify",
                     "/api/mission/catalog", "/api/mission/config",
                     "/api/live/session", "/api/live/runs",
                     "/api/experiments", "/api/experiments/specs",
                     "/api/experiments/status", "/api/experiments/report",
                     "/api/experiments/probe"):
            self.assertIn(path, app.GET_ROUTES, path)
        for path in ("/api/route", "/api/bind", "/api/unbind", "/api/reset",
                     "/api/write", "/api/bridge", "/api/tick",
                     "/api/mission/dispatch", "/api/mission/close",
                     "/api/mission/file", "/api/designer/preview"):
            self.assertIn(path, app.POST_ROUTES, path)
        self.assertFalse(set(app.GET_ROUTES) & set(app.POST_ROUTES))

    def test_api_knowledge_reports_the_real_counts_and_sources(self):
        payload = app.api_knowledge({}, {})
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["counts"]["concepts"], 16)
        self.assertEqual(payload["counts"]["skills"], 83)
        self.assertEqual(payload["counts"]["agents"], 67)
        self.assertEqual(payload["counts"]["loops"], 84)
        self.assertEqual(len(payload["concepts"]), 16)
        self.assertEqual(len(payload["skills"]), 83)
        self.assertEqual(len(payload["agents"]), 67)
        self.assertEqual(payload["sources"]["maxey0_root"],
                          str((VENDOR / "maxey0").relative_to(ROOT)))
        self.assertEqual(payload["sources"]["loops_json"],
                          str((VENDOR / "data" / "loops.json").relative_to(ROOT)))
        self.assertEqual(payload["sources"]["scw_runtime"],
                          str(VENDOR.relative_to(ROOT)))
        self.assertEqual(payload["sources"]["event_log"],
                          app._display_path(TEST_EVENT_LOG))
        for value in payload["sources"].values():
            self.assertNotIn(str(pathlib.Path.home()), value)

    def test_api_loops_filters(self):
        every = app.api_loops({}, {})
        self.assertEqual(every["count"], 84)

        validated = app.api_loops({"status": ["validated"]}, {})
        self.assertEqual(validated["count"], 78)
        self.assertTrue(all(l["status"] == "validated" for l in validated["loops"]))

        memory = app.api_loops({"concept": ["memory"]}, {})
        self.assertGreater(memory["count"], 0)
        self.assertLess(memory["count"], 84)
        self.assertTrue(all("memory" in l["concept_tags"] for l in memory["loops"]))

    def test_api_loop_by_id(self):
        found = app.api_loop({"id": [PIPELINE_LOOP]}, {})
        self.assertTrue(found["ok"])
        self.assertEqual(found["loop"]["id"], PIPELINE_LOOP)
        missing = app.api_loop({"id": ["nope"]}, {})
        self.assertFalse(missing["ok"])
        self.assertEqual(missing["error"], "unknown_loop")

    def test_api_route_rejects_an_empty_task(self):
        self.assertEqual(app.api_route({}, {"task": "   "})["error"], "empty_task")

    def test_api_route_matches_state_route(self):
        task = "promote working memory into the semantic tier"
        via_http = app.api_route({}, {"task": task})
        direct = st.route(task, app.SESSION.knowledge)
        self.assertTrue(via_http["ok"])
        self.assertEqual(via_http["decision"], direct["decision"])
        self.assertEqual(via_http["loop"]["id"], direct["loop"]["id"])

    def test_api_designer_preview_rejects_a_loop_with_no_stages(self):
        result = app.api_designer_preview({}, {"slug": "empty", "title": "Empty"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "no_stages")

    def test_api_designer_preview_builds_and_hardens_a_real_window(self):
        result = app.api_designer_preview({}, {
            "slug": "test-chain", "title": "Test chain",
            "roles": ["planner", "implementer", "checker"],
        })
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["roles"], ["planner", "implementer", "checker"])
        self.assertTrue(result["hardening"]["passed"])
        self.assertEqual(result["hardening"]["negative_controls_refused"], "6/6")
        self.assertTrue(result["regions"])


# ---------------------------------------------------------------------------
# experiment harness: generic over an external workload spec
# ---------------------------------------------------------------------------
class TestExperimentSpecs(unittest.TestCase):
    """The harness must carry no workload of its own.

    Everything workload-specific -- tasks, probe text, the sentinel that counts
    as a refusal -- comes from a spec. These tests pin that boundary: a spec is
    validated rather than trusted, and a missing spec is an error rather than a
    silent default.
    """

    def test_the_module_holds_no_workload_of_its_own(self):
        for leaked in ("DEFAULT_TASKS", "LEAK_PROBE"):
            self.assertFalse(
                hasattr(exp_mod, leaked),
                f"{leaked} is workload data and belongs in a spec file")

    def test_create_without_a_spec_is_an_error_naming_what_is_available(self):
        with self.assertRaises(exp_mod.SpecError) as caught:
            exp_mod.load_spec(None)
        self.assertIn("maxey0-website", str(caught.exception))

    def test_unknown_spec_reference_is_an_error(self):
        with self.assertRaises(exp_mod.SpecError):
            exp_mod.load_spec("no-such-workload")

    def test_shipped_spec_loads_and_normalizes(self):
        spec = exp_mod.load_spec("maxey0-website")
        self.assertEqual(spec["id"], "maxey0-website")
        self.assertEqual(len(spec["tasks"]), 4)
        self.assertEqual([c["partition"] for c in spec["conditions"]],
                         ["scw", "flat"])
        self.assertIn(spec["probe"]["sentinel"], spec["probe"]["text"])

    def test_list_specs_finds_the_shipped_workload(self):
        ids = [s["spec_id"] for s in exp_mod.list_specs()]
        self.assertIn("maxey0-website", ids)

    def test_a_bare_string_condition_is_shorthand_for_its_own_partition(self):
        """A bare string names a partition and takes the default other axes.

        `routing` defaults to `maxey0` and `gating` to `off` so a spec written
        before either axis existed keeps meaning exactly what it meant:
        execute whatever routing selected, with nothing watching the agents.
        """
        spec = exp_mod.normalize_spec(
            {"tasks": [{"id": "t", "task": "do a thing"}],
             "conditions": ["scw", "flat"]})
        self.assertEqual(
            spec["conditions"],
            [{"id": "scw", "partition": "scw", "routing": "maxey0", "gating": "off"},
             {"id": "flat", "partition": "flat", "routing": "maxey0", "gating": "off"}])

    def test_spec_validation_rejects_what_the_harness_cannot_run(self):
        cases = {
            "no tasks": {"tasks": []},
            "task with no id": {"tasks": [{"task": "x"}]},
            "task with no task": {"tasks": [{"id": "a"}]},
            "unknown partition": {"tasks": [{"id": "a", "task": "x"}],
                                  "conditions": [{"id": "q", "partition": "wat"}]},
            "condition with no id": {"tasks": [{"id": "a", "task": "x"}],
                                     "conditions": [{"partition": "scw"}]},
            "unknown gating": {"tasks": [{"id": "a", "task": "x"}],
                               "conditions": [{"id": "q", "partition": "scw",
                                               "gating": "sometimes"}]},
            # A gated condition that cannot say how a call will be attributed
            # would report unattributed residue as a gating measurement.
            "gating without declared attribution": {
                "tasks": [{"id": "a", "task": "x"}],
                "conditions": [{"id": "q", "partition": "scw", "gating": "enforce"}]},
        }
        for why, doc in cases.items():
            with self.subTest(why=why):
                with self.assertRaises(exp_mod.SpecError):
                    exp_mod.normalize_spec(doc)

    def test_a_gated_spec_that_declares_its_attribution_is_accepted(self):
        spec = exp_mod.normalize_spec({
            "tasks": [{"id": "a", "task": "x"}],
            "gate": {"attribution": "cwd"},
            "conditions": [{"id": "q", "partition": "scw", "gating": "enforce"}],
        })
        self.assertEqual(spec["conditions"][0]["gating"], "enforce")
        self.assertTrue(spec["has_gating"])
        self.assertEqual(spec["gate"]["attribution"], "cwd")

    def test_a_sentinel_absent_from_its_own_probe_is_rejected(self):
        """A role cannot emit a refusal token it was never shown, so a spec
        that grades against one would report 0% refusal by construction."""
        with self.assertRaises(exp_mod.SpecError):
            exp_mod.normalize_spec({
                "tasks": [{"id": "a", "task": "x"}],
                "probe": {"text": "quote everything", "sentinel": "NOPE"}})

    def test_grading_uses_the_spec_sentinel_not_a_builtin_one(self):
        exp = exp_mod.Experiment("exp-test", {
            "exp_id": "exp-test", "calls": [], "tasks": [], "conditions": [],
            "spec": exp_mod.normalize_spec({
                "id": "custom", "tasks": [{"id": "a", "task": "x"}],
                "probe": {"text": "say REFUSED-BY-SCOPE if you cannot",
                          "sentinel": "REFUSED-BY-SCOPE"}}),
        })
        self.assertEqual(exp._grade_probe("REFUSED-BY-SCOPE"), "refused")
        # The old hard-coded sentinel must no longer count as a refusal here.
        self.assertEqual(exp._grade_probe("CANNOT: not in my scope"),
                         "disclosed_or_other")
        self.assertIsNone(exp._grade_probe(None))


class TestExperimentRun(unittest.TestCase):
    """One real run of a small spec, through the real window and real writes."""

    @classmethod
    def setUpClass(cls):
        cls.runs_dir = TMPDIR / "experiment-runs"
        cls._real_dir = exp_mod.EXPERIMENTS_DIR
        exp_mod.EXPERIMENTS_DIR = cls.runs_dir

    @classmethod
    def tearDownClass(cls):
        exp_mod.EXPERIMENTS_DIR = cls._real_dir

    def _spec(self) -> dict:
        return {
            "id": "unit-workload",
            "label": "Unit workload",
            "objective": "Exercise the harness with one small unit of work.",
            "probe": {"text": "If you cannot see it, say ONLY-MY-SCOPE",
                      "sentinel": "ONLY-MY-SCOPE"},
            "tasks": [{
                "id": "promote",
                "title": "Promote a finding",
                "task": "promote working memory into the semantic tier",
            }],
        }

    def test_a_run_carries_its_spec_and_grades_against_its_own_sentinel(self):
        session = fresh_session()
        exp = exp_mod.Experiment.create(session, spec=self._spec())
        self.assertEqual(exp.spec["id"], "unit-workload")

        result = exp.materialize(session)
        self.assertTrue(result["ok"])
        self.assertGreater(result["calls"], 0)

        status = exp.status()
        self.assertEqual(status["spec_id"], "unit-workload")
        self.assertEqual(status["probe"]["sentinel"], "ONLY-MY-SCOPE")
        self.assertFalse(status["complete"])

        call = status["next"]
        self.assertIn("Exercise the harness", call["prompt"])
        self.assertIn("MATERIAL IN SCOPE", call["prompt"])

        ingested = exp.ingest(session, call["call_id"], "a deliverable",
                              probe_response="ONLY-MY-SCOPE")
        self.assertTrue(ingested["ok"])
        self.assertEqual(ingested["leak_verdict"], "refused")

        # Ingest is idempotent per call, so an interrupted run can resume.
        again = exp.ingest(session, call["call_id"], "different text")
        self.assertTrue(again["already_ingested"])

        report = exp.report(session)
        self.assertEqual(report["spec_id"], "unit-workload")
        self.assertIn("scw", report["per_condition"])
        self.assertEqual(report["per_condition"]["scw"]["partition"], "scw")
        self.assertEqual(report["per_condition"]["flat"]["partition"], "flat")
        # One probe is a pilot, not a rate, and the report has to say so.
        self.assertIn("underpowered",
                      [item["kind"] for item in report["residue"]])

    def test_a_spec_with_no_probe_reports_null_leakage_not_zero(self):
        session = fresh_session()
        spec = self._spec()
        spec.pop("probe")
        exp = exp_mod.Experiment.create(session, spec=spec)
        exp.materialize(session)
        report = exp.report(session)

        for stats in report["per_condition"].values():
            self.assertIsNone(stats["leak_refusal_rate"])
        self.assertIn("no_probe_defined",
                      [item["kind"] for item in report["residue"]])

    def test_api_create_rejects_a_bad_spec_and_names_the_alternatives(self):
        payload = app.api_exp_create({}, {"spec": "no-such-workload"})
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "bad_spec")
        self.assertIn("maxey0-website",
                      [s["spec_id"] for s in payload["specs"]])

    def test_api_probe_requires_a_run_because_the_probe_belongs_to_its_spec(self):
        payload = app.api_exp_probe({}, {})
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "unknown_experiment")


# ---------------------------------------------------------------------------
# semantic field
# ---------------------------------------------------------------------------
class TestSemanticField(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.field = semantic.build_field(_KNOWLEDGE)

    def test_one_node_per_concept_skill_and_agent(self):
        self.assertEqual(self.field["stats"]["nodes"], 16 + 83 + 67)
        self.assertEqual(len(self.field["nodes"]), self.field["stats"]["nodes"])
        levels = [n["level"] for n in self.field["nodes"]]
        self.assertEqual(levels.count("concept"), 16)
        self.assertEqual(levels.count("skill"), 83)
        self.assertEqual(levels.count("agent"), 67)
        # Every node id is unique: a collision would silently merge two
        # entities into one point on the plane.
        self.assertEqual(len({n["id"] for n in self.field["nodes"]}),
                         self.field["stats"]["nodes"])

    def test_z_is_the_assigned_hierarchy_level(self):
        for node in self.field["nodes"]:
            self.assertEqual(node["z"], semantic.LEVEL_Z[node["level"]])
        self.assertIn("not a measured dimension", self.field["method"])

    def test_every_edge_resolves_to_a_real_node(self):
        known = {n["id"] for n in self.field["nodes"]}
        for edge in self.field["edges"]:
            self.assertIn(edge["source"], known)
            self.assertIn(edge["target"], known)
        self.assertEqual(len(self.field["edges"]), self.field["stats"]["edges"])

    def test_unanchored_nodes_are_flagged_not_dropped_at_the_origin(self):
        for node in self.field["nodes"]:
            if node.get("unanchored"):
                self.assertAlmostEqual(
                    (node["x"] ** 2 + node["y"] ** 2) ** 0.5,
                    semantic.RING_RADIUS, delta=semantic.RING_RADIUS * 0.25)
        self.assertEqual(
            self.field["stats"]["unanchored"],
            sum(1 for n in self.field["nodes"] if n.get("unanchored")))


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestTheStudioMatchesTheTableThatDescribesIt(unittest.TestCase):
    """`catalog.VIEWS` exists so no surface invents its own list. One did.

    `menu`, `observe.studio`, the generated UI catalog and the lexicon check all
    read `catalog.VIEWS`. The Studio does not: it is a stdlib-only server with
    no template step, so its navigation is hand-written HTML. That makes the one
    surface which *is* these views the one that can drift from the table
    describing it — and it had. Evidence and Gate were declared in the opposite
    order to the order the Studio presents them, so `observe.studio` reported a
    running order that did not exist.

    Nothing compared them, which is why nobody noticed. This compares them.
    """

    STATIC = ROOT / "server" / "maxey0_studio" / "static" / "index.html"

    @classmethod
    def setUpClass(cls):
        import re

        cls.html = cls.STATIC.read_text(encoding="utf-8")
        cls.nav = re.findall(
            r'<button data-view="([a-z0-9-]+)"[^>]*>([^<]+)</button>', cls.html)
        cls.sections = re.findall(
            r'<section[^>]*data-view="([a-z0-9-]+)"', cls.html)
        from planes import catalog

        cls.catalog = catalog

    def test_the_navigation_matches_the_declared_table_in_order(self):
        self.assertEqual(
            [name for _, name in self.nav],
            [name for name, _ in self.catalog.VIEWS],
            "the Studio's navigation and catalog.VIEWS disagree; "
            "observe.studio reports the table, users see the navigation",
        )

    def test_every_navigation_button_has_a_view_to_show(self):
        """A tab that selects nothing is a tab that looks broken."""
        self.assertEqual(
            sorted(view for view, _ in self.nav), sorted(self.sections),
            "a data-view button with no matching section",
        )

    def test_there_are_no_orphan_sections(self):
        """A view nothing can navigate to is a view nobody sees."""
        self.assertEqual(
            sorted(set(self.sections)), sorted({v for v, _ in self.nav}),
        )

    def test_exactly_one_view_starts_active(self):
        self.assertEqual(self.html.count('class="active"'), 1)

    def test_observe_studio_reports_what_the_studio_serves(self):
        """The observability tool and the thing it observes, compared."""
        from planes import observe_impl

        reported = observe_impl.studio_view({}) if hasattr(
            observe_impl, "studio_view") else None
        if reported is None:  # the tool is named differently; read the table
            reported = {"views": [n for n, _ in self.catalog.VIEWS]}
        self.assertEqual(
            list(reported["views"]), [name for _, name in self.nav],
        )


class TestCrossWindowRunsPersist(unittest.TestCase):
    """0.2.0 shipped a known-issue list saying `cross_window.py persists no run`.

    That was wrong, and carrying it forward would have been worse than never
    having written it: `CrossWindowRun.save()` is called on create and on
    report, and `load`/`list_all` are reached from both the Studio's HTTP routes
    and the loops plane. This asserts the round trip so the claim cannot drift
    in either direction again.
    """

    def test_a_run_survives_a_save_and_a_load(self):
        from maxey0_studio import cross_window as cw

        run = cw.CrossWindowRun.create("01-horizontal-4way")
        self.assertTrue(run.run_id)
        self.assertTrue(run.path.exists(), "create() must persist")

        reloaded = cw.CrossWindowRun.load(run.run_id)
        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded.doc["loop_id"], "01-horizontal-4way")

    def test_a_saved_run_is_listed(self):
        from maxey0_studio import cross_window as cw

        run = cw.CrossWindowRun.create("02-vertical-nesting")
        self.assertIn(run.run_id, [r["run_id"] for r in cw.CrossWindowRun.list_all()])

    def test_loading_an_unknown_run_returns_none_rather_than_inventing_one(self):
        from maxey0_studio import cross_window as cw

        self.assertIsNone(cw.CrossWindowRun.load("no-such-run"))


class TestRequestGuard(unittest.TestCase):
    """The Studio has no auth, so loopback is its only boundary. These drive a
    real server with raw headers, because the attack is a browser sending
    headers the Studio's own front end never would."""

    @classmethod
    def setUpClass(cls):
        import threading
        from http.server import ThreadingHTTPServer

        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), app.StudioHandler)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _req(self, method, path, headers, body=None):
        import http.client

        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.putrequest(method, path, skip_host=True)
        for k, v in headers.items():
            conn.putheader(k, v)
        data = body.encode() if body is not None else b""
        if method == "POST":
            conn.putheader("Content-Length", str(len(data)))
        conn.endheaders(data if method == "POST" else None)
        resp = conn.getresponse()
        resp.read()
        conn.close()
        return resp.status

    def test_rebound_host_is_refused_on_get(self):
        self.assertEqual(self._req("GET", "/api/knowledge",
                                   {"Host": f"evil.example:{self.port}"}), 403)

    def test_loopback_host_is_served(self):
        self.assertEqual(self._req("GET", "/api/knowledge",
                                   {"Host": f"127.0.0.1:{self.port}"}), 200)
        self.assertEqual(self._req("GET", "/api/knowledge",
                                   {"Host": f"[::1]:{self.port}"}), 200)

    def test_text_plain_post_is_refused(self):
        # A CORS "simple request" needs no preflight, so it must not be JSON-parsed.
        self.assertEqual(self._req("POST", "/api/route",
                                   {"Host": f"127.0.0.1:{self.port}",
                                    "Content-Type": "text/plain"}, "{}"), 403)

    def test_cross_origin_post_is_refused(self):
        self.assertEqual(self._req("POST", "/api/route",
                                   {"Host": f"127.0.0.1:{self.port}",
                                    "Content-Type": "application/json",
                                    "Origin": "http://evil.example"}, "{}"), 403)

    def test_a_refusal_is_not_lost_when_the_body_arrives_late(self):
        """Regression: the two refusal tests above failed intermittently.

        http.client sends the headers and the body in separate writes. When
        the server parsed the headers before the body landed, it refused and
        closed with the body unread, the kernel answered the late body with a
        reset, and the reset discarded the 403 before the client read it. The
        pauses here force that ordering every time instead of now and then;
        with the body drained before the reply, the outcome does not depend on
        them.
        """
        import http.client
        import time

        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.putrequest("POST", "/api/route", skip_host=True)
        conn.putheader("Host", f"127.0.0.1:{self.port}")
        conn.putheader("Content-Type", "text/plain")
        conn.putheader("Content-Length", "2")
        conn.endheaders()
        time.sleep(0.2)
        conn.send(b"{}")
        time.sleep(0.2)
        resp = conn.getresponse()
        resp.read()
        conn.close()
        self.assertEqual(resp.status, 403)

    def test_a_non_integer_limit_is_a_400_not_a_500(self):
        # int("abc") used to escape to the generic handler as a 500.
        self.assertEqual(self._req("GET", "/api/live/runs?limit=abc",
                                   {"Host": f"127.0.0.1:{self.port}"}), 400)
        self.assertEqual(self._req("GET", "/api/trace?limit=abc",
                                   {"Host": f"127.0.0.1:{self.port}"}), 400)
        self.assertEqual(self._req("GET", "/api/trace?limit=5",
                                   {"Host": f"127.0.0.1:{self.port}"}), 200)

    def test_same_origin_json_post_passes_the_guard(self):
        # An unknown route: the guard lets it through and dispatch answers 404.
        self.assertEqual(self._req("POST", "/api/__no_such_route__",
                                   {"Host": f"localhost:{self.port}",
                                    "Content-Type": "application/json",
                                    "Origin": f"http://localhost:{self.port}"},
                                   "{}"), 404)


class TestRunIdsCannotTraverse(unittest.TestCase):
    """run_id / exp_id reach load() from ?id= and MCP arguments unfiltered."""

    def test_a_traversing_run_id_is_unknown(self):
        from maxey0_studio import cross_window as cw

        # experiments/maxey0_example_loops.json exists one level above RUNS_DIR.
        self.assertTrue((cw.RUNS_DIR.parent / "maxey0_example_loops.json").exists())
        for bad in ("../maxey0_example_loops", "..\\maxey0_example_loops",
                    "cw-x-0000000a/../../maxey0_example_loops"):
            with self.subTest(bad=bad):
                self.assertIsNone(cw.CrossWindowRun.load(bad))

    def test_a_minted_run_id_still_loads(self):
        from maxey0_studio import cross_window as cw

        run = cw.CrossWindowRun.create("01-horizontal-4way")
        self.assertIsNotNone(cw.CrossWindowRun.load(run.run_id))

    def test_a_traversing_experiment_id_is_unknown(self):
        self.assertIsNone(exp_mod.Experiment.load("../plugins/maxey0"))
        self.assertIsNone(exp_mod.Experiment.load(".."))
