# Maxey0 + MCP 2026-07-28 architecture

## Boundary

MCP is the stateless capability/resource transport. Maxey0 owns the application-level enforceable address space, SCW state, admission, routing, observability, and execution coordination.

```text
Host / Agent
    |
    v
MCP 2026-07-28
    |  Mcp-Method / Mcp-Name / _meta / trace context
    v
Maxey0 Gateway
    |
    +--> SCW address resolution
    +--> role/capability authorization
    +--> structural gate
    +--> optional semantic gate provider
    +--> cache policy
    +--> execution routing
    |
    v
SCW -> Agent/Loop/Harness -> MCP capability
```

## Statelessness

No protocol session is required. SCW/application state is carried by explicit handles/address values. This permits ordinary round-robin infrastructure and removes the need for protocol-level sticky sessions.

## Header routing

`Mcp-Method` and `Mcp-Name` are treated as early routing signals. Maxey0 can reject header/body disagreement before invoking a tool.

## Caching

Catalog and resource metadata are cache-aware. The public in-process cache is deliberately replaceable by Redis/CDN/host caches. Cache freshness never grants authorization.

## Semantic gating

The public repo exposes the interface and structural gate but does not embed a proprietary semantic model or credential. A private/paid semantic provider implements the same `SemanticGateProvider` interface.

## MCP Apps

The SuperSpace is delivered as an MCP App UI resource using `ui://` and `_meta.ui.resourceUri`. The UI is an application of the SuperSpace concept; the SuperSpace itself remains the broader Maxey0 runtime/context model.
