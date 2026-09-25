---
description: Inspect or partition this session's Structured Context Window — regions, scopes, bridges, disjointness, and the audit chain
argument-hint: "[inspect|partition|verify|closure <role>]"
allowed-tools: mcp__maxey0-context__context_window_inspect, mcp__maxey0-context__context_window_reset, mcp__maxey0-context__context_region_create, mcp__maxey0-context__context_region_write, mcp__maxey0-context__context_harness_create, mcp__maxey0-context__context_scope_bind, mcp__maxey0-context__context_window_seal, mcp__maxey0-context__context_scope_closure, mcp__maxey0-context__context_window_disjointness, mcp__maxey0-context__context_criterion_pin
---

Work with this session's live window. Mode: **$ARGUMENTS** (default `inspect`).

## inspect

Call `context_window_inspect`. Report the region map — each region's type,
token ceiling and current use — then the bound roles, the open bridges with
their remaining TTL, the cache plan for the next iteration, and any advisories.

Say what is *not* established as well as what is. A window with no bound roles
has no containment properties at all, and reporting it as clean would be wrong.

## partition

Build a partition from scratch. Narrate each step — the taxonomy is the
interesting part, and a silent partition teaches nothing.

1. `context_window_reset` — destructive. Confirm first.
2. `context_region_create`, one per region. The type is a policy, not a label:

   | type | mutability | bridgeable | for |
   |---|---|---|---|
   | `reference` | read-only | yes | instructions, corpus, a pinned rubric |
   | `durable` | writable | yes | what should survive the run |
   | `episodic` | writable | yes | run history, promoted findings |
   | `working` | writable | **no** | task state nothing else may reach |
   | `scratchpad` | volatile | **no** | per-iteration reasoning, cleared each tick |

3. `context_region_write` the reference material **as the host, before any
   binding**. A bound role cannot write a reference region, and that refusal is
   the point.
4. `context_criterion_pin` if anything will be graded.
5. `context_harness_create` with `architecture="maker_checker"` — this makes
   self-approval a refusal rather than a policy.
6. `context_scope_bind` each role to **its own scratchpad**, with one durable
   region to publish into. Scratchpads are unbridgeable, so a downstream role
   reads the published output and cannot reach the reasoning — there is no
   grant to mint.
7. `context_window_seal` — ends setup and closes the privileged unbound path.

## verify

Call `context_window_inspect` and report whether the hash chain verifies and
whether the log replays to an identical window. Both, separately. A chain that
verifies proves nothing was altered; a replay that reconstructs proves the log
is complete rather than a commentary on the run.

## closure <role>

Call `context_scope_closure(loop_id="<role>")` and answer two questions
plainly: what can this role reach right now, and what is it walled off from.
Then `context_window_disjointness` for a maker/judge pair if one is bound.

If you cannot say what a role is allowed to read, do not report it as
contained.

## Rules

- **Never route around a refusal.** `isolation_violation` and
  `policy_violation` are the system working. Read the `hint` — it names the
  bridge that would legitimize the access — and decide whether that access is
  actually justified.
- **Grants expire.** Prefer `ttl_ticks=1`. A standing grant is a wall with a
  door propped open.
- **`context_window_reset` destroys the window.** Confirm before calling it.
