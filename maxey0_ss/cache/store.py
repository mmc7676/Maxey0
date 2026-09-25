"""The Maxey0 cache store: namespaced, measured, and invalidatable by SCW.

Isolation is structural. A caller does not get the store, it gets a
:class:`CacheView` bound to one :class:`Namespace`, and a view can only address
keys under its own prefix. There is no filter to forget and no lookup path that
could reach another plane's entries.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .config import CacheConfig
from .identity import Namespace, SemanticPlane

#: Tool results that must never be cached, with the reason.
#:
#: These are not performance judgements. Each one would be a correctness bug:
#: the first three mutate or read live SCW state, and the fourth is a pure
#: function of host-supplied context that belongs to a single request.
NEVER_CACHE: dict[str, str] = {
    "maxey0-ss.scw.create": "mutates the SCW graph",
    "maxey0-ss.scw.close": "mutates the SCW graph",
    "maxey0-ss.scw.describe": "reads live SCW state that a sibling call may have changed",
    "maxey0-ss.scw.observe_host_window": "reads host-supplied context belonging to one request",
    "maxey0-ss.auth.manifest": "derives from environment; caching outlives a credential change",
    "maxey0-ss.deployment": (
        "reports live credential configuration. It gained a `models` block in "
        "0.3.0 naming which providers hold a real key, a placeholder, or "
        "nothing, and a cached answer there outlives the credential change it "
        "describes -- the same reason auth.manifest is on this list"
    ),
    "maxey0-ss.provider.status": (
        "same: which providers are callable is a fact about the environment "
        "right now"
    ),
    "maxey0-ss.provider.complete": (
        "sends a prompt to a third party. A replayed completion would report an "
        "egress that did not happen, and the attestation chain would disagree "
        "with the answer the caller was given"
    ),
    "maxey0-ss.gate.inspect": (
        "is a gate decision, not a fact. DisabledSemanticGate is pure, but a "
        "SemanticGateProvider may consult an external policy service, and a "
        "replayed allow outlives the policy that produced it"
    ),
    "maxey0-ss.scw.drift": (
        "anchors baselines and measures against live ones; both the read and "
        "the write belong to the moment they were made"
    ),
}


class NotCacheable(ValueError):
    """Raised when something on the never-cache list is offered to the cache."""


def assert_cacheable(name: str) -> None:
    reason = NEVER_CACHE.get(name)
    if reason is not None:
        raise NotCacheable(f"{name} must never be cached: {reason}")


@dataclass
class Entry:
    key: str
    value: Any
    created_ms: int
    ttl_ms: int

    def fresh(self, now_ms: int) -> bool:
        return self.ttl_ms > 0 and (now_ms - self.created_ms) < self.ttl_ms


@dataclass
class Metrics:
    """Cache observability. A cache with no metrics cannot be shown correct."""

    hits: int = 0
    misses: int = 0
    writes: int = 0
    evictions: int = 0
    expirations: int = 0
    bypasses: int = 0
    invalidations: int = 0
    by_plane: dict[str, dict[str, int]] = field(default_factory=dict)

    def _plane(self, plane: SemanticPlane) -> dict[str, int]:
        return self.by_plane.setdefault(plane.value, {"hits": 0, "misses": 0, "writes": 0})

    def record(self, plane: SemanticPlane, event: str) -> None:
        setattr(self, event, getattr(self, event) + 1)
        bucket = self._plane(plane)
        if event in bucket:
            bucket[event] += 1

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "writes": self.writes,
            "evictions": self.evictions,
            "expirations": self.expirations,
            "bypasses": self.bypasses,
            "invalidations": self.invalidations,
            "hit_rate": round(self.hit_rate, 4),
            "by_plane": self.by_plane,
        }


def _now_ms() -> int:
    return int(time.time() * 1000)


class MaxeyCache:
    """Namespaced TTL cache with SCW-aware invalidation."""

    def __init__(self, config: CacheConfig | None = None, *, clock: Callable[[], int] = _now_ms) -> None:
        self.config = config or CacheConfig()
        self.metrics = Metrics()
        self._clock = clock
        self._entries: dict[str, Entry] = {}

    # -- access -------------------------------------------------------------

    def view(self, namespace: Namespace) -> "CacheView":
        return CacheView(self, namespace)

    def get(self, namespace: Namespace, key: str) -> Any | None:
        if not self.config.active:
            self.metrics.record(namespace.plane, "bypasses")
            return None
        entry = self._entries.get(key)
        if entry is None:
            self.metrics.record(namespace.plane, "misses")
            return None
        if not entry.fresh(self._clock()):
            del self._entries[key]
            self.metrics.record(namespace.plane, "expirations")
            self.metrics.record(namespace.plane, "misses")
            return None
        self.metrics.record(namespace.plane, "hits")
        return entry.value

    def put(self, namespace: Namespace, key: str, value: Any, *, ttl_ms: int | None = None) -> None:
        if not self.config.active:
            self.metrics.record(namespace.plane, "bypasses")
            return
        ttl = self.config.ttl_for(namespace.plane) if ttl_ms is None else ttl_ms
        if ttl <= 0:
            return  # a zero TTL means "do not cache", not "cache forever"
        self._evict_if_full()
        self._entries[key] = Entry(key, value, self._clock(), ttl)
        self.metrics.record(namespace.plane, "writes")

    def _evict_if_full(self) -> None:
        while len(self._entries) >= self.config.max_entries:
            oldest = min(self._entries.values(), key=lambda e: e.created_ms)
            del self._entries[oldest.key]
            self.metrics.evictions += 1

    # -- invalidation -------------------------------------------------------

    def invalidate_prefix(self, prefix: str) -> int:
        dropped = [k for k in self._entries if k.startswith(prefix)]
        for key in dropped:
            del self._entries[key]
        if dropped:
            self.metrics.invalidations += len(dropped)
        return len(dropped)

    def invalidate_namespace(self, namespace: Namespace) -> int:
        return self.invalidate_prefix(namespace.prefix())

    def invalidate_plane(self, plane: SemanticPlane) -> int:
        return self.invalidate_prefix(f"{plane.value}/")

    def invalidate_scw(self, scw_id: str) -> int:
        """Drop every entry bound to one SCW, across every plane.

        Closing an SCW and reopening the identifier must not inherit the old
        one's cached answers, so this is dependency-aware rather than per-plane.
        """
        dropped = 0
        for plane in SemanticPlane:
            if plane is SemanticPlane.PROTOCOL:
                continue  # server-scoped; never bound to an SCW
            dropped += self.invalidate_prefix(f"{plane.value}/{scw_id}/")
        return dropped

    def clear(self) -> None:
        self._entries.clear()

    # -- reporting ----------------------------------------------------------

    def __len__(self) -> int:
        return len(self._entries)

    def status(self) -> dict[str, Any]:
        """Describe the cache without exposing its contents.

        Keys are digests of prompts and application state, so neither keys nor
        values belong in an inspectable status surface.
        """
        planes: dict[str, int] = {}
        for key in self._entries:
            plane = key.split("/", 1)[0]
            planes[plane] = planes.get(plane, 0) + 1
        return {
            "entries": len(self._entries),
            "entries_by_plane": planes,
            "config": self.config.as_dict(),
            "metrics": self.metrics.as_dict(),
            "never_cached": sorted(NEVER_CACHE),
        }


class CacheView:
    """A handle bound to one namespace. Cannot address another plane's keys."""

    __slots__ = ("_cache", "_ns")

    def __init__(self, cache: MaxeyCache, namespace: Namespace) -> None:
        self._cache = cache
        self._ns = namespace

    @property
    def namespace(self) -> Namespace:
        return self._ns

    def get(self, *identity: Any) -> Any | None:
        return self._cache.get(self._ns, self._ns.key(*identity))

    def put(self, *identity: Any, value: Any, ttl_ms: int | None = None) -> None:
        self._cache.put(self._ns, self._ns.key(*identity), value, ttl_ms=ttl_ms)

    def get_model(self, model, prompt: str, *, tool_schema: Any = None, extra: Any = None) -> Any | None:
        return self._cache.get(
            self._ns, self._ns.model_key(model, prompt, tool_schema=tool_schema, extra=extra)
        )

    def put_model(
        self, model, prompt: str, value: Any, *, tool_schema: Any = None, extra: Any = None,
        ttl_ms: int | None = None,
    ) -> None:
        self._cache.put(
            self._ns,
            self._ns.model_key(model, prompt, tool_schema=tool_schema, extra=extra),
            value,
            ttl_ms=ttl_ms,
        )

    def invalidate(self) -> int:
        return self._cache.invalidate_namespace(self._ns)
