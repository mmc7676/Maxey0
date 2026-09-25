/**
 * What the edge tells the origin about the caller, and what it tells the caller
 * about the origin's answer.
 *
 * Both directions were narrower than the origin's per-IP limiter needs. The
 * upstream request carried no client address, so the limiter could not tell
 * one caller from another; and the rebuilt response dropped `Retry-After`, so a
 * throttled client was told "429" with no backoff. The allowlists stay
 * allowlists: a client-supplied `x-real-ip` or `X-Forwarded-For` would let a
 * caller pick its own limiter bucket, and an origin header nobody named is
 * still not the edge's to repeat.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import worker, { type Env } from "../src/index";
import catalog from "../src/generated/surface.json";

const V = "2026-07-28";
const MCP = "https://mcp.example.test/mcp";
const KNOWN = catalog.tools[0].name;
const ORIGIN: Env = { MAXEY0_ORIGIN: "https://origin.example.invalid" };

function toolCall(headers: Record<string, string> = {}, env: Env = ORIGIN) {
  return worker.fetch(
    new Request(MCP, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "MCP-Protocol-Version": V,
        "Mcp-Method": "tools/call",
        "Mcp-Name": KNOWN,
        ...headers,
      },
      body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: KNOWN } }),
    }),
    env,
  );
}

/** Stub the origin: record every upstream request, answer with `reply`. */
function origin(reply: () => Response = () => new Response(
  JSON.stringify({ jsonrpc: "2.0", id: 1, result: { ok: true } }),
  { status: 200, headers: { "content-type": "application/json" } },
)): Request[] {
  const seen: Request[] = [];
  vi.stubGlobal("fetch", async (req: Request) => {
    seen.push(req);
    return reply();
  });
  return seen;
}

afterEach(() => vi.unstubAllGlobals());

describe("the caller's address reaches the origin's limiter", () => {
  it("sets x-real-ip from CF-Connecting-IP", async () => {
    const seen = origin();
    await toolCall({ "CF-Connecting-IP": "203.0.113.7" });
    expect(seen).toHaveLength(1);
    expect(seen[0].headers.get("x-real-ip")).toBe("203.0.113.7");
  });

  it("forwards an IPv6 caller unchanged", async () => {
    const seen = origin();
    await toolCall({ "CF-Connecting-IP": "2001:db8::7" });
    expect(seen[0].headers.get("x-real-ip")).toBe("2001:db8::7");
  });

  it("never forwards a client-supplied x-real-ip or X-Forwarded-For", async () => {
    const seen = origin();
    await toolCall({
      "CF-Connecting-IP": "203.0.113.7",
      "x-real-ip": "198.51.100.1",
      "X-Forwarded-For": "198.51.100.2, 198.51.100.3",
    });
    // The Cloudflare-observed address wins; the caller's claims go nowhere.
    expect(seen[0].headers.get("x-real-ip")).toBe("203.0.113.7");
    expect(seen[0].headers.get("x-forwarded-for")).toBeNull();
  });

  it("sets no x-real-ip when CF-Connecting-IP is absent, as under wrangler dev", async () => {
    const seen = origin();
    await toolCall({ "x-real-ip": "198.51.100.1", "X-Forwarded-For": "198.51.100.2" });
    expect(seen).toHaveLength(1);
    expect(seen[0].headers.get("x-real-ip")).toBeNull();
    expect(seen[0].headers.get("x-forwarded-for")).toBeNull();
  });

  it("drops a CF-Connecting-IP that is not an IP address", async () => {
    for (const bogus of ["", "not-an-ip", "256.1.1.1", "1.2.3", "::1]@evil.example", "fe80::1%eth0"]) {
      const seen = origin();
      await toolCall({ "CF-Connecting-IP": bogus });
      expect(seen[0].headers.get("x-real-ip"), bogus).toBeNull();
      vi.unstubAllGlobals();
    }
  });

  it("does the same for every method it forwards, not only tools/call", async () => {
    for (const [method, params, name] of [
      ["tasks/get", { taskId: "t1" }, "t1"],
      ["subscriptions/listen", { notifications: { taskIds: ["t1"] } }, undefined],
    ] as const) {
      const seen = origin();
      await worker.fetch(
        new Request(MCP, {
          method: "POST",
          headers: {
            "content-type": "application/json",
            "MCP-Protocol-Version": V,
            "Mcp-Method": method,
            ...(name ? { "Mcp-Name": name } : {}),
            "CF-Connecting-IP": "203.0.113.9",
            "x-real-ip": "198.51.100.1",
          },
          body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
        }),
        ORIGIN,
      );
      expect(seen[0].headers.get("x-real-ip"), method).toBe("203.0.113.9");
      vi.unstubAllGlobals();
    }
  });
});

