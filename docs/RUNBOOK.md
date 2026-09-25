# Runbook: run, monitor, log, and report one Maxey0 agentic loop

Start-to-finish procedure, from a cold laptop to a reported result.

---

## 0. Power on and get a terminal open

Boot the laptop, log in, open a terminal (PowerShell or Git Bash).

## 1. Get the repository, then start Claude Code

If you have not installed the plugin in this Claude Code environment yet, and
want to install it from a local clone, clone it first, **in the shell**, in the
directory you will start Claude Code from:

```bash
git clone https://github.com/mmc7676/Maxey0.git
```

Skip the clone if you install from GitHub directly (step 2).

Then start the session:

```bash
claude
```

`/plugin`, `/maxey0:*` and every other slash command below only exist **inside
an active `claude` chat session**. They are not shell commands, and typing them
straight into PowerShell or Bash fails with something like
`The term '/plugin' is not recognized...`. Everything from here on is typed into
that chat prompt, not the shell it was launched from.

## 2. Get the plugin loaded

Inside the `claude` session, add the marketplace from your clone or from GitHub:

```
/plugin marketplace add ./Maxey0
```

`./Maxey0` resolves against the directory Claude Code was started from, which is
why step 1 clones there. Use an absolute path if the clone is elsewhere, or
`/plugin marketplace add mmc7676/Maxey0` to install from GitHub. Then:

```
/plugin install maxey0@maxey0
```

**Restart Claude Code** (exit and run `claude` again). All three MCP servers
(`maxey0-context`, `maxey0-loops`, `maxey0-observe`) and the plugin's hooks
(`SessionStart`, plus the Gate's `PreToolUse`, `PostToolUse`, `SubagentStart`
and `SubagentStop`) load only at session start.

If `/plugin` is unavailable in your environment at all (some hosted or managed
Claude Code setups restrict it), the plugin's tools may already be registered
another way for you. Check with `/maxey0:doctor` below before assuming the
plugin is not loaded.

## 3. Health check before you trust anything

```
/plugin
```
Confirm `maxey0` shows enabled and tools like `context_route_bind` and
`loops_catalog` are listed.

```
/maxey0:doctor
```
This reports which planes are reachable and how many tools each serves, whether
the context ledger exists and how many records it holds, the Gate's mode and
activity, and which runtime and Python interpreter the servers loaded.

Keep one caveat in mind the whole session: the Studio's browser window and this
session's window are **separate live windows**.

## 3b. Confirm the Gate is actually live

Skip this and every containment number you report later is about the runtime,
not about the agents.

```
observe_gate_mode()
```
Reports the current mode and the modes available. It does not list declared
policies. After a subagent has run, `observe_gate_activity()` reports, per role,
what was reached for, allowed and refused.

Two things must be true before a run's containment figure means anything:

1. **You restarted Claude Code after installing or upgrading.** Hooks load at
   session start. If you did not, the Gate is not running at all and
   `observe_gate_activity` will report no journal.
2. **You are in Claude Code, not Claude Desktop.** Desktop has no hook system
   and dispatches no subagents, so the Gate does not run there.

Leave it in `observe` unless you want refusals to actually block. `observe`
records every crossing and is what measures how often a role *tries* to leave
its partition.

## 4. Pick the loop

Ask Claude to call `loops_catalog`, or open the Studio's **Loops** view
(`/maxey0:studio`). `loops_catalog` returns 25 loops unless you pass a larger
`limit` (for example `loops_catalog(limit=100)`), and it can filter by
`status` or `concept`. The library holds 84 loops: 78 `validated`, 1 `partial`
and 5 `draft-unexecuted`. Pick one, or skip picking and let a task route to one
automatically (step 6).

To see what a task would route to without binding anything:

```
/maxey0:route <describe the task in plain language>
```

## 5. Declare what each role may reach outside the window

Do this **before** any role is dispatched; a policy governs nothing that was
dispatched before it existed. If you run the loop with `/maxey0:run` (step 6,
in-window loop), it declares each role's policy for you just before
dispatching that role, and that declaration replaces any earlier one for the
same role in the session. Skip to step 6 in that case.

The partition governs regions. It does not govern the filesystem, the shell or
the network: a role handed `Read` can reach the whole disk while every region
stays perfectly contained. That is the gap the Gate closes, and it closes it
only for roles you declared.

If you dispatch roles by hand, declare each one first, under its bound name:

```
observe_gate_policy(role="<role>", read_paths=[], tools=["Read"])
```

