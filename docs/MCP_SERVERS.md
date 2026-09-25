# Running the MCP servers

## Setup

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows
.venv/Scripts/python.exe -m pip install -e .
# POSIX: .venv/bin/python -m pip install -r requirements.txt && .venv/bin/python -m pip install -e .
```

The editable install is required, not optional. It puts `maxey0_ss` on the
interpreter's path and installs the `maxey0-ss-mcp` console entrypoint, so the
server can be launched from any working directory. Without it, `python -m
maxey0_ss.mcp_stdio_server` only works when the shell is already sitting in the
repository root — which a host launching the server is not.

`pyproject.toml` declares `[tool.setuptools.packages.find] include =
["maxey0_ss*"]`. Without that, auto-discovery finds nothing among the
repository's many non-package top-level directories and `pip install -e .`
succeeds while installing no importable package.

`requirements.txt` pins `mcp>=1.19.0,<2`. The upper bound is load-bearing: mcp
2.x renamed `FastMCP` to `MCPServer` and removed `mcp.server.fastmcp`, which
breaks every v1 entrypoint in this repository. An unbounded pin silently
resolves to 2.x and fails at import.

## Build the MCP App before serving it

```bash
cd mcp_apps/super_space_react
npm install
npm run typecheck
npm run build
```

This produces `dist/mcp-app.html` — one self-contained file, no external
fetches. `dist/` is gitignored, so **a fresh clone has no artifact** and the
server falls back to `mcp_apps/super_space.html`, an unbuilt stub. The fallback
is deliberate but silent, so verify which artifact is live:

```bash
.venv/Scripts/python.exe -c "from maxey0_ss.mcp_surface import super_space_artifact; print(super_space_artifact())"
```

`kind` must read `built`, not `fallback-stub`.

## Local stdio server (Claude Code, Claude Desktop)

Configured by the repository's `.mcp.json`:

```json
{
  "mcpServers": {
    "maxey0-ss": {
      "command": ".venv/Scripts/maxey0-ss-mcp.exe",
      "args": []
    }
  }
}
```

A project `.mcp.json` is only read when *this directory is the project root*.
To use the server from any directory, register it at user scope with an
absolute path to the same executable:

```bash
claude mcp add maxey0-ss --scope user -- "<absolute path to this repo>\.venv\Scripts\maxey0-ss-mcp.exe"
```

Run it by hand to check it starts:

```bash
.venv/Scripts/maxey0-ss-mcp.exe
```

It will sit silently waiting for JSON-RPC on stdin. That is correct — a stdio
server that prints anything to stdout corrupts the protocol stream.

**A config file is not evidence.** Claude Code reads `.mcp.json` at session
start only; after editing it, restart the session. Then confirm the server is
listed and its tools resolve, rather than assuming the file took effect.

## Public HTTP server (remote / edge)

```bash
.venv/Scripts/python.exe -m maxey0_ss.public_server     # 0.0.0.0:8765
.venv/Scripts/python.exe -m maxey0_ss                   # 127.0.0.1:8765
```

Probe it — note the headers are mandatory:

```bash
curl -s localhost:8765/mcp \
  -H 'MCP-Protocol-Version: 2026-07-28' \
  -H 'Mcp-Method: server/discover' \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"server/discover","params":{}}'
```

`initialize` is **not** implemented and will return `-32601`. That is the
2026-07-28 contract, not a fault.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `No module named 'mcp.server.fastmcp'` | mcp 2.x installed | `pip install "mcp<2"` |
| Server connects, App renders as a plain stub | `dist/mcp-app.html` missing | run the npm build |
| `-32601 Method not found: initialize` on HTTP | Expected | use `server/discover`, or the stdio transport |
| `-32600 Unsupported MCP protocol version` | Missing `MCP-Protocol-Version` header | send `2026-07-28` |
| `CONNECTION_CLOSED` at session start | Interpreter or module path wrong | run the command from `.mcp.json` by hand and read stderr |
| Tool rejected with "SCW address required" | Address not `scw://a/b/c/d/e` | supply all five segments |
