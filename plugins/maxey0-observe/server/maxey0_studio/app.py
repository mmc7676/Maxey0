"""The Maxey0 Studio HTTP server: a local UI over a real SCW runtime.

Standard library only -- no Flask, no build step, nothing to install. Binds to
127.0.0.1 by default and refuses to serve anything outside its own `static/`
directory, because this process exposes the contents of live context regions and
has no authentication of its own.

    python -m maxey0_studio            # http://127.0.0.1:7676
    python -m maxey0_studio --port 8080 --no-open

Every endpoint that reports on a window reads that window through the runtime's
own API, so what the UI shows and what an agent would be allowed to read are the
same computation, not two implementations that can drift apart.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import parse_qs, urlparse

if __package__ in (None, ""):  # allow `python app.py` as well as `-m`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from maxey0_studio import experiment as exp_mod  # type: ignore
    from maxey0_studio import semantic, state as st  # type: ignore
    from maxey0_studio import cross_window as cw_mod  # type: ignore
    from maxey0_studio import live_session as live_mod  # type: ignore
    from maxey0_studio import mission as mission_mod  # type: ignore
    from maxey0_studio import observability as obs_mod  # type: ignore
    from maxey0_studio import gate_view as gate_mod  # type: ignore
    from maxey0_studio import traces as traces_mod  # type: ignore
else:
    from . import experiment as exp_mod
    from . import semantic
    from . import state as st
    from . import cross_window as cw_mod
    from . import live_session as live_mod
    from . import mission as mission_mod
    from . import observability as obs_mod
    from . import gate_view as gate_mod
    from . import traces as traces_mod

STATIC = Path(__file__).resolve().parent / "static"

SESSION = st.Session()
_FIELD_CACHE: dict[str, Any] = {}
_FIELD_LOCK = threading.Lock()


def field_payload() -> dict:
    """The semantic field is a pure function of the knowledge files, so build
    it once rather than on every pan of the 3D view."""
    with _FIELD_LOCK:
        if "value" not in _FIELD_CACHE:
            _FIELD_CACHE["value"] = semantic.build_field(SESSION.knowledge)
        return _FIELD_CACHE["value"]


# ---------------------------------------------------------------------------
# route table
# ---------------------------------------------------------------------------
Handler = Callable[[dict, dict], Any]
GET_ROUTES: dict[str, Handler] = {}
POST_ROUTES: dict[str, Handler] = {}


def get(path: str) -> Callable[[Handler], Handler]:
    def wrap(fn: Handler) -> Handler:
        GET_ROUTES[path] = fn
        return fn
    return wrap


def post(path: str) -> Callable[[Handler], Handler]:
    def wrap(fn: Handler) -> Handler:
        POST_ROUTES[path] = fn
        return fn
    return wrap


class BadParam(ValueError):
    """A request parameter that is not what the route needs: a 400, not a 500."""


def _int_param(source: dict, name: str, default: int, lo: int, hi: int) -> int:
    """Read an integer parameter from a query (lists) or a JSON body, clamped.

    int() on `?limit=abc` raised ValueError, which the generic handler turned
    into a 500 with a traceback in the log. Missing, empty or zero-ish values
    keep meaning "the default", as the `or` fallbacks did before.
    """
    raw = source.get(name)
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if raw is None or raw == "" or raw is False:
        return default
    if isinstance(raw, bool):
        raise BadParam(f"{name} must be an integer")
    try:
        value = int(raw)
    except (TypeError, ValueError, OverflowError) as exc:
        raise BadParam(f"{name} must be an integer") from exc
    return max(lo, min(hi, value))


def _display_path(p: Path) -> str:
    """A source path safe to show in the UI.

    Relative to the plugin root when it lives there (the common case, and the
    one every user sees), `~`-relative when it lives under the user's home
    (the default event log), and the raw absolute path only for a developer
    override that is neither -- never a bare `C:\\Users\\...` string for a
    path this plugin already knows how to shorten.
    """
    p = Path(p)
    try:
        return str(p.relative_to(st.PLUGIN_ROOT))
    except ValueError:
        pass
    try:
        return "~/" + p.relative_to(Path.home()).as_posix()
    except ValueError:
        return str(p)


# -- knowledge ---------------------------------------------------------------
@get("/api/knowledge")
def api_knowledge(query: dict, body: dict) -> dict:
    k = SESSION.knowledge
    return {
        "ok": True,
        "counts": k.counts(),
        "concepts": k.concepts,
        "skills": [
            {"id": s["id"], "title": s.get("title", s["id"]),
             "concept": s.get("concept", ""), "tags": s.get("tags", []),
             "memory_tier": s.get("memory_tier", ""),
             "description": s.get("description", ""),
             "agents": s.get("agents", [])}
            for s in k.skills
        ],
        "agents": [
            {"registry_index": a["registry_index"], "name": a["name"],
             "slug": a.get("slug", ""), "specialization": a.get("specialization", ""),
             "provenance": a.get("provenance", ""),
             "assignments": a.get("assignments", [])}
            for a in k.agents
        ],
        "sources": {
            "maxey0_root": _display_path(st.MAXEY0_ROOT),
            "loops_json": _display_path(st.LOOPS_JSON),
            "scw_runtime": _display_path(st.SCW_SRC),
            "event_log": _display_path(st.EVENT_LOG),
        },
    }


@get("/api/loops")
def api_loops(query: dict, body: dict) -> dict:
    loops = SESSION.knowledge.loops
    concept = (query.get("concept") or [None])[0]
    status = (query.get("status") or [None])[0]
    if concept:
        loops = [l for l in loops if concept in l.get("concept_tags", [])]
    if status:
        loops = [l for l in loops if l.get("status") == status]
    return {
        "ok": True,
        "count": len(loops),
        "loops": [
            {"id": l["id"], "title": l["title"], "status": l["status"],
             "provenance": l["provenance"], "execution_mode": l.get("execution_mode"),
             "topic": l.get("topic", ""), "topology": l.get("topology", ""),
             "concept_tags": l.get("concept_tags", []),
             "skill_tags": l.get("skill_tags", []),
             "stages": len(l.get("agent_stages") or l.get("roles") or []),
             "hardening": {
                 "passed": l.get("hardening", {}).get("passed"),
                 "bound_holds": l.get("hardening", {}).get("bound_holds"),
                 "reduction_ratio": l.get("hardening", {}).get("reduction_ratio"),
                 "widest_read_closure":
                     l.get("hardening", {}).get("widest_read_closure"),
                 "negative_controls_refused":
                     l.get("hardening", {}).get("negative_controls_refused"),
             }}
            for l in loops
        ],
    }


@get("/api/loop")
def api_loop(query: dict, body: dict) -> dict:
    loop_id = (query.get("id") or [""])[0]
    record = SESSION.knowledge.loop(loop_id)
    if record is None:
        return {"ok": False, "error": "unknown_loop", "id": loop_id}
    return {"ok": True, "loop": record}


@get("/api/field")
def api_field(query: dict, body: dict) -> dict:
    return field_payload()


# -- live session (this machine's real SCW MCP activity, read off disk) -----
@get("/api/live/session")
def api_live_session(query: dict, body: dict) -> dict:
    return live_mod.read_live_session()


@get("/api/live/runs")
def api_live_runs(query: dict, body: dict) -> dict:
    limit = _int_param(query, "limit", 20, 1, 10_000)
    return live_mod.list_runs(limit=limit)


# -- the gate (what the delegated agents themselves did) ---------------------
# This is the stream the runtime's log cannot contain. `/api/observability`
# reports on the Studio's OWN window; `/api/live/session` reports the coding
# session's window structure but exposes no events. Neither can answer "what
# did the agent try to reach", because until the gate existed nothing recorded
# it. See docs/ARCHITECTURE.md.
#
# Cached on (mtime, size) following the `_FIELD_CACHE` pattern: the read is
# O(file) and a 2 s poll against a growing journal would re-parse and re-hash
# the whole thing every tick.
_GATE_CACHE: dict[str, Any] = {}
_GATE_LOCK = threading.Lock()


def _gate_records() -> dict:
    from pathlib import Path as _Path
    try:
        from gate import journal as gate_journal
    except Exception:  # noqa: BLE001 - the gate is optional; the Studio still runs
        return {"records": [], "damaged": 0, "available": False,
                "message": "the gate package is not importable from this process"}

    path = _Path(gate_journal.journal_path())
    try:
        stat = path.stat()
        stamp = (stat.st_mtime_ns, stat.st_size)
    except OSError:
        return {"records": [], "damaged": 0, "available": False,
                "path": _display_path(path),
                "message": "no gate journal on this machine yet; no agent tool call "
                           "has been intercepted"}

    with _GATE_LOCK:
        if _GATE_CACHE.get("stamp") != stamp:
            data = gate_journal.read_all(path)
            data["verify"] = gate_journal.verify(data["records"], data["damaged"])
            data["available"] = True
            _GATE_CACHE["stamp"] = stamp
            _GATE_CACHE["value"] = data
        return _GATE_CACHE["value"]


@get("/api/live/gate")
def api_live_gate(query: dict, body: dict) -> dict:
    data = _gate_records()
    if not data.get("available"):
        return {"ok": True, "available": False, "message": data.get("message"),
                "path": data.get("path")}
    kinds = query.get("kinds") or None
    loop_id = (query.get("loop_id") or [None])[0]
    tool = (query.get("tool") or [None])[0]
    since = _int_param(query, "since_seq", 0, 0, 2**53)
    limit = _int_param(query, "limit", 200, 1, 100_000)
    projected = gate_mod.project(data["records"], kinds=kinds, loop_id=loop_id,
                                 tool=tool, since_seq=since, limit=limit)
    return {
        "ok": True,
        "available": True,
        "path": data.get("path"),
        "chain": data.get("verify"),
        "damaged": data.get("damaged", 0),
        **projected,
    }


@get("/api/live/gate/roles")
def api_live_gate_roles(query: dict, body: dict) -> dict:
    data = _gate_records()
    if not data.get("available"):
        return {"ok": True, "available": False, "message": data.get("message")}
    out = gate_mod.by_role(data["records"])
    out["available"] = True
    out["summary"] = gate_mod.summary(data["records"], damaged=data.get("damaged", 0))
    out["chain"] = data.get("verify")
    return out


@get("/api/live/isolation")
def api_live_isolation(query: dict, body: dict) -> dict:
    """Which isolation level the recorded evidence supports.

    Reads the LIVE coding session's window (not the Studio's own), because the
    question is about the run whose agents the gate was watching.
    """
    from gate import levels as lv
    declared = (query.get("declared") or [None])[0]
    if declared is not None and declared not in lv.LEVELS:
        return {"ok": False, "error": "unknown_level",
                "levels": list(lv.LEVEL_NAMES)}
    data = _gate_records()
    records = data.get("records", [])
    live = live_mod.read_live_session()
    loops = (live.get("window") or {}).get("loops", []) if live.get("available") else []
    assessment = lv.assess(loops, records, declared=declared,
                           damaged=data.get("damaged", 0))
    return {"ok": True, "ladder": lv.ladder(),
            "window_available": bool(live.get("available")),
            **assessment.to_dict()}


@get("/api/live/traces")
def api_live_traces(query: dict, body: dict) -> dict:
    """The context, execution and state traces, correlated."""
    from scw_runtime.events import iter_records as _iter
    limit = _int_param(query, "limit", 200, 1, 100_000)
    data = _gate_records()
    try:
        runtime_records = list(_iter(live_mod.LIVE_LOG)) \
            if live_mod.LIVE_LOG.exists() else []
    except Exception:  # noqa: BLE001 - a torn runtime log must not 500 this view
        runtime_records = []
    return traces_mod.correlate(runtime_records, data.get("records", []), limit=limit)


# -- mission control (skill-mediated create/dispatch on the Studio's own
# standalone window -- real regions, real budgets, real-or-simulated agent
# work depending on whether an Anthropic key is configured) -----------------
@get("/api/mission/catalog")
def api_mission_catalog(query: dict, body: dict) -> dict:
    return {"ok": True, "catalog": mission_mod.catalog_from_knowledge(SESSION.knowledge)}


@get("/api/mission/config")
def api_mission_config(query: dict, body: dict) -> dict:
    from . import anthropic_client as ac
    return {"ok": True, "anthropic": ac.key_status()}


@post("/api/mission/dispatch")
def api_mission_dispatch(query: dict, body: dict) -> dict:
    return mission_mod.dispatch(
        SESSION,
        target_scw_id=body.get("target_scw_id") or None,
        new_label=body.get("label") or None,
        region_type=body.get("region_type") or "working",
        token_ceiling=_int_param(body, "token_ceiling", 8000, 1, 10_000_000),
        agent_slug=body.get("agent_slug") or "",
        agent_name=body.get("agent_name") or "",
        skill_desc=body.get("skill_desc") or "",
        prompt=body.get("prompt") or "",
        create_count=_int_param(body, "create_count", 1, 1, 1000),
    )


@post("/api/mission/close")
def api_mission_close(query: dict, body: dict) -> dict:
    return SESSION.close_scw(body.get("scw_id", ""))


@post("/api/mission/file")
def api_mission_file(query: dict, body: dict) -> dict:
    scw_id = body.get("scw_id", "")
    filename = body.get("filename", "file")
    content = body.get("content", "")
    return SESSION.write_region(scw_id, f"[file: {filename}]\n{content}", loop_id=None)


# -- live window -------------------------------------------------------------
@get("/api/window")
def api_window(query: dict, body: dict) -> dict:
    return SESSION.snapshot()


@get("/api/region")
def api_region(query: dict, body: dict) -> dict:
    scw_id = (query.get("id") or [""])[0]
    as_loop = (query.get("as_loop") or [None])[0]
    return SESSION.region_detail(scw_id, as_loop=as_loop or None)


@get("/api/trace")
def api_trace(query: dict, body: dict) -> dict:
    limit = _int_param(query, "limit", 200, 1, 100_000)
    kinds = (query.get("kinds") or [None])[0]
    return SESSION.trace(limit=limit,
                         kinds=kinds.split(",") if kinds else None)


@get("/api/containment")
def api_containment(query: dict, body: dict) -> dict:
    return SESSION.containment()


@get("/api/verify")
def api_verify(query: dict, body: dict) -> dict:
    return SESSION.verify_chain()


@get("/api/observability")
def api_observability(query: dict, body: dict) -> dict:
    """The event log as a typed stream. No filters -> a summary of the run.

    `kinds` filters by group (access, refusal, scope, bridge, utilization,
    audit, routing), not by raw event type.
    """
    kinds = (query.get("kinds") or [""])[0]
    kinds_list = [k.strip() for k in kinds.split(",") if k.strip()] or None
    loop_id = (query.get("loop_id") or [None])[0]
    scw_id = (query.get("scw_id") or [None])[0]
    since = _int_param(query, "since_seq", 0, 0, 2**53)
    limit = _int_param(query, "limit", 200, 1, 100_000)
    records = SESSION.window.log.records
    if not kinds_list and loop_id is None and scw_id is None and since == 0:
        return obs_mod.summary(records)
    return obs_mod.project(records, kinds=kinds_list, loop_id=loop_id,
                           scw_id=scw_id, since_seq=since, limit=limit)


@get("/api/observability/attempts")
def api_observability_attempts(query: dict, body: dict) -> dict:
    """Did this role attempt to reach this region, and what happened?

    `contained` is three-valued: null means nothing was attempted, which
    establishes nothing either way.
    """
    return obs_mod.attempts(
        SESSION.window.log.records,
        loop_id=(query.get("loop_id") or [None])[0],
        scw_id=(query.get("scw_id") or [None])[0])


@post("/api/route")
def api_route(query: dict, body: dict) -> dict:
    task = (body.get("task") or "").strip()
    if not task:
        return {"ok": False, "error": "empty_task"}
    return {"ok": True, **st.route(task, SESSION.knowledge)}


@post("/api/bind")
def api_bind(query: dict, body: dict) -> dict:
    return SESSION.bind_loop(body.get("loop_id", ""))


@post("/api/unbind")
def api_unbind(query: dict, body: dict) -> dict:
    return SESSION.unbind(body.get("instance", ""))


@post("/api/reset")
def api_reset(query: dict, body: dict) -> dict:
    return SESSION.reset()


@post("/api/write")
def api_write(query: dict, body: dict) -> dict:
    return SESSION.write_region(
        body.get("scw_id", ""), body.get("data", ""),
        loop_id=body.get("loop_id") or None, key=body.get("key") or None)


@post("/api/bridge")
def api_bridge(query: dict, body: dict) -> dict:
    return SESSION.open_bridge(
        body.get("from_scw", ""), body.get("to_scw", ""),
        mode=body.get("mode", "read"), reason=body.get("reason", "studio bridge"),
        loop_id=body.get("loop_id") or None, ttl_ticks=body.get("ttl_ticks"))


@post("/api/tick")
def api_tick(query: dict, body: dict) -> dict:
    return SESSION.tick(
        body.get("loop_id", ""), note=body.get("note", ""),
        verified=body.get("verified"), verified_by=body.get("verified_by"))


# -- designer ----------------------------------------------------------------
@post("/api/designer/preview")
def api_designer_preview(query: dict, body: dict) -> dict:
    """Compile a designed loop and harden it, without saving.

    The same instantiate-and-check pass the dataset build runs: if the designed
    topology cannot be built against a live window with every negative control
    refused, the designer says so instead of accepting it.
    """
    record = {
        "id": f"draft:{body.get('slug', 'untitled')}",
        "title": body.get("title", "Untitled loop"),
        "agent_stages": body.get("agent_stages", []),
        "roles": body.get("roles", []),
    }
    if not (record["agent_stages"] or record["roles"]):
        return {"ok": False, "error": "no_stages",
                "message": "a loop needs at least one agent stage"}
    try:
        spec = st.spec_from_record(record)
        ops = st.build_init_ops(spec, "scw", {})
        window = st.ContextWindow(total_budget=200_000, name="designer-preview")
        refused = 0
        expected = 0
        for op in ops:
            args = dict(op.get("args", {}))
            if op.get("expect_refusal"):
                expected += 1
                try:
                    getattr(window, op["op"])(**args)
                except st.SCWError:
                    refused += 1
                continue
            getattr(window, op["op"])(**args)
        report = st.containment_report(window)
        costs = st.cost_model(window)
    except Exception as exc:  # noqa: BLE001 - a failed build is the answer
        return {"ok": False, "error": type(exc).__name__, "message": str(exc)}

    return {
        "ok": True,
        "roles": [r.role_id for r in spec.roles],
        "regions": sorted(window.regions),
        "hardening": {
            "passed": bool(report["bound_holds"]) and refused == expected,
            "bound_holds": report["bound_holds"],
            "breaches": report["breaches"],
            "widest_read_closure": report["widest_read_closure"],
            "verdict": report["verdict"],
            "reduction_ratio": costs["totals"]["reduction_ratio"],
            "negative_controls_refused": f"{refused}/{expected}",
        },
    }


@post("/api/designer/save")
def api_designer_save(query: dict, body: dict) -> dict:
    """Persist a designed loop into a user-owned overlay dataset.

    Deliberately writes to `experiments/maxey0_example_loops.json`, never to
    the vendored `loops.json`: the shipped dataset is evidence tied to a
    build report, and a UI edit must not silently become part of it. This
    file holds worked examples of agents composed into a loop -- reference
    content, not a run's output -- which is why it lives outside the
    gitignored run-instance directories.
    """
    preview = api_designer_preview(query, body)
    if not preview.get("ok"):
        return preview

    slug = (body.get("slug") or "untitled").strip().replace(" ", "-").lower()
    record = {
        "id": f"custom:{slug}",
        "title": body.get("title", "Untitled loop"),
        "provenance": "custom",
        "source_files": ["designed in Maxey0 Studio"],
        "status": "validated" if preview["hardening"]["passed"] else "partial",
        "execution_mode": "in-window",
        "topic": body.get("topic", "custom"),
        "concept_tags": body.get("concept_tags", []),
        "skill_tags": body.get("skill_tags", []),
        "topology": "chain",
        "agent_stages": body.get("agent_stages", []),
        "hardening": {"checked": True, "method":
                      "Maxey0 Studio designer preview (real ContextWindow)",
                      **preview["hardening"]},
        "notes": body.get("notes", ""),
    }

    path = exp_mod.EXPERIMENTS_DIR / "maxey0_example_loops.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = (json.loads(path.read_text(encoding="utf-8"))
                if path.exists() else {"loops": []})
    existing["loops"] = [l for l in existing["loops"] if l["id"] != record["id"]]
    existing["loops"].append(record)
    # Saved to disk: same privacy rules as every other Studio write.
    path.write_text(json.dumps(exp_mod.redact(existing), indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")

    # Make it routable immediately, without a restart.
    SESSION.knowledge.loops = [l for l in SESSION.knowledge.loops
                               if l["id"] != record["id"]] + [record]
    return {"ok": True, "saved": record["id"], "path": _display_path(path),
            "status": record["status"], "hardening": preview["hardening"]}


# -- experiments -------------------------------------------------------------
# A generic harness over an externally defined workload spec. Nothing here
# knows what the workload is: `spec` says what to run and how to measure it,
# and `experiments/specs/README.md` documents its shape.
@get("/api/experiments")
def api_experiments(query: dict, body: dict) -> dict:
    return {"ok": True, "experiments": exp_mod.Experiment.list_all()}


def _specs_for_display() -> list[dict]:
    """The experiment spec list with every path shortened for the screen.

    `list_specs` returns absolute paths, which carry the username; the UI only
    needs to show where a spec lives, so route them through `_display_path`.
    """
    specs = exp_mod.list_specs()
    for spec in specs:
        if spec.get("path"):
            spec["path"] = _display_path(Path(spec["path"]))
    return specs


@get("/api/experiments/specs")
def api_exp_specs(query: dict, body: dict) -> dict:
    return {"ok": True, "specs": _specs_for_display()}


@post("/api/experiments/create")
def api_exp_create(query: dict, body: dict) -> dict:
    try:
        exp = exp_mod.Experiment.create(
            SESSION, spec=body.get("spec"), label=body.get("label", ""))
    except exp_mod.SpecError as exc:
        return {"ok": False, "error": "bad_spec", "message": str(exc),
                "specs": _specs_for_display()}
    result = exp.materialize(SESSION)
    return {"ok": True, "exp_id": exp.exp_id, **result, **exp.status()}


@get("/api/experiments/status")
def api_exp_status(query: dict, body: dict) -> dict:
    exp = exp_mod.Experiment.load((query.get("id") or [""])[0])
    if exp is None:
        return {"ok": False, "error": "unknown_experiment"}
    return exp.status()


@post("/api/experiments/ingest")
def api_exp_ingest(query: dict, body: dict) -> dict:
    exp = exp_mod.Experiment.load(body.get("exp_id", ""))
    if exp is None:
        return {"ok": False, "error": "unknown_experiment"}
    return exp.ingest(SESSION, body.get("call_id", ""),
                      body.get("response", ""),
                      probe_response=body.get("probe_response"))


@get("/api/experiments/report")
def api_exp_report(query: dict, body: dict) -> dict:
    exp = exp_mod.Experiment.load((query.get("id") or [""])[0])
    if exp is None:
        return {"ok": False, "error": "unknown_experiment"}
    return exp.report(SESSION)


@get("/api/experiments/probe")
def api_exp_probe(query: dict, body: dict) -> dict:
    """This run's leak probe, as its workload spec defined it."""
    exp = exp_mod.Experiment.load((query.get("id") or [""])[0])
    if exp is None:
        return {"ok": False, "error": "unknown_experiment",
                "message": "pass ?id=<exp_id>; the probe belongs to the run's "
                           "workload spec, not to the harness"}
    probe = exp.probe()
    return {"ok": True, "probe": probe["text"], "sentinel": probe["sentinel"]}


