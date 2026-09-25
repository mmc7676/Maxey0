# Maxey0-SuperSpace — Claude Code / Cloudflare MCP Setup

## Scope

This runbook is for the repository produced by the Maxey0-SuperSpace API refactor.

Important boundary:

- The repository refactor is complete.
- The Maxey0-SuperSpace Python API is now `maxey0_ss`.
- MCP server deployment has **not** been performed.
- A production Cloudflare Worker MCP server has **not** been created by this runbook.
- Do not replace the existing Maxey0-SuperSpace implementation with a Cloudflare template.
- The future Cloudflare MCP server should be an edge/transport adapter over the Maxey0-SuperSpace API, not a replacement for the core.

The current MCP 2026-07-28 specification is stateless at the protocol layer. Cloudflare's current guidance recommends `createMcpHandler()` for new stateless servers and identifies `McpAgent` as deprecated and feature-frozen. Cloudflare's current MCP endpoint is `/mcp`. 

---

## STEP 0 — Do not deploy anything yet

Open Claude Code in the local:

```text
Maxey0-SuperSpace
```

First instruction to Claude Code:

> Inspect this repository before changing anything. Do not deploy, publish, create Cloudflare resources, modify DNS, create Durable Objects, create MCP servers, or change secrets. Review the Maxey0-SuperSpace package/API, existing MCP 2026 implementation, tests, `wrangler` configuration if present, and repository structure. Report what is already implemented and what must be added for a Cloudflare remote MCP edge adapter.

---

## STEP 1 — Verify the new Python API

From the repository root:

```bash
python -m pip install -e .
python -c "from maxey0_ss import SuperSpaceSystem; print(SuperSpaceSystem().__class__.__name__)"
python -m pytest -q
```

Expected baseline:

```text
266 passed, 1 skipped, 11 subtests passed
```

Do not proceed if the refactored baseline is broken.

---

## STEP 2 — Inspect the implementation/API boundary

Have Claude Code identify these canonical surfaces:

```text
maxey0_ss/
  __init__.py
  system.py
  api/
  context/
  execution/
  runtimes/
  gating/
  observability/
  adapters/
  mcp_2026.py
```

Confirm that the canonical API is:

```python
from maxey0_ss import SuperSpaceSystem
```

and that `SuperSpaceSystem` is also available.

The old `SuperSpaceSystem` name is compatibility-only.

---

## STEP 3 — Inspect the existing MCP implementation before creating a Worker

Review:

```text
maxey0_ss/mcp_2026.py
maxey0_ss/mcp_public_server.py
maxey0_ss/mcp_server.py
```

Determine exactly which functionality is already implemented:

- `server/discover`
- `tools/list`
- `tools/call`
- `resources/list`
- `resources/read`
- `prompts/list`
- `Mcp-Method`
- `Mcp-Name`
- cache metadata
- explicit SCW addresses
- semantic gate interface
- trace metadata

Do not assume the existing FastAPI implementation is the final Cloudflare Worker implementation. Treat it as the current protocol/application reference surface.

---

## STEP 4 — Verify Claude Code's MCP connectivity tools

Run:

```bash
claude mcp list
```

Then inside Claude Code:

```text
/mcp
```

Confirm the Cloudflare integration is available before using it.

Do not modify Cloudflare resources yet.

---

## STEP 5 — Add Cloudflare documentation MCP to Claude Code

If it is not already configured:

```bash
claude mcp add --transport http cloudflare-docs https://docs.mcp.cloudflare.com/mcp
```

Then verify:

```bash
claude mcp list
```

Use the Cloudflare documentation MCP for Cloudflare-specific implementation questions rather than inventing configuration values.

---

## STEP 6 — Inspect Cloudflare account and domain configuration, read-only

Ask Claude Code to inspect the connected Cloudflare account and determine:

```text
Account
Workers access
Existing Worker projects
Existing routes
Existing custom domains
DNS zone for maxey0.com
Whether mcp.maxey0.com already exists
Existing secrets/bindings relevant to the deployment
```

No writes.

The intended production hostname is:

```text
https://mcp.maxey0.com/mcp
```

Do not create this hostname until the Worker exists and passes local/remote testing.

---

## STEP 7 — Design the Cloudflare adapter around Maxey0-SuperSpace

The target architecture is:

```text
Claude Code / MCP Client
          │
          ▼
Cloudflare Worker /mcp
          │
          ▼
MCP 2026-07-28 transport adapter
          │
          ▼
Maxey0-SuperSpace application API
          │
          ├── maxey0_ss context
          ├── maxey0_ss execution
          ├── SCW runtime
          ├── gates
          ├── provenance / observability
          └── A2A integration
```

The Worker is **not** the Maxey0-SuperSpace runtime.

