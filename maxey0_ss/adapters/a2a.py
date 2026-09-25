from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.request import Request, urlopen

from ..models import LoopSpec
from ..auth.policy import is_placeholder_secret, is_public_deployment
if TYPE_CHECKING:
    from ..system import SuperSpaceSystem


@dataclass
class A2ARequest:
    sender: str
    task: str
    topic: str | None = None
    concept: str | None = None
    skill: str | None = None
    requested_loop: str | None = None
    context: dict[str, Any] | None = None


def a2a_credential_valid(presented: str | None, expected: str) -> bool:
    """Constant-time check of the A2A shared secret.

    An empty `expected` means the deployment supplied no secret. On a local
    deployment that is permissive by design. On one that declares itself public
    it is an unauthenticated write endpoint reachable by anyone who can resolve
    the hostname, so the empty case refuses there — the same fail-closed rule
    the MCP tiers apply, rather than an exception carved out for the one
    authenticated REST route.
    """
    if not expected:
        return not is_public_deployment()
    if is_placeholder_secret(expected):
        # Left as shipped in .env.example: never a secret anyone may present.
        return False
    if not presented:
        return False
    token = presented.split(None, 1)[1] if presented.lower().startswith("bearer ") else presented
    return hmac.compare_digest(token.strip(), expected)


class A2AClient:
    """Small transport-neutral A2A HTTP client for external harness adapters."""

    def __init__(self, endpoint: str, timeout: float = 30.0, shared_secret: str = "") -> None:
        self.endpoint = endpoint
        self.timeout = timeout
        self.shared_secret = shared_secret

    def send(self, request: A2ARequest) -> dict[str, Any]:
        payload = json.dumps(request.__dict__).encode("utf-8")
        headers = {"content-type": "application/json"}
        if self.shared_secret:
            headers["authorization"] = f"Bearer {self.shared_secret}"
        req = Request(self.endpoint, data=payload, headers=headers, method="POST")
        with urlopen(req, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))


class A2AHost:
    """Harness-neutral A2A host: external agents ask Maxey0 what loop/context to run."""

    def __init__(self, system: SuperSpaceSystem) -> None:
        self.system = system

    def handle(self, request: A2ARequest) -> dict[str, Any]:
        candidates = self.system.context.graph.semantic_candidates(request.topic, request.concept, request.skill)
        # The admission bar is server policy, not something the gated caller
        # supplies: passing request.context through let a sender set
        # minimum_score=-1 and be "accepted" with a score of 0, recorded in
        # the observatory as allowed. Anything else in the context still flows.
        context = {k: v for k, v in (request.context or {}).items() if k != "minimum_score"}
        decision = self.system.router.choose_skill({"skill": request.skill or request.task, "topic": request.topic, "concept": request.concept}, candidates, context)
        # The task is caller-written text and may carry personal data or a pasted
        # secret; the observatory keeps a digest, as routing and egress already do.
        self.system.observatory.record("a2a.request", request.sender, task_digest=hashlib.sha256(str(request.task).encode("utf-8")).hexdigest()[:16], gate=decision.gate_id, allowed=decision.allowed)
        return {"accepted": decision.allowed, "decision": decision.__dict__, "candidate_skills": [s.id for s in candidates], "a2a_host": "maxey0"}
