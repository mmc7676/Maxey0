# Authorization and the tool tiers

## The exposure this closes

An edge deployed with `mode=disabled, configured=false` is unauthenticated. The
moment `MAXEY0_ORIGIN` points at a reachable core, `scw.create`, `scw.close` and
the gate-mode writes are callable by anyone who can resolve the hostname. The
tiers below exist so that state cannot happen silently.

## Every tool declares what it requires

`Tool.capability` — `None` means public. Enforcement happens in
`maxey0_ss/auth/policy.py`, **before the SCW gate and before any handler runs**.
An unauthorized caller must not reach either.

| Tier | Capability | Tools |
|---|---|---|
| **public** | `None` | health, distribution, auth.manifest, cache.status, app.artifact, tasks.status, gate.inspect, super_space |
| **observe** | `observe` | observe.events, observe.attempts, observe.traces, observe.gate_activity, observe.gate_mode, observe.isolation_level, observe.studio, maxey0-ss.scw.observe_host_window |
| **read state** | `scw.read` | scw.describe |
| **write state** | `scw.create`, `scw.admit` | scw.create, scw.start, scw.close |
| **gate** | `gate.write` | gate.set_mode, gate.set_policy, gate.declare_isolation |

**`gate.write` is admin-only by construction.** No role in `auth/roles.py` holds
it except admin's wildcard. Turning the Gate off removes containment
enforcement, which is the most destructive operation on this surface, so it is
not reachable by a shared token.

## Modes

`MAXEY0_AUTH_MODE`:

| Mode | Behavior |
|---|---|
| `disabled` *(default)* | Trusted local deployment. Every caller is admin — this is what keeps a developer install and the stdio transport working unchanged. |
| `bearer` | `Authorization: Bearer <token>`. Per-caller tokens live in `MAXEY0_MCP_TOKEN_HASHES` as `sha256:<hex>:<role>:<label>` (mint with `scripts/mint_token.py`), so the origin never holds the plaintext. `MAXEY0_MCP_TOKENS` / the default token are still accepted for migration and warned about on public deployments. Every entry is compared in constant time; any malformed entry refuses every request with `-32004`/501. Over HTTP there is no anonymous tier in this mode: a call without a token is 401, public tools included. |
| `oidc` | JWT verified against configured issuer, audience and JWKS. See below. |
| anything else | Refuses with `-32004`/501. It used to fall through to `disabled`. |

### The fail-closed switch

```bash
MAXEY0_PUBLIC=1
```

Set this on anything reachable from the internet. With it, `disabled` no longer
grants admin: an unauthenticated caller gets the **public read-only tier only**.
Without it, a public deployment with unconfigured auth is an open surface.

Historical: measured on the retired workers.dev host under `disabled` +
`MAXEY0_PUBLIC=1`. The current bearer posture is under "Live posture" below.

```
maxey0-ss.health        -> 200
maxey0-ss.scw.create    -> -32002  role 'public' does not hold 'scw.create'
maxey0-ss.gate.set_mode -> -32002  role 'public' does not hold 'gate.write'
maxey0-ss.observe.events-> -32002  role 'public' does not hold 'observe'
```

### A shared token is not an admin

`MAXEY0_MCP_DEFAULT_BEARER_TOKEN` maps to `operator`, not `admin`. One shared
secret in a config file should not be able to disable the Gate.

### oidc: implemented as a resource server, not usable by Claude clients yet

`maxey0_ss/auth/oidc.py` verifies RS256/384/512 and ES256/384 JWTs. The
issuer, audience and JWKS URL all come from configuration, never from the
token, and the issuer is checked before any key is selected. That is the
resource-server analogue of RFC 9207's issuer binding, not RFC 9207 itself.
`exp` and `sub` are required, with 60 s leeway.

- **Key set:** JWKS is cached for 300 s. An unknown `kid` forces at most one
  refresh per 30 s. If refresh fails, the last good key set is served for up
  to 24 h.
- **Roles:** the role comes from `MAXEY0_OIDC_ROLE_CLAIM`, matched by exact
  key first and then as a dotted path. A list resolves to the most
  privileged known role.
- **Failures:** misconfiguration refuses with `-32004`/501.

