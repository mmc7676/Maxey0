# Fly.io deployment of the origin

Moves the Python origin off the maintainer's laptop and onto one Fly.io
Machine. Hostnames do not change: the edge Worker keeps serving
`https://mcp.maxey0.com/mcp` and forwarding `tools/call` to
`https://origin.maxey0.com`, and session clients keep using
`https://origin.maxey0.com/mcp/session`. Only what answers `origin.maxey0.com`
changes.

```
mcp.maxey0.com/mcp (Worker) ──> origin.maxey0.com ─┐
session clients ──────────────> origin.maxey0.com ─┴─> Cloudflare Tunnel
    ──> cloudflared ──> 127.0.0.1:8765 origin        (both in one Fly Machine)
```

| File | Role |
|---|---|
| `Dockerfile` | `python:3.11-slim-trixie`, deps from `pyproject.toml` pinned by `deploy/constraints.txt`, cloudflared 2026.9.1 checksum-verified, tini as init |
| `.dockerignore` | Keeps `.env`, `.env.*`, `config/credentials.json` and cloudflared credentials out of the build context |
| `deploy/entrypoint.sh` | Refuses unsafe configuration, starts the origin, waits for `/health`, starts cloudflared, exits if either dies |
| `fly.toml` | One Machine, one volume, no public service, restart always |

## Invariants

- **One Machine, one tunnel connector.** The attestation hash chain, MCP
  sessions and tasks live in memory. Two Machines, or a Fly Machine and the
  laptop both connected to the same tunnel, would have Cloudflare balance
  requests between two processes that each hold half the state. Deploy with
  `--ha=false`; `fly.toml` uses the in-place `rolling` strategy.
- **No Fly ingress.** `fly.toml` has no `[http_service]` or `[[services]]`, so
  the Machine has no public or Flycast address. The origin binds 127.0.0.1 and
  the only way in is the tunnel cloudflared dials out.
- **Fail closed.** The entrypoint refuses to start (exit 78, reason in
  `fly logs`) unless `MAXEY0_PUBLIC` is 1 and `MAXEY0_AUTH_MODE` is `bearer` or
  `oidc`; unless `TUNNEL_TOKEN` is set (`MAXEY0_TUNNEL=off` is for local smoke
  tests only); and unless `MAXEY0_HOST` is loopback while the tunnel is on.
- **Separate users.** The origin runs as `maxey0`, cloudflared as
  `cloudflared`, neither as root. The origin's environment has no
  `TUNNEL_TOKEN`, and a different uid cannot read cloudflared's.
- **State.** Only `SCW_HOME=/data/scw` (the Fly volume) outlives a restart. The
  core starts empty on every boot and every deploy.
- **Host planes are off.** The `observe.*` and gate tools answer from journals
  on the machine the origin runs on. A Fly Machine has none, and with
  `MAXEY0_PUBLIC=1` they report `available: false` unless
  `MAXEY0_PUBLIC_HOST_PLANES` is set. Leave it unset on Fly.

## Prerequisites

- `flyctl`, logged in (`fly auth login`) to an account with billing enabled.
- Cloudflare dashboard access to the `maxey0.com` zone and Zero Trust
  (Networks, Tunnels).
- This checkout, with the test suite green. The image serves
  `workers/mcp-edge/src/generated/super-space.html` as the MCP App, the same
  bytes the edge serves; if the App changed, run
  `python scripts/export_mcp_surface.py` first.

## One-time setup

1. Pick an app name and region and write them into `fly.toml` (`app`,
   `primary_region`). The shipped values are deliberately invalid.
2. Create the app and its volume. One volume means one Machine can mount it.

   ```
   fly apps create <app>
   fly volumes create maxey0_data --region <region> --size 1 -a <app>
   ```

3. In Cloudflare Zero Trust, Networks, Tunnels: create a **new** tunnel of type
   Cloudflared (remotely managed), for example `maxey0-origin-fly`. Copy its
   token from the install command shown (the long string after `--token`).
   **Do not add the `origin.maxey0.com` public hostname yet**; that is the
   cutover. A new tunnel rather than the laptop's `maxey0-origin` keeps the two
   separable: rollback is a DNS change, and no laptop connector can ever join
   the Fly tunnel by accident.
4. Mint one bearer token per caller. Each command prints the token once, and
   the `sha256:<hex>:<role>:<label>` entry to store:

   ```
   python scripts/mint_token.py --role operator --label claude-code
   ```

5. Store the secrets without deploying. `fly secrets import` reads
   `NAME=VALUE` lines from stdin, which keeps the tunnel token out of shell
   history:

   ```
   fly secrets import --stage -a <app>
   TUNNEL_TOKEN=<tunnel token>
   MAXEY0_MCP_TOKEN_HASHES=<entry>,<entry>
   ```

   (end stdin with Ctrl+Z Enter on Windows, Ctrl+D elsewhere). Add
   `MAXEY0_A2A_SHARED_SECRET` only if `/v1/a2a/message` is used, and a
   provider's API key only if a provider tool must run on the origin. Do
   **not** set `MAXEY0_MCP_TOKENS`: it holds tokens in plaintext.

## Deploy

```
fly deploy --ha=false -a <app>
fly status -a <app>          # exactly one Machine, state started
fly logs -a <app>
```

The logs should show `origin healthy`, `cloudflared started` and cloudflared
registering its connections. The tunnel shows Healthy in the dashboard while
serving no hostname. Check the origin from inside the Machine:

```
fly ssh console -a <app> -C "python -c \"import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8765/health').read())\""
```

## Cutover

The laptop must stop serving **before** the Fly tunnel serves the hostname.

1. On the laptop, stop `cloudflared tunnel run maxey0-origin`, then the origin
   (`maxey0-ss-public.exe`). Tool execution is down from here until step 3.
2. In Cloudflare DNS, delete the `origin` CNAME that points at the laptop
   tunnel (`<uuid>.cfargotunnel.com`). The dashboard will not add a public
   hostname over an existing record.
3. In the Fly tunnel, add the public hostname `origin.maxey0.com`, service
   `HTTP`, URL `localhost:8765`.
4. Run the verification below. The Worker needs no change: `MAXEY0_ORIGIN`
   still names `https://origin.maxey0.com`.

Nothing in memory migrates. Session clients reconnect, and callers switch to
their new tokens.

## Verification

```
python scripts/verify_mcp_remote.py https://mcp.maxey0.com
```

Protocol, catalog and App checks must pass, including the parity checks
against this checkout (tool names, version, App sha256). The script sends no
bearer token, and the Worker passes the origin's status through, so its two
`tools/call` checks report FAIL with HTTP 401 and the script exits 1: expected
under `bearer`, and itself evidence that the origin is reached and enforcing.
A 5xx there instead (502 with -32011, or Cloudflare's 530 passed through)
means the Worker is not reaching the origin through the tunnel.

Then authorization, with `TOKEN` set to a newly minted token and then to the
laptop's old plaintext token:

```
curl -s https://mcp.maxey0.com/mcp \
  -H "Content-Type: application/json" -H "MCP-Protocol-Version: 2026-07-28" \
  -H "Mcp-Method: tools/call" -H "Mcp-Name: maxey0-ss.auth.manifest" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"maxey0-ss.auth.manifest","arguments":{}}}'
```

| Token | Expected |
|---|---|
| new | 200; `admin_open: false`, `public_deployment: true`, `mode: "bearer"` |
| old laptop token | 401, -32001: it is not configured on Fly |
| none | 401, -32001 |

Finally, reconnect one session client to `https://origin.maxey0.com/mcp/session`
with a new token.

## Rollback

1. `fly machine stop <machine id> -a <app>` (the id is in `fly status`), so
   the Fly connector goes away. The volume and its state stay.
2. Remove the `origin.maxey0.com` public hostname from the Fly tunnel, and
   delete the `origin` CNAME in DNS if it remains.
3. On the laptop, point the hostname back at the old tunnel and start both
   processes as in the README:

   ```
   cloudflared tunnel route dns maxey0-origin origin.maxey0.com
   cloudflared tunnel run maxey0-origin
   ```

   (or re-add the `origin` CNAME to `<laptop tunnel uuid>.cfargotunnel.com` by
   hand), and `maxey0-ss-public.exe`. Callers already moved to new tokens need the
   same `MAXEY0_MCP_TOKEN_HASHES` entries in the laptop's `.env`.

Keep the laptop tunnel and its credentials until the Fly origin has run cleanly
for a while; rollback depends on them.

## Decommission the laptop tunnel

Once rollback is no longer wanted:

1. `cloudflared tunnel info maxey0-origin` shows no connectors, then
   `cloudflared tunnel delete maxey0-origin`.
2. Delete its credentials file (`~/.cloudflared/<tunnel uuid>.json`) and its
   `config.yml`. Delete `~/.cloudflared/cert.pem` too unless this machine
   manages other tunnels: it is an account-level credential.
3. Remove `MAXEY0_MCP_TOKENS` and `MAXEY0_MCP_DEFAULT_BEARER_TOKEN` from the
   laptop's `.env`. A token is revoked by being configured nowhere, and the
   old-token check above shows Fly never had it.

## Not verified

As prepared, before the first deploy:

- **No Fly deploy has run.** `flyctl` is not installed on the machine where
  these files were written, and there is no Fly account, app, volume or tunnel
  token there. `fly.toml` was checked against the Fly configuration reference
  and parsed with `tomllib`, not by `fly deploy`.
- **The image has not been built.** Docker Desktop failed to start on that
  machine, so no Dockerfile step has run. What was checked instead: the base
  tag exists; Debian trixie's package index puts `setpriv` in `util-linux` and
  `tini` at `/usr/bin/tini`; PyPI has a Linux x86_64 or pure wheel for every
  pinned runtime package; the cloudflared checksum is the one on the official
  release page, and GitHub's own asset digest agrees. The build re-checks the
  checksum.
- **The tunnel has never connected from a Machine.** Outbound QUIC from Fly,
  the tunnel's Healthy state and the hostname routing are untested.
- What was run: `tests/test_deploy_artifacts.py` (the refusal paths execute
  the real entrypoint), a syntax check under busybox `sh`, and the entrypoint's
  start, health-wait and supervision path under Git for Windows' `sh` against
  the origin running from a copy of the image layout, with the tunnel off:
  healthy start, `auth.manifest` 200 with a throwaway token and 401 without,
  the edge's App bytes served as `kind: "built"`, exit 0 on SIGTERM, exit 1
  when the origin dies or cannot start. Not on Linux, so without `setpriv`.
- `shared-cpu-1x` with 512 MB is an estimate; it has not been measured.
