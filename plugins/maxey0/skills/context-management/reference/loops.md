# Context Management — loops

The 16 loop(s) tagged `context-management`. Every entry is a real composition whose regions, roles and refusals were built against a live window before it was written down.

**Status is evidence, not decoration.** `validated` means it was executed and the result recorded. `partial` means some of it was. `draft-unexecuted` means it has never run — treat it as a design, not a guarantee.

## `pipeline:014-retrieval-to-scw-reasoning-loop`

**Retrieval-to-SCW Reasoning Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

10 stage(s): Retrieval Orchestrator → Memory API Keeper → Context Window Architect → SCW ReasoningFrame Schema Agent → SCW Packing Schema Agent → Frames Steward → Anchor Miner → Anchor Metrics → Context Window Architect → Retrieval Orchestrator

| hardening | |
|---|---|
| checked | True |
| passed | True |
| method | harness_dsl.build_init_ops + harness_kit.rebuild (real ContextWindow, real ops) |
| bound_holds | True |
| widest_read_closure | 2 |
| verdict | 10/20 regions refuse all grants; the widest scope reads 2/20; 0 containment breaches |
| reduction_ratio | 10.557 |
| negative_controls_refused | 90/90 |

## `pipeline:015-scw-construction-and-packing-loop`

**SCW Construction and Packing Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

8 stage(s): Context Window Architect → SCW ReasoningFrame Schema Agent → SCW Packing Schema Agent → Cost Guard → Debugger Agent → OTel Collector Agent → SCW Packing Schema Agent → Context Window Architect

| hardening | |
|---|---|
| checked | True |
| passed | True |
| method | harness_dsl.build_init_ops + harness_kit.rebuild (real ContextWindow, real ops) |
| bound_holds | True |
| widest_read_closure | 2 |
| verdict | 8/16 regions refuse all grants; the widest scope reads 2/16; 0 containment breaches |
| reduction_ratio | 8.565 |
| negative_controls_refused | 56/56 |

## `pipeline:016-context-boundary-enforcement-loop`

**Context Boundary Enforcement Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

8 stage(s): Context Boundary Warden → Policy Proxy → Security Sentinel → Working Memory Manager → Provenance Logger → Provenance Querier → Compliance Auditor → Context Boundary Warden

| hardening | |
|---|---|
| checked | True |
| passed | True |
| method | harness_dsl.build_init_ops + harness_kit.rebuild (real ContextWindow, real ops) |
| bound_holds | True |
| widest_read_closure | 2 |
| verdict | 8/16 regions refuse all grants; the widest scope reads 2/16; 0 containment breaches |
| reduction_ratio | 8.565 |
| negative_controls_refused | 56/56 |

## `pipeline:017-context-persistence-and-rehydration-loop`

**Context Persistence and Rehydration Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

8 stage(s): Working Memory Manager → Artifact Store → Vector Store Agent → Provenance Logger → Provenance Querier → Memory Manager → Context Window Architect → Working Memory Manager

| hardening | |
|---|---|
| checked | True |
| passed | True |
| method | harness_dsl.build_init_ops + harness_kit.rebuild (real ContextWindow, real ops) |
| bound_holds | True |
| widest_read_closure | 2 |
| verdict | 8/16 regions refuse all grants; the widest scope reads 2/16; 0 containment breaches |
| reduction_ratio | 8.565 |
| negative_controls_refused | 56/56 |

## `pipeline:043-context-utilization-optimization-loop`

**Context Utilization Optimization Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

7 stage(s): Debugger Agent → OTel Collector Agent → Context Window Architect → SCW Packing Schema Agent → SCW ReasoningFrame Schema Agent → Cost Guard → Debugger Agent

| hardening | |
|---|---|
| checked | True |
| passed | True |
| method | harness_dsl.build_init_ops + harness_kit.rebuild (real ContextWindow, real ops) |
| bound_holds | True |
| widest_read_closure | 2 |
| verdict | 7/14 regions refuse all grants; the widest scope reads 2/14; 0 containment breaches |
| reduction_ratio | 7.571 |
| negative_controls_refused | 42/42 |

