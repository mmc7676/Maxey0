"""What a cache entry is *about*, expressed precisely enough to be safe.

The whole risk in caching this system is answering a question with a value
computed for a different question. Two failure modes matter:

1. **Cross-model reuse.** The same prompt against a different model, model
   version, or decoding configuration is a different function. Keying on model
   name alone silently serves one model's output as another's.

2. **Cross-plane contamination.** Maxey0 partitions work into semantic planes
   and an explicit SCW address space. A value computed inside one SCW must never
   satisfy a read from another; that isolation is the product.

Both are handled the same way: everything that makes the answer different goes
*into the key*, and the key's namespace is chosen before the lookup happens.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SemanticPlane(str, Enum):
    """The planes Maxey0 partitions work into, plus the protocol layer.

    `PROTOCOL` is the MCP catalog surface: server-wide, identical for every
    caller, and the only plane whose entries are safe to share across SCWs.
    """

    PROTOCOL = "protocol"
    CONTEXT = "context"
    EXECUTION = "execution"
    OBSERVATION = "engineering-observation"
    MODEL = "model"


#: Scope used when an entry genuinely belongs to the whole server.
SERVER_SCOPE = "server"


def _canonical(value: Any) -> str:
    """Stable text for hashing. Key order must not change the digest."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def digest(*parts: Any) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(_canonical(part).encode("utf-8"))
        h.update(b"\x1f")  # unit separator: "ab"+"c" must not equal "a"+"bc"
    return h.hexdigest()


@dataclass(frozen=True)
class ModelIdentity:
    """Everything that makes one model's answer different from another's.

    `version` and `params` are not optional decoration. The same `model_id` at a
    different temperature, or after a provider-side version bump, is a different
    function and must not share cache entries.
    """

    model_id: str
    version: str
    params: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.model_id:
            raise ValueError("model_id is required for a per-model cache key")
        if not self.version:
            raise ValueError(
                "model version is required; without it a provider-side version "
                "bump silently reuses the previous model's answers"
            )

    def fingerprint(self) -> str:
        return digest(self.model_id, self.version, self.params)


@dataclass(frozen=True)
class Namespace:
    """A cache partition. Chosen before lookup, so isolation is structural.

    `scope` carries the SCW identifier for SCW-bound planes, which is what makes
    `invalidate_scw` able to drop exactly one SCW's entries.
    """

    plane: SemanticPlane
    scope: str = SERVER_SCOPE

    def __post_init__(self) -> None:
        if not self.scope:
            raise ValueError("namespace scope is required")
        if self.plane is SemanticPlane.PROTOCOL and self.scope != SERVER_SCOPE:
            raise ValueError("the protocol plane is server-scoped by definition")

    def prefix(self) -> str:
        return f"{self.plane.value}/{self.scope}/"

    def key(self, *identity: Any) -> str:
        return self.prefix() + digest(*identity)

    def model_key(
        self,
        model: ModelIdentity,
        prompt: str,
        *,
        tool_schema: Any = None,
        extra: Any = None,
    ) -> str:
        """Key a model response.

        The tool schema is part of the identity: the same prompt offered a
        different set of tools is a different request, and the model's answer
        is not interchangeable between the two.
        """
        return self.key(
            "model-response",
            model.fingerprint(),
            digest(prompt),
            digest(tool_schema),
            extra,
        )
