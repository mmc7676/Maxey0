import PCA from "ml-pca";
import { UMAP } from "umap-js";
import { mulberry32, hashSeed } from "@/server/rng";

export type ProjectionMethod = "pca" | "umap";

export type ProjectionModel =
  | { method: "pca"; components: number[][]; mean: number[]; explainedVariance: number[] }
  | { method: "umap"; umapParams: { nNeighbors: number; minDist: number; spread: number }; seed: number };

export function project2D(
  vectors: number[][],
  method: ProjectionMethod,
  options: { seed: string; umap?: { nNeighbors?: number; minDist?: number; spread?: number } }
): { coords: [number, number][], model: ProjectionModel } {
  if (vectors.length === 0) return { coords: [], model: { method: "pca", components: [], mean: [], explainedVariance: [] } };

  if (method === "pca") {
    const pca = new PCA(vectors, { center: true, scale: false });
    const predicted = pca.predict(vectors, { nComponents: 2 }).to2DArray();
    const coords = predicted.map((r) => [r[0], r[1]] as [number, number]);
    const loadings = pca.getLoadings().to2DArray(); // dim x comps
    const components = [loadings.map((row) => row[0]), loadings.map((row) => row[1])];
    const mean = pca.means;
    const explainedVariance = pca.getExplainedVariance();
    return { coords, model: { method: "pca", components, mean, explainedVariance } };
  }

  const seedN = hashSeed(options.seed);
  const rand = mulberry32(seedN);
  const umap = new UMAP({
    nComponents: 2,
    nNeighbors: options.umap?.nNeighbors ?? 15,
    minDist: options.umap?.minDist ?? 0.1,
    spread: options.umap?.spread ?? 1.0,
    random: rand,
  });
  const embedding = umap.fit(vectors) as number[][];
  const coords = embedding.map((r) => [r[0], r[1]] as [number, number]);
  return { coords, model: { method: "umap", umapParams: { nNeighbors: options.umap?.nNeighbors ?? 15, minDist: options.umap?.minDist ?? 0.1, spread: options.umap?.spread ?? 1.0 }, seed: seedN } };
}
