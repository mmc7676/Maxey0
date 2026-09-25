"""Optional MCP Delivery server exposing the Maxey0 delivery directory.

The server does not pretend to proxy arbitrary MCP protocol traffic. Delivery is
performed through explicitly bound server sessions in MCPDelivery. This keeps
credentials and transport ownership with the integration that registered them.
"""
from __future__ import annotations

import json
from typing import Any

from .mcp_delivery import MCPDelivery
from .system import SuperSpaceSystem


def build(system: SuperSpaceSystem | None = None):
    from mcp.server.fastmcp import FastMCP

    system = system or SuperSpaceSystem()
    delivery = MCPDelivery(system.directory)
    mcp = FastMCP("maxey0-mcp-delivery")

    @mcp.resource("maxey0://mcp/delivery/directory")
    def directory() -> str:
        return json.dumps(delivery.describe(), sort_keys=True)

    @mcp.tool()
    def deliver(server_id: str, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        result = delivery.deliver(server_id, method, **(params or {}))
        return result.__dict__

    return mcp


if __name__ == "__main__":
    build().run()
