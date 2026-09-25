# Protocol — skills

The 4 skill(s) this concept owns, from the Maxey0 manifest. Each names the agent formation already bound to it: a `primary` that produces, a `checker` that verifies, and `support` roles around them.

That formation is why routing beats improvising. A pre-scoped formation for the matched skill is almost always cheaper and better targeted than a hand-written maker/checker pair.

## `agent-to-agent-protocol-engineering`

**Agent-to-Agent Protocol Engineering**

Defines, validates, versions, and adapts schema-checked A2A envelopes so any conformant agent can exchange work with the network.

memory tier: `episodic` · tags: `a2a`, `envelope`, `schema`, `handoff`, `version`

| agent | role |
|---|---|
| MCP Bridge | `primary` |
| SuperAgent Orchestrator | `checker` |
| LangChain Adapter Agent | `support` |
| Retrieval Orchestrator | `support` |

## `model-context-protocol-engineering`

**Model Context Protocol Engineering**

Builds and operates MCP servers: tool registration, capability advertisement, auth, and the lazy-load manifest pattern.

memory tier: `episodic` · tags: `mcp`, `server`, `tool`, `capability`, `manifest`

| agent | role |
|---|---|
| MCP Bridge | `primary` |
| QA Agent | `checker` |
| Memory API Keeper | `support` |
| Runner API Keeper | `support` |

## `multi-mcp-federation`

**Multi-MCP Federation**

Federates multiple MCP servers behind a unified discovery surface; routes tool calls to the right server without exposing federation internals to callers.

memory tier: `episodic` · tags: `federation`, `mcp`, `discovery`, `routing`, `multi-server`

| agent | role |
|---|---|
| MCP Bridge | `primary` |
| SuperAgent Orchestrator | `checker` |
| Runner API Keeper | `support` |
| Retrieval Orchestrator | `support` |

## `protocol-translation`

**Protocol Translation**

Translates between A2A, MCP, and foreign agent frameworks' message shapes without loss of contract fields.

memory tier: `episodic` · tags: `translation`, `adapter`, `foreign`, `bridge`, `interop`

| agent | role |
|---|---|
| LangChain Adapter Agent | `primary` |
| MCP Bridge | `checker` |
| Runner API Keeper | `support` |
| Memory API Keeper | `support` |
