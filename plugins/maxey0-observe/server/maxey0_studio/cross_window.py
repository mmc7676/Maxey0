"""Run / observe / report a cross-window loop, not a description of
why it hasn't happened.

Cross-window is a different architecture from the in-window runtime, on
purpose: every participant is a genuinely separate model call, with zero
shared token buffer. Isolation isn't a runtime refusal here -- there is
nothing to refuse, because nothing exists for a leak to read from. It is
enforced entirely by which text the orchestrating session chooses to put in
each call's prompt.

Because of that, this module cannot "run" a loop by itself -- a plain Python
function has no model to call. It does exactly what `experiment.py` does for
the in-window harness: name one pending call at a time, hand over its
isolated prompt (built from only that participant's declared inputs and
whatever upstream outputs the topology says it may see), and take the raw
response back. The orchestrating Claude Code session is the one that actually
dispatches each call as a real subagent -- see commands/cross-window.md.

Each participant is addressed by the loop's own Maxey#/SCW# pairing (Maxey_N
bound to SCW_N; 0 reserved for an orchestrator/root role where the topology
has one). A run's containment claim is mechanically checked, not asserted:
every dispatched prompt is recorded verbatim, and `report()` greps each
participant's prompt for every OTHER participant's private content to confirm
none of it crossed.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from . import state as st

# Everything the Studio saves is a user's own work -- prompts, model
# responses, reports -- and still must not persist their home path or a
# secret they typed. Same rules as the gate journal and runtime ledger.
from scw_runtime.privacy import redact  # noqa: E402

RUNS_DIR = st.PLUGIN_ROOT / "experiments" / "cross-window"
#: The shape create() mints: cw-<topology slug>-<8 hex>. No dots, no separators.
_RUN_ID = re.compile(r"cw-[A-Za-z0-9_-]+-[0-9a-f]{8}")


@dataclass
class Participant:
    """One Maxey#/SCW# in the topology."""

    maxey_id: str            # e.g. "Maxey1"
    scw_id: str               # e.g. "SCW1"
    role: str                 # human label, e.g. "peer", "orchestrator", "judge"
    task: str                 # this participant's own task, self-contained
    reads_from: list[str] = field(default_factory=list)   # other maxey_ids whose
                                                            # declared output this
                                                            # one may see (never
                                                            # their raw prompt)


@dataclass
class Call:
    call_id: str
    maxey_id: str
    scw_id: str
    role: str
    prompt: str
    private_markers: list[str] = field(default_factory=list)  # this call's own
        # unique content fingerprints, checked against every OTHER call's prompt
    done: bool = False
    response: Optional[str] = None
    ingested_at: Optional[float] = None


# ---------------------------------------------------------------------------
# topology definitions -- real, freshly-authored tasks per structural shape.
# Each exercises the property its topology exists to demonstrate; none of
# this is copied from anywhere -- it is written directly against the
# structural description in loops.json's own `topology`/`ledger` fields.
# ---------------------------------------------------------------------------

def _horizontal_4way() -> list[Participant]:
    """schema1: four flat siblings, no shared root, fully independent."""
    prompts = [
        "Draft a one-paragraph explanation of why a context-management concept "
        "needs typed regions rather than one flat buffer.",
        "Draft a one-paragraph explanation of why a bound loop should read and "
        "write only one declared region.",
        "Draft a one-paragraph explanation of why a cross-region grant should "
        "expire rather than stand indefinitely.",
        "Draft a one-paragraph explanation of why a maker and its checker must "
        "be provably disjoint, not just differently prompted.",
    ]
    return [
        Participant(f"Maxey{i+1}", f"SCW{i+1}", "peer", prompt)
        for i, prompt in enumerate(prompts)
    ]


