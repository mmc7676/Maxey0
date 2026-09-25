# Verification

What this system's behavior actually is, measured rather than described. Every
block below is reproducible from a script in `scripts/`. The final section
records what is **not** verified, which is the part that matters most.

## Baseline

```
Python : 1109 passed, 1 skipped, 981 subtests passed
Worker :  52 passed (vitest), tsc --noEmit clean
Surface:  29 tools, 3 resources
```

`.venv/Scripts/python.exe -m pytest -q`, plus `npm run check` in `ui/`
and in `workers/mcp-edge/`. The `ui/` front end is optional -- the Studio
runs on the standard library alone -- and it had never been built or
tested in this environment before 0.3.0, which is how its package.json
kept version 0.7.2 while the product shipped 0.3.0. · Python 3.11.9 · fastapi 0.141.1,
mcp 1.30.0, pydantic 2.13.5, pytest 9.1.1. Measured at `0.3.0`.

The `Surface:` line is **checked**, not written down:
`tests/test_documented_counts.py` reads it back out of this file and compares
it to `build_surface()`. It said `26 tools` for one commit after the surface
gained a 27th, and the previous `Python : 439` line was stale by 150 tests —
a document that records measurements has to be measured too, or it becomes the
same kind of claim this page exists to argue against.

The two suite counts are not self-checking (a test that asserts its own suite's
size is a test that has to be edited every time a test is added, which trains
people to edit it without looking). They are what the chain below printed at the
commit named above; re-run it rather than trusting them.

The Python and Worker suites are independent. A change to the tool surface that
is not exported to the edge catalog fails the parity test rather than shipping a
catalog that disagrees with the origin.

## Transport behavior

The same surface is served over three transports. None of them owns behavior.

HTTP (`POST /mcp`), stateless, protocol `2026-07-28`:

| Request | Result |
|---|---|
| `initialize` | `404` / `-32601 Method not found` — correct for 2026-07-28 |
| `server/discover` | `200`, protocol `2026-07-28` |
| no routing headers | `400` / `-32600` |
| `tools/list` | `200`, `ttlMs=300000`, `cacheScope=server` |

There is no handshake and no `Mcp-Session-Id`. A client that expects one is
speaking an older protocol, and the `-32601` is the server saying so rather than
silently accepting.

stdio, driven by a real `ClientSession` (`scripts/verify_mcp_stdio.py`):

```
HANDSHAKE   : OK
serverInfo  : Maxey0-SuperSpace 1.0.0
health      : 2026-07-28
app artifact: built 463986 sha256 b4a18845deb7e294
ui resource : text/html;profile=mcp-app 463968 chars
GATE        : enforced -> SCW address must start with scw://
GATE        : valid address -> accepted
```

The gate bites on stdio exactly as it does over HTTP. A malformed SCW address is
refused on every transport, because admission is a property of the core.

## Edge adapter

Against real `workerd` via `wrangler dev`, Python origin live:

```
/health                     origin_configured: True
tools/call health     -> HTTP 200 | protocol 2026-07-28 | artifact built 463986
tools/call scw.create -> HTTP 200
observe_host_window   -> HTTP 403 | -32001 SCW address required
resources/read ui://  -> HTTP 200 | 463968 chars | sha b4a18845deb7e294
```

**The edge executes no tool.** With no origin configured, `tools/call` returns
`-32010` / HTTP 503 and **no `result` field**. It refuses to fabricate a result
it cannot compute, which is the only behavior that makes a metadata-only edge
safe to deploy.

## Live deployment

Measured against `https://maxey0-ss-mcp.maxey0.workers.dev`, before the
`mcp.maxey0.com` custom domain was attached. Attaching a custom domain route
makes Cloudflare disable the `workers.dev` route automatically — that host now
404s on every path. The current live host is `https://mcp.maxey0.com/mcp`; see
"Not verified" below. Verified over the wire, version `4c1049e0`:

```
TRANSPORT   /health 200
PROTOCOL    server/discover 200 | protocolVersion 2026-07-28 | serverInfo present
            MCP Apps extension advertised
            initialize rejected -32601 | headerless request refused 400
CATALOG     ttlMs 300000 | App tool linked | 3 resources
MCP APP     text/html;profile=mcp-app | 463968 chars | kind "built"
            sha256 b4a18845deb7e2943fe031384f29a1cf
EXECUTION   -32010 / 503, no result field when no origin is configured
```

Authorization measured over the same public URL with `MAXEY0_PUBLIC=1`:

