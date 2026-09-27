# Changelog

## 0.3.2 — attestation records serialized

**Fixed**
- `AttestationLog.record()` read the chain head, digested against it and
  appended with no lock. The HTTP app runs handlers on a thread pool and
  `provider.complete`'s `async` mode on worker threads, so two records could
  chain to the same head. With `MAXEY0_ATTESTATION_PATH` set, the fsync between
  those steps made this routine: the chain failed verification and the file
  refused to load, so the next restart failed closed. A lock now covers the
  whole step. The in-memory default was affected only in principle; no forked
  chain was observed without persistence.

## 0.3.1 — on PyPI, and the gaps narrowed

The package is now `pip install maxey0`. Several items that 0.3.0 listed as
"not yet" are implemented; what remains is in the README under "What it is not
yet". 30 tools, 3 resources.

**Packaging**
- Distribution renamed to `maxey0` and published on PyPI. It installs two
  import packages: `maxey0`, a short front door (`from maxey0 import scw`, with
  `create`, `start`, `describe`, `close`, `drift`, `surface` and `reset`, plus
  `maxey0.SCWSpec` and `maxey0.SuperSpaceSystem`), and `maxey0_ss`, the
  implementation. Extras install as `pip install "maxey0[langchain]"`.
  Contributors still use `pip install -e .` from a clone.
- The Claude Code plugin's prerequisite is now `python -m pip install maxey0`.
- New console script `maxey0-verify` (also `scripts/verify_records.py`): a
  standard-library-only verifier for exported attestations, the plugin Gate
  journal and the context ledger. Exit codes: 0 verified, 1 not verified,
  2 unreadable.

**Windows and evidence**
- `maxey0-ss.scw.start` and `POST /v1/context/scws/{scw_id}/start` instantiate
  a specification (capability `scw.admit`). The owner is the authenticated
  caller, and a duplicate start is refused. MCP alone can now start a window.
- `maxey0-ss.evidence.verify` accepts `expected_head` and `expected_entries`,
  so records removed from the end are detected.
- `maxey0-ss.provider.complete` accepts `"async": true` and returns a `working`
  task handle at once; `tasks/get` returns the result later. In memory, per
  process.
- MCP and `/v1` share one drift store. Anchors and inspections are written to
  the attestation log as digests, never raw vectors. Vectors are still
  supplied by the caller, and the correction is still an advisory label.
- `MAXEY0_ATTESTATION_PATH` persists the attestation log as JSONL; it is
  reloaded and verified at startup, and a broken chain refuses to start.
  Persisted records are redacted before hashing. `MAXEY0_ATTESTATION_KEY_FILE`
  adds HMAC-SHA256 signatures, which prove integrity to key holders, not
  public authorship.
- `LangChainAdapter.callback_handler(system, scw_id)` and
  `OpenAIAgentsAdapter.install_trace_processor(system, scw_id)` record a
  framework's model and tool calls to the containment log as digests and
  lengths. They observe; they do not gate.

**Operations**
- `MAXEY0_ROOT_REACH`, `MAXEY0_MAX_DEPTH` and `MAXEY0_MAX_CHILDREN` bound the
  root window from the environment (unbounded by default; a malformed value
  refuses to start), reported under `root_bounds` by `maxey0-ss.deployment`.
- `MAXEY0_MCP_TOKEN_HASHES_FILE` is re-read about once a second, so tokens
  rotate without a restart.
- `MAXEY0_RATE_LIMIT_STORE=sqlite:<path>` keeps rate limits across restarts
  and shares them among processes on one host. The default is still in memory,
  per process.

**Removed**
- The advertised but unimplemented `deployment-secret-manager` binding.

## 0.3.0 — a live endpoint, hardened for what it is

`mcp.maxey0.com` serves tool execution: a Cloudflare Worker edge, then a named
tunnel, then a Python origin. This release makes that deployment's auth,
abuse limits and exposure honest and measured. What it still is not, above all
isolated from the development laptop it runs on, is listed in
`docs/AUTHORIZATION.md` under "Not implemented" and in `docs/VERIFICATION.md`
under "Not verified".

Baseline before the hardening work: 875 Python tests, 1 skipped. After: 1117+
Python tests, 52 Worker tests, tsc clean, 29 tools, 3 resources.

**Transports and identity**
- Session-based Streamable HTTP at `/mcp/session` for hosts that open a session
  (Claude Code, Claude Desktop), under the same Authorizer as `/mcp`.
- OIDC bearer verification (`maxey0_ss/auth/oidc.py`). The issuer, audience
  and JWKS come from configuration, never from the token. There is no RFC
  9728 metadata and no `WWW-Authenticate` yet, so MCP clients cannot obtain
  tokens through this server.
