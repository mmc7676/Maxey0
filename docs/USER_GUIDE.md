# Maxey0 User Guide

This is the guide for **using** Maxey0. It assumes you have installed the plugin
and want to get work done with it. If you want to change the code, this is the wrong
document.

Maxey0 makes **Structured Context Windows (SCWs)** a runtime primitive. The context
window is partitioned into addressable, typed, policy-enforced regions. A loop's
execution scope is bound to one region. Isolation is enforced at the tool layer, which
means a refusal is real — it is informative output, not an error to route around.

Two things ship together, and they are separate live windows:

| Surface | What it is |
|---|---|
| The plugin | Three MCP connectors (`maxey0-context`, `maxey0-loops`, `maxey0-observe`), slash commands, agents, skills. Acts on **your Claude Code session's** window. |
| The Studio | A local browser app on `127.0.0.1:7676`. Holds **its own** standalone window, and can mirror your session's window read-only. |

---

## 1. Install and first run

Installation (marketplace entry, plugin install, Python and `mcp` package requirements)
is covered in the repository `README.md`. Read that first. The short version:

- Python 3.10+. The SCW runtime core is pure standard library.
- The MCP servers additionally need the `mcp` package (FastMCP), which pulls in
  pydantic — a compiled dependency, so it needs a wheel for your platform. If it is
  missing, the server exits with the exact `pip` command for the interpreter your
  host actually launched, rather than a bare `ImportError`.
- Nothing else. The Studio's HTTP server, the Anthropic client, and the semantic
  placement are all stdlib.

### Which host are you installing into?

| | Claude Code | Claude Desktop |
|---|---|---|
| how | marketplace / plugin install | drag the `.mcpb` into Settings → Extensions |
| MCP tools | 50, as three servers | 47, as one server (no `observe_gate_*`) |
| Studio | yes | yes |
| slash commands, skills, role agents | yes | — |
| **the Gate** | **yes** | **—** |

The Gate needs a host that runs hooks *and* dispatches subagents. A Desktop
extension declares an MCP server and nothing else, and Desktop does not dispatch
subagents — so there are no delegated actors to attribute and nothing is missing
that Desktop could use. Full reasoning in `docs/CONNECTORS.md` ("Two hosts").

**In Claude Code, restart after installing or upgrading.** Hooks load at session
start; until you restart, the session is still running the hooks it booted with
and the Gate records nothing.

Once installed, start the app:

```
/maxey0:studio
```

The command checks `http://127.0.0.1:7676/api/knowledge` first and will not start a
second copy if one is already answering. To start it by hand instead:

```bash
python server/run_studio.py --port 7676 --no-open
```

Open `http://127.0.0.1:7676`. The header should read **Maxey0** with a subtitle
summarizing what loaded: 16 concepts, 83 skills, 67 deployed agents over a 722-row
roster, and 84 agentic loops.

Environment overrides, all optional:

| Variable | Effect |
|---|---|
| `MAXEY0_STUDIO_PORT` | Port the Studio and `observe_studio` report (default 7676) |
| `MAXEY0_STUDIO_VERBOSE` | Verbose request logging |
| `SCW_RUNTIME_SRC` | Use a live `scw-runtime` checkout instead of the vendored copy |
| `MAXEY0_ROOT` | Point at a different Maxey0-OKF knowledge bundle |
| `MAXEY0_LOOPS` | Point at a different `loops.json` |
| `SCW_EVENT_LOG` | Where events are written / read (see §8) |
| `ANTHROPIC_API_KEY` | Enables real model calls in Mission Control |
| `MAXEY0_GATE_MODE` | Pins the Gate to `enforce`/`observe`/`off` for a whole run |
| `MAXEY0_GATE_LOG` | Where the Gate's journal is written (default `~/.scw/gate.jsonl`). Its entries are redacted: your home folder becomes `~`, transcript paths are dropped, and anything shaped like a secret (API key, token, bearer header, private key, `password=`) becomes `[REDACTED:<kind>]`. The same applies to the event log and to everything the Studio saves. |
| `MAXEY0_GATE_STATE` | Where declared gate policy and actor bindings are cached |
| `MAXEY0_GATE_POLICY` | A policy file pinned for a run, independent of session id |
| `MAXEY0_MODEL` | Overrides the default `claude-sonnet-5` |

A bad override falls back to the vendored copy loudly, on stderr, rather than
half-loading.

The Studio binds to loopback and has **no authentication**. It displays the live
contents of context regions. Do not expose the port.

---

## 2. The 60-second tour

**Route a task.** On the **Overview** tab, type a task and press Route. Try:

```
promote a memory record through the working and episodic tiers
```

What comes back (verified, this is the real result):

