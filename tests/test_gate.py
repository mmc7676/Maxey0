"""One test per property the gate is supposed to protect.

Named after the properties, not the functions, so a regression tells you what
broke rather than where. The properties, in the order they appear below:

    the gate never grants          returning `allow` would skip the user's own
                                   permission prompt, so a component installed
                                   to restrict an agent would end up widening it
    attribution never guesses      an ambiguous actor stays unresolved rather
                                   than being assigned a plausible role
    ambient is not residue         a subagent in a session that dispatched no
                                   role is ordinary activity, not a hole in
                                   some containment claim
    residue disqualifies a claim   any fail-open, lost record or unattributed
                                   call makes containment un-claimable
    observe blocks nothing         and produces the same finding enforce would
    the host is never refused      the orchestrator builds the partition
    the chain survives concurrency the failure mode that destroys the runtime
                                   log when two processes share a file
    a torn line is counted         not silently dropped, and not fatal
    a gate crash never blocks      but is recorded as a fail-open
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from gate import attribution, journal, store  # noqa: E402
from gate.core import classify, decide, resource_of  # noqa: E402
from gate.protocol import Policy, ToolEvent  # noqa: E402


def event(tool: str, phase: str = "pre", actor_ref: str = "a1", **inp) -> ToolEvent:
    return ToolEvent(phase=phase, tool=tool, tool_input=inp, host="test",
                     session_ref="s1", actor_ref=actor_ref, actor_kind="role",
                     cwd=os.getcwd())


class GateEnvIsolated(unittest.TestCase):
    """Restores the process environment after every test.

    The tests below point the gate at a throwaway directory by assigning
    MAXEY0_GATE_STATE, MAXEY0_GATE_LOG and MAXEY0_GATE_MODE directly, because
    `state_dir()` and `journal_path()` read them on every call. Unrestored,
    those values outlived the test and the temporary directory they named.
    Every later test in the process, in any module, then resolved gate state
    and the gate journal to a deleted directory (and `decide()` recreated it,
    since it resolves both paths), so what a test saw depended on which test
    happened to run before it. A snapshot per test is restored even when the
    test fails partway, which a trailing `del` never was.
    """

    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)


class GateNeverGrants(GateEnvIsolated):
    """The gate is a restrictor. It must never widen what the host allowed."""

    def test_in_scope_call_is_not_an_allow_decision_to_the_host(self):
        from gate.adapters import claude_code as cc
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["MAXEY0_GATE_STATE"] = tmp
            os.environ["MAXEY0_GATE_LOG"] = str(Path(tmp) / "g.jsonl")
            store.declare("s1", Policy(loop_id="r", read_paths=(tmp + "/**",),
                                       tools=("Read",)))
            attribution.bind_actor("s1", "a1", "r", "test")
            out = cc.run({
                "hook_event_name": "PreToolUse", "tool_name": "Read",
                "session_id": "s1", "agent_id": "a1", "agent_type": "role",
                "cwd": tmp, "tool_input": {"file_path": str(Path(tmp) / "x.md")},
            })
        # Silence, not {"permissionDecision": "allow"} -- an allow would bypass
        # the user's own permission rules.
        self.assertEqual(out, {})

    def test_out_of_scope_call_denies_and_carries_the_reason(self):
        from gate.adapters import claude_code as cc
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["MAXEY0_GATE_STATE"] = tmp
            os.environ["MAXEY0_GATE_LOG"] = str(Path(tmp) / "g.jsonl")
            os.environ["MAXEY0_GATE_MODE"] = "enforce"
            store.declare("s1", Policy(loop_id="r", read_paths=(tmp + "/**",),
                                       tools=("Read",)))
            attribution.bind_actor("s1", "a1", "r", "test")
            out = cc.run({
                "hook_event_name": "PreToolUse", "tool_name": "Read",
                "session_id": "s1", "agent_id": "a1", "agent_type": "role",
                "cwd": tmp, "tool_input": {"file_path": "/etc/shadow"},
            })
        hook = out["hookSpecificOutput"]
        self.assertEqual(hook["permissionDecision"], "deny")
        self.assertIn("outside", hook["permissionDecisionReason"])


class TheGateEnvironmentDoesNotLeak(unittest.TestCase):
    """Regression: gate tests left MAXEY0_GATE_* naming deleted directories."""

    def test_a_test_that_points_the_gate_elsewhere_restores_it(self):
        keys = ("MAXEY0_GATE_STATE", "MAXEY0_GATE_LOG", "MAXEY0_GATE_MODE")
        before = {key: os.environ.get(key) for key in keys}
        # This one assigns all three; run it as a nested case so its cleanup
        # has finished by the time the environment is compared.
        case = GateNeverGrants("test_out_of_scope_call_denies_and_carries_the_reason")
        result = unittest.TestResult()
        case.run(result)
        self.assertTrue(result.wasSuccessful(), result.failures + result.errors)
        self.assertEqual({key: os.environ.get(key) for key in keys}, before)


class ADeclarationMadeBeforeTheSessionExistsStillApplies(GateEnvIsolated):
    """Regression: a gate configured to enforce silently enforced nothing.

    A session id is minted by the host when the session starts, so an operator
    configuring the gate beforehand necessarily writes the no-session file. The
    hook then looked up the REAL session id, found nothing, and ran in
    `observe` with `no_policy` — so out-of-scope reads sailed through while the
    journal recorded them as observed. Observed live: four subagent reads,
    every one `reason_code: no_policy`, `mode: observe`, none refused.
    """

    def test_a_policy_declared_with_no_session_governs_a_real_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["MAXEY0_GATE_STATE"] = tmp
            os.environ.pop("MAXEY0_GATE_POLICY", None)
            store.declare(None, Policy(loop_id="maker", read_paths=("/ok/**",),
                                       tools=("Read",)))
            found = store.get("a-real-session-id-minted-later", "maker")
        self.assertIsNotNone(found)
        self.assertEqual(found.read_paths, ("/ok/**",))

    def test_a_mode_declared_with_no_session_governs_a_real_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["MAXEY0_GATE_STATE"] = tmp
            os.environ.pop("MAXEY0_GATE_MODE", None)
            store.set_mode(None, "enforce")
            mode = store.get_mode("a-real-session-id-minted-later")
        self.assertEqual(mode, "enforce")

    def test_a_session_specific_declaration_still_wins(self):
        """The default must never widen a role that declared its own scope."""
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["MAXEY0_GATE_STATE"] = tmp
            os.environ.pop("MAXEY0_GATE_POLICY", None)
            store.declare(None, Policy(loop_id="maker", read_paths=("/wide/**",)))
            store.declare("s9", Policy(loop_id="maker", read_paths=("/narrow/**",)))
            found = store.get("s9", "maker")
        self.assertEqual(found.read_paths, ("/narrow/**",))


class AttributionNeverGuesses(GateEnvIsolated):

    def test_an_unresolvable_actor_is_never_given_a_role(self):
        """It resolves to nothing. Which *kind* of nothing depends on whether a
        role was ever dispatched -- see AmbientActivityIsNotResidue."""
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["MAXEY0_GATE_STATE"] = tmp
            loop_id, how = attribution.resolve("s-none", "ghost", None, None, None)
        self.assertIsNone(loop_id)
        self.assertIn(how, ("ambient", "unattributed"))

    def test_two_pending_roles_of_one_actor_kind_stay_ambiguous(self):
        """Guessing here would attribute one role's behavior to another."""
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["MAXEY0_GATE_STATE"] = tmp
            attribution.declare_dispatch("s2", "maker", actor_kind="general-purpose")
            attribution.declare_dispatch("s2", "checker", actor_kind="general-purpose")
            loop_id, how = attribution.resolve("s2", "aX", "general-purpose", None, None)
        self.assertIsNone(loop_id)
        self.assertEqual(how, "ambiguous_actor_kind")

    def test_marker_in_the_actors_transcript_resolves_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["MAXEY0_GATE_STATE"] = tmp
            session = Path(tmp) / "sess.jsonl"
            session.write_text("{}\n", encoding="utf-8")
            sub = Path(tmp) / "sess" / "subagents"
            sub.mkdir(parents=True)
            (sub / "agent-aZ.jsonl").write_text(
                json.dumps({"message": {"content": "[[scw:role=judge]] do the thing"}}),
                encoding="utf-8")
            loop_id, how = attribution.resolve("s3", "aZ", None, str(session), None)
        self.assertEqual(loop_id, "judge")
        self.assertEqual(how, "transcript_marker")

    def test_unattributed_calls_are_never_denied(self):
        """Refusing on a guess would be worse than the hole it closes."""
        decision = decide(event("Read", file_path="/etc/shadow"), None,
                          mode="enforce", attributed=False)
        self.assertFalse(decision.blocks)
        self.assertEqual(decision.reason_code, "unattributed")

    def test_a_per_role_working_directory_attributes_portably(self):
        """The only mechanism every surveyed host can support.

        `cwd` is the sole identity-bearing field present in every host's
        pre-tool payload, and unlike the transcript resolver it answers before
        the call rather than after it.
        """
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["MAXEY0_GATE_STATE"] = tmp
            maker = Path(tmp) / "work" / "maker"
            maker.mkdir(parents=True)
            attribution.declare_dispatch("s4", "maker", workdir=str(maker))
            # a call from inside the role's own tree, from an actor we have
            # never seen and whose type tells us nothing
            loop_id, how = attribution.resolve(
                "s4", "unknown-actor", None, None, None, str(maker / "deep" / "sub"))
        self.assertEqual(loop_id, "maker")
        self.assertEqual(how, "cwd")

    def test_a_nested_role_directory_resolves_to_the_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["MAXEY0_GATE_STATE"] = tmp
            parent = Path(tmp) / "w"
            child = parent / "checker"
            child.mkdir(parents=True)
            attribution.declare_dispatch("s5", "parent", workdir=str(parent))
            attribution.declare_dispatch("s5", "checker", workdir=str(child))
            loop_id, _ = attribution.resolve("s5", "a9", None, None, None, str(child))
        self.assertEqual(loop_id, "checker")


