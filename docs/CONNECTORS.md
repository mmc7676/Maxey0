# Connectors — what runs, where, and how it is configured

Maxey0 installs as **three MCP connectors and one hook**, plus a local HTTP
application you start yourself.

A connector is not a plane. A plane is what the system is — Execution, Context,
Engineering — and Maxey0 owns two of the three. A connector is what installs,
and two of them serve the same plane. See
[ARCHITECTURE.md](ARCHITECTURE.md) for why the split falls where it does.

| connector | serves |
|---|---|
| `maxey0-context` | Context plane — the state machinery |
| `maxey0-loops` | Context plane — the semantic machinery |
| `maxey0-observe` | Engineering plane |
| *(none)* | Execution plane, owned by the host |

| component | kind | entry point | tools | writes |
|---|---|---|---|---|
| `maxey0-context` | MCP over stdio | `server/context_server.py` | 32 | the ledger, `~/.scw/events.jsonl` |
| `maxey0-loops` | MCP over stdio | `server/loops_server.py` | 10 | nothing |
| `maxey0-observe` | MCP over stdio | `server/observe_server.py` | 8 | the Gate journal, `~/.scw/gate.jsonl` |
| the Gate | hook, one process per tool call | `server/gate/adapters/claude_code.py` | — | the Gate journal |
| the Studio | HTTP on `127.0.0.1:7676` | `server/run_studio.py` | — | its own window, `~/.scw/studio.jsonl` |

This replaces the 0.6.0 topology, which was two connectors whose names described
how the code had grown rather than any boundary a user could act on. Tools
prefixed for one connector were registered on the other, the Gate's control
surface was fused into the enforcement engine, and installing the engine without
the loop library was not a choice the packaging offered. See
[LEXICON.md](LEXICON.md) for the full migration table.

---

## What decides which connector a capability belongs to

> The **Context** plane holds bytes and refuses reads.
> The **Loop** plane decides who should act and in what shape.
> The **Observatory** records what actually happened and refuses what left scope.

Underneath that, one mechanical fact does most of the work: **the window is
process-local state.**

A tool in a different process acts on a different window. So every tool that
reads or writes the live window has to live on the Context plane, and two
consequences follow that look surprising until you see why:

- **The four containment assertions are Context tools**, not Observatory ones.
  They are the sharpest evidence in the product precisely because they perform a
  real read through the real authorization path — and that read has to happen in
  the process that owns the window.
- **`context_route_bind` is a Context tool** even though routing is the Loop
  plane's subject. `loops_route` scores a task and explains the decision;
  `context_route_bind` asks the same question and commits. One reads, the other
  writes the window.

And one consequence that is the whole point:

- **The Observatory holds no window at all.** It reads the ledger from disk, and
  replays it into a window when it needs the region graph rather than a record
  list. That gives it every scope and every closure while leaving it
  structurally unable to write any of them.

---

## `maxey0-context` — the window, and its only writer

32 tools, grouped:

**Prompt (3)** — `context_prompt_create`, `context_prompt_revise`,
`context_prompt_render`. The instruction held as versioned data rather than as
prose in a script.

**Region (4)** — `context_region_create`, `context_region_close`,
`context_region_write`, `context_region_read`. Regions and the bytes in them.
Pass `role` and the call is checked against that role's scope; omit it and you
are the host.

**Harness (2)** — `context_harness_create`, `context_harness_call`. The
architecture a loop runs under, including `maker_checker`, which makes
self-approval a refusal rather than a policy.

**Scope (4)** — `context_scope_bind`, `context_scope_unbind`,
`context_scope_closure`, `context_scope_tick`. Binding a role to a region,
computing what that reaches, pricing each iteration, and closing with a terminal
state that has to be earned.

**Bridge (3)** — `context_bridge_open`, `context_bridge_close`,
`context_bridge_promote`. The only legitimate way across a region boundary,
minted explicitly and recorded.

**Evidence (3)** — `context_criterion_pin`, `context_criterion_repin`,
`context_evidence_attest`. Freezing what a run will be graded against, and
recording external results.

**Window (5)** — `context_window_inspect`, `context_window_render`,
`context_window_disjointness`, `context_window_seal`, `context_window_reset`.
The audit surface, plus lifecycle. `context_window_reset` is destructive.

