# Observability — loops

The 9 loop(s) tagged `observability`. Every entry is a real composition whose regions, roles and refusals were built against a live window before it was written down.

**Status is evidence, not decoration.** `validated` means it was executed and the result recorded. `partial` means some of it was. `draft-unexecuted` means it has never run — treat it as a design, not a guarantee.

## `pipeline:037-hallucination-localization-loop`

**Hallucination Localization Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

7 stage(s): Provenance Logger → Provenance Querier → Debugger Agent → OTel Collector Agent → Provenance Signer → Compliance Auditor → Provenance Logger

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

## `pipeline:039-reasoning-path-instrumentation-loop`

**Reasoning Path Instrumentation Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

8 stage(s): Debugger Agent → OTel Collector Agent → Provenance Signer → OTel Module Agent → Grafana Agent → Context Window Architect → SCW Packing Schema Agent → Debugger Agent

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

## `pipeline:040-ai-observability-feedback-loop`

**AI Observability Feedback Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

10 stage(s): OTel Collector Agent → OTel Module Agent → Grafana Agent → Debugger Agent → Context Window Architect → SCW Packing Schema Agent → Superposition Agent → Anchor Metrics → Drift Detector → OTel Collector Agent

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

## `pipeline:041-agent-trace-diagnosis-loop`

**Agent Trace Diagnosis Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

8 stage(s): Debugger Agent → OTel Module Agent → Grafana Agent → Provenance Logger → OTel Collector Agent → Superposition Agent → Anchor Metrics → Debugger Agent

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

## `pipeline:069-superposition-observation-and-coordinate-loop`

**Superposition Observation and Coordinate Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

9 stage(s): Superposition Agent → Drift Detector → Temporal Drift Agent → Anchor Metrics → State Vector Cartographer → Magnitude Spectrum Mapper → Anchor Miner → Anchor Metrics → Superposition Agent

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
