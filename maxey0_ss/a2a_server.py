from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from .adapters.a2a import A2AHost, A2ARequest
from .system import SuperSpaceSystem
from . import __version__


class Message(BaseModel):
    sender: str
    task: str
    topic: str | None = None
    concept: str | None = None
    skill: str | None = None
    requested_loop: str | None = None
    context: dict = {}


def create_a2a_app(system: SuperSpaceSystem | None = None) -> FastAPI:
    system = system or SuperSpaceSystem()
    host = A2AHost(system)
    app = FastAPI(title="Maxey0 A2A Host", version=__version__)

    @app.get("/.well-known/maxey0-agent.json")
    def card():
        return {
            "name": "Maxey0-SuperSpace",
            "description": "Context-aware agentic-loop orchestrator",
            "protocol": "A2A",
            "capabilities": ["loop-routing", "semantic-context-routing", "scw-instantiation"],
        }

    @app.post("/a2a/message")
    def message(body: Message):
        return host.handle(A2ARequest(**body.model_dump()))

    return app
