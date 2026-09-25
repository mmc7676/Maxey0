import { describe, expect, it } from "vitest";

import { CONNECTORS, COUNTS, PLANES, TOOLS, VIEWS, toolsFor } from "../generated/catalog";
import { isProjection, isRefusal, type StreamResponse } from "./types";

/**
 * These test the two distinctions that are easy to lose in a type that looks
 * tidier, and that the product's honesty depends on.
 */

describe("the generated catalog", () => {
  it("agrees with its own counts", () => {
    expect(TOOLS).toHaveLength(COUNTS.total);
    expect(toolsFor("context")).toHaveLength(COUNTS.context);
    expect(toolsFor("loops")).toHaveLength(COUNTS.loops);
    expect(toolsFor("observe")).toHaveLength(COUNTS.observe);
  });

  it("names every tool for its connector", () => {
    for (const tool of TOOLS) {
      expect(tool.name.startsWith(`${tool.connector}_`)).toBe(true);
    }
  });

  it("keeps planes and connectors as different decompositions", () => {
    // A plane is what the system is; a connector is what installs. Two
    // connectors serve the Context plane, and the Execution plane has none —
    // collapsing them would erase the product's whole differentiation.
    expect(Object.keys(PLANES)).toEqual(["execution", "context", "engineering"]);
    expect(PLANES.execution.owner).toBe("the host");
    expect(PLANES.execution.connectors).toBe("");
    expect(CONNECTORS.context.plane).toBe("context");
    expect(CONNECTORS.loops.plane).toBe("context");
    expect(CONNECTORS.observe.plane).toBe("engineering");
  });

  it("carries the nine Studio views", () => {
    expect(VIEWS).toHaveLength(9);
    expect(VIEWS.map((v) => v.name)).toContain("Evidence");
  });

  it("has no maxey0_-prefixed tool", () => {
    expect(TOOLS.filter((t) => t.name.startsWith("maxey0_"))).toEqual([]);
  });
});

describe("a refusal is a result, not an exception", () => {
  it("is narrowed by isRefusal", () => {
    const refused = { ok: false as const, error: "isolation_violation", hint: "open a bridge" };
    expect(isRefusal(refused)).toBe(true);
    if (isRefusal(refused)) expect(refused.hint).toBe("open a bridge");
  });
});

describe("the stream has two shapes", () => {
  const summary = {
    events: 774,
    by_kind: { refusal: 633 },
    by_type: {},
    refusals_by_loop: {},
    regions_refused: {},
  } satisfies StreamResponse;

  const projection = {
    events: [{ seq: 1, kind: "refusal" as const, type: "scw.denied" }],
    returned: 1,
    matched: 1,
    scanned: 1,
    truncated: false,
  } satisfies StreamResponse;

  it("tells a summary from a projection", () => {
    expect(isProjection(summary)).toBe(false);
    expect(isProjection(projection)).toBe(true);
  });

  it("does not read a summary count as an empty list", () => {
    // The bug this predicate exists to prevent: `events` is 774 here, and
    // reading it as a list renders "no events" over a run that had 774.
    expect(isProjection(summary) ? summary.events.length : summary.events).toBe(774);
  });
});
