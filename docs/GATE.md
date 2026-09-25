# The Gate

Where an agent inside a partition becomes observable, what it is allowed to do
about that, and exactly what a run may claim afterwards.

Read `docs/ARCHITECTURE.md` first for why this exists. This document is the
contract.

---

## The one-paragraph version

A tool call is the only moment an agent running in a delegated context has to
ask its host for something, so it is the only place an outside observer can
stand. The gate stands there. It attributes each call to a bound SCW role,
records it in its own hash-chained journal, and — in `enforce` mode — refuses
the calls that reach outside that role's declared scope. Everything else in
this document is a consequence of taking that seriously.

---

## Modes

| mode | behavior | for |
|---|---|---|
| `enforce` | out-of-scope calls denied; the refusal reaches the model | production |
| `observe` | everything recorded, nothing blocked | measurement |
| `off` | inert | the control condition |

`observe` is **not** a weaker `enforce`. It is the only way to measure how often
an agent *attempts* to leave its partition, which is a property of the formation
rather than of the enforcement, and it produces exactly the same finding
`enforce` would — same reason code, same message — differing only in whether the
call proceeded.

`off` is genuinely inert, so a control condition does not pay the gate's cost or
appear in its numbers.

Set it with `observe_gate_mode("enforce")`, or pin it for a whole run with
`MAXEY0_GATE_MODE`, which wins over anything stored.

---

## Declaring a policy

The SCW model knows regions. It has never known anything about the filesystem,
which is why a role bound to a 2 048-token scratchpad could read the whole disk
and no measurement noticed.

```python
observe_gate_policy(
    loop_id="maker",
    read_paths=[],                 # [] means NO filesystem read is in scope
    tools=["Read", "Glob"],        # None would mean every tool
    bash_allow=[],                 # a shell escapes every path check above it
)
```

Three distinctions that carry weight:

- **`read_paths=[]` is not `read_paths=None`.** The empty list says no
  filesystem read is in scope — the correct default for a role meant to work
  from what `context_window_render` gave it. Omitting the policy entirely says the
  role's reach is *unmeasured*, which is reported as residue, not as zero.
- **A policy is host-authored.** A role cannot declare its own, for the same
  reason `Loop.exposes` is host-authored: a party that can widen its own scope
  satisfies any containment rule vacuously.
- **A directory pattern covers its subtree.** `/repo/docs` matches
  `/repo/docs/a/b.md`.

---

## Attribution

The gate sees a host's actor identifier. The window knows `loop_id`s. Mapping
one to the other is the part of this design most able to produce a quietly wrong
number, so it is built to fail loudly.

Four resolvers, tried in order:

| # | resolver | works when | resolves |
|---|---|---|---|
| 1 | recorded binding | the actor has been seen before | instantly |
| 2 | **working directory** | the role was dispatched with its own directory | **before the call** |
| 3 | transcript marker | the prompt carried `[[scw:role=…]]` | before the call |
| 4 | actor kind | exactly one role of that type is pending | before the call |

**The working directory is the important one**, because it is the only mechanism
that works on a host which never sends an actor id — which is every host except
Claude Code and the Claude Agent SDK. Give each dispatched role its own
directory and that directory *becomes* the role identity, with no host support
at all.

If none resolves, the call is recorded `unattributed`. It is never guessed, and
two pending roles of the same actor type stay `ambiguous_actor_kind` rather than
being resolved to whichever was declared first — attributing one role's behavior
to another is worse than not knowing.

**An unattributed call is never denied.** Refusing on a guess would be worse than
the hole it was trying to close.

### The marker

The orchestrator puts this at the top of the dispatched prompt:

```
[[scw:role=maker]]
```

It is not decoration. Without it — and without a per-role working directory —
every call that role makes is `unattributed` residue, and the run's containment
claim is void.

---

## What a run may claim

`containment.claimable` is the field a report leads with, and it is **false
whenever any residue exists**:

| residue | meaning |
|---|---|
| `unattributed` | the gate saw the call but could not tie it to a role |
| `fail_open` | the gate could not evaluate the call and allowed it |
| `gate_errors` | the gate itself failed |
| `damaged_records` | a torn line; the observation is simply gone |
| `unlocked_writes` | a record written without the append lock, holding no place in the chain |

`held` is three-valued, for the same reason the runtime's `contained` is: `true`
and `false` mean every evaluated attempt was refused or some was not, and
**`null` means nothing was evaluated**, which establishes nothing either way.

