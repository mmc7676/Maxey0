---
name: scw
description: Make Structured Context Windows the default way multi-step and multi-agent work is organized in this project. Use when a task needs several roles, when reference material must not be editable by whatever consumes it, when something must be verified by something that did not produce it, when the context window is getting long or expensive, or whenever the user mentions SCWs, partitions, regions, isolation, agentic loops, the Gate, or Maxey0.
---

# Structured Context Windows

An **SCW** is a context window that has been partitioned into typed,
addressable **regions**, with each **role** bound to a **scope** that the
runtime enforces at the tool layer — not by asking the prompt nicely.

This skill makes partitioning the working assumption before spreading a task
across several roles or steps: route first, then partition, then bind scopes,
then dispatch.

## When this applies

- More than one role will touch the same body of material.
- Something must be **verified by something that did not produce it**.
- There is reference material a working step must read but must never edit.
- The window is getting long, expensive, or reordered on every turn.
- The user says SCW, region, partition, isolation, agentic loop, Gate, or
  Maxey0, or asks who can see what.

## Route before you build — this is not optional

**Always call `loops_route` before hand-building a maker/checker pair or any
other formation.** Skipping this is expensive, concretely: routing a
documentation-audit task returned a coherent tri-plane hit — concept
`observability`, skill `ai-observability`, a pre-scoped four-role formation —
at an estimated 10,792-token read budget. The same task run instead as two
generic subagents with hand-written personas cost 253,481 tokens: roughly
**23× more**, for a worse-scoped result.

1. `loops_route(task=...)` scores and explains. It binds nothing.
2. `context_route_bind(task=...)` asks the same question and commits — it binds
   the matching loop's regions and roles in this session's own window.
3. **`loop_hit`** — use the formation it names.
4. **fallback** — nothing matched. Say so out loud; it is real information
   about what the library does not cover. Then use the matched skill's own
   formation, or build by hand (below), or design a loop in the Studio's
   Designer view so the gap does not recur.

`loops_catalog`, `loops_concepts` and `loops_skills` browse the library
directly, routing and binding nothing.

## Building a partition by hand

Region types are policies, not labels:

| type | mutability | bridgeable | use it for |
|---|---|---|---|
| `reference` | read-only | yes | instructions, retrieved corpus, a pinned rubric |
| `durable` | writable | yes | what should survive the run |
| `episodic` | writable | yes | run history, promoted findings |
| `working` | writable | **no** | task state nothing else should reach into |
| `scratchpad` | volatile | **no** | per-iteration reasoning; cleared every tick |

The shape that makes separation structural rather than polite: **bind each role
to its own scratchpad**, and give it one `durable` region to publish into. A
downstream role then reads the published output and *cannot* reach the
reasoning, because scratchpads are unbridgeable by policy — there is no grant
to mint.

```
context_window_reset
context_region_create    one per region                # host, before any binding
context_region_write     reference material            # host only; a bound role cannot
context_criterion_pin                                  # if anything will be graded
context_harness_create   architecture="maker_checker"  # self-approval becomes a refusal
context_scope_bind       <role> -> its own scratchpad
context_window_seal
```

Then per iteration: `context_region_write` → `context_bridge_open` (short TTL)
→ `context_region_read` → `context_window_render` → `context_bridge_promote`
what survived → `context_scope_tick`.

## Declare each role's reach outside the window

The partition governs regions. It has never governed the filesystem, the shell,
or the network — which is how a role bound to a 2,048-token scratchpad could
read the whole disk while every region stayed perfectly contained, and no
measurement noticed.

Before dispatching a role: `observe_gate_policy(role=..., read_paths=[],
tools=[...])`. Default to nothing, and never grant `bash_allow` unless a shell
is genuinely required — a shell is a general-purpose escape from every path
check above it.

## Cross-window: a different architecture, not a lesser one

Some loops are **cross-window**: one genuinely separate model call per
participant, zero shared token buffer, no region to bind. Isolation there comes
from what *you* put in each prompt, not from a runtime refusal. Run one for
real with `/maxey0:crosswindow` — never leave a cross-window topology as
"designed, not run" when the mechanism to run it exists.

## Rules that carry

1. **Never route around a refusal.** `isolation_violation` and
   `policy_violation` are the system working. Read the `hint` — it names the
   bridge that would make the access legal — and decide whether that access is
   actually justified. If it is not, the refusal already did its job.
2. **Never paste elided material into a subagent's prompt.**
   `context_window_render` is scope-true; adding back what it withheld silently
   destroys the partition and makes any measurement over the run meaningless.
3. **Grants expire.** Prefer `ttl_ticks=1`. A standing grant is a wall with a
   door propped open.
4. **`success` has to be earned.** `context_scope_unbind(terminal_state=
   "success")` is refused unless a verification actually passed. Do not
   relabel `exhausted` as success.
5. **A judge must be provably disjoint.** Under a `maker_checker` harness the
   runtime checks five rules before accepting a verdict. If it refuses, the
   separation you thought you had was not real — report that, do not reshape
   the call until it passes.

## Test containment rather than asserting it

Four assertions, and two of them are stronger evidence than the other two:

| tool | how it answers |
|---|---|
| `context_assert_cannot_read` | **Attempts a real read** and expects a refusal. `breach: true` if the read succeeds. |
| `context_assert_can_read` | Attempts a real read and expects authorization. |
| `context_assert_scope_closed` | Computes the closure. `evidence.pure: true`. |
| `context_assert_disjoint` | Computes closure intersection. `evidence.pure: true`. |

The first two go through the real authorization path, so a refusal is a
`scw.denied` record in the hash chain that replay reproduces. Always report
`evidence.pure` alongside the result.

`observe_events` and `observe_attempts` answer the same question from the
ledger — *did this role try to reach that region, and what happened* — without
injecting anything into the run. `contained` there is three-valued: **null
means nothing was attempted**, which establishes nothing either way.

## What isolation means here, exactly

The runtime enforces **context-access disjointness**: two roles cannot obtain
bytes from the same region. It does not establish that the model's internal
representation is independent, and it does not claim embedding-space
separation. Enforced information access is not proven representational
independence — say the first, never the second.

## Reporting on a run

Say what the partition actually did: which refusals fired and what each
prevented, what the cache plan cost, whether the chain verifies and replays,
and — from `observe_gate_activity` — what the agents themselves reached for.
Report `containment.claimable` verbatim; if it is false, name the residue.

`context_window_inspect`, `context_scope_closure`,
`context_window_disjointness` and the four assertions are how you find out.
None of it should be asserted from memory of how the partition was set up.

## What ships with this skill

| file | contents |
|---|---|
| [reference/planes.md](reference/planes.md) | the three planes, what each owns, and what each is worth alone |
| [reference/tools.md](reference/tools.md) | all 48 tools, grouped by plane |
| [reference/migration.md](reference/migration.md) | every 0.6.0 name and what replaced it |
