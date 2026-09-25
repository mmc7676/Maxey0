# The Maxey0 Lexicon

One name per thing, and the same name in every surface: MCP tool, slash command,
skill, agent, hook, Studio view, document, and marketplace listing.

This file is **normative**. `scripts/check_lexicon.py` enforces it and
`scripts/validate_plugin.py` runs that check, so a term that drifts fails the
build rather than shipping.

Before 0.7.0 the same referent carried up to five names — a container was an
`SCW`, a `window`, a `partition`, a `region`, and a `world` depending on which
file you opened; `maxey0_*` tools lived on a server called `worlds`; the
`skills/` directory contained concepts. That is what this document ends.

---

## 1. Planes and connectors

These are two different decompositions and the lexicon keeps them apart. A
**plane** is what the system *is*. A **connector** is what *installs*. The
mapping is many-to-one, and one plane has no connector.

### The three planes

> Most agent infrastructure primarily adds capability to the execution plane.
> Maxey0 makes the contextual environment surrounding agentic execution an
> independently structured, routable, partitionable, and observable plane,
> while providing an engineering plane that can observe and tune both.

| plane | owner | holds |
|---|---|---|
| **Execution** | the host | Agents, agentic loops, LLM calls, tool calls, working memory, generated output. Maxey0 adds no capability here. |
| **Context** | Maxey0 | Concepts, Skills, SCWs, regions, scopes, admission gates, routing, provenance. |
| **Engineering** | Maxey0 | The Gate, the ledger, the three correlated traces, the isolation ladder, the Studio. |

### The three connectors

Each installs on its own and is useful alone.

| connector | serves | owns | useful alone because |
|---|---|---|---|
| `maxey0-context` | Context plane | Regions, scopes, bridges, harnesses, ticks, the hash-chained ledger, the four assertions | You can partition a context window and enforce who reads what without routing a task or watching an agent. |
| `maxey0-loops` | Context plane | 16 concepts, 83 skills, 67 agents, 84 hardened loops, routing, cross-window topologies | You can route a task to a pre-scoped formation against a fixed context scheme, with no enforcement engine. |
| `maxey0-observe` | Engineering plane | The Gate, containment evidence, the event stream, traces, isolation levels, the Studio | You can attribute and refuse any delegated agent's tool calls — global workspace semantics — with no window and no library. |

`maxey0` (no suffix) installs all three.

**The rule that decides which connector a capability belongs to** is mechanical
rather than thematic: *the window is process-local state*. Anything that reads
or writes the live window lives on `maxey0-context` — including the four
containment assertions and `context_route_bind`. `maxey0-loops` holds no window
state at all. `maxey0-observe` holds none either, and reads the other two from
disk.

### Planes vs. strata

"Plane" means exactly one thing: **one of the three above.** The five-level
address model earlier versions also called planes is the **address strata**
(`stratum 0`..`stratum 4`) — see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## 2. Nouns

Each row is the only approved name for its referent. The "not" column lists
terms that previously meant the same thing and are now retired.

| canonical | means | not |
|---|---|---|
| **window** | The whole addressable context of one session. Exactly one per runtime process. | context window (in product copy), SCW0 as a synonym for the session |
| **region** | One typed, addressable, budgeted subdivision of the window. What `context_region_create` creates. | SCW, partition, world, tier, container, bucket |
| **region type** | `reference` / `durable` / `episodic` / `working` / `scratchpad`. A policy, not a label. | tier, class, kind |
| **partition** | The **act** of dividing a window, and the resulting arrangement of regions. Always a verb or an arrangement — never one region. | — |
| **SCW** | **Structured Context Window** — the product name for the partitioned-window architecture as a whole. Expanded on first use in every document. | Structured Concept Window (retired second expansion) |
| **role** | One named actor in a loop, bound to its own scope. What a subagent is dispatched as. | participant, stage, agent (when you mean the actor in *this* run), loop (when you mean the actor) |
| **scope** | The set of regions a role may reach, declared at bind time. | reach, closure |
| **closure** | The **computed** transitive set of regions a scope resolves to. Output, not declaration. | scope (when you mean the computed set) |
| **bridge** | An explicit, expiring grant that lets one scope reach a region outside it. The only legal crossing. | grant, crossing, door |
| **formation** | A set of roles and the shape they are arranged in — maker/checker/judge, for instance. | topology, team, squad, pipeline, battery |
| **topology** | Reserved for **cross-window** formations only, where isolation comes from separate model calls rather than from regions. | — |
| **loop** | One entry in the library: a formation plus its partition plus its hardening record. Always a library artifact. | the procedure a command runs, the actor in a run, the generic pattern |
| **concept** | One of the 16 subject areas a loop and a window are scoped to. | domain, area, topic |
| **skill** | One of the 83 capability definitions in the library, owned by a concept. | — |
| **agent** | One of the 67 registry entries a loop stage names. Distinct from a **role agent**. | — |
| **role agent** | A shipped Claude Code agent file in `agents/` that a role is dispatched as. | agent (unqualified, when you mean the file) |
| **the Gate** | Capitalized, always "the Gate". The resident component at every tool call. Its tools are lowercase `observe_gate_*`. | gate (lowercase in prose), the hook, the interceptor |
| **the Studio** | Capitalized. The local browser application. | the app, browser app, local UI, dashboard, Mission Control (one view inside it) |
| **view** | One tab in the Studio. There are nine, listed once in §5. | tab, screen, page, panel |
| **private** | A region no role but its owner may reach. `bridgeable=False` by policy. Two roles reaching one is the only thing `context_assert_disjoint` fails on. | isolated (an outcome, not a region property) |
| **admitted** | A region one role writes and another reads: a declared handoff. Overlap that is the formation working. | shared, leaked |
| **shared reference** | A region no bound role can write. Both may read it; neither can put anything in it, so it cannot carry state between them. | shared context |
| **residue** | Anything in a run that prevents a containment claim: an unattributed call, a fail-open, a lost record. | noise, gaps |
| **claimable** | A containment figure is claimable only when residue is zero. | proven, verified, clean |
| **scope-true** | Rendered material containing exactly what a role's scope reaches and nothing else. | filtered, scoped, redacted |
| **hardened** | A loop whose partition has been built and executed against a live window, with the result recorded. | validated (one of three *status* values), tested |

