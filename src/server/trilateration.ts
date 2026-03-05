import { l2Distance, Vec, add, scale, sub } from "@/lib/vec";
import { mulberry32, hashSeed } from "@/server/rng";

export function estimateByTrilateration(
  anchors: Vec[],
  distances: number[],
  opts: { dim: number; seed: string; steps?: number; lr?: number; lambda?: number }
): { x: Vec; loss: number; steps: number } {
  const steps = opts.steps ?? 250;
  const lr = opts.lr ?? 0.05;
  const lambda = opts.lambda ?? 1e-4;

  const rand = mulberry32(hashSeed(opts.seed));
  let x: Vec = new Array(opts.dim).fill(0).map(() => (rand() * 2 - 1) * 0.01);

  const safeNorm = (v: Vec) => Math.max(1e-9, Math.sqrt(v.reduce((s, t) => s + t * t, 0)));

  let loss = 0;
  for (let t = 0; t < steps; t++) {
    let grad: Vec = new Array(opts.dim).fill(0);
    loss = 0;

    for (let i = 0; i < anchors.length; i++) {
      const a = anchors[i];
      const r = distances[i];
      const diff = sub(x, a);
      const n = safeNorm(diff);
      const resid = (n - r);
      loss += resid * resid;
      const g = scale(diff, (2 * resid) / n);
      grad = add(grad, g);
    }

    loss += lambda * x.reduce((s, v) => s + v * v, 0);
    grad = add(grad, scale(x, 2 * lambda));
    x = sub(x, scale(grad, lr));
  }

  return { x, loss, steps };
}

export function distancesToAnchors(x: Vec, anchors: Vec[]): number[] {
  return anchors.map((a) => l2Distance(x, a));
}
