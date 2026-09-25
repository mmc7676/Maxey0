# Caching architecture

Caching here is a correctness problem before it is a performance one. A cache
that returns the right value faster is an optimization; a cache that returns
another model's or another SCW's value is a defect that looks like a feature.

Everything below is implemented and tested unless a section says otherwise.

## Two caches, different jobs

| | `MCPMetadataCache` (`cache/policy.py`) | `MaxeyCache` (`cache/store.py`) |
|---|---|---|
| Caches | MCP catalog responses | application and model state |
| Keys | flat strings (`tools:list`) | namespaced digests |
| Partitioned by | nothing — server-wide | semantic plane + SCW |
| Used by | `mcp_2026.build_router` | `mcp_surface`, callers |

The metadata cache was already correct for its job: catalog responses are
server-wide and identical for every caller. It is unchanged.

## Isolation is structural, not filtered

A caller never receives the store. It receives a `CacheView` bound to one
`Namespace`, and a view can only address keys under its own prefix:

```python
view = cache.view(Namespace(SemanticPlane.CONTEXT, "SCW0"))
view.put("window", value=...)      # context/SCW0/<digest>
```

There is no lookup path that reaches another plane's entries, so there is no
filter to forget. `Namespace` also refuses incoherent partitions — the protocol
plane is server-scoped by definition and raises if given an SCW scope.

## Per-model identity

The key carries everything that makes the answer different:

```
sha256(model_id ‖ version ‖ decoding_params ‖ prompt ‖ tool_schema ‖ extra)
```

`ModelIdentity` **refuses to construct without a version**, because a
provider-side version bump would otherwise silently reuse the previous model's
answers. Decoding parameters are in the key for the same reason: the same model
at a different temperature is a different function. So is the tool schema — the
same prompt offered a different toolset is a different request.

Digest construction inserts a unit separator between parts, so `("ab","c")` and
`("a","bc")` cannot collide. Key order in dicts does not affect the digest.

## Semantic planes

`protocol`, `context`, `execution`, `engineering-observation`, `model`.

Only `protocol` is server-scoped and shareable across SCWs. The rest are bound
to an SCW, which is what makes per-SCW invalidation possible.

## Invalidation

| Call | Drops |
|---|---|
| `invalidate_namespace(ns)` | one plane+scope |
| `invalidate_plane(plane)` | one plane, every scope |
| `invalidate_scw(scw_id)` | that SCW, **across every plane**; leaves `protocol` alone |

`invalidate_scw` is dependency-aware on purpose: closing an SCW and reopening
the identifier must not inherit the old one's answers. `maxey0-ss.scw.close`
calls it and reports `cache_entries_dropped`.

## What must never be cached

Enforced by name in `NEVER_CACHE`, which raises `NotCacheable`:

| Tool | Why |
|---|---|
| `maxey0-ss.scw.create` | mutates the SCW graph |
| `maxey0-ss.scw.close` | mutates the SCW graph |
| `maxey0-ss.scw.describe` | reads live state a sibling call may have changed |
| `maxey0-ss.scw.observe_host_window` | host-supplied context belonging to one request |
| `maxey0-ss.auth.manifest` | derives from environment; caching outlives a credential change |

## Configuration

Explicit and inspectable — no hidden constants. `CacheConfig.from_env()`:

| Variable | Effect |
|---|---|
| `MAXEY0_CACHE_ENABLED` | master switch |
| `MAXEY0_CACHE_BYPASS` | disable reads and writes, count bypasses |
| `MAXEY0_CACHE_MAX_ENTRIES` | eviction bound (default 10 000) |
| `MAXEY0_CACHE_TTL_MS_<PLANE>` | per-plane TTL |

Defaults: protocol 300 s, context 30 s, execution 15 s, observation 15 s,
model 1 h. The SCW-bound planes are short deliberately — they describe live
application state, and a stale answer there is worse than a slow one.

**Bypass is a first-class control, not a debug hack.** Verification runs must be
able to prove a result was computed rather than replayed. A TTL of `0` means
"do not cache", never "cache forever".

## Observability

`Metrics` tracks hits, misses, writes, evictions, expirations, bypasses and
invalidations, globally and per plane, plus `hit_rate`. Surfaced through
`maxey0-ss.cache.status` under `application_cache`.

`status()` reports counts and configuration but **never keys or values** — keys
are digests of prompts and application state. `test_status_reports_shape_without_leaking_contents`
asserts a stored prompt and answer do not appear in the status output.

## Tests

`maxey0_ss/tests/test_cache_isolation.py` — 23 tests, 9 subtests. Crossover
coverage: model id, model version, decoding params, tool schema, plane pairs,
SCW pairs, reused SCW identifiers, never-cache enforcement, TTL expiry, zero
TTL, bypass accounting, eviction bound, digest separation, metrics, and status
non-leakage.

## Not implemented

- **No shared backend.** The cache is per process and in memory. Multiple origin
  instances do not share it. Redis or a CDN tier would need a serialization
  contract the namespace scheme supports but does not yet define.
- **No cache warming or negative caching.**
- **Edge caching** is limited to the `ttlMs` / `cacheScope` hints the Worker
  returns on catalog responses. The Worker does not use the Cache API.