```
decision:  loop_hit
concepts:  memory (6.50)
loop:      pipeline:004-semantic-memory-construction-loop
           "Semantic Memory Construction Loop" — validated
roles:     stage0-maxey394, stage1-maxey27, stage2-maxey109,
           stage3-maxey71, stage4-maxey28, stage5-maxey394
alternatives: pipeline:003-working-memory-rehydration-loop,
              pipeline:005-persistent-graph-vector-memory-loop,
              pipeline:028-memory-graph-evolution-loop,
              pipeline:006-memory-promotion-governance-loop,
              pipeline:017-context-persistence-and-rehydration-loop
```

`loop_hit` means a hardened loop already covers this work, with its partition already
configured. That is the decision the whole system exists to make.

**See a fallback.** Not everything hits. When no validated in-window loop shares a top
concept, the result is `fallback_skill` — the matched skills, and no partition. When even
that comes back empty, it is `fallback_agent`, scored against the agent roster. A
fallback is real information: it names a gap in the loop library. Say it out loud rather
than papering over it.

**Bind it.** Press **Bind SCWs** on the route result (or **Bind** on any in-window loop
in the **Loops** tab). Binding is not a preview — it builds the loop's regions, harness
and roles against a live `ContextWindow` and attempts every negative control the loop
declares. Binding `battery:l1-maker-checker-judge` returns, verified:

```
instance: L1   roles: L1-maker, L1-checker, L1-judge
refused_negative_controls: 6
  context_bridge_open — "maker attempts to read checker's private pad"
    PolicyViolation: region 'L1-checker-pad' declares bridgeable=false;
                     no grant can be minted
```

Six attempts to cross a wall, six refusals from the runtime.

**Look at the window.** Go to **Window**. You will see six regions:

| Region | Type | Budget |
|---|---|---|
| `L1-maker-pad`, `L1-checker-pad`, `L1-judge-pad` | scratchpad | 2048 each |
| `L1-maker-out`, `L1-checker-out`, `L1-judge-out` | durable | — |

Now set **view as** to `L1-maker` and click `L1-judge-pad`. The contents pane does not
hide the region; it shows you the runtime refusing:

```
isolation_violation
loop 'L1-maker' is bound to 'L1-maker-pad'; 'L1-judge-pad' is outside its
scope and no bridge grants 'read'
hint: context_bridge_open(from_scw_id='L1-maker-pad', to_scw_id='L1-judge-pad',
      mode='read', reason=...) — or bind the loop to a common ancestor.
```

That is the tour. Everything else is depth on those four moves.

---

## 3. The tabs

The header carries three controls that apply to the Studio's own window regardless of
tab: a **run badge** (the current run id), **Verify chain** (verifies the hash chain and
proves the log replays to an identical window), and **Reset window** (tears the run down
and starts a fresh one — it discards).

### Overview — *does something already cover this?*

Route input, the decision, and the concept scores behind it. Alongside it, the counts and
the source paths everything loaded from. Look at the **decision** first and the
**alternatives** second: the alternatives tell you how close the call was.

### Mission Control — *what is actually running, and what is it allowed to spend?*

This is where you create regions and put work into them. It is the newest surface in the
app and the one that repays the most attention.

**The cascade.** Creating an SCW here is not a bare CRUD action. You pick **concept →
skill → agent** first, and only then is there anywhere for work to write. The three
selects are chained: choosing a concept enables the skill select and populates it with
that concept's skills; choosing a skill shows its description and enables the agent
select, populated with that skill's agents and their roles. You may leave any level at
"— any —" / "— unbound —"; the label defaults down the chain (skill id, else concept id,
else `scw`).

**Creating one or several regions.** With **target scw** on `+ new scw` you get:

| Field | Meaning |
|---|---|
| `label` | Region label; `auto` derives it from the selected skill or concept |
| `count` | How many regions to create in one go. With count > 1 the labels are suffixed `-1`, `-2`, … and the dispatch targets the first |
| `region type` | `working`, `durable`, `episodic`, or `scratchpad` |
| `token ceiling` | A real budget, created with `eviction: reject` — the region refuses a write that would exceed it rather than quietly dropping old content |

Set **target scw** to an existing region instead and the create fields disappear; the
dispatch writes into that region.

**Dispatch.** Press Dispatch with a prompt and the work runs on a background thread as a
bound loop, not as a host write: the dispatch adds a `<target>-pad` scratchpad under the
target region, binds a loop named `dispatch:<target>` to the target, writes every step
*through that loop id* (so the runtime scope-checks it like any other role) using the same
`write()` every other part of the system uses, ticks once per step, and unbinds with an
honest terminal state (`success`, `blocked` or `no_op`). The **mode badge** tells you
which path you are on:

- `mode: real api` — `ANTHROPIC_API_KEY` is set (env, or a `.env` beside `server/`). The
  dispatch makes a real Claude Messages API call with the agent name and skill
  description as its system prompt, and writes the response into the target under key
  `dispatch-result`. An API failure writes `[api error] …` into the scratchpad under key
  `error` and ends the loop `blocked`, rather than vanishing.
