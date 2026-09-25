# Maxey0 Full-Stack Architecture

## Boundary

Maxey0 is the system layer between an external model/agent harness and the structured context/execution environment. It does not claim ownership of the LLM or the harness runtime.

```text
External harness/model
        |
       A2A
        v
+---------------------------+
|           MAXEY0          |
|                           |
| Context Graph             |
| Execution Graph           |
| SCW Runtime               |
| Semantic/Drift Runtime    |
| A2A Directory             |
| MCP Directory             |
| MCP Delivery              |
| A2A Integration           |
| Engineering/Observability |
+---------------------------+
        |
       MCP
        v
External MCP servers/resources
```

## Hierarchical context

```text
Topic
  |
  +-- Concept
       |
       +-- Skill
            |
            +-- Gate
                 |
                 +-- MCP Server / Resource
```

The graph is semantic state. A database is an implementation choice, not a requirement.

## Execution

```text
SCW0 / Maxey0
      |
      +-- Maxey1 / Maker -- SCW1
      +-- Maxey2 / Checker - SCW2
      +-- Maxey3 / Judge -- SCW3
```

SCWs are instantiated because they carry runtime identity, ownership, boundary state, and lifecycle. They are not merely context-server records.

## MCP delivery

The MCP Directory says where a capability exists semantically. MCP Delivery says which explicitly bound session can deliver it. This preserves the distinction between a resource's semantic location and its runtime connection.

## A2A

The A2A Directory records peers and capabilities. The A2A Client sends a task/context request. Maxey0 receives it through the A2A Host, resolves semantic candidates, applies a gate decision, and returns routing/admission information.

## Harness adapters

Four first-class distribution adapters are included:

- Claude Agent SDK
- OpenAI Agents SDK
- LangChain/LangGraph
- Google ADK

They are optional dependencies and loaded lazily. This prevents Maxey0 from becoming coupled to a single execution framework.

## Distribution surfaces

- Claude Code: native plugin
- Codex: MCP + skill bundle
- Claude: MCP connector bundle
- ChatGPT: MCP/App connector bundle
- maxey0.com: canonical distribution/documentation site scaffold

Platform-side publication is explicitly separate from repository implementation.