### Words that mean one thing only, now

- **plane** — a product plane. One of three. Nothing else.
- **world** — *retired entirely.* It previously meant a bound region, a
  possible-worlds reasoning space, and an MCP server. The server is now
  `maxey0-context`; the bound region is a **region**; the reasoning sense
  survives only inside vendored skill titles, which are data, not product copy.
- **harness** — the SCW runtime object created by `context_harness_create`.
  The experiment runner has left the product (§6), so the collision is gone.
- **designer** — the Studio's **Designer** view. Cross-window loop ids keep
  their historical `designer:NN-slug` form because they are data already
  written to disk; they are read as ids, never as the view.

---

## 3. Tool names

**Rule: every tool name begins with its plane.** `context_`, `loops_`, or
`observe_`. No exceptions, and no `maxey0_`-prefixed tool on a server not
named `maxey0`.

Within a plane: `<plane>_<object>_<verb>`, or `<plane>_<verb>` when there is no
object. Verbs are bare (`create`, not `create_new`); objects are singular.

### Context plane — 32 tools

| canonical | was |
|---|---|
| `context_prompt_create` | `create_prompt` |
| `context_prompt_revise` | `revise_prompt` |
| `context_prompt_render` | `render_prompt` |
| `context_region_create` | `create_scw` |
| `context_region_close` | `close_scw` |
| `context_region_write` | `write` |
| `context_region_read` | `read` |
| `context_harness_create` | `create_harness` |
| `context_harness_call` | `harness_call` |
| `context_scope_bind` | `bind_scope` |
| `context_scope_unbind` | `unbind_scope` |
| `context_scope_closure` | `scope_closure` |
| `context_scope_tick` | `loop_tick` |
| `context_bridge_open` | `open_bridge` |
| `context_bridge_close` | `close_bridge` |
| `context_bridge_promote` | `promote` |
| `context_criterion_pin` | `pin_criterion` |
| `context_criterion_repin` | `repin_criterion` |
| `context_evidence_attest` | `attest_evidence` |
| `context_window_inspect` | `inspect_window` |
| `context_window_render` | `render_window` |
| `context_window_disjointness` | `check_disjointness` |
| `context_window_seal` | `seal_window` |
| `context_window_reset` | `reset_window` |
| `context_assert_can_read` | `assert_can_read` |
| `context_assert_cannot_read` | `assert_cannot_read` |
| `context_assert_scope_closed` | `assert_scope_closed` |
| `context_assert_disjoint` | `assert_disjoint` |
| `context_route_bind` | `route_task` — scores **and** binds |
| `context_formation_build` | `create_concept_scw` |
| `context_admit` | *new — the egress gate for a declared handoff; approve, summarize, redact, or reject what crosses* |
| `context_assert_admitted` | *new — finds a handoff a scope permits that no `context_admit` decision has ever governed* |

The four assertions and the two route tools lived on `observe`/`loops` in an
earlier draft of 0.7.0, under their bare legacy names. Both moved to
`context` for the reason ARCHITECTURE.md gives: the window is process-local
state, so a tool that reads or writes it — including a real read that proves
containment, and a routing decision that commits — has to live in the
process that owns the window.

### Loop plane — 10 tools

| canonical | was |
|---|---|
| `loops_menu` | *new — the control surface, rendered from the registry* |
| `loops_concepts` | `maxey0_concepts` |
| `loops_skills` | *new — the 83 skills were reachable only through the manifest* |
| `loops_agents` | `maxey0_agents` |
| `loops_catalog` | `maxey0_loops` |
| `loops_route` | `maxey0_route` — scores, binds nothing |
| `loops_crosswindow_create` | `maxey0_cross_window_create` |
| `loops_crosswindow_status` | `maxey0_cross_window_status` |
| `loops_crosswindow_ingest` | `maxey0_cross_window_ingest` |
| `loops_crosswindow_report` | `maxey0_cross_window_report` |