- `mode: simulated` — no key. A timed simulation writes 4–9 real steps of real text into
  the region. It is not model work and the app says so.

Both paths go through the **same** `write()`, so both hit the same real budget
enforcement. That is the point of the simulation: the enforcement you observe without a
key is the enforcement you get with one.

The **anthropic api key** box at the bottom of the console states which it is, and names
the model when configured.

**The observation grid.** Nine cells, three by three, one page at a time. The page line
reads `regions 1–9 of N · page 1/M`; **‹ prev** / **next ›** page through the rest. The
layout is sized around a 32-region window — four pages of nine — but it paginates over
however many regions the window actually holds. Each occupied cell shows:

- label and region type
- lifecycle, entry count, nesting depth
- a token bar: `own_tokens / token_budget`, colored by eviction policy
- **inspect** (jumps to the Window view with that region selected) and **close**

**Drag-and-drop ingest.** Drop a text file onto a cell and its contents are written into
that region as `[file: <name>]` plus the text. There is also a drop strip under the
console, which writes into whatever **target scw** currently names — it refuses politely
if the target is still `+ new scw`.

**What a refusal looks like here.** Give a region a ceiling of 200 tokens and drop a file
larger than that. The toast carries the runtime's own message, unedited:

```
budget_exceeded
write of 500 tokens would exceed budget 200 for 'budget-demo'
  budget: 200   would_be: 550
```

Note the asymmetry, because it matters when you are reading the grid: a **file drop** or
a **failed create** surfaces as a red toast and a `refused: …` line under the console,
because those are synchronous. A budget hit **during a dispatch** happens on the
background thread — the run simply stops writing, and what you see is the region's token
bar parked at its ceiling with no further entries appearing. If a dispatch goes quiet,
check the bar before you check anything else.

**The source switch.** The select above the grid has two positions:

- **Studio standalone** — the Studio's own window. You can create, dispatch, drop files,
  and close regions. The note reads `studio's own standalone window · run <id>`.
- **This coding session** — a **read-only mirror** of this machine's real SCW MCP
  activity, replayed from `~/.scw/events.jsonl` with the same reducer that produces
  "real" state everywhere else. Dispatch is disabled, the create fields and the drop
  strip are hidden, and the close buttons disappear. The note line reads, for example:

  ```
  this coding session · run <id> · 214 events · chain intact · read-only mirror
  ```

  If the log's last run has no activity yet, the mirror falls back to the most recent run
  that did and labels itself `last recorded session` instead. If the whole-file hash chain
  does not verify, it says `chain integrity broken (concurrent writers on this machine)`
  and keeps working — see §8.

This mirror cannot be written to. Nothing in the browser mutates the window your Claude
Code tool calls act on. That limit is structural, not a missing feature: the two live in
different OS processes and share no memory.

### Concepts — *what territory does the system cover?*

The 16 Maxey0 concepts with the number of loops touching each. Click one to see them.

### Loops — *what has actually been proven, and how?*

All 84 loops, filterable by concept, by status, and by name. Status is evidence, not
decoration:

| Status | Count | Meaning |
|---|---|---|
| `validated` | 78 | Built clean against a live window, with every negative control actually attempted and actually refused |
| `partial` | 1 | A real, named problem. `battery:l4-nested` carries a genuine containment breach |
| `draft-unexecuted` | 5 | Never run. The five `designer:*` cross-window topologies |

By provenance: 74 pipeline, 4 battery, 5 designer, 1 planned. Cross-window loops show no
**Bind** button, because there is no single window to bind — see §7.

A `designer:*` loop is promoted to `validated` only when a real cross-window run's own
report file says so, recomputed from disk on every load. Nothing here is hand-set.

### Designer — *can I build a loop that survives contact with the runtime?*

Search the 67 deployed agents on the left, drag or click them into the stage strip, drag
a stage to reorder. Each stage becomes one role bound to its own private scratchpad,
publishing to one declared handoff region — so stage N reads stage N−1's *output*, never
its reasoning.

**Harden** compiles the design and builds it against a live window, negative controls and
all. **Save** stays disabled until Harden passes. You cannot save a loop that has not been
made to work.

### Window — *who can see what, right now?*

Three panes: the region tree, the contents of the selected region, and the trace.

The control that matters is **view as**. Set it to a bound role and every region is read
*through that role's scope*. Regions outside the role's closure come back as real
refusals with the runtime's own message and hint, not as blanks the UI decided to hide.
This is the fastest honest answer to "is the partition real?"

The trace pane lists events as they happen; tick **live** to follow along.

### Semantic — *where does this sit relative to everything else?*

Concepts, skills and agents placed against Maxey0's anchor field, one plane per hierarchy
level, with toggles per level and for edges.

Read the method line under the heading and believe it: **x and y are measured by
trilateration against the anchor field; z is the assigned hierarchy level, not a measured
dimension.** The vertical axis is a layout decision. Do not read distance in z as meaning.

