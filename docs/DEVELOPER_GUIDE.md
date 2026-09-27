# Maxey0 — Developer Guide

For somebody modifying or extending this repository. It describes what the code
does, not what it aspires to. Where a guarantee has a hole, the hole is named.

Repository: <https://github.com/mmc7676/Maxey0> · plugin name `maxey0` ·
product name **Maxey0** · Python 3.10+.

The SCW runtime core is pure standard library. The plugin's three MCP servers —
one per connector: `maxey0-context` (`server/context_server.py`, 32 tools),
`maxey0-loops` (`server/loops_server.py`, 10 tools) and `maxey0-observe`
(`server/observe_server.py`, 8 tools), declared in
`plugins/maxey0/.claude-plugin/plugin.json` — additionally need the `mcp`
package (FastMCP), which pulls `pydantic` — a compiled dependency. Nothing else
is required, and nothing is built. The tool names are declared once, in
`server/planes/catalog.py`.

The repository also carries a separate server that is not part of the plugin:
`maxey0-ss`, from the `maxey0_ss/` package (30 tools, 3 resources, surface in
`maxey0_ss/mcp_surface.py`), registered by the repository's own `.mcp.json` and
launched as the `maxey0-ss-mcp` console script. It needs `pip install -e .`;
see `docs/MCP_SERVERS.md`. This guide covers the plugin and the Studio.

---

## 1. Architecture

One process. One `Session`. One live `ContextWindow`. No build step.

`server/run_studio.py` (a wrapper, so a launch config can name one file; the
package also runs as a module through `server/maxey0_studio/__main__.py`)
starts a `ThreadingHTTPServer` from `http.server`. `server/maxey0_studio/app.py`
holds a single module-level `SESSION = st.Session()`, created at import time. That
`Session` owns exactly one `scw_runtime.ContextWindow`, constructed in
`Session._new_window()` with `total_budget=200_000`, `name="maxey0-studio"`, and
an `EventLog` writing to `SCW_EVENT_LOG` (default `~/.scw/studio.jsonl`).

The front end in `server/maxey0_studio/static/` — `index.html`, `studio.js`,
`studio.css`, `graph3d.js` — is served straight off disk by `_send_static()`.
There is no bundler, no transpile, no `node_modules`, no `npm install`. This is
deliberate and load-bearing: the install story for a Claude Code plugin is "clone
and it works", and a build step would break that on any machine without Node.
Edit the file, reload the page. `Cache-Control: no-store` is set on every
response so a reload really re-reads the file. (An optional React front end
lives in `ui/`; `npm run build` there emits `static/app/`, which is gitignored
and served at `/app/`. Nothing the default Studio serves depends on it.)

```
  browser (static/studio.js)
        |
        |  fetch("/api/...")   GET: query string    POST: JSON body
        v
  StudioHandler.do_GET / do_POST            server/maxey0_studio/app.py
        |
        |  _dispatch(GET_ROUTES | POST_ROUTES, path, query, body)
        |     miss on GET -> _send_static(path)  (containment-checked)
        v
  @get("/api/...") / @post("/api/...") handler function
        |
        v
  SESSION : state.Session                   server/maxey0_studio/state.py
        |  self._lock (RLock) around every mutation
        |  self.knowledge : Knowledge       (concepts/skills/agents/loops)
        v
  self.window : ContextWindow               server/vendor/scw_runtime/window.py
        |  _authorize() -> isolation.Scope.check()   <-- the wall
        |  _commit(type, actor, payload, apply)      <-- emit first, apply second
        v
  self.window.log : EventLog                server/vendor/scw_runtime/events.py
        |  sha256 hash chain, flushed per record
        v
  ~/.scw/studio.jsonl        (JSONL, append-only, one run per window)
```

Two properties fall out of that shape and are worth stating explicitly:

- **Every endpoint that reports on the window reads it through the runtime's own
  API.** `Session.region_detail(scw_id, as_loop=...)` calls
  `ContextWindow.read()` and reports the refusal it gets. The UI is not a second
  implementation of the access rules that could drift from the first one.
- **`_commit` writes the log record before it mutates state.** If `EventLog.emit`
  raises — full disk, revoked handle — `apply` never runs and the window is
  byte-identical to how it was found. Reversing that order would let a replay
  rebuild a window that never existed. Any new mutating method must go through
  `_commit`.

### The two-window fact

The Studio's window and the MCP server's window are **separate live windows in
separate OS processes**. `server/context_server.py` (the `maxey0-context`
connector, through `server/planes/context_plane.py`) imports
`scw_runtime.server` via `planes/bootstrap.open_runtime()`; that module keeps its
own `ContextWindow` and flushes to `~/.scw/events.jsonl`. It is the only plane
that opens a window: `maxey0-loops` holds no window state, and `maxey0-observe`
reads the ledger file instead.
Browsing the Studio does not mutate the window your Claude Code session's tool
calls act on, and never will without shared memory or a lock protocol neither
process has.

