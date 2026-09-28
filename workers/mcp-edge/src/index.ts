/**
 * Maxey0-SuperSpace MCP 2026-07-28 edge adapter.
 *
 * This Worker is a transport, not a second implementation. It answers the
 * metadata half of the protocol from a catalog generated out of the Python
 * `maxey0_ss.mcp_surface`, and forwards every `tools/call` to the origin that
 * owns tool execution and SCW state.
 *
 * It deliberately executes no tool — not even the deterministic ones. Running
 * `gate.inspect` at the edge would mean a second copy of Maxey0 semantics that
 * could drift from the core. Metadata here, execution at origin.
 */
import catalog from "./generated/surface.json";
import superSpaceHtml from "./generated/super-space.html";

export interface Env {
  /** Base URL of the Python origin, e.g. https://origin.example.com. Unset = metadata-only. */
  MAXEY0_ORIGIN?: string;
  /** Seconds the edge may cache catalog responses. "0" means do not cache. */
  MAXEY0_CATALOG_TTL?: string;
  /**
   * Comma-separated browser origins allowed to call this endpoint, e.g.
   * "https://app.example.com,https://studio.example.com". "*" is accepted and
   * means what it says. Unset is the safe default -- see `corsHeaders`.
   */
  MAXEY0_ALLOWED_ORIGINS?: string;
  /** Optional build identifier reported by /health, e.g. the deployed commit SHA. */
  MAXEY0_BUILD_ID?: string;
}

/** Every tool name the catalog declares. Built once per isolate. */
const TOOL_NAMES: ReadonlySet<string> = new Set(catalog.tools.map((t) => t.name));

const PROTOCOL = catalog.protocolVersion;
const JSONRPC = "2.0";
const DEFAULT_TTL_MS = 300_000;

/**
 * SEP-2663 task methods. Tasks are durable state owned by the origin, so the
 * edge forwards them exactly as it forwards tools/call. Answering them here
 * would mean two task stores that disagree.
 */
const TASK_METHODS = ["tasks/get", "tasks/update", "tasks/cancel"] as const;
const SUBSCRIBE_METHOD = "subscriptions/listen";

type Json = Record<string, unknown>;

const ok = (id: unknown, result: unknown): Json => ({ jsonrpc: JSONRPC, id, result });

const err = (id: unknown, code: number, message: string, data?: unknown): Json => ({
  jsonrpc: JSONRPC,
  id,
  error: data === undefined ? { code, message } : { code, message, data },
});

function json(
  body: Json,
  status = 200,
  ctx: { request?: Request; env?: Env } = {},
  extra: HeadersInit = {},
): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json",
      ...corsHeaders(ctx.request, ctx.env),
      ...extra,
    },
  });
}

/** `{build}` when MAXEY0_BUILD_ID is a plain identifier; otherwise nothing. */
function buildId(env: Env): { build?: string } {
  const raw = (env.MAXEY0_BUILD_ID ?? "").trim();
  return /^[0-9A-Za-z._+-]{1,64}$/.test(raw) ? { build: raw } : {};
}

/** Headers every caller needs, whatever the origin policy. */
const BASE_CORS_HEADERS = "content-type, mcp-protocol-version, mcp-method, mcp-name";

/**
 * Origin response headers passed back to the caller, and the only ones.
 *
 * The forwarded response is rebuilt with content-type and CORS alone, which
 * also dropped two headers that belong to the protocol rather than to the
 * origin's internals: `Retry-After` on a 429 from the origin's per-IP limiter
 * -- without it a client has no backoff and retries straight back into the
 * limit -- and `WWW-Authenticate` on a 401, which is where an OAuth-protected
 * MCP server tells a client how to obtain a token. Everything else the origin
 * sets (server banners, cookies, tunnel and hosting headers) stays dropped:
 * the edge's response is the edge's contract, not a window onto the origin.
 */
const PASSTHROUGH_RESPONSE_HEADERS = ["retry-after", "www-authenticate"] as const;

/**
 * Browsers hide every non-safelisted response header from script unless it is
 * exposed, so a passed-through header a browser client cannot read would be
 * passed through for non-browser clients only.
 */
