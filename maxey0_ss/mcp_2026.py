"""MCP 2026-07-28 stateless HTTP surface for Maxey0.

This adapter intentionally does not depend on a protocol-level session. Each
request is self-describing and may land on any server instance. Application
state (SCWs, ledgers, explicit handles) remains above the transport layer.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from . import __version__
from .cache.policy import CacheHint, MCPMetadataCache
from .gating.address import EnforceableAddress
from .auth.policy import AuthError, Authorizer
from .gating.semantic import SemanticGateProvider, select_semantic_gate
from .tasks import (
    ACK_NOTIFICATION,
    SUBSCRIBE_METHOD,
    TASK_METHODS,
    TASKS_EXTENSION,
    TaskError,
    TaskStore,
    owned_by,
)

#: Reading or mutating a task exposes the originating tool's result, so
#: the task branch demands the observation capability rather than nothing.
TASK_CAPABILITY = "observe"


MCP_VERSION = "2026-07-28"
JSONRPC = "2.0"

@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], Any]
    meta: dict[str, Any] | None = None
    requires_scw: bool = False
    #: Capability a caller must hold. None means public/unauthenticated.
    capability: str | None = None
    #: A further capability particular arguments demand, or None. Additive:
    #: both are authorized, so an argument can make a call dearer than the
    #: declared tier and never cheaper. `capability` stays what the catalog
    #: reports. `scw.drift` measures under scw.read and anchors under scw.admit.
    argument_capability: Callable[[Any], str | None] | None = None

    def required_capabilities(self, arguments: Any) -> tuple[str | None, ...]:
        """Every capability this call needs, declared tier first."""
        extra = self.argument_capability(arguments) if self.argument_capability else None
        return (self.capability,) if extra is None else (self.capability, extra)

@dataclass
class Resource:
    uri: str
    name: str
    description: str
    mime_type: str
    reader: Callable[[], Any]
    meta: dict[str, Any] | None = None


def _ok(req_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC, "id": req_id, "result": result}


def _err(req_id: Any, code: int, message: str, data: Any | None = None) -> dict[str, Any]:
    out = {"jsonrpc": JSONRPC, "id": req_id, "error": {"code": code, "message": message}}
    if data is not None:
        out["error"]["data"] = data
    return out


def _structured(value: Any) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(value, sort_keys=True)}], "structuredContent": value}


def build_router(tools: list[Tool], resources: list[Resource], server_name: str = "Maxey0-SuperSpace", *, cache: MCPMetadataCache | None = None, semantic_gate: SemanticGateProvider | None = None, tasks: TaskStore | None = None, authorizer: Authorizer | None = None) -> APIRouter:
    router = APIRouter()
    tool_map = {t.name: t for t in tools}
    resource_map = {r.uri: r for r in resources}
    cache = cache or MCPMetadataCache()
    # Configuration reaches the gate here. Defaulting to
    # DisabledSemanticGate() meant `semantic_gate.provider` -- which
    # settings.py reads from the environment and config/credentials.json --
    # had no consumer, so naming a provider changed nothing.
    semantic_gate = semantic_gate or select_semantic_gate()
    tasks = tasks if tasks is not None else TaskStore()
    authorizer = authorizer or Authorizer()
    catalog_hint = CacheHint(300000, "server")

    @router.post("/mcp")
    async def mcp(request: Request) -> Response:
        # 2026-07-28 Streamable HTTP requires these routing headers.
        protocol = request.headers.get("MCP-Protocol-Version")
        method_header = request.headers.get("Mcp-Method")
        name_header = request.headers.get("Mcp-Name")
        if protocol != MCP_VERSION:
            return JSONResponse(_err(None, -32600, "Unsupported MCP protocol version", {"expected": MCP_VERSION}), status_code=400)
        if not method_header:
            return JSONResponse(_err(None, -32600, "Missing Mcp-Method header"), status_code=400)
        if method_header == "tools/call" and not name_header:
            return JSONResponse(_err(None, -32600, "Missing Mcp-Name header for tools/call"), status_code=400)
        # SEP-2663: over Streamable HTTP the client MUST set Mcp-Name to the
        # taskId, so intermediaries can route a task to the instance holding it.
        if method_header in TASK_METHODS and not name_header:
            return JSONResponse(_err(None, -32600, f"Missing Mcp-Name header for {method_header}; it must carry params.taskId"), status_code=400)

        try:
            body = await request.json()
        except Exception:
            return JSONResponse(_err(None, -32700, "Parse error"), status_code=400)
        req_id = body.get("id")
        method = body.get("method")
        params = body.get("params") or {}
        if method != method_header:
            return JSONResponse(_err(req_id, -32600, "Mcp-Method does not match JSON-RPC method"), status_code=400)

        if method == "server/discover":
            result = {
                "protocolVersion": MCP_VERSION,
                "serverInfo": {"name": server_name, "version": __version__},
                "capabilities": {"tools": {}, "resources": {}, "prompts": {}, "extensions": {"io.modelcontextprotocol/tasks": {}, "io.modelcontextprotocol/ui": {}}},
            }
            return JSONResponse(_ok(req_id, result))
        if method == "tools/list":
            key = "tools:list"
            result = cache.get(key)
            if result is None:
                result = {"tools": [{"name": t.name, "description": t.description, "inputSchema": t.input_schema, **({"_meta": t.meta} if t.meta else {})} for t in tools], **catalog_hint.as_dict()}
                cache.put(key, result, catalog_hint)
            return JSONResponse(_ok(req_id, result))
        if method == "tools/call":
            # Mirror the SEP-2663 taskId rule. The header is what intermediaries
            # route and meter on, so letting params.name silently win on
            # disagreement lets the name they routed differ from the tool the
            # origin executes.
            if name_header and params.get("name") and params["name"] != name_header:
                return JSONResponse(
                    _err(req_id, -32600, "Mcp-Name must equal params.name",
                         {"header": name_header, "name": params["name"]}),
                    status_code=400,
                )
            name = params.get("name") or name_header
            tool = tool_map.get(name)
            if tool is None:
                return JSONResponse(_err(req_id, -32602, f"Unknown tool: {name}"), status_code=400)
            arguments = params.get("arguments") or {}
            # Authorization precedes the gate and the handler. A caller who may
            # not invoke this tool must not reach either -- including with the
            # arguments it sent, which can demand more than the declared tier.
            try:
                # In a worker thread: an OIDC verifier may fetch a key set, and
                # a network round-trip on the event loop stalls every request.
                principal = await run_in_threadpool(
                    authorizer.principal, request.headers.get("authorization"))
                for capability in tool.required_capabilities(arguments):
                    authorizer.authorize(principal, capability, tool.name)
            except AuthError as exc:
                return JSONResponse(_err(req_id, exc.code, str(exc)), status_code=exc.status)
            if tool.requires_scw:
                address = arguments.get("scw_address")
                try:
                    parsed = EnforceableAddress.parse(address or "")
                except ValueError as exc:
                    return JSONResponse(_err(req_id, -32001, "SCW address required", {"reason": str(exc)}), status_code=403)
                decision = semantic_gate.evaluate(address=parsed.uri(), capability=name, metadata={"headers": dict(request.headers), "meta": params.get("_meta") or {}})
                if not decision.allowed:
                    return JSONResponse(_err(req_id, -32003, "SCW semantic gate denied request", decision.__dict__), status_code=403)
            try:
                with owned_by(principal.subject):
                    value = tool.handler(arguments)
                payload = _structured(value)
                meta = params.get("_meta") or {}
                trace = {k: meta[k] for k in ("traceparent", "tracestate", "baggage") if k in meta}
                if trace:
                    payload["_meta"] = {"trace": trace}
                return JSONResponse(_ok(req_id, payload))
            except Exception as exc:
                return JSONResponse(_err(req_id, -32603, "Tool execution failed", {"type": type(exc).__name__, "message": str(exc)}), status_code=500)
        if method == "resources/list":
            key = "resources:list"
            result = cache.get(key)
            if result is None:
                result = {"resources": [{"uri": r.uri, "name": r.name, "description": r.description, "mimeType": r.mime_type, **({"_meta": r.meta} if r.meta else {})} for r in resources], **catalog_hint.as_dict()}
                cache.put(key, result, catalog_hint)
            return JSONResponse(_ok(req_id, result))
        if method == "resources/read":
            uri = params.get("uri")
            resource = resource_map.get(uri)
            if resource is None:
                return JSONResponse(_err(req_id, -32602, f"Unknown resource: {uri}"), status_code=400)
            value = resource.reader()
            text = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
            return JSONResponse(_ok(req_id, {"contents": [{"uri": uri, "mimeType": resource.mime_type, "text": text, **({"_meta": resource.meta} if resource.meta else {})}], "ttlMs": 300000, "cacheScope": "server"}))
        if method in TASK_METHODS:
            # A task carries the terminal result payload of the tool that
            # produced it, so reading one is reading that tool's output. The
            # branch consulted no authorizer at all, which made every task a
            # way around the capability the originating tool declared.
            try:
                principal = await run_in_threadpool(
                    authorizer.principal, request.headers.get("authorization"))
                authorizer.authorize(principal, TASK_CAPABILITY, method)
            except AuthError as exc:
                return JSONResponse(_err(req_id, exc.code, str(exc)), status_code=exc.status)
            task_id = params.get("taskId")
            if not isinstance(task_id, str) or not task_id:
                return JSONResponse(_err(req_id, -32602, "taskId is required"), status_code=400)
            if name_header != task_id:
                return JSONResponse(_err(req_id, -32600, "Mcp-Name must equal params.taskId", {"header": name_header, "taskId": task_id}), status_code=400)
            try:
                # Another principal's task is answered exactly as a missing one:
                # "forbidden" would confirm the id exists.
                owner = tasks.get(task_id).owner
                if owner is not None and owner != principal.subject:
                    raise TaskError(f"Unknown task: {task_id}")
                if method == "tasks/get":
                    task = tasks.get(task_id)
                elif method == "tasks/update":
                    task = tasks.provide_input(task_id, params.get("inputResponses") or {})
                else:  # tasks/cancel
                    task = tasks.cancel(task_id)
            except TaskError as exc:
                return JSONResponse(_err(req_id, -32602, str(exc)), status_code=404)
            # "complete" once terminal, so a poller knows the payload is final.
            result_type = "complete" if task.status.terminal else "task"
            return JSONResponse(_ok(req_id, task.as_result(result_type=result_type)))

        if method == SUBSCRIBE_METHOD:
            requested = (params.get("notifications") or {}).get("taskIds")
            subscriber = request.headers.get("Mcp-Subscriber") or "anonymous"
            accepted = tasks.listen(subscriber, requested)
            # Stateless transport: acknowledge inline rather than holding a stream.
            return JSONResponse(_ok(req_id, {
                "notifications": {"taskIds": accepted},
                "acknowledgement": ACK_NOTIFICATION,
            }))

        if method == "prompts/list":
            return JSONResponse(_ok(req_id, {"prompts": [], "ttlMs": 300000, "cacheScope": "server"}))
        return JSONResponse(_err(req_id, -32601, f"Method not found: {method}"), status_code=404)

    return router
