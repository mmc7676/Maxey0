# Migration from 0.6.0

Every retired name, and what replaced it. The old names are gone rather than aliased: an alias would double the surface and let the old vocabulary survive in transcripts, which is the drift 0.7.0 exists to end.

| 0.6.0 | 0.7.0 |
|---|---|
| `assert_can_read` | `context_assert_can_read` |
| `assert_cannot_read` | `context_assert_cannot_read` |
| `assert_disjoint` | `context_assert_disjoint` |
| `assert_scope_closed` | `context_assert_scope_closed` |
| `attest_evidence` | `context_evidence_attest` |
| `bind_scope` | `context_scope_bind` |
| `check_disjointness` | `context_window_disjointness` |
| `close_bridge` | `context_bridge_close` |
| `close_scw` | `context_region_close` |
| `create_concept_scw` | `context_formation_build` |
| `create_harness` | `context_harness_create` |
| `create_prompt` | `context_prompt_create` |
| `create_scw` | `context_region_create` |
| `declare_gate_policy` | `observe_gate_policy` |
| `gate_activity` | `observe_gate_activity` |
| `gate_mode` | `observe_gate_mode` |
| `harness_call` | `context_harness_call` |
| `inspect_window` | `context_window_inspect` |
| `isolation_level` | `observe_isolation_level` |
| `loop_tick` | `context_scope_tick` |
| `maxey0_access_attempts` | `observe_attempts` |
| `maxey0_agents` | `loops_agents` |
| `maxey0_concepts` | `loops_concepts` |
| `maxey0_cross_window_create` | `loops_crosswindow_create` |
| `maxey0_cross_window_ingest` | `loops_crosswindow_ingest` |
| `maxey0_cross_window_report` | `loops_crosswindow_report` |
| `maxey0_cross_window_status` | `loops_crosswindow_status` |
| `maxey0_loops` | `loops_catalog` |
| `maxey0_observe` | `observe_events` |
| `maxey0_route` | `loops_route` |
| `maxey0_studio` | `observe_studio` |
| `maxey0_traces` | `observe_traces` |
| `open_bridge` | `context_bridge_open` |
| `pin_criterion` | `context_criterion_pin` |
| `promote` | `context_bridge_promote` |
| `read` | `context_region_read` |
| `render_prompt` | `context_prompt_render` |
| `render_window` | `context_window_render` |
| `repin_criterion` | `context_criterion_repin` |
| `reset_window` | `context_window_reset` |
| `revise_prompt` | `context_prompt_revise` |
| `route_task` | `context_route_bind` |
| `scope_closure` | `context_scope_closure` |
| `seal_window` | `context_window_seal` |
| `unbind_scope` | `context_scope_unbind` |
| `write` | `context_region_write` |

## Commands

| 0.6.0 | 0.7.0 |
|---|---|
| `/maxey0:scw` | `/maxey0:window` |
| `/maxey0:loop` | `/maxey0:run` |
| `/maxey0:cross-window` | `/maxey0:crosswindow` |
| `/maxey0:experiment-run` | removed from the product; see the `maxey0-lab` connector |

## Connectors

| 0.6.0 | 0.7.0 |
|---|---|
| `worlds` | `maxey0-context` (plus `maxey0-observe` for the Gate) |
| `maxey0` | `maxey0-loops` |

## Agents

| 0.6.0 | 0.7.0 |
|---|---|
| `agent-role` | `maxey0-role`, and `maxey0-maker` / `maxey0-checker` for those positions |
| `loop-judge` | `maxey0-judge` |