# -- cross-window runs --------------------------------------------------
# Real execution of the 5 cross-window topologies. Unlike in-window loops,
# this server cannot dispatch the model calls itself -- see cross_window.py's
# own docstring. These endpoints plan the run and take real responses back;
# commands/cross-window.md drives the actual dispatch from Claude Code.
@get("/api/crosswindow/topologies")
def api_cw_topologies(query: dict, body: dict) -> dict:
    return {"ok": True, "topologies": sorted(cw_mod.TOPOLOGY_BUILDERS)}


@get("/api/crosswindow/runs")
def api_cw_runs(query: dict, body: dict) -> dict:
    return {"ok": True, "runs": cw_mod.CrossWindowRun.list_all()}


@post("/api/crosswindow/create")
def api_cw_create(query: dict, body: dict) -> dict:
    try:
        run = cw_mod.CrossWindowRun.create(body.get("loop_id", ""))
    except ValueError as exc:
        return {"ok": False, "error": "unknown_topology", "message": str(exc)}
    return {"ok": True, "run_id": run.run_id, **run.status()}


@get("/api/crosswindow/status")
def api_cw_status(query: dict, body: dict) -> dict:
    run = cw_mod.CrossWindowRun.load((query.get("id") or [""])[0])
    if run is None:
        return {"ok": False, "error": "unknown_run"}
    return run.status()


