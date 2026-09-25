from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .. import __version__
from ..models import AgentSpec, LoopSpec, MCPServerRecord, SCWSpec, SkillRecord
from ..adapters.a2a import A2AHost, A2ARequest, a2a_credential_valid
from ..settings import settings as _settings
from ..system import SuperSpaceSystem
from ..adapters.harnesses import ClaudeAgentSDKAdapter, GoogleADKAdapter, LangChainAdapter, OpenAIAgentsAdapter
from ..host_window import HostWindowObserver
from ..context.service import SpecificationExists
from ..semantic.runtime import UnanchoredWindow
from ..scw_deployer import deploy_default_scw
from ..mcp_2026 import build_router
from ..mcp_session_server import build_session_manager
from ..ratelimit import RateLimitMiddleware
from ..auth.policy import (
    OBSERVE_READ,
    SCW_ADMIT,
    SCW_CREATE,
    SCW_READ,
    AuthError,
    is_public_deployment,
)


class MCPIn(BaseModel):
    id: str
    endpoint: str
    name: str
    capabilities: list[str] = Field(default_factory=list)


class SkillIn(BaseModel):
    id: str
    name: str
    concept: str
    topic: str
    gate_id: str
    mcp_servers: list[str] = Field(default_factory=list)
    embedding: list[float] | None = None


class SCWIn(BaseModel):
    id: str
    concept: str
    skills: list[str] = Field(default_factory=list)
    parent_id: str | None = None
    drift_threshold: float = 0.15


class AgentIn(BaseModel):
    id: str
    role: str
    scw_id: str
    capabilities: list[str] = Field(default_factory=list)


class LoopIn(BaseModel):
    id: str
    name: str
    agents: list[str]
    max_iterations: int = 1


#: What each /v1 route requires, by (method, path). The REST surface mirrors
#: operations the MCP tiers protect, so it has to demand the same capability —
#: otherwise the tiers describe a boundary that one transport does not hold.
#: A path absent from this map is public, and that has to be deliberate.
V1_CAPABILITIES: dict[tuple[str, str], str] = {
    ("POST", "/v1/scw/default-deploy"): SCW_CREATE,
    ("POST", "/v1/context/scws"): SCW_CREATE,
    ("POST", "/v1/context/mcp"): SCW_CREATE,
    ("POST", "/v1/context/skills"): SCW_CREATE,
    ("POST", "/v1/execution/agents"): SCW_CREATE,
    ("POST", "/v1/execution/loops"): SCW_CREATE,
    ("POST", "/v1/mcp/delivery"): SCW_CREATE,
    ("POST", "/v1/context/observe/host-window"): OBSERVE_READ,
    ("GET", "/v1/context/observe/host-window"): OBSERVE_READ,
    ("GET", "/v1/observability/trace"): OBSERVE_READ,
    ("GET", "/v1/observability/verify"): OBSERVE_READ,
    ("GET", "/v1/context/graph"): SCW_READ,
    ("GET", "/v1/execution/graph"): SCW_READ,
    ("GET", "/v1/context/scws"): SCW_READ,
    ("GET", "/v1/semantic/drift"): SCW_READ,
    ("POST", "/v1/context/scws/close"): SCW_ADMIT,
    ("POST", "/v1/context/scws/anchor"): SCW_ADMIT,
    ("POST", "/v1/context/scws/drift"): SCW_ADMIT,
}


def _required_capability(method: str, path: str) -> str | None:
    """Resolve a concrete request path to the capability its route declares.

    Path parameters are collapsed so that `/v1/context/scws/SCW1/close` matches
    the `/v1/context/scws/close` entry rather than falling through to public.
    Falling through is the dangerous direction, so the suffix forms are matched
    explicitly instead of by prefix.
    """
    direct = V1_CAPABILITIES.get((method, path))
    if direct is not None:
        return direct
    for suffix, capability in (
        ("/close", SCW_ADMIT), ("/anchor", SCW_ADMIT), ("/drift", SCW_ADMIT),
    ):
        if path.startswith("/v1/context/scws/") and path.endswith(suffix):
            return capability
    if path.startswith("/v1/semantic/drift/"):
        return SCW_READ
    if path.startswith("/v1/mcp/delivery/") and method == "POST":
        return SCW_CREATE
    return None


