from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

@dataclass
class HostContextSegment:
    segment_id: str
    start: int
    end: int
    label: str
    role: str = "host-visible"
    source: str = "host"
    writable: bool = False
    metadata: dict[str, Any] | None = None

class HostWindowObserver:
    """Observes only context metadata explicitly supplied by the host.

    It never claims access to hidden model/runtime context. A ChatGPT App can
    call this with host-visible segments or an application-managed transcript.
    """
    #: Segments accepted per call. The list was unbounded.
    MAX_SEGMENTS = 1000

    def observe(self, segments: list[dict[str, Any]]) -> dict[str, Any]:
        # Every malformed shape below used to escape as AttributeError,
        # ValueError or OverflowError and reach the caller as a 500. They are
        # input errors, so they are raised as ValueError naming the segment.
        if not isinstance(segments, list):
            raise ValueError("segments must be a list")
        if len(segments) > self.MAX_SEGMENTS:
            raise ValueError(f"at most {self.MAX_SEGMENTS} segments per call")
        normalized = []
        for i, raw in enumerate(segments):
            if not isinstance(raw, dict):
                raise ValueError(f"invalid segment {i}: must be an object")
            metadata = raw.get("metadata", {})
            if metadata is None:
                metadata = {}
            if not isinstance(metadata, dict):
                raise ValueError(f"invalid segment {i}: metadata must be an object")
            try:
                start, end = int(raw.get("start", 0)), int(raw.get("end", 0))
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError(f"invalid segment {i}: start/end must be integers") from exc
            normalized.append(asdict(HostContextSegment(
                segment_id=str(raw.get("segment_id", f"seg-{i+1}")),
                start=start, end=end,
                label=str(raw.get("label", "unlabeled")), role=str(raw.get("role", "host-visible")),
                source=str(raw.get("source", "host")), writable=bool(raw.get("writable", False)),
                metadata=dict(metadata),
            )))
        return {"observable": True, "scope": "host-supplied", "segments": normalized, "partition_count": len(normalized)}