**Assertions (5)** — `context_assert_can_read`, `context_assert_cannot_read`,
`context_assert_scope_closed`, `context_assert_disjoint`,
`context_assert_admitted`.

**Route (2)** — `context_route_bind`, `context_formation_build`.

**Admit (1)** — `context_admit`. Bridges and scope are ingress: what a role
may reach. This is egress: what a role's own output is allowed to become once
it exists — approve, summarize, redact, or reject a declared handoff, with
every outcome, including reject, recorded. See
[ARCHITECTURE.md](ARCHITECTURE.md#egress-context_admit).

### The assertions, and why two are stronger

`context_assert_can_read` and `context_assert_cannot_read` **do not compute set
membership.** They perform a real read through the real authorization path. A
refusal is produced by the enforcement layer, lands in the ledger as a
`scw.denied` record, and replay reproduces it. They report
`evidence.pure: false` — meaning the evidence is not a computation.

`context_assert_scope_closed`, `context_assert_disjoint`, and
`context_assert_admitted` are computations — the first two over the region
graph, the third over the ledger's recorded `context_admit` decisions rather
than a new attempt. All three report `evidence.pure: true`. That is not a
defect; it is a different and weaker claim, and the result says so rather
than letting a reader assume otherwise.

A `breach: true` from `context_assert_cannot_read` is a headline finding, not a
soft negative: the runtime authorized a read it was expected to refuse.

---

## `maxey0-loops` — the library, and no window at all

10 tools: `loops_menu`, `loops_concepts`, `loops_skills`, `loops_agents`,
`loops_catalog`, `loops_route`, and the four `loops_crosswindow_*` runners.

This connector opens no ledger, creates no `~/.scw/`, and writes nothing except
cross-window run files under `experiments/cross-window/`. That is what makes it
genuinely installable alone: you get routing, the full library, and the
cross-window runner against an entirely fixed context scheme.

`loops_menu` is new, and so is `loops_skills`. Through 0.6.0 the menu was a
296-line prompt instructing the model to render the surface from a tool call,
whose fallback when the call failed was the prose in the file — so with the
connectors down it transcribed its own instructions. It is now a function over
`server/planes/catalog.py`. And the 83 skills were the one level of the library
with no tool: concepts, agents and loops were each browsable, and the skills
between them were reachable only by reading the manifest.

### Cross-window is a topology, not a partition

One genuinely separate model call per participant, zero shared token buffer, no
region to bind. Isolation comes from what the operator puts in each prompt.

`loops_crosswindow_report` checks it by grepping every dispatched prompt for the
other participants' markers — real leak detection over the actual text. A leak
it finds is the finding, not a bug to quietly fix and rerun.

---

## `maxey0-observe` — the Gate, and evidence read from disk

8 tools: `observe_events`, `observe_attempts`, `observe_traces`,
`observe_gate_mode`, `observe_gate_policy`, `observe_gate_activity`,
`observe_isolation_level`, `observe_studio`.

**The Gate is not a server.** It is a hook: a short-lived process Claude Code
spawns on `PreToolUse`, `PostToolUse`, `SubagentStart` and `SubagentStop`. It
has no MCP connection and no window. This connector is its *control surface* —
the only way to declare a policy or read its journal from a session.

A policy is declared by the **host, before dispatch**, and deliberately not by
the role it governs: a party that can widen its own scope satisfies any
containment rule vacuously.

### Why the journal is a separate file

`~/.scw/gate.jsonl` is chained independently of `~/.scw/events.jsonl`. A second
writer on the runtime's ledger permanently destroys its chain, and the Gate
writes from a different process at unpredictable moments. Two chains, verified
separately, correlated by anchor rather than by wall clock.

### Standalone value

The Gate stands at every tool call in every session, whether or not anything has
been partitioned. Installed alone, this connector attributes and can refuse any
delegated agent's tool calls — global workspace semantics — with no window and
no library.

When there is no ledger to read, it says so. "No evidence was recorded" and "the
evidence says nothing happened" are different claims, and the tools refuse to
collapse them: `observe_events` returns `present: false`, and `contained` is
three-valued with **null meaning nothing was attempted**.

---

## Two hosts

| | Claude Code | Claude Desktop |
|---|---|---|
| Context and Loop tools | yes — separate processes | yes — one process, the `.mcpb` bundle |
| Region isolation on every scoped call | yes | yes |
| Hash-chained ledger, replay, disjointness proof | yes | yes |
| The Studio | yes | yes |
| Slash commands, skills, role agents | yes | — |
| **The Gate** (`observe_gate_*`) | **yes** | **—** |

The Gate needs two things from its host: a hook system to intercept a tool call,
and delegated subagents whose calls there are to intercept. A Desktop extension
declares an MCP server and nothing else — `manifest.json` has no hooks field —
and Desktop does not dispatch subagents.

So this is not an unfinished port. On a host that dispatches no roles there is
nothing to attribute, and shipping the Gate's tools there would let a run report
an empty journal as though it were evidence of containment.

**The bundle presents one server, not three.** An MCPB manifest declares exactly
one, so `server/mcpb_entry.py` registers the union onto a single instance —
re-registering the same function objects rather than reimplementing them, so
there is one implementation of each tool in this codebase and not two that can
drift.

---

## Configuration

| variable | read by | default |
|---|---|---|
| `MAXEY0_ROOT` | all three | `server/vendor/maxey0` |
| `MAXEY0_LOOPS` | Context, Loop | `server/vendor/data/loops.json` |
| `SCW_EVENT_LOG` | Context, Observatory | `~/.scw/events.jsonl` |
| `SCW_HOME` | the Gate | `~/.scw` |
| `SCW_RUNTIME_SRC` | all | the vendored copy |
| `MAXEY0_GATE_MODE` | the Gate | `observe` — pins the mode when set |
| `MAXEY0_GATE_LOG` | the Gate | `~/.scw/gate.jsonl` |
| `MAXEY0_GATE_STATE` | the Gate | `~/.scw/gate/` |
| `MAXEY0_GATE_SESSION` | Observatory | unset — the run-wide default file |
| `MAXEY0_STUDIO_PORT` | Studio, Observatory | `7676` |
| `MAXEY0_MODEL` | Studio only | `claude-sonnet-5` |
| `ANTHROPIC_API_KEY` | Studio only | unset — dispatch simulates |

### Point separate installs at separate logs

Two installations sharing one ledger interleave two runs into one chain. Set
`SCW_EVENT_LOG` per install.

### The vendored runtime, and what can shadow it

`server/vendor/` exists so the plugin installs standalone, and
`scripts/sync_vendor.py` is the only thing allowed to write it.

A developer with `pip install -e` of the same runtime breaks that in a way path
ordering cannot fix: modern editable installs register a `MetaPathFinder`, and
`sys.meta_path` is consulted **before** `sys.path`. The plugin then silently
runs code it did not ship, and a drift check that passes proves nothing.

`server/planes/bootstrap.py` removes those finders unless `SCW_RUNTIME_SRC` is
set — that variable is the supported way to say "use my checkout on purpose".
`/maxey0:doctor` reports which copy actually loaded, because "the vendored copy"
is a claim about the import system, and the import system is exactly what an
editable install changes.

---

## When a connector will not start

The host reports `CONNECTION_CLOSED` and nothing else, so work through these in
order.

**1. A stale entry in your own MCP config.** A connector name in
`~/.claude.json` or a project `.mcp.json` shadows the plugin's. If its `args`
point at a path that no longer exists, Python exits immediately and the host
reports exactly the same failure as a broken plugin. This is the most common
cause and has nothing to do with the plugin.

**2. `python` resolving to the wrong thing.** The manifests use bare `python`.
On Windows the Microsoft Store App Execution Alias can win PATH resolution and
exits with no stderr at all.

**3. `mcp` missing from that interpreter.** `server/_preflight.py` writes an
actionable message to stderr and exits 1 — which the host still reports as
`CONNECTION_CLOSED`, because the message only reaches the MCP log.

**4. The ledger cannot be opened.** The Context plane opens
`~/.scw/events.jsonl` for append while starting, rather than on first use, so a
run can never be half-recorded. A read-only home, a roaming-profile lock, or
antivirus holding the handle kills the process during import.
`server/planes/bootstrap.py` names the path and the cause on stderr and suggests
`SCW_EVENT_LOG`. The Loop plane needs no ledger and starts regardless — which is
itself a useful diagnostic.

`/maxey0:doctor` checks all four.

---

## Which connector am I talking to?

Read the prefix. Every tool name begins with its plane: `context_`, `loops_`,
`observe_`. There are no exceptions and no aliases — see
[LEXICON.md](LEXICON.md) for the migration table from 0.6.0.