- Hashed per-caller bearer tokens, `MAXEY0_MCP_TOKEN_HASHES` (minted with
  `scripts/mint_token.py`). They are compared in constant time, and subjects
  carry a label, never token material.
- Fail closed on a malformed token entry, and on an unknown
  `MAXEY0_AUTH_MODE`, which used to fall through to `disabled`.

**Abuse limits**
- Origin rate limiter (`maxey0_ss/ratelimit.py`): per-client IP, per
  principal, session opens, and an auth-failure lockout that a valid
  credential always passes. A refusal is 429 with `Retry-After` and `-32005`.
- Caps: request bodies over 1 MiB get 413; at most 50 sessions, 600 s idle.
- The edge Worker forwards the client IP (`x-real-ip`), so edge callers are
  keyed by their own address. Verified live.

**Privacy of what Maxey0 records about its user**
- The gate journal (`~/.scw/gate.jsonl`), the runtime ledger
  (`~/.scw/events.jsonl`) and the gate's attribution state no longer persist
  personal data.
- Rules applied at the moment of writing:
  - a home folder, which names the user, is shortened to `~`;
  - transcript paths are dropped;
  - secret-shaped values are replaced with `[REDACTED:<kind>]`. That covers
    API keys, tokens, bearer headers, private keys and `password=...`.
- The gate still decides on the real values. Only the record is sanitized.
- Observe tools and Studio screens show shortened paths.
- A2A task text is stored as a digest, not verbatim.
- `tests/test_privacy.py` writes through each real path and checks what landed
  on disk.

**Exposure**
- On `MAXEY0_PUBLIC` deployments, the observe/gate tools no longer serve the
  host's own `~/.scw` journals or write its gate policy (opt in with
  `MAXEY0_PUBLIC_HOST_PLANES`). `/docs` and `/openapi.json` are not served.
- Capability alignment:
  - anchoring a drift baseline needs `scw.admit` on every transport;
  - REST close needs `scw.admit`, as MCP close does;
  - tasks are visible only to the principal that created them.

**Fixes found by review.** An adversarial review of the above confirmed 7
defects: 1 medium, 6 low. Whole-codebase release passes confirmed 25 more:
- 3 high: Studio CSRF and DNS rebinding; gate Grep/Glob without a path
  escaping enforce mode; `bash_allow` grants matching chained commands.
- 11 medium.
- 11 low.

Every one was reproduced before fixing, and all are fixed with regression
tests (see `docs/VERIFICATION.md`).

**Deployment and packaging**
- Fly.io artifacts (`Dockerfile`, `fly.toml`, `deploy/`,
  `docs/FLY_DEPLOYMENT.md`). The image has not been built or deployed yet.
- `mcp` is a core dependency, because the app imports it at load.

**Install and release fixes**
- An installed package works:
  - it now bundles `server/` and the MCP App, so `pip install` (from a clone or
    from git) serves all 29 tools and the App (it served 19 and crashed);
  - an installed package reads `.env` from the working directory.
- The built MCP App page is tracked in git, so a fresh clone serves it and its
  tests pass.
- Distribution targets:
  - the start commands are `maxey0-ss-public`, which actually serves;
  - installs come from git, since the package is not on PyPI;
  - `/.well-known/agent-card.json` is served.
- Server entry points: `maxey0-ss` and `maxey0-ss-api` turn uvicorn's proxy
  headers off, as `maxey0-ss-public` does, so the rate limiter's client address
  cannot be spoofed from loopback.
- Plugins:
  - `claude plugin validate` passes for every plugin: the `crosswindow` command
    frontmatter parsed as broken YAML;
  - the `scw-deployer` agent's `scw-default-deployer` skill now ships with it;
  - the Context plugin's listing says 32 tools, which it has.
- Intermittent test failures fixed. The suite passes repeatedly from a fresh
  clone.
- `docs/USER_GUIDE.md` and `docs/DEVELOPER_GUIDE.md` brought up to date with the
  current commands, servers and paths.
- The README is rewritten around what Maxey0 is for, the problem it solves and
  how to use it.

**Other**
- `config/roles.yaml` removed. No code read it.
- The test suite no longer rewrites the host's real gate policy file.

## 0.2.0-rc.1 — wiring the mechanisms that were connected to nothing

Release candidate. Deliberately numbered below 1.0.0: the 1.0.0 artifacts
shipped a set of controls that looked finished and were reachable from no call
path, and a version should not claim more than the build can show.

Baseline before this release, all executed: 589 Python tests + 151 subtests,
25 Worker tests, tsc clean, 26 tools, 3 resources, tree clean at `a31ee45`.
After: 694 Python tests + 312 subtests, 40 Worker tests, tsc clean, 27 tools.