@post("/api/crosswindow/ingest")
def api_cw_ingest(query: dict, body: dict) -> dict:
    run = cw_mod.CrossWindowRun.load(body.get("run_id", ""))
    if run is None:
        return {"ok": False, "error": "unknown_run"}
    return run.ingest(body.get("call_id", ""), body.get("response", ""))


@get("/api/crosswindow/report")
def api_cw_report(query: dict, body: dict) -> dict:
    run = cw_mod.CrossWindowRun.load((query.get("id") or [""])[0])
    if run is None:
        return {"ok": False, "error": "unknown_run"}
    return run.report()


# ---------------------------------------------------------------------------
# HTTP plumbing
# ---------------------------------------------------------------------------
# Host names that always mean "this machine". The port is not compared: the
# Vite dev server proxies /api with its own Host port, and a rebinding attack
# is defeated by the name alone.
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class StudioHandler(BaseHTTPRequestHandler):
    server_version = "Maxey0Studio/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:  # quieter console
        if os.environ.get("MAXEY0_STUDIO_VERBOSE"):
            super().log_message(fmt, *args)

    def handle_one_request(self) -> None:  # noqa: D102
        # A browser navigating away mid-response aborts the socket, which on
        # Windows surfaces as ConnectionAbortedError and on POSIX as a broken
        # pipe. That is the client's normal behavior, not a server fault, so it
        # gets closed quietly instead of dumping a traceback per tab close.
        try:
            super().handle_one_request()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            self.close_connection = True

    # -- helpers ---------------------------------------------------------
    def _send_json(self, payload: Any, status: int = 200) -> None:
        raw = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _send_static(self, rel: str) -> None:
        # Resolve then confirm containment: a served path must be inside STATIC
        # no matter what the request said, since this process can read regions.
        candidate = (STATIC / rel.lstrip("/")).resolve()
        try:
            candidate.relative_to(STATIC.resolve())
        except ValueError:
            self._send_json({"ok": False, "error": "forbidden"}, 403)
            return
        # A directory resolves to its index. The optional React front end in
        # `ui/` builds to `static/app/`, and a single-page app asks for `/app/`
        # rather than `/app/index.html`. Containment was already confirmed
        # above, and this only ever appends a fixed filename.
        if candidate.is_dir():
            candidate = candidate / "index.html"
        if not candidate.is_file():
            self._send_json({"ok": False, "error": "not_found", "path": rel,
                             "hint": "the built front end lives at /app/ and is "
                                     "optional; run `npm run build` in ui/ to "
                                     "produce it"}, 404)
            return
        ctype = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
        raw = candidate.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8"
                         if ctype.startswith("text/") or ctype.endswith("javascript")
                         else ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _dispatch(self, table: dict[str, Handler], path: str,
                  query: dict, body: dict) -> bool:
        handler = table.get(path)
        if handler is None:
            return False
        try:
            self._send_json(handler(query, body))
        except BadParam as exc:
            self._send_json({"ok": False, "error": "bad_param", "message": str(exc)}, 400)
        except Exception as exc:  # noqa: BLE001 - surface it, don't hang the UI
            traceback.print_exc()
            self._send_json({"ok": False, "error": type(exc).__name__,
                             "message": str(exc)}, 500)
        return True

    # -- request guard ---------------------------------------------------
    # The Studio has no auth; its only protection is that it listens on
    # loopback. That alone does not stop a web page the user visits: a page on
    # evil.example can POST a CORS "simple request" (text/plain, no preflight)
    # to 127.0.0.1, and a DNS-rebinding page can make the browser send GETs
    # with `Host: evil.example` and read the answers. So every request must
    # name a loopback host, and every POST must be JSON (which forces a
    # preflight this server never grants) from a loopback origin, if any.
    def _host_name(self, value: str) -> str:
        value = value.strip().lower()
        if value.startswith("["):  # [::1]:7676
            return value[1:value.find("]")] if "]" in value else value
        return value.rsplit(":", 1)[0] if value.count(":") == 1 else value

    def _allowed_hosts(self) -> set[str]:
        allowed = set(_LOOPBACK_HOSTS)
        bound = str(getattr(self.server, "server_address", ("",))[0]).lower()
        # An explicit non-wildcard --host is the operator's own choice of name.
        if bound and bound not in ("0.0.0.0", "::"):
            allowed.add(bound)
        return allowed

    # A refusal is decided from the headers alone, so the request body is still
    # unread when the 403 goes out. Closing a socket with unread input sends a
    # TCP reset rather than an orderly close, and a reset that reaches the
    # client before it reads the reply discards that reply on Windows: the
    # caller sees ConnectionAbortedError instead of the refusal. Whether the
    # reset wins depends on whether the body arrived before the headers were
    # parsed, so the refusal was lost intermittently. The declared body is
    # therefore read and discarded, never parsed, before replying. Past this
    # cap it is left unread, because buffering an arbitrarily large body for a
    # request already refused costs more than a lost 403 does.
    _REFUSAL_DRAIN_LIMIT = 64 * 1024

    def _refuse(self, error: str) -> None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if 0 < length <= self._REFUSAL_DRAIN_LIMIT:
            self.rfile.read(length)
        self._send_json({"ok": False, "error": error}, 403)

    def _guard(self, post: bool) -> bool:
        """True when the request may proceed; otherwise a 403 has been sent."""
        allowed = self._allowed_hosts()
        host = self.headers.get("Host")
        if not host or self._host_name(host) not in allowed:
            self._refuse("forbidden_host")
            return False
        if not post:
            return True
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            self._refuse("json_required")
            return False
        origin = self.headers.get("Origin")
        if origin is not None:
            parsed_origin = urlparse(origin)
            if (parsed_origin.scheme not in ("http", "https")
                    or (parsed_origin.hostname or "").lower() not in allowed):
                self._refuse("forbidden_origin")
                return False
        return True

    # -- verbs -----------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        if not self._guard(post=False):
            return
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if self._dispatch(GET_ROUTES, parsed.path, query, {}):
            return
        if parsed.path in ("/", "/index.html"):
            self._send_static("index.html")
            return
        self._send_static(parsed.path)

    def do_POST(self) -> None:  # noqa: N802
        if not self._guard(post=True):
            return
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._send_json({"ok": False, "error": "bad_json"}, 400)
            return
        if not self._dispatch(POST_ROUTES, parsed.path, parse_qs(parsed.query), body):
            self._send_json({"ok": False, "error": "not_found",
                             "path": parsed.path}, 404)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Maxey0 Studio — SCW control plane")
    parser.add_argument("--port", type=int,
                        default=int(os.environ.get("MAXEY0_STUDIO_PORT", 7676)))
    parser.add_argument("--host", default="127.0.0.1",
                        help="loopback by default; this server has no auth")
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        getattr(stream, "reconfigure", lambda **_: None)(encoding="utf-8",
                                                         errors="replace")

    counts = SESSION.knowledge.counts()
    url = f"http://{args.host}:{args.port}"
    print("  Maxey0 Studio — Structured Context Windows, natively")
    print(f"  {counts['concepts']} concepts · {counts['skills']} skills · "
          f"{counts['agents']} agents · {counts['loops']} agentic loops")
    print(f"  loops by status: {counts['loops_by_status']}")
    print(f"  event log: {st.EVENT_LOG}")
    print(f"  serving {url}")

    httpd = ThreadingHTTPServer((args.host, args.port), StudioHandler)
    if not args.no_open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