describe("the origin's answer reaches the caller", () => {
  it("passes Retry-After through on a 429", async () => {
    origin(() => new Response(
      JSON.stringify({ jsonrpc: "2.0", id: 1, error: { code: -32000, message: "rate limited" } }),
      { status: 429, headers: { "content-type": "application/json", "Retry-After": "17" } },
    ));
    const res = await toolCall({ "CF-Connecting-IP": "203.0.113.7" });
    expect(res.status).toBe(429);
    expect(res.headers.get("retry-after")).toBe("17");
    expect((await res.json() as any).error.message).toBe("rate limited");
  });

  it("passes WWW-Authenticate through on a 401", async () => {
    const challenge = 'Bearer resource_metadata="https://origin.example.invalid/.well-known/oauth-protected-resource"';
    origin(() => new Response("{}", {
      status: 401, headers: { "content-type": "application/json", "WWW-Authenticate": challenge },
    }));
    const res = await toolCall();
    expect(res.status).toBe(401);
    expect(res.headers.get("www-authenticate")).toBe(challenge);
  });

  it("still drops every origin header nobody named", async () => {
    origin(() => new Response("{}", {
      status: 429,
      headers: {
        "content-type": "application/json",
        "Retry-After": "5",
        server: "uvicorn",
        "set-cookie": "session=abc",
        "x-origin-internal": "fly-iad-1",
      },
    }));
    const res = await toolCall();
    expect(res.headers.get("retry-after")).toBe("5");
    expect(res.headers.get("server")).toBeNull();
    expect(res.headers.get("set-cookie")).toBeNull();
    expect(res.headers.get("x-origin-internal")).toBeNull();
    // The origin's content-type is not echoed either; the edge states its own.
    expect(res.headers.get("content-type")).toBe("application/json");
  });

  it("adds no Retry-After of its own when the origin sent none", async () => {
    origin();
    const res = await toolCall();
    expect(res.status).toBe(200);
    expect(res.headers.get("retry-after")).toBeNull();
    expect(res.headers.get("www-authenticate")).toBeNull();
  });

  it("exposes both headers to browser script under either CORS policy", async () => {
    for (const env of [ORIGIN, { ...ORIGIN, MAXEY0_ALLOWED_ORIGINS: "https://app.example.invalid" }]) {
      origin();
      const res = await toolCall({ Origin: "https://app.example.invalid" }, env);
      const exposed = (res.headers.get("access-control-expose-headers") ?? "").split(/,\s*/);
      expect(exposed).toEqual(expect.arrayContaining(["retry-after", "www-authenticate"]));
      vi.unstubAllGlobals();
    }
  });
});

describe("/health states what the edge forwards", () => {
  it("says it forwards the client IP and which origin headers it passes back", async () => {
    const body = await (await worker.fetch(
      new Request("https://mcp.example.test/health"), {},
    )).json() as any;
    expect(body.forwards_client_ip).toBe(true);
    expect(body.client_ip).toMatch(/CF-Connecting-IP/);
    expect(body.client_ip).toMatch(/never forwarded/);
    expect(body.origin_response_headers).toEqual(["retry-after", "www-authenticate"]);
  });
});