| Call | Result |
|---|---|
| `maxey0-ss.health` | 200 |
| `maxey0-ss.scw.create` | `-32002` role 'public' lacks 'scw.create' |
| `maxey0-ss.gate.set_mode` | `-32002` role 'public' lacks 'gate.write' |
| `maxey0-ss.observe.events` | `-32002` role 'public' lacks 'observe' |

Reproduce with `python scripts/verify_mcp_remote.py <url>`.

Tool execution reached the core through a Cloudflare quick tunnel. That
hostname is **ephemeral** and changes on restart — a verification origin, never
a production one.

### Cloudflare blocks the bare urllib signature

`Python-urllib/3.11` receives **HTTP 403, `error code: 1010`** from the live
endpoint — a bot-signature block, not a server fault:

| Client | Result |
|---|---|
| `Python-urllib/3.11` (default) | **403** |
| `python-httpx/0.28.1` — MCP Python SDK | 200 |
| node/undici — MCP TypeScript SDK | 200 |
| empty or browser UA | 200 |

Real MCP clients are unaffected; both official SDKs use HTTP stacks that pass.
`verify_mcp_remote.py` sets an explicit User-Agent because of this. Worth
knowing before concluding a deployment is broken on the strength of a quick
`urllib` probe.

## Known duplication

433 files (5.8 MB) are duplicated across `plugins/` (297), `server/` (68) and
`skills/` (68). Each `plugins/maxey0*/` tree vendors a copy of `server/`.

This is the distribution packaging mechanism, not dead code — deleting it breaks
the plugin bundles. It is a genuine drift risk and worth a build step that
generates the vendored copies instead of storing them. That is a change of
approach rather than a cleanup, and it has not been made.

## Not verified

- **`https://mcp.maxey0.com/mcp`** — the custom domain is now attached and
  live; it is the production endpoint. Attaching it retired
  `https://maxey0-ss-mcp.maxey0.workers.dev` (Cloudflare disables the
  `workers.dev` route once a custom domain route is attached, confirmed via
  404), so the measurements above are historical and not reproducible against
  that host anymore.
- **An isolated origin.** Tool execution is live, served through the named
  tunnel `origin.maxey0.com` from a personal development laptop. The Fly.io
  image (`docs/FLY_DEPLOYMENT.md`) has **never been built or deployed**:
  Docker's backend failed to start here. Its entrypoint was run under `sh`
  only.
- **Per-client IPs for edge traffic: now verified.** On 2026-09-23, before
  the Worker set `x-real-ip`, a bad token sent directly to
  `origin.maxey0.com` was not locked out by bad tokens sent through
  `mcp.maxey0.com`, so edge callers were not keyed by their own IP. After the
  Worker was deployed (`forwards_client_ip: true` on `/health`), the same
  test was repeated on 2026-09-24 with the auth-failure limit set to 3. Four
  bad tokens through the edge got 401, 401, 401 and then 429, and a bad token
  sent directly to origin from the same machine also got 429: edge and direct
  traffic now share the caller's real IP as the key. A valid token got 200
  throughout.
  Still not verified: behavior with many real callers, and IPv6 clients.
- **Independent review coverage.** An adversarial review (4 reviewers, with
  each finding reproduced by a separate verifier) confirmed 7 defects in this
  change: 1 medium, 6 low. All 7 are fixed, with regression tests. The review
  is one pass, not an audit. A second, whole-codebase release pass then
  covered the SCW core, the tool surface and transports, the shipped plugins,
  and the web front ends. It confirmed 2 defects, both fixed: public
  `evidence.verify` returned an HTTP 500 on malformed records, and a
  maintainer's absolute path shipped in every plugin, which the release
  scanner now refuses. That pass was shallow: few tool calls per area.
  A third, deep pass split the SCW core and the shipped plugins into six
  narrow areas (containment, context, semantic runtime, Studio, gate hooks,
  packaging), with 187 tool calls. It confirmed 23 defects, each reproduced
  by a separate verifier: 3 high (Studio CSRF and DNS rebinding, gate
  searches without a path escaping enforce mode, chained commands matching a
  `bash_allow` grant), 10 medium and 10 low. All 23 are fixed, each with a
  regression test. `scripts/validate_plugin.py` now passes and runs as part
  of packaging.
- **Rendering in a live host** — requires a host to load the App resource.
- **OAuth / OIDC.** The verifier is implemented and unit-tested with an
  injected JWKS, and it has never been run against a real issuer. MCP clients
  cannot obtain tokens through this server: there is no RFC 9728 metadata and
  no `WWW-Authenticate` header (see `docs/AUTHORIZATION.md`). Only a
  misconfigured `oidc` mode returns 501.
- **The semantic gate** — `DisabledSemanticGate` is 22 lines. Gating is
  designed, not built.
- **The drift runtime** — 6 lines and a `pass`.
