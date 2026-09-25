# Before / After: Maxey0 ingestion into SCW0

## BEFORE — repository baseline
The ingested baseline already contained Context Graph, Execution Graph, SCW runtime, semantic/drift runtime, A2A directory/server, MCP directory/delivery, observability, harness adapters, Claude/Codex/ChatGPT distribution bundles, and Claude Code plugin surfaces.

The earlier distribution model still mixed three concerns in places: protocol transport, application state, and host-specific packaging. MCP server implementations also depended on the prior FastMCP abstraction rather than explicitly targeting the final MCP `2026-07-28` wire contract.

## AFTER — SCW0 synthesis
1. **SuperSpace / SCW** is the bounded execution/context substrate with WHERE, WHEN, HOW, and OBSERVABILITY.
2. **Context Plane** owns semantic addressing, context graph, SCW definitions, admission, MCP directory, and context observation.
3. **Execution Plane** owns agents, loops, routing, coordination, and harness adapters.
4. **Engineering/Observation Plane** owns telemetry, provenance, replay, drift, topology, and inspection.
5. **MCP** is the capability boundary and is upgraded to the `2026-07-28` stateless HTTP contract.
6. **A2A** remains the agent/task interoperability boundary.
7. **SCW** remains stateful at the application/runtime layer, but its state is represented by explicit handles rather than MCP transport sessions.
8. A default SCW deployer creates the initial execution capsule before governed loops.
9. ChatGPT context-window observation is host-mediated: Maxey0 can partition and observe only context segments explicitly exposed to the app, not hidden model internals.
10. The public repository is harness-neutral; host-specific packages are distributions over the same core.
11. Internal implementation detail is hidden behind stable protocol/API surfaces; source remains open-source in the public repository while runtime state, credentials, and provider secrets stay outside it.