const EXPOSED_HEADERS = PASSTHROUGH_RESPONSE_HEADERS.join(", ");

const IPV4 = /^(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}$/;

function isIpAddress(value: string): boolean {
  if (IPV4.test(value)) return true;
  // Restrict the alphabet before handing the value to the URL parser, so it
  // sees an address and nothing else (no `]`, `/`, `@` or `%zone` that would
  // let a different host parse), then let it apply the IPv6 grammar.
  if (!value.includes(":") || !/^[0-9A-Fa-f:.]+$/.test(value)) return false;
  try {
    new URL(`http://[${value}]/`);
    return true;
  } catch {
    return false;
  }
}

/**
 * The caller's address, forwarded to the origin as `x-real-ip`.
 *
 * The upstream request is a new request built from an allowlist of headers,
 * so what the origin learns about the caller's address is decided here, and
 * the origin's per-IP rate limiter can only key on what arrives. Cloudflare
 * documents that for a same-zone Worker subrequest the origin's
 * `CF-Connecting-IP` reflects the `x-real-ip` the Worker sets:
 * https://developers.cloudflare.com/fundamentals/reference/http-headers/#cf-connecting-ip-in-worker-subrequests
 * The edge hostname and the origin hostname share one zone, which is
 * the case relied on here. Cross-zone, Cloudflare replaces the value with a
 * fixed Worker address and every caller lands in one limiter bucket, so an
 * origin moved to another zone needs this revisited, not only re-pointed.
 *
 * The value is taken from the incoming `CF-Connecting-IP`, which Cloudflare
 * sets on the request entering the Worker. A client-supplied `x-real-ip` or
 * `X-Forwarded-For` is never read and never forwarded: honouring either would
 * let a caller choose its own limiter bucket, which switches the limit off for
 * anyone willing to rotate a header. Cloudflare also requires the value to be
 * a syntactically valid IP address
 * (https://developers.cloudflare.com/rules/transform/request-header-modification/),
 * so anything else is dropped. When the header is absent -- `wrangler dev`, a
 * unit test -- no `x-real-ip` is set at all, rather than a placeholder the
 * origin would count as one shared client.
 */
function clientIp(request: Request): string | null {
  const ip = (request.headers.get("CF-Connecting-IP") ?? "").trim();
  return isIpAddress(ip) ? ip : null;
}

/**
 * CORS for a governed surface.
 *
 * The old headers paired `access-control-allow-origin: "*"` with an
 * `access-control-allow-headers` that advertised `authorization`, on the
 * endpoint that proxies tool execution. That combination tells any web page on
 * any origin that it may send this endpoint a bearer token from the user's
 * browser.
 *
 * Both remedies the audit named are implemented, and the safe one is default:
 *
 * - `MAXEY0_ALLOWED_ORIGINS` set -- the request's `Origin` is echoed back when
 *   it is on the list, `Vary: Origin` is set so a cache cannot serve one
 *   origin's response to another, and `authorization` is advertised. This is
 *   what a browser client with credentials needs.
 * - unset -- wildcard origin, and `authorization` is *not* advertised. Any
 *   caller may read the public catalog; no browser may attach credentials to
 *   it. Non-browser MCP clients are unaffected either way, because CORS is
 *   enforced by browsers and by nothing else.
 *
 * `authorization` is still forwarded verbatim when a request carries it. This
 * governs what a *browser* is told it may send, not what the edge accepts.
 *
 * `access-control-expose-headers` is the same in both modes: which response
 * headers script may read is not a credential question.
 */
