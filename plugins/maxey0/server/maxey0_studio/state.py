"""The one live state the Studio serves: Maxey0's hierarchy + a real SCW window.

Everything here is backed by real files and the real `scw_runtime` enforcement
engine. There is no mock layer and no in-memory imitation of a region: when the
Studio shows you an SCW's contents, those bytes came out of a `ContextWindow`
that would have refused the read if the scope did not reach them.

Path resolution prefers a live checkout when the user has one (env vars), and
falls back to the vendored copy so the plugin works standalone:

    SCW_RUNTIME_SRC   -> scw-runtime/src        (the enforcement engine)
    MAXEY0_ROOT       -> Maxey0-OKF bundle root (concepts/skills/agents)
    MAXEY0_LOOPS      -> loops.json             (the hardened loop dataset)
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
VENDOR = PLUGIN_ROOT / "server" / "vendor"


def _resolve(env_var: str, vendored: Path, marker: str = "") -> Path:
    """Live checkout if the user has one and it really contains the marker;
    the vendored copy otherwise. A wrong env var should fall back loudly
    rather than half-load."""
    override = os.environ.get(env_var)
    if override:
        candidate = Path(override).expanduser()
        if not marker or (candidate / marker).exists() or candidate.is_file():
            return candidate
        print(f"[maxey0-studio] {env_var}={override} has no {marker!r}; "
              f"using vendored copy", file=sys.stderr)
    return vendored


SCW_SRC = _resolve("SCW_RUNTIME_SRC", VENDOR, "scw_runtime")
MAXEY0_ROOT = _resolve("MAXEY0_ROOT", VENDOR / "maxey0", "manifest.json")
LOOPS_JSON = _resolve("MAXEY0_LOOPS", VENDOR / "data" / "loops.json")

for _p in (str(SCW_SRC), str(VENDOR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from scw_runtime import ContextWindow, EventLog, partition, replay  # noqa: E402
from scw_runtime.errors import SCWError  # noqa: E402
from d4.harness_dsl import HarnessSpec, RoleDef, build_init_ops  # noqa: E402
from loopkit.harness_kit import access_matrix, containment_report, cost_model  # noqa: E402

EVENT_LOG = Path(
    os.environ.get("SCW_EVENT_LOG") or (Path.home() / ".scw" / "studio.jsonl")
)


# ---------------------------------------------------------------------------
# knowledge: concepts / skills / agents / loops
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


CROSS_WINDOW_RUNS_DIR = PLUGIN_ROOT / "experiments" / "cross-window"


def _apply_cross_window_evidence(loops: list[dict]) -> list[dict]:
    """A designer:* loop's status is `validated` only where a real cross-window
    run's own report says so -- computed fresh from the report file every load,
    never hand-set in loops.json. A loop with no report on disk, or a report
    that isn't complete and clean, stays exactly as the vendored data says.
    """
    if not CROSS_WINDOW_RUNS_DIR.exists():
        return loops

    best_by_loop: dict[str, dict] = {}
    for path in CROSS_WINDOW_RUNS_DIR.glob("*.report.json"):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        loop_id = report.get("loop_id")
        if not loop_id or not report.get("complete") or not report.get("bound_holds"):
            continue
        # Prefer the most recently written qualifying report if more than one.
        existing = best_by_loop.get(loop_id)
        if existing is None or path.stat().st_mtime > existing["_mtime"]:
            best_by_loop[loop_id] = {**report, "_mtime": path.stat().st_mtime,
                                     "_report_file": path.name}

    if not best_by_loop:
        return loops

    out = []
    for loop in loops:
        evidence = best_by_loop.get(loop["id"])
        if evidence is None:
            out.append(loop)
            continue
        out.append({
            **loop,
            "status": "validated",
            "hardening": {
                **loop.get("hardening", {}),
                "checked": True, "passed": True,
                "method": "cross_window.CrossWindowRun.report() -- real dispatched-prompt "
                          "grep for every other participant's private markers/response text",
                "bound_holds": True, "leaks": evidence.get("leaks", []),
                "participants": evidence.get("participants"),
                "verdict": evidence.get("verdict"),
            },
            "notes": f"{evidence.get('participants')} isolated subagent calls, "
                     f"0 leaks found. Report: experiments/cross-window/{evidence['_report_file']}.",
        })
    return out


@dataclass
class Knowledge:
    """Maxey0's hierarchy, loaded once. Read-only for the Studio's purposes."""

    concepts: list[dict] = field(default_factory=list)
    skills: list[dict] = field(default_factory=list)
    agents: list[dict] = field(default_factory=list)
    loops: list[dict] = field(default_factory=list)
    anchors: list[dict] = field(default_factory=list)
    roster: dict[str, dict] = field(default_factory=dict)
    team_edges: list[dict] = field(default_factory=list)

    @classmethod
    def load(cls) -> "Knowledge":
        manifest = _read_json(MAXEY0_ROOT / "manifest.json")
        registry = _read_json(MAXEY0_ROOT / "registry.json"
                              if (MAXEY0_ROOT / "registry.json").exists()
                              else MAXEY0_ROOT / "registry" / "registry.json")
        loops_doc = _read_json(LOOPS_JSON)

        anchors_path = (MAXEY0_ROOT / "anchors.json"
                        if (MAXEY0_ROOT / "anchors.json").exists()
                        else MAXEY0_ROOT / "data" / "anchors.json")
        anchors = _read_json(anchors_path)["anchors"]

        roster: dict[str, dict] = {}
        roster_path = (MAXEY0_ROOT / "maxey0_subagents.csv"
                       if (MAXEY0_ROOT / "maxey0_subagents.csv").exists()
                       else MAXEY0_ROOT / "data" / "maxey0_subagents.csv")
        if roster_path.exists():
            with roster_path.open(encoding="utf-8-sig", newline="") as fh:
                for row in csv.DictReader(fh):
                    roster[row["Index"]] = row

        team_edges: list[dict] = []
        team_path = (MAXEY0_ROOT / "team_mapping.csv"
                     if (MAXEY0_ROOT / "team_mapping.csv").exists()
                     else MAXEY0_ROOT / "data" / "team_mapping.csv")
        if team_path.exists():
            with team_path.open(encoding="utf-8-sig", newline="") as fh:
                team_edges = list(csv.DictReader(fh))

        loops = _apply_cross_window_evidence(loops_doc["loops"])

        return cls(
            concepts=manifest["concepts"],
            skills=manifest["skills"],
            agents=registry["agents"],
            loops=loops,
            anchors=anchors,
            roster=roster,
            team_edges=team_edges,
        )

    # -- lookups ------------------------------------------------------------
    def loop(self, loop_id: str) -> Optional[dict]:
        return next((l for l in self.loops if l["id"] == loop_id), None)

    def agent(self, registry_index: str) -> Optional[dict]:
        return next((a for a in self.agents
                     if a["registry_index"] == registry_index), None)

    def agent_name(self, registry_index: str) -> str:
        found = self.agent(registry_index)
        if found:
            return found["name"]
        row = self.roster.get(registry_index)
        return row["Name"] if row else registry_index

    def counts(self) -> dict:
        by_status: dict[str, int] = {}
        by_provenance: dict[str, int] = {}
        for loop in self.loops:
            by_status[loop["status"]] = by_status.get(loop["status"], 0) + 1
            by_provenance[loop["provenance"]] = by_provenance.get(loop["provenance"], 0) + 1
        return {
            "concepts": len(self.concepts),
            "skills": len(self.skills),
            "agents": len(self.agents),
            "roster": len(self.roster),
            "loops": len(self.loops),
            "loops_by_status": by_status,
            "loops_by_provenance": by_provenance,
        }


# ---------------------------------------------------------------------------
# turning a loops.json record into a real, bindable HarnessSpec
# ---------------------------------------------------------------------------

def spec_from_record(record: dict) -> HarnessSpec:
    """Compile a dataset record into a bindable HarnessSpec.

    loops.json is the contract: `agent_stages` (pipeline loops) or `roles`
    (battery/formation loops) is all the topology this needs. Deliberately does
    NOT import the dataset build script -- that needs openpyxl and the source
    spreadsheet, neither of which a plugin install can assume.
    """
    stages = record.get("agent_stages") or []
    roles: list[RoleDef] = []

    if stages:
        for index, stage in enumerate(stages):
            agent_id = stage["agent_id"]
            role_id = f"stage{index}-{agent_id.lower()}"
            prior = frozenset()
            if index > 0:
                prev_id = stages[index - 1]["agent_id"].lower()
                prior = frozenset({f"stage{index - 1}-{prev_id}"})
            roles.append(RoleDef(
                role_id=role_id,
                reads_from=prior,
                exposes=(f"{role_id}-out",),
                verification_level=1,
                max_iterations=2,
                output_kind="text",
                goal=f"{stage['agent_name']} ({agent_id}) performs its stage "
                     f"of {record['title']!r}",
            ))
    else:
        # battery / formation records name their roles directly; chain them so
        # each reads only its immediate upstream's declared exposure.
        named = record.get("roles") or record.get("hardening", {}).get("roles") or []
        for index, role_id in enumerate(named):
            prior = frozenset({named[index - 1]}) if index > 0 else frozenset()
            roles.append(RoleDef(
                role_id=role_id,
                reads_from=prior,
                exposes=(f"{role_id}-out",),
                verification_level=3 if "judge" in role_id or "check" in role_id else 1,
                max_iterations=2,
                output_kind="verdict" if ("judge" in role_id or "check" in role_id)
                            else "text",
                goal=f"{role_id} performs its role in {record['title']!r}",
            ))

    if not roles:
        raise ValueError(f"record {record['id']!r} declares no roles to bind")

    return HarnessSpec(
        harness_id=record["id"].replace(":", "-"),
        topology="chain",
        roles=tuple(roles),
        resources=(),
        iteration_budget=max(16, len(roles) * 2),
        artifact_role=roles[-1].role_id,
    )


# ---------------------------------------------------------------------------
# the live SCW session
# ---------------------------------------------------------------------------

class Session:
    """One live `ContextWindow` plus the bookkeeping the UI needs on top.

    Thread-safe because the HTTP server is threaded: every mutation takes the
    lock, so two browser tabs cannot interleave a half-applied loop binding.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.knowledge = Knowledge.load()
        self.window: ContextWindow = self._new_window()
        self.bound: dict[str, dict] = {}   # instance_id -> binding info
        self._counter = 0

    def _new_window(self) -> ContextWindow:
        EVENT_LOG.parent.mkdir(parents=True, exist_ok=True)
        return ContextWindow(
            total_budget=200_000,
            event_log=EventLog(path=EVENT_LOG),
            name="maxey0-studio",
        )

    # -- lifecycle ----------------------------------------------------------
    def reset(self) -> dict:
        with self._lock:
            head = self.window.log.head()
            self.window.log.close()
            self.window = self._new_window()
            self.bound.clear()
            self._counter = 0
            return {"ok": True, "run_id": self.window.log.run_id,
                    "previous_run": head, "event_log": str(EVENT_LOG)}

    # -- binding a loop -----------------------------------------------------
    def bind_loop(self, loop_id: str) -> dict:
        """Build a dataset loop's regions, harness and roles, now."""
        with self._lock:
            record = self.knowledge.loop(loop_id)
            if record is None:
                return {"ok": False, "error": "unknown_loop",
                        "message": f"no loop {loop_id!r} in the dataset"}
            if record.get("execution_mode") != "in-window":
                return {
                    "ok": False, "error": "not_bindable",
                    "message": f"{loop_id} is {record.get('execution_mode')!r}; only "
                               "in-window loops have regions this runtime can bind.",
                    "hint": "cross-window topologies are separate model calls with no "
                            "shared buffer -- there is nothing here to partition.",
                }

            self._counter += 1
            instance = f"L{self._counter}"
            prefix = f"{instance}-"
            spec = spec_from_record(record)
            ops = build_init_ops(spec, "scw", {})

            bound_loops: list[str] = []
            refusals: list[dict] = []
            for op in ops:
                args = dict(op.get("args", {}))
                for key in ("scw_id", "parent_scw_id", "from_scw_id",
                            "to_scw_id", "harness_id"):
                    if key in args and args[key]:
                        args[key] = prefix + args[key]
                for key in ("loop_id", "parent_loop_id"):
                    if args.get(key):
                        args[key] = prefix + args[key]
                if args.get("exposes"):
                    args["exposes"] = [prefix + n for n in args["exposes"]]

                try:
                    getattr(self.window, op["op"])(**args)
                except SCWError as exc:
                    if op.get("expect_refusal"):
                        # A refused negative control is the partition working.
                        refusals.append({
                            "op": op["op"],
                            "reason": args.get("reason", ""),
                            "error": type(exc).__name__,
                            "message": str(exc),
                        })
                        continue
                    raise
                else:
                    if op["op"] == "bind_scope":
                        bound_loops.append(args["loop_id"])

            info = {
                "instance": instance,
                "loop_id": loop_id,
                "title": record["title"],
                "prefix": prefix,
                "harness_id": prefix + spec.harness_id,
                "roles": bound_loops,
                "refused_negative_controls": len(refusals),
                "refusals": refusals,
                "status": record["status"],
                "provenance": record["provenance"],
            }
            self.bound[instance] = info
            return {"ok": True, **info, "regions": self.region_rows(prefix)}

    def unbind(self, instance: str) -> dict:
        with self._lock:
            info = self.bound.get(instance)
            if info is None:
                return {"ok": False, "error": "unknown_instance"}
            released = []
            for loop_id in info["roles"]:
                loop = self.window.loops.get(loop_id)
                if loop is not None and loop.status == "bound":
                    self.window.unbind_scope(loop_id, terminal_state="no_op")
                    released.append(loop_id)
            self.bound.pop(instance, None)
            return {"ok": True, "instance": instance, "released": released}

    # -- reads --------------------------------------------------------------
    def region_rows(self, prefix: str = "") -> list[dict]:
        rows = self.window.region_map(include_content=False)
        if prefix:
            rows = [r for r in rows if r["scw_id"].startswith(prefix)]
        return rows

    def region_detail(self, scw_id: str, as_loop: Optional[str] = None) -> dict:
        """Contents of one region, optionally *through a loop's scope*.

        `as_loop` is the point: asking as a bound role goes through the real
        authorization path, so a region outside that role's closure comes back
        as a refusal with the runtime's own hint, rather than a UI-level
        filter over content the caller was already handed.
        """
        with self._lock:
            region = self.window.regions.get(scw_id)
            if region is None:
                return {"ok": False, "error": "unknown_region", "scw_id": scw_id}
            payload = {
                "ok": True,
                "scw_id": scw_id,
                "label": region.label,
                "region_type": region.region_type,
                "policy": region.policy.to_dict(),
                "lifecycle": region.lifecycle,
                "revision": region.revision,
                "tokens": region.own_tokens,
                "entries": [
                    {"entry_id": e.entry_id, "key": e.key, "tokens": e.tokens,
                     "written_by": e.written_by, "tick": e.tick, "data": e.data}
                    for e in region.entries
                ],
            }
            if as_loop:
                try:
                    self.window.read(scw_id, loop_id=as_loop)
                except SCWError as exc:
                    detail = exc.to_dict()
                    payload["scope_check"] = {
                        "as_loop": as_loop, "allowed": False,
                        "error": detail.get("error"),
                        "message": detail.get("message"),
                        "hint": detail.get("hint"),
                    }
                    payload["entries"] = []   # honestly withheld, not styled away
                else:
                    payload["scope_check"] = {"as_loop": as_loop, "allowed": True}
            return payload

    def snapshot(self) -> dict:
        with self._lock:
            inspected = self.window.inspect()
            loops = []
            for loop_id, loop in sorted(self.window.loops.items()):
                loops.append({
                    "loop_id": loop_id,
                    "scw_id": loop.scw_id,
                    "status": loop.status,
                    "iteration": loop.iteration,
                    "max_iterations": loop.max_iterations,
                    "exposes": list(loop.exposes),
                    "read_closure": sorted(partition.read_closure(self.window, loop_id)),
                    "write_closure": sorted(partition.write_closure(self.window, loop_id)),
                })
            bridges = [
                {"bridge_id": b.bridge_id, "from": b.from_scw_id, "to": b.to_scw_id,
                 "mode": b.mode, "status": b.status, "reason": b.reason,
                 "owner": b.owner_loop_id}
                for b in self.window.bridges.values()
            ]
            return {
                "ok": True,
                "run_id": self.window.log.run_id,
                "event_log": str(EVENT_LOG),
                "regions": self.window.region_map(include_content=False),
                "loops": loops,
                "bridges": bridges,
                "cache": inspected.get("cache", {}),
                "tokens": inspected.get("tokens", {}),
                "advisories": self.window.advisories(),
                "instances": list(self.bound.values()),
                "events": len(self.window.log.records),
            }

    def containment(self) -> dict:
        """The real containment + cost report, computed by the runtime's own
        functions against the live region graph -- not simulated or asserted."""
        with self._lock:
            if not self.window.loops:
                return {"ok": False, "error": "no_loops_bound",
                        "message": "bind a loop before asking for containment"}
            report = containment_report(self.window)
            costs = cost_model(self.window)
            # Two kinds of evidence, kept apart on purpose. The report is a
            # computation over the region graph. `access_matrix` probes every
            # (role, region) pair with a REAL read through the real
            # authorization path, so each refusal it reports is an event the
            # ledger records and replay reproduces.
            #
            # `closure_disagreements` is the interesting field: any cell where
            # the computation and the attempt disagree is a defect in one of
            # them, and until now nothing in the product ever compared the two.
            probed = access_matrix(self.window)
            return {"ok": True, "containment": report, "cost": costs,
                    "probed": probed,
                    "evidence": {
                        "containment": {"pure": True,
                                        "how": "computed over the region graph"},
                        "probed": {"pure": False,
                                   "how": "a real read was attempted per cell"},
                    }}

    def trace(self, limit: int = 200, kinds: Optional[list[str]] = None) -> dict:
        with self._lock:
            records = self.window.log.records
            if kinds:
                records = [r for r in records if r["type"] in kinds]
            tail = records[-limit:]
            return {
                "ok": True,
                "total": len(self.window.log.records),
                "returned": len(tail),
                "events": [
                    {"seq": r["seq"], "ts": r["ts"], "type": r["type"],
                     "actor": r["actor"], "payload": r["payload"],
                     "digest": r["digest"][:12]}
                    for r in tail
                ],
            }

    def verify_chain(self) -> dict:
        """Real hash-chain verification -- the audit claim, actually checked."""
        with self._lock:
            try:
                self.window.log.verify()
            except Exception as exc:  # noqa: BLE001 - a broken chain is the datum
                return {"ok": False, "verified": False,
                        "error": type(exc).__name__, "message": str(exc)}
            rebuilt = replay(self.window.log.records)
            identical = (rebuilt.inspect(include_content=True)
                         == self.window.inspect(include_content=True))
            return {
                "ok": True, "verified": True,
                "events": len(self.window.log.records),
                "replay_identical": identical,
                "run_id": self.window.log.run_id,
            }

    # -- creating (the mission-control dispatch surface) ---------------------
    def create_scw(self, label: str, region_type: str = "working",
                   policy: Optional[dict] = None,
                   parent_scw_id: Optional[str] = None) -> dict:
        with self._lock:
            try:
                region = self.window.create_scw(
                    label=label, region_type=region_type, policy=policy,
                    parent_scw_id=parent_scw_id, loop_id=None)
            except SCWError as exc:
                return {"ok": False, **exc.to_dict()}
            return {"ok": True, "scw_id": region.scw_id, "label": region.label,
                    "region_type": region.region_type,
                    "policy": region.policy.to_dict()}

    def close_scw(self, scw_id: str) -> dict:
        with self._lock:
            try:
                result = self.window.close_scw(scw_id, loop_id=None)
            except SCWError as exc:
                return {"ok": False, **exc.to_dict()}
            return {"ok": True, **result}

    # -- loop engineering ----------------------------------------------------
    # A dispatch that only writes is not a loop; it is a write with a story
    # attached. These three wrap the runtime's own loop layer so a dispatched
    # agent runs with its position in the taxonomy -- trigger, goal,
    # verification level, iteration ceiling -- declared as data in the log
    # rather than left implicit in whatever code happened to call write().
    def bind_dispatch(self, loop_id: str, scw_id: str, goal: str,
                      trigger: str = "manual",
                      verification_level: Optional[int] = None,
                      max_iterations: Optional[int] = None,
                      exposes: Optional[list] = None) -> dict:
        with self._lock:
            try:
                loop = self.window.bind_scope(
                    loop_id=loop_id, scw_id=scw_id, trigger=trigger, goal=goal,
                    verification_level=verification_level,
                    max_iterations=max_iterations, exposes=exposes)
            except (SCWError, ValueError) as exc:
                if isinstance(exc, SCWError):
                    return {"ok": False, **exc.to_dict()}
                return {"ok": False, "error": "invalid_loop_spec", "message": str(exc)}
            return {"ok": True, "loop_id": loop_id, "scw_id": loop.scw_id,
                    "trigger": trigger, "goal": goal,
                    "verification_level": verification_level,
                    "max_iterations": max_iterations}

    def unbind_dispatch(self, loop_id: str,
                        terminal_state: str = "no_op") -> dict:
        with self._lock:
            try:
                result = self.window.unbind_scope(
                    loop_id, terminal_state=terminal_state)
            except (SCWError, ValueError) as exc:
                if isinstance(exc, SCWError):
                    return {"ok": False, **exc.to_dict()}
                return {"ok": False, "error": "invalid_terminal_state",
                        "message": str(exc)}
            return {"ok": True, **result}

    # -- writing (the Studio's own authoring surface) -----------------------
    def write_region(self, scw_id: str, data: str, loop_id: Optional[str] = None,
                     key: Optional[str] = None) -> dict:
        with self._lock:
            try:
                result = self.window.write(scw_id, data, loop_id=loop_id, key=key)
            except SCWError as exc:
                return {"ok": False, **exc.to_dict()}
            return {"ok": True, **result}

    def open_bridge(self, from_scw: str, to_scw: str, mode: str,
                    reason: str, loop_id: Optional[str] = None,
                    ttl_ticks: Optional[int] = None) -> dict:
        with self._lock:
            try:
                bridge = self.window.open_bridge(
                    from_scw, to_scw, mode=mode, reason=reason,
                    ttl_ticks=ttl_ticks, loop_id=loop_id)
            except SCWError as exc:
                return {"ok": False, **exc.to_dict()}
            return {"ok": True, "bridge_id": bridge.bridge_id,
                    "from": bridge.from_scw_id, "to": bridge.to_scw_id,
                    "mode": bridge.mode}

    def tick(self, loop_id: str, note: str = "",
             verified: Optional[bool] = None,
             verified_by: Optional[str] = None) -> dict:
        with self._lock:
            try:
                return {"ok": True, **self.window.loop_tick(
                    loop_id, note=note or None,
                    verified=verified, verified_by=verified_by)}
            except SCWError as exc:
                return {"ok": False, **exc.to_dict()}


