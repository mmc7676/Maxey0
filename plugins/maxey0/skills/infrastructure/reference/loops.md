# Infrastructure — loops

The 3 loop(s) tagged `infrastructure`. Every entry is a real composition whose regions, roles and refusals were built against a live window before it was written down.

**Status is evidence, not decoration.** `validated` means it was executed and the result recorded. `partial` means some of it was. `draft-unexecuted` means it has never run — treat it as a design, not a guarantee.

## `pipeline:052-agent-runtime-safety-loop`

**Agent Runtime Safety Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

7 stage(s): Code Interpreter Agent → Sandbox Runner → Security Scanner → Context Boundary Warden → Security Sentinel → Compliance Auditor → Code Interpreter Agent

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

## `pipeline:054-agent-platform-deployment-loop`

**Agent Platform Deployment Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

7 stage(s): Code Interpreter Agent → API Gateway Agent → Integration Engineer → Security Scanner → Sandbox Runner → Backup & Restore → Code Interpreter Agent

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