function corsHeaders(request?: Request, env?: Env): Record<string, string> {
  const configured = (env?.MAXEY0_ALLOWED_ORIGINS ?? "").trim();
  if (configured === "") {
    return {
      "access-control-allow-origin": "*",
      "access-control-allow-methods": "POST, OPTIONS",
      "access-control-allow-headers": BASE_CORS_HEADERS,
      "access-control-expose-headers": EXPOSED_HEADERS,
      "access-control-max-age": "86400",
    };
  }

  const allowed = configured.split(",").map((o) => o.trim()).filter(Boolean);
  const origin = request?.headers.get("Origin") ?? "";
  const wildcard = allowed.includes("*");
  const match = wildcard ? "*" : allowed.includes(origin) ? origin : "";

  const headers: Record<string, string> = {
    "access-control-allow-methods": "POST, OPTIONS",
    "access-control-allow-headers": `${BASE_CORS_HEADERS}, authorization`,
    "access-control-expose-headers": EXPOSED_HEADERS,
    "access-control-max-age": "86400",
    vary: "Origin",
  };
  if (match) headers["access-control-allow-origin"] = match;
  return headers;
}

function cacheHint(ttlMs: number): Json {
  return { ttlMs, cacheScope: "server" };
}

/**
 * Catalog TTL in milliseconds.
 *
 * Was `Number(env.MAXEY0_CATALOG_TTL ?? "") * 1000 || DEFAULT_TTL_MS`, which
 * had a defect on either side of the `||`. `"0"` -- a deliberate request for
 * no caching -- multiplies to 0, which is falsy, so it silently became 300 s:
 * the one value an operator sets to turn caching off was the one value that
 * could not. And a negative passed straight through, so `"-5"` was emitted to
 * clients as `ttlMs: -5000` in the cache hint.
 *
 * Parsed explicitly instead: fall back only when unset or unparseable, and
 * clamp a negative to 0 rather than publishing it.
 */
function catalogTtlMs(env: Env): number {
  const raw = (env.MAXEY0_CATALOG_TTL ?? "").trim();
  if (raw === "") return DEFAULT_TTL_MS;
  const seconds = Number(raw);
  if (!Number.isFinite(seconds)) return DEFAULT_TTL_MS;
  return Math.max(0, Math.trunc(seconds * 1000));
}

/** Resource bodies the edge is allowed to serve. */
function readResource(uri: string): { mimeType: string; text: string } | null {
  const meta = catalog.resources.find((r) => r.uri === uri);
  if (!meta) return null;
  if (uri === catalog.superSpaceUri) {
    return { mimeType: meta.mimeType, text: superSpaceHtml };
  }
  const value = (catalog.staticResources as Record<string, unknown>)[uri];
  if (value === undefined) return null;
  return {
    mimeType: meta.mimeType,
    text: typeof value === "string" ? value : JSON.stringify(value),
  };
}

/** Forward a tools/call to the origin verbatim, preserving MCP routing headers. */
async function proxyToOrigin(request: Request, env: Env, body: Json, id: unknown, method: string, routeName?: string): Promise<Response> {
  const ctx = { request, env };
  const origin = env.MAXEY0_ORIGIN?.replace(/\/+$/, "");
  if (!origin) {
    return json(
      err(
        id,
        -32010,
        "Tool execution origin is not configured",
        {
          reason:
            "This edge adapter serves MCP metadata only. Tool execution and task state " +
            "belong to the Maxey0-SuperSpace Python core, reachable at MAXEY0_ORIGIN.",
          method,
          configure: "wrangler secret put MAXEY0_ORIGIN  (or set a var in wrangler.jsonc)",
        },
      ),
      503,
      ctx,
    );
  }

  const name = routeName ?? (body.params as Json | undefined)?.name ?? request.headers.get("Mcp-Name");
  const ip = clientIp(request);
  const upstream = new Request(`${origin}/mcp`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "MCP-Protocol-Version": PROTOCOL,
      "Mcp-Method": method,
      ...(typeof name === "string" ? { "Mcp-Name": name } : {}),
      ...(request.headers.get("authorization")
        ? { authorization: request.headers.get("authorization")! }
        : {}),
      ...(ip ? { "x-real-ip": ip } : {}),
    },
    body: JSON.stringify(body),
  });

  try {
    const res = await fetch(upstream);
    const text = await res.text();
    const passthrough: Record<string, string> = {};
    for (const header of PASSTHROUGH_RESPONSE_HEADERS) {
      const value = res.headers.get(header);
      if (value !== null) passthrough[header] = value;
    }
    return new Response(text, {
      status: res.status,
      headers: {
        "content-type": "application/json",
        ...passthrough,
        ...corsHeaders(request, env),
      },
    });
  } catch (e) {
    return json(
      err(id, -32011, "Origin unreachable", { origin, detail: String(e).slice(0, 200) }),
      502,
      ctx,
    );
  }
}

