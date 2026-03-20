import { mulberry32, hashSeed } from "@/server/rng";
import { Vec, dot } from "@/lib/vec";

export function buildFoldMatrix(d: number, m: number, seed: string): number[][] {
  const rand = mulberry32(hashSeed(seed));
  const W: number[][] = [];
  for (let i = 0; i < m; i++) {
    const row = new Array(d).fill(0).map(() => {
      const u = Math.max(1e-12, rand());
      const v = Math.max(1e-12, rand());
      return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
    });
    const n = Math.sqrt(row.reduce((s, x) => s + x * x, 0)) || 1;
    for (let j = 0; j < d; j++) row[j] /= n;
    W.push(row);
  }
  return W;
}

export function fold(x: Vec, W: number[][]): Vec {
  const m = W.length;
  const y = new Array(m).fill(0);
  for (let i = 0; i < m; i++) y[i] = dot(W[i], x);
  return y;
}

export function unfold(y: Vec, W: number[][], d: number): Vec {
  const x = new Array(d).fill(0);
  for (let i = 0; i < W.length; i++) {
    const coeff = y[i];
    const row = W[i];
    for (let j = 0; j < d; j++) x[j] += row[j] * coeff;
  }
  return x;
}

export function reconstructionLoss(x: Vec, xHat: Vec): number {
  let s = 0;
  for (let i = 0; i < x.length; i++) {
    const d = x[i] - xHat[i];
    s += d * d;
  }
  return s / x.length;
}

export function adaptiveFoldStep(x: Vec, seed: string, foldDim: number): { folded: Vec; recon: Vec; loss: number } {
  const W = buildFoldMatrix(x.length, foldDim, seed);
  const y = fold(x, W);
  const xHat = unfold(y, W, x.length);
  const loss = reconstructionLoss(x, xHat);
  return { folded: y, recon: xHat, loss };
}