Do not move the Python core into a JavaScript Worker merely to make the deployment convenient. Decide explicitly whether the first deployment is a Worker-native implementation of the required MCP surface or an edge adapter to a separately hosted application service.

---

## STEP 8 — Implement the new Cloudflare MCP server using the current stateless path

For a new Cloudflare remote MCP server, use the current stateless architecture:

```text
createMcpHandler()
@modelcontextprotocol/server
agents/mcp/server
/mcp
```

Do **not** start a new implementation with:

```text
McpAgent
WorkerTransport
legacy HTTP+SSE
```

unless an actual stateful legacy requirement is demonstrated.

The MCP protocol itself should not carry SCW state through `Mcp-Session-Id`. SCW/application state must be represented explicitly by application identifiers/handles and governed by Maxey0-SuperSpace.

---

## STEP 9 — Define the first production MCP surface

Do not expose the entire internal API initially.

Start with a minimal, auditable MCP surface such as:

```text
maxey0-ss.health
maxey0-ss.distribution
maxey0-ss.gate.inspect
maxey0-ss.scw.create
maxey0-ss.scw.describe
maxey0-ss.scw.close
maxey0-ss.observe
```

Every operation that requires an SCW must require an explicit SCW address/handle or otherwise have a documented admission rule.

Do not make discovery itself an authorization mechanism.

---

## STEP 10 — Preserve stateless protocol semantics

For every request, verify that the Worker does not depend on an MCP protocol session.

The implementation must remain compatible with:

```text
MCP 2026-07-28
Streamable HTTP
Mcp-Method
Mcp-Name
server/discover
```

Use application state only where Maxey0-SuperSpace requires it.

If multi-round interaction is later required, use the stateless MCP mechanisms rather than rebuilding the old persistent protocol-session model.

---

## STEP 11 — Local Worker test before any deployment

Run the Worker locally.

Use the repository's actual Worker command once its Worker adapter exists; normally this will be based on Wrangler:

```bash
npx wrangler dev
```

Do not deploy.

Verify:

```text
/mcp
server/discover
tools/list
tools/call
resources/list
resources/read
```

Also verify that an SCW-gated operation is rejected without a valid admission context.

---

## STEP 12 — Test with MCP Inspector

Run:

```bash
npx @modelcontextprotocol/inspector
```

Connect Inspector to the local `/mcp` endpoint.

Test in this order:

1. discovery
2. tool catalog
3. SCW creation
4. SCW description
5. gated operation
6. provenance/observation
7. SCW close

Record the request/response behavior.

---

## STEP 13 — Deploy only the first Worker to `workers.dev`

Only after local tests pass:

```bash
npx wrangler deploy
```

Do not attach the custom domain yet.

Verify the generated `workers.dev` endpoint using MCP Inspector.

Confirm that independent requests work without a protocol session and that application state is represented explicitly by Maxey0-SuperSpace state.

---

## STEP 14 — Attach `mcp.maxey0.com`

After the `workers.dev` deployment passes:

```text
mcp.maxey0.com
```

Configure the custom domain through Cloudflare.

The intended endpoint becomes:

```text
https://mcp.maxey0.com/mcp
```

Verify the route before connecting Claude Code.

Do not introduce DNS indirection that obscures the Worker route unless there is a specific infrastructure requirement.

---

## STEP 15 — Connect Claude Code to Maxey0-SuperSpace

Add the remote MCP server:

```bash
claude mcp add --transport http scw0 https://mcp.maxey0.com/mcp
```

Then:

```bash
claude mcp list
```

and inside Claude Code:

```text
/mcp
```

Confirm the server appears and discovery succeeds.

For a project-level configuration, use `.mcp.json` and commit only non-secret configuration.

Do not put Cloudflare API tokens, OAuth secrets, private keys, or other credentials into the repository.

---

## STEP 16 — Final production test

The final test should be performed **from Claude Code itself**.

Start with a real but safe test task and verify the complete path:

```text
Claude Code
    ↓
MCP 2026-07-28
    ↓
Cloudflare /mcp
    ↓
Maxey0-SuperSpace
    ↓
SCW creation/admission
    ↓
SCW-gated operation
    ↓
observable/provenance trail
    ↓
SCW termination
```

The test must demonstrate, at minimum:

- Claude Code can discover Maxey0-SuperSpace.
- The MCP transport is functioning without a protocol session dependency.
- An SCW can be explicitly addressed.
- A gated operation cannot bypass the SCW boundary.
- The operation produces an observable/provenance record.
- The SCW can terminate cleanly.
- The result can be traced back to the originating Claude Code task.
- No hidden model-context access is claimed or required.

Only after this test passes should the deployment be treated as the first production Maxey0-SuperSpace MCP integration.
