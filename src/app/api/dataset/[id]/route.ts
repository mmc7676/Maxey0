import { NextResponse } from "next/server";
import { db } from "@/server/db";
import { demoDatasetId, loadDemoDataset } from "@/lib/demoDataset";

export async function GET(_req: Request, { params }: { params: { id: string } }) {
  if (params.id === demoDatasetId()) {
    const demo = loadDemoDataset();
    return NextResponse.json({
      dataset: {
        id: demoDatasetId(),
        name: demo.name,
        createdAt: demo.createdAt,
        config: {
          seed: demo.seed,
          dim: demo.dimension_count,
          source: "data/demo_latent_states.json",
        },
      },
      points: demo.points.map((p) => ({
        id: p.id,
        label: p.label,
        text: p.text ?? "",
        vec: p.vec,
        meta: p.meta ?? {},
        createdAt: demo.createdAt,
      })),
    });
  }

  const ds = db().prepare("SELECT id, name, config_json, created_at FROM datasets WHERE id = ?").get(params.id) as any;
  if (!ds) return NextResponse.json({ error: "not_found" }, { status: 404 });
  const pts = db().prepare("SELECT point_id, label, text, vec_json, meta_json, created_at FROM dataset_points WHERE dataset_id = ? LIMIT 5000").all(params.id) as any[];
  return NextResponse.json({
    dataset: { id: ds.id, name: ds.name, config: JSON.parse(ds.config_json), createdAt: new Date(ds.created_at).toISOString() },
    points: pts.map(p => ({
      id: p.point_id,
      label: p.label,
      text: p.text,
      vec: JSON.parse(p.vec_json),
      meta: JSON.parse(p.meta_json),
      createdAt: new Date(p.created_at).toISOString(),
    })),
  });
}