# ---------------------------------------------------------------------------
# routing: task -> concept -> loop | skill | agent
# ---------------------------------------------------------------------------

def score_concepts(task: str, knowledge: Knowledge) -> list[dict]:
    """Maxey0's own lexical tag scoring: exact word = 2.0, substring = 0.5."""
    lowered = task.lower()
    scored = []
    for concept in knowledge.concepts:
        score = 0.0
        hits = []
        for tag in concept.get("tags", []):
            tag_l = tag.lower()
            if re.search(rf"\b{re.escape(tag_l)}\b", lowered):
                score += 2.0
                hits.append(tag)
            elif tag_l in lowered:
                score += 0.5
                hits.append(tag)
        if score > 0:
            scored.append({"concept": concept["id"], "score": round(score, 2),
                           "tags_hit": hits})
    scored.sort(key=lambda x: -x["score"])
    return scored


#: Routing precedence, strongest first. A hit at one level stops the search;
#: everything below it is recorded as "not reached" rather than silently
#: dropped, because which level answered is itself the measurement.
FORMATION_PRECEDENCE = ("loop", "skill", "agent", "manual")

#: The legacy `decision` string for each formation kind, kept so callers
#: written against the pre-0.4.0 shape keep working.
_DECISION_FOR = {"loop": "loop_hit", "skill": "fallback_skill",
                 "agent": "fallback_agent", "manual": "no_match"}


