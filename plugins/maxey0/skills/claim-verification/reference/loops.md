# Claim Verification — loops

The 8 loop(s) tagged `claim-verification`. Every entry is a real composition whose regions, roles and refusals were built against a live window before it was written down.

**Status is evidence, not decoration.** `validated` means it was executed and the result recorded. `partial` means some of it was. `draft-unexecuted` means it has never run — treat it as a design, not a guarantee.

## `pipeline:036-claim-lineage-verification-loop`

**Claim Lineage Verification Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

6 stage(s): Conversation Ingestor → Provenance Logger → Provenance Querier → Provenance Signer → Compliance Auditor → Provenance Logger

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

## `pipeline:038-hallucination-attribution-loop`

**Hallucination Attribution Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

7 stage(s): Provenance Logger → Provenance Querier → Conversation Ingestor → Debugger Agent → OTel Collector Agent → Provenance Signer → Provenance Logger

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

## `battery:l1-maker-checker-judge`

**l1-maker-checker-judge**

status `validated` · provenance `battery` · mode `in-window` · topology `star`

| hardening | |
|---|---|
| checked | True |
| passed | True |
| method | harness_dsl.build_init_ops + harness_kit.rebuild (real ContextWindow, real ops) |
| bound_holds | True |
| widest_read_closure | 4 |
| verdict | 3/6 regions refuse all grants; the widest scope reads 4/6; 0 containment breaches |
| reduction_ratio | 1.051 |
| negative_controls_refused | 7/7 |

> L1's 18 real subagent calls (results/coded.json) are the paper's headline maker-checker-judge trial -- scw condition: 3/3 trials disjoint, 0% leakage; flat condition: 0/3 disjoint, 66.7% mean leakage rate.

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
