# Protocol — loops

The 5 loop(s) tagged `protocol`. Every entry is a real composition whose regions, roles and refusals were built against a live window before it was written down.

**Status is evidence, not decoration.** `validated` means it was executed and the result recorded. `partial` means some of it was. `draft-unexecuted` means it has never run — treat it as a design, not a guarantee.

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

## `pipeline:010-a2a-contract-execution-loop`

**A2A Contract Execution Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

5 stage(s): MCP Bridge → LangChain Adapter Agent → Retrieval Orchestrator → SuperAgent Orchestrator → MCP Bridge

| hardening | |
|---|---|
| checked | True |
| passed | True |
| method | harness_dsl.build_init_ops + harness_kit.rebuild (real ContextWindow, real ops) |
| bound_holds | True |
| widest_read_closure | 2 |
| verdict | 5/10 regions refuse all grants; the widest scope reads 2/10; 0 containment breaches |
| reduction_ratio | 5.59 |
| negative_controls_refused | 20/20 |

## `pipeline:011-mcp-federated-tool-loop`

**MCP Federated Tool Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

7 stage(s): MCP Bridge → Memory API Keeper → Runner API Keeper → Retrieval Orchestrator → Memory API Keeper → QA Agent → MCP Bridge

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

## `pipeline:012-protocol-translation-and-validation-loop`

**Protocol Translation and Validation Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

6 stage(s): LangChain Adapter Agent → MCP Bridge → QA Agent → Memory API Keeper → Runner API Keeper → LangChain Adapter Agent

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

## `pipeline:050-cross-organization-policy-negotiation-loop`

**Cross-Organization Policy Negotiation Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

7 stage(s): Security Sentinel → Policy Proxy → LangChain Adapter Agent → MCP Bridge → SuperAgent Orchestrator → Compliance Auditor → Security Sentinel

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