def _planned_partition(record: dict) -> dict:
    """The partition binding this loop *would* create, without creating it.

    `route()` scores and reports; it does not bind. Naming the regions here
    lets a caller see the WHERE of a routing decision before committing to it,
    and lets an experiment record the decision separately from the execution
    that followed -- which is the point of treating routing as an observation.
    """
    try:
        spec = spec_from_record(record)
    except (ValueError, KeyError):
        return {"scw": None, "regions": [], "roles": [],
                "note": "this record declares no bindable roles"}
    roles = [r.role_id for r in spec.roles]
    regions: list[str] = []
    for role in spec.roles:
        regions.append(role.role_id)
        regions.extend(role.exposes)
    return {
        "scw": roles[0] if roles else None,
        "regions": regions,
        "roles": roles,
        "harness": spec.harness_id,
        "note": "region ids are unprefixed; binding assigns an instance prefix "
                "such as 'L1-'",
    }


def route(task: str, knowledge: Knowledge) -> dict:
    """Route a task to a contextual address (WHERE) and an execution formation
    (HOW), and say what the decision was made on.

    Returns both shapes. The 0.4.0 shape is `where` / `how` / `evidence`: the
    two decisions are addressable separately, so an experiment can establish
    that Maxey0 *chose* a formation independently of how the execution then
    went. The pre-0.4.0 keys (`decision`, `loop`, `skills`, `agents`,
    `concept_scores`) are still populated and mean exactly what they did.

    A miss is reported, never absorbed: `evidence.rejected_because` names why
    each precedence level did not answer, and a task that reaches `manual` is
    a gap in library coverage rather than an error.
    """
    concept_scores = score_concepts(task, knowledge)
    top = {c["concept"] for c in concept_scores[:3]}
    considered: list[dict] = []
    rejected: list[dict] = []

    def result(kind: str, where: dict, how: dict, **legacy: Any) -> dict:
        return {
            "where": where,
            "how": how,
            "evidence": {
                "precedence": _DECISION_FOR[kind],
                "formation_kind": kind,
                "levels_tried": list(
                    FORMATION_PRECEDENCE[:FORMATION_PRECEDENCE.index(kind) + 1]),
                "concept_scores": concept_scores,
                "top_concepts": sorted(top),
                "considered": considered,
                "rejected_because": rejected,
            },
            # pre-0.4.0 keys, unchanged in meaning
            "decision": _DECISION_FOR[kind],
            "concept_scores": concept_scores,
            **legacy,
        }

    # -- level 1: an existing hardened loop ---------------------------------
    if not top:
        rejected.append({"level": "loop",
                         "why": "the task matched no concept tags, so no loop "
                                "could be scored against it"})
    else:
        pool = [l for l in knowledge.loops if top & set(l.get("concept_tags", []))]
        candidates = [l for l in pool
                      if l.get("execution_mode") == "in-window"
                      and l.get("status") == "validated"]
        considered.append({"level": "loop", "concept_matched": len(pool),
                           "bindable_and_validated": len(candidates)})
        if candidates:
            candidates.sort(key=lambda l: (
                -len(top & set(l.get("concept_tags", []))),
                len(l.get("hardening", {}).get("roles", [])),
            ))
            chosen = candidates[0]
            return result(
                "loop",
                where=_planned_partition(chosen),
                how={"formation": "loop", "id": chosen["id"],
                     "title": chosen.get("title", ""),
                     "status": chosen.get("status"),
                     "execution_mode": chosen.get("execution_mode"),
                     "roles": list(chosen.get("hardening", {}).get("roles", [])),
                     "alternatives": [c["id"] for c in candidates[1:6]]},
                loop=chosen,
                alternatives=[c["id"] for c in candidates[1:6]],
            )
        rejected.append({
            "level": "loop",
            "why": (f"{len(pool)} loop(s) carry a matching concept tag, but none "
                    f"is both in-window and validated"
                    if pool else
                    "no loop carries any of this task's top concept tags"),
        })

    # -- level 2: a skill formation -----------------------------------------
    skills = []
    for skill in knowledge.skills:
        if skill["concept"] not in top:
            continue
        score = 1.0 + sum(1.0 for tag in skill.get("tags", [])
                          if tag.lower() in task.lower())
        skills.append({"skill": skill["id"], "concept": skill["concept"],
                       "title": skill.get("title", skill["id"]),
                       "score": round(score, 2)})
    skills.sort(key=lambda x: -x["score"])
    considered.append({"level": "skill", "in_top_concepts": len(skills)})
    if skills:
        return result(
            "skill",
            where={"scw": None, "regions": [], "roles": [],
                   "note": "no pre-scoped partition; a skill formation has to be "
                           "bound by hand before dispatch"},
            how={"formation": "skill", "id": skills[0]["skill"],
                 "title": skills[0]["title"],
                 "roles": [], "alternatives": [s["skill"] for s in skills[1:6]]},
            skills=skills[:8],
        )
    rejected.append({"level": "skill",
                     "why": "no skill belongs to any of this task's top concepts"})

    # -- level 3: an agent --------------------------------------------------
    words = [w for w in re.findall(r"[a-z]+", task.lower()) if len(w) > 3]
    agents = []
    for agent in knowledge.agents:
        text = f"{agent.get('specialization', '')} {agent.get('name', '')}".lower()
        score = sum(1.0 for w in words if w in text)
        if score > 0:
            agents.append({"agent": agent["registry_index"], "name": agent["name"],
                           "specialization": agent.get("specialization", ""),
                           "score": score})
    agents.sort(key=lambda x: -x["score"])
    considered.append({"level": "agent", "keyword_matched": len(agents)})
    if agents:
        return result(
            "agent",
            where={"scw": None, "regions": [], "roles": [],
                   "note": "no pre-scoped partition; give the agent its own "
                           "scratchpad plus exactly the reference it needs"},
            how={"formation": "agent", "id": agents[0]["agent"],
                 "title": agents[0]["name"], "roles": [],
                 "alternatives": [a["agent"] for a in agents[1:6]]},
            agents=agents[:8],
        )
    rejected.append({"level": "agent",
                     "why": "no agent specialization shares a keyword with the task"})

    # -- level 4: nothing covered it ----------------------------------------
    # A real gap in library coverage. Reported as such, not as an error.
    return result(
        "manual",
        where={"scw": None, "regions": [], "roles": [],
               "note": "nothing in the library covered this; the partition has "
                       "to be built by hand"},
        how={"formation": "manual", "id": None, "title": "", "roles": [],
             "alternatives": []},
        agents=[],
    )