### Evidence — *is containment tested, or only declared?*

Three cards, all over the Studio's own window except the isolation level:

- **Containment.** `bound_holds` computed over the region graph, then a probed matrix —
  a real read attempted for every (role, region) cell — with the refused, authorized and
  cell counts, and any **closure disagreements** where the computation and the attempt
  disagree. A disagreement is a defect in one of them, not a measurement.
- **Isolation level.** Which of L0–L3 the recorded evidence supports, against the level
  you pick as declared, with the shortfall named.
- **Event stream.** A summary of the run, or the individual events filtered by kind
  (`access`, `refusal`, `scope`, `bridge`, `utilization`, `audit`, `routing`), role or
  region. Give a role or region and it also reports `contained`, which is three-valued:
  null means nothing was attempted, and establishes nothing either way.

Experiments have no tab. The workload harness is research tooling in the separate
`maxey0-lab` plugin, driven with `/maxey0-lab:experiment-run` — see §6.

---

### Gate — *what did the agents themselves actually do?*

The only tab that reports on your **coding session's** agents rather than the
Studio's own window. Everything else here shows what the host did to the window;
this shows what a delegated role did once it was running.

Four things, top to bottom:

**Isolation level.** Which of L0–L3 the recorded evidence supports, with the
evidence listed and the shortfall named where it is below what you declared.
Pick your declared level in the dropdown to see whether it holds. Each level also
states what it **may not claim** — L1 is logical isolation, not hard isolation;
even L3 is not representational independence.

**Containment.** `held` is three-valued (true / false / not established), and
`claimable` is separate and stricter: it goes false whenever there is any
residue — an unattributed call, a fail-open, a lost record — because a hole in
the evidence sits exactly where the claim would go.

**Per role — context in, execution out.** What each role was handed against what
it then did, with a finding where those disagree. A role given context that made
no observed call, and a role that acted with no recorded transfer, are both
surfaced rather than left as blank rows. The host's own calls appear separately
as `(host)`; the orchestrator is governed by no policy and is not residue.

**Activity.** Every intercepted call in order, with its verdict, and refusals
carrying the runtime's own message and hint.

If it says no journal exists, no delegated agent has been intercepted yet — see
§8.

## 4. Slash commands

Ten commands ship in `commands/`. The full-stack `maxey0` plugin exposes all ten as
`/maxey0:<name>`; if you installed a single plane instead, that plane's commands appear
under its own plugin name (`/maxey0-context:window`, for example).

| command | plane | what it does |
|---|---|---|
| `/maxey0:menu [section]` | loops | The control surface — every plane, connector, tool, command and view, rendered from the registry |
| `/maxey0:doctor` | loops | What is up, what is down, and what is missing — connectors, ledger, Gate, runtime provenance |
| `/maxey0:window [inspect\|partition\|verify\|closure <role>]` | context | Inspect or partition this session's window |
| `/maxey0:route <task>` | loops | Route a task and report the decision, binding nothing |
| `/maxey0:run <task>` | context | Route, bind, dispatch every role, close out |
| `/maxey0:crosswindow <designer:NN-slug> [run-id]` | loops | Run a cross-window topology |
| `/maxey0:gate [status\|observe\|enforce\|off\|policy <role>\|activity\|level]` | observe | Read or set the Gate; declare a role's reach outside the window |
| `/maxey0:assert [cannot\|can\|closed\|disjoint\|all …]` | context | Test containment by attempting a real read |
| `/maxey0:studio [port]` | observe | Start the Studio and hand over its address |
| `/maxey0:scw-deploy [task]` | context | Create the default SCW and report its address, constitution and observability contract |

One more command ships outside the product, in the separate `maxey0-lab` plugin:
`/maxey0-lab:experiment-run` (see §6).

### `/maxey0:studio [port]`

Starts the Studio and hands you the URL, after checking whether it is already up.

```
> /maxey0:studio
Studio already running at http://127.0.0.1:7676
```

It starts the process in the background so it outlives the turn, and it will tell you the
Studio's window is not this session's window if you seem to expect otherwise. The nine
views are described in §3.

### `/maxey0:run <task description>`

The full orchestrated run: route, bind, understand the partition, declare each role's
reach outside the window, dispatch one real subagent per role, close out honestly.

```
> /maxey0:run write the release notes for the 0.3.0 plugin release,
  then have them checked by something that did not write them
```

What comes back, in order: the routing decision (`loop_hit` and the bound role per stage,
or a fallback plus a `loops_route` second opinion); a table of which region each role is
bound to, what it may read, and what it publishes; the Gate policy declared for each role
(`observe_gate_policy`) and the Gate mode chosen; then one subagent per role in topology
order, each given exactly `context_window_render(loop_id=<role>)` behind a
`[[scw:role=<role>]]` marker and nothing more; then `context_scope_unbind` per role with an
honest terminal state, every refusal the runtime issued and what each one prevented, and
`observe_gate_activity` with `containment.claimable` reported verbatim.

