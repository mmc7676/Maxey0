# Protocol boundary

The public core treats A2A and MCP as protocol boundaries rather than as ownership boundaries.

- A2A: external agent ↔ Maxey0 communication.
- MCP: capability/context source ↔ client.
- Context graph: semantic registration and location of MCP servers/resources.
- SCW instance: runtime-bound context boundary and policy.
- Gate: admission decision between semantic context selection and execution.

The JSON schemas in this directory are deliberately small. Provider-specific protocol envelopes should be implemented in adapters rather than embedded into Maxey0's core ontology.