class ResidueDisqualifiesAClaim(unittest.TestCase):

    def _containment(self, records, damaged=0):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
        from maxey0_studio import gate_view
        return gate_view.containment(records, damaged=damaged)

    def _rec(self, kind, **payload):
        return {"type": kind, "seq": 0, "payload": {"attributed": True, **payload}}

    def test_clean_run_is_claimable(self):
        out = self._containment([
            self._rec("gate.allowed", mode="enforce"),
            self._rec("gate.denied", mode="enforce"),
        ])
        self.assertTrue(out["claimable"])
        self.assertTrue(out["held"])

    def test_a_single_fail_open_makes_it_unclaimable(self):
        out = self._containment([
            self._rec("gate.allowed", mode="enforce"),
            self._rec("gate.fail_open", mode="enforce"),
        ])
        self.assertFalse(out["claimable"])
        self.assertEqual(out["residue"]["fail_open"], 1)

    def test_a_lost_record_makes_it_unclaimable(self):
        out = self._containment([self._rec("gate.allowed", mode="enforce")],
                                damaged=1)
        self.assertFalse(out["claimable"])
        self.assertEqual(out["residue"]["damaged_records"], 1)

    def test_nothing_evaluated_is_null_not_true(self):
        """An absence of evidence is never reported as evidence."""
        out = self._containment([])
        self.assertIsNone(out["held"])
        self.assertFalse(out["claimable"])
        self.assertIn("absence of evidence", out["note"])

    def test_the_hosts_own_calls_are_not_residue(self):
        """Regression: they made every clean run report `claimable: false`.

        The orchestrator is not an unattributed role -- it is the thing that
        builds the partition, and no policy was ever meant to govern it. Every
        real run contains its dispatch and tooling calls, so counting them as
        residue meant containment could never be claimable in practice.
        `gate.levels.assess` already excluded them; the two must agree.
        """
        records = [
            {"type": "gate.observed", "seq": 0,
             "payload": {"attributed": False, "reason_code": "host_actor",
                         "mode": "enforce", "tool": "Agent"}},
            {"type": "gate.allowed", "seq": 1,
             "payload": {"attributed": True, "loop_id": "maker",
                         "reason_code": "in_scope", "mode": "enforce"}},
            {"type": "gate.denied", "seq": 2,
             "payload": {"attributed": True, "loop_id": "maker",
                         "reason_code": "path_outside_scope", "mode": "enforce"}},
        ]
        out = self._containment(records)
        self.assertEqual(out["residue"]["unattributed"], 0)
        self.assertTrue(out["claimable"])
        self.assertTrue(out["held"])

    def test_the_host_and_an_unattributed_actor_are_reported_separately(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
        from maxey0_studio import gate_view
        records = [
            {"type": "gate.observed", "seq": 0,
             "payload": {"attributed": False, "reason_code": "host_actor",
                         "tool": "Agent"}},
            {"type": "gate.observed", "seq": 1,
             "payload": {"attributed": False, "reason_code": "unattributed",
                         "tool": "Read"}},
        ]
        out = gate_view.by_role(records)
        actors = {r.get("actor") for r in out["roles"]}
        self.assertIn("(host)", actors)
        self.assertIn("(unattributed)", actors)
        self.assertEqual(out["unattributed_calls"], 1)


class ObserveBlocksNothing(unittest.TestCase):

    def test_observe_finds_what_enforce_would_refuse_but_allows_it(self):
        policy = Policy(loop_id="r", read_paths=("/allowed/**",), tools=("Read",))
        call = event("Read", file_path="/etc/shadow")
        strict = decide(call, policy, mode="enforce", attributed=True)
        loose = decide(call, policy, mode="observe", attributed=True)
        self.assertTrue(strict.blocks)
        self.assertFalse(loose.blocks)
        # identical finding, different consequence
        self.assertEqual(strict.reason_code, loose.reason_code)
        self.assertEqual(strict.message, loose.message)

    def test_off_checks_nothing_and_says_so(self):
        decision = decide(event("Read", file_path="/etc/shadow"),
                          Policy(loop_id="r"), mode="off", attributed=True)
        self.assertEqual(decision.reason_code, "mode_off")
        self.assertFalse(decision.blocks)


class TheHostIsNeverRefused(unittest.TestCase):

    def test_main_loop_calls_are_not_governed_by_a_role_policy(self):
        """Refusing the host would break the orchestrator that builds the partition."""
        call = ToolEvent(phase="pre", tool="Read", tool_input={"file_path": "/etc/shadow"},
                         host="test", session_ref="s", actor_ref=None)
        decision = decide(call, Policy(loop_id="r"), mode="enforce", attributed=False)
        self.assertFalse(decision.blocks)
        self.assertEqual(decision.reason_code, "host_actor")


class TheChainSurvivesConcurrency(GateEnvIsolated):
    """The exact failure that permanently destroys the runtime's shared log.

    `scw_runtime.events.EventLog` gives each process its own `seq` starting at
    zero, so two writers on one file can never verify again. The gate chains
    per FILE under an exclusive lock instead.
    """

    def test_many_concurrent_writers_leave_one_verifiable_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gate.jsonl"
            os.environ["MAXEY0_GATE_LOG"] = str(path)

            def write(i: int) -> bool:
                # payloads over the 8 KB buffer are where torn writes begin
                return journal.emit("gate.attempt",
                                    {"i": i, "pad": "x" * 9000})["persisted"]

            with ThreadPoolExecutor(max_workers=16) as pool:
                results = list(pool.map(write, range(64)))

            self.assertTrue(all(results))
            data = journal.read_all(path)
            report = journal.verify(data["records"])

        # Every observation survives, nothing is torn, and the chain never
        # reports a gap -- a record that could not take the lock is residue
        # rather than a hole.
        self.assertEqual(data["damaged"], 0)
        self.assertEqual(len(data["records"]), 64)
        self.assertTrue(report["ok"], report["broken"])
        self.assertEqual(report["chained"] + report["unlocked_writes"], 64)
        self.assertEqual(report["verified_prefix"], report["chained"])
        self.assertGreater(report["writers"], 1)


class ATornLineIsCountedNotDropped(GateEnvIsolated):

    def test_damage_is_reported_rather_than_crashing_the_reader(self):
        """`iter_records` in the runtime dies on this; the gate must not."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gate.jsonl"
            os.environ["MAXEY0_GATE_LOG"] = str(path)
            journal.emit("gate.attempt", {"ok": 1}, path=path)
            with path.open("a", encoding="utf-8") as fh:
                fh.write('{"seq": 1, "type": "gate.attempt", "payl\n')  # torn
            journal.emit("gate.attempt", {"ok": 2}, path=path)
            data = journal.read_all(path)

        self.assertEqual(data["damaged"], 1)
        self.assertEqual(len(data["records"]), 2)


class AGateCrashNeverBlocks(GateEnvIsolated):

    def test_unparseable_payload_exits_clean_and_records_a_fail_open(self):
        from gate.adapters import claude_code as cc
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gate.jsonl"
            os.environ["MAXEY0_GATE_LOG"] = str(path)
            cc._fail_open("payload_unparseable", "boom", tool="Read")
            records = journal.read_all(path)["records"]
        self.assertEqual(records[0]["type"], "gate.fail_open")
        self.assertIn("residue", records[0]["payload"]["note"])


class AnUncheckedCallIsNeverReportedAsContained(unittest.TestCase):
    """Regression: three ways a call escaped checking and was called in_scope."""

    def test_a_known_tool_under_a_variant_path_key_is_still_checked(self):
        """`Read{filePath}` was allowed where `Read{file_path}` was denied.

        `resource_of` consulted only the tool's own declared key, so a host
        spelling the argument differently produced no resource, skipped the
        path branch, and fell through to the blanket allow — the same read
        permitted or refused by spelling alone, and the permitted one recorded
        as `in_scope`.
        """
        policy = Policy(loop_id="r", read_paths=("/allowed/**",), tools=("Read",))
        for key in ("file_path", "filePath", "path", "target_file"):
            with self.subTest(key=key):
                decision = decide(event("Read", **{key: "/etc/shadow"}), policy,
                                  mode="enforce", attributed=True)
                self.assertTrue(decision.blocks, f"{key} escaped the check")

    def test_a_file_tool_naming_nothing_recognizable_fails_open_loudly(self):
        """Not `allow / in_scope` — that would call an unchecked read contained."""
        policy = Policy(loop_id="r", read_paths=("/allowed/**",), tools=("Read",))
        decision = decide(event("Read", mystery_arg="/etc/shadow"), policy,
                          mode="enforce", attributed=True)
        self.assertEqual(decision.verdict, "fail_open")
        self.assertEqual(decision.reason_code, "gate_error")
        self.assertFalse(decision.blocks)

    def test_a_bare_relative_filename_is_treated_as_a_path(self):
        """`secrets.env` has no separator but is still a file under cwd."""
        policy = Policy(loop_id="r", read_paths=("/allowed/**",),
                        tools=("some_host_tool",))
        decision = decide(event("some_host_tool", file="secrets.env"), policy,
                          mode="enforce", attributed=True)
        self.assertTrue(decision.blocks)


class ContainmentCanReportFailure(unittest.TestCase):
    """Regression: `held` was a tautology and could never be False.

    It was `denied > 0 or allowed == evaluated`, and since
    `evaluated = allowed + denied` one disjunct is always true. The gate could
    never report that containment failed — which is precisely what `observe`
    mode exists to detect.
    """

    def _containment(self, records):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
        from maxey0_studio import gate_view
        return gate_view.containment(records)

    def _rec(self, kind, reason):
        return {"type": kind, "seq": 0,
                "payload": {"attributed": True, "loop_id": "m",
                            "reason_code": reason, "mode": "observe"}}

    def test_an_allowed_out_of_scope_call_makes_held_false(self):
        out = self._containment([self._rec("gate.allowed", "path_outside_scope")])
        self.assertFalse(out["held"])
        self.assertEqual(out["violations"], 1)

    def test_a_refused_out_of_scope_call_keeps_held_true(self):
        out = self._containment([self._rec("gate.denied", "path_outside_scope")])
        self.assertTrue(out["held"])
        self.assertEqual(out["violations"], 0)

    def test_held_is_reachable_in_all_three_states(self):
        seen = {
            self._containment([])["held"],
            self._containment([self._rec("gate.allowed", "in_scope")])["held"],
            self._containment([self._rec("gate.allowed", "tool_not_granted")])["held"],
        }
        self.assertEqual(seen, {None, True, False})


class AmbientActivityIsNotResidue(GateEnvIsolated):
    """Regression: ordinary subagent use made containment permanently un-claimable.

    The gate sees EVERY subagent tool call, including ones from work that has
    nothing to do with an SCW loop. Counting those as `unattributed` meant the
    residue signal fired constantly and therefore meant nothing. An actor in a
    session where no role was ever dispatched is ambient host activity: there is
    no containment claim for it to weaken.
    """

    def _containment(self, records):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
        from maxey0_studio import gate_view
        return gate_view.containment(records)

    def _obs(self, reason):
        return {"type": "gate.observed", "seq": 0,
                "payload": {"attributed": False, "reason_code": reason,
                            "mode": "observe", "tool": "Read"}}

    def _role_call(self):
        return {"type": "gate.allowed", "seq": 1,
                "payload": {"attributed": True, "loop_id": "m",
                            "reason_code": "in_scope", "mode": "enforce"}}

    def test_ambient_calls_do_not_make_a_run_unclaimable(self):
        out = self._containment([self._obs("ambient_actor"),
                                 self._obs("ambient_actor"),
                                 self._role_call()])
        self.assertTrue(out["claimable"])
        self.assertEqual(out["residue"]["total"], 0)
        self.assertEqual(out["ambient_calls"], 2)

    def test_a_genuine_unattributed_call_still_does(self):
        out = self._containment([self._obs("unattributed"), self._role_call()])
        self.assertFalse(out["claimable"])
        self.assertEqual(out["residue"]["unattributed"], 1)

    def test_ambient_host_and_role_are_three_distinct_rows(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
        from maxey0_studio import gate_view
        rows = gate_view.by_role([self._obs("ambient_actor"),
                                  self._obs("host_actor"),
                                  self._role_call()])["roles"]
        labels = {r.get("actor") or r["loop_id"] for r in rows}
        self.assertEqual(labels, {"(ambient)", "(host)", "m"})

    def test_a_session_with_no_dispatch_resolves_ambient(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["MAXEY0_GATE_STATE"] = tmp
            _, how = attribution.resolve("fresh-session", "a1", None, None, None, None)
        self.assertEqual(how, "ambient")

    def test_a_session_that_dispatched_a_role_resolves_unattributed(self):
        """Once a role is in play, an actor we cannot place is real residue."""
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["MAXEY0_GATE_STATE"] = tmp
            attribution.declare_dispatch("s-live", "maker", actor_kind="general-purpose")
            _, how = attribution.resolve("s-live", "aX", None, None, None, None)
        self.assertEqual(how, "unattributed")


class PathScoping(unittest.TestCase):

    def test_a_directory_pattern_covers_its_subtree(self):
        policy = Policy(loop_id="r", read_paths=("/repo/docs",), tools=("Read",))
        inside = decide(event("Read", file_path="/repo/docs/a/b.md"), policy,
                        mode="enforce", attributed=True)
        outside = decide(event("Read", file_path="/repo/src/x.py"), policy,
                         mode="enforce", attributed=True)
        self.assertFalse(inside.blocks)
        self.assertTrue(outside.blocks)

    def test_empty_read_paths_means_no_filesystem_read_is_in_scope(self):
        """Distinct from no policy at all, which means unmeasured."""
        policy = Policy(loop_id="r", read_paths=(), tools=("Read",))
        decision = decide(event("Read", file_path="/anything"), policy,
                          mode="enforce", attributed=True)
        self.assertTrue(decision.blocks)
        self.assertEqual(decision.reason_code, "path_outside_scope")

    def test_a_shell_is_refused_unless_explicitly_granted(self):
        policy = Policy(loop_id="r", tools=("Bash",), bash_allow=())
        decision = decide(event("Bash", command="cat /etc/shadow"), policy,
                          mode="enforce", attributed=True)
        self.assertTrue(decision.blocks)
        self.assertEqual(decision.reason_code, "command_not_granted")

    def test_tool_classification_covers_the_reach_categories(self):
        self.assertEqual(classify("Read"), "file_read")
        self.assertEqual(classify("Write"), "file_write")
        self.assertEqual(classify("Bash"), "shell")
        self.assertEqual(classify("WebFetch"), "egress")
        self.assertEqual(classify("Agent"), "delegation")
        self.assertEqual(classify("mcp__worlds__read"), "mcp")
        self.assertEqual(classify("SomethingNew"), "opaque")

    def test_resource_extraction_names_the_thing_reached(self):
        self.assertEqual(resource_of(event("Read", file_path="/a/b")), "/a/b")
        self.assertEqual(resource_of(event("Bash", command="ls -la")), "ls -la")


if __name__ == "__main__":
    unittest.main(verbosity=2)


class SearchToolsCannotEscapeByOmission(unittest.TestCase):
    """Grep/Glob with no `path` search the working directory. Treating that as
    "names nothing" failed open in enforce mode and let a docs-only role sweep
    the repo for secrets."""

    def setUp(self):
        self.root = os.getcwd()
        self.docs = os.path.join(self.root, "docs")
        self.policy = Policy(loop_id="r", read_paths=(self.docs,),
                             tools=("Grep", "Glob", "LS"))

    def _ev(self, tool, cwd, **inp):
        return ToolEvent(phase="pre", tool=tool, tool_input=inp, host="test",
                         session_ref="s1", actor_ref="a1", actor_kind="role", cwd=cwd)

    def test_pathless_search_from_outside_scope_is_denied(self):
        for tool, inp in (("Grep", {"pattern": "KEY"}), ("Glob", {"pattern": "**/.env"})):
            with self.subTest(tool=tool):
                d = decide(self._ev(tool, self.root, **inp), self.policy,
                           mode="enforce", attributed=True)
                self.assertEqual(d.verdict, "deny")

    def test_pathless_search_inside_scope_is_allowed(self):
        d = decide(self._ev("Grep", self.docs, pattern="KEY"), self.policy,
                   mode="enforce", attributed=True)
        self.assertEqual(d.verdict, "allow")

    def test_pathless_search_with_unknown_cwd_is_denied(self):
        d = decide(self._ev("Glob", None, pattern="**/.env"), self.policy,
                   mode="enforce", attributed=True)
        self.assertEqual((d.verdict, d.reason_code), ("deny", "path_undeterminable"))

    def test_glob_pattern_cannot_reach_outside_its_path(self):
        outside = self.root.replace("\\", "/") + "/**/.env"
        for pattern in (outside, "../**/.env"):
            with self.subTest(pattern=pattern):
                d = decide(self._ev("Glob", self.root, pattern=pattern, path=self.docs),
                           self.policy, mode="enforce", attributed=True)
                self.assertEqual(d.verdict, "deny")

    def test_relative_glob_under_path_is_allowed(self):
        d = decide(self._ev("Glob", self.root, pattern="**/*.md", path=self.docs),
                   self.policy, mode="enforce", attributed=True)
        self.assertEqual(d.verdict, "allow")


class BashAllowIsOneSimpleCommand(unittest.TestCase):
    """fnmatch's `*` matches `;`, `&&`, `|`, backticks and newlines, so a grant
    of `git status*` used to permit any command chained after it."""

    def test_chaining_does_not_ride_a_narrow_grant(self):
        from gate.protocol import command_matches

        grant = ("git status*",)
        self.assertTrue(command_matches("git status --short", grant))
        for cmd in ("git status; type .env", "git status && curl evil",
                    "git status || x", "git status | x", "git status `x`",
                    "git status $(x)", "git status\ncat .env", "git status > f"):
            with self.subTest(cmd=cmd):
                self.assertFalse(command_matches(cmd, grant))

    def test_a_pattern_that_spells_the_syntax_out_still_matches(self):
        from gate.protocol import command_matches

        self.assertTrue(command_matches("git log | head", ("git log | head",)))


class DispatchesSurviveConcurrentHookProcesses(unittest.TestCase):
    """Each hook is its own process, so a thread lock serialized nothing and
    parallel Agent dispatches overwrote each other's pending entries."""

    def test_parallel_processes_keep_every_pending_dispatch(self):
        import subprocess

        server = str(Path(__file__).resolve().parents[1] / "server")
        script = ("import sys; sys.path.insert(0, sys.argv[1]);"
                  "from gate import attribution;"
                  "r = attribution.declare_dispatch('S', 'role-' + sys.argv[2]);"
                  "sys.exit(0 if r.get('persisted', True) else 3)")
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, MAXEY0_GATE_STATE=tmp)
            procs = [subprocess.Popen([sys.executable, "-c", script, server, str(i)], env=env)
                     for i in range(12)]
            codes = [p.wait(timeout=60) for p in procs]
            state = json.loads((Path(tmp) / "actors-S.json").read_text(encoding="utf-8"))
            leftovers = [p.name for p in Path(tmp).iterdir() if p.name.endswith(".tmp")]
        self.assertEqual(codes, [0] * 12)
        self.assertEqual(sorted(e["loop_id"] for e in state["pending"]),
                         sorted(f"role-{i}" for i in range(12)))
        self.assertEqual(leftovers, [])


