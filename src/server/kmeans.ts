import { mulberry32, hashSeed } from "@/server/rng";
import { l2Distance, centroid, Vec } from "@/lib/vec";

export type KMeansResult = {
  k: number;
  centroids: number[][];
  assignments: number[];
  inertia: number;
  iters: number;
};

function pickDistinctIndices(n: number, k: number, rand: () => number): number[] {
  const idx = new Set<number>();
  while (idx.size < k) idx.add(Math.floor(rand() * n));
  return [...idx];
}

export function kmeans(vectors: Vec[], k: number, seed: string, maxIters = 50): KMeansResult {
  if (vectors.length === 0) return { k, centroids: [], assignments: [], inertia: 0, iters: 0 };
  const n = vectors.length;
  const rand = mulberry32(hashSeed(seed));
  const initIdx = pickDistinctIndices(n, Math.min(k, n), rand);
  let centroidsArr = initIdx.map((i) => vectors[i].slice());

  let assignments = new Array(n).fill(0);
  let iters = 0;

  for (; iters < maxIters; iters++) {
    let changed = 0;

    for (let i = 0; i < n; i++) {
      let best = 0;
      let bestD = Infinity;
      for (let c = 0; c < centroidsArr.length; c++) {
        const d = l2Distance(vectors[i], centroidsArr[c]);
        if (d < bestD) { bestD = d; best = c; }
      }
      if (assignments[i] !== best) { assignments[i] = best; changed++; }
    }

    const buckets: Vec[][] = Array.from({ length: centroidsArr.length }, () => []);
    for (let i = 0; i < n; i++) buckets[assignments[i]].push(vectors[i]);

    const nextCentroids: Vec[] = [];
    for (let c = 0; c < centroidsArr.length; c++) {
      nextCentroids.push(buckets[c].length ? centroid(buckets[c]) : vectors[Math.floor(rand() * n)].slice());
    }

    centroidsArr = nextCentroids.map((v) => v.slice());
    if (changed === 0) break;
  }

  let inertia = 0;
  for (let i = 0; i < n; i++) {
    const d = l2Distance(vectors[i], centroidsArr[assignments[i]]);
    inertia += d * d;
  }

  return { k: centroidsArr.length, centroids: centroidsArr, assignments, inertia, iters: iters + 1 };
}