Sentences a run may use, and may not:

> ✅ "In enforce mode, 12 out-of-scope reads by `maker` were refused by the gate;
> each refusal is a recorded event the chain covers."
>
> ✅ "In observe mode, `checker` attempted 4 reads outside its declared scope."
>
> ❌ "The agents were contained." — not without `claimable: true`.
>
> ❌ "No leakage occurred." — an absence of attempts is an absence of evidence.
>
> ❌ "Isolation was proven." — only level 1 of the disjointness table is
> enforced, and gate telemetry does not change that.

---

## The two rules the gate cannot break

**A broken gate must never break a session.** Every exit path is exit code 0 on
Claude Code; a malformed payload, an unknown tool, an unparseable policy — none
may stop an agent from working.

**A gate that fails open must say so.** `fail_open` is a distinct verdict, not an
`allow` with a flag, because letting a call through *because the gate could not
evaluate it* is not the same as letting it through *because it was in scope*.
Collapsing them would manufacture containment out of a malfunction, which is
precisely the error this whole version exists to correct.

### The gate never grants

It returns `deny` or it stays silent. It never returns
`permissionDecision: "allow"`, because `allow` **skips the user's own permission
prompt** — a component installed to restrict an agent would end up granting it
access the user never approved. The gate is a restrictor, never a granter.

---

## The journal, and why it is a separate file

Appending gate records to the runtime's `~/.scw/events.jsonl` was measured, and
it destroys the log.

`scw_runtime.events.EventLog` starts every writer at `seq = 0` with
`prev = GENESIS`, and `verify_records` resets its expectations at each `run_id`
boundary. Two processes appending to one file therefore produce a sequence that
can never verify again — the record bytes stay individually valid while the file
as a whole is permanently broken. `split_runs` partitions on *consecutive*
`run_id`, so an interleaved file also shatters each run into fragments, and
`replay` — which takes the last fragment and requires it to open with
`window.init` — fails outright. The Studio's live mirror returns `ok: false` from
that point on. `EventLog`'s `run_id` counter is a per-process global, so two
processes starting in the same millisecond mint the *same* run id and the
corruption becomes invisible rather than loud.

A gate hook is a new OS process **per tool call**. So:

- **Its own file**, `~/.scw/gate.jsonl` (`MAXEY0_GATE_LOG` to move it).
- **Redacted before it is written** (`server/gate/privacy.py`). The Gate decides
  on the real values; only the record is sanitized:
  - the user's home folder, which names them, becomes `~`;
  - transcript paths are dropped;
  - secret-shaped values become `[REDACTED:<kind>]`. That covers API keys,
    tokens, bearer headers, private keys and `password=...`.

  The same rules apply to the runtime log, the gate's attribution state and
  everything the Studio saves. `tests/test_privacy.py` checks each on disk.
- **Chained per file, not per process**, under an exclusive lock. A hook process
  reads the file's own tail and links to it, which makes the file
  single-writer-at-a-time even though it has many writers over its life.
  `stream` is provenance — which process wrote a record — not a chain key.
- **A record that cannot take the lock takes no place in the chain.** It is
  still written, because losing an observation is worse, but it carries
  `seq: null` and is reported as residue. Two unlocked writers could otherwise
  mint the same `seq` and leave what looks like a hole, discrediting records
  that were written correctly.
- **Torn lines are counted, not fatal.** The runtime's `iter_records` calls bare
  `json.loads` and dies on a torn line with a `JSONDecodeError` that is not an
  `SCWError` and escapes every handler above it. This reader skips and counts,
  because a dropped record is a gap in the evidence and the count is what makes
  the gap visible.
- **Anchored, not merged.** Each record carries the runtime log's head so the
  two streams can be tied together, and they are never concatenated into one
  chain — a chain over records from two processes cannot verify, which is the
  whole point.

Measured: 12 trials × 64 concurrent 9 KB writes → 768/768 records present, 0
damaged, 0 chain breaks.

---

## Portability

`gate_core` imports nothing host-specific. An adapter's entire job is to
normalize its host's event into a `ToolEvent` and translate a `Decision` back.

```
        ┌──────────────────────────────────────────┐
        │  gate.core.decide(ToolEvent, Policy, …)  │
        └──────────────────────────────────────────┘
             ▲                ▲                ▲
      claude_code          generic          (your host)
      hooks.json      stdin JSON, exit 2
```

