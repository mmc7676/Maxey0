# The 50 tools

Every tool name begins with its plane. Generated from the catalog, so this list is what the product registers.

## Context — `maxey0-context`

### prompt

| tool | writes | does |
|---|---|---|
| `context_prompt_create` | yes | Declare an instruction as versioned data rather than as prose. |
| `context_prompt_revise` | yes | Edit a prompt, keeping the superseded version in history. |
| `context_prompt_render` | no | Materialize a prompt against variable bindings. |

### region

| tool | writes | does |
|---|---|---|
| `context_region_create` | yes | Create one typed, budgeted, addressable region of the window. |
| `context_region_close` | yes | Seal a region, or destroy its content when purge_on_close is set. |
| `context_region_write` | yes | Write content into a region. Pass role and the call is scope-checked. |
| `context_region_read` | no | Read a region. Refused, with a hint, when the role's scope excludes it. |

### harness

| tool | writes | does |
|---|---|---|
| `context_harness_create` | yes | Declare the environment and architecture a loop runs under. maker_checker makes self-approval a refusal rather than a policy. |
| `context_harness_call` | yes | Record a role invoking a named skill under a harness profile. |

### scope

| tool | writes | does |
|---|---|---|
| `context_scope_bind` | yes | Bind a role's execution scope to one region and declare its spec. |
| `context_scope_unbind` | yes | Release a role's scope with a terminal state that has to be earned. |
| `context_scope_closure` | no | The computed set of regions a role can actually reach, read and write. |
| `context_scope_tick` | yes | Advance one iteration and price it. Call once per model call. |

### bridge

| tool | writes | does |
|---|---|---|
| `context_bridge_open` | yes | Mint an explicit, expiring grant across a region boundary. |
| `context_bridge_close` | yes | Revoke a grant before its TTL expires. |
| `context_bridge_promote` | yes | Move content across a region boundary with provenance attached. |

### evidence

| tool | writes | does |
|---|---|---|
| `context_criterion_pin` | yes | Freeze the region a run will be graded against, before it runs. |
| `context_criterion_repin` | yes | Accept the criterion's current bytes as the new yardstick. |
| `context_evidence_attest` | yes | Record an external result for a forthcoming verdict. |

### window

| tool | writes | does |
|---|---|---|
| `context_window_inspect` | no | Region map, token accounting, cache economics, and advisories. |
| `context_window_render` | no | Materialize the window as prompt text. Scope-true for a bound role. |
| `context_window_disjointness` | no | Would this judge's verdict on this maker be accepted, and if not why. |
| `context_window_seal` | yes | End setup and close the privileged unbound path. |
| `context_window_reset` | yes | Tear the window down and start a fresh run. Destructive. |

### assert

| tool | writes | does |
|---|---|---|
| `context_assert_can_read` | yes | Attempt a real read and expect it to be authorized. |
| `context_assert_cannot_read` | yes | Attempt a real read and expect a refusal. Reports breach if it succeeds. |
| `context_assert_scope_closed` | no | The closure equals what was declared, computed over the region graph. |
| `context_assert_disjoint` | no | No private working space is shared. Overlap is classified: a pad both reach fails; a declared handoff and unwritable reference do not. |
| `context_assert_admitted` | no | Every region from_role can write and to_role can read has a recorded context_admit decision naming the pair. |

### route

| tool | writes | does |
|---|---|---|
| `context_route_bind` | yes | Route a task and bind the matching loop's partition in this window. |
| `context_formation_build` | yes | Build a maker/checker/judge partition from a named concept. |

### admit

| tool | writes | does |
|---|---|---|
| `context_admit` | yes | Gate a content handoff between two roles: approve, summarize, redact, or reject what crosses. Egress, where bridges are ingress. |

## Loop — `maxey0-loops`

### surface

| tool | writes | does |
|---|---|---|
| `loops_menu` | no | The whole Maxey0 control surface, rendered from the registry. |

### library

| tool | writes | does |
|---|---|---|
| `loops_concepts` | no | The 16 concepts, their tag vocabularies, and their loop coverage. |
| `loops_skills` | no | The 83 skills, grouped by concept, with the agents each one binds. |
| `loops_agents` | no | The 67 registry agents and their specializations. |
| `loops_catalog` | no | The 84 hardened loops, filterable, each with its hardening record. |

### route

| tool | writes | does |
|---|---|---|
| `loops_route` | no | Score a task against the library and explain the decision. Binds nothing — use context_route_bind to commit. |

### crosswindow

| tool | writes | does |
|---|---|---|
| `loops_crosswindow_create` | yes | Plan a cross-window run over one of the five topologies. |
| `loops_crosswindow_status` | no | The next pending call in a cross-window run. |
| `loops_crosswindow_ingest` | yes | Record one participant's real response and splice it downstream. |
| `loops_crosswindow_report` | no | Grep every dispatched prompt for other participants' markers. Real leak detection, not an assertion that there was none. |

## Observatory — `maxey0-observe`

### stream

| tool | writes | does |
|---|---|---|
| `observe_events` | no | The Context plane's ledger as a typed, queryable stream. |
| `observe_attempts` | no | Did this role attempt this region, and what happened. contained is three-valued; null means nothing was attempted. |
| `observe_traces` | no | The context, execution and state traces, correlated causally. |

### gate

| tool | writes | does |
|---|---|---|
| `observe_gate_mode` | yes | Read or set the Gate: enforce, observe, or off. |
| `observe_gate_policy` | yes | Declare what a bound role may reach outside the window. |
| `observe_gate_activity` | no | What the delegated agents actually did, per role, from the journal. |
| `observe_isolation_level` | no | Which of L0-L3 the evidence supports, and the shortfall where it is below what was declared. |

### studio

| tool | writes | does |
|---|---|---|
| `observe_studio` | no | The Studio's address and start command. |
