# I/O Contract — loops

The 5 loop(s) tagged `io-contract`. Every entry is a real composition whose regions, roles and refusals were built against a live window before it was written down.

**Status is evidence, not decoration.** `validated` means it was executed and the result recorded. `partial` means some of it was. `draft-unexecuted` means it has never run — treat it as a design, not a guarantee.

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

## `pipeline:013-tool-capability-negotiation-loop`

**Tool Capability Negotiation Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

5 stage(s): Memory API Keeper → MCP Bridge → Runner API Keeper → QA Agent → Memory API Keeper

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

## `pipeline:055-tool-schema-to-inference-loop`

**Tool Schema to Inference Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

7 stage(s): Memory API Keeper → MCP Bridge → Runner API Keeper → API Gateway Agent → Code Interpreter Agent → QA Agent → Memory API Keeper

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

## `pipeline:056-ai-platform-contract-loop`

**AI Platform Contract Loop**

status `validated` · provenance `pipeline` · mode `in-window` · topology `chain`

7 stage(s): Code Interpreter Agent → Memory API Keeper → API Gateway Agent → QA Agent → MCP Bridge → Runner API Keeper → Code Interpreter Agent

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
