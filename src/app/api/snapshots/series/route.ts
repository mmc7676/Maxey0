import { NextResponse } from "next/server";
import { nanoid } from "nanoid";
import { db } from "@/server/db";

export async function GET() {
  const rows = db().prepare("SELECT id, name, created_at FROM snapshot_series ORDER BY created_at DESC LIMIT 200").all() as any[];
  return NextResponse.json({ series: rows.map(r => ({ id: r.id, name: r.name, createdAt: new Date(r.created_at).toISOString() })) });
}

export async function POST(req: Request) {
  const body = await req.json() as { name: string };
  const id = nanoid();
  db().prepare("INSERT INTO snapshot_series(id, name, created_at) VALUES(?,?,?)").run(id, body.name || "series", Date.now());
  return NextResponse.json({ ok: true, id });
}