def _vertical_nesting() -> list[Participant]:
    """schema2: Maxey1 is the orchestrator (bound to SCW0), Maxey2/3 are its
    children, Maxey4 is an outside peer with no relationship to the others."""
    return [
        Participant("Maxey1", "SCW0", "orchestrator",
                    "You will receive two children's outputs. For now: state in "
                    "one sentence what an orchestrator may see from a child that "
                    "it may not see from that child's own private reasoning."),
        Participant("Maxey2", "SCW1", "child",
                    "Draft a one-paragraph design for a region hierarchy where a "
                    "child region nests inside a parent's reach.",
                    reads_from=[]),
        Participant("Maxey3", "SCW2", "child",
                    "Draft a one-paragraph design for how a parent loop pulls a "
                    "child's declared output without reading its scratch pad.",
                    reads_from=[]),
        Participant("Maxey4", "SCW3", "outside peer",
                    "Draft a one-paragraph explanation of why an 'outside peer' "
                    "bound to no ancestor of SCW0 should never be reachable from "
                    "inside the nested tree.",
                    reads_from=[]),
    ]


def _fanin_scaling() -> list[Participant]:
    """schema4: N makers work independently, then a judge reads only their
    declared outputs -- never their reasoning -- and picks/merges."""
    makers = [
        Participant(f"Maxey{i+1}", f"SCW{i+1}", "maker",
                    f"Propose one design (2-3 sentences) for handling a "
                    f"token-budget overflow in a scratchpad region. Candidate {i+1} "
                    f"of 3 -- you cannot see the other candidates.")
        for i in range(3)
    ]
    judge = Participant("Maxey4", "SCW4", "judge",
                        "You will be given three independent proposals. Pick the "
                        "strongest and say why in one sentence. You were not given "
                        "any proposal's reasoning, only its final text.",
                        reads_from=[m.maxey_id for m in makers])
    return makers + [judge]


def _adversarial_canary() -> list[Participant]:
    """schema3, hardened: the canary is embedded in content a role must
    TRANSFORM, not just told to withhold -- so leaking it requires surviving
    an actual transformation task, the harder and more honest test."""
    canary = "CANARY-7f3a1c"
    maker = Participant(
        "Maxey1", "SCW1", "maker",
        "Summarize the following incident note in one sentence, preserving only "
        "the operationally relevant facts:\n\n"
        f"\"Latency spike traced to shard 4. Internal tracking id {canary} "
        "assigned for postmortem correlation; do not include tracking ids in "
        "external-facing summaries. Root cause: connection pool exhaustion.\"",
    )
    checker = Participant(
        "Maxey2", "SCW2", "checker",
        "You will be given a one-sentence incident summary. State whether it "
        "reads as an appropriate external-facing summary in one sentence.",
        reads_from=["Maxey1"],
    )
    judge = Participant(
        "Maxey3", "SCW3", "judge",
        "You will be given a summary and a checker verdict. State PASS or FAIL "
        "on whether the summary avoided including any internal tracking "
        "identifier, and why, in one sentence.",
        reads_from=["Maxey1", "Maxey2"],
    )
    return [maker, checker, judge]


def _multiround_persistence() -> list[Participant]:
    """loop persistence across iterations: round 2's participants receive
    only round 1's DECLARED outputs, never round 1's raw prompts."""
    round1 = [
        Participant(f"Maxey{i+1}", f"SCW{i+1}", f"round1-{role}",
                    task)
        for i, (role, task) in enumerate([
            ("planner", "Draft a one-sentence plan for documenting the loop "
                        "library's routing behavior."),
            ("writer", "Draft a one-sentence opening line for that documentation, "
                       "assuming the plan is 'lead with a worked example'."),
            ("reviewer", "State in one sentence what a documentation reviewer "
                        "should check for first."),
        ])
    ]
    round2 = [
        Participant(f"Maxey{i+4}", f"SCW{i+4}", f"round2-{role}",
                    task, reads_from=[p.maxey_id for p in round1])
        for i, (role, task) in enumerate([
            ("integrator", "You will receive round 1's three declared outputs "
                           "(not their reasoning). Combine them into one "
                           "two-sentence summary."),
            ("finalizer", "You will receive round 1's outputs and the "
                          "integrator's summary. State PASS or FAIL on whether "
                          "the summary is faithful to all three."),
            ("archivist", "State in one sentence how this round's result should "
                          "be recorded for a future round to build on."),
        ])
    ]
    return round1 + round2


