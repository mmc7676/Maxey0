# Cloudflare edge adapter

`workers/mcp-edge/` is the remote transport for `https://mcp.maxey0.com/mcp`.
It is a transport, not a second implementation.

## The boundary

| Layer | Owns |
|---|---|
| **Worker** | Header validation, `server/discover`, `tools/list`, `resources/list`, `resources/read` (incl. the MCP App), CORS, cache hints |
| **Origin (Python)** | Every `tools/call` — all 11 tools, and all SCW state |

**The Worker executes no tool.** Not even the seven deterministic ones. Running
`gate.inspect` at the edge would mean a second copy of Maxey0 semantics that
could drift from the core, and the whole point of `mcp_surface.py` is that no
transport owns behavior.

## The catalog is generated

```bash
python scripts/export_mcp_surface.py
```

Writes `workers/mcp-edge/src/generated/`:

- `surface.json` — tools, resources, artifact identity
- `super-space.html` — the MCP App, byte-identical to the origin's copy

`maxey0_ss/tests/test_edge_surface.py` fails if these fall behind
`maxey0_ss.mcp_surface`, so a tool added in Python cannot be silently missing
from the remote surface.

The HTML is exported with `newline=""`. Without it Python rewrites LF to CRLF on
Windows, the edge copy diverges from the origin by ~109 bytes, and the published
sha256 stops matching. `.gitattributes` marks the same files `-text` so a fresh
Windows clone does not reintroduce the problem.

## Without an origin

`MAXEY0_ORIGIN` is deliberately unset by default. A `tools/call` then returns:

```json
{"jsonrpc":"2.0","id":1,"error":{"code":-32010,
 "message":"Tool execution origin is not configured"}}
```

HTTP 503, and **no `result` field**. The edge refuses to fabricate a tool result
it cannot compute. An unreachable configured origin returns `-32011` / 502 for
the same reason.

This means the Worker is deployable and verifiable *before* an origin exists:
discovery, the catalog, and the MCP App all work from the edge alone.

## Deploy

```bash
cd workers/mcp-edge
npm install
npm run typecheck && npm test
npx wrangler deploy
```

First deploy gives a `*.workers.dev` URL. Verify:

```bash
curl https://maxey0-ss-mcp.<subdomain>.workers.dev/health
```

`app_artifact.kind` must read `built`.

### Attaching the custom domain

Only after the `maxey0.com` zone is **Active** in Cloudflare. Uncomment in
`wrangler.jsonc`:

```jsonc
"routes": [{ "pattern": "mcp.maxey0.com", "custom_domain": true }]
```

Cloudflare creates the DNS record and certificate. Do **not** pre-create a
`mcp.maxey0.com` CNAME — an existing record blocks the Custom Domain attach.

### Connecting the origin

```bash
wrangler secret put MAXEY0_ORIGIN
```

The Python core must be reachable at a public HTTPS URL; the Worker appends
`/mcp`. There is currently no such host: the core runs on localhost only, so
the deployed Worker is metadata-only and answers `-32010` for every
`tools/call`. See [VERIFICATION.md](VERIFICATION.md).

## Deployed

**The `workers.dev` URL below is retired.** Attaching the `mcp.maxey0.com`
custom domain route made Cloudflare disable the `workers.dev` route
automatically — it now 404s on every path. The table records the state at
first deploy, before the custom domain was attached; it is not reproducible
today. The live host is `https://mcp.maxey0.com/mcp`.

| Fact | Value |
|---|---|
| Worker | `maxey0-ss-mcp` |
| Account tag | `f06aa8586e094e9ea922658a979fe3ad` |
| Created | 2026-09-14T20:07:42Z |
| URL (retired) | `https://maxey0-ss-mcp.maxey0.workers.dev` |
| Upload | 464.54 KiB / gzip 133.07 KiB |
| Startup | 9 ms |
| Bindings | `MAXEY0_CATALOG_TTL="300"` — no `MAXEY0_ORIGIN` |

Confirmed independently: `workers_list` on the account returns this Worker,
where it previously returned an empty list.

The upload size matches the MCP App artifact, which is how you can tell the
464 KB bundle went up rather than a stub.

A newly created `workers.dev` subdomain serves a TLS alert
(`SEC_E_ILLEGAL_MESSAGE`) until Cloudflare issues its certificate, even though
DNS already resolves. That is expected for the first few minutes after
`wrangler deploy` creates the subdomain — it is not a Worker fault, and
`workers_list` confirming the Worker exists is the check that distinguishes the
two.

## Verifying a deployment

```bash
python scripts/verify_mcp_remote.py https://mcp.maxey0.com/mcp
```

Checks the 2026-07-28 contract over the wire: discovery, `initialize` rejection,
header enforcement, catalog, cache hints, App tool linkage, App artifact size
and identity, and whether tool execution reaches an origin. A metadata-only
deployment is reported, not failed — it is a valid state.

All 16 checks passed against the live endpoint (then `workers.dev`, before the
custom domain retired it) on 2026-09-14.

Note the script sets an explicit `User-Agent`. Cloudflare answers the bare
`Python-urllib/x.y` signature with HTTP 403 `error code: 1010`; the official MCP
SDKs (httpx, undici) are not affected. See VERIFICATION.md.

## Verified locally

Against real `workerd` via `wrangler dev`, with the Python origin live:

```
/health                     origin_configured: True | tools: 11
tools/call health     -> HTTP 200 | protocol 2026-07-28 | artifact built 463986
tools/call scw.create -> HTTP 200 | created: SCW-EDGE
observe_host_window   -> HTTP 403 | -32001 SCW address required
resources/read ui://  -> HTTP 200 | 463968 chars | sha b4a18845deb7e294
```

SCW state and the admission rule survive the edge hop unchanged. The App is
served from the edge with no origin round trip.

Unit tests: `workers/mcp-edge/test/edge.test.ts`, 20 tests.
