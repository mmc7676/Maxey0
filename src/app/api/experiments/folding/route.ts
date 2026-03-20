import { NextResponse } from "next/server";
import { adaptiveFoldStep } from "@/server/folding";

export async function POST(req: Request) {
  const body = await req.json() as { x: number[]; seed: string; foldDim: number };
  const r = adaptiveFoldStep(body.x, body.seed, body.foldDim);
  return NextResponse.json({ ok: true, foldDim: body.foldDim, loss: r.loss, foldedPreview: r.folded.slice(0, 16), reconPreview: r.recon.slice(0, 16) });
}
