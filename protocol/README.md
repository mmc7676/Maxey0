# Protocol surface

Maxey0 targets MCP `2026-07-28` for the transport boundary. The adapter is stateless at the protocol layer: no `initialize` handshake and no `Mcp-Session-Id` dependency. Requests carry `MCP-Protocol-Version`; Streamable HTTP uses `Mcp-Method` and `Mcp-Name` for routing/authorization. List responses expose cache hints. Application state remains in explicit SCW handles and Maxey0 state stores.

MCP Tasks and MCP Apps are modeled as extensions, not as private Maxey0 protocol features.