async function handleMcp(request: Request, env: Env): Promise<Response> {
  const ctx = { request, env };
  // 2026-07-28 Streamable HTTP routing headers. Same validation order as the
  // Python adapter so the two transports reject identically.
  const protocol = request.headers.get("MCP-Protocol-Version");
  const methodHeader = request.headers.get("Mcp-Method");
  const nameHeader = request.headers.get("Mcp-Name");

  if (protocol !== PROTOCOL) {
    return json(err(null, -32600, "Unsupported MCP protocol version", { expected: PROTOCOL }), 400, ctx);
  }
  if (!methodHeader) {
    return json(err(null, -32600, "Missing Mcp-Method header"), 400, ctx);
  }
  if (methodHeader === "tools/call" && !nameHeader) {
    return json(err(null, -32600, "Missing Mcp-Name header for tools/call"), 400, ctx);
  }
  // `Mcp-Name` was required-present and never checked against anything, so any
  // string forwarded to origin. `docs/MCP_2026_ARCHITECTURE.md` states that
  // "Mcp-Method and Mcp-Name are treated as early routing signals. Maxey0 can
  // reject header/body disagreement before invoking a tool", and the Python
  // adapter does exactly that (`Mcp-Name must equal params.name`). The comment
  // directly above claims these two transports "reject identically"; until
  // 0.2.0 they did not. This is a routing check, not an authorization one -- no
  // Maxey0 semantics are evaluated here, only whether the name is one the
  // catalog this Worker was generated from declares.
  if (methodHeader === "tools/call" && nameHeader && !TOOL_NAMES.has(nameHeader)) {
    return json(
      err(null, -32602, `Unknown tool: ${nameHeader}`, { header: "Mcp-Name" }),
      400,
      ctx,
    );
  }
  if ((TASK_METHODS as readonly string[]).includes(methodHeader) && !nameHeader) {
    return json(err(null, -32600, `Missing Mcp-Name header for ${methodHeader}; it must carry params.taskId`), 400, ctx);
  }

  let body: Json;
  try {
    body = (await request.json()) as Json;
  } catch {
    return json(err(null, -32700, "Parse error"), 400, ctx);
  }

  const id = body.id ?? null;
  const method = body.method;
  const params = (body.params as Json) ?? {};

  if (method !== methodHeader) {
    return json(err(id, -32600, "Mcp-Method does not match JSON-RPC method"), 400, ctx);
  }
  if (method === "tools/call") {
    const bodyName = params.name;
    if (typeof bodyName === "string" && bodyName !== nameHeader) {
      return json(
        err(id, -32600, "Mcp-Name must equal params.name", {
          header: nameHeader,
          name: bodyName,
        }),
        400,
        ctx,
      );
    }
  }

  const ttlMs = catalogTtlMs(env);

  switch (method) {
    case "server/discover":
      return json(
        ok(id, {
          protocolVersion: PROTOCOL,
          serverInfo: { name: catalog.serverName, version: catalog.serverVersion },
          capabilities: {
            tools: {},
            resources: {},
            prompts: {},
            extensions: {
              "io.modelcontextprotocol/tasks": {},
              "io.modelcontextprotocol/ui": {},
            },
          },
        }),
        200,
        ctx,
      );

    case "tools/list":
      return json(ok(id, { tools: catalog.tools, ...cacheHint(ttlMs) }), 200, ctx);

    case "resources/list":
      return json(ok(id, { resources: catalog.resources, ...cacheHint(ttlMs) }), 200, ctx);

    case "resources/read": {
      const uri = params.uri as string | undefined;
      const found = uri ? readResource(uri) : null;
      if (!found) {
        return json(err(id, -32602, `Unknown resource: ${uri}`), 400, ctx);
      }
      const meta = catalog.resources.find((r) => r.uri === uri);
      return json(
        ok(id, {
          contents: [
            {
              uri,
              mimeType: found.mimeType,
              text: found.text,
              ...((meta as Json | undefined)?._meta ? { _meta: (meta as Json)._meta } : {}),
            },
          ],
          ...cacheHint(ttlMs),
        }),
        200,
        ctx,
      );
    }

    case "prompts/list":
      return json(ok(id, { prompts: [], ...cacheHint(ttlMs) }), 200, ctx);

    case "tools/call":
      return proxyToOrigin(request, env, body, id, "tools/call");

    // SEP-2663: Mcp-Name must carry params.taskId so intermediaries route a
    // task to the instance that holds it. Enforced here before forwarding.
    case "tasks/get":
    case "tasks/update":
    case "tasks/cancel": {
      const taskId = params.taskId as string | undefined;
      if (!taskId) {
        return json(err(id, -32602, "taskId is required"), 400, ctx);
      }
      if (nameHeader !== taskId) {
        return json(err(id, -32600, "Mcp-Name must equal params.taskId", { header: nameHeader, taskId }), 400, ctx);
      }
      return proxyToOrigin(request, env, body, id, method, taskId);
    }

    case SUBSCRIBE_METHOD:
      return proxyToOrigin(request, env, body, id, SUBSCRIBE_METHOD);

    default:
      return json(err(id, -32601, `Method not found: ${method}`), 404, ctx);
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders(request, env) });
    }

    // Operational probe. Not part of the MCP contract; safe to GET.
    if (url.pathname === "/health" && request.method === "GET") {
      return json({
        ok: true,
        service: "maxey0-ss-edge",
        version: catalog.serverVersion,
        ...buildId(env),
        mcp_protocol: PROTOCOL,
        tools: catalog.tools.length,
        resources: catalog.resources.length,
        app_artifact: catalog.artifact,
        origin_configured: Boolean(env.MAXEY0_ORIGIN),
        // The composition risk, stated by the half that knows its own half.
        // This Worker performs no authorization by design: `authorization` is
        // forwarded verbatim and terminated at origin. So an origin running
        // MAXEY0_AUTH_MODE=disabled without MAXEY0_PUBLIC=1 -- which treats
        // every caller as admin -- is unauthenticated admin over the internet
        // once this edge is reachable. The edge cannot observe the origin's
        // posture; it can and now does say that it contributes none of its
        // own, and where to read the other half.
        edge_authorizes: false,
        authorization: "forwarded verbatim; terminated at origin",
        origin_auth_posture: "call maxey0-ss.auth.manifest at the origin; "
          + "admin_open must be false on any internet-reachable deployment",
        // The same statement for the other forwarded header the origin makes
        // a decision on: its per-IP limiter keys on the address this edge
        // sends, so an operator reading a limiter bucket needs to know where
        // that address came from.
        forwards_client_ip: true,
        client_ip: "x-real-ip set from CF-Connecting-IP when Cloudflare supplies one; "
          + "client-supplied x-real-ip and x-forwarded-for are never forwarded",
        origin_response_headers: [...PASSTHROUGH_RESPONSE_HEADERS],
        cors_allowed_origins: (env.MAXEY0_ALLOWED_ORIGINS ?? "").trim() || "*",
        cors_advertises_authorization:
          (env.MAXEY0_ALLOWED_ORIGINS ?? "").trim() !== "",
      }, 200, { request, env });
    }

    if (url.pathname === "/mcp") {
      if (request.method !== "POST") {
        // A browser GET lands here. 405 is the correct answer for an MCP
        // Streamable HTTP endpoint; the body says where the status probe is.
        return json(
          err(null, -32600, "MCP endpoint accepts POST (Streamable HTTP)", {
            endpoint: "/mcp", transport: "streamable-http", health: "/health",
          }),
          405,
          { request, env },
        );
      }
      return handleMcp(request, env);
    }

    return json(
      err(null, -32601, "Not found", { endpoint: "/mcp", health: "/health" }),
      404,
      { request, env },
    );
  },
};
