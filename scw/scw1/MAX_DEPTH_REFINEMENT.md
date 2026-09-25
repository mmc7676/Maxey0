# Maximum-depth refinement loop

## Q1: What else is missing?
- Protocol/version negotiation and explicit stateless MCP semantics.
- Explicit application handles for SCWs instead of transport sessions.
- MCP cache semantics on list/read surfaces.
- Host-mediated context observation contract.
- Default SCW deployer as a reusable skill.
- Clear separation between public control surfaces and private backend state.
- Conformance tests for MCP headers, statelessness, tool dispatch, and resource reads.
- Marketplace-ready manifests without claiming platform publication.

## Q2: How else can the platform be delivered?
1. Local Claude Code plugin: process-local SCW/MCP runtime.
2. Remote MCP server: stateless HTTP behind any ordinary load balancer.
3. ChatGPT App: remote MCP + MCP App UI; host supplies observable context segments.
4. Codex plugin: MCP + skill bundle.
5. Direct Python library/API: embed SCW and Maxey0 control plane.
6. Harness adapters: Claude Agent SDK, OpenAI Agents SDK, LangChain/LangGraph, Google ADK.
7. A2A service: external agents submit governed tasks to Maxey0.

## Q3: Where do LLM APIs and storage for other MCP servers live?
They remain outside the SCW protocol boundary unless explicitly registered as capabilities. Provider API credentials belong in the host/deployment secret manager. Other MCP servers are registered in the MCP directory and reached through Maxey0 gates. Graph/vector/relational/queue storage are backend dependencies behind context/memory adapters, not protocol-visible secrets.

## Q4: How do developers get maximum functionality without exposing internals?
Expose stable interfaces: MCP tools/resources, A2A agent card/task endpoint, Python API, CLI, and host manifests. Keep provider credentials, database credentials, deployment topology, internal ledgers, and mutable runtime state external. Source code can remain open under Apache-2.0; runtime data and secrets are never embedded.

## Q5: What does ChatGPT context observation actually mean?
Maxey0 cannot inspect hidden ChatGPT model context by itself. The app must receive host-visible context metadata/segments. Maxey0 can then assign regions, show boundaries, calculate overlap/admission, and emit provenance. The implementation therefore exposes a host-window observation contract rather than claiming privileged access.

## Q6: Default deployment semantics
Every governed task starts with an SCW unless explicitly unmanaged. SCW0 owns the task-level constitution. Child SCWs are created for agent/role isolation. Closing a child does not erase its sealed provenance; the parent receives only the admitted projection.

## Q7: MCP 2026-07-28 implications
The protocol layer must not rely on `initialize`, `initialized`, or `Mcp-Session-Id`. Each request is independently routable. `Mcp-Method` and `Mcp-Name` are available to gateways for routing and authorization. List/read responses may carry `ttlMs` and `cacheScope`. Tasks are an extension; MCP Apps are an extension; deprecated Roots/Sampling/Logging are not used for new design. DCR is not the new authorization default; CIMD is the forward direction.
