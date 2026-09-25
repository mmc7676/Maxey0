"""Cache configuration. Explicit and inspectable, never hidden constants."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from .identity import SemanticPlane

#: Per-plane defaults, in milliseconds.
#:
#: Protocol metadata is server-wide and changes only on redeploy, so it tolerates
#: a long TTL. The SCW-bound planes are deliberately shorter: they describe live
#: application state, and a stale answer there is worse than a slow one.
DEFAULT_TTL_MS: dict[SemanticPlane, int] = {
    SemanticPlane.PROTOCOL: 300_000,
    SemanticPlane.CONTEXT: 30_000,
    SemanticPlane.EXECUTION: 15_000,
    SemanticPlane.OBSERVATION: 15_000,
    SemanticPlane.MODEL: 3_600_000,
}

#: Environment variable that disables every cache read and write at once.
BYPASS_ENV = "MAXEY0_CACHE_BYPASS"
ENABLED_ENV = "MAXEY0_CACHE_ENABLED"
MAX_ENTRIES_ENV = "MAXEY0_CACHE_MAX_ENTRIES"


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class CacheConfig:
    """How the cache behaves. Constructed from defaults or the environment.

    `bypass` is a first-class control, not a debugging hack: verification runs
    must be able to prove a result was computed rather than replayed.
    """

    enabled: bool = True
    bypass: bool = False
    max_entries: int = 10_000
    ttl_ms: dict[SemanticPlane, int] = field(default_factory=lambda: dict(DEFAULT_TTL_MS))

    @classmethod
    def from_env(cls) -> "CacheConfig":
        cfg = cls(
            enabled=_flag(ENABLED_ENV, True),
            bypass=_flag(BYPASS_ENV, False),
        )
        raw = os.environ.get(MAX_ENTRIES_ENV)
        if raw:
            try:
                cfg.max_entries = max(1, int(raw))
            except ValueError:
                pass  # keep the default rather than fail startup on a typo
        for plane in SemanticPlane:
            env = f"MAXEY0_CACHE_TTL_MS_{plane.name}"
            value = os.environ.get(env)
            if value:
                try:
                    cfg.ttl_ms[plane] = max(0, int(value))
                except ValueError:
                    pass
        return cfg

    @property
    def active(self) -> bool:
        return self.enabled and not self.bypass

    def ttl_for(self, plane: SemanticPlane) -> int:
        return self.ttl_ms.get(plane, DEFAULT_TTL_MS[plane])

    def as_dict(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "bypass": self.bypass,
            "active": self.active,
            "max_entries": self.max_entries,
            "ttl_ms": {p.value: self.ttl_for(p) for p in SemanticPlane},
        }