### What is actually universal

Across the hook-capable coding agents surveyed, exactly five things:

1. a pre-tool event delivered as JSON on stdin to a subprocess;
2. a payload carrying a session id, a working directory, a tool name and a
   tool-input object (under host-specific field names);
3. denial expressible via stdout JSON and/or **exit code 2**;
4. a human-readable reason returned to the model on denial;
5. a post-tool event.

**`exit 2` is the most portable enforcement primitive that exists here** — it
means deny on Claude Code, Codex, Cursor, Cline and OpenHands — so `generic.py`
uses it, and also emits the JSON decision for hosts that read one.

Everything else differs. In particular, **subagent identity on the tool event is
native only on Claude Code and the Claude Agent SDK.** That is why the working
directory is the primary attribution mechanism rather than a fallback.

### The degradation ladder

A host is run at the level it can actually support, and the level is recorded
with every event so a report can never present one it did not have.

| level | meaning | hosts |
|---|---|---|
> **Two ladders, deliberately spelled differently.** `H0`–`H3` below are
> **host capability** — what the host is *able* to do about a tool call.
> `L0`–`L3` in `server/gate/levels.py` are **isolation levels** — what a *run*
> actually achieved. A capable host does not make a run isolated: you can reach
> H3 and still evidence only L1 if the roles never ran in separate contexts.
> Both were once spelled `L0`–`L3`, which was confusing; `L*` is still accepted
> by the adapter as a deprecated alias.

| **H3** | enforce + native per-actor attribution | Claude Code, Claude Agent SDK |
| **H2** | enforce; attribution manufactured (cwd) | Codex CLI, Cursor, Gemini CLI, Copilot CLI, OpenHands, Cline |
| **H1** | observe only | any H2 host the operator chose not to enforce on |
| **H0** | no interception; the run records the null and claims nothing | Aider |

An H1 host configured for `enforce` is silently downgraded to `observe` — a host
that cannot block never runs in a mode that says it did.

```bash
<host hook> | python server/gate/adapters/generic.py --host codex --level H2
```

### Verified

The generic adapter was exercised against a Codex-shaped payload — camelCase
field names, **no actor id at all** — attributed purely by working directory:

| case | verdict | exit |
|---|---|---|
| `read_file` outside declared scope | `deny` / `path_outside_scope` | 2 |
| `read_file` inside declared scope | `allow` / `in_scope` | 0 |
| unknown tool naming a path outside scope | `deny` | 2 |
| same call on an H1 host | `observe_only`, finding preserved | 0 |

### Host caveats worth knowing before you trust one

- **Copilot CLI fails open on hook timeout.** A slow gate is no gate.
- **Cursor** is the only host with a first-class `beforeReadFile` channel — it
  closes the file-read side channel as a *typed* channel rather than by tool
  name.
- **Gemini CLI** has no subagent lifecycle events at all; cwd is the only option.
- **OpenHands** has a documented bypass (`conversation.execute_tool()`), so an
  OpenHands containment claim is conditional on that path being unused.
- **Cline**'s shipped hooks are macOS/Linux only.
- **Aider** has no interception surface of any kind. Not observe-only —
  *nothing*.

### Tool vocabularies differ

A gate that knew only one host's tool names would classify every other host's
file read as opaque and wave it through. `gate.core` therefore carries
cross-host aliases (`read_file`, `write_file`, `shell`, `run_terminal_cmd`, …),
and for a tool it has never seen it scans the arguments for anything
path-shaped and checks that as a read. An unfamiliar name is not a reason to
skip the check.

---

## Known limits

Stated here rather than left to be discovered.

- **Symlinks are not resolved.** `os.path.realpath` would touch the filesystem
  on every tool call and the gate has a millisecond budget. A symlink pointing
  out of scope defeats a path check.
- **A shell is a general-purpose escape** from every path check above it.
  `bash_allow` is empty by default and granting it broadly voids the
  filesystem guarantees.
- **The gate governs tool calls, not thought.** It records what an agent
  reached for, not what it inferred.
- **Level 1 disjointness only.** Enforced information access is not proven
  representational independence, and no amount of gate telemetry changes that.
- **Two plugin versions installed together both fire.** Hooks merge; if v0.5.0
  and v0.6.0 are both enabled, both hook sets run.
