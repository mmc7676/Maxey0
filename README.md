# Maxey0-SuperSpace

Maxey0-SuperSpace (Maxey0 for short) is a governance and evidence layer for
multi-agent work. It gives each agent's working context a name the system can
enforce. It decides every crossing between those contexts, and every prompt sent
to a model provider through it, before the crossing happens. It writes each
decision, allowed or refused, to a hash-chained record, so an edit to the record
can be detected afterward. Maxey0 does not run agents or add agent capability.
Your host (Claude Code, LangGraph, OpenAI Agents, Google ADK and others) still
runs the agents. Maxey0 controls and records what they could see and what they
reached for, to the extent the table under
[What each install can answer](#what-each-install-can-answer) shows.

---

## The problem

**Who it is for:** teams that hand work to more than one agent. That includes
Claude Code subagents, maker/checker/judge formations, and agents built on
frameworks such as LangGraph, OpenAI Agents or Google ADK. How much Maxey0 can
see differs a great deal between these hosts, so read the coverage table below
before you choose.

After a run, those teams have to answer four questions:

1. What could each agent see?
2. What did each agent try to reach?
3. What left the machine for a third-party model?
4. Can anyone prove the record was not edited afterward?

Two secondary questions follow from these: can the run honestly claim it was
isolated, and has the work wandered from where it started?

Without a layer like this, there is usually no good answer:

- **The context has no name.** It is a string assembled just before each call,
  so nothing can enforce who reads it.
- **Delegated work is invisible.** A subagent's file reads and tool calls happen
  where no log can see them. `docs/ARCHITECTURE.md` records a measurement of 115
  real subagent tool calls that produced zero entries in the context log.
- **Prompts leave unrecorded.** A prompt goes to a model API and nothing notes
  what went where.
- **"Isolation" is only a request.** Telling an agent not to look in a prompt
  is not a boundary.
- **The record can be rewritten.** After an incident you have the outputs, not
  the reach, and a plain log file can be quietly edited.

### What each install can answer

Maxey0 ships as a Claude Code plugin and as a Python package (see
[Quick start](#quick-start)). Each answers a different part of the four
questions.

| Question | Claude Code plugin | Python package, with your own framework | Claude Desktop bundle |
|---|---|---|---|
| 1. What could each agent see? | **Yes**, for roles dispatched through a partition. Each role is bound to its own regions of the session's window, and region reads outside its scope are refused by code. What the orchestrating model pastes into a subagent's prompt is observed, not enforced. | **Partial.** Containment decides and records every read your code asks about. It does not hold your agents' content or see reads your code does not ask about. | **Partial.** The context tools partition the window, but Claude Desktop dispatches no subagents, so there are no separate agents to keep apart. |
| 2. What did each agent try to reach? | **Yes.** The Gate sees every tool call, including subagents' calls. | **No.** Adapters do not intercept a framework's tool calls, and the Gate needs Claude Code's hooks. | **No.** Claude Desktop runs no hooks, so the Gate does not run. |
| 3. What left the machine? | **No.** A subagent's model calls go through Claude Code, not through Maxey0. | **Partial.** Only calls you send through `maxey0_ss.providers`: single-turn text completions (a prompt, an optional system prompt, `max_tokens`, `temperature`) to Anthropic, OpenAI or Hugging Face. There is no message list, tool use or streaming, so a framework agent's own model calls cannot practically go through them. | **No.** |
| 4. Can anyone prove the record was not edited? | **Yes, with Maxey0's own tools.** The context ledger and the Gate journal are hash-chained files. No standalone verifier ships for them. | **Yes, offline.** The attestation log verifies from exported records alone. It is in memory, so it is lost on restart. | **Partial.** The context ledger is written and can be verified; there is no Gate journal. |

Every record is tamper-evident, not signed: it shows that nothing was changed
inside the chain, not who wrote it.

---

## How Maxey0 solves it

Maxey0 sits at the boundaries, where an agent's request becomes visible, and
does three things there: it **names**, it **decides**, and it **records**.

| Concept | What it is | Question it answers |
|---|---|---|
| **SCW (Structured Context Window)** | A named, enforceable context for an agent. In the Python package, each role gets an SCW such as `SCW1`, with running instances such as `SCW1@scw-runtime-0`, all chartered under the root window, **SCW0**. In the plugin, the session's window is divided into typed regions and each role is bound to its own (see [below](#what-scw-means-in-each-install)). | 1. What could each agent see? |
| **Containment** | Structural rules, enforced by code rather than requested in a prompt, that decide which window may read, write, bridge to or spawn another, and which may send data out. It fails closed. | 1. What could each agent see? |
| **The Gate** | A component that stands at every tool call in Claude Code, including subagents' calls. It attributes each call to a role, records it, and in `enforce` mode refuses calls outside that role's declared scope. | 2. What did each agent try to reach, including files and the shell? |
| **Egress gating** | Model calls made through Maxey0's providers (Anthropic, OpenAI, Hugging Face) are admitted and recorded before any byte leaves. The prompt is recorded only as a digest. | 3. What left the machine, for calls made through these providers? |
| **Hash-chained records** | The attestation log, the context ledger and the Gate journal (see [below](#three-records-three-names)). Each entry's digest covers the previous one. | 4. Was the record edited? |
| **Isolation levels (L0–L3)** | A level that a run earns from recorded evidence, with any shortfall named. | Secondary: can this run honestly claim it was isolated? |
| **Semantic drift** | The distance between a window's current state and a baseline you anchored, with a threshold. | Secondary: has this window's work wandered? |

### What "SCW" means in each install

The name covers two arrangements, and the difference matters for question 1.

- **In the Claude Code plugin**, the SCW is this session's **window**, divided
  into typed **regions**. Each role is bound to a **scope**, usually its own
  scratchpad plus one durable region to publish into, and it sees only what
  `context_window_render` returns for it.
- **In the Python package**, each role gets its own SCW specification (`SCW1`)
  and running instance (`SCW1@scw-runtime-0`), and containment decides between
  instances.

The region types in the plugin (from `/maxey0:window partition`):

| Type | Mutability | Bridgeable | For |
|---|---|---|---|
| `reference` | read-only | yes | Instructions, source material, a pinned rubric. The host writes it before any role is bound. |
| `durable` | writable | yes | What should survive the run, such as a published draft |
| `episodic` | writable | yes | Run history and promoted findings |
| `working` | writable | no | Task state nothing else may reach |
| `scratchpad` | volatile, cleared each tick | no | A role's own reasoning |

### Three records, three names

| Record | Install | Where it lives | What writes to it | How to check it |
|---|---|---|---|---|
| **Attestation log** | Python package | In memory, in one process. Export it with `system.context.isolation.log.export()` or `maxey0-ss.evidence.attestations`. | Every containment decision, egress admission and completed egress | `AttestationLog.verify_records(records)` offline, or `maxey0-ss.evidence.verify` |
| **Context ledger** | Claude Code plugin and the Claude Desktop bundle | `~/.scw/events.jsonl` on disk (`SCW_EVENT_LOG` overrides it) | The context tools: regions, bindings, bridges, routing decisions and refusals | `/maxey0:window verify` checks the chain and that replaying the ledger rebuilds the same window |
| **Gate journal** | Claude Code plugin | `~/.scw/gate.jsonl` on disk (`MAXEY0_GATE_LOG` overrides it) | The Gate's hooks, one record per intercepted tool call | `/maxey0:gate status` reports the chain check (from `observe_gate_activity`) |

All three are SHA-256 hash chains. Only the attestation log has a verifier that
runs from exported records alone. The context ledger and the Gate journal are
checked with Maxey0's own tools.

### Terms used in this README

| Term | Meaning |
|---|---|
| **charter, constitution** | In the Python package, every SCW specification is *chartered* (registered) under a parent, and the root is SCW0. Its *constitution* is the set of rules it gets from that parent: its reach, whether it may be bridged, and optional depth and child caps. A child's constitution can only be narrower than its parent's. |
| **reach** | Two uses. In a constitution, the set of SCWs a window may name at all. In Gate reports, what a role tried to touch: files, tools and the shell. |
| **region, scope** | In the plugin, a region is one typed subdivision of the session's window. A role's scope is the set of regions it may read or write, declared when the role is bound. |
| **bind, render, seal** | Binding attaches a role to its scope. Rendering returns exactly what a role's scope reaches and nothing else ("scope-true" material). Sealing ends setup, after which no unbound caller can write the window. |
| **bridge** | An explicit, recorded grant that lets one window (Python) or scope (plugin) read something outside it. In the plugin, a bridge expires after a set number of ticks. |
| **disjoint** | Two roles are disjoint when nothing private is reachable by both. `/maxey0:assert disjoint` checks it in the plugin; `iso.assert_private_disjoint(a, b)` checks it between two Python windows, counting open bridges. |
| **formation** | A set of roles and the shape they are arranged in, such as maker/checker/judge. |
| **concept, skill, agent, loop** | The routing library: 16 concepts (subject areas), 83 skills (capability definitions, each owned by a concept), 67 agents (registry entries a loop stage names) and 84 loops. A loop is a formation plus its partition plus the record of building and running it. |
| **residue, claimable** | Residue is anything that prevents a containment claim: a call the Gate could not tie to a role (`unattributed`), a call it let through without evaluating (`fail_open`), or a lost journal record. A containment figure is claimable only when residue is zero, which `containment.claimable` reports. |
| **unmeasured** | A role with no declared Gate policy. Its calls are recorded with the reason `no_policy`, so nothing about its scope is measured. |
| **declared outputs** | What a formation says each role hands back, such as a published draft. `L3_observed` requires evidence that only these crossed back. |
| **H0–H3** | How much a host can do at a tool call. H3 enforces and names the actor natively (Claude Code). H2 enforces, with attribution by working directory. H1 observes only. H0 cannot intercept. These are separate from the isolation levels L0–L3, which describe what a run achieved. |

---

## Quick start

Two different things ship in this repository. Pick the one that matches where
your agents run.

| You want | Install | You get |
|---|---|---|
| Governance for **Claude Code** subagents | The Claude Code plugin `maxey0` | Three MCP servers (`maxey0-context`, 32 tools; `maxey0-loops`, 10; `maxey0-observe`, 8), 10 slash commands, the Gate hooks and the Studio |
| Governance for **your own agents**, or a server | The Python package `maxey0-superspace` (import name `maxey0_ss`) | The `maxey0-ss` MCP server (29 tools, over stdio and HTTP), a REST API, A2A routing, harness adapters, gated model providers and the attestation log |

The plugin does not install the 29-tool `maxey0-ss` server, and the Python
package does not install the Gate hooks.

### Claude Code (plugin)

The plugin's servers and hooks run with the `python` on your `PATH`. That Python
needs the MCP SDK:

```bash
python -m pip install mcp pydantic
```

Then, inside a Claude Code session:

```
/plugin marketplace add mmc7676/Maxey0
/plugin install maxey0@maxey0
```

**Restart Claude Code** so the hooks load, then run `/maxey0:menu` or
`/maxey0:doctor`.

The marketplace also offers each server as its own plugin:

| Plugin | Serves | Purpose |
|---|---|---|
| `maxey0@maxey0` | All three planes | All three servers, the Gate hooks, the Studio, 10 commands, 5 agents and 16 concept skills. Recommended. |
| `maxey0-context@maxey0` | Context plane | Partitioned windows and the context ledger (32 tools; the marketplace listing says 30, but the server registers 32). |
| `maxey0-loops@maxey0` | Context plane | Task routing against the loop library (10 tools). Holds no window state. |
| `maxey0-observe@maxey0` | Engineering plane | The Gate and the Studio (8 tools). Installs in `observe` mode, so it does not block a role's out-of-scope calls until you switch to `enforce`. In every mode but `off`, it still refuses a governed role's attempt to change the Gate itself. |
| `maxey0-lab@maxey0` | None | A research harness for running experiments. Not part of the product. It needs the Studio running. |

The 5 agents are the role agents a formation's roles are dispatched as:
`maxey0-maker` (produces the artifact), `maxey0-checker` (verifies it against
the source material), `maxey0-judge` (grades it against a pinned criterion),
`maxey0-role` (any other role) and `scw-deployer` (sets up the default SCW for
a task). The 16 concept skills are one skill per library concept. Each tells
Claude when a task falls under that concept and lists the concept's skills and
loops, so Claude routes with `loops_route` first.

### Python package (Windows, macOS, Linux)

The package is not on PyPI. Install it from a checkout. Python 3.10 or later is
required.

Windows (PowerShell):

```powershell
git clone https://github.com/mmc7676/Maxey0
cd Maxey0
python -m venv .venv
.venv\Scripts\python -m pip install -e .
```

macOS and Linux:

```bash
git clone https://github.com/mmc7676/Maxey0
cd Maxey0
python -m venv .venv
.venv/bin/python -m pip install -e .
```

The editable install (`-e`) is what the rest of this README assumes: the
scripts in `scripts/` and the tests run from the checkout, and the checkout's
`.env` is read wherever you start the server. A non-editable install, including
`pip install git+https://github.com/mmc7676/Maxey0`, also serves all 29 tools
and the built MCP App, which it carries in `maxey0_ss/_bundled/`. It reads
`.env` and `config/credentials.json` from the **current working directory**
when it is imported. Starting `maxey0-ss-mcp` in a folder that holds another
project's `.env` therefore loads that file's keys and `MAXEY0_*` settings.
Variables already set in the environment win over the file.

Optional extras add a framework for a harness adapter: `claude-agent-sdk`,
`openai-agents`, `langchain`, `google-adk`, `microsoft`, `nvidia` and
`all-harnesses`. `graph` installs `networkx`, which no code in this build
imports. `all` installs everything. For example: `pip install -e ".[langchain]"`.

After installing you have these commands:

| Command | What it starts |
|---|---|
| `maxey0-ss-mcp` | The MCP server over stdio, for a host that launches it |
| `maxey0-ss-public` | The HTTP server (MCP, REST, health) on `127.0.0.1:8765` unless `MAXEY0_HOST` / `MAXEY0_PORT` say otherwise. It applies the proxy and rate-limit rules described under [Security and privacy](#security-and-privacy). |
| `maxey0-ss`, `maxey0-ss-api` | Aliases of `maxey0-ss-public`: the same HTTP app, the same `MAXEY0_HOST`/`MAXEY0_PORT` settings and the same proxy handling. |

To use the stdio server from Claude Code: opening Claude Code inside the checkout
on Windows picks up `.mcp.json`, which launches `.venv/Scripts/maxey0-ss-mcp.exe`.
On macOS or Linux, register it yourself:
`claude mcp add maxey0-ss -- /path/to/Maxey0/.venv/bin/maxey0-ss-mcp`.

### Claude Desktop

No prebuilt bundle is in the repository. Build one from a checkout with the
package installed:

```bash
python scripts/build_package.py --check   # validate, write nothing
python scripts/build_package.py           # writes dist/maxey0-0.3.0.mcpb
```

The built MCP App (`mcp_apps/super_space_react/dist/mcp-app.html`) is in the
repository. Rebuild it (requires Node.js) only after changing its `src/`:
`cd mcp_apps/super_space_react && npm ci && npm run build`.

Install the `.mcpb` file through Claude Desktop's extension settings. The bundle
serves 47 tools (32 context, 10 loops and 5 of the 8 observe tools). Claude
Desktop runs no hooks and dispatches no subagents, so **the Gate does not run
there**. Building the bundle is checked; installing it inside Claude Desktop is
not covered by this repository's checks.

### Other hosts

| Host | How | Status |
|---|---|---|
| Codex | Install the package, then append `distributions/codex/config.toml` to `~/.codex/config.toml`. It runs `python -m maxey0_ss.mcp_stdio_server`, so point `command` at the Python that has the package installed. | Not exercised against Codex itself |
| ChatGPT | Manifests are in `distributions/chatgpt-app/`. Add the server under Settings, Connectors, with a server URL and a bearer token. | Listing is a platform action. ChatGPT behavior, including whether it accepts a bearer token this way, is not verified. |
| Claude custom connector | `distributions/claude-remote-connector/`. Use a `/mcp/session` URL (see [Running your own server](#running-your-own-server)), not the `/mcp` value in `connector.json`. | Manifest only |

All install targets are generated from one registry. See
`distributions/DISTRIBUTION_MATRIX.md`, and check it with
`python scripts/build_distributions.py --check` (20 targets: 18 shipped, 2
external).

---

## Solving it, step by step

A worked example. A **maker** agent summarizes a research paper with Claude, a
**checker** verifies the summary's claims, and a **judge** grades the result.
Later an auditor asks three questions. Could the maker read the checker's work?
Did any prompt leave after the maker was finished? Has the log been edited?
The auditor would like to check the answers without trusting Maxey0.

### Path A: Claude Code subagents

Install the Claude Code plugin first (see [Quick start](#quick-start)).

1. **Restart Claude Code** after installing, so the Gate's hooks load. Run
   `/maxey0:doctor` to see what loaded.
2. **Preview the formation.** `/maxey0:route summarize a research paper and
   verify the claims` binds nothing and reports what the library has for the
   task. For this task it names the validated loop
   `battery:l1-maker-checker-judge`, with the roles `maker`, `checker` and
   `judge`. When nothing in the library matches a task, the command says so,
   and `/maxey0:run` then builds the partition by hand and reports that it did.
3. **Choose the Gate mode.** `/maxey0:gate enforce` blocks out-of-scope calls.
   The default, `observe`, records the same findings without blocking, which
   measures what roles *would* reach for. `/maxey0:run` may also set the mode,
   and its report says which mode the run used.
4. **Run the task.** `/maxey0:run summarize a research paper and verify the
   claims` routes the task and binds the formation. The bound roles get
   per-run names such as `route1-maker`. It then writes the source material you
   supply into a read-only reference region, declares each role's Gate policy,
   dispatches one subagent per role in order, and reports each role's output
   and every refusal.
5. **Read what happened.** `/maxey0:gate activity` shows, per role, what it
   reached for, what was allowed and what was refused, and whether the run's
   containment claim holds (`containment.claimable`). `/maxey0:gate level`
   shows which isolation level the evidence supports.
6. **Check the ledger.** `/maxey0:window verify` confirms that the hash chain
   verifies and that replaying the ledger rebuilds the same window.
7. **Hand over the evidence.** The run's records are two files: the context
   ledger, `~/.scw/events.jsonl`, and the Gate journal, `~/.scw/gate.jsonl`
   (see [Three records, three names](#three-records-three-names)). No standalone
   verifier ships for these two files, so an auditor checks them with Maxey0's
   own tools: `/maxey0:window verify` for the ledger and `/maxey0:gate status`
   for the journal. Only the Python attestation log (Path B) has
   a verifier that works from exported records alone.

**Who declares each role's policy.** `/maxey0:run` declares a policy for each
role just before dispatching it, defaulting to `read_paths=[]` (no file reads in
scope) and a narrow `tools` list. That declaration replaces any policy declared
earlier for the same role in the session, so there is nothing to set up in
advance. If you dispatch roles yourself instead, declare each role's policy
before dispatching it, under its bound name:

```
observe_gate_policy(role="route1-maker", read_paths=["/repo/docs"], tools=["Read"])
```

`/maxey0:gate policy <role>` makes the same call. Its only fixed argument is the
role name, so name the paths and tools in the same message; otherwise it
declares none. A policy of `tools=["Read"]` with `read_paths=[]` grants the Read
tool but no path, so every Read is refused in `enforce` mode and recorded as out
of scope in `observe` mode.

**What is enforced and what is observed.** Code enforces two things in Path A:
a context-tool read or write outside a role's scope is refused and recorded,
and in `enforce` mode the Gate refuses a tool call outside the role's policy.
One thing is observed rather than enforced: the orchestrating model assembles
each subagent's prompt from the render output. `/maxey0:run` tells it to paste
in nothing else and to start the prompt with the `[[scw:role=<role>]]` marker,
and `observe_traces` compares what each role was given with what it then did.

**What Path A answers.** It answers "could the maker read the checker's work?"
(the scopes and the Gate) and "has the log been edited?" (steps 5 to 7). It
does not answer "did any prompt leave after the maker was finished?". In Claude
Code, a subagent's model calls go through Claude Code, not through Maxey0, so
Maxey0 does not see them. Path B answers that question for calls made through
Maxey0's providers.

What the Gate decides, from its decision logic: with a `maker` policy of
`tools=["Read"]` and `read_paths=["/repo/docs"]`, a `Read` of
`/repo/secrets.txt` is denied in `enforce` mode (reason `path_outside_scope`).
In `observe` mode the same call goes through and is recorded with the same
reason. A `Bash` call is denied with `tool_not_granted`.

### Path B: your own agents, in Python

Install the Python package first (see [Quick start](#quick-start)). This script
runs the same story for the maker and the checker; the judge is left out to
keep it short. No network access or API key is needed.

In Python, Maxey0 enforces only where your code asks it to. Your orchestration
code calls the containment checks (`iso.can_read`, `iso.require_read`) before it
moves material between agents, and sends model calls through the gated
provider. Maxey0 decides and records each of those. It does not hold your
agents' content, and it does not intercept anything your code does without
asking. For agents built on another framework, see
[Harness adapters](#harness-adapters).

```python
from maxey0_ss import SuperSpaceSystem
from maxey0_ss.scw_deployer import deploy_default_scw
from maxey0_ss.containment import AttestationLog
from maxey0_ss.providers import registry

system = SuperSpaceSystem()

# 1. Name a window for each role. Both are chartered under SCW0.
system.create_scw(deploy_default_scw("summarize the research paper", scw_id="SCW1"))
system.create_scw(deploy_default_scw("verify the summary's claims", scw_id="SCW2"))

# 2. Start a running instance of each. A harness adapter does this for you.
maker = system.scw_runtime.start("SCW1", "maker")      # SCW1@scw-runtime-0
checker = system.scw_runtime.start("SCW2", "checker")  # SCW2@scw-runtime-0

# 3. The maker tries to read the checker's window: refused, and recorded.
iso = system.context.isolation
print(iso.can_read(maker.id, checker.id))  # False

# 4. The checker needs the maker's draft. Without a bridge it cannot read it;
#    an explicit bridge allows the read, and both steps are recorded.
print(iso.can_read(checker.id, maker.id))  # False
iso.open_bridge(checker.id, maker.id)
print(iso.can_read(checker.id, maker.id))  # True

# 5. The maker is done. Closing its window revokes its registration.
system.context.close(maker.id)

# 6. A late model call from the closed window is refused before any byte leaves.
claude = registry(log=iso.log, containment=iso)["anthropic"]
try:
    claude.complete("summarize the paper", scw_id=maker.id)
except Exception as exc:
    print(type(exc).__name__, exc)  # ProviderRefused ... window is not registered

# 7. The auditor exports the record and checks it without the engine.
records = iso.log.export()
print(AttestationLog.verify_records(records).as_dict())  # ok: True, entries: 9

# 8. Flip one refusal to "allowed" and the chain breaks at that entry.
records[3]["allowed"] = True
print(AttestationLog.verify_records(records).as_dict())  # ok: False, broken_at: 3
```

The recorded chain for this run reads:

| seq | operation | agent_scw → target_scw | allowed | reason |
|---|---|---|---|---|
| 0 | spawn | SCW0 → SCW0 | yes | root chartered with reach [unbounded] |
| 1 | spawn | SCW1 → SCW0 | yes | chartered under the parent constitution |
| 2 | spawn | SCW2 → SCW0 | yes | chartered under the parent constitution |
| 3 | read | SCW1@scw-runtime-0 → SCW2@scw-runtime-0 | **no** | target is outside the declared read set |
| 4 | read | SCW2@scw-runtime-0 → SCW1@scw-runtime-0 | **no** | target is outside the declared read set |
| 5 | bridge | SCW2@scw-runtime-0 → SCW1@scw-runtime-0 | yes | bridge declared between explicit addresses |
| 6 | read | SCW2@scw-runtime-0 → SCW1@scw-runtime-0 | yes | an explicit bridge is open |
| 7 | spawn | SCW1@scw-runtime-0 → itself | yes | instance revoked |
| 8 | egress | SCW1@scw-runtime-0 → anthropic:messages.create | **no** | window is not registered |

Chartering a window and revoking an instance are both recorded as `spawn`
operations. For a charter, `agent_scw` is the new window and `target_scw` is its
parent. "Reach [unbounded]" means SCW0 may name any window, which is the default
(see [What it is not yet](#what-it-is-not-yet)).

**What Path B answers.** All three of the auditor's questions, for what goes
through Maxey0: the maker's refused read (seq 3), the late model call refused
after the maker finished (seq 8), and a chain that verifies from the exported
records alone. The attestation log is in memory and unsigned, so export it
before the process ends.

With `ANTHROPIC_API_KEY` set, a call from an **open** window is admitted, sent,
and followed by an `egress completed` record that carries the model, token
usage, latency and a digest of the prompt. The prompt text itself never appears
in the log.

A longer demo ships with the package: `python -m maxey0_ss.examples.maker_checker_judge`.

---

## Features

Each feature below has a name, a purpose, what it does and how to use it. Tool
names that start with `maxey0-ss.` belong to the Python package's server. Names
such as `context_*`, `loops_*` and `observe_*`, and the `/maxey0:` commands,
belong to the Claude Code plugin.

### Slash commands (plugin)

| Command | What it is for | Example |
|---|---|---|
| `/maxey0:menu [menu\|context\|loops\|observe\|commands\|views\|planes]` | Print the control surface from the registry: planes, servers, tools, commands and Studio views | `/maxey0:menu commands` |
| `/maxey0:doctor` | Health check: which servers are reachable, whether the context ledger exists, the Gate's mode and activity, and which runtime and Python loaded | `/maxey0:doctor` |
| `/maxey0:window [inspect\|partition\|verify\|closure <role>]` | Inspect the session's window (regions, bound roles, bridges), build a partition by hand, verify the ledger's chain and replay, or show what one role can reach | `/maxey0:window verify` |
| `/maxey0:route <task>` | Score a task against the library and report the formation. Binds nothing. | `/maxey0:route summarize a research paper and verify the claims` |
| `/maxey0:run <task>` | Route, bind, declare each role's Gate policy, dispatch every role, and close out with the evidence | `/maxey0:run summarize a research paper and verify the claims` |
| `/maxey0:crosswindow <designer:NN-slug> [run-id]` | Run one of the five cross-window loops: one separate subagent call per participant, with no regions and no shared context. The argument is the loop's id. | `/maxey0:crosswindow designer:01-horizontal-4way` |
| `/maxey0:gate [status\|observe\|enforce\|off\|policy <role>\|activity\|level]` | Read or set the Gate's mode, declare a role's policy, and report what the agents did and which isolation level the evidence supports | `/maxey0:gate activity` |
| `/maxey0:assert [cannot <role> <region>\|can <role> <region>\|closed <role>\|disjoint <role-a> <role-b>\|all]` | Test containment by attempting a real read, rather than asserting it from the region graph | `/maxey0:assert all` |
| `/maxey0:studio [port]` | Start the Studio and hand over its address | `/maxey0:studio 7676` |
| `/maxey0:scw-deploy [task]` | Create the default SCW for a task and report its address, constitution, child-SCW plan and observability contract | `/maxey0:scw-deploy summarize a research paper` |

### Structured Context Windows (SCWs) and SCW0

- **Purpose:** give each agent's working context a name the system can enforce
  and audit, so every read, write and model call can be traced to a window.
- **What it does:** in the Python package, an SCW has a specification (`SCW1`)
  and running instances (`SCW1@scw-runtime-0`). Each specification is chartered
  under its parent, and the root is SCW0, which is chartered automatically. A
  child's reach can only narrow: a request to widen it is refused and recorded,
  not quietly clamped. A `Constitution` can also cap depth, children and
  descendants (`max_depth`, `max_children`, `max_descendants`). The caps are
  off by default, and only Python code can set them; no MCP tool or `/v1` route
  does. The default specification from `deploy_default_scw` describes
  fail-closed isolation, explicit admission and addressed routing, with a drift
  threshold of 0.15. The full address form is
  `scw://<topic>/<concept>/<skill>/<region>/<scw_id>`. In the plugin, the
  session's window is divided into regions instead (see
  [What "SCW" means in each install](#what-scw-means-in-each-install)).
- **How to use:** `maxey0-ss.scw.create {scw_id: "SCW1", task: "...", concept: "..."}`
  creates a specification. `maxey0-ss.scw.describe` lists windows.
  `maxey0-ss.scw.close` closes an instance. Instances are started only from
  Python (`system.scw_runtime.start(spec_id, owner)`) or by a harness adapter;
  no MCP tool starts one. In the plugin, `/maxey0:window` inspects and
  partitions the session's window, and `/maxey0:scw-deploy` creates the default
  SCW for a task.

### Containment

- **Purpose:** enforce which window may touch which, independent of how the
  model behaves.
- **What it does:** decides read, write, disjointness, bridge, spawn and egress.
  An unregistered or closed window is refused. A read outside the declared read
  set is refused. A bridge is an explicit, recorded widening. Closing an
  instance revokes its registration. Every decision is written to the
  attestation log with the name of the provider that decided. `structural` is
  the one provider (`MAXEY0_CONTAINMENT_PROVIDER`); an unknown name is refused.
- **How to use:** in Python, `iso = system.context.isolation`, then
  `iso.can_read(a, b)`, `iso.require_read(a, b)` (raises on refusal),
  `iso.can_write(a, b)`, `iso.assert_private_disjoint(a, b)` and
  `iso.open_bridge(src, dst)`. Your code has to call these; nothing else stops
  a direct read. The plugin's `/maxey0:assert` tests containment by attempting
  a real read.

### Attestation log

- **Purpose:** make the Python package's containment record tamper-evident, so
  a deleted refusal or an edited decision can be detected.
- **What it does:** appends every decision with a sequence number, the operation,
  both windows, the reason and a digest that covers the previous entry. Editing
  a record breaks its digest. Deleting or reordering one breaks the next
  record's link.
- **How to use:** `maxey0-ss.evidence.summary` (counts and whether the chain is
  intact) and `maxey0-ss.evidence.attestations {limit, denials_only}` (the
  records, plus the anchor needed to verify a slice). In Python:
  `system.context.isolation.log.export()`.

### Evidence verification

- **Purpose:** let someone who does not run or trust Maxey0 check an exported
  attestation log.
- **What it does:** recomputes the chain from the records alone and returns
  `ok`, the entry count and the head digest, or `broken_at` and a reason.
- **How to use:** over MCP, `maxey0-ss.evidence.verify {records, anchor_prev_digest, start_seq}`
  using the fields from `evidence.attestations`. Offline, with no server:
  `AttestationLog.verify_records(records, expected_head=..., expected_entries=...)`.
  Pass `expected_head` or `expected_entries` when you have them. Without one of
  them, records removed from the end of the chain go undetected.

### Egress gating (model providers)

- **Purpose:** a prompt leaving for a third party is the largest crossing there
  is. It should be admitted and recorded before it leaves, without the log
  becoming a copy of user data.
- **What it does:** each call is checked twice, in order. First, containment:
  the sending window must be an open, registered instance. Second, the semantic
  admission hook. Both decisions are recorded, and a refusal is recorded before
  it is raised. A successful call adds an `egress completed` record with the
  model, usage, latency and prompt digest. In the log, `allowed` means
  *admitted*; the `egress completed` record is what shows the prompt was
  actually sent. Providers are `anthropic`, `openai` and `huggingface`, called
  over plain HTTPS with no vendor SDK. Each is a single-turn text completion:
  a prompt, an optional system prompt (not for Hugging Face), `max_tokens` and
  `temperature`, with no message list, tool use or streaming. Keys come from
  `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` and `HF_TOKEN`.
- **How to use:** in Python,
  `registry(log=iso.log, containment=iso)["anthropic"].complete(prompt, scw_id=instance_id)`.
  Over MCP, `maxey0-ss.provider.status` shows which providers are configured
  (never the key values), and `maxey0-ss.provider.complete` makes the call. It
  needs an open instance ID, so over MCP alone it is refused (see
  [What it is not yet](#what-it-is-not-yet)).

### The Gate

- **Purpose:** a tool call is the only moment a subagent becomes visible outside
  its context. The Gate stands there to attribute, record and optionally refuse
  what the agent reaches for: files, the shell and tools outside its scope.
- **What it does:** runs on Claude Code's `PreToolUse`, `PostToolUse`,
  `SubagentStart` and `SubagentStop` hooks. For each call it names the role,
  writes the call to the Gate journal (`~/.scw/gate.jsonl`, with personal paths
  and secrets redacted) and decides it against the role's policy. The Gate only
  ever denies or stays silent; it never grants permission. Modes:

  | Mode | Behavior |
  |---|---|
  | `observe` (default) | Records every finding and blocks nothing, except a governed role's attempt to change the Gate |
  | `enforce` | Denies out-of-scope calls; the refusal reaches the model |
  | `off` | Inert; records nothing as checked |

  In `observe` and `enforce`, a call attributed to a role that would change the
  Gate itself is denied, whatever the role's policy grants. That covers
  `observe_gate_mode`, `observe_gate_policy`, the `maxey0-ss.gate.*` setters,
  and writes to the Gate's state files or journal.
  `MAXEY0_GATE_MODE` pins the mode so it cannot be changed from a session.
  Claude Code is host level H3 (enforcement plus native attribution).
  `server/gate/adapters/generic.py` is written for H2 hosts such as Codex CLI
  and Cursor (see `docs/GATE.md`). It has been exercised only with a
  Codex-shaped test payload, not inside Codex or Cursor, and this repository
  ships no hook configuration for those hosts.
- **How to use:** `/maxey0:gate [status|observe|enforce|off|policy <role>|activity|level]`,
  or the `observe_gate_mode` and `observe_gate_activity` tools. From the Python
  package's server: `maxey0-ss.observe.gate_mode`, `maxey0-ss.observe.gate_activity`
  and `maxey0-ss.gate.set_mode {mode}` (admin only).

### Gate policies and attribution

- **Purpose:** declare what each role may reach outside its window. The host
  declares it before dispatch, because a role that could widen its own scope
  would pass any rule.
- **What it does:** a policy lists `read_paths`, `write_paths`, `tools` and
  `bash_allow` for one role. `read_paths=[]` means no file reads are in scope,
  and an omitted `tools` list grants no tools. A role with no policy is recorded
  as unmeasured. Each call is attributed to a role by, in order: a recorded
  binding, a per-role working directory, the prompt marker
  `[[scw:role=<role>]]`, then the kind of actor. A call that matches none is
  recorded as `unattributed` and never guessed.
- **How to use:** `/maxey0:gate policy <role>`,
  `observe_gate_policy(role=..., read_paths=[...], tools=[...])` or
  `maxey0-ss.gate.set_policy` (admin only). `/maxey0:run` declares each role's
  policy and adds the role marker to each dispatched prompt for you. Pass
  `workdir=...` to `observe_gate_policy` to record a role's working directory,
  which lets the Gate attribute calls on hosts that report no actor identity.
  `MAXEY0_GATE_POLICY` can name a JSON file of policies pinned for a whole run,
  such as `{"roles": {"maker": {"loop_id": "maker", "tools": ["Read"], "denied_tools": ["Bash"]}}}`.
  It is consulted only for a role that has no policy declared in the session.
  No tool accepts `denied_tools`, so this file is where you set it.

### Isolation levels (L0–L3)

- **Purpose:** stop a run from claiming more isolation than it achieved.
- **What it does:** replays the context ledger and reads the Gate journal, then
  reports the level the evidence supports, the reasons, the shortfall against
  what you declared, and residue counts (such as unattributed calls).

  | Level | Meaning |
  |---|---|
  | `L0_none` | No partition |
  | `L1_logical` | Separate context objects in one runtime; logical, not hard, isolation |
  | `L2_execution` | Each role ran in its own execution context |
  | `L3_observed` | L2, plus every crossing recorded and only declared outputs carried back |

- **How to use:** `/maxey0:gate level`, `observe_isolation_level(declared="L3_observed")`,
  `maxey0-ss.observe.isolation_level`, or `maxey0-ss.gate.declare_isolation {declared}`,
  which compares a claim with the evidence and stores nothing.

### Semantic admission hook (the semantic gate)

This is not the Gate. No semantic provider ships in this build, so in practice
it is a structural check of the SCW address.

- **Purpose:** a pluggable admission check for addressed requests and for model
  egress. A deployment that asks for stricter gating must never quietly get
  less.
- **What it does:** the default provider, `disabled`, checks the SCW address
  structurally and allows. Naming a provider this build does not have
  (`MAXEY0_SEMANTIC_GATE_PROVIDER=<name>`) denies everything and says why. The
  hook is consulted on model egress, by `maxey0-ss.gate.inspect`, and by the one
  tool that requires an SCW address (`maxey0-ss.scw.observe_host_window`). Other
  tools are governed by capability authorization (see
  [Security and privacy](#security-and-privacy)).
- **How to use:** `maxey0-ss.gate.inspect {scw_address: "scw://research/Task/summarize/eu-west/SCW1"}`
  shows whether an address is well formed and what the configured provider
  decides.

### Semantic drift

- **Purpose:** show when a window's work has moved too far from where it started,
  as a number with a threshold.
- **What it does:** you supply vectors (for example, embeddings; Maxey0 computes
  none). Anchoring stores a baseline. Measuring returns the cosine distance, the
  threshold (the window's 0.15 by default, or one you pass) and whether it
  drifted. When it has, the result carries the label `re-anchor-and-reroute`;
  no action is taken for you. Measuring a window with no baseline is refused,
  never reported as 0.
- **How to use:** `maxey0-ss.scw.drift {scw_id: "SCW1", vector: [...], anchor: true}`
  once, then `maxey0-ss.scw.drift {scw_id: "SCW1", vector: [...]}` to measure.
  Over HTTP: `POST /v1/context/scws/{id}/anchor` and `/drift`, which keep a
  separate store keyed by instance ID.

### Loop library and routing

- **Purpose:** route a task to a formation that already exists instead of
  improvising a maker/checker pair.
- **What it does:** routes against a library of 16 concepts, 83 skills, 67 agents
  and 84 loops, and returns the formation. Of the 84 loops, 78 are
  `validated`, 1 is `partial` and 5 are `draft-unexecuted`. 79 run in one
  window; the other 5 are cross-window loops, with ids of the form
  `designer:NN-slug`. `/maxey0:run` binds the partition and dispatches it.
  Cross-window runs execute one separate subagent call per participant, with no
  shared context.
- **How to use:** `/maxey0:route <task>` (routes, binds nothing),
  `/maxey0:run <task>`, `/maxey0:crosswindow designer:01-horizontal-4way`, and
  the `loops_*` tools such as `loops_route` and `loops_catalog` (which lists the
  loops, 25 at a time unless you pass a larger `limit`).

### The Studio

- **Purpose:** a local browser console for browsing the library, composing
  formations, and looking at the window, the Gate and the evidence.
- **What it does:** serves nine views:

  | View | Shows |
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

  It checks the hash chain and replay on request (`/api/verify`). It uses only
  the standard library. It has **no authentication**, binds to loopback by
  default and refuses non-loopback `Host` headers.
- **How to use:** `/maxey0:studio [port]`, or from a checkout
  `python server/run_studio.py --port 7676`, then open `http://127.0.0.1:7676`.
  `maxey0-ss.observe.studio` reports the address and start command; it does not
  start the Studio.

### Harness adapters

- **Purpose:** connect an agent built in another framework to a named SCW, so
  the model calls and checks your code makes for it are attributable to that
  window.
- **What it does:** six adapters: `claude-agent-sdk`, `openai-agents`,
  `langchain` (LangGraph), `google-adk`, `microsoft` (Agent Framework) and
  `nvidia` (NeMo Agent Toolkit). `bind_agent()` starts an instance of an
  existing SCW specification for the agent and returns a binding. Framework
  imports are deferred, so `bind_agent()` works without the framework installed,
  and using the framework without it raises a clear install message. Adapters
  do not intercept the framework's own tool or model calls: egress is recorded
  only when it goes through `maxey0_ss.providers`.
- **How to use:** create the specification first, bind, then use the binding's
  instance ID for every check and model call:

  ```python
  # system, deploy_default_scw and registry as in Path B
  from maxey0_ss.adapters.harnesses import ADAPTERS
  from maxey0_ss.models import AgentSpec

  system.create_scw(deploy_default_scw("review the summary", scw_id="SCW3"))
  binding = ADAPTERS["langchain"]().bind_agent(system, AgentSpec("reviewer", "checker", "SCW3", []))
  # binding.scw_id is the instance ID, for example "SCW3@scw-runtime-0"
  iso = system.context.isolation
  registry(log=iso.log, containment=iso)["anthropic"].complete(prompt, scw_id=binding.scw_id)
  ```

  Nothing else the framework does is recorded.

### Host window observation

- **Purpose:** let a host such as a ChatGPT App or an MCP App report how its own
  context is partitioned, without Maxey0 claiming access to hidden model
  context.
- **What it does:** normalizes up to 1000 host-supplied segments and returns
  them with a partition count, marked as host-supplied.
- **How to use:** `maxey0-ss.scw.observe_host_window {scw_address: "scw://...", segments: [...]}`.
  It requires a full `scw://` address.

### MCP App, tasks, caching and A2A

| Feature | Purpose | What it does and how to use it |
|---|---|---|
| **MCP App** (`ui://maxey0-ss/super-space.html`) | See windows, evidence, providers and posture in a host that renders MCP Apps | Opened by `maxey0-ss.super_space`. Five tabs: **Observe** (check an SCW address with `gate.inspect` and report host segments), **Windows** (list, create and close specifications, and measure drift), **Evidence** (the attestation summary and records, and the event stream), **Providers** (provider status and a gated model call) and **Posture** (auth manifest, deployment, health, cache and distribution). The built page is in the repository; if it is missing, a small fallback page is served, and `maxey0-ss.app.artifact` reports which one. |
| **MCP Tasks** | Fetch the record of a finished model call again | `maxey0-ss.provider.complete` runs synchronously and attaches a completed or failed task record to its result. `tasks/get` on the stateless endpoint returns that record again for its TTL (one hour by default). A client that timed out never received the task ID, so it cannot recover the call this way. There is no `tasks/list`; `maxey0-ss.tasks.status` gives counts only. In memory, per process. |
| **Caching** | Speed up repeated read-only answers without mixing windows | Only `health`, `distribution` and `app.artifact` are cached. Closing an SCW invalidates its entries. See `docs/CACHING.md`. |
| **A2A routing** | Let an external agent ask which registered skill should handle a task | `POST /v1/a2a/message`, checked against `MAXEY0_A2A_SHARED_SECRET` rather than a capability. The task text is recorded only as a digest. Agent card: `/.well-known/maxey0-agent.json`. |

### The `maxey0-ss` tool catalog

The Python package's MCP server exposes 29 tools. The capability column is what
a caller's role must hold (see [Security and privacy](#security-and-privacy)).

| Group | Tools | Capability |
|---|---|---|
| Windows | `scw.create`, `scw.describe`, `scw.close`, `scw.drift` | `scw.create`, `scw.read`, `scw.admit`, `scw.read` (anchoring also needs `scw.admit`) |
| Gate | `gate.inspect` / `gate.set_mode`, `gate.set_policy`, `gate.declare_isolation` | none / `gate.write` (admin only) |
| Evidence | `evidence.summary`, `evidence.attestations` / `evidence.verify` | `observe` / none |
| Observation | `scw.observe_host_window`, `observe.events`, `observe.attempts`, `observe.traces`, `observe.gate_activity`, `observe.gate_mode`, `observe.isolation_level`, `observe.studio` | `observe` |
| Providers | `provider.status` / `provider.complete` | `observe` / `scw.admit` |
| Server | `health`, `distribution`, `auth.manifest`, `cache.status`, `app.artifact`, `deployment`, `super_space`, `tasks.status` | none |

Every name above is prefixed `maxey0-ss.`. "None" means no capability is needed,
but a token is still required when the server runs in `bearer` or `oidc` mode.

### The three planes

The documentation divides the system into three planes. Knowing which one owns
what explains what Maxey0 does and does not do. The marketplace's plugins are
servers, not planes: `maxey0-context` and `maxey0-loops` both serve the Context
plane, and `maxey0-observe` serves the Engineering plane.

| Plane | Owned by | Contains |
|---|---|---|
| **Execution** | Your host | Agents, loops, model calls, tool calls. Maxey0 adds no capability here. It constrains at the tool call and records what crossed. |
| **Context** | Maxey0 | Concepts, skills, windows and their regions, scopes, admission, routing, provenance. |
| **Engineering** | Maxey0 | The Gate, the context ledger, correlated traces, isolation levels and the Studio. It reads records rather than reaching into the other two planes. |

---

## What it is not yet

An honest list. Details are in `docs/AUTHORIZATION.md` and `docs/VERIFICATION.md`.

- **MCP alone cannot start a window.** `scw.create` makes a specification, and
  no MCP tool or `/v1` route starts an instance, so `maxey0-ss.provider.complete`
  called over MCP alone is always refused ("window is not registered"). Start
  instances from Python or through a harness adapter.
- **Adapters do not intercept framework calls.** A LangGraph or OpenAI Agents
  agent's own tool and model calls are not recorded. Only egress through
  `maxey0_ss.providers` is, and those providers are single-turn text
  completions.
- **The Gate runs only where hooks run.** That means Claude Code. The generic
  adapter for other hosts has been tested only with a Codex-shaped payload.
  Not Claude Desktop. The Gate defaults to `observe`, records nothing as checked
  in `off`, never denies an unattributed call, and lets a call through
  (recorded as `fail_open`) when it cannot evaluate it, so a broken Gate never
  breaks a session.
- **Model calls made outside Maxey0 are not seen.** That includes every model
  call a Claude Code subagent makes. The gated provider wraps a provider that
  can still be called directly.
- **The Python attestation log is unsigned and in memory.** It proves internal
  consistency, not authorship: anyone holding the log can build a fresh valid
  chain. It lives in one process and does not survive a restart. Records
  removed from the end are detected only when you pass the expected head or
  entry count, and the `maxey0-ss.evidence.verify` tool accepts neither. On a
  `bearer` server that tool also needs a token; the offline Python verifier
  needs nothing. The plugin's context ledger and Gate journal are on disk, but
  they are unsigned too.
- **No standalone verifier for the plugin's records.** The context ledger and
  the Gate journal are checked with `/maxey0:window verify` and
  `/maxey0:gate status`, which run Maxey0's own code.
- **MCP Tasks cannot recover a timed-out call.** The task ID arrives only with
  the finished result.
- **No semantic gate provider ships.** The default checks the address
  structurally only.
- **SCW0's reach is unbounded, and depth and child caps are off, by default.**
  The narrowing rule holds, but it constrains nothing until you pass
  `root_reach` to `ContextService`, or caps to a `Constitution`, in Python. No
  MCP tool sets either.
- **Drift is measurement only.** You supply the vectors, the correction is a
  label, drift results are not written to the attestation log, and the MCP and
  `/v1` drift stores are separate.
- **Security gaps.** No OAuth sign-in for MCP clients, and OIDC has not been run
  against a real identity provider. No per-tenant isolation. Rate limits are per
  process and reset on restart. Token changes need a restart. No secrets manager.
  No independent security audit. Redaction is pattern-based, so a secret in an
  unrecognized shape can still be written.
- **Not on PyPI.** Install from a checkout.
- `maxey0-ss.incident.*` is not part of this package. Corpus-replay research
  lives in a separate consumer of it.

---

## Security and privacy

| You get | How it works |
|---|---|
| **Tokens stored as hashes** | The recommended store is `sha256:<hex>:<role>:<label>` entries in `MAXEY0_MCP_TOKEN_HASHES`, compared in constant time, so a leaked config does not reveal a working token. `scripts/mint_token.py` mints tokens. Plaintext tokens are still accepted in `MAXEY0_MCP_TOKENS` and `MAXEY0_MCP_DEFAULT_BEARER_TOKEN`, and a config that uses them leaks working tokens. `auth.manifest` reports how many hashed and plaintext tokens are configured. Logs name the caller as `bearer:<label>` (or `bearer:sha256:<12 hex>` and `bearer:default` for plaintext tokens), never the token. |
| **Least privilege by role** | `viewer` (observe: 21 tools), `operator` (+ read windows: 23), `builder` (+ create and admit windows, call providers: 26), `admin` (everything: 29). With `MAXEY0_PUBLIC=1` and auth disabled, anonymous callers get only the 10 tools that need no capability. Only `admin` can change the Gate. |
| **Fail-closed configuration** | Over HTTP, a malformed token entry, a leftover `<BEARER_TOKEN>` placeholder, an unknown `MAXEY0_AUTH_MODE` or an incomplete OIDC setup refuses every tool call and every capability-gated `/v1` request (HTTP 501) and names the variable, never its value. `/health`, discovery, the agent card, `/docs` (when not public) and capability-free `/v1` routes such as `POST /v1/a2a/message` are still served. |
| **A switch for internet-reachable servers** | `MAXEY0_PUBLIC=1` drops unauthenticated callers to the anonymous tier, turns on rate limits, hides `/docs` and `/openapi.json`, refuses A2A messages when no shared secret is set, and stops tools from reading or writing the host's own `~/.scw` journals (unless `MAXEY0_PUBLIC_HOST_PLANES=1`). |
| **Authorization before admission** | A caller is authorized before any window gate or handler runs, so an unauthorized caller cannot probe them. |
| **Rate limits and request caps** | Per client IP (120/min), per caller (300/min), session opens (6/min), 20 failed credentials per hour per client, 1 MiB request bodies, 50 sessions. All adjustable. |
| **Trusted proxy handling** | `CF-Connecting-IP` is believed only from addresses in `MAXEY0_TRUSTED_PROXY_IPS` (loopback by default), and uvicorn's own `X-Forwarded-For` handling is off in every server command (`maxey0-ss-public`, `maxey0-ss`, `maxey0-ss-api`), so nothing else can choose the client address the rate limiter keys on. |
| **Logs that do not become a record of you** | The Gate journal, the context ledger and attribution state replace home directories with `~` and redact secret-shaped values (API keys, tokens, JWTs, private keys, `password=` assignments) at write time. Prompts are recorded as digests; A2A task text as a short digest. |

Two things to know. Discovery (`server/discover`, `tools/list`,
`resources/list`, `resources/read`) needs no token even in `bearer` mode, so
treat tool names and the MCP App as public. And the local stdio server carries
no credentials: it treats its caller as local admin unless `MAXEY0_PUBLIC=1`.

---

## Running your own server

1. **Configure.** Copy `.env.example` to `.env` and edit it. A checkout or
   editable install reads `.env` and `config/credentials.json` from the
   repository root, wherever you start the server. An installed (non-editable)
   package reads them from the directory you start it in. Variables already set
   in the environment win. Every variable in `.env.example` is read by this
   build, and `tests/test_configuration.py` checks that in both directions.
   Values left at `<API_KEY>` or `<BEARER_TOKEN>` are treated as unconfigured
   templates and refused, not sent.
2. **Run locally.** The defaults suit a trusted machine: `MAXEY0_AUTH_MODE=disabled`
   makes every caller admin, and the server binds `127.0.0.1:8765`.
   `maxey0-ss.auth.manifest` reports `admin_open: true` in that state.
3. **Before anything can reach it from outside the machine**, run
   `maxey0-ss-public` (or either alias) and set:

   ```bash
   MAXEY0_PUBLIC=1
   MAXEY0_AUTH_MODE=bearer
   MAXEY0_MCP_TOKEN_HASHES=sha256:<64 hex>:operator:<label>   # from mint_token.py
   MAXEY0_TRUSTED_PROXY_IPS=<your proxy's addresses>          # if the proxy is not on this host
   MAXEY0_A2A_SHARED_SECRET=<a long random value>             # or A2A messages are refused
   ```

   Keep the server bound to loopback behind a tunnel or reverse proxy. Then
   check `maxey0-ss.auth.manifest`: `admin_open: false`,
   `public_deployment: true`, no plaintext tokens and no token config errors.
4. **Mint tokens**, one per caller:

   ```bash
   python scripts/mint_token.py --role operator --label claude-code
   ```

   It prints the token once and the `MAXEY0_MCP_TOKEN_HASHES` entry. Add the
   entry to the server (comma-separated for several) and restart. `--out PATH`
   writes the token to a file outside the repository. Changing tokens requires
   a restart.
5. **Connect a client.** Claude Code and Claude Desktop open a session, so they
   need the session endpoint:

   ```bash
   claude mcp add --transport http maxey0 http://127.0.0.1:8765/mcp/session --header "Authorization: Bearer <token>"
   ```

   Clients that speak the stateless MCP `2026-07-28` transport use `/mcp`:

   ```bash
   curl -X POST http://127.0.0.1:8765/mcp \
     -H "Content-Type: application/json" \
     -H "MCP-Protocol-Version: 2026-07-28" \
     -H "Mcp-Method: server/discover" \
     -d '{"jsonrpc":"2.0","id":1,"method":"server/discover"}'
   ```

| Endpoint | Use |
|---|---|
| `POST /mcp` | Stateless MCP, protocol `2026-07-28`. Needs the `MCP-Protocol-Version` and `Mcp-Method` headers (plus `Mcp-Name` for `tools/call`). No `initialize`. |
| `/mcp/session` | Session MCP (Streamable HTTP) for Claude Code and Claude Desktop |
| `/v1/...` | REST API. Most routes need the same capability as their MCP counterpart, with two differences: measuring drift at `/v1/context/scws/{id}/drift` needs `scw.admit` (MCP `scw.drift` measuring needs `scw.read`), and `POST /v1/a2a/message` is checked against `MAXEY0_A2A_SHARED_SECRET` instead, which leaves it open when the secret is unset unless `MAXEY0_PUBLIC=1`. `/docs` lists the routes on a non-public server. |
| `GET /health` | Liveness |
| `/.well-known/maxey0-agent.json` | A2A agent card |

**OIDC.** `MAXEY0_AUTH_MODE=oidc` with `MAXEY0_JWT_ISSUER`, `MAXEY0_JWT_AUDIENCE`
and `MAXEY0_JWKS_URL` verifies identity-provider JWTs (RS256/384/512; ES256/384
with the `cryptography` package). The role comes from the claim named in
`MAXEY0_OIDC_ROLE_CLAIM`. Tokens must be obtained outside Maxey0; there is no
OAuth sign-in flow for MCP clients.

**Hosting.** `Dockerfile`, `fly.toml` and `deploy/entrypoint.sh` prepare a
Fly.io deployment whose entrypoint refuses to start unless the server is
public and authenticated and, with the tunnel on, bound to loopback. They have
never been built or deployed, and `fly.toml` ships with `CHANGE-ME` values you
must replace. See `docs/FLY_DEPLOYMENT.md`.

---

## Hosted endpoint

`mcp.maxey0.com` is the maintainer's own running instance, not a service you can
sign up for. Every tool call needs a token that the maintainer issues; minting
your own token does nothing there. Stateless clients use
`https://mcp.maxey0.com/mcp`. Claude Code and Claude Desktop use
`https://origin.maxey0.com/mcp/session` with `Authorization: Bearer <token>`. The
origin runs on a development machine, not an isolated host. These statements
describe the maintainer's deployment; nothing in this repository's tests checks
them. For your own use, [run your own server](#running-your-own-server).

---

## Verify it yourself

From a checkout, with the virtual environment active (`.venv\Scripts\activate`
on Windows, `source .venv/bin/activate` on macOS and Linux):

```bash
python -m pip install -e . pytest
python -m pytest -q
python scripts/check_lexicon.py
python scripts/build_distributions.py --check
```

`pytest` is not installed by the package, hence the extra install. The built
MCP App that some packaging tests need is in the repository, so those tests run
from a fresh clone.

`docs/VERIFICATION.md` records how the system actually behaves, measured rather
than described, and its surface counts are checked against the code by a test.

---

## Documentation

| Document | What it covers |
|---|---|
| [ARCHITECTURE](docs/ARCHITECTURE.md) | How the planes divide, and why |
| [GATE](docs/GATE.md) | The Gate: modes, policies, attribution, host levels, isolation levels |
| [SCW0](docs/SCW0.md) | The root window and the constitution hierarchy |
| [CONTAINMENT](docs/CONTAINMENT.md) | The enforcement seam and the evidence format |
| [AUTHORIZATION](docs/AUTHORIZATION.md) | Capabilities, roles, auth modes, and what is not implemented |
| [VERIFICATION](docs/VERIFICATION.md) | Measured behavior, and what is *not* verified |
| [LEXICON](docs/LEXICON.md) | One name per thing |
| [MCP_2026_07_28](docs/MCP_2026_07_28.md) | The stateless protocol surface |
| [CACHING](docs/CACHING.md) | What is cached, and what never is |
| [FLY_DEPLOYMENT](docs/FLY_DEPLOYMENT.md) | The prepared, undeployed Fly.io setup |
| [RUNBOOK](docs/RUNBOOK.md) | Running one loop in Claude Code, and restarting the maintainer's origin |
| [ROADMAP](docs/ROADMAP.md) | Planned work, and what is not planned |

---

## License

Apache-2.0. See [LICENSE](LICENSE).
