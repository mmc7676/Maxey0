"""Framework-call records: what a harness did inside a window, as attestations.

Binding an agent to a window attributed the agent, but nothing the harness did
afterwards reached the ledger -- a LangChain chain or an OpenAI Agents run could
call ten models and five tools and `evidence.attestations` showed none of it.
The observers built on this module append one record per model or tool call to
the same hash-chained containment log the rest of the system writes to.

These observers OBSERVE; they do not gate. A record is written after (or as)
the framework acts, `allowed` is always true, and nothing here can refuse a
call. Gating egress is `providers.GatedProvider`'s job.

Content never enters the record. Prompts, outputs and tool arguments are
reduced to a SHA-256 digest and a character length, in keeping with the
redaction policy in `server/gate/privacy.py`: the ledger proves *that* a
payload was seen and lets a holder of the payload confirm *which* one, without
the ledger itself becoming a copy of user data.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from ...containment.attestation import AttestationLog
from ...containment.protocol import ContainmentDecision, Operation

#: `reason` on every observer record. Stable, so a reader can filter observed
#: activity apart from gate decisions.
OBSERVED_REASON = "observed (not gated)"


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return str(value)


def payload_summary(value: Any) -> dict[str, Any]:
    """Digest and length of a payload -- never the payload itself."""
    text = _text(value)
    return {
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "chars": len(text),
    }


def resolve_log(target: Any) -> AttestationLog:
    """Accept a log, or a system whose containment log should be used.

    Adapters reach the log the same way `mcp_surface` does:
    ``system.context.isolation.log``. Anything else fails at construction
    rather than silently recording nowhere.
    """
    if isinstance(target, AttestationLog):
        return target
    isolation = getattr(getattr(target, "context", None), "isolation", None)
    log = getattr(isolation, "log", None)
    if not isinstance(log, AttestationLog):
        raise TypeError("expected an AttestationLog or a SuperSpaceSystem with a containment log")
    return log


class FrameworkRecorder:
    """Writes one observation record per framework event."""

    def __init__(self, target: Any, *, scw_id: str, harness: str) -> None:
        if not scw_id:
            raise ValueError("a framework recorder needs the SCW id it records into")
        self.log = resolve_log(target)
        self.scw_id = scw_id
        self.harness = harness

    def record(self, kind: str, name: str, **payloads: Any) -> None:
        name = name or "unknown"
        metadata: dict[str, Any] = {"kind": kind, "name": name, "harness": self.harness}
        for key, value in payloads.items():
            if value is not None:
                metadata[key] = payload_summary(value)
        self.log.record(
            ContainmentDecision(
                allowed=True,
                # EGRESS is the closest existing operation; `metadata.kind`
                # tells framework observations apart from provider egress.
                operation=Operation.EGRESS,
                agent_scw=self.scw_id,
                target_scw=f"{self.harness}:{name}",
                reason=OBSERVED_REASON,
                provider=f"{self.harness}-observer",
                metadata=metadata,
            )
        )
