# Evaluation — loops

The 7 loop(s) tagged `evaluation`. Every entry is a real composition whose regions, roles and refusals were built against a live window before it was written down.

**Status is evidence, not decoration.** `validated` means it was executed and the result recorded. `partial` means some of it was. `draft-unexecuted` means it has never run — treat it as a design, not a guarantee.

## `pipeline:044-agent-evaluation-and-drift-loop`

**Agent Evaluation and Drift Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

7 stage(s): Superposition Agent → Drift Detector → Temporal Drift Agent → Vector Store Agent → Latent Mapper → Anchor Metrics → Superposition Agent

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

## `pipeline:046-retrieval-attribution-evaluation-loop`

**Retrieval Attribution Evaluation Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

9 stage(s): Superposition Agent → Provenance Querier → Anchor Metrics → Vector Store Agent → Seed Agent Graph Agent → Neighborhood Graph Builder → Context Window Architect → Provenance Logger → Superposition Agent

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

> source data validation warnings present -- see source_validation

## `pipeline:058-latent-provenance-and-evaluation-loop`

**Latent Provenance and Evaluation Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

8 stage(s): Vector Store Agent → Cross-Modality Mapper → Feature Attribution Analyst → Feature Set Curator → Superposition Agent → Provenance Querier → Anchor Metrics → Vector Store Agent

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

## `pipeline:059-latent-drift-control-loop`

**Latent Drift Control Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

9 stage(s): Latent Mapper → Magnitude Spectrum Mapper → PCA Cartographer → UMAP Navigator → Neighborhood Graph Builder → Drift Detector → Temporal Drift Agent → Anchor Metrics → Latent Mapper

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
