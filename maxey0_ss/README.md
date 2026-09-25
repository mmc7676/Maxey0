# Maxey0 Full Stack

Maxey0-SuperSpace is the harness-neutral system layer. The model and agent harness remain outside the Maxey0 product boundary.

## Actual product boundary

```text
                         MAXEY0
                           |
       +-------------------+-------------------+
       |                   |                   |
       v                   v                   v
 CONTEXT GRAPH       EXECUTION GRAPH    SEMANTIC/DRIFT
       |                   |               RUNTIME
 Topics                Agents                 |
 Concepts              Loops                 |
 Skills                Routing               |
 Gates                 Coordination          |
 SCW specs             A2A integration       |
 MCP locations         A2A directory         |
 MCP directory         Execution state       |
       |                   |                   |
       +-------------------+-------------------+
                           |
                    SCW INSTANCE RUNTIME
                           |
                    MCP DELIVERY BINDINGS
                           |
                    ENGINEERING / OBSERVABILITY
                           |
                     model / harness
                       remain external
```

The product boundary consists of:

1. Context Graph
2. Execution Graph
3. SCW Runtime
4. Semantic/Drift Runtime
5. A2A Directory
6. MCP Directory
7. MCP Delivery
8. A2A integration
9. Engineering/Observability

## Harness distributions

The repository provides adapters for:

- Claude Agent SDK
- OpenAI Agents SDK
- LangChain/LangGraph
- Google ADK

Each adapter can bind a Maxey1/2/3-style agent to an SCW runtime and can construct A2A requests for an external agent that wants Maxey0 routing.

The provider SDK remains the execution harness. Maxey0 does not absorb the harness into its core.

## Client/plugin distributions

The repository also contains integration bundles for:

- Claude Code
- Codex
- Claude
- ChatGPT

Claude Code uses the native plugin already present in this repository. Codex, Claude, and ChatGPT bundles are MCP/A2A integration surfaces. Platform-side app, connector, or marketplace approval is not falsely represented as source-code completion.

## MCP Directory and MCP Delivery

The Context Graph stores semantic locations for external MCP servers. MCP Delivery stores explicit server-session bindings and routes approved operations to those sessions.

Maxey0 does not become the owner of arbitrary external MCP servers. It owns the semantic directory and delivery boundary used by Maxey0 executions.

## Runtime model

An SCW specification is context-plane state. An SCW instance is created by the SCW runtime and is bound to an agent and runtime identity. The semantic/drift runtime observes state transitions and computes drift against an anchor. A future implementation can replace the in-memory graph with NetworkX, Neo4j, a GNN-backed representation, or another store without changing the semantic contracts.

## maxey0.com

`maxey0.com` is an appropriate distribution channel for the core package, harness adapters, plugin/connector bundles, MCP delivery server, documentation, and future hosted A2A/API services. This repository includes a static site scaffold only; production hosting and platform publication remain deployment operations.


## Canonical Python API

```python
from maxey0_ss import SuperSpaceSystem

system = SuperSpaceSystem()
```

`maxey0_ss` is the Python import namespace because the product name `Maxey0-SuperSpace` contains a hyphen, which is not legal in a Python identifier. `SuperSpaceSystem` is the system class. There are no other spellings: `tests/test_ontology.py` fails if one reappears.
