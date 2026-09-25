from __future__ import annotations

from typing import Any, Callable


class MCPClient:
    """Minimal MCP capability adapter; protocol transport is intentionally pluggable."""

    def __init__(self) -> None:
        self.sessions: dict[str, Callable[..., Any]] = {}

    def bind(self, server_id: str, call: Callable[..., Any]) -> None:
        self.sessions[server_id] = call

    def call(self, server_id: str, method: str, **params: Any) -> Any:
        if server_id not in self.sessions:
            raise KeyError(f"no MCP session for {server_id}")
        return self.sessions[server_id](method=method, **params)
