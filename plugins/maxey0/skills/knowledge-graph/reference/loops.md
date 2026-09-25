# Knowledge Graph — loops

The 13 loop(s) tagged `knowledge-graph`. Every entry is a real composition whose regions, roles and refusals were built against a live window before it was written down.

**Status is evidence, not decoration.** `validated` means it was executed and the result recorded. `partial` means some of it was. `draft-unexecuted` means it has never run — treat it as a design, not a guarantee.

## `pipeline:025-knowledge-graph-construction-loop`

**Knowledge Graph Construction Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

7 stage(s): Seed Agent Graph Agent → Graph Store Agent → Graph GNN Router → Provenance Logger → Neighborhood Graph Builder → QA Agent → Seed Agent Graph Agent

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

## `pipeline:026-graph-neural-routing-loop`

**Graph Neural Routing Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

7 stage(s): Latent GNN Router → Graph GNN Router → Neighborhood Graph Builder → Seed Agent Graph Agent → Vector Store Agent → QA Agent → Latent GNN Router

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

## `pipeline:027-temporal-knowledge-graph-loop`

**Temporal Knowledge Graph Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

7 stage(s): Graph GNN Router → Temporal Drift Agent → Seed Agent Graph Agent → Vector Store Agent → QA Agent → Promotion Policy Agent → Graph GNN Router

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

## `pipeline:029-hybrid-vector-graph-retrieval-loop`

**Hybrid Vector-Graph Retrieval Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

7 stage(s): Vector Store Agent → Seed Agent Graph Agent → Neighborhood Graph Builder → Latent GNN Router → Graph GNN Router → QA Agent → Vector Store Agent

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

## `pipeline:030-research-paper-to-knowledge-graph-loop`

**Research Paper to Knowledge Graph Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

7 stage(s): Seed Agent Graph Agent → Superposition Agent → Temporal Drift Agent → Graph GNN Router → Neighborhood Graph Builder → QA Agent → Seed Agent Graph Agent

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

## `pipeline:060-latent-to-concept-graph-loop`

**Latent-to-Concept Graph Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

9 stage(s): Latent Mapper → PCA Cartographer → UMAP Navigator → Neighborhood Graph Builder → Graph GNN Router → Seed Agent Graph Agent → Provenance Logger → QA Agent → Latent Mapper

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

## `pipeline:067-full-latent-semantic-mapping-loop`

**Full Latent-Semantic Mapping Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

13 stage(s): Anchor Miner → Magnitude Spectrum Mapper → PCA Cartographer → UMAP Navigator → Neighborhood Graph Builder → Latent Mapper → Feature Attribution Analyst → Feature Set Curator → Seed Agent Graph Agent → Graph GNN Router → QA Agent → Frames Steward → Anchor Miner

| hardening | |
|---|---|
| checked | True |
| passed | True |
| method | harness_dsl.build_init_ops + harness_kit.rebuild (real ContextWindow, real ops) |
| bound_holds | True |
| widest_read_closure | 2 |
| verdict | 13/26 regions refuse all grants; the widest scope reads 2/26; 0 containment breaches |
| reduction_ratio | 13.55 |
| negative_controls_refused | 156/156 |

## `pipeline:068-full-semantic-coordinate-construction-loop`

**Full Semantic Coordinate Construction Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

12 stage(s): Latent Mapper → PCA Cartographer → UMAP Navigator → Neighborhood Graph Builder → Seed Agent Graph Agent → Graph GNN Router → State Vector Cartographer → Magnitude Spectrum Mapper → Anchor Miner → Anchor Metrics → Frames Steward → Latent Mapper

| hardening | |
|---|---|
| checked | True |
| passed | True |
| method | harness_dsl.build_init_ops + harness_kit.rebuild (real ContextWindow, real ops) |
| bound_holds | True |
| widest_read_closure | 2 |
| verdict | 12/24 regions refuse all grants; the widest scope reads 2/24; 0 containment breaches |
| reduction_ratio | 12.552 |
| negative_controls_refused | 132/132 |

## `pipeline:073-superposition-coordinate-to-graph-loop`

**Superposition Coordinate-to-Graph Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

10 stage(s): State Vector Cartographer → Magnitude Spectrum Mapper → Anchor Miner → Latent Mapper → Graph GNN Router → Seed Agent Graph Agent → Provenance Logger → Superposition Agent → Anchor Metrics → State Vector Cartographer

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