### The recurring defect, in nine places

Each was built, documented, sometimes unit-tested, and consulted by nothing.
None produced an error, which is why they survived.

- **The application cache had no write path.** `MaxeyCache` was constructed,
  invalidated on `scw.close` and reported by `cache.status` — but `put` was
  never called, so no `CacheView` ever existed, `_entries` was permanently
  empty, `invalidate_scw` always dropped 0, and every metric published by
  `cache.status` was *structurally incapable* of being non-zero. Handlers are
  now wrapped once in `mcp_surface._wire_cache`, so both transports get it and
  neither can forget. `assert_cacheable`/`NEVER_CACHE` — a list of results that
  would be correctness bugs to cache, previously enforced at zero call sites —
  is the guard on that wrapping.
- **`maxey0-ss.gate.inspect` did not use the gate.** It returned a dict literal
  with `"allowed": True` and `"semantic_provider": "disabled"` hardcoded. It now
  routes through the configured provider and returns its real `GateDecision`.
- **`semantic_gate.provider` had no reader.** `settings.py` resolved it from the
  environment and `config/credentials.json`; nothing acted on the result.
  `select_semantic_gate()` is that reader, and both transports default to it.
  A named-but-unimplemented provider **fails closed**.
- **`config/credentials.json`'s `mcp` and `oauth` sections had no reader at
  all.** `AuthConfig` read the environment only, so an operator who followed the
  documented setup and filled in `oauth.client_secret` configured nothing and
  was not told. `AuthConfig.load()` reads them, environment first.
- **A credentials-file bearer token was loaded, reported, then rejected.**
  `_bearer_tokens()` read the environment variable rather than the resolved
  config, so authentication failed for a credential the system said it accepted.
- **`Authorizer.manifest()` had one caller, and it was a test.** The
  `auth.manifest` tool returned `AuthConfig.public_manifest()`, which omits
  `public_deployment` and `enforced` — so the single fact the deployment
  checklist turns on could not be read from the surface that exists to report
  it. It now returns the authorizer's manifest, with a new `admin_open` flag and
  a warning naming the fix.
- **`SCWSpec.isolation` and `SCWSpec.region_kinds` are removed.** Neither had a
  reader. `isolation` was a bool defaulting True that read as a containment
  switch on a system whose containment is structural and has no "off";
  `DEFAULT_CONSTITUTION["isolation"] = "fail-closed"` already carries the real
  declaration. `region_kinds` was a *required positional* passed
  `list(RegionKind)` at five sites and `[]` at four, with no difference between
  them. `RegionKind` went with it: it duplicated
  `scw_runtime.model.REGION_TYPES`, the one the Context plane actually builds
  regions with.
- **`SCWSpec.drift_threshold` stayed and got its reader.** It was the declared
  input to `SemanticRuntime.inspect`, a complete drift engine no transport
  called. New tool `maxey0-ss.scw.drift` anchors and measures, defaulting the
  threshold to the spec's own. An un-anchored window is refused, not answered
  `0.0`.
- **`SkillRecord.embedding` was written by the HTTP API and read by nothing**,
  while `ExecutionRouter` imported `weighted_semantic_distance`, never called
  it, and labeled a keyword match `"semantic match"` in its own `GateDecision`.
  The router now ranks on the embedding when one is comparable, and reports
  `source: "lexical"` when it did not.

### Packaging

- **Both builders had a secret-leak path.** `.gitignore` marks
  `config/credentials.json` as "Real secrets"; neither exclusion list held it,
  and both walked the filesystem rather than git. Latent, because only the
  `.example` existed. Inclusion is now derived from `git ls-files` in one place,
  `scripts/_packaging.py` — plus a denylist that catches a force-added file, and
  a scan of the bytes of every file about to be archived.
- **`.env` was matched by exact name**, so `.env.local` and `.env.production`
  were never excluded. Matched by prefix now; `.env.example` is the one that
  ships.
- **`maxey0_superspace.egg-info/` shipped in every source archive** — 906 files
  against 899 tracked — because `.egg-info` sat in a *file*-suffix set while
  naming a directory.
- **Nothing verified the generated plugin trees before packaging.** At `a31ee45`
  fifteen files under `plugins/**` had already drifted from `server/`, and every
  1.0.0 artifact shipped them. `build_package.py` now runs
  `build_planes.py --check` first and aborts on drift.
- **The built MCP App was in no archive.** `mcp_apps/super_space_react/dist/` is
  gitignored *and* was in the exclusion list, so every installed `.mcpb` served
  the unbuilt stub and reported `app_artifact.kind == "fallback-stub"` — which
  the deployment checklist lists as a **rollback trigger**. The packaging
  guaranteed the condition it rolls back for.
