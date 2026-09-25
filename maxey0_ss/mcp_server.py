"""Optional MCP surface for the Maxey0 Context Directory.

Install the MCP dependency declared by the root project to run this module.
The deterministic core does not import MCP, so tests remain runnable without it.
"""
from __future__ import annotations

from .system import SuperSpaceSystem


def build():
    from mcp.server.fastmcp import FastMCP
    system = SuperSpaceSystem()
    mcp = FastMCP("maxey0-context")

    @mcp.resource("maxey0://context/graph")
    def context_graph() -> str:
        import json
        return json.dumps(system.context.graph.graph.to_dict(), sort_keys=True)

    @mcp.resource("maxey0://mcp/directory")
    def mcp_directory() -> str:
        import json
        return json.dumps({k: v.__dict__ for k, v in system.context.graph.mcp.items()}, sort_keys=True)

    @mcp.tool()
    def semantic_candidates(topic: str = "", concept: str = "", skill: str = "") -> list[dict]:
        return [s.__dict__ for s in system.context.graph.semantic_candidates(topic or None, concept or None, skill or None)]

    return mcp


if __name__ == "__main__":
    build().run()
