from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .adapters.mcp import MCPClient
from .context.directory import MCPDirectory
from .models import MCPServerRecord


@dataclass
class MCPDeliveryResult:
    server_id: str
    method: str
    delivered: bool
    result: Any = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class MCPDelivery:
    """Routes calls to registered MCP server sessions without owning the servers."""

    def __init__(self, directory: MCPDirectory, client: MCPClient | None = None) -> None:
        self.directory = directory
        self.client = client or MCPClient()

    def register_server(self, server: MCPServerRecord, call: Callable[..., Any]) -> None:
        self.directory.register(server)
        self.client.bind(server.id, call)

    def deliver(self, server_id: str, method: str, **params: Any) -> MCPDeliveryResult:
        if server_id not in self.directory.context.mcp:
            return MCPDeliveryResult(server_id, method, False, error="unknown MCP server")
        try:
            result = self.client.call(server_id, method, **params)
        except Exception as exc:
            return MCPDeliveryResult(server_id, method, False, error=str(exc))
        return MCPDeliveryResult(server_id, method, True, result=result)

    def describe(self) -> list[dict[str, Any]]:
        return [s.__dict__ for s in self.directory.context.mcp.values()]