`server/maxey0_studio/live_session.py` is the honest bridge: it tails and
replays `~/.scw/events.jsonl` with the same reducer (`scw_runtime.replay`) and
returns a read-only mirror. Mission Control's "This coding session" view is that
mirror. It cannot write.

---

## 2. The enforcement model

### Regions

A region (an SCW) is an addressable, typed slice of the window:
`scw_runtime.model.Region`. Regions nest (`parent_id` / `children`), carry
`entries` (and `history` when versioned), a `lifecycle` of `open` / `sealed` /
`purged`, a monotonically increasing `revision`, and an `order` that decides
render position.

Default order is `TYPE_ORDER[region_type] * 1000 + len(siblings)`:

| type | `TYPE_ORDER` |
|---|---|
| `reference` | 10 |
| `durable` | 20 |
| `episodic` | 30 |
| `working` | 40 |
| `scratchpad` | 50 |

The ordering is not cosmetic. Prompt caches are prefix caches, so anything that
mutates invalidates every token after it. Read-only and durable tiers first,
volatile scratchpad last, is the cache-optimal default; an explicit `order` that
breaks it produces an advisory from `cache.ordering_advisories`.

### The five preset policies

Built from `PRESETS` in `server/vendor/scw_runtime/model.py`. `Policy` field
defaults, when a preset does not override them, are `mutability="durable"`,
`eviction="fifo"`, `token_budget=None`, `purge_on_close=False`,
`bridgeable=True`, `versioned=False`, `reset_each_tick=False`, `cache="auto"`.

| region type | mutability | eviction | token_budget | bridgeable | versioned | reset_each_tick | purge_on_close | cache |
|---|---|---|---|---|---|---|---|---|
| `reference` | `readonly` | `reject` | — | yes | yes | no | no | `always` |
| `durable` | `durable` | `lru` | — | yes | yes | no | no | `auto` |
| `episodic` | `durable` | `fifo` | — | yes | yes | no | no | `auto` |
| `working` | `durable` | `fifo` | — | **no** | no | no | no | `auto` |
| `scratchpad` | `volatile` | `fifo` | **2048** | **no** | no | **yes** | **yes** | `auto` |

Reading the table:

- `readonly` rejects every write from a bound loop. Only the unbound host may
  seed a `reference` region — which is what makes an acceptance criterion held
  there worth pinning.
- `eviction="reject"` means *refuse the write*, not *drop the oldest*.
  `write()` and `promote()` both pre-check via `_would_exceed()` before
  mutating, and `_enforce_budget()` returns early rather than falling through to
  FIFO. A refusal under `reject` leaves the region untouched.
- `bridgeable=False` means no grant can ever be minted into this region, by
  anyone. It also survives nesting: `partition.grant_visible_subtree()` stops
  descent at any non-bridgeable region, so reading a bridgeable parent through a
  grant does not leak a walled child. The elided children are recorded as a
  `scw.denied` event — a pruned read is a refusal in miniature.
- `reset_each_tick` is what makes a scratchpad a scratchpad rather than an
  accumulator: `context_scope_tick` clears every such region in the ticking loop's scope.
- Any field can be overridden per region via `preset_for(region_type, overrides)`
  — that is the `policy=` argument to `context_region_create`. Mission Control uses
  `{"token_budget": N, "eviction": "reject"}` to get a hard ceiling.

### Scope binding

`context_scope_bind(loop_id, scw_id, descend=True, ...)` binds a loop's execution scope
to exactly one region. From then until `context_scope_unbind`, every call carrying that
`loop_id` resolves against that region (plus its subtree when `descend`) and is
refused anywhere else. `isolation.resolve_scope()` builds the `Scope`;
`Scope.check(op, scw_id)` decides, returning a `Decision` with `via` set to
`"scope"`, `"descend"`, `"orchestrator"`, or a bridge id.

`context_scope_bind` is also where a loop's specification becomes data rather than prose:
`trigger`, `goal`, `verification_level` (the 1–5 ladder in
`VERIFICATION_LADDER`), `prompt_id`, `harness_id`, `exposes`, `criterion_id`,
`parent_loop_id`. The runtime then holds the declaration to account — see
`ContextWindow.advisories()` for `verification.overclaimed`,
`verification.self_approving`, `loop.stalled`.

Two things that are enforced, not advised:

- `context_scope_unbind(terminal_state="success")` is **refused** if the loop recorded
  zero accepted iterations. An error or an exhausted budget is never a success.
- `exposes` is monotonically non-widening, keyed on **both** the loop id and the
  scope root region. Keying it only on the loop id let `bind("maker2", R,
  exposes=[...])` reset the ceiling with a fresh name. The ceiling is consulted
  and moved only for bindings whose harness declares
  `verification_policy="disjoint"`.

### Read closure, write closure

`server/vendor/scw_runtime/partition.py`. `Scope.check` answers one question at a
time; the closures answer the set question.

- **read_closure(loop)** — bound region, its subtree if `descend`, and for each
  open read-granting bridge whose source it holds, that bridge's target plus
  `grant_visible_subtree(target)`.