Two rules it will not bend: nothing elided by `context_window_render` gets pasted back into a
subagent's prompt, and `terminal_state="success"` is only claimed when a verification
actually passed.

### `/maxey0:window [inspect|partition|verify|closure <role>]`

Works on this session's live window. Default mode is `inspect`.

```
> /maxey0:window inspect
```

Returns the region map (id, type, policy, tokens, who is bound where), open bridges with
mode/owner/TTL, the cache plan — hit ratio, where the breakpoint falls, how many tokens a
different region order would recover — and any advisories verbatim.

```
> /maxey0:window closure L1-checker
can read:   L1-checker-pad, L1-maker-out
can write:  L1-checker-pad, L1-checker-out
walled off: L1-maker-pad, L1-judge-pad (bridgeable=false — no grant can be minted)
```

`partition` builds a window for the work at hand, explaining each region-type choice as it
makes it. `verify` proves the hash chain and the replay. `context_window_reset` is destructive and
the command confirms before calling it.

### `/maxey0-lab:experiment-run [spec-id|spec-path|exp-id]`

Runs a workload spec to completion and reports it. Ships in the `maxey0-lab` plugin, not
in `maxey0`; install that plugin only if you are running a study. See §6.

### `/maxey0:crosswindow <designer:NN-slug> [run-id]`

Runs a cross-window topology. See §7.

---

## 5. Working with SCWs conversationally

You do not have to use a command. The **scw** skill activates on its own when a task
needs several agents or roles, when something must be verified by something that did not
produce it, when there is reference material a step must read but must never edit, when
the window is getting long or expensive, or when you say SCW, region, partition, isolation,
agentic loop, or Maxey0.

Its first instruction is not optional: **route before you build.** Call `context_route_bind`
(which binds) or `loops_route` (which scores only) before hand-assembling a
maker/checker pair. The skill records one measured case where an improvised pair cost
253,481 tokens against roughly 10,792 for the formation routing actually named.

The `maxey0-context` connector exposes 32 tools: the 24 SCW primitives below,
plus the four containment assertions (`context_assert_can_read`,
`context_assert_cannot_read`, `context_assert_scope_closed`,
`context_assert_disjoint`), `context_route_bind`, `context_formation_build`,
and the egress gate — `context_admit` and `context_assert_admitted`. The
`maxey0-loops` connector holds the library and routing instead — `loops_catalog`,
`loops_concepts`, `loops_route`, `loops_agents` among them — and holds no
window state at all, so browsing and scoring it work with nothing else
installed.

The 24 primitives make sense in groups, following the prompt → context → harness → loop
progression:

**Prompt layer — the instruction, held as data.**
`context_prompt_create` declares a template with `{{slot}}` placeholders. `context_prompt_revise` edits it
while keeping the superseded version in history, and is refused if the prompt is locked.
`context_prompt_render` materializes it against bindings, and is refused if you bind a variable
the prompt never declared — which is almost always a typo, caught at the tool layer.

**Context layer — the regions themselves.**
`context_region_create` makes an addressable region; `region_type` picks a policy preset, and the
type is a policy, not a label. `context_region_write` and `context_region_read` move bytes
in and out; pass `loop_id` and the call is checked against that loop's scope, omit it and
you are the host.
`context_region_close` seals or purges, and refuses while a loop is still bound or a child is open.

| type | mutability | bridgeable | use it for |
|---|---|---|---|
| `reference` | read-only | yes | instructions, retrieved corpus, a pinned rubric |
| `durable` | writable | yes | memory that should survive the run |
| `episodic` | writable | yes | run history, promoted findings |
| `working` | writable | no | task state nothing else should reach into |
| `scratchpad` | volatile | no | per-iteration reasoning; cleared every tick |

**Harness layer — the environment work runs inside.**
`context_harness_create` declares tools, skills and architecture. `architecture="maker_checker"`
is what turns self-approval into a refusal. `context_harness_call` records a loop invoking a named
skill, and is refused when the skill is outside the harness's declared set under strict
mode.

**Loop layer — scope and iteration.**
`context_scope_bind` is the pivot of the entire runtime: it binds a loop to one region and
declares its trigger, goal, verification level and iteration cap. From then on every call
carrying that `loop_id` is checked. `context_scope_tick` advances one iteration — call it once per
model call, and record the verdict. `context_scope_unbind` releases, naming a terminal state; you
cannot claim `success` unless a verification actually passed.

**Verification — the yardstick and the evidence.**
`context_criterion_pin` freezes a region as the standard a loop is graded against and re-checks
its signature at every tick. `context_criterion_repin` accepts new bytes as the standard, and is
deliberately manual because re-pinning restarts comparability. `context_evidence_attest` records
external proof — a command and its exit code, for instance — and returns an id a verdict
can cite.

