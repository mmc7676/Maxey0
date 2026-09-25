# Memory — loops

The 14 loop(s) tagged `memory`. Every entry is a real composition whose regions, roles and refusals were built against a live window before it was written down.

**Status is evidence, not decoration.** `validated` means it was executed and the result recorded. `partial` means some of it was. `draft-unexecuted` means it has never run — treat it as a design, not a guarantee.

## `pipeline:001-memory-lifecycle-promotion-loop`

**Memory Lifecycle Promotion Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

10 stage(s): Memory Manager → Working Memory Manager → Promotion Policy Agent → Compliance Auditor → Provenance Signer → Provenance Logger → Database Architect → Graph Store Agent → Vector Store Agent → Promotion Policy Agent

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

## `pipeline:002-conversation-to-semantic-memory-loop`

**Conversation-to-Semantic-Memory Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

10 stage(s): Conversation Importer Agent → Conversation Store Agent → Session Store Manager → Working Memory Manager → Seed Agent Graph Agent → Graph GNN Router → QA Agent → Promotion Policy Agent → Provenance Logger → Memory Manager

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

## `pipeline:003-working-memory-rehydration-loop`

**Working-Memory Rehydration Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

7 stage(s): Memory Manager → Memory API Keeper → Working Memory Manager → Session Store Manager → Conversation Store Agent → Promotion Policy Agent → Working Memory Manager

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

## `pipeline:004-semantic-memory-construction-loop`

**Semantic Memory Construction Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

6 stage(s): Seed Agent Graph Agent → Graph GNN Router → Provenance Logger → QA Agent → Neighborhood Graph Builder → Seed Agent Graph Agent

| hardening | |
|---|---|
| checked | True |
| passed | True |
| method | harness_dsl.build_init_ops + harness_kit.rebuild (real ContextWindow, real ops) |
| bound_holds | True |
| widest_read_closure | 2 |
| verdict | 6/12 regions refuse all grants; the widest scope reads 2/12; 0 containment breaches |
| reduction_ratio | 6.579 |
| negative_controls_refused | 30/30 |

## `pipeline:005-persistent-graph-vector-memory-loop`

**Persistent Graph-Vector Memory Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

7 stage(s): Database Architect → Graph Store Agent → Vector Store Agent → Seed Agent Graph Agent → Neighborhood Graph Builder → QA Agent → Database Architect

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

## `pipeline:006-memory-promotion-governance-loop`

**Memory Promotion Governance Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

8 stage(s): Promotion Policy Agent → Provenance Signer → Provenance Logger → Security Sentinel → Compliance Auditor → Working Memory Manager → Database Architect → Promotion Policy Agent

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

## `pipeline:028-memory-graph-evolution-loop`

**Memory Graph Evolution Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

7 stage(s): Graph GNN Router → Seed Agent Graph Agent → QA Agent → Promotion Policy Agent → Provenance Logger → Provenance Signer → Graph GNN Router

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

## `pipeline:042-memory-access-telemetry-loop`

**Memory Access Telemetry Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

8 stage(s): OTel Collector Agent → Provenance Logger → Debugger Agent → Memory Manager → Working Memory Manager → Promotion Policy Agent → Compliance Auditor → OTel Collector Agent

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

## `pipeline:051-enterprise-memory-isolation-loop`

**Enterprise Memory Isolation Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

8 stage(s): Security Sentinel → Working Memory Manager → Database Architect → Context Boundary Warden → Policy Proxy → Promotion Policy Agent → Compliance Auditor → Security Sentinel

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