- **write_closure(loop)** — the same reachable set minus anything `readonly` or
  not `open`, plus write-granting bridge targets. Note the asymmetry: a read
  grant exposes a subtree, a write grant exposes exactly one region, because that
  is what `Scope.check` allows and the closure must not claim more.
- `loop_id=None` (the unbound host) reaches everything. That is exactly why
  `strict_scope` and `seal()` exist.

`disjointness(window, maker_id, judge_id)` is pure and side-effect free, so an
operator can ask "would this verdict be accepted?" before running the iteration.
Five rules, weakest first:

| rule | what it catches |
|---|---|
| `R1.identity` | judge is absent, is the maker, or does not resolve to a bound loop |
| `R2.control_flow` | judge is a sub-loop of the maker, or vice versa |
| `R3.distinct_root` | both loops bound to the same region — one context, two names |
| `R4.exposure` | `judge_reads & maker_writes` minus the maker's declared `exposes` is non-empty |
| `R5.criterion` | the maker can write the region holding the criterion it is graded against |

Under a harness with `verification_policy="disjoint"`, a failing report makes
`context_scope_tick(verified=True)` raise `DisjointnessViolation`, and the whole decision
— pass or fail — lands in the log as one `partition.check` record.

### Bridges

`context_bridge_open(from_scw_id, to_scw_id, mode, reason, ttl_ticks, loop_id)` is the
only legitimate hole in a wall. Both endpoints must be `open`; the target must
declare `bridgeable=True`; a `write`/`read_write` bridge into a `readonly` region
is refused. `ttl_ticks` is measured in **the owner's** iterations —
`_expire_bridges` skips bridges owned by a different loop, so loop A's tick
cannot revoke loop B's grant. Host-minted grants (no owner) expire on the global
tick. `context_bridge_close` refuses a bound loop that neither minted the bridge nor
holds its source region; without that check, any loop could revoke any other
loop's grants mid-iteration. Closing a region revokes every bridge touching it.

### Why a bound loop cannot create a top-level region

In `context_region_create`, when `parent_scw_id is None`, the code resolves the caller's
scope and refuses if `scope.loop_id is not None`:

> "a bound loop cannot create top-level regions; nest under its scope instead"

The reason is structural. A loop that can add siblings escapes its partition by
construction: it creates a region outside anybody's closure, writes into it, and
the write closure the disjointness proof was computed over no longer describes
what the loop can reach. Nesting under its own scope keeps the new region inside
the parent's closure, where the proof still holds. The refusal is logged as
`scw.denied` and raised as `IsolationViolation`.