**Controlled crossing — the only legal holes.**
`context_bridge_open` mints an explicit, reasoned, expiring grant. Prefer `ttl_ticks=1`; a
standing grant is a wall with the door propped open. `context_bridge_close` revokes early, as soon
as the crossing it authorized is done. `context_bridge_promote` moves or copies content across a tier
boundary with provenance intact — how volatile work becomes durable at the end of an
iteration.

**Observation and audit — how you find out rather than assert.**
`context_window_inspect` returns the region map, token accounting, cache plan and advisories.
`context_window_render` materializes the window as prompt text, scope-true, with per-region token
offsets and `cache_breakpoint_after`. `context_scope_closure` gives a loop's read and write
closures as sets. `context_window_disjointness` is pure — it mutates nothing — so ask it *before*
running the iteration a `maker_checker` harness would refuse.

**Window lifecycle.**
`context_window_seal` ends setup and closes the privileged unbound host path for the rest of the
run. `context_window_reset` tears everything down and starts a fresh run.

Four rules carry across all of it:

1. Never route around a refusal. `IsolationViolation` and `PolicyViolation` are the system
   working. Read the `hint`, then decide whether the access is actually justified.
2. Never paste elided material into a subagent's prompt. `context_window_render` is scope-true;
   adding back what it withheld destroys the partition silently and makes any measurement
   over the run meaningless.
3. Grants expire. Prefer `ttl_ticks=1`.
4. Do not claim isolation held without calling `context_scope_closure` or `context_window_disjointness`.

---

## 5b. What "isolation" means here, exactly

The runtime enforces **context-access disjointness**: two roles cannot obtain
bytes from the same region. It does not establish either stronger property, and
it is worth being precise about which is which.

| level | property | status |
|---|---|---|
| 1 — context access | `Vis(Si) ∩ Vis(Sj) = ∅` | **enforced by the runtime** |
| 2 — representation | `I(Zi ; C¬i \| Ci) = 0` | not established |
| 3 — embedding geometry | `Ei ∩ Ej = ∅` | not established, not a near-term goal |

Enforced information access is not proven representational independence. A
model holding the whole context may still carry information about a region a
bound role cannot read. That is not a containment failure — it is a different
proposition, and this system does not claim it.

---

## 6. Running an experiment end to end

The plugin ships a harness, not an experiment. You hand it a **workload spec** — tasks,
conditions and a leak probe — and it drives that spec to a report. Nothing in the harness
knows what the workload is, so swapping the spec is the only change needed to run a
different one.

The harness is research tooling, not part of the product. Its HTTP API is served by the
Studio; the command that drives it, `/maxey0-lab:experiment-run`, ships in the separate
`maxey0-lab` plugin, and nothing in the three planes depends on it.

Specs live in `experiments/specs/`, loadable by id, or anywhere on disk, loadable by path.
Four ship: `maxey0-website`, which builds maxey0.com through Maxey0 agentic loops and
compares SCW partitioning against an unpartitioned control; `maxey0-routing-efficacy`
(Maxey0's routing against a declared baseline formation); `maxey0-factorial` (both of
those axes crossed, 2×2); and `maxey0-gating` (ungated, observed and enforced Gate).
`experiments/specs/README.md` documents the shape and the rules the harness enforces on it.

The harness never calls a model. It names exactly one pending call, hands you the literal
prompt, and takes the raw response back. You supply the model calls. Everything is on
disk after every step, so an interrupted session resumes by asking for the next call
again; `ingest` is idempotent per call.

**Create a run.** `POST {"spec": "maxey0-website"}` to `/api/experiments/create` (the lab
command does this for you; there is no Studio tab for it). List what is installed at
`/api/experiments/specs`. Creating a run routes every task in the spec, records each
routing decision *before any model call*, then binds each task's loop under every
condition the spec declares. A condition names a cell on up to three axes. Its partition
strategy:

- `scw` — the loop's real partition, one private scratchpad per role.
- `flat` — the unpartitioned control: one shared `durable` region, every role bound to it.

It may also name a `routing` (`maxey0`, the default, or `baseline`: the task's declared
`baseline_loop`) and a `gating` (`off`, the default, `observe` or `enforce`).

A task whose routing found no loop produces no calls at all and is recorded as a
`loop_coverage_gap`. It is not backfilled with a substitute, because "the library did not
cover this" is exactly what the routing measurement exists to surface.

**Drive it.**

```
> /maxey0-lab:experiment-run exp-20260821-141233-a1b2c3
```

The command loops: fetch `next.prompt` from `/api/experiments/status`, spawn exactly one
subagent whose entire prompt is that text verbatim, then — same turn, before any other
tool call — send the run's leak probe to that same agent, then POST both raw responses to
`/api/experiments/ingest`. The ordering is not stylistic: agent transcripts do not
survive, so a probe sent late fails with "no transcript found." Treat the primary call and
its probe as one atomic unit.