- **A dirty tree is a gate, not a label.** `build_source_archive.py` wrote
  `tree state : DIRTY` and then wrote the zip anyway. Both builders now refuse,
  with `--allow-dirty` as the explicit escape. This became load-bearing once
  contents are git-derived: an untracked file is *absent* from the archive.
- `server/_preflight.py` no longer prints `pip install -r
  "<plugin>/requirements.txt"`. No plugin tree has ever contained one, so the
  only command on the only start-up failure path named a file the reader could
  not open. It prints the package names from `_PACKAGES` instead, and
  `build_package.py`'s closing banner says the same.

### Edge adapter

- `MAXEY0_CATALOG_TTL=0` — the one value that turns caching off — was the one
  value that could not, because `0 * 1000` is falsy and fell through to 300 s.
  A negative was emitted to clients as `ttlMs: -5000`.
- `access-control-allow-origin: *` advertised `authorization` on the endpoint
  that proxies tool execution. Unset `MAXEY0_ALLOWED_ORIGINS` now answers `*`
  *without* advertising `authorization`; setting it echoes an allowlisted
  `Origin`, sets `Vary: Origin`, and advertises it.
- `Mcp-Name` was required-present and validated against nothing, while the
  comment above the check claimed this transport and the Python one "reject
  identically". It is now checked against the catalog, and header/body
  disagreement is refused as the Python adapter refuses it.
- `/health` reports the edge's own auth posture: it performs no authorization,
  forwards `authorization` verbatim, and says where to read the origin's half.

### Correctness

- `evidence.attestations` clamps `limit`. A negative inverted the slice —
  `limit=-5` yielded `records[5:]`, returning *more* than the cap from the
  containment-disclosure tool.
- `cache.status` derives its policy block from `CacheConfig` instead of
  returning the literals `300000` / `"server"`.
- `super_space_artifact()` is memoized on the bundle's `(mtime_ns, size)`. It
  read ~470 KB and computed a SHA-256 on every call to `health`, which is public
  and uncapability-gated. Keyed on the stat rather than a TTL, so a rebuild is
  reflected immediately.
- One version literal, `maxey0_ss.__version__`. Ten files declared `"1.0.0"`
  independently and the build compared three, so `server/discover` could report
  a version that disagreed with the surface.

### Configuration

- `.env.example` was missing six variables the code reads, including every
  `MAXEY0_CACHE_TTL_MS_*` and all three the edge Worker consumes.
  `tests/test_configuration.py` checks both directions: a variable the code
  reads and the file omits fails, and a variable the file declares that nothing
  reads fails too.
- `config/credentials.example.json` names the reader of every section, and the
  test resolves each named reader rather than trusting the claim.

### Known-shipping-with

`MAXEY0_AUTH_MODE=oidc` still refuses (-32004/501): 2026-07-28 requires RFC 9207
issuer validation, which this build does not implement. Every provider socket
except the semantic gate remains `implemented: false` and is reported as inert.
`mcp.maxey0.com` is now attached and live alongside
`maxey0-ss-mcp.maxey0.workers.dev`.


## 2026-09-13 — Maxey0-SuperSpace API refactor

- New repository identity: `Maxey0-SuperSpace`.
- Canonical Python package: `maxey0_ss`.
- Canonical system API: `SuperSpaceSystem`, with `Maxey0SuperSpace` and `Maxey0SS` aliases.
- Previous `Maxey0System` retained only as a compatibility alias.
- CLI names are `maxey0-ss`, `maxey0-ss-api`, and `maxey0-ss-public`.
- Public MCP identifiers use the `maxey0-ss` namespace.
- A2A canonical identity is `maxey0-ss` / `Maxey0-SuperSpace`.
- Existing Maxey0 plugin/vendor surfaces remain available as application/integration surfaces.
- No Cloudflare MCP server deployment is included in this release.


## 0.7.2 — the egress gate, and every install standing on its own

### `context_admit`: egress, where bridges and scope are ingress

**The remaining architectural gap.** Scope, bridges, and the Gate all decide
what a role may *reach*. None of them decided what a role's own output was
allowed to *become* once it existed — a maker's draft was either fully
visible through a declared handoff or not visible at all, because reach is
binary.

`context_admit(from_role, to_role, from_region, to_region, rule)` gates a
handoff the partition already declared, without minting new reach:
`approve` (unchanged), `summarize` (deterministically truncated, never an
invented summary), `redact` (named keys dropped), or `reject` (nothing
crosses). A real, authorized read of `from_region` happens under every rule,
including `reject` — the gate has to see what it is deciding about — and
every outcome is recorded as a `promote` event tagged `payload.gate ==
"admit"`, reusing the ledger's existing "content crossed a tier boundary
under a gate" event type rather than adding a new one to the vendored
runtime.

