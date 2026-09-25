import { afterEach, describe, expect, it, vi } from "vitest";
import worker, { type Env } from "../src/index";
import catalog from "../src/generated/surface.json";

const V = "2026-07-28";
const MCP = "https://mcp.example.test/mcp";

function call(method: string, params: unknown = {}, opts: {
  env?: Env;
  headers?: Record<string, string>;
  id?: unknown;
} = {}) {
  const headers: Record<string, string> = {
    "content-type": "application/json",
    "MCP-Protocol-Version": V,
    "Mcp-Method": method,
    ...opts.headers,
  };
  const req = new Request(MCP, {
    method: "POST",
    headers,
    body: JSON.stringify({ jsonrpc: "2.0", id: opts.id ?? 1, method, params }),
  });
  return worker.fetch(req, opts.env ?? {});
}

afterEach(() => vi.unstubAllGlobals());

describe("protocol envelope", () => {
  it("answers server/discover with the 2026-07-28 contract", async () => {
    const body = await (await call("server/discover")).json() as any;
    expect(body.result.protocolVersion).toBe(V);
    expect(body.result.serverInfo.name).toBe("Maxey0-SuperSpace");
    expect(body.result.capabilities.extensions).toHaveProperty("io.modelcontextprotocol/ui");
  });

  it("rejects a client that does not speak 2026-07-28", async () => {
    const res = await call("tools/list", {}, { headers: { "MCP-Protocol-Version": "2025-06-18" } });
    expect(res.status).toBe(400);
    expect((await res.json() as any).error.code).toBe(-32600);
  });

  it("rejects initialize, exactly as the Python transport does", async () => {
    const res = await call("initialize");
    expect(res.status).toBe(404);
    expect((await res.json() as any).error.message).toMatch(/Method not found/);
  });

  it("requires the Mcp-Method header", async () => {
    const req = new Request(MCP, {
      method: "POST",
      headers: { "content-type": "application/json", "MCP-Protocol-Version": V },
      body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/list" }),
    });
    const res = await worker.fetch(req, {});
    expect(res.status).toBe(400);
    expect((await res.json() as any).error.message).toMatch(/Missing Mcp-Method/);
  });

  it("requires Mcp-Name on tools/call", async () => {
    const res = await call("tools/call", { name: "maxey0-ss.health", arguments: {} });
    expect(res.status).toBe(400);
    expect((await res.json() as any).error.message).toMatch(/Missing Mcp-Name/);
  });

  it("refuses a header that disagrees with the JSON-RPC method", async () => {
    const req = new Request(MCP, {
      method: "POST",
      headers: { "content-type": "application/json", "MCP-Protocol-Version": V, "Mcp-Method": "tools/list" },
      body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "resources/list" }),
    });
    const res = await worker.fetch(req, {});
    expect(res.status).toBe(400);
    expect((await res.json() as any).error.message).toMatch(/does not match/);
  });

  it("reports a parse error on a malformed body", async () => {
    const req = new Request(MCP, {
      method: "POST",
      headers: { "content-type": "application/json", "MCP-Protocol-Version": V, "Mcp-Method": "tools/list" },
      body: "{not json",
    });
    expect((await (await worker.fetch(req, {})).json() as any).error.code).toBe(-32700);
  });
});

describe("catalog", () => {
  it("serves every tool the Python surface defines", async () => {
    const body = await (await call("tools/list")).json() as any;
    expect(body.result.tools).toHaveLength(catalog.tools.length);
    expect(body.result.tools.map((t: { name: string }) => t.name)).toEqual(
      catalog.tools.map((t) => t.name),
    );
  });

  it("attaches cache hints to catalog responses", async () => {
    const body = await (await call("tools/list")).json() as any;
    expect(body.result.ttlMs).toBe(300_000);
    expect(body.result.cacheScope).toBe("server");
  });

  it("honours a configured catalog TTL", async () => {
    const body = await (await call("tools/list", {}, { env: { MAXEY0_CATALOG_TTL: "60" } })).json() as any;
    expect(body.result.ttlMs).toBe(60_000);
  });

  it("keeps the App tool linked to the App resource", async () => {
    const body = await (await call("tools/list")).json() as any;
    const tool = body.result.tools.find((t: { name: string }) => t.name === "maxey0-ss.super_space");
    expect(tool._meta.ui.resourceUri).toBe(catalog.superSpaceUri);
  });
});

describe("resources", () => {
  it("serves the built MCP App, not a stub", async () => {
    const body = await (await call("resources/read", { uri: catalog.superSpaceUri })).json() as any;
    const content = body.result.contents[0];
    expect(content.mimeType).toBe("text/html;profile=mcp-app");
    expect(content.text.length).toBeGreaterThan(100_000);
    expect(catalog.artifact.kind).toBe("built");
  });

  it("serves the static JSON resources", async () => {
    const body = await (await call("resources/read", { uri: "maxey0-ss://architecture/planes" })).json() as any;
    expect(body.result.contents[0].text).toContain("context");
  });

  it("refuses an unknown resource", async () => {
    const res = await call("resources/read", { uri: "ui://nope" });
    expect(res.status).toBe(400);
    expect((await res.json() as any).error.code).toBe(-32602);
  });
});