def create_app(system: SuperSpaceSystem | None = None) -> FastAPI:
    system = system or SuperSpaceSystem()
    # One surface for the whole process, shared by every transport built below
    # rather than each building — and paying for — its own.
    from ..mcp_surface import SERVER_NAME, build_surface

    surface = build_surface(system)
    # One Authorizer for every door: the stateless router, the session
    # transport, the /v1 middleware below and the rate limiter all resolve a
    # caller with this instance, so none of them can disagree about who is
    # calling -- and the /v1 check no longer rebuilds one per request.
    authorizer = surface.authorizer
    # One StreamableHTTPSessionManager per app instance — its own docs warn it
    # cannot be reused past one run() lifecycle, so a fresh app (as tests build
    # per-case) needs a fresh manager rather than a module-level singleton.
    session_manager = build_session_manager(system, surface=surface, authorizer=authorizer)

    @contextlib.asynccontextmanager
    async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
        async with session_manager.run():
            yield

    # /docs, /redoc and /openapi.json answered 200 through the tunnel: a
    # generated map of every /v1 route, served to anybody. A public deployment
    # does not serve them; a local one keeps them for development.
    hidden = (
        {"docs_url": None, "redoc_url": None, "openapi_url": None}
        if is_public_deployment() else {}
    )
    app = FastAPI(title="Maxey0-SuperSpace", version=__version__, lifespan=_lifespan, **hidden)

    @app.middleware("http")
    async def _enforce_v1_capabilities(request: Request, call_next):
        """Apply the MCP capability model to the REST surface.

        /v1 is mounted on the same app as /mcp and enforced none of it, so on a
        deployment with MAXEY0_PUBLIC=1 every operation the tiers protect was
        reachable unauthenticated through the other door.
        """
        capability = _required_capability(request.method, request.url.path)
        if capability is not None:
            try:
                principal = authorizer.principal(request.headers.get("authorization"))
            except AuthError as exc:
                return JSONResponse({"detail": str(exc)}, status_code=exc.status)
            if not principal.may(capability):
                return JSONResponse(
                    {"detail": f"role {principal.role!r} lacks {capability!r}"},
                    status_code=403,
                )
        return await call_next(request)

    # Added after the /v1 middleware, so it runs outside it: Starlette puts the
    # last-added middleware outermost. A refused request costs no routing, no
    # body parsing and no second credential check. See maxey0_ss.ratelimit.
    app.add_middleware(RateLimitMiddleware, limiter=surface.rate_limiter, authorizer=authorizer)

    app.state.superspace = system
    app.state.maxey0 = system  # compatibility alias
    app.state.host_window = HostWindowObserver()
    # Reachable for inspection and tests — the surface itself was built above.
    app.state.maxey0_surface = surface
    app.state.session_manager = session_manager
    # `build_router` rather than `mcp_public_server.create_public_router`,
    # which does not pass an Authorizer through and so gave the router one of
    # its own.
    app.include_router(build_router(
        surface.tools, surface.resources, SERVER_NAME,
        cache=surface.cache, tasks=surface.tasks, authorizer=authorizer,
    ))
    # Session-based Streamable HTTP, for hosts that open a session (Claude
    # Code, Claude Desktop) and so cannot speak to the stateless /mcp above.
    # Same surface, same Authorizer policy, different handshake — see
    # mcp_session_server.py.
    app.mount("/mcp/session", session_manager.handle_request)

    @app.post("/v1/scw/default-deploy")
    def default_scw_deploy(body: dict):
        task = body.get("task")
        if not isinstance(task, str) or not task.strip():
            raise HTTPException(400, "task is required")
        spec = deploy_default_scw(task, scw_id=body.get("scw_id", "SCW0"), parent_id=body.get("parent_id"), concept=body.get("concept", "Task"))
        try:
            system.create_scw(spec)
        except SpecificationExists as exc:
            raise HTTPException(409, str(exc)) from exc
        return spec.__dict__

    @app.post("/v1/context/observe/host-window")
    def observe_host_window(body: dict):
        segments = body.get("segments")
        if not isinstance(segments, list):
            raise HTTPException(400, "segments must be a list")
        try:
            return app.state.host_window.observe(segments)
        except ValueError as exc:  # malformed segment: the caller's input, not a 500
            raise HTTPException(400, str(exc)) from exc

    @app.get("/v1/context/observe/host-window")
    def host_window_contract():
        return {"scope": "host-supplied", "hidden_model_context_access": False, "required_input": ["segment_id", "start", "end", "label"]}

    @app.get("/health")
    def health():
        return {"ok": True, "service": "maxey0-ss"}

    # agent-card.json is the path A2A clients look for; the two maxey0-*
    # names are kept for callers that already use them.
    @app.get("/.well-known/agent-card.json")
    @app.get("/.well-known/maxey0-ss-agent.json")
    @app.get("/.well-known/maxey0-agent.json")
    def agent_card():
        return {"name": "Maxey0-SuperSpace", "protocol": "A2A", "capabilities": ["loop-routing", "semantic-context-routing", "scw-instantiation"]}

    @app.post("/v1/a2a/message")
    def a2a_message(body: dict, request: Request):
        # The shared secret was loaded into AuthConfig and never checked, so any
        # caller could drive the A2A surface. Verified here, in constant time.
        if not a2a_credential_valid(request.headers.get("authorization"), _settings().a2a_shared_secret):
            raise HTTPException(status_code=401, detail="A2A shared secret required")
        # A raw **body turned an unknown key, a non-dict context or a
        # non-string task into an unhandled 500. Bad input is a 400.
        try:
            a2a_request = A2ARequest(**body)
        except TypeError as exc:
            raise HTTPException(400, f"invalid A2A request: {exc}") from exc
        if not isinstance(a2a_request.sender, str) or not isinstance(a2a_request.task, str):
            raise HTTPException(400, "sender and task must be strings")
        if a2a_request.context is not None and not isinstance(a2a_request.context, dict):
            raise HTTPException(400, "context must be an object")
        for name in ("topic", "concept", "skill", "requested_loop"):
            if getattr(a2a_request, name) is not None and not isinstance(getattr(a2a_request, name), str):
                raise HTTPException(400, f"{name} must be a string")
        return A2AHost(system).handle(a2a_request)

    @app.get("/v1/context/graph")
    def context_graph():
        return system.context.graph.graph.to_dict()

    @app.get("/v1/execution/graph")
    def execution_graph():
        return system.execution.snapshot()

    @app.get("/v1/observability/trace")
    def trace():
        return system.observatory.trace()

    @app.get("/v1/observability/verify")
    def verify():
        return {"valid": system.observatory.verify()}

    @app.post("/v1/context/mcp")
    def register_mcp(body: MCPIn):
        system.register_mcp(MCPServerRecord(body.id, body.endpoint, body.name, body.capabilities))
        return {"registered": body.id}

    @app.post("/v1/context/skills")
    def register_skill(body: SkillIn):
        system.register_skill(SkillRecord(body.id, body.name, body.concept, body.topic, body.gate_id, body.mcp_servers, body.embedding))
        return {"registered": body.id}

    @app.post("/v1/context/scws")
    def create_scw(body: SCWIn):
        try:
            system.create_scw(SCWSpec(body.id, body.parent_id, body.concept, body.skills, {}, body.drift_threshold))
        except SpecificationExists as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"created": body.id}

    @app.post("/v1/execution/agents")
    def add_agent(body: AgentIn):
        if body.scw_id not in system.context.graph.scw_specs:
            raise HTTPException(404, "SCW spec not found")
        system.add_agent(AgentSpec(body.id, body.role, body.scw_id, body.capabilities))
        return {"registered": body.id}

    @app.post("/v1/execution/loops")
    def add_loop(body: LoopIn):
        system.add_loop(LoopSpec(body.id, body.name, body.agents, body.max_iterations))
        return {"registered": body.id}

    @app.post("/v1/context/scws/{scw_id}/close")
    def close_scw(scw_id: str):
        if scw_id not in system.context.instances:
            raise HTTPException(404, "SCW instance not found")
        system.context.close(scw_id)
        return {"closed": scw_id}

    @app.get("/v1/context/scws")
    def scws():
        return system.context.snapshot()["scw_instances"]

    @app.post("/v1/context/scws/{scw_id}/anchor")
    def anchor_scw(scw_id: str, body: dict):
        if scw_id not in system.context.instances:
            raise HTTPException(404, "SCW instance not found")
        vector = body.get("vector")
        if not isinstance(vector, list) or not vector:
            raise HTTPException(400, "vector must be a non-empty list")
        # SemanticRuntime validates (finite numbers, dimension cap) before it
        # stores anything; ['a','b'] used to be stored and poison every later
        # inspection of the window with a 500.
        try:
            system.drift_runtime.anchor(scw_id, vector)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"anchored": scw_id}

    @app.post("/v1/context/scws/{scw_id}/drift")
    def inspect_drift(scw_id: str, body: dict):
        instance = system.context.instances.get(scw_id)
        if instance is None:
            raise HTTPException(404, "SCW instance not found")
        vector = body.get("vector")
        try:
            record = system.drift_runtime.inspect(scw_id, vector, body.get("threshold", 0.15))
        except UnanchoredWindow as exc:
            # The MCP tool answers this as a structured refusal; REST let the
            # exception escape as a 500. Same state, same answer, here a 409.
            raise HTTPException(409, str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc
        return record.__dict__

    @app.get("/v1/a2a/directory")
    def a2a_directory():
        return {"agents": system.a2a_directory.describe()}

    @app.get("/v1/harnesses")
    def harnesses():
        adapters = [ClaudeAgentSDKAdapter(), OpenAIAgentsAdapter(), LangChainAdapter(), GoogleADKAdapter()]
        return [{"name": a.capabilities.name, "maxey0_host": a.capabilities.maxey0_host, "a2a_agent": a.capabilities.a2a_agent, "mcp_client": a.capabilities.mcp_client, "notes": list(a.capabilities.notes)} for a in adapters]

    @app.get("/v1/distribution")
    def distribution():
        return {
            "product_boundary": ["context_graph", "execution_graph", "scw_runtime", "semantic_drift_runtime", "a2a_directory", "mcp_directory", "mcp_delivery", "a2a_integration", "engineering_observability"],
            "external": ["model", "agent_harness"],
            "harnesses": ["claude-agent-sdk", "openai-agents", "langchain", "google-adk"],
            "plugin_surfaces": ["claude-code", "codex", "claude", "chatgpt"],
            "distribution_site": "maxey0.com",
        }

    @app.post("/v1/mcp/delivery/{server_id}")
    def deliver_mcp(server_id: str, body: dict):
        method = body.get("method")
        if not isinstance(method, str) or not method:
            raise HTTPException(400, "method is required")
        return system.mcp_delivery.deliver(server_id, method, **body.get("params", {})).__dict__

    @app.get("/v1/mcp/delivery")
    def delivery_directory():
        return {"servers": system.mcp_delivery.describe()}

    @app.get("/v1/mcp/directory")
    def directory():
        return {"servers": [s.__dict__ for s in system.context.graph.mcp.values()]}

    @app.get("/v1/semantic/drift/{scw_id}")
    def semantic_drift(scw_id: str):
        records = [r.__dict__ for r in system.drift_runtime.records if r.scw_id == scw_id]
        return {"scw_id": scw_id, "records": records}

    return app


app = create_app()
