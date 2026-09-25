---
description: Read or set the Gate, declare a role's reach outside the window, and report what the agents actually did
argument-hint: "[status|observe|enforce|off|policy <role>|activity|level]"
allowed-tools: mcp__maxey0-observe__observe_gate_mode, mcp__maxey0-observe__observe_gate_policy, mcp__maxey0-observe__observe_gate_activity, mcp__maxey0-observe__observe_isolation_level, mcp__maxey0-observe__observe_traces
---

Work the Gate. Mode: **$ARGUMENTS** (default `status`).

The Gate stands at every tool call. A tool call is the only moment an agent in
a delegated context has to ask its host for something, so it is the only place
an outside observer can stand — between two calls a subagent is a sealed box.

## status

`observe_gate_mode()` for the current mode, then `observe_gate_activity()`.
Report the mode, whether a journal exists, and — if it does — the chain
verification and `containment.claimable` verbatim.

`available: false` means no subagent has run yet. The Gate records nothing
until there is a delegated call to intercept. That is not a fault.

## observe | enforce | off

`observe_gate_mode(mode="<mode>")`.

| mode | behavior | what it is for |
|---|---|---|
| `enforce` | out-of-scope calls denied; the refusal reaches the model | production |
| `observe` | everything recorded, nothing blocked | measuring what roles *would* do |
| `off` | inert | the control condition |

**`observe` is not a weaker `enforce`.** It is the only way to measure how
often a role *attempts* to leave its partition, which is a property of the
formation rather than of the enforcement.

If the mode is pinned by `MAXEY0_GATE_MODE`, say so and do not try to work
around it.

## policy <role>

`observe_gate_policy(role="<role>", read_paths=[], tools=[...])`.

Default to nothing. A role in a partitioned loop works from what the render
gave it; needing the repo is a decision to record, not a convenience to leave
open. Never grant `bash_allow` unless a shell is genuinely required.

A policy is declared by the host **before** dispatch. A role that could widen
its own scope would satisfy any containment rule vacuously.

## activity

`observe_gate_activity()`. Report per role: what it reached for, what was
allowed, what was refused. Then `containment.claimable` verbatim.

If it is false, **name the residue** — unattributed calls, fail-opens, lost
records. Each means the run has a hole exactly where the evidence would go. Do
not average it away.

## level

`observe_isolation_level(declared="<L0_none|L1_logical|L2_execution|L3_observed>")`.

A level is **earned from evidence, never asserted**. Declare L3 and get L1 —
three roles dispatched into one shared context, the partition existing only in
the prompt — and nothing else in the stack would notice. This is what notices.
Report the evidenced level, the declared one, and the shortfall between them.

Add `observe_traces()` when the question is *why* they differ: it correlates
what each role was given with what it then did, and flags where those disagree.
