"""Maxey0 caching.

`policy` holds the original MCP metadata cache, which the 2026-07-28 HTTP
adapter uses for catalog responses. The remaining modules are the namespaced
cache: partitioned by semantic plane and SCW, keyed by full model identity, and
invalidatable per SCW.

See `docs/CACHING.md`.
"""
from .config import CacheConfig, DEFAULT_TTL_MS
from .identity import ModelIdentity, Namespace, SemanticPlane, SERVER_SCOPE, digest
from .policy import CacheEntry, CacheHint, MCPMetadataCache
from .store import (
    CacheView,
    Entry,
    MaxeyCache,
    Metrics,
    NEVER_CACHE,
    NotCacheable,
    assert_cacheable,
)

__all__ = [
    "CacheConfig",
    "CacheEntry",
    "CacheHint",
    "CacheView",
    "DEFAULT_TTL_MS",
    "Entry",
    "MCPMetadataCache",
    "MaxeyCache",
    "Metrics",
    "ModelIdentity",
    "NEVER_CACHE",
    "Namespace",
    "NotCacheable",
    "SERVER_SCOPE",
    "SemanticPlane",
    "assert_cacheable",
    "digest",
]
