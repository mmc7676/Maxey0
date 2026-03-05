import { NextResponse } from "next/server";
import { db } from "@/server/db";

export async function GET(_req: Request, { params }: { params: { id: string } }) {
  const s = db().prepare("SELECT id, name, created_at FROM snapshot_series WHERE id = ?").get(params.id) as any;
  if (!s) return NextResponse.json({ error: "not_found" }, { status: 404 });

  const rows = db().prepare("SELECT id, step_index, label, text, vec_json, meta_json, created_at FROM snapshots WHERE series_id = ? ORDER BY step_index ASC").all(params.id) as any[];
  return NextResponse.json({
    series: { id: s.id, name: s.name, createdAt: new Date(s.created_at).toISOString() },
    snapshots: rows.map(r => ({
      id: r.id,
      stepIndex: r.step_index,
      label: r.label,
      text: r.text,
      vec: JSON.parse(r.vec_json),
      meta: JSON.parse(r.meta_json),
      createdAt: new Date(r.created_at).toISOString(),
    }))
  });
}