The probe comes from the spec, not the harness — it is on the `probe` field of the status
response, and at `/api/experiments/probe?id=<EXP_ID>`. Each spec also declares the single
sentinel that counts as a refusal, and that sentinel must appear in its own probe text
(otherwise the run would report 0% refusal by construction, and the harness rejects the
spec). Grading is on that one string: `refused` if present, `disclosed_or_other`
otherwise. Nothing is inferred from prose. A spec with no probe reports leakage as
**null**, and says so in the residue.

**Report.** `/api/experiments/report?id=<EXP_ID>` writes `report.json` and `report.md`
under `experiments/<exp-id>/`. The fields:

| Field | What it measures | Where it comes from |
|---|---|---|
| `progress.total` / `.done` / `.complete` | Call ledger | Count of materialized calls vs. ingested ones |
| `routing.per_task` | Per task: decision, loop id, loop status | `state.route()`, run at creation before any model call |
| `routing.counts` | How many `loop_hit` / `fallback_skill` / `fallback_agent` | Same |
| `routing.loop_coverage_rate` | `loop_hit` ÷ total tasks | Same |
| `per_condition.calls_done` | Completed calls in this condition | The call ledger |
| `per_condition.probes_collected` | Probes with any graded verdict | Ingested probe responses |
| `per_condition.probes_refused` | Probes that returned the sentinel | The one pre-registered key |
| `per_condition.leak_refusal_rate` | refused ÷ collected, or **null** | Computed only when probes exist |
| `per_condition.mean_read_closure` / `max_read_closure` | How much each role could reach | `partition.read_closure` over the live window at materialization |
| `containment` | Structural containment over the real region graph | `loopkit.harness_kit.containment_report` |
| `cost` | Flat vs. partitioned render tokens | `loopkit.harness_kit.cost_model` |
| `integrity` | Chain verifies, and replay reconstructs an identical window | `Session.verify_chain()` |
| `residue` | Everything that could not be measured | Accumulated during the run, plus checks at report time |

Read `residue` **before** you say anything about the results. Six kinds appear:

- `loop_coverage_gap` — tasks no validated in-window loop matched. They produced no calls
  and are excluded from every per-condition rate.
- `no_leak_probes` — no probe responses supplied, so every leakage field is **null, not
  zero**.
- `no_probe_defined` — the spec declares no probe at all, so leakage was never measured.
- `routing_correctness_ungraded` — no task declared `valid_loops`, so routing correctness
  and reliability are null: the run shows what Maxey0 chose, not whether it was right.
- `no_verified_work` — a condition accepted zero verifications, so its efficiency figure is
  zero work per token rather than a quality signal.
- `underpowered` — a condition with 0 < N < 3 probes. Carry the word "underpowered" into
  your summary rather than quoting the percentage bare.

Reporting rules, in order of how easy they are to violate: never fabricate a number;
report cost in call counts and tokens, never dollars; a small N is a pilot, not a rate; a
containment breach (`bound_holds: false`) is a headline, not a footnote; null is not zero;
and if the conditions come out indistinguishable, say so — a null result is a result.

---

## 7. Running a cross-window topology

Cross-window is a different architecture, not a lesser one. There is no region, no scope,
and no runtime refusal, because every participant is a genuinely separate model call with
zero shared token buffer — there is nothing for a leak to read *from*. Isolation is
enforced entirely by which text **you** put in each call's prompt. That makes you the
enforcement mechanism for the run.

Five topologies ship:

| Loop id | Shape |
|---|---|
| `designer:01-horizontal-4way` | Four flat siblings, no shared root |
| `designer:02-vertical-nesting` | Orchestrator (SCW0) + two children + one outside peer |
| `designer:03-fanin-scaling` | Three independent makers → one judge reading only outputs |
| `designer:04-adversarial-embedded-canary` | A canary embedded in content that must be *transformed*, not merely withheld |
| `designer:05-multiround-persistence` | Round 2 reads only round 1's declared outputs |

**Run one.**

```
> /maxey0:crosswindow designer:03-fanin-scaling
```

The loop: `loops_crosswindow_create(loop_id)` plans the run and returns the first
pending call. Dispatch exactly that call's prompt, verbatim, as one subagent — no framing,
no "here's what the others are doing." Anything you add beyond the given prompt is a leak
you created by hand, in the one place this architecture cannot stop you.
`loops_crosswindow_ingest(run_id, call_id, response)` records the response and splices
it into any downstream call that declared it may read this participant's output — you
never do that splicing yourself. Repeat via `loops_crosswindow_status(run_id)` until
`complete: true`. One subagent per call, never reused.

**Report.** `loops_crosswindow_report(run_id)` is a mechanical check, not an assumption.
For every call it greps that call's **actual dispatched prompt** for every other
participant's private markers and raw response text it was never granted. Any hit is a
named leak.

