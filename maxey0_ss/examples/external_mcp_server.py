"""Optional external MCP server used by the full-stack example."""
from __future__ import annotations


def build():
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP("external-security")

    @mcp.resource("security://threat-model/example")
    def threat_model() -> str:
        return "Example security resource: identify assets, trust boundaries, threats, mitigations, and residual risk."

    @mcp.tool()
    def threat_check(asset: str) -> dict:
        return {"asset": asset, "status": "review-required"}

    return mcp


if __name__ == "__main__":
    build().run()
