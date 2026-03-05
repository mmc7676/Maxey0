import { NextResponse } from "next/server";
import { nanoid } from "nanoid";
import { db } from "@/server/db";
import { kvGet, kvSet } from "@/server/kv";
import { sha256Hex, stableJson } from "@/lib/hash";
import { embedByConstitution, zConstitution } from "@/lib/constitution";
import { mulberry32, hashSeed } from "@/server/rng";
import { adaptiveFoldStep } from "@/server/folding";
import { centroid, variance } from "@/lib/vec";

type Req = {
  name: string;
  seed: string;
  points: number;
  stepsPerPoint: number;
  foldDim: number;
};

function loadConstitution(): any {
  const row = db().prepare("SELECT value_json FROM constitution WHERE id = ?").get("active") as { value_json: string } | undefined;
  if (!row) throw new Error("constitution not initialized");
  return zConstitution.parse(JSON.parse(row.value_json));
}

export async function POST(req: Request) {
  const body = (await req.json()) as Req;
  const points = Math.max(1, Math.min(10000, Math.floor(body.points)));
  const stepsPerPoint = Math.max(1, Math.min(50, Math.floor(body.stepsPerPoint)));
  const foldDim = Math.max(2, Math.min(63, Math.floor(body.foldDim)));

  const constitution = loadConstitution();

  const config = { ...body, points, stepsPerPoint, foldDim, constitutionVersion: constitution.version, constitutionCount: constitution.laws.length };
  const cacheKey = "dataset_generate:" + sha256Hex(stableJson(config));
  const cached = kvGet(cacheKey);
  if (cached) return NextResponse.json(cached);

  const rand = mulberry32(hashSeed(body.seed));
  const datasetId = nanoid();

  db().prepare("INSERT INTO datasets(id, name, config_json, created_at) VALUES(?,?,?,?)")
    .run(datasetId, body.name || "dataset", JSON.stringify(config), Date.now());

  const insert = db().prepare(`
    INSERT INTO dataset_points(dataset_id, point_id, label, text, vec_json, meta_json, created_at)
    VALUES(?,?,?,?,?,?,?)
  `);

  const nouns = ["portal", "gate", "anchor", "marker", "snapshot", "fold", "memory", "agent", "policy", "trace", "delta"];
  const verbs = ["measure", "infer", "stabilize", "route", "probe", "compress", "expand", "triangulate", "observe", "map"];

  const mkText = (i: number, j: number) => {
    const a = constitution.laws[Math.floor(rand() * constitution.laws.length)];
    const b = nouns[Math.floor(rand() * nouns.length)];
    const c = verbs[Math.floor(rand() * verbs.length)];
    return `SCW sample ${i} step ${j}: ${c} using ${b}. Constraint: ${a.label}. ${a.desc}`;
  };

  const createdAt = Date.now();
  const vecs: number[][] = [];

  for (let i = 0; i < points; i++) {
    const baseText = mkText(i, 0);
    const baseVec = embedByConstitution(baseText, constitution);
    vecs.push(baseVec);

    const meta: any = { baseText, steps: [] as any[] };
    let current = baseVec.slice();

    for (let j = 1; j <= stepsPerPoint; j++) {
      const text = mkText(i, j);
      const v = embedByConstitution(text, constitution);

      const alpha = 0.35;
      const next = current.map((x, k) => (1 - alpha) * x + alpha * v[k]);

      const fold = adaptiveFoldStep(next, `${body.seed}::${i}::${j}`, foldDim);
      meta.steps.push({
        j,
        text,
        deltaL2: Math.sqrt(next.reduce((s, x, k) => { const d = x - current[k]; return s + d*d; }, 0)),
        foldLoss: fold.loss,
      });

      current = next;
    }

    const pointId = nanoid();
    insert.run(datasetId, pointId, `sample_${i}`, baseText, JSON.stringify(baseVec), JSON.stringify(meta), createdAt);
  }

  const mu = centroid(vecs);
  const v = variance(vecs, mu);

  const out = { ok: true, datasetId, points, stepsPerPoint, dim: constitution.laws.length, stats: { centroid: mu, variance: v } };
  kvSet(cacheKey, out, 60);
  return NextResponse.json(out);
}
