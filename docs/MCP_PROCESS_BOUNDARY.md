# MCP process boundary

This document records what was established from the implementation, not from
naming. It is the answer to "how many MCP servers does Maxey0-SuperSpace need?"

## The short answer

**One core, four transports. Not four processes.**

SCW0, SCW1, SCW2 and SCW3 are *application state*. They are not MCP servers,
not OS processes, and not transports.

## Why SCW names are not processes

| Evidence | Location | What it shows |
|---|---|---|
| `SCWSpec` is a dataclass | `maxey0_ss/models.py` | An SCW is a record |
| `deploy_default_scw(task, scw_id="SCW0", parent_id=...)` | `maxey0_ss/scw_deployer.py` | SCW0 is the default *id*; children are `parent_id` links |
| `SCWRuntime` — "Can be embedded or process-isolated" | `maxey0_ss/runtimes/scw.py` | Embedded is the shipped path; `start`/`stop` mutate an in-memory set |
| `scw/` holds only Markdown | `scw/scw0…scw11` | Design-note workstreams. There is no `scw2/` or `scw3/` directory at all |
| `SCW0_TO_SCW1.md` | repository root | Describes a *knowledge-provenance* handoff, not a process boundary |

Subdeployment is parent/child linkage inside one context graph. Creating four
OS processes because four names exist would have invented a topology the
implementation does not have.

`maxey0_ss/tests/test_mcp_surface.py::test_scw_identifiers_are_application_state_not_processes`
holds this property.

## The four transports

All four adapt the same surface, defined once in `maxey0_ss/mcp_surface.py`.

### 1. Stateless HTTP — MCP 2026-07-28

```
maxey0_ss/mcp_public_server.py  →  mcp_2026.py::build_router()  →  POST /mcp
   mounted at maxey0_ss/api/app.py
   served by  maxey0_ss/public_server.py::main()   (uvicorn, 0.0.0.0:8765)
```

Per `docs/MCP_2026_07_28.md`, this adapter deliberately has **no**
`initialize` / `initialized` handshake and **no** `Mcp-Session-Id`. Discovery is
`server/discover`. Routing uses `MCP-Protocol-Version`, `Mcp-Method` and
`Mcp-Name` request headers.

This is the surface intended for `https://mcp.maxey0.com/mcp`.

**Consequence, verified:** a host that opens a session cannot talk to it.
`initialize` returns `-32601 Method not found`; a request without the custom
headers returns `-32600`. That is correct for 2026-07-28, not a defect — but it
means this transport alone cannot serve Claude Code or Claude Desktop.

### 2. Session stdio — classic MCP

```
maxey0_ss/mcp_stdio_server.py   →  mcp.server.lowlevel.Server  →  stdio
```

Exists precisely because of the consequence above, for a host that spawns this
process locally (Claude Desktop's `.mcpb`, a Desktop/Code config entry). Same
tools, same resources, same admission rule, different protocol era. Tool
schemas are declared verbatim from the shared surface rather than inferred from
function signatures, so transports advertise identical contracts. stdio carries
no credentials, so a local caller is trusted the same way `MAXEY0_AUTH_MODE=disabled`
trusts one — see `mcp_stdio_server._stdio_principal`.

### 3. Session Streamable HTTP — classic MCP, remote

```
maxey0_ss/mcp_session_server.py  →  mcp.server.streamable_http_manager  →  POST /mcp/session
   mounted at maxey0_ss/api/app.py, same process as transport 1
```

Same consequence, same fix, over HTTP instead of stdio — for a host that can
only reach a URL and still opens a session (Claude Code / Claude Desktop's
remote-connector UI, pointed at `https://origin.maxey0.com/mcp/session` rather
than the stateless `/mcp`). Built on the SDK's own `StreamableHTTPSessionManager`
rather than hand-rolled session state, and shares `mcp_stdio_server.build_server()`
verbatim — only the principal resolver differs, because unlike stdio this
transport crosses the public tunnel the same as transport 1 does, so it reads
the real `Authorization` header on every request rather than assuming local
trust. Deliberately *not* built into the Cloudflare edge: a Worker is
stateless by design (Cloudflare's own current guidance deprecated `McpAgent`,
their prior Durable-Object-backed pattern for exactly this), so session state
lives on the origin process instead, which is already long-running.

### 4. Cloudflare edge — remote, stateless only

```
workers/mcp-edge/  →  POST /mcp at the edge
```

Serves the metadata half of the protocol from a catalog generated out of
`mcp_surface`, and forwards every `tools/call` to the Python origin. It executes
no tool, so it adds a transport without adding a second implementation. See
[EDGE_DEPLOYMENT.md](EDGE_DEPLOYMENT.md). Session state doesn't fit here — see
transport 3's note — which is why the edge only ever grew the stateless surface.

## What keeps them from drifting

No transport owns the tool list. `mcp_surface.build_surface()` owns it, and
`test_mcp_surface.py` asserts the HTTP tool list equals the surface tool list.
Adding a tool to one transport and not the other is a test failure. Transports
2 and 3 additionally share one `Server` builder
(`mcp_stdio_server.build_server`) rather than each declaring `list_tools`/
`call_tool`/`list_resources`/`read_resource` again — the only thing that
differs between them is `principal_resolver`.

## Surface

11 tools, 3 resources:

```
maxey0-ss.health              maxey0-ss.scw.create
maxey0-ss.distribution        maxey0-ss.scw.describe
maxey0-ss.auth.manifest       maxey0-ss.scw.close
maxey0-ss.cache.status        maxey0-ss.scw.observe_host_window   [ui, requires SCW address]
maxey0-ss.app.artifact        maxey0-ss.super_space     [ui]
maxey0-ss.gate.inspect

ui://maxey0-ss/super-space.html        text/html;profile=mcp-app
maxey0-ss://super-space/host-window    application/json
maxey0-ss://architecture/planes        application/json
```

## Admission

`maxey0-ss.scw.observe_host_window` sets `requires_scw`. The Python transports parse the
`scw_address` through `EnforceableAddress` and refuse anything that is not
`scw://topic/concept/skill/region/scw_id`, then consult the semantic gate
(`DisabledSemanticGate` by default — structural checks only). A tool cannot be
reached locally under weaker conditions than it is remotely. The edge inherits
the rule for free: it forwards tool calls rather than executing them, so the
origin's admission check is the only one there is.
