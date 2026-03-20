import { NextResponse } from "next/server";
import { nanoid } from "nanoid";
import { db } from "@/server/db";
import { embedByConstitution, zConstitution } from "@/lib/constitution";
import { centroid, variance } from "@/lib/vec";

type Req = { seriesId: string; stepIndex: number; label: string; text?: string; vec?: number[]; meta?: any; };

function loadConstitution(): any {
  const row = db().prepare("SELECT value_json FROM constitution WHERE id = ?").get("active") as { value_json: string } | undefined;
  if (!row) throw new Error("constitution not initialized");
  return zConstitution.parse(JSON.parse(row.value_json));
}

export async function POST(req: Request) {
  const body = (await req.json()) as Req;
  const id = nanoid();
  const createdAt = Date.now();
  const meta = body.meta ?? {};

  let vec = body.vec;
  if (!vec) {
    const constitution = loadConstitution();
    vec = embedByConstitution(body.text ?? body.label, constitution);
    meta.autoEmbedded = true;
  }

  db().prepare(`
    INSERT INTO snapshots(id, series_id, step_index, label, text, vec_json, meta_json, created_at)
    VALUES(?,?,?,?,?,?,?,?)
  `).run(id, body.seriesId, body.stepIndex, body.label, body.text ?? null, JSON.stringify(vec), JSON.stringify(meta), createdAt);

  const rows = db().prepare("SELECT vec_json FROM snapshots WHERE series_id = ? ORDER BY step_index ASC").all(body.seriesId) as any[];
  const vs = rows.map(r => JSON.parse(r.vec_json) as number[]);
  const mu = centroid(vs);
  const v = variance(vs, mu);

  return NextResponse.json({ ok: true, id, stats: { steps: vs.length, centroid: mu, variance: v } });
}