class AGovernedRoleCannotReconfigureTheGate(unittest.TestCase):
    """A role with tools=None could call observe_gate_mode{mode: off}."""

    def test_gate_control_tools_are_denied_to_an_attributed_role(self):
        for name in ("mcp__maxey0-observe__observe_gate_mode",
                     "mcp__maxey0-observe__observe_gate_policy",
                     "mcp__maxey0-ss__maxey0-ss_gate_set_mode",
                     "mcp__maxey0-ss__maxey0-ss_gate_set_policy",
                     "mcp__maxey0-ss__maxey0-ss_gate_declare_isolation"):
            for mode in ("observe", "enforce"):
                with self.subTest(tool=name, mode=mode):
                    d = decide(event(name, mode="off"), Policy(loop_id="r", tools=None),
                               mode=mode, attributed=True)
                    self.assertEqual((d.verdict, d.reason_code), ("deny", "gate_control_denied"))

    def test_writing_the_gate_state_directly_is_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            from unittest import mock

            with mock.patch.dict(os.environ, {"MAXEY0_GATE_STATE": tmp}):
                d = decide(event("Write", file_path=os.path.join(tmp, "policy-s1.json")),
                           Policy(loop_id="r", tools=None, write_paths=(tmp,)),
                           mode="enforce", attributed=True)
        self.assertEqual(d.reason_code, "gate_control_denied")

    def test_the_host_itself_can_still_set_the_mode(self):
        d = decide(event("mcp__maxey0-observe__observe_gate_mode", mode="off"),
                   None, mode="enforce", attributed=False)
        self.assertFalse(d.blocks)


