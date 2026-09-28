/**
 * Edge defects found by static review and fixed in 0.2.0.
 *
 * Three of them, each the same shape as the ones on the Python side: a control
 * that exists, is configurable, and does not do what reading it suggests.
 *
 *  - `MAXEY0_CATALOG_TTL=0` -- the one value that turns caching off -- was the
 *    one value that could not, because `0 * 1000` is falsy.
 *  - `access-control-allow-origin: *` advertised `authorization` on the
 *    endpoint that proxies tool execution.
 *  - `Mcp-Name` was required-present and validated against nothing, while the
 *    comment above the check claimed this transport and the Python one "reject
 *    identically" and the architecture doc claimed early routing rejection.
 */
import { describe, expect, it } from "vitest";
import worker, { type Env } from "../src/index";
import catalog from "../src/generated/surface.json";

const V = "2026-07-28";
const MCP = "https://mcp.example.test/mcp";
const KNOWN = catalog.tools[0].name;

function call(method: string, params: unknown = {}, opts: {
  env?: Env;
  headers?: Record<string, string>;
} = {}) {
  return worker.fetch(
    new Request(MCP, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "MCP-Protocol-Version": V,
        "Mcp-Method": method,
        ...opts.headers,
      },
      body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
    }),
    opts.env ?? {},
  );
}

describe("catalog TTL", () => {
  it("honours a deliberate zero instead of silently using 300s", async () => {
    const body = await (await call("tools/list", {}, {
      env: { MAXEY0_CATALOG_TTL: "0" },
    })).json() as any;
    expect(body.result.ttlMs).toBe(0);
  });

  it("never emits a negative ttl to clients", async () => {
    const body = await (await call("tools/list", {}, {
      env: { MAXEY0_CATALOG_TTL: "-5" },
    })).json() as any;
    expect(body.result.ttlMs).toBe(0);
    expect(body.result.ttlMs).toBeGreaterThanOrEqual(0);
  });

  it("falls back to the default when unset or unparseable", async () => {
    for (const env of [{}, { MAXEY0_CATALOG_TTL: "" }, { MAXEY0_CATALOG_TTL: "abc" }]) {
      const body = await (await call("tools/list", {}, { env })).json() as any;
      expect(body.result.ttlMs).toBe(300_000);
    }
  });

  it("converts seconds to milliseconds", async () => {
    const body = await (await call("tools/list", {}, {
      env: { MAXEY0_CATALOG_TTL: "60" },
    })).json() as any;
    expect(body.result.ttlMs).toBe(60_000);
  });
});

describe("CORS on a governed surface", () => {
  it("does not advertise authorization under a wildcard origin", async () => {
    const res = await call("tools/list");
    expect(res.headers.get("access-control-allow-origin")).toBe("*");
    expect(res.headers.get("access-control-allow-headers")).not.toContain("authorization");
  });

  it("advertises authorization only to an allowlisted origin", async () => {
    const env = { MAXEY0_ALLOWED_ORIGINS: "https://app.example.invalid" };
    const res = await call("tools/list", {}, {
      env, headers: { Origin: "https://app.example.invalid" },
    });
    expect(res.headers.get("access-control-allow-origin")).toBe("https://app.example.invalid");
    expect(res.headers.get("access-control-allow-headers")).toContain("authorization");
    expect(res.headers.get("vary")).toBe("Origin");
  });

  it("omits the allow-origin header entirely for an origin not on the list", async () => {
    const res = await call("tools/list", {}, {
      env: { MAXEY0_ALLOWED_ORIGINS: "https://app.example.invalid" },
      headers: { Origin: "https://evil.example.invalid" },
    });
    expect(res.headers.get("access-control-allow-origin")).toBeNull();
  });

  it("still applies the policy to preflight", async () => {
    const res = await worker.fetch(
      new Request(MCP, { method: "OPTIONS", headers: { Origin: "https://app.example.invalid" } }),
      { MAXEY0_ALLOWED_ORIGINS: "https://app.example.invalid" },
    );
    expect(res.status).toBe(204);
    expect(res.headers.get("access-control-allow-origin")).toBe("https://app.example.invalid");
  });

  it("accepts an explicit wildcard in the allowlist as meaning what it says", async () => {
    const res = await call("tools/list", {}, {
      env: { MAXEY0_ALLOWED_ORIGINS: "*" }, headers: { Origin: "https://any.example.invalid" },
    });
    expect(res.headers.get("access-control-allow-origin")).toBe("*");
  });
});

