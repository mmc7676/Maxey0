import { NextResponse } from "next/server";
import { db } from "@/server/db";
import { kvGet, kvSet } from "@/server/kv";
import { sha256Hex, stableJson } from "@/lib/hash";
import { project2D } from "@/server/projection";

type Req = { datasetId: string; method: "pca" | "umap"; seed: string; umap?: { nNeighbors?: number; minDist?: number; spread?: number } };

export async function POST(req: Request) {
  const body = (await req.json()) as Req;
  const config = { ...body, umap: body.umap ?? {} };
  const cacheKey = "proj2d:" + sha256Hex(stableJson(config));
  const cached = kvGet(cacheKey);
  if (cached) return NextResponse.json(cached);

  const pts = db().prepare("SELECT point_id, vec_json, label FROM dataset_points WHERE dataset_id = ? LIMIT 10000").all(body.datasetId) as any[];
  const vectors = pts.map(p => JSON.parse(p.vec_json) as number[]);
  const { coords, model } = project2D(vectors, body.method, { seed: body.seed, umap: body.umap });

  const out = { ok: true, model, points: pts.map((p, i) => ({ id: p.point_id, label: p.label, x: coords[i][0], y: coords[i][1] })) };
  kvSet(cacheKey, out, 300);
  return NextResponse.json(out);
}
