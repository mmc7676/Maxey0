# Semantic gating after MCP 2026-07-28

The public release separates **structural gating** from an optional **semantic provider**.

Structural gating is always available:

1. Validate MCP protocol/method/name headers.
2. Resolve the explicit SCW address.
3. Validate SCW state and capability ownership.
4. Apply role/capability authorization.
5. Invoke the optional semantic gate provider.
6. Execute only after admission.

The default public provider is intentionally disabled. It passes after structural validation and exposes the integration point for a private/paid semantic gate.

This preserves the full-stack boundary without requiring a proprietary model, embedding service, or credential in the public repository.