`context_assert_admitted(from_role, to_role)` makes the record checkable: it
finds every region the write/read closures say *could* carry a handoff
between the pair, and flags any with no recorded admission decision behind
it. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#egress-context_admit).

Two new tools, both on `maxey0-context` (the window is process-local state,
same reasoning as the other four assertions). **48 → 50 tools; the Context
plane, 30 → 32.**

### The differentiator sentence, made consistent

Four hand-written surfaces — `docs/LEXICON.md`, `docs/ARCHITECTURE.md`,
`README.md`, and `loops_menu`'s own output in `server/planes/menu.py` — carried
an earlier draft of the sentence that describes the product, missing
"primarily," "can," and the Oxford comma the canonical version uses. All four
now read identically. The plugin, marketplace, and Desktop manifest
descriptions (`plugin.json`, `marketplace.json`, `manifest.json`) previously
opened with prose describing what the product contains; they now open with
the sentence itself.

### A stale migration table, six tools misassigned

`docs/LEXICON.md` §3 dated from a draft of 0.7.0 in which the four containment
assertions and the two route tools still lived on `maxey0-observe` /
`maxey0-loops` under their bare legacy names (`observe_assert_can_read`,
`loops_bind`, `loops_formation_build`) — names the shipped catalog has never
registered. The per-plane headers (24/12/12) never matched the plane totals
(30/10/8) either, though both summed to the same 48. Both are fixed: the six
tools' rows moved to the Context section under their real names, and every
header now names the plane's actual tool count.

### The repository root is the marketplace now, not also a plugin

**The Contents tab, and a deeper problem it was a symptom of.** Through 0.7.1
`.claude-plugin/marketplace.json` listed the full-stack `maxey0` plugin with
`"source": "./"` — the bare repository root — so its installed file tree
recursively contained four other plugins' own `.claude-plugin/plugin.json`
manifests (`plugins/maxey0-context/`, `-loops/`, `-observe/`, `-lab/`) nested
inside it. No other marketplace checked against this one, including
Anthropic's own `claude-plugins-official`, ever does that; every plugin,
including ones bundled in the same repository as their marketplace, points at
a dedicated subdirectory.

The nesting was also downstream of a real functional bug, not just a display
one. Claude Code copies an installed plugin into an isolated cache directory
and documents that the copy cannot read a file outside itself — so the four
"install this plane alone" connectors, whose MCP servers were three-line
shims resolving `../../../server` back to the repository root, would fail
the moment someone installed one without also having the full repository
cloned alongside it. That directly contradicted what `docs/CONNECTORS.md` and
this file's own descriptions claimed about each plane being "useful alone."

Both are fixed the same way. `plugins/maxey0/` is now a generated, installable
unit exactly like the four connectors, and `scripts/build_planes.py` gives
**all five** — `maxey0`, `-context`, `-loops`, `-observe`, `-lab` — their own
complete copy of `server/` rather than a shim into the root. The repository
root now carries only `.claude-plugin/marketplace.json`; `.claude-plugin/
plugin.json` lives at `plugins/maxey0/`. Verified by copying each of
`plugins/maxey0/`, `plugins/maxey0-context/`, and `plugins/maxey0-observe/`
into an isolated temp directory with no sibling access to the rest of the
repository and confirming their MCP servers and Gate hook still build and run
from there. `maxey0-observe` also gained `hooks/hooks.json`, which it never
had — the Gate is a hook, not a server call, so an install of just the
Observatory plane had no Gate running at all despite its own documentation
already claiming it did.

### The Desktop bundle needs nothing installed by hand

`manifest.json` declared `server.type: "python"` with no bundled dependency
directory, while `requirements.txt` documented — correctly, at the time — that
`pydantic` is a compiled dependency the old bundled-Python MCPB type cannot
portably ship, and that an `.mcpb` install therefore needed one manual `pip
install -r requirements.txt` first. For someone with nothing already set up
but Claude Desktop itself, that manual step is the difference between the
bundle working and a `ModuleNotFoundError` on first launch.

MCPB 0.4 added a `uv` server type built for exactly this: dependencies
declared in `pyproject.toml`, installed by the host application itself, no
bundled platform-specific wheels and no user Python installation required.
`manifest_version` is now `0.4`, `server.type` is `uv`, and a `pyproject.toml`
pins the same `mcp` dependency `requirements.txt` already declared.
`requirements.txt` still applies to the three Claude Code connectors, which
run on whatever `python` your PATH resolves to and have no such runtime to
delegate to.