The same reasoning drives the neighboring host-only rules: `context_prompt_create` /
`context_prompt_revise` refuse any `loop_id` at all (no bridge could ever legalize an
agent rewriting its own instructions), and `context_criterion_pin` / `context_criterion_repin`
(and the runtime's `ContextWindow.unpin_criterion`, which has no MCP tool) do the
same for the yardstick.

---

## 3. The event log

`server/vendor/scw_runtime/events.py`. One JSON object per line, UTF-8, no
trailing commas:

```json
{"seq": 7, "ts": 1761350400.0, "run_id": "run-...", "type": "scw.write",
 "actor": "loop:refine", "payload": {...}, "prev": "<sha256>", "digest": "<sha256>"}
```

- `digest = sha256(canonical_json(record_without_digest))`, where `canonical` is
  `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`.
- `prev` is the previous record's digest. The first record of a run carries
  `GENESIS` = 64 zeros.
- `seq` is contiguous from 0 **within a run**.
- `EVENT_TYPES` is an explicit tuple. `emit()` raises on an unknown type, so the
  UI, the docs and the reducer cannot silently disagree. Adding an event kind
  means adding it there and handling it in `replay.replay()`.
- Every record is flushed immediately, which is what keeps `tail -f` and the live
  mirror honest.

### Per-run chains

A single file holds many runs — `context_window_reset` appends a new one, and the default
log path is one file shared by every session on the machine. The chain restarts
at `GENESIS` with `seq` 0 whenever `run_id` changes, so a multi-run file still
verifies. `replay.split_runs()` partitions a record list by `run_id` in file
order; `replay()` folds the **last** run by default (folding several together
used to produce duplicated roots and double-counted tokens while
`verify_records` still passed).

### What `verify_records(strict_runs=True)` closes, and the one residue it cannot

Default `verify_records(records)` detects, **within a run**, any edit, deletion,
or reorder. Across runs it detects nothing: each run's chain is independent, so
deleting a whole run or reordering runs leaves every remaining block valid.

`strict_runs=True` closes that. Every run after the first must begin with
`window.init` carrying a `prev_run` back-link — `{run_id, digest, length}` from
`EventLog.head()` of the preceding run — and the link is checked against what was
actually just read. A deleted, reordered, or truncated interior run breaks it.

**The residue:** truncating the *last* run, or dropping it entirely, leaves a
wholly consistent prefix, because nothing later refers back to it. This is not
closable from inside the file. Detecting it requires a commitment kept somewhere
the file cannot reach — record `EventLog.head()` externally at the end of a run.
Say this plainly in any paper text; do not soften it.

`Session.verify_chain()` (`POST`-free, `GET /api/verify`) runs
`window.log.verify()` and then `replay(records)`, comparing
`rebuilt.inspect(include_content=True)` against the live window's. `replay_identical`
in that payload is the claim that the log is a complete description rather than a
commentary on one.

---

## 4. HTTP endpoints

Built from the `@get` / `@post` decorators in
`server/maxey0_studio/app.py`. 28 GET routes, 16 POST routes. Anything not in
`GET_ROUTES` falls through to `_send_static`, which resolves the path and then
confirms it is inside `static/` before serving; `/` and `/index.html` serve
`index.html`.

### GET

| path | purpose |
|---|---|
| `/api/knowledge` | counts, concepts, skills, agents, and the resolved source paths |
| `/api/loops` | loop catalog; optional `?concept=` and `?status=` filters |
| `/api/loop` | one loop record by `?id=` |
| `/api/field` | the 3D semantic field, built once and cached in `_FIELD_CACHE` |
| `/api/live/session` | read-only replay of this machine's real SCW MCP log |
| `/api/live/runs` | runs present in that log, most recent first (`?limit=`) |
| `/api/live/gate` | the Gate journal's intercepted calls, with chain verification (`?kinds=`, `?loop_id=`, `?tool=`, `?since_seq=`, `?limit=`) |
| `/api/live/gate/roles` | the Gate journal grouped per role, plus a summary and chain verification |
| `/api/live/isolation` | which isolation level the evidence supports, over the coding session's window (`?declared=`) |
| `/api/live/traces` | the runtime ledger and the Gate journal, correlated (`?limit=`) |
| `/api/mission/catalog` | concept → skill → agent tree for Mission Control |
| `/api/mission/config` | whether an Anthropic key is configured, and the model id |
| `/api/window` | `Session.snapshot()` — regions, loops with closures, bridges, cache, advisories |
| `/api/region` | one region's contents; `?as_loop=` runs the real authorization path |
| `/api/trace` | tail of the event log (`?limit=`, `?kinds=a,b`) |
| `/api/containment` | `loopkit.containment_report` + `cost_model` over the live graph |
| `/api/verify` | hash-chain verification plus replay-identity check |
| `/api/observability` | the Studio window's log as a typed stream: a run summary unfiltered, else events by `?kinds=`, `?loop_id=`, `?scw_id=`, `?since_seq=`, `?limit=` |
| `/api/observability/attempts` | did `?loop_id=` attempt `?scw_id=`, and what happened (`contained` is three-valued) |
| `/api/experiments` | every experiment run on disk |
| `/api/experiments/specs` | the workload specs in `experiments/specs/` |
| `/api/experiments/status` | one run by `?id=` |
| `/api/experiments/report` | that run's report |
| `/api/experiments/probe` | that run's leak probe by `?id=`, from its spec |
| `/api/crosswindow/topologies` | the topology builder names |
| `/api/crosswindow/runs` | every cross-window run on disk |
| `/api/crosswindow/status` | one run by `?id=` |
| `/api/crosswindow/report` | that run's leak report |

### POST

| path | purpose |
|---|---|
| `/api/mission/dispatch` | create real region(s) with an enforced budget and dispatch an agent |
| `/api/mission/close` | `context_region_close` on the Studio's window |
| `/api/mission/file` | drag-and-drop ingest: writes `[file: name]\n<content>` into a region |
| `/api/route` | score a task against the concept graph → loop / skill / agent |
| `/api/bind` | build a dataset loop's regions, harness and roles |
| `/api/unbind` | release every role of a bound instance (`terminal_state="no_op"`) |
| `/api/reset` | tear down the window, start a fresh run, return the previous `head()` |
| `/api/write` | `ContextWindow.write` (optionally as a loop, optionally keyed) |
| `/api/bridge` | `context_bridge_open` |
| `/api/tick` | `context_scope_tick` with optional `verified` / `verified_by` |
| `/api/designer/preview` | compile a designed loop and harden it against a live window, without saving |
| `/api/designer/save` | persist a designed loop into the overlay dataset (preview must pass first) |
| `/api/experiments/create` | create and materialize a run from `{"spec": …}` |
| `/api/experiments/ingest` | take a real response back into a run |
| `/api/crosswindow/create` | plan a cross-window run for one of the topologies |
| `/api/crosswindow/ingest` | take one participant's real response back |

Every request passes `_guard` first: the `Host` header must name a loopback
address (or the explicit `--host`), and a POST must be `application/json` from a
loopback `Origin`, if any — otherwise HTTP 403. `_dispatch` then turns a
`BadParam` into HTTP 400 (`bad_param`), and catches every other exception, prints
the traceback to the console, and returns
`{"ok": false, "error": <type>, "message": <str>}` with HTTP 500 rather than
hanging the UI. Handlers that talk to the runtime generally catch `SCWError`
themselves and return `{"ok": false, **exc.to_dict()}` so the refusal — including
its `hint` — reaches the browser intact.

---

## 5. How to add things

### A new endpoint

```python
@get("/api/thing")
def api_thing(query: dict, body: dict) -> dict:
    return {"ok": True, "thing": SESSION.thing()}
```

Both tables map an exact path string to `Callable[[query, body], Any]`. `query`
is `parse_qs` output (so values are lists — `(query.get("id") or [""])[0]` is the
house idiom); `body` is the parsed JSON object for POST, `{}` for GET. Return a
JSON-serializable dict; `_send_json` handles the rest with
`default=str`. Put runtime work behind a `Session` method so it takes the lock,
rather than touching `SESSION.window` from the handler.

### A new app tab

1. Add a button to `<nav class="tabs" id="tabs">` in `static/index.html` with a
   `data-view="yourview"`.
2. Add `<section class="view hidden" data-view="yourview">…</section>` in
   `<main id="main">`.
3. In `static/studio.js`, the tab handler at the top toggles `.hidden` on
   sections by `data-view` automatically. Add a lazy initializer to the same
   handler if the view needs to fetch on first show — that is what
   `initSemantic()`, `refreshWindow()`, `refreshEvidence()`, `initMission()`
   and `initGate()` do.
4. Add the view to `VIEWS` in `server/planes/catalog.py`, in navigation order.
   `tests/test_studio.py` compares the nav, the sections and that table;
   `scripts/check_lexicon.py` holds every other list of views to it; and
   `scripts/generate_ui_types.py` must be re-run so `ui/src/generated/catalog.ts`
   matches.

House rule for anything you render: when the runtime refuses something, show the
refusal, its reason and its hint. Never render an empty panel — "you cannot read
this" and "this is empty" are different facts, and conflating them
misrepresents the exact thing the app exists to demonstrate.

### A new slash command

Drop a Markdown file in `commands/`. It becomes `/maxey0:<filename>` in the
full-stack plugin, and `/maxey0-<plane>:<filename>` in the standalone plugin of
the plane that owns it. The file must start with YAML frontmatter containing a
`description:` (this is checked by `scripts/validate_plugin.py`) and an
`allowed-tools:` line whose `mcp__<connector>__<tool>` entries name real catalog
tools on the right connector; `argument-hint:` is optional and shows in the
picker. `$ARGUMENTS` interpolates what the user typed. Declare the command in
`COMMANDS` in `server/planes/catalog.py` with its plane — `scripts/check_lexicon.py`
fails on a command file the catalog does not declare, and on a declared command
with no file — then run `python scripts/build_planes.py` to copy it into
`plugins/`. Existing commands: `menu.md`, `doctor.md`, `window.md`, `route.md`,
`run.md`, `crosswindow.md`, `gate.md`, `assert.md`, `studio.md`,
`scw-deploy.md`. The lab command is not in `commands/`: its source is
`plugins/_lab/experiment-run.md`, which `build_planes.py` copies into the
`maxey0-lab` plugin, where it is exposed as `/maxey0-lab:experiment-run`.

### A new skill

Create `skills/<name>/SKILL.md` with frontmatter carrying `name:` and
`description:`. The description is the trigger surface — write it as "use
when…", naming the words a user would actually type.

`skills/` currently holds 18 directories: `scw/`, `scw-default-deployer/` (the
skill `agents/scw-deployer.md` names), and one skill per Maxey0 concept (16).
`validate_plugin.py` asserts exactly that count, and that every skill directory
bundles reference material beyond its `SKILL.md`, so adding a nineteenth means
updating the assertion in `scripts/validate_plugin.py` in the same commit. The concept stubs are generated
by `scripts/generate_concept_skills.py`; regenerate rather than hand-editing
them, and keep them as pointers — they route to the real material through
`loops_route` / `context_route_bind`, they do not duplicate it.

### A new agentic loop

A loop record lives in a `loops.json`-shaped document. The keys the code actually
reads are:

`id`, `title`, `provenance`, `status`, `execution_mode`, `topic`,
`concept_tags`, `skill_tags`, `topology`, `agent_stages` (or `roles`),
`hardening`, `notes`, `source_validation`.

`state.spec_from_record()` compiles it into a `HarnessSpec`. Pipeline records use
`agent_stages` — an ordered list of `{agent_id, agent_name}` — and each stage
becomes a `RoleDef` with `role_id = f"stage{i}-{agent_id.lower()}"`, reading only
from the previous stage and exposing `{role_id}-out`. Battery/formation records
name `roles` directly and are chained the same way.

**Use the designer, and understand its gate.** `POST /api/designer/preview` runs
the real thing:

1. `spec_from_record(record)` → `HarnessSpec`.
2. `d4.harness_dsl.build_init_ops(spec, "scw", {})` → the op list: one
   `reference` region per resource, one `durable` region per declared exposure,
   one `scratchpad` pad per role, `context_scope_bind` per role, then grants — plus, for
   **every ordered pair of distinct roles**, a `context_bridge_open` marked
   `expect_refusal: True` attempting to read the other role's private pad.
3. Every op is executed against a fresh `ContextWindow(total_budget=200_000)`.
   Ops marked `expect_refusal` must raise `SCWError`; ops not so marked must
   succeed.
4. `loopkit.containment_report(window)` and `cost_model(window)` are computed.

The gate: `hardening.passed = bool(report["bound_holds"]) and refused == expected`.
Pad privacy is a universal invariant in this DSL — a role immediately upstream in
the topology must *still* be refused a direct read of another role's raw pad,
because `reads_from` only ever grants access to declared `exposes` regions. Do
not exempt connected pairs from the negative controls; that would stop testing
the one invariant the whole partition design rests on.

`POST /api/designer/save` re-runs the preview and refuses to save if the build
itself fails; a loop that builds but fails hardening is stored with
`status: "partial"`, not `"validated"`. It writes
to `experiments/maxey0_example_loops.json` — a tracked, user-owned overlay —
**never** to the vendored `server/vendor/data/loops.json`, because the shipped
dataset is evidence tied to a build report and a UI edit must not silently join
it. The saved record is spliced into `SESSION.knowledge.loops` immediately, so it
is routable without a restart.

Note also `state._apply_cross_window_evidence()`: a `designer:*` loop's status is
promoted to `validated` only when a real run's own report file in
`experiments/cross-window/*.report.json` says `complete` **and** `bound_holds`.
That is computed fresh on every load and is never hand-set in `loops.json`. This
is why the count is **78 validated**, not 79: a previous build shipped someone
else's cross-window report, and that borrowed evidence was removed on purpose. It
returns to 79 when a real cross-window run is executed with this codebase and
writes its own report.

---

## 6. Testing

Three layers, and they prove different things.

**The runtime's unit suite lives upstream**, in the `scw-runtime` engineering
checkout (`scw-runtime/tests/`), not in this repository. `server/vendor/` carries
only the importable runtime, not its tests. The upstream files are
`test_attestation.py`, `test_cache.py`, `test_ceilings.py`, `test_chain_runs.py`,
`test_criterion.py`, `test_durability.py`, `test_events.py`, `test_formation.py`,
`test_harness.py`, `test_isolation.py`, `test_loop_spec.py`, `test_loops.py`,
`test_nesting.py`, `test_observability.py`, `test_partition.py`, `test_policy.py`,
`test_prompt.py`, `test_repairs.py`, `test_replay.py`, `test_server.py`. Run them
from that checkout with `pytest`. If you change vendored runtime code, change it
upstream, run those tests there, then re-vendor (§7) — never patch
`server/vendor/` in place.

**This repository's own suite** is collected from `tests/` and `maxey0_ss/tests/`
(the `testpaths` in `pyproject.toml`):

```
python -m pytest -q
```

It covers the vendored runtime's behavior as shipped (`tests/test_scw_runtime.py`),
the three planes, the Gate, the Studio, packaging, privacy, and the rules that keep
the surface consistent: `tests/test_ontology.py` (one spelling per name),
`tests/test_documented_counts.py` (the counts written in `docs/VERIFICATION.md`),
and `tests/test_version.py` (one version everywhere).

**The third layer is an end-to-end gate:**

```
python scripts/validate_plugin.py
```

Exit 0 means installable. It checks, in the order things break:

1. `.claude-plugin/marketplace.json` exists and parses. The repository root is
   the marketplace only; `plugins/maxey0/.claude-plugin/plugin.json` exists,
   parses, has `name`/`version`/`description`, and every
   `${CLAUDE_PLUGIN_ROOT}`-relative MCP entry point and env path resolves to a
   file that exists.
2. `commands/`, `agents/`, `skills/scw/SKILL.md`, `hooks/hooks.json`,
   `README.md` exist; every command has frontmatter with a description; every
   agent declares `name` + `description`; `skills/` has exactly 18 directories
   each with a `SKILL.md` and bundled reference material; every hook script
   named by a hook resolves. Then four generators and checkers run with
   `--check` or as-is: `generate_concept_skills.py`, `build_planes.py` (the
   `plugins/` directories match the root), `check_lexicon.py`, and
   `generate_ui_types.py`.
3. `scripts/sync_vendor.py --check` (exit 2 = upstream absent, downgraded to a
   note; exit 1 = real drift, a failure).
4. In a clean subprocess: the three connectors build 32, 10 and 8 tools; the
   Loop plane opens no ledger; the runtime loads from `server/vendor/`; the
   Desktop bundle (`server/mcpb_entry.py`) unions the planes into 47 tools;
   the Studio app imports; and the semantic field builds with more than 100
   nodes.
5. **Enforcement.** It binds a validated in-window loop with
   at least three stages, then asserts: negative controls were refused (`> 0`), a
   role can read its own pad, a role is **refused** another role's pad, the hash
   chain verifies, and the log replays to an identical window.
6. **The leak checker is checked both ways.** A clean 4-way cross-window run must
   report `bound_holds=true` with zero leaks; a second run with a deliberately
   injected leak — maker 1's response pasted into maker 2's prompt before
   dispatch — must report `bound_holds=false` with leaks found. Both probe runs
   are deleted afterwards, because unlike a real run they carry no evidence worth
   keeping.

Steps 5 and 6 are what unit tests cannot do here. A unit test asserts a function
returns a refusal; `validate_plugin.py` builds an actual loop out of the shipped
dataset, in the shipped process, through the shipped `Session`, and **gets
refused**. And it proves the leak detector is not a function that only ever
returns "clean" — it constructs a leak and requires it to be caught.

---

## 7. The vendoring rule

**`server/vendor/` is generated. Never hand-edit it.**

```
python scripts/sync_vendor.py            # re-vendor
python scripts/sync_vendor.py --check    # drift gate; non-zero if stale
```

`PLAN` in `scripts/sync_vendor.py` is the whole contract — source path,
destination relative to `server/vendor/`, and whether it is a `tree` or a `file`:

| source | vendored as |
|---|---|
| `scw-runtime/src/scw_runtime` | `scw_runtime/` (tree) |
| `scw-runtime/loops/d4/harness_dsl.py` | `d4/harness_dsl.py` |
| `scw-runtime/loops/d4/compositions.py` | `d4/compositions.py` |
| `scw-runtime/loops/lib/harness_kit.py` | `loopkit/harness_kit.py` |
| `scw-runtime/loops/dataset/loops.json` | `data/loops.json` |
| `Maxey0/Maxey0/manifest.json` | `maxey0/manifest.json` |
| `Maxey0/Maxey0/registry/registry.json` | `maxey0/registry.json` |
| `Maxey0/Maxey0/data/team_mapping.csv` | `maxey0/team_mapping.csv` |
| `Maxey0/Maxey0/data/maxey0_subagents.csv` | `maxey0/maxey0_subagents.csv` |
| `Maxey0/Maxey0/data/anchors.json` | `maxey0/anchors.json` |
| `Maxey0/Maxey0/data/complexity-map.json` | `maxey0/complexity-map.json` |

A full sync also writes `server/vendor/VENDOR.json` with a SHA-256 per entry
(directories hashed over sorted relative paths plus bytes, skipping
`__pycache__` and `*.pyc`), and creates `__init__.py` for `d4` and `loopkit`
because they are imported as packages.

Each plugin under `plugins/` carries its own complete copy of `server/`, so after
re-vendoring (or any change under `server/`, `commands/`, `agents/`, `hooks/` or
`skills/`) run `python scripts/build_planes.py`. `validate_plugin.py` fails while
`build_planes.py --check` reports drift.

`--check` recomputes those digests and exits **1** on drift, **0** on match, and
**2** when the upstream source paths are absent — which is the normal case on a
standalone install, and is why `validate_plugin.py` downgrades exit 2 to a note
instead of a failure.

Runtime override, for a developer who *does* have the engineering checkout:
`SCW_RUNTIME_SRC`, `MAXEY0_ROOT`, `MAXEY0_LOOPS` (resolved in
`state._resolve()`, which falls back loudly to the vendored copy and prints to
stderr if the override does not contain the expected marker file).

Other environment overrides: `SCW_EVENT_LOG`, `SCW_HOME`, `MAXEY0_STUDIO_PORT`,
`MAXEY0_STUDIO_VERBOSE`, `ANTHROPIC_API_KEY`, `MAXEY0_MODEL`, and the Gate's
`MAXEY0_GATE_MODE`, `MAXEY0_GATE_LOG`, `MAXEY0_GATE_STATE`,
`MAXEY0_GATE_POLICY` and `MAXEY0_GATE_SESSION` (see `docs/CONNECTORS.md`).

---

## 8. Release

The version is currently `0.3.2`. The one literal is `__version__` in
`maxey0_ss/__init__.py`, and `tests/test_version.py` requires every other
declaration to agree with it:

- `pyproject.toml` → `version`
- `.claude-plugin/marketplace.json` → `"metadata"."version"` — the anchor
  `scripts/build_planes.py` writes into every generated
  `plugins/*/.claude-plugin/plugin.json`
- `manifest.json` (the `.mcpb` bundle manifest) → `"version"`
- `server/maxey0_studio/__init__.py` → `__version__`
- every `package.json` (and `package-lock.json`) outside `plugins/`
- `workers/mcp-edge/src/generated/surface.json` → re-run
  `scripts/export_mcp_surface.py`

Keep them identical — a marketplace descriptor that disagrees with the plugin
manifest is the failure mode that only shows up on somebody else's machine, and
`scripts/build_package.py` refuses to build when they disagree.

Order of operations:

1. Bump the version everywhere it appears, then run
   `python scripts/build_planes.py` so the generated plugin manifests follow.
2. Re-vendor if the runtime or knowledge base changed: `python
   scripts/sync_vendor.py`, and commit the result as a separate, reviewable diff.
3. Run the upstream runtime tests in the `scw-runtime` checkout.
4. `python scripts/validate_plugin.py` — must exit 0, with no `FAIL` lines.
5. Build the distributable with `scripts/build_package.py`.
6. Confirm nothing gitignored got swept in: `experiments/exp-*/` and
   `experiments/cross-window/*.json` are real run output produced by executing
   this software, not something it ships with. Two things under `experiments/`
   *are* tracked and belong in a package: `maxey0_example_loops.json` (worked
   examples of composed loops) and `specs/` (workload specs for the experiment
   harness). `.env` must never enter a package.

---

## 9. Extending Mission Control, and where the LLM boundary sits

`server/maxey0_studio/mission.py` is small on purpose. Two functions matter.

`catalog_from_knowledge(knowledge)` builds concept → skill → agent from the same
in-memory `Knowledge` every other tab reads. There is no separate seed data. If
you add a concept or a skill, it appears here without touching this file.

`dispatch(session, *, target_scw_id, new_label, region_type, token_ceiling,
agent_slug, agent_name, skill_desc, prompt, create_count)` does three things:

1. If no `target_scw_id`, it calls `Session.create_scw` `create_count` times with
   `policy={"token_budget": token_ceiling, "eviction": "reject"}`. These are real
   `scw_runtime.Region`s on the Studio's real window with a real, enforced hard
   ceiling. No prompt means `mode: "create_only"` and it stops there.
2. Otherwise it makes the dispatch a loop rather than a host write: it creates a
   `scratchpad` region, `<target>-pad`, nested under the target, and binds the
   loop `dispatch:<target>` to the target through `Session.bind_dispatch`, which
   declares `trigger="manual"`, a goal, a verification level (4 for a real call,
   none for a simulation) and an iteration ceiling.
3. It then starts a daemon thread running `_run_loop(..., real_call=...)` —
   `real_call` is `anthropic_client.is_configured()` — and returns
   `mode: "real_api"` or `"simulated"` immediately, so the HTTP request does not
   block on a model call. `_run_loop` writes every step with the bound
   `loop_id`, ticks once per step, and always ends in
   `Session.unbind_dispatch` with `success` (a verification was accepted),
   `blocked` (a refusal or an API error) or `no_op`.

**The LLM boundary is exactly one function:** `anthropic_client.complete(system,
user, max_tokens, model)` in `server/maxey0_studio/anthropic_client.py`. It is
one `urllib.request` POST to `https://api.anthropic.com/v1/messages` with
`x-api-key` and `anthropic-version: 2023-06-01`, stdlib only — deliberately not
the `anthropic` pip package, because zero install friction is the point. The key
comes from `ANTHROPIC_API_KEY` or a `.env` beside `server/` (gitignored). Default
model id `claude-sonnet-5`, overridable with `MAXEY0_MODEL`.

Everything below that boundary is identical on both paths. Both branches of
`_run_loop` end in `session.write_region(..., loop_id=...)` → `Session.write_region`
→ `ContextWindow.write()`. Same authorization, same `_would_exceed` pre-check,
same `BudgetExceeded` refusal, same event records. The simulated path even
generates real filler text so `write()` counts real tokens, and it stops on the
first non-`ok` result exactly as the API path does when the budget is hit.

To extend it:

- **Multi-turn or tool-using dispatch.** Keep `complete()` as the only network
  call, or add a sibling function next to it; do not scatter HTTP into
  `mission.py`. Everything the model produces must land through
  `session.write_region` so the budget and the log stay authoritative.
- **Dispatch under a bound loop** is how it already works: every write carries
  `loop_id="dispatch:<target>"`, so `Scope.check` is in the path and a write
  outside that loop's scope is refused like any other role's. That is what
  makes Mission Control "an agent writes inside its own partition" rather than
  "the host writes into a budgeted region". Keep it that way; do not add a
  host-write shortcut.
- **Streaming.** The current call is non-streaming with a 60-second timeout. A
  streaming variant should still write one entry per completed unit rather than
  per token, or the event log becomes unreadable and the token accounting
  churns.

Be honest in the UI about which path ran. `mode` is returned for that reason:
without a key, Mission Control dispatch is a **timed simulation, not model work**.

---

## 10. Standing limits

Repeat these anywhere the system is described. They are not caveats to be
softened.

- The Studio's window and the MCP server's window are separate live windows.
  Browser exploration does not mutate the window your Claude Code session's tool
  calls act on. "This coding session" is a read-only mirror.
- `~/.scw/events.jsonl` is append-only and shared by every session on the
  machine, so its whole-file hash chain can legitimately be broken by concurrent
  writers. `live_session.py` verifies and reports `chain_intact: false`, then
  falls back to per-run replay, which stays valid.
- The Studio binds to loopback and has **no authentication**. It exposes live
  region contents. That is why `_send_static` resolves-then-contains, why
  `_guard` refuses a non-loopback `Host` or `Origin`, and why the default host is
  `127.0.0.1`.
- Semantic: x/y are measured by trilateration; z is the **assigned** hierarchy
  level, not a measured dimension.
- One battery loop (`l4-nested`) carries a real containment breach and is marked
  `partial`.
- Mission Control dispatch without an API key is a timed simulation.
- 78 validated loops, not 79. See §5.
