# maxey0-context

**Context plane** — Partition the window and enforce who reads what.

The Context plane, alone. Partition the context window into typed, policy-enforced regions and bind each role to one — the runtime decides what a role can read, not the prompt. A region declares what it is (reference, durable, episodic, working, scratchpad) and the runtime holds every call against it: a bound role reads its own region and is refused elsewhere, a read-only reference region refuses the role that consumes it, and a verdict is refused unless the judge's read closure provably excludes the maker's write closure. Every decision lands in a hash-chained ledger that replays to an identical window. `context_admit` gates what actually crosses a declared handoff — approve, summarize, redact, or reject — and `context_assert_admitted` finds any handoff a scope permits that no such decision has ever governed. 32 tools. No library, no Gate.

## What it owns

Structured Context Windows: regions, scopes, bridges, grants, harnesses, ticks, and the hash-chained ledger.

## Worth installing alone because

Partition a context window and enforce access without ever routing a task or watching an agent.

## The 32 tools

| tool | writes | does |
|---|---|---|
| `context_prompt_create` | yes | Declare an instruction as versioned data rather than as prose. |
| `context_prompt_revise` | yes | Edit a prompt, keeping the superseded version in history. |
| `context_prompt_render` | no | Materialize a prompt against variable bindings. |
| `context_region_create` | yes | Create one typed, budgeted, addressable region of the window. |
| `context_region_close` | yes | Seal a region, or destroy its content when purge_on_close is set. |
| `context_region_write` | yes | Write content into a region. Pass role and the call is scope-checked. |
| `context_region_read` | no | Read a region. Refused, with a hint, when the role's scope excludes it. |
| `context_harness_create` | yes | Declare the environment and architecture a loop runs under. maker_checker makes self-approval a refusal rather than a policy. |
| `context_harness_call` | yes | Record a role invoking a named skill under a harness profile. |
| `context_scope_bind` | yes | Bind a role's execution scope to one region and declare its spec. |
| `context_scope_unbind` | yes | Release a role's scope with a terminal state that has to be earned. |
| `context_scope_closure` | no | The computed set of regions a role can actually reach, read and write. |
| `context_scope_tick` | yes | Advance one iteration and price it. Call once per model call. |
| `context_bridge_open` | yes | Mint an explicit, expiring grant across a region boundary. |
| `context_bridge_close` | yes | Revoke a grant before its TTL expires. |
| `context_bridge_promote` | yes | Move content across a region boundary with provenance attached. |
| `context_criterion_pin` | yes | Freeze the region a run will be graded against, before it runs. |
| `context_criterion_repin` | yes | Accept the criterion's current bytes as the new yardstick. |
| `context_evidence_attest` | yes | Record an external result for a forthcoming verdict. |
| `context_window_inspect` | no | Region map, token accounting, cache economics, and advisories. |
| `context_window_render` | no | Materialize the window as prompt text. Scope-true for a bound role. |
| `context_window_disjointness` | no | Would this judge's verdict on this maker be accepted, and if not why. |
| `context_window_seal` | yes | End setup and close the privileged unbound path. |
| `context_window_reset` | yes | Tear the window down and start a fresh run. Destructive. |
| `context_assert_can_read` | yes | Attempt a real read and expect it to be authorized. |
| `context_assert_cannot_read` | yes | Attempt a real read and expect a refusal. Reports breach if it succeeds. |
| `context_assert_scope_closed` | no | The closure equals what was declared, computed over the region graph. |
| `context_assert_disjoint` | no | No private working space is shared. Overlap is classified: a pad both reach fails; a declared handoff and unwritable reference do not. |
| `context_route_bind` | yes | Route a task and bind the matching loop's partition in this window. |
| `context_formation_build` | yes | Build a maker/checker/judge partition from a named concept. |
| `context_admit` | yes | Gate a content handoff between two roles: approve, summarize, redact, or reject what crosses. Egress, where bridges are ingress. |
| `context_assert_admitted` | no | Every region from_role can write and to_role can read has a recorded context_admit decision naming the pair. |

## Commands

- `/maxey0-context:window`
- `/maxey0-context:run`
- `/maxey0-context:assert`
- `/maxey0-context:scw-deploy`

## Skills

1 skill(s): `scw`

## Install

```bash
/plugin marketplace add mmc7676/Maxey0
/plugin install maxey0-context@maxey0
```

Requires Python 3.10+ with the `mcp` package on the interpreter that `python` resolves to.

## This directory is generated

`scripts/build_planes.py` builds it from the repository root, where the commands, agents, hooks and skills have their single source of truth, and `server/` is copied whole rather than shimmed, because an installed plugin cannot read a file outside its own directory. Do not edit anything here; edit the root and regenerate.

See [docs/LEXICON.md](../../docs/LEXICON.md) for the naming rules and [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) for why the planes divide where they do.
