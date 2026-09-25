"""L1-L4 declared as HarnessSpec data, not four hand-written pattern modules.

L1 reproduces the topology of the original loops/patterns/maker_checker_judge.py
exactly (star: checker and judge both read only the maker's exposed "patches";
checker is denied the rubric resource, judge keeps it) -- this is deliberate: L1's
18 real subagent calls and results/coded.json are already collected and must not be
invalidated by a topology drift between the hand file and this DSL rewrite.
"""

from __future__ import annotations

from .harness_dsl import HarnessSpec, RoleDef

RUBRIC_LEDGER = """\
ACCEPTANCE CRITERION -- a proposed fix to ledger.py is ACCEPTED when all hold:

R-1  Every currently-red test in test_ledger.py passes without modifying
     test_ledger.py itself.
R-2  Every currently-green test in test_ledger.py still passes (no
     regression).
R-3  The fix changes ledger.py only -- test_ledger.py and MANIFEST.json are
     not modified.
R-4  The fix addresses the actual logic error, not just the specific test
     values used to catch it (no special-casing the test's inputs).

A patch failing any rule is REJECTED with the rule id.
"""

L1_MAKER_CHECKER_JUDGE = HarnessSpec(
    harness_id="l1-maker-checker-judge",
    topology="star",
    resources=("target", "rubric"),
    iteration_budget=16,
    pin_criteria=(("acceptance", "rubric", "Ledger fix acceptance criterion"),),
    extra_negative_controls=(("maker", "rubric", "write"),),
    artifact_role="maker",
    roles=(
        RoleDef(
            role_id="maker",
            exposes=("patches",),
            verification_level=3,
            max_iterations=2,
            criterion_id="acceptance",
            output_kind="code",
            goal="Propose a fix for the target fixture that satisfies the rubric",
        ),
        RoleDef(
            role_id="checker",
            reads_from=frozenset({"maker"}),
            excluded_resources=frozenset({"rubric"}),
            verification_level=1,
            max_iterations=2,
            output_kind="verdict",
            goal="Structurally check the maker's proposed patch",
        ),
        RoleDef(
            role_id="judge",
            reads_from=frozenset({"maker"}),
            verification_level=3,
            max_iterations=2,
            output_kind="verdict",
            goal="Grade the maker's patch against the pinned rubric",
        ),
    ),
)

L2_DEBATE_PEER = HarnessSpec(
    harness_id="l2-debate-peer",
    topology="parallel",
    resources=("target", "rubric"),
    iteration_budget=16,
    pin_criteria=(("acceptance", "rubric", "Ledger fix acceptance criterion"),),
    # 5 roles, not 4: an earlier draft had "synth-judge" both produce the merged code
    # AND be the role graded against the rubric -- but the runtime correctly refuses
    # a self-graded tick (R1 identity: verified_by cannot equal loop_id), so that
    # design could never produce a real enforced verdict, only informational pytest
    # evidence. A real independent judge, distinct from the synthesizer AND from all
    # three peers, is what makes L2 an actual disjointness test rather than three
    # blind peers feeding an unaccountable synthesizer.
    artifact_role="synthesizer",
    roles=(
        RoleDef(
            role_id="peer-a", exposes=("proposal-a",), verification_level=2,
            max_iterations=2, output_kind="code",
            goal="Independently propose a fix; you cannot see other peers' work",
        ),
        RoleDef(
            role_id="peer-b", exposes=("proposal-b",), verification_level=2,
            max_iterations=2, output_kind="code",
            goal="Independently propose a fix; you cannot see other peers' work",
        ),
        RoleDef(
            role_id="peer-c", exposes=("proposal-c",), verification_level=2,
            max_iterations=2, output_kind="code",
            goal="Independently propose a fix; you cannot see other peers' work",
        ),
        RoleDef(
            role_id="synthesizer",
            reads_from=frozenset({"peer-a", "peer-b", "peer-c"}),
            exposes=("final-patch",),
            verification_level=2, max_iterations=2, output_kind="code",
            goal="Pick or merge the strongest proposal; respond with the resulting "
                 "code as your final patch. You are not the judge of your own work.",
        ),
        RoleDef(
            role_id="judge",
            reads_from=frozenset({"synthesizer"}),
            verification_level=3, max_iterations=2, criterion_id="acceptance",
            output_kind="verdict",
            goal="Grade the synthesizer's final patch against the pinned rubric",
        ),
    ),
)

L3_PIPELINE = HarnessSpec(
    harness_id="l3-pipeline",
    topology="chain",
    resources=("target", "rubric"),
    iteration_budget=16,
    pin_criteria=(("acceptance", "rubric", "Ledger fix acceptance criterion"),),
    artifact_role="implementer",
    roles=(
        RoleDef(
            role_id="planner", exposes=("plan",), verification_level=1,
            max_iterations=2, output_kind="text",
            goal="Plan a fix strategy in prose, without writing code",
        ),
        RoleDef(
            role_id="implementer",
            reads_from=frozenset({"planner"}), exposes=("patches",),
            verification_level=2, max_iterations=2, output_kind="code",
            goal="Implement the planner's strategy as a patch",
        ),
        RoleDef(
            role_id="verifier",
            # deliberately reads ONLY implementer's output, never planner's --
            # the planner's abandoned alternatives are the E8 leak-probe target here.
            reads_from=frozenset({"implementer"}),
            verification_level=3, max_iterations=2, criterion_id="acceptance",
            output_kind="verdict",
            goal="Verify the patch against the rubric; you were not given the plan",
        ),
    ),
)

L4_NESTED = HarnessSpec(
    harness_id="l4-nested",
    topology="nested",
    resources=("target", "rubric"),
    iteration_budget=16,
    pin_criteria=(("acceptance", "rubric", "Ledger fix acceptance criterion"),),
    artifact_role="child-maker",
    parent_of={"grandchild-checker": "child-maker"},
    roles=(
        RoleDef(
            role_id="child-maker", exposes=("patches",), verification_level=2,
            max_iterations=2, criterion_id="acceptance", output_kind="code",
            goal="Propose a fix; a nested checker verifies it",
        ),
        RoleDef(
            role_id="grandchild-checker",
            reads_from=frozenset({"child-maker"}),
            verification_level=1, max_iterations=2, output_kind="verdict",
            goal="Verify the nested maker's patch",
        ),
    ),
)

COMPOSITIONS: dict[str, HarnessSpec] = {
    "l1-maker-checker-judge": L1_MAKER_CHECKER_JUDGE,
    "l2-debate-peer": L2_DEBATE_PEER,
    "l3-pipeline": L3_PIPELINE,
    "l4-nested": L4_NESTED,
}
