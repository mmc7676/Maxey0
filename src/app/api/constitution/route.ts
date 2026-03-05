import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";
import { db } from "@/server/db";
import { zConstitution } from "@/lib/constitution";

const ID = "active";

function loadDefault(): unknown {
  const p = path.join(process.cwd(), "data", "constitution.default.json");
  const raw = fs.readFileSync(p, "utf-8");
  return JSON.parse(raw);
}

export async function GET() {
  const row = db().prepare("SELECT value_json FROM constitution WHERE id = ?").get(ID) as { value_json: string } | undefined;
  if (!row) {
    const def = loadDefault();
    const parsed = zConstitution.parse(def);
    db().prepare("INSERT OR REPLACE INTO constitution(id, value_json, created_at) VALUES(?,?,?)").run(ID, JSON.stringify(parsed), Date.now());
    return NextResponse.json(parsed);
  }
  return NextResponse.json(zConstitution.parse(JSON.parse(row.value_json)));
}

export async function POST(req: Request) {
  const body = await req.json();
  const parsed = zConstitution.parse(body);
  db().prepare("INSERT OR REPLACE INTO constitution(id, value_json, created_at) VALUES(?,?,?)").run(ID, JSON.stringify(parsed), Date.now());
  return NextResponse.json({ ok: true });
}