## `pipeline:057-scw-lineage-and-provenance-loop`

**SCW Lineage and Provenance Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

8 stage(s): Provenance Logger → Provenance Querier → Provenance Signer → Frames Steward → Anchor Miner → Anchor Metrics → Compliance Auditor → Provenance Logger

| hardening | |
|---|---|
| checked | True |
| passed | True |
| method | harness_dsl.build_init_ops + harness_kit.rebuild (real ContextWindow, real ops) |
| bound_holds | True |
| widest_read_closure | 2 |
| verdict | 8/16 regions refuse all grants; the widest scope reads 2/16; 0 containment breaches |
| reduction_ratio | 8.565 |
| negative_controls_refused | 56/56 |

## `pipeline:063-full-semantic-context-control-loop`

**Full Semantic Context Control Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

10 stage(s): Seed Agent Graph Agent → Graph GNN Router → Vector Store Agent → Neighborhood Graph Builder → Retrieval Orchestrator → Context Window Architect → SCW ReasoningFrame Schema Agent → Frames Steward → Anchor Miner → Seed Agent Graph Agent

| hardening | |
|---|---|
| checked | True |
| passed | True |
| method | harness_dsl.build_init_ops + harness_kit.rebuild (real ContextWindow, real ops) |
| bound_holds | True |
| widest_read_closure | 2 |
| verdict | 10/20 regions refuse all grants; the widest scope reads 2/20; 0 containment breaches |
| reduction_ratio | 10.557 |
| negative_controls_refused | 90/90 |

## `pipeline:064-full-agentic-memory-to-reasoning-loop`

**Full Agentic Memory-to-Reasoning Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

14 stage(s): Conversation Importer Agent → Conversation Store Agent → Session Store Manager → Working Memory Manager → Seed Agent Graph Agent → Graph GNN Router → Retrieval Orchestrator → Context Window Architect → Frames Steward → Anchor Miner → Anchor Metrics → Promotion Policy Agent → Provenance Logger → Conversation Importer Agent

| hardening | |
|---|---|
| checked | True |
| passed | True |
| method | harness_dsl.build_init_ops + harness_kit.rebuild (real ContextWindow, real ops) |
| bound_holds | True |
| widest_read_closure | 2 |
| verdict | 14/28 regions refuse all grants; the widest scope reads 2/28; 0 containment breaches |
| reduction_ratio | 14.548 |
| negative_controls_refused | 182/182 |

## `pipeline:065-full-agentic-observability-loop`

**Full Agentic Observability Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

14 stage(s): OTel Collector Agent → OTel Module Agent → Grafana Agent → Debugger Agent → Provenance Logger → Provenance Signer → Context Window Architect → SCW Packing Schema Agent → Superposition Agent → Drift Detector → Temporal Drift Agent → Provenance Querier → Anchor Metrics → OTel Collector Agent

| hardening | |
|---|---|
| checked | True |
| passed | True |
| method | harness_dsl.build_init_ops + harness_kit.rebuild (real ContextWindow, real ops) |
| bound_holds | True |
| widest_read_closure | 2 |
| verdict | 14/28 regions refuse all grants; the widest scope reads 2/28; 0 containment breaches |
| reduction_ratio | 14.548 |
| negative_controls_refused | 182/182 |

## `pipeline:066-full-agentic-governance-loop`

**Full Agentic Governance Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

10 stage(s): Compliance Auditor → Security Sentinel → Policy Proxy → Cost Guard → SuperAgent Orchestrator → Working Memory Manager → Database Architect → Context Boundary Warden → Security Sentinel → Compliance Auditor

| hardening | |
|---|---|
| checked | True |
| passed | True |
| method | harness_dsl.build_init_ops + harness_kit.rebuild (real ContextWindow, real ops) |
| bound_holds | True |
| widest_read_closure | 2 |
| verdict | 10/20 regions refuse all grants; the widest scope reads 2/20; 0 containment breaches |
| reduction_ratio | 10.557 |
| negative_controls_refused | 90/90 |

