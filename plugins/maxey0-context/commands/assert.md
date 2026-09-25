---
description: Test containment by attempting a real read, rather than asserting it from the region graph
argument-hint: "[cannot <role> <region>|can <role> <region>|closed <role>|disjoint <role-a> <role-b>|all]"
allowed-tools: mcp__maxey0-context__context_assert_cannot_read, mcp__maxey0-context__context_assert_can_read, mcp__maxey0-context__context_assert_scope_closed, mcp__maxey0-context__context_assert_disjoint, mcp__maxey0-context__context_scope_closure, mcp__maxey0-context__context_window_inspect
---

Test containment. Mode: **$ARGUMENTS** (default `all`).

## The distinction that matters

Two of these four are stronger evidence than the other two, and the result says
which you got.

| assertion | how it answers |
|---|---|
| `context_assert_cannot_read` | **Attempts a real read** and expects a refusal. Reports `breach: true` if the read succeeds. |
| `context_assert_can_read` | Attempts a real read and expects it to be authorized. |
| `context_assert_scope_closed` | Computes the closure over the region graph. `evidence.pure: true`. |
| `context_assert_disjoint` | Computes closure intersection. `evidence.pure: true`. |

The first two go through the real authorization path, so a refusal is produced
by the enforcement layer, lands in the ledger as a `scw.denied` record, and
replay reproduces it. "The closure does not contain region Y" is a statement
about a data structure. "Role X asked for region Y and the runtime refused,
here is the event" is a statement about the system.

Always report `evidence.pure` alongside the result. Presenting a computation as
though it were an attempt overstates what you know.

## cannot <role> <region>

`context_assert_cannot_read(loop_id="<role>", scw_id="<region>")`.

If `breach: true`, **lead with it**. The runtime authorized a read it was
expected to refuse; that is a headline finding, not a soft negative.

## can <role> <region>

`context_assert_can_read(...)`. A refusal here means the role's partition is
narrower than assumed — report the refusal's own message and hint.

## closed <role>

`context_assert_scope_closed(loop_id="<role>")`. With no expected sets, it
answers whether anything currently widens the role beyond its own partition,
and names the grant that does.

## disjoint <role-a> <role-b>

`context_assert_disjoint(...)`. Reports the overlap, plus the maker/judge
verdict report in both directions — a verdict can be refused for reasons that
have nothing to do with overlap.

## all

Call `context_window_inspect` for the bound roles, then run `closed` for each
and `disjoint` for every pair, then `cannot` for each role against one region
it should not reach. Report a matrix, and say plainly which cells are attempts
and which are computations.

## What this does not establish

The runtime enforces **context-access disjointness**: two roles cannot obtain
bytes from the same region. It does not establish that the model's internal
representation is independent, and it does not claim embedding-space
separation. Enforced information access is not proven representational
independence — say the first, never the second.
