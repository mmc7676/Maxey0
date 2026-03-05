import { Card } from "@/lib/ui/Card";

export default function Page() {
  return (
    <div className="space-y-4">
      <div className="text-2xl font-semibold tracking-tight">Maxey0 Latent Space Lab</div>
      <div className="text-sm text-white/70">
        Multi-page research interface for interpretable latent coordinate design, mapping, geometry analysis, experimentation,
        dataset generation, and observability replay.
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Card title="Research workflow pages">
          <ol className="list-decimal pl-5 space-y-1 text-sm">
            <li>Constitution Designer: edit/weight 64 latent axes.</li>
            <li>Latent Space Mapper: project points, place SCW nodes, animate trajectories.</li>
            <li>Experiment Runner: run latent sequences and snapshot recording.</li>
            <li>Geometry View: Voronoi partitions + Delaunay triangulation overlay.</li>
            <li>Dataset Generator: synthesize/export latent trajectories.</li>
            <li>Observability: inspect transitions and replay experiments.</li>
          </ol>
        </Card>

        <Card title="Core primitives">
          <ul className="list-disc pl-5 space-y-1 text-sm">
            <li>64-axis constitution and deterministic latent embedding.</li>
            <li>Snapshot series with SQLite persistence + KV cache.</li>
            <li>Projection, partitioning, and dual graph analysis.</li>
            <li>Demo dataset loader backed by <code>data/demo_latent_states.json</code>.</li>
          </ul>
        </Card>
      </div>
    </div>
  );
}