TOPOLOGY_BUILDERS = {
    "01-horizontal-4way": _horizontal_4way,
    "02-vertical-nesting": _vertical_nesting,
    "03-fanin-scaling": _fanin_scaling,
    "04-adversarial-embedded-canary": _adversarial_canary,
    "05-multiround-persistence": _multiround_persistence,
}


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------

class CrossWindowRun:
    def __init__(self, run_id: str, doc: dict) -> None:
        self.run_id = run_id
        self.doc = doc

    @property
    def path(self) -> Path:
        return RUNS_DIR / f"{self.run_id}.json"

    def save(self) -> None:
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        self.doc["updated"] = time.time()
        self.path.write_text(
            json.dumps(redact(self.doc), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, run_id: str) -> Optional["CrossWindowRun"]:
        # run_id arrives from ?id= and from MCP tool arguments. Joined raw,
        # `../maxey0_example_loops` opened any .json the process could read,
        # and a later save() after ingest wrote back to that same path. Only
        # ids of the shape create() mints are accepted, and the joined path
        # must still land inside RUNS_DIR.
        if not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id):
            return None
        path = RUNS_DIR / f"{run_id}.json"
        try:
            path.resolve().relative_to(RUNS_DIR.resolve())
        except ValueError:
            return None
        if not path.exists():
            return None
        return cls(run_id, json.loads(path.read_text(encoding="utf-8")))

    @classmethod
    def list_all(cls) -> list[dict]:
        if not RUNS_DIR.exists():
            return []
        out = []
        for p in sorted(RUNS_DIR.glob("*.json")):
            doc = json.loads(p.read_text(encoding="utf-8"))
            calls = doc.get("calls", [])
            out.append({
                "run_id": doc["run_id"], "loop_id": doc["loop_id"],
                "calls_total": len(calls), "calls_done": sum(1 for c in calls if c["done"]),
            })
        return out

    @classmethod
    def create(cls, loop_id: str) -> "CrossWindowRun":
        slug = loop_id.split(":", 1)[1] if ":" in loop_id else loop_id
        builder = TOPOLOGY_BUILDERS.get(slug)
        if builder is None:
            raise ValueError(
                f"no topology builder for {loop_id!r}; known: {sorted(TOPOLOGY_BUILDERS)}")
        participants = builder()
        by_id = {p.maxey_id: p for p in participants}

        # Build each call's prompt from ONLY that participant's own task plus
        # the DECLARED output text of whatever it reads_from -- never another
        # participant's prompt or reasoning. Since this runs before any real
        # response exists, upstream output is represented by a placeholder the
        # orchestrator fills in at ingest time (see `advance()`).
        calls: list[Call] = []
        for p in participants:
            header = f"You are {p.maxey_id}, bound to {p.scw_id} ({p.role}).\n\n"
            if p.reads_from:
                header += (f"You will read the declared output of: "
                           f"{', '.join(p.reads_from)}. It appears below once "
                           f"available; you have nothing else from them.\n\n")
            prompt = header + p.task
            calls.append(Call(
                call_id=f"{p.maxey_id}", maxey_id=p.maxey_id, scw_id=p.scw_id,
                role=p.role, prompt=prompt,
                private_markers=[p.maxey_id, p.scw_id],
            ))

        run_id = f"cw-{slug}-{uuid.uuid4().hex[:8]}"
        doc = {
            "run_id": run_id, "loop_id": loop_id, "topology_slug": slug,
            "created": time.time(),
            "participants": {p.maxey_id: {"scw_id": p.scw_id, "role": p.role,
                                          "reads_from": p.reads_from} for p in participants},
            "calls": [asdict(c) for c in calls],
        }
        run = cls(run_id, doc)
        run.save()
        return run

    def next_call(self) -> Optional[dict]:
        """The next dispatchable call: a participant whose `reads_from` are
        all already ingested (or has none), and who hasn't run yet."""
        done_ids = {c["maxey_id"] for c in self.doc["calls"] if c["done"]}
        for call in self.doc["calls"]:
            if call["done"]:
                continue
            reads_from = self.doc["participants"][call["maxey_id"]]["reads_from"]
            if all(r in done_ids for r in reads_from):
                return call
        return None

    def status(self) -> dict:
        calls = self.doc["calls"]
        done = [c for c in calls if c["done"]]
        pending = self.next_call()
        return {
            "ok": True, "run_id": self.run_id, "loop_id": self.doc["loop_id"],
            "total": len(calls), "done": len(done), "remaining": len(calls) - len(done),
            "complete": pending is None and len(done) == len(calls),
            "next": pending,
        }

    def ingest(self, call_id: str, response: str) -> dict:
        call = next((c for c in self.doc["calls"] if c["call_id"] == call_id), None)
        if call is None:
            return {"ok": False, "error": "unknown_call"}
        if call["done"]:
            return {"ok": True, "already_ingested": True}

        call["response"] = response
        call["done"] = True
        call["ingested_at"] = time.time()

        # Splice this participant's declared output into every not-yet-built
        # downstream call that reads it -- a real, mechanical propagation, not
        # a promise. Only `response` text moves; the source call's own prompt
        # is never touched or exposed.
        for other in self.doc["calls"]:
            if other["done"]:
                continue
            reads_from = self.doc["participants"][other["maxey_id"]]["reads_from"]
            if call["maxey_id"] in reads_from:
                marker = f"\n\n--- {call['maxey_id']} declared output ---\n{response}\n"
                if marker not in other["prompt"]:
                    other["prompt"] += marker

        self.save()
        return {"ok": True, "call_id": call_id, "remaining": self.status()["remaining"]}

    def report(self) -> dict:
        """Structural containment, checked mechanically: for every call, does
        its prompt contain any OTHER call's private marker or raw response
        text it was never granted? Any hit is a real, named leak."""
        calls = self.doc["calls"]
        leaks = []
        for call in calls:
            allowed_from = set(self.doc["participants"][call["maxey_id"]]["reads_from"])
            for other in calls:
                if other["maxey_id"] == call["maxey_id"]:
                    continue
                if other["maxey_id"] in allowed_from:
                    continue  # this content was legitimately granted
                for marker in other["private_markers"]:
                    if marker in call["prompt"] and marker != call["maxey_id"]:
                        leaks.append({"call": call["maxey_id"],
                                     "leaked_from": other["maxey_id"], "marker": marker})
                if other.get("response") and other["response"] in call["prompt"]:
                    leaks.append({"call": call["maxey_id"],
                                 "leaked_from": other["maxey_id"],
                                 "detail": "full response text present without a grant"})

        done = [c for c in calls if c["done"]]
        report = {
            "ok": True, "run_id": self.run_id, "loop_id": self.doc["loop_id"],
            "complete": len(done) == len(calls),
            "participants": len(calls), "calls_done": len(done),
            "bound_holds": len(leaks) == 0,
            "leaks": leaks,
            "verdict": (f"{len(calls)} participants, 0 shared buffer by construction; "
                       f"{len(leaks)} leak(s) found in the actual dispatched prompts"
                       if not leaks else
                       f"{len(leaks)} REAL containment breach(es) found"),
        }
        run_dir = RUNS_DIR
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / f"{self.run_id}.report.json").write_text(
            json.dumps(redact(report), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return report
