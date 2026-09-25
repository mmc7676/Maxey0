from __future__ import annotations

from maxey0_ss.adapters.a2a import A2AHost, A2ARequest
from .maker_checker_judge import build_demo


if __name__ == "__main__":
    result = A2AHost(build_demo()).handle(A2ARequest(
        sender="external-agent",
        task="Review the service for threat modeling",
        topic="software-engineering",
        concept="security",
        skill="threat modeling",
    ))
    print(result)