`loops_route` and `context_route_bind` are the same question on different
planes; only the second commits, because committing means writing the window.

### Observatory plane — 8 tools

| canonical | was |
|---|---|
| `observe_events` | `maxey0_observe` |
| `observe_attempts` | `maxey0_access_attempts` |
| `observe_traces` | `maxey0_traces` |
| `observe_gate_mode` | `gate_mode` |
| `observe_gate_policy` | `declare_gate_policy` |
| `observe_gate_activity` | `gate_activity` |
| `observe_isolation_level` | `isolation_level` |
| `observe_studio` | `maxey0_studio` |

**50 tools across three connectors.** The legacy names are gone, not aliased:
an alias would double the surface and let the old vocabulary survive in
transcripts, which is the drift this version exists to end.

### One parameter rename

`loop_id` carried a **role** name in every scope-bound call. It is `role`
everywhere in the plane servers. The vendored runtime keeps its own parameter
name; the plane facade translates.

---

## 4. Command names

`/<connector>:<verb>` or `/<connector>:<noun>`. One word, lowercase, no hyphens
unless the canonical noun has one.

| command | connector | does |
|---|---|---|
| `/maxey0:menu` | all three | The control surface, rendered from `loops_menu` |
| `/maxey0:doctor` | all three | What is up, what is down, what is missing |
| `/maxey0:window` | Context | Inspect or partition this session's window |
| `/maxey0:route` | Loop | Route a task and report the decision, binding nothing |
| `/maxey0:run` | Loop | Route, bind, dispatch every role, close out |
| `/maxey0:crosswindow` | Loop | Run a cross-window topology |
| `/maxey0:gate` | Observatory | Read or set gate mode, declare a role's reach |
| `/maxey0:assert` | Observatory | Test containment by attempting a real read |
| `/maxey0:studio` | Observatory | Start the Studio and hand over its address |

Installed as a single plane, the same commands appear under that plane's own
prefix — `/maxey0-context:window`, `/maxey0-loops:run`, `/maxey0-observe:gate`.

**Retired:** `/maxey0:scw` (→ `window`), `/maxey0:loop` (→ `run`),
`/maxey0:cross-window` (→ `crosswindow`), `/maxey0:experiment-run` (→ out of
the product; see §6).

---

## 5. The nine Studio views

Named once, here. Every document, command and manifest that lists views copies
this table and nothing else.

| view | shows |
|---|---|
| **Overview** | Route a task in plain language and watch the decision |
| **Mission Control** | Walk concept → skill → agent → dispatch against the live window |
| **Concepts** | The 16 concepts and their loop coverage |
| **Loops** | All 84, filterable, each with its hardening record |
| **Designer** | Compose a formation and harden it before it can be saved |
| **Window** | The region map, read through any role's scope |
| **Semantic** | Concepts, skills and agents placed in the anchor field, in 3D |
| **Gate** | What the delegated agents actually did, per role |
| **Evidence** | Containment assertions, the event stream, isolation level |

**Retired:** the *Experiment* view (§6). **New:** *Evidence*, which gives the
four assertion tools and the two stream tools a surface they never had.
*SCW Window* is now *Window*; *Semantic 3D* is now *Semantic*.

---

## 6. What is no longer part of the product

**The experiment harness.** `docs/ROADMAP.md` has said since 0.3.0 that
experiment protocol, conditions, probes, analysis and reports belong in a
consumer repository, not here — and then shipped `/maxey0:experiment-run`, an
Experiment view, six HTTP routes and four workload specs anyway. A measurement
instrument that ships the study it was used for is not a product; it is a lab
notebook with an installer.

The harness code is intact and moves to the `maxey0-lab` connector, listed in
the marketplace as **research tooling, not part of the product**. It installs
separately, by choice, and nothing in the three planes depends on it.

The one place the word stays is `server/gate/levels.py`, where L0–L3 are
defined by reference to the four conditions they were derived from. That is a
citation, not a dependency.

---

## 7. Models

The product hard-codes no model. The two role agents ship `model: inherit`, so
a dispatched role runs on whatever the session runs on. The Studio's optional
Anthropic client — used only when `ANTHROPIC_API_KEY` is set, and only by the
Mission Control view — reads `MAXEY0_MODEL`, defaulting to `claude-sonnet-5`.

There has never been a Haiku model anywhere in this repository. That was
verified for 0.7.0 across the source tree, the built archives, and the full git
history.

---

## 8. Enforcement

```bash
python scripts/check_lexicon.py
```

Fails on: any retired tool name outside this file's migration tables; any
retired noun in product copy; any list of Studio views that disagrees with §5;
any `maxey0_`-prefixed tool name; any plane word used for a stratum. Run by
`scripts/validate_plugin.py`, so a lexicon regression fails the same gate a
broken import does.
