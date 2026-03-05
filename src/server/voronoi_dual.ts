import { l2Distance } from "@/lib/vec";

export function approxVoronoiAdjacency(points: number[][], centroids: number[][]): { edges: { a: number; b: number; support: number }[] } {
  const edgeKey = (a: number, b: number) => (a < b ? `${a}-${b}` : `${b}-${a}`);
  const support = new Map<string, number>();

  for (const x of points) {
    let best = -1, second = -1;
    let bestD = Infinity, secondD = Infinity;

    for (let i = 0; i < centroids.length; i++) {
      const d = l2Distance(x, centroids[i]);
      if (d < bestD) {
        secondD = bestD; second = best;
        bestD = d; best = i;
      } else if (d < secondD) {
        secondD = d; second = i;
      }
    }
    if (best >= 0 && second >= 0 && best !== second) {
      const k = edgeKey(best, second);
      support.set(k, (support.get(k) ?? 0) + 1);
    }
  }

  const edges = [...support.entries()].map(([k, v]) => {
    const [a, b] = k.split("-").map((n) => parseInt(n, 10));
    return { a, b, support: v };
  }).sort((x,y) => y.support - x.support);

  return { edges };
}
