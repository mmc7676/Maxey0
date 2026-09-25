# Maxey0-SuperSpace documentation

Generated from the implementation and from results reproduced in this
repository. Where something was not verified, it says so.

| Document | Covers |
|---|---|
| [MCP_PROCESS_BOUNDARY.md](MCP_PROCESS_BOUNDARY.md) | What SCW0–SCW3 actually are, why there is one core and three transports, the tool/resource surface, admission |
| [MCP_SERVERS.md](MCP_SERVERS.md) | Setup, building the App, running stdio and HTTP servers, `.mcp.json`, troubleshooting |
| [MCP_APP.md](MCP_APP.md) | `ui://maxey0-ss/super-space.html` — source → build → artifact → registration → tool linkage → identity |
| [EDGE_DEPLOYMENT.md](EDGE_DEPLOYMENT.md) | The Cloudflare Worker: edge/origin boundary, generated catalog, deploy and custom-domain steps |
| [SCW0.md](SCW0.md) | When to deploy a window, the hierarchy invariant, and the swarm question answered |
| [CONTAINMENT.md](CONTAINMENT.md) | Enforcement as a swappable provider, hash-chained attestations, and what publishing the engine does or does not require |
| [AUTHORIZATION.md](AUTHORIZATION.md) | Tool capability tiers, auth modes, the MAXEY0_PUBLIC fail-closed switch, hashed bearer tokens, OIDC, rate limiting, live posture |
| [TASKS.md](TASKS.md) | MCP Tasks extension (SEP-2663) — methods, statuses, the Mcp-Name routing rule, per-transport support |
| [VERIFICATION.md](VERIFICATION.md) | The baseline, measured transport and edge behavior, and what is *not* verified |
| [CACHING.md](CACHING.md) | Namespaced cache, per-model identity, semantic-plane and SCW isolation, invalidation, configuration, metrics, and what must never be cached |

Repository-level documents in `docs/` (architecture, authorization, gate,
lexicon, public surface) describe the wider Maxey0 system and predate this work.
`docs/MCP_2026_07_28.md` in the roadmap repository is the protocol contract this
implementation targets.

## The five facts worth knowing first

1. **SCW0–SCW3 are application state, not processes.** One core, two transports.
   See [MCP_PROCESS_BOUNDARY.md](MCP_PROCESS_BOUNDARY.md).

2. **MCP 2026-07-28 has no handshake.** The public HTTP adapter answers
   `server/discover` and rejects `initialize`. That is the contract. The stdio
   transport exists because session-based hosts still need one.

3. **The MCP App must be built.** `dist/` is gitignored; without
   `npm run build` the server silently serves a stub. Check
   `maxey0-ss.app.artifact` reports `kind: "built"`.

4. **Set `MAXEY0_PUBLIC=1` on anything internet-reachable.** Without it an
   unconfigured deployment treats every caller as admin. With it, unauthenticated
   callers get the public read-only tier. See [AUTHORIZATION.md](AUTHORIZATION.md).

5. **The edge executes no tool.** The Worker serves MCP metadata and the App;
   every `tools/call` goes to the Python origin. With no origin configured it
   returns `-32010` rather than a fabricated result.