describe("Mcp-Name routing", () => {
  it("rejects a tool name the catalog does not declare", async () => {
    const res = await call("tools/call", { name: "not.a.tool" }, {
      headers: { "Mcp-Name": "not.a.tool" },
      env: { MAXEY0_ORIGIN: "https://origin.example.invalid" },
    });
    expect(res.status).toBe(400);
    const body = await res.json() as any;
    expect(body.error.code).toBe(-32602);
    expect(body.error.message).toMatch(/Unknown tool/);
  });

  it("rejects header/body disagreement, as the Python transport does", async () => {
    const res = await call("tools/call", { name: catalog.tools[1].name }, {
      headers: { "Mcp-Name": KNOWN },
      env: { MAXEY0_ORIGIN: "https://origin.example.invalid" },
    });
    expect(res.status).toBe(400);
    expect((await res.json() as any).error.message).toMatch(/must equal params.name/);
  });

  it("accepts a declared tool name", async () => {
    // No origin configured, so this reaches the -32010 refusal rather than a
    // network call -- which is exactly the proof it got past validation.
    const res = await call("tools/call", { name: KNOWN }, { headers: { "Mcp-Name": KNOWN } });
    expect((await res.json() as any).error.code).toBe(-32010);
  });

  it("validates every name the catalog actually declares", () => {
    expect(catalog.tools.length).toBeGreaterThan(0);
    for (const t of catalog.tools) expect(typeof t.name).toBe("string");
  });
});

describe("/health states the edge's own auth posture", () => {
  it("says it performs no authorization, and where to read the other half", async () => {
    const res = await worker.fetch(
      new Request("https://mcp.example.test/health"), {},
    );
    const body = await res.json() as any;
    expect(body.edge_authorizes).toBe(false);
    expect(body.authorization).toMatch(/terminated at origin/);
    expect(body.origin_auth_posture).toMatch(/admin_open/);
  });

  it("reports the CORS posture it is actually running", async () => {
    const open = await (await worker.fetch(
      new Request("https://mcp.example.test/health"), {},
    )).json() as any;
    expect(open.cors_allowed_origins).toBe("*");
    expect(open.cors_advertises_authorization).toBe(false);

    const locked = await (await worker.fetch(
      new Request("https://mcp.example.test/health"),
      { MAXEY0_ALLOWED_ORIGINS: "https://app.example.invalid" },
    )).json() as any;
    expect(locked.cors_allowed_origins).toBe("https://app.example.invalid");
    expect(locked.cors_advertises_authorization).toBe(true);
  });
});

describe("/health and GET /mcp identify the service without internals", () => {
  it("reports the version and a plain build id, and drops an unsafe one", async () => {
    const ok = await worker.fetch(
      new Request("https://mcp.example.test/health"), { MAXEY0_BUILD_ID: "8b105559" },
    );
    const body = await ok.json() as Record<string, unknown>;
    expect(typeof body.version).toBe("string");
    expect(body.build).toBe("8b105559");
    const unsafe = await worker.fetch(
      new Request("https://mcp.example.test/health"), { MAXEY0_BUILD_ID: "http://10.0.0.5/" },
    );
    expect((await unsafe.json() as Record<string, unknown>).build).toBeUndefined();
  });

  it("answers a browser GET on /mcp with 405 and where the probe is", async () => {
    const res = await worker.fetch(new Request("https://mcp.example.test/mcp"), {});
    expect(res.status).toBe(405);
    const body = await res.json() as { error: { data: Record<string, string> } };
    expect(body.error.data.health).toBe("/health");
  });
});