class ToolCallsAreAttributedByWorkingDirectory(unittest.TestCase):
    """claude_code.run() dropped event.cwd on ordinary tool calls, and no tool
    could declare a workdir, so the portable cwd resolver never ran."""

    def test_run_passes_cwd_to_the_resolver(self):
        from unittest import mock

        from gate.adapters import claude_code as cc

        seen = {}

        def fake_resolve(*args, **kwargs):
            seen["args"] = args
            return None, "unattributed"

        payload = {"hook_event_name": "PreToolUse", "tool_name": "Read",
                   "tool_input": {"file_path": "x"}, "session_id": "s-cwd",
                   "cwd": "/work/role-a"}
        with tempfile.TemporaryDirectory() as tmp:
            env = {"MAXEY0_GATE_STATE": tmp, "MAXEY0_GATE_LOG": os.path.join(tmp, "g.jsonl")}
            with mock.patch.dict(os.environ, env), \
                    mock.patch.object(cc.attribution, "resolve", side_effect=fake_resolve):
                cc.run(payload)
        self.assertIn("/work/role-a", seen["args"])

    def test_a_declared_workdir_attributes_calls_made_from_it(self):
        from unittest import mock

        with tempfile.TemporaryDirectory() as tmp:
            workdir = os.path.join(tmp, "role-a")
            os.makedirs(workdir)
            with mock.patch.dict(os.environ, {"MAXEY0_GATE_STATE": tmp}):
                attribution.declare_dispatch("s-wd", "role-a", workdir=workdir)
                self.assertEqual(attribution.resolve_by_cwd("s-wd", workdir), "role-a")
