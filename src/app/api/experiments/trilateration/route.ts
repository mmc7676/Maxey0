import { NextResponse } from "next/server";
import { estimateByTrilateration } from "@/server/trilateration";

export async function POST(req: Request) {
  const body = await req.json() as { anchors: number[][]; distances: number[]; dim: number; seed: string; steps?: number; lr?: number; lambda?: number; target?: number[] };
  const res = estimateByTrilateration(body.anchors, body.distances, { dim: body.dim, seed: body.seed, steps: body.steps, lr: body.lr, lambda: body.lambda });
  let errorL2: number | null = null;
  if (body.target) {
    let s = 0;
    for (let i = 0; i < body.dim; i++) { const d = res.x[i] - body.target[i]; s += d*d; }
    errorL2 = Math.sqrt(s);
  }
  return NextResponse.json({ ok: true, ...res, errorL2 });
}