### Fixes

- **The Studio's "Sources" panel no longer prints raw `C:\Users\...` paths.**
  `maxey0_root`, `loops_json`, `scw_runtime`, and `event_log` now render
  relative to the plugin root, or `~`-relative for the default event log under
  the user's home; only a developer override that is neither prints absolute.
- **The concept count hooks report is now singular.** `session_notice.py`
  derived its concept list from `loops.json`'s `concept_tags`, which produced
  15 against the manifest's 16 (`knowledge` is tagged but not a manifest
  concept; `agentic-loops` and `registry` are manifest concepts with no
  tagged loop). It now reads the manifest directly, per the standing rule
  that a name has exactly one source.
- **`scripts/sync_vendor.py` resolves to a real path again.** `WORKSPACE =
  PLUGIN_ROOT.parents[1]` overshot by one directory level, landing on
  `Documents` — a comment above it described a nesting the plugin stopped
  using a while ago. Fixed to `PLUGIN_ROOT.parent`. The `scw-runtime` half of
  the vendor plan now resolves and the drift check runs against it for the
  first time in a long time; a false positive it immediately surfaced — CRLF
  vs. LF between a Windows checkout and a raw source directory — is now
  fixed at the source: digests normalize line endings before hashing. The
  `Maxey0/Maxey0` manifest-data half still does not resolve on this machine;
  see below. `--check` also now reports real drift on whatever it *can* check
  instead of aborting entirely the moment one source path is missing.
- **Removed a stale git worktree and its branch**, `.claude/worktrees/
  maxey0-plugin-updates-a64e41` on `claude/maxey0-plugin-updates-a64e41`
  (local and remote), pinned at an old v0.6.0 commit and already pushed —
  leftover state from an earlier session, unrelated to any of the above.

### Findings, not fixes

- **Startup outside the repo directory.** Timed directly rather than guessed
  at: a full connector cold-build (~0.9s) and a single Gate hook invocation
  (~150-200ms) show no measurable difference between a working directory
  inside this repo and an empty directory elsewhere. `matcher: "*"` on both
  `PreToolUse` and `PostToolUse` does confirm the named suspect fires twice
  per tool call regardless of location — real, compounding overhead on a busy
  turn, but not itself location-dependent. Whatever makes *outside* worse
  specifically was not reproduced from a shell; it most plausibly matches the
  `python`-resolution failure mode `docs/CONNECTORS.md` already documents
  (PATH resolution that can differ by working directory or launcher), but
  that is inference, not confirmation.
- **`scripts/sync_vendor.py`'s `Maxey0/Maxey0` upstream.** The path documented
  in `docs/DEVELOPER_GUIDE.md` (`<workspace>/Maxey0/Maxey0/manifest.json`) does not
  exist on this machine. One sibling directory's content is byte-identical to
  four of the six files already vendored here (`manifest.json`,
  `registry.json`, `team_mapping.csv`, `complexity-map.json`) — strong
  evidence it is the successor location — but it is explicitly out of bounds
  for import under this session's posture, so the path was left pointing at
  the documented (currently absent) location rather than repointed
  unilaterally. `--check` now reports this honestly as an absent source
  instead of silently skipping.

### Counts

| | 0.7.1 | 0.7.2 |
|---|---|---|
| tools | 48 | 50 |
| context-plane tools | 30 | 32 |
| tests (Python) | 274 | 281 |
| self-contained installable plugin directories | 4 | 5 |
| manifest_version (Desktop bundle) | 0.3 | 0.4 |

---

## 0.7.1 — one architecture

### Planes are not connectors

0.7.0 said "three planes, each a connector." That collapsed two different
decompositions into one and lost the plane Maxey0 does not own — the plane whose
absence is the entire differentiation.

> Most agent infrastructure adds capability to the **execution plane**. Maxey0
> makes the contextual environment surrounding agentic execution an
> independently structured, routable, partitionable and observable **plane**,
> and provides an **engineering plane** that observes and tunes both.

| plane | owner | connectors |
|---|---|---|
| **Execution** | the host | none — the Gate stands at its boundary, not inside it |
| **Context** | Maxey0 | `maxey0-context`, `maxey0-loops` |
| **Engineering** | Maxey0 | `maxey0-observe` |

`catalog.PLANES` now holds the three architectural planes, including Execution.
`catalog.CONNECTORS` (was `PLANES`) holds the three installable connectors, each
declaring the plane it serves. `Tool.plane` is `Tool.connector`. `/maxey0:menu`
reports both, and `menu planes` / `menu connectors` are separate sections.

### `context_assert_disjoint`: private, not disjoint

