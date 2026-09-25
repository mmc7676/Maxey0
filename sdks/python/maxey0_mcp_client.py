"""Minimal MCP 2026-07-28 client surface for Maxey0."""
from __future__ import annotations
import json
import urllib.request


def call(url: str, method: str, name: str = "", params: dict | None = None) -> dict:
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    headers = {"Content-Type": "application/json", "MCP-Protocol-Version": "2026-07-28", "Mcp-Method": method}
    if name:
        headers["Mcp-Name"] = name
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read())