describe("tool execution belongs to the origin", () => {
  it("never executes a tool at the edge when no origin is set", async () => {
    const res = await call(
      "tools/call",
      { name: "maxey0-ss.health", arguments: {} },
      { headers: { "Mcp-Name": "maxey0-ss.health" } },
    );
    expect(res.status).toBe(503);
    const body = await res.json() as any;
    expect(body.error.code).toBe(-32010);
    // The point: no fabricated result.
    expect(body).not.toHaveProperty("result");
  });

  it("forwards to the origin with the MCP routing headers intact", async () => {
    const seen: Request[] = [];
    vi.stubGlobal("fetch", async (req: Request) => {
      seen.push(req);
      return new Response(JSON.stringify({ jsonrpc: "2.0", id: 1, result: { ok: true } }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    });

    const res = await call(
      "tools/call",
      { name: "maxey0-ss.health", arguments: {} },
      { env: { MAXEY0_ORIGIN: "https://origin.test/" }, headers: { "Mcp-Name": "maxey0-ss.health" } },
    );

    expect(res.status).toBe(200);
    expect((await res.json() as any).result.ok).toBe(true);
    expect(seen).toHaveLength(1);
    expect(seen[0].url).toBe("https://origin.test/mcp");
    expect(seen[0].headers.get("MCP-Protocol-Version")).toBe(V);
    expect(seen[0].headers.get("Mcp-Name")).toBe("maxey0-ss.health");
  });

  it("reports an unreachable origin instead of inventing a result", async () => {
    vi.stubGlobal("fetch", async () => {
      throw new Error("ECONNREFUSED");
    });
    const res = await call(
      "tools/call",
      { name: "maxey0-ss.health", arguments: {} },
      { env: { MAXEY0_ORIGIN: "https://down.test" }, headers: { "Mcp-Name": "maxey0-ss.health" } },
    );
    expect(res.status).toBe(502);
    expect((await res.json() as any).error.code).toBe(-32011);
  });
});

describe("operational surface", () => {
  it("answers /health with the artifact identity", async () => {
    const res = await worker.fetch(new Request("https://mcp.example.test/health"), {});
    const body = await res.json() as any;
    expect(body.ok).toBe(true);
    expect(body.app_artifact.sha256).toBe(catalog.artifact.sha256);
    expect(body.origin_configured).toBe(false);
  });

  it("answers CORS preflight", async () => {
    const res = await worker.fetch(new Request(MCP, { method: "OPTIONS" }), {});
    expect(res.status).toBe(204);
    expect(res.headers.get("access-control-allow-methods")).toContain("POST");
  });

  it("rejects GET on the MCP endpoint", async () => {
    expect((await worker.fetch(new Request(MCP), {})).status).toBe(405);
  });
});

describe("tasks belong to the origin (SEP-2663)", () => {
  it("requires Mcp-Name on task methods", async () => {
    const req = new Request(MCP, {
      method: "POST",
      headers: { "content-type": "application/json", "MCP-Protocol-Version": V, "Mcp-Method": "tasks/get" },
      body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tasks/get", params: { taskId: "t1" } }),
    });
    const res = await worker.fetch(req, {});
    expect(res.status).toBe(400);
    expect((await res.json() as any).error.message).toMatch(/must carry params.taskId/);
  });

  it("refuses when Mcp-Name disagrees with the taskId", async () => {
    const res = await call("tasks/get", { taskId: "t1" }, { headers: { "Mcp-Name": "other" } });
    expect(res.status).toBe(400);
    expect((await res.json() as any).error.message).toMatch(/must equal params.taskId/);
  });

  it("never answers a task from the edge when no origin is set", async () => {
    const res = await call("tasks/get", { taskId: "t1" }, { headers: { "Mcp-Name": "t1" } });
    expect(res.status).toBe(503);
    const body = await res.json() as any;
    expect(body.error.code).toBe(-32010);
    expect(body).not.toHaveProperty("result");
  });

  it("forwards tasks/get to the origin with taskId as the route name", async () => {
    const seen: Request[] = [];
    vi.stubGlobal("fetch", async (req: Request) => {
      seen.push(req);
      return new Response(JSON.stringify({ jsonrpc: "2.0", id: 1, result: { taskId: "t1", status: "working" } }), {
        status: 200, headers: { "content-type": "application/json" },
      });
    });
    const res = await call("tasks/get", { taskId: "t1" }, {
      env: { MAXEY0_ORIGIN: "https://origin.test" }, headers: { "Mcp-Name": "t1" },
    });
    expect(res.status).toBe(200);
    expect(seen[0].headers.get("Mcp-Method")).toBe("tasks/get");
    expect(seen[0].headers.get("Mcp-Name")).toBe("t1");
  });

  it("forwards subscriptions/listen to the origin", async () => {
    const seen: Request[] = [];
    vi.stubGlobal("fetch", async (req: Request) => {
      seen.push(req);
      return new Response(JSON.stringify({ jsonrpc: "2.0", id: 1, result: { notifications: { taskIds: [] } } }), {
        status: 200, headers: { "content-type": "application/json" },
      });
    });
    const res = await call("subscriptions/listen", { notifications: { taskIds: ["t1"] } }, {
      env: { MAXEY0_ORIGIN: "https://origin.test" },
    });
    expect(res.status).toBe(200);
    expect(seen[0].headers.get("Mcp-Method")).toBe("subscriptions/listen");
  });
});
