# Maxey0-SuperSpace API Refactor

## Canonical identity

- Repository: `Maxey0-SuperSpace`
- Product: `Maxey0-SuperSpace`
- Short forms: `Maxey0-SuperSpace`, `SuperSpaceSystem`, `Maxey0-SuperSpace`
- Python package: `maxey0_ss`
- Canonical system class: `SuperSpaceSystem`
- Product-facing aliases: `SuperSpaceSystem`, `SuperSpaceSystem`
- Compatibility alias: `SuperSpaceSystem`

The hyphen is retained in the repository/product name and removed only where the target syntax cannot accept it, such as Python import identifiers.

## Before

```python
from maxey0_fullstack import SuperSpaceSystem
system = SuperSpaceSystem()
```

## Now

```python
from maxey0_ss import SuperSpaceSystem
system = SuperSpaceSystem()
```

Equivalent canonical form:

```python
from maxey0_ss import SuperSpaceSystem
system = SuperSpaceSystem()
```

## CLI

```text
maxey0-ss
maxey0-ss-api
maxey0-ss-public
```

## Application/API identity

The FastAPI application is titled `Maxey0-SuperSpace`. Its canonical application state is exposed as `app.state.superspace`; `app.state.maxey0` remains a compatibility alias.

The canonical A2A identity is `maxey0-ss` / `Maxey0-SuperSpace`.

The canonical agent-card path is:

```text
/.well-known/maxey0-ss-agent.json
```

The prior `/.well-known/maxey0-agent.json` path remains as a compatibility alias.

## MCP identifiers

Public MCP identifiers now use the `maxey0-ss` namespace, including:

```text
maxey0-ss.health
maxey0-ss.distribution
maxey0-ss.auth.manifest
maxey0-ss.cache.status
maxey0-ss.gate.inspect
maxey0-ss.super_space

ui://maxey0-ss/super-space.html
maxey0-ss://super-space/host-window
maxey0-ss://architecture/planes
```

## Boundary

The `Maxey0` name is still valid where it refers to the broader Maxey0 application, plugin, or historical integration surfaces. The refactor removes the previous `maxey0_fullstack` Python package identity from the canonical implementation API.
