# I/O Contract — skills

The 5 skill(s) this concept owns, from the Maxey0 manifest. Each names the agent formation already bound to it: a `primary` that produces, a `checker` that verifies, and `support` roles around them.

That formation is why routing beats improvising. A pre-scoped formation for the matched skill is almost always cheaper and better targeted than a hand-written maker/checker pair.

## `tool-schema-negotiation`

**Tool Schema Negotiation**

Publishes owned, versioned service contracts; discovers and negotiates capabilities before first call; tests contracts in both directions.

memory tier: `episodic` · tags: `schema`, `contract`, `endpoint`, `negotiate`, `tolerant-reader`

| agent | role |
|---|---|
| Memory API Keeper | `primary` |
| QA Agent | `checker` |
| Runner API Keeper | `support` |
| MCP Bridge | `support` |

## `tool-capability-discovery`

**Tool Capability Discovery**

Discovers what tools and capabilities are available in the current environment: MCP servers, APIs, and local capabilities.

memory tier: `episodic` · tags: `discovery`, `capability`, `tool`, `mcp`, `environment`

| agent | role |
|---|---|
| Memory API Keeper | `primary` |
| QA Agent | `checker` |
| MCP Bridge | `support` |
| Runner API Keeper | `support` |

## `context-infrastructure-engineering`

**Context Infrastructure Engineering**

Engineers the infrastructure that serves context to agents: retrieval endpoints, caching layers, and contract-validated context APIs.

memory tier: `episodic` · tags: `context`, `infrastructure`, `retrieval`, `cache`, `api`

| agent | role |
|---|---|
| Context Window Architect | `primary` |
| QA Agent | `checker` |
| Retrieval Orchestrator | `support` |
| Memory API Keeper | `support` |

## `inference-pipeline-engineering`

**Inference Pipeline Engineering**

Engineers the pipeline from request to model inference: batching, routing, caching, and contract-validated responses.

memory tier: `episodic` · tags: `inference`, `pipeline`, `batch`, `routing`, `cache`

| agent | role |
|---|---|
| Memory API Keeper | `primary` |
| QA Agent | `checker` |
| API Gateway Agent | `support` |
| Code Interpreter Agent | `support` |

## `ai-platform-engineering`

**AI Platform Engineering**

Engineers the end-to-end AI platform: model serving, tool integration, agent orchestration endpoints, and platform-level observability.

memory tier: `episodic` · tags: `platform`, `serving`, `integration`, `orchestration`, `endpoint`

| agent | role |
|---|---|
| Code Interpreter Agent | `primary` |
| QA Agent | `checker` |
| Memory API Keeper | `support` |
| API Gateway Agent | `support` |