```json
{
  "run_id": "...", "loop_id": "designer:03-fanin-scaling",
  "complete": true, "participants": 4, "calls_done": 4,
  "bound_holds": true,
  "leaks": [],
  "verdict": "4 participants, 0 shared buffer by construction; 0 leak(s) found in the actual dispatched prompts"
}
```

The report is written to `experiments/cross-window/<run_id>.report.json`. A complete,
clean report is what promotes that `designer:*` loop from `draft-unexecuted` to
`validated` in the Loops tab — recomputed from the file on every load, never hand-set.

If `bound_holds` comes back false, that is the finding. Say so plainly and name which call
leaked what. Do not quietly fix and rerun.

---

## 8. Troubleshooting

**The Gate recorded nothing — 0 tool calls observed.** Three causes, in order of
likelihood. (1) **You have not restarted Claude Code since installing.** Hooks load
at session start; the running session is still using the hooks it booted with.
(2) **You are in Claude Desktop**, which has no hook system and dispatches no
subagents — the Gate is Claude Code only, by construction rather than by
omission. (3) **The plugin your host loaded is an older copy.** Check the version
the host actually has, not the version in your working tree.

**The Gate recorded calls but refused nothing.** It installs in `observe`, which
records everything and blocks nothing, on purpose. To enforce you need both a
declared policy (`observe_gate_policy(role=…, read_paths=[…], tools=[…])`) and
`observe_gate_mode("enforce")`. A call with no policy is reported `no_policy` and allowed
— that is "unmeasured", not "permitted". Note that a policy declared before a
session exists is stored under no session id and still applies; a session-specific
declaration always wins over it.

**Containment says `claimable: false` on a run that looks clean.** Read the
residue block. Any fail-open, unattributed call, or lost record makes the figure
incomplete, and the report says so rather than averaging it away.

**Port already in use.** `/maxey0:studio` checks `/api/knowledge` before starting anything,
so a `200` just means it is already up. If something *else* holds 7676, start on another
port — `python server/run_studio.py --port 7777 --no-open`, or set `MAXEY0_STUDIO_PORT` so
the `observe_studio` tool reports the same address you are actually using.

**MCP server not appearing.** The three connectors are registered in the plugin's
`.claude-plugin/plugin.json` (`plugins/maxey0/` in this repository) and launched as
`python server/context_server.py`, `python server/loops_server.py` and
`python server/observe_server.py`. If their tools do not show up:

- `/maxey0:doctor` reports which planes are reachable and whether each imports here.
- The `mcp` package (FastMCP) is missing, or pydantic has no wheel for your Python. All
  three servers need it; the SCW runtime core does not.
- `python` on PATH is not the interpreter you installed into.
- Run any of them directly to see the real error: `python server/context_server.py`.
- If `context_route_bind` returns `maxey0_root_not_found`, point `MAXEY0_ROOT` at the directory
  containing `manifest.json`. The plugin manifest's env block normally sets this for you.
- Tools named `maxey0-ss.*` come from a different server, `maxey0-ss`, which this
  repository's own `.mcp.json` registers. It is not part of the plugin; see
  `docs/MCP_SERVERS.md`.

**No API key.** Mission Control shows `mode: simulated` and says so under the console.
Dispatch still creates real regions and still writes through the real `write()`, so budget
enforcement and refusals are identical — only the text is generated by a timed simulation
instead of a model. To enable real calls, set `ANTHROPIC_API_KEY` or drop a `.env`
containing `ANTHROPIC_API_KEY=...` beside `server/`, then reload the tab. The `.env` is
gitignored. Override the model with `MAXEY0_MODEL`.

**Broken event-log chain.** `~/.scw/events.jsonl` is append-only and shared by every
session on this machine. Two sessions writing at once can legitimately break the
whole-file hash chain without anything being wrong with either run. The live mirror
verifies **per run** instead and reports `chain_intact: false` rather than crashing — you
will see `chain integrity broken (concurrent writers on this machine)` in the note line,
and the per-run replay stays valid. If you want a clean chain for a specific run, point
`SCW_EVENT_LOG` at a fresh file for that session. The Studio's own window logs separately,
to `~/.scw/studio.jsonl`.

**Studio window ≠ session window.** This is the limit to internalize. The Studio holds its
own live window in its own process; your Claude Code session's SCW MCP tools act on a
different one. Nothing you click in the browser mutates the window your tool calls touch.
Mission Control's **This coding session** view is a read-only mirror, reconstructed from
the same durable log that session is writing — genuinely that session's state, but
observation only. To act on your session's window, use the MCP tools or `/maxey0:window`. To
act on the Studio's, use the Studio.

**A dispatch went quiet.** Check the token bar in the observation grid. A budget refusal
during dispatch happens on a background thread and stops the run without a toast; the
region parked at its ceiling is the signal.

**One loop is marked `partial`, on purpose.** `battery:l4-nested` carries a real
containment breach. It is not a data error and should not be filtered out of view — it is
the one loop in the library whose honest status is "this does not fully hold."