**A defect, found by testing the assertion against the product's own
formation.** It asserted `read_closure(a) ∩ read_closure(b) = ∅` and therefore
reported the shipped maker/checker/judge partition as a containment failure on
every pair — a checker is supposed to read the maker's draft, and every role is
supposed to read the concept's constitution.

Overlap is now classified rather than counted:

| class | fails |
|---|---|
| `private_overlap` — a `bridgeable=False` pad both roles reach | **yes** |
| `admitted` — one writes it, the other reads it; a declared handoff | no |
| `shared_reference` — no bound role can write it | no |

The third is the one worth stating: a read-only region is shared context
without being a channel. Contamination needs a writer.

An earlier draft of the fix excused a region inside either role's own subtree,
which excused the case that matters most — a role bound to a parent with
`descend` reaches every private pad beneath it. The negative control caught it.
Seven tests now cover the classification, including that breach.

### Also

- The React app gained a Planes view showing all three planes and the
  connector→plane mapping; `toolsForPlane` is `toolsFor`.
- Dropped the last of the register that sounds surprised the software works.

---

## 0.7.0 — three planes, one lexicon, and a product

**The final free production release.** Not a preview or a staging post: a
finished instrument for one concept and one formation. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for what is deliberately elsewhere,
and why each of those is a different product rather than a withheld feature.

0.6.0 was a working runtime wrapped in packaging that described how the code had
grown. This release is the packaging catching up with the engineering.

### The architecture is now three planes

Each is a separately installable connector with its own MCP server, commands and
skills. Each is useful alone. The Observatory can see the other two; neither of
the other two can see it.

| plane | connector | tools | alone |
|---|---|---|---|
| Context | `maxey0-context` | 30 | partitions and enforces, with no library and no Gate |
| Loop | `maxey0-loops` | 10 | routes against a fixed context scheme, holding no window state |
| Observatory | `maxey0-observe` | 8 | global workspace semantics for any session |

The boundary is not thematic. **The window is process-local state**, so every
tool that touches the live window lives on the Context plane — including the
four containment assertions and `context_route_bind` — and the Observatory reads
the ledger from disk, replaying it when it needs the region graph. That is how a
plane can see another plane without reaching into it.

`scripts/validate_plugin.py` and `tests/test_planes.py` now assert the Loop
plane opens no ledger, which is what makes its standalone claim checkable rather
than merely stated.

**Replaces** the two connectors named `maxey0` and `worlds`, whose names
corresponded to no boundary a user could act on: `maxey0_*`-prefixed tools were
registered on `worlds`, the Gate's control surface was fused into the
enforcement engine, and installing the engine without the loop library was not
an option the packaging offered.

### One lexicon, enforced

[docs/LEXICON.md](docs/LEXICON.md) is normative, and
`scripts/check_lexicon.py` fails the build when it drifts. It runs inside
`validate_plugin.py`, so a term that slips fails the same gate a broken import
does.

- **Every tool name begins with its plane.** All 46 tools renamed; 2 added. No
  aliases — an alias would double the surface and let the old vocabulary survive
  in transcripts, which is the drift this release exists to end. Full migration
  table in the lexicon.
- **`world` is retired entirely.** It had meant a bound region, a
  possible-worlds reasoning space, and a server name. `skills/worlds/` is now
  `skills/scw/`.
- **"Plane" means one thing**: a product plane, one of three. The five-level
  address model is now the **address strata**.
- **Commands renamed** to one verb each: `scw`→`window`, `loop`→`run`,
  `cross-window`→`crosswindow`, plus new `route`, `gate`, `assert`, `doctor`.
- **The nine Studio views are named once**, in `server/planes/catalog.py`, and
  every surface that lists them copies that table.

`server/planes/catalog.py` is the single source of truth: the servers register
from it, `loops_menu` renders from it, the TypeScript is generated from it, and
the checker enforces it.

### The menu is a tool, not a prompt

`/maxey0:menu` was 296 lines of prose instructing the model to render a table
the surface from a tool call, whose fallback when the call failed was the prose in
the file. With the connectors down it transcribed its own instructions and
appended a caveat — the exact failure it was written to prevent.

It is now `loops_menu`, a function over the catalog. The command file is 35
lines and says: call it, print what came back, stop.

### Skills have contents

All 16 concept skills were ~33-line stubs whose third step said to "read the
real skill via the Maxey0 knowledge base (`/<concept>/<concept>.md`)" — a path
that exists nowhere in the plugin. Every stub dead-ended its own instructions,
and the plugin UI's Contents tab had nothing to show.

Each concept now ships `SKILL.md` plus `reference/skills.md`,
`reference/loops.md` and `reference/agents.md`, rendered from the vendored
manifest. 68 files where there were 17.

