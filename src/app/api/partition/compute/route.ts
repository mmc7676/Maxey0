import { NextResponse } from "next/server";
import { db } from "@/server/db";
import { kvGet, kvSet } from "@/server/kv";
import { sha256Hex, stableJson } from "@/lib/hash";
import { kmeans } from "@/server/kmeans";
import { approxVoronoiAdjacency } from "@/server/voronoi_dual";

type Req = { datasetId: string; k: number; seed: string; };

export async function POST(req: Request) {
  const body = (await req.json()) as Req;
  const k = Math.max(2, Math.min(256, Math.floor(body.k)));
  const config = { ...body, k };
  const cacheKey = "partition:" + sha256Hex(stableJson(config));
  const cached = kvGet(cacheKey);
  if (cached) return NextResponse.json(cached);

  const pts = db().prepare("SELECT vec_json FROM dataset_points WHERE dataset_id = ?").all(body.datasetId) as any[];
  const vectors = pts.map(p => JSON.parse(p.vec_json) as number[]);
  const km = kmeans(vectors, k, body.seed, 60);
  const dual = approxVoronoiAdjacency(vectors, km.centroids);

  const out = { ok: true, k: km.k, centroids: km.centroids, assignments: km.assignments, inertia: km.inertia, iters: km.iters, dualEdges: dual.edges };
  kvSet(cacheKey, out, 120);
  return NextResponse.json(out);
}
