import { NextResponse } from "next/server";
import { kvStats } from "@/server/kv";

export async function GET() {
  return NextResponse.json({ ok: true, now: new Date().toISOString(), kv: kvStats() });
}
