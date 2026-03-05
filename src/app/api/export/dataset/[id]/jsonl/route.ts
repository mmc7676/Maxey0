import { NextResponse } from "next/server";
import { db } from "@/server/db";

export async function GET(_req: Request, { params }: { params: { id: string } }) {
  const ds = db().prepare("SELECT id, name, config_json, created_at FROM datasets WHERE id = ?").get(params.id) as any;
  if (!ds) return NextResponse.json({ error: "not_found" }, { status: 404 });

  const pts = db().prepare("SELECT point_id, label, text, vec_json, meta_json, created_at FROM dataset_points WHERE dataset_id = ?").all(params.id) as any[];
  const lines = pts.map(p => JSON.stringify({
    datasetId: ds.id,
    datasetName: ds.name,
    pointId: p.point_id,
    label: p.label,
    text: p.text,
    vec: JSON.parse(p.vec_json),
    meta: JSON.parse(p.meta_json),
    createdAt: new Date(p.created_at).toISOString(),
  })).join("\n") + "\n";

  return new NextResponse(lines, {
    headers: {
      "Content-Type": "application/x-ndjson; charset=utf-8",
      "Content-Disposition": `attachment; filename="dataset_${ds.id}.jsonl"`,
    }
  });
}