### Four role agents, not two

`maxey0-maker`, `maxey0-checker`, `maxey0-judge`, `maxey0-role` — one per
position in the shipped formation. Through 0.6.0 every role was dispatched as
the same `subagent_type`, so `agent_type` could not distinguish them and the
`[[scw:role=…]]` marker carried the whole attribution load. The Gate now has a
second, independent attribution signal. All four are `model: inherit`.

### The Evidence view

Four HTTP routes existed, were documented, and were never fetched by the front
end: `/api/containment`, `/api/observability`, `/api/observability/attempts`. So
the containment assertions and the typed event stream had no surface at all.

The new **Evidence** view surfaces them, and exposes `access_matrix` — which
probes every (role, region) pair with a **real read** and was reachable from
nowhere. It reports `closure_disagreements`: cells where the computation and the
attempt disagree, which is a defect in one of them and which nothing in the
product had ever compared before.

It replaces the **Experiment** view; the harness moves to `maxey0-lab`.

### The experiment harness left the product

`docs/ROADMAP.md` has said since 0.3.0 that experiment protocol, conditions,
probes and analysis belong in a consumer repository — and the plugin shipped
`/maxey0:experiment-run`, an Experiment view, six HTTP routes and four workload
specs anyway. A measurement instrument that ships the study it was used for is a
lab notebook with an installer.

The code is intact, in the `maxey0-lab` connector, listed in the marketplace as
research tooling. Nothing in the three planes depends on it.

### npm, TypeScript and React

`ui/` is an optional, additive front end. `python server/run_studio.py` still
serves the Studio on a bare Python 3.10+ with no `npm install`, and that promise
is worth more than a uniform stack.

What it adds is a **typed boundary against the catalog**:
`scripts/generate_ui_types.py` emits `ui/src/generated/catalog.ts`, so renaming
a tool in Python becomes a compile error in TypeScript. Two distinctions are
enforced by the type system — `Contained` is `boolean | null` because null means
nothing was attempted, and `StreamResponse` is a union because the endpoint
returns a count in one shape and a list in the other.

### Fixes

- **The vendored runtime can no longer be silently shadowed.** An editable
  install elsewhere on the machine registers a `MetaPathFinder`, and
  `sys.meta_path` is consulted before `sys.path` — so the plugin ran code it did
  not ship while every drift check passed. `bootstrap.prepare()` removes those
  finders unless `SCW_RUNTIME_SRC` is set, and `/maxey0:doctor` reports which
  copy actually loaded.
- **Archives no longer ship a second copy of the repository.** A `git worktree`
  under `.claude/` was included in every build, so `maxey0-0.6.0.mcpb` contained
  each documentation file twice, from two different commits.
- **A ledger that cannot be opened now says so.** The Context plane opens
  `~/.scw/events.jsonl` while starting, so a failure there killed the process
  during import and the host reported `CONNECTION_CLOSED` with nothing else. It
  now names the path, the cause, and the variable that fixes it.
- **The Loop plane no longer opens a ledger** to borrow one decorator from the
  runtime's session module.
- **Directory requests resolve to their index**, so the built front end serves
  at `/app/`.
- **The event stream renders both response shapes.** Reading the summary's
  `events` count as a list rendered "no events" over a run that had hundreds.
- **Every command declares `allowed-tools`**, checked against the catalog, so
  the plugin UI has something real to show.

### Not found

There is **no Haiku model anywhere in this repository**, and there never has
been. Verified across the source tree, the built archives, and the full git
history. The only model identifier in the product is `claude-sonnet-5`, a single
env-overridable default (`MAXEY0_MODEL`) used only by the Studio's optional
Anthropic client, and only when `ANTHROPIC_API_KEY` is set. The role agents are
`model: inherit`.

### Counts

| | 0.6.0 | 0.7.0 |
|---|---|---|
| connectors | 2 | 3, plus 2 more marketplace entries |
| tools | 46 | 48 |
| commands | 6 | 9 |
| role agents | 2 | 4 |
| skill files | 17 | 68 |
| tests | 240 | 261 |
| docs enforcing one lexicon | 0 | all of them |

---

## 0.6.0 — the Gate

Measure the agents, not just the runtime. See
[docs/ROADMAP.md](docs/ROADMAP.md) for 0.6.0 and earlier.


- Added explicit Autograph / Non-Autograph classification.
- Added explicit Insert / Base Set classification with parallel separation.
- Added pricing-evaluation SCW.
- Added deterministic Maxey0 composite grading using four condition dimensions.
- Added final nine-card release run with SCW log and hashed provenance.
- Added ChatGPT-oriented MCP distribution surface.
