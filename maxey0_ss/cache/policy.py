from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CacheHint:
    ttl_ms: int
    scope: str

    def as_dict(self) -> dict[str, Any]:
        return {"ttlMs": self.ttl_ms, "cacheScope": self.scope}


@dataclass
class CacheEntry:
    key: str
    value: Any
    created_ms: int
    hint: CacheHint

    def fresh(self, now_ms: int | None = None) -> bool:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        return now - self.created_ms < self.hint.ttl_ms


class MCPMetadataCache:
    """Small deterministic cache for MCP catalog/resource metadata.

    This is intentionally optional. Production deployments can replace it with
    Redis, a CDN, or another shared cache without changing the MCP contract.
    """

    def __init__(self) -> None:
        self.entries: dict[str, CacheEntry] = {}

    def put(self, key: str, value: Any, hint: CacheHint) -> None:
        self.entries[key] = CacheEntry(key, value, int(time.time() * 1000), hint)

    def get(self, key: str) -> Any | None:
        entry = self.entries.get(key)
        if entry is None or not entry.fresh():
            if entry is not None:
                self.entries.pop(key, None)
            return None
        return entry.value

    def invalidate(self, prefix: str | None = None) -> None:
        if prefix is None:
            self.entries.clear()
        else:
            for key in list(self.entries):
                if key.startswith(prefix):
                    self.entries.pop(key, None)