## `pipeline:074-maxey0-closed-loop-agentic-operating-cycle`

**Maxey0 Closed-Loop Agentic Operating Cycle**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

20 stage(s): SuperAgent Orchestrator → Retrieval Orchestrator → Memory Manager → Working Memory Manager → Context Window Architect → Frames Steward → Anchor Miner → Graph GNN Router → Seed Agent Graph Agent → Code Interpreter Agent → Debugger Agent → OTel Collector Agent → Provenance Logger → Superposition Agent → Anchor Metrics → Drift Detector → Security Sentinel → Compliance Auditor → Promotion Policy Agent → SuperAgent Orchestrator

| hardening | |
|---|---|
| checked | True |
| passed | True |
| method | harness_dsl.build_init_ops + harness_kit.rebuild (real ContextWindow, real ops) |
| bound_holds | True |
| widest_read_closure | 2 |
| verdict | 20/40 regions refuse all grants; the widest scope reads 2/40; 0 containment breaches |
| reduction_ratio | 20.542 |
| negative_controls_refused | 380/380 |

> source data validation warnings present -- see source_validation

## `designer:01-horizontal-4way`

**horizontal 4way**

status `draft-unexecuted` · provenance `designer` · mode `cross-window` · topology `schema1 (horizontal)`

| hardening | |
|---|---|
| checked | False |
| passed | None |
| method | cross_window.run_topology() -- one isolated subagent dispatch per Maxey#/SCW# participant, zero shared context by construction; not yet run for this topology |

> Designed, not yet run. Run it for real from the Studio's Designer view ("Run cross-window") or the run_cross_window_loop MCP tool.

## `designer:02-vertical-nesting`

**vertical nesting**

status `draft-unexecuted` · provenance `designer` · mode `cross-window` · topology `schema2 (vertical + horizontal)`

| hardening | |
|---|---|
| checked | False |
| passed | None |
| method | cross_window.run_topology() -- one isolated subagent dispatch per Maxey#/SCW# participant, zero shared context by construction; not yet run for this topology |

> Designed, not yet run. Run it for real from the Studio's Designer view ("Run cross-window") or the run_cross_window_loop MCP tool.

## `designer:03-fanin-scaling`

**fanin scaling**

status `draft-unexecuted` · provenance `designer` · mode `cross-window` · topology `schema4 (N-to-1 fan-in)`

| hardening | |
|---|---|
| checked | False |
| passed | None |
| method | cross_window.run_topology() -- one isolated subagent dispatch per Maxey#/SCW# participant, zero shared context by construction; not yet run for this topology |

> Designed, not yet run. Run it for real from the Studio's Designer view ("Run cross-window") or the run_cross_window_loop MCP tool.

## `designer:04-adversarial-embedded-canary`

**adversarial embedded canary**

status `draft-unexecuted` · provenance `designer` · mode `cross-window` · topology `schema3, hardened`

| hardening | |
|---|---|
| checked | False |
| passed | None |
| method | cross_window.run_topology() -- one isolated subagent dispatch per Maxey#/SCW# participant, zero shared context by construction; not yet run for this topology |

> Designed, not yet run. Run it for real from the Studio's Designer view ("Run cross-window") or the run_cross_window_loop MCP tool.

## `designer:05-multiround-persistence`

**multiround persistence**

status `draft-unexecuted` · provenance `designer` · mode `cross-window` · topology `loop persistence across iterations`

| hardening | |
|---|---|
| checked | False |
| passed | None |
| method | cross_window.run_topology() -- one isolated subagent dispatch per Maxey#/SCW# participant, zero shared context by construction; not yet run for this topology |

> Designed, not yet run. Run it for real from the Studio's Designer view ("Run cross-window") or the run_cross_window_loop MCP tool.
