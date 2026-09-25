from __future__ import annotations

from dataclasses import dataclass

from ..identity import validate_scw_reference


@dataclass(frozen=True)
class EnforceableAddress:
    """Maxey0's explicit application-level address for governed execution."""

    topic: str
    concept: str
    skill: str
    region: str
    scw_id: str

    def uri(self) -> str:
        return f"scw://{self.topic}/{self.concept}/{self.skill}/{self.region}/{self.scw_id}"

    @classmethod
    def parse(cls, value: str) -> "EnforceableAddress":
        if not value.startswith("scw://"):
            raise ValueError("SCW address must start with scw://")
        parts = value[6:].split("/")
        if len(parts) != 5 or any(not p for p in parts):
            raise ValueError("SCW address must contain topic/concept/skill/region/scw_id")
        # The final segment is an SCW identifier, not free text.
        validate_scw_reference(parts[4])
        return cls(*parts)
