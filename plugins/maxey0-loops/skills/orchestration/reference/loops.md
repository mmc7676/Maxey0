# Orchestration — loops

The 14 loop(s) tagged `orchestration`. Every entry is a real composition whose regions, roles and refusals were built against a live window before it was written down.

**Status is evidence, not decoration.** `validated` means it was executed and the result recorded. `partial` means some of it was. `draft-unexecuted` means it has never run — treat it as a design, not a guarantee.

## `pipeline:007-hierarchical-task-routing-loop`

**Hierarchical Task Routing Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

7 stage(s): SuperAgent Orchestrator → Retrieval Orchestrator → SuperAgent Orchestrator → API Gateway Engineer → Cost Guard → DR Coordinator → SuperAgent Orchestrator

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

## `pipeline:008-registry-to-execution-orchestration-loop`

**Registry-to-Execution Orchestration Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

7 stage(s): SuperAgent Orchestrator → API Gateway Engineer → Retrieval Orchestrator → LangChain Adapter Agent → MCP Bridge → SuperAgent Orchestrator → Cost Guard

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

## `pipeline:009-swarm-coordination-and-recovery-loop`

**Swarm Coordination and Recovery Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

7 stage(s): SuperAgent Orchestrator → DR Coordinator → Cost Guard → Superposition Agent → Anchor Metrics → Drift Detector → SuperAgent Orchestrator

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

## `pipeline:045-swarm-evaluation-and-re-routing-loop`

**Swarm Evaluation and Re-Routing Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

9 stage(s): Superposition Agent → Anchor Metrics → Cost Guard → DR Coordinator → SuperAgent Orchestrator → Retrieval Orchestrator → Drift Detector → Temporal Drift Agent → Superposition Agent

| hardening | |
|---|---|
| checked | True |
| passed | True |
| method | harness_dsl.build_init_ops + harness_kit.rebuild (real ContextWindow, real ops) |
| bound_holds | True |
| widest_read_closure | 2 |
| verdict | 9/18 regions refuse all grants; the widest scope reads 2/18; 0 containment breaches |
| reduction_ratio | 9.561 |
| negative_controls_refused | 72/72 |

## `pipeline:048-enterprise-agent-governance-loop`

**Enterprise Agent Governance Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

6 stage(s): Security Sentinel → Policy Proxy → SuperAgent Orchestrator → Cost Guard → Compliance Auditor → Security Sentinel

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

## `pipeline:053-distributed-agent-runtime-recovery-loop`

**Distributed Agent Runtime Recovery Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

7 stage(s): Code Interpreter Agent → Backup & Restore → Incident Commander → SuperAgent Orchestrator → DR Coordinator → Security Scanner → Code Interpreter Agent

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

## `pipeline:061-concept-to-latent-to-routing-loop`

**Concept-to-Latent-to-Routing Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

8 stage(s): Seed Agent Graph Agent → Neighborhood Graph Builder → Latent Mapper → Latent GNN Router → Graph GNN Router → SuperAgent Orchestrator → Retrieval Orchestrator → Seed Agent Graph Agent

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

## `pipeline:062-semantic-retrieval-to-agent-routing-loop`

**Semantic Retrieval-to-Agent Routing Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

8 stage(s): Vector Store Agent → Seed Agent Graph Agent → Latent GNN Router → Graph GNN Router → SuperAgent Orchestrator → Retrieval Orchestrator → Context Window Architect → Vector Store Agent

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

## `pipeline:071-actor-critic-agentic-execution-loop`

**Actor-Critic Agentic Execution Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

7 stage(s): SuperAgent Orchestrator → Agentic Runner Agent → QA Agent → Superposition Agent → Anchor Metrics → Drift Detector → SuperAgent Orchestrator

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

## `battery:l3-pipeline`

**l3-pipeline**

status `validated` · provenance `battery` · mode `in-window` · topology `chain`

| hardening | |
|---|---|
| checked | True |
| passed | True |
| method | harness_dsl.build_init_ops + harness_kit.rebuild (real ContextWindow, real ops) |
| bound_holds | True |
| widest_read_closure | 4 |
| verdict | 3/7 regions refuse all grants; the widest scope reads 4/7; 0 containment breaches |
| reduction_ratio | 1.04 |
| negative_controls_refused | 6/6 |

> 3 real scw-condition battery trials, 0 containment breaches.

## `battery:l4-nested`

**l4-nested**

status `partial` · provenance `battery` · mode `in-window` · topology `nested`

| hardening | |
|---|---|
| checked | True |
| passed | False |
| method | harness_dsl.build_init_ops + harness_kit.rebuild (real ContextWindow, real ops) |
| bound_holds | False |
| widest_read_closure | 5 |
| verdict | 2/5 regions refuse all grants; the widest scope reads 5/5; 1 containment breaches |
| reduction_ratio | 1.006 |
| negative_controls_refused | 2/2 |

> Real containment breach in live battery data: 3/3 scw trials show bound_holds=false (grandchild-checker reaching a region it should not) -- flagged, not smoothed over. Nesting is where this dataset's isolation evidence is empirically weakest. Separately, raw per-trial completion markers suggest some L4/scw trials may be missing their grandchild-checker leg despite this aggregate reporting full tri

## `formation:three-agent-loop`

**Planner / implementer / checker formation**

status `validated` · provenance `planned` · mode `in-window` · topology `chain`

| hardening | |
|---|---|
| checked | True |
| passed | True |
| method | scenarios.three_agent_loop() (real run, this build) |
| bound_holds | True |
| widest_read_closure | 0 |
| verdict | 3/7 regions refuse all grants; the widest scope reads 0/7; 0 containment breaches |
| reduction_ratio | None |

> Implemented by this build, per three-agent-loop.md's own spec: bind-to-pad, promote-via-bridge shape; 7 tests in tests/test_formation.py pass, including the two structural refusals and a real disjointness-checked verdict.
