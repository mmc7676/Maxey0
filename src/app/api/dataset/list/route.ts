import { NextResponse } from "next/server";
import { db } from "@/server/db";
import { demoDatasetId, loadDemoDataset } from "@/lib/demoDataset";

export async function GET() {
  const rows = db().prepare("SELECT id, name, created_at FROM datasets ORDER BY created_at DESC LIMIT 200").all() as any[];
  const demo = loadDemoDataset();
  return NextResponse.json({
    datasets: [
      { id: demoDatasetId(), name: demo.name, createdAt: demo.createdAt },
      ...rows.map(r => ({ id: r.id, name: r.name, createdAt: new Date(r.created_at).toISOString() })),
    ],
  });
}