Unit-tested with an injected JWKS; **never run against a real issuer.** Still
absent, so no MCP client can obtain a token through this server:
- RFC 9728 protected-resource metadata
- `WWW-Authenticate` on 401
- a real 401 (instead of HTTP 200 `isError`) on `/mcp/session`
- multi-audience
- any OAuth flow, CIMD or DCR

Tokens have to come from out of band.

### Host planes on public deployments

With `MAXEY0_PUBLIC` set, the observe/gate bridge tools that read the host's
own journals return `available: false`. The ones that write gate policy
refuse. `MAXEY0_PUBLIC_HOST_PLANES=1` opts back in; without it, a public
server never exposes the journals of the machine it runs on.

`scw.drift` with `anchor=true` requires `scw.admit`; measuring stays on
`scw.read`.

### Rate limiting and request caps

`maxey0_ss/ratelimit.py` is outermost ASGI middleware covering `/mcp`,
`/mcp/session`, `/v1` and A2A. It has four limits:
- per client IP (120/min)
- per principal (300/min)
- session opens (6/min)
- auth-failure lockout: 20 rejected credentials per hour per client

A refusal is 429 with `Retry-After` and `-32005`. The client IP is
`CF-Connecting-IP`, trusted only from `MAXEY0_TRUSTED_PROXY_IPS`.

Request caps:
- request bodies over 1 MiB get 413
- at most 50 sessions, with a 600 s idle timeout

Limits and caps are on automatically when `MAXEY0_PUBLIC` is set or auth is
enabled. On public deployments `/docs` and `/openapi.json` are not served.
By default limits are per process and in memory, so they reset on restart.
`MAXEY0_RATE_LIMIT_STORE=sqlite:<path>` keeps them in one SQLite file instead:
they survive a restart and are shared by every process on the host that names
the same file. They are still not shared across hosts.

### Other settings

| Variable | Effect |
|---|---|
| `MAXEY0_MCP_TOKEN_HASHES_FILE` | A file of hashed token entries, one per line, in the same format as `MAXEY0_MCP_TOKEN_HASHES`. It is re-read about once a second, so tokens can be rotated without a restart. |
| `MAXEY0_ATTESTATION_PATH` | Persists the attestation log as JSONL. The file is reloaded and verified at startup; a broken chain refuses to start. Records are redacted before they are hashed. |
| `MAXEY0_ATTESTATION_KEY_FILE` | Adds an HMAC-SHA256 signature to each attestation record. It proves integrity to whoever holds the key, not public authorship. |
| `MAXEY0_ROOT_REACH`, `MAXEY0_MAX_DEPTH`, `MAXEY0_MAX_CHILDREN` | Bound the root window SCW0: a comma-separated list of SCW IDs it may reach, the maximum depth and the maximum number of children. Unset means unbounded. A malformed value refuses to start. `maxey0-ss.deployment` reports them under `root_bounds`. |

### Live posture (measured 2026-09-23 against the hosted edge and origin)

| Call | Result |
|---|---|
| no token, `scw.describe` | 401 `-32001` |
| rotated-out token, `scw.create` / `scw.describe` | 401 `-32001` |
| current hashed token, `scw.describe` | 200 |
| current token (operator), `scw.create` | 403 `-32002` |
| `auth.manifest` | `token_storage: hashed`, `token_config_errors: 0`, `admin_open: false`, rate limit enabled |
| `observe.gate_activity` | 200, `available: false` |
| `GET /docs`, `/openapi.json` | 404 |

## Ordering

```
protocol headers -> authorization -> SCW admission -> semantic gate -> handler
```

`test_authorization_precedes_the_scw_gate` asserts this: an unauthorized caller
sending a malformed SCW address gets `-32002` (capability denied), never
`-32001` (which would mean it reached the gate).

## Not implemented

- MCP-client OAuth (see the oidc section). No identity provider is configured.
- Per-tenant isolation. Roles are global; there is no tenant dimension.
- A limiter shared across hosts. `MAXEY0_RATE_LIMIT_STORE=sqlite:<path>`
  shares limits among processes on one host only.
- Secrets manager, unless the host provides one.
  The token hash lives in `.env` or `MAXEY0_MCP_TOKEN_HASHES_FILE`, and the
  hash is not sensitive. The plaintext token lives only on the client side.
- A security audit. One adversarial review pass ran; its 7 reproduced
  findings are fixed (see `docs/VERIFICATION.md`).