Default to `read_paths=[]` and a narrow `tools` list: a role in a partitioned
loop is supposed to work from what `context_window_render` gave it. Put the
`[[scw:role=<role>]]` marker at the start of each dispatched prompt, as
`/maxey0:run` does. Without that marker the role's calls are recorded
`unattributed`, which is residue that invalidates the run's containment claim
rather than a cosmetic gap.

## 6. Run it

**In-window loop (most loops, simplest)**

```
/maxey0:run <describe the task in plain language>
```
Routes the task, binds the partition, declares each role's Gate policy,
dispatches one subagent per role in topology order, and reports each role's
output plus every refusal along the way.

**Cross-window loop (the 5 `designer:*` loops, no shared buffer)**

```
/maxey0:crosswindow <designer:NN-slug>
```
For example `/maxey0:crosswindow designer:01-horizontal-4way`. This is the path
that writes a real `.report.json`. All five cross-window loops are currently
`draft-unexecuted`, so a report from one of them is the evidence that loop
lacks.

## 7. Monitor it while it runs

- **In the same Claude Code session**: `/maxey0:window inspect` shows the
  region map, which role is bound where, open bridges, the cache plan and live
  advisories, right now.
- **In the Studio**: `/maxey0:studio`, then the **Window** view (pick a role in
  "view as" to see the window *through its scope*) or **Mission Control**. This
  is a *separate* window from the one your loop is actually running in. Use
  `/maxey0:window inspect` in the session for ground truth, and the Studio for
  visualization.

## 8. Log and verify the audit trail afterward

```
/maxey0:window verify
```
Confirms two things and reports both plainly: the hash chain verifies over
every event, and replaying the log reconstructs a window identical to the
live one. If either fails, that is the headline finding. Do not proceed as if
the run were trustworthy.

The raw log is the context ledger at `~/.scw/events.jsonl` (or wherever
`SCW_EVENT_LOG` points). Every event from this run is a hash-chained line in
it, if you want to inspect it directly or archive it. The Gate journal is at
`~/.scw/gate.jsonl` (or wherever `MAXEY0_GATE_LOG` points).

## 8b. Read what the agents actually did

```
observe_gate_activity()
observe_isolation_level(declared="L3_observed")
```

`observe_gate_activity` gives, per role, what each reached for, what was
allowed, what was refused, and the residue, plus the Gate journal's chain
check. `observe_isolation_level` reports which level the **evidence** supports
and names the shortfall where that is below what you declared. Declaring L3
and running L1 is a failure nothing else in the stack would notice.

Report `containment.claimable` verbatim. If it is false, name the residue rather
than reporting the containment figure as though it were clean.

## 9. Report the result

Ask, in the same session:

> Summarize this loop run: what each role produced, every refusal the
> runtime issued and what it prevented, and the cache/cost figures from the
> final context_scope_tick.

This is step 6 ("Close out") of the `/maxey0:run` procedure, so the data is
already there; you are asking Claude to state it.

For a **formal written report** instead of a chat summary, use the experiment
harness. It is not part of the product and ships as a separate plugin:

1. Install it: `/plugin install maxey0-lab@maxey0`, then restart Claude Code.
2. Start the Studio from a checkout, because the workload specs live in the
   checkout's `experiments/specs/`: `python server/run_studio.py --port 7676`.
   A Studio started with `/maxey0:studio` from the installed plugin has no
   `experiments/specs/` directory, so pass a spec path in that case.
3. Run `/maxey0-lab:experiment-run <spec-id|spec-path>`. With no argument it
   lists the available specs and stops.
4. Read `experiments/<exp_id>/report.json` and `report.md`, under the Studio's
   root (the checkout, for a Studio started from it): containment, cost,
   leakage and integrity as separate measured fields, with a `residue` section
   for anything it could not measure. Add a spec to `experiments/specs/` to run
   a different workload.

---

## Restarting the origin

Maintainer operations for the hosted instance behind `mcp.maxey0.com`. These
steps need the maintainer's Cloudflare tunnel credentials, so they do not apply
to anyone running their own server. They are recorded from the maintainer's
setup; nothing in this repository checks the tunnel name, the credentials or
the edge Worker's state.

The origin is a normal long-running process, and this project does not run it on
an always-on host yet, so after any restart of the machine it runs on:

```powershell
# terminal 1 — the tunnel
cloudflared tunnel run maxey0-origin

# terminal 2 — the origin itself
cd <your checkout of Maxey0-SuperSpace>
.venv\Scripts\maxey0-ss-public.exe
```

In the maintainer's setup, `mcp.maxey0.com` stays resolvable either way,
because the edge Worker (source in `workers/mcp-edge`) runs separately; only
tool execution depends on both of the above running.
