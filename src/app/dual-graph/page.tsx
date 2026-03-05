"use client";

import { useEffect, useMemo, useState } from "react";
import { Card } from "@/lib/ui/Card";
import { Button } from "@/lib/ui/Button";
import { Input } from "@/lib/ui/Input";
import { Select } from "@/lib/ui/Select";
import { Delaunay } from "d3-delaunay";
import ReactFlow, { Background, Controls, Edge, Node } from "reactflow";
import "reactflow/dist/style.css";

type DatasetRow = { id: string; name: string; createdAt: string };
type ProjPoint = { id: string; label: string; x: number; y: number };

export default function DualGraphPage() {
  const [datasets, setDatasets] = useState<DatasetRow[]>([]);
  const [datasetId, setDatasetId] = useState("");
  const [seed, setSeed] = useState("maxey0");
  const [k, setK] = useState(24);
  const [busy, setBusy] = useState(false);
  const [proj, setProj] = useState<ProjPoint[]>([]);
  const [partition, setPartition] = useState<any | null>(null);

  async function refreshDatasets() {
    const r = await fetch("/api/dataset/list");
    const j = await r.json();
    const ds = j.datasets ?? [];
    setDatasets(ds);
    if (!datasetId && ds.length) setDatasetId(ds[0].id);
  }
  useEffect(() => { refreshDatasets(); }, []);

  async function compute() {
    if (!datasetId) return;
    setBusy(true);
    try {
      const [projR, partR] = await Promise.all([
        fetch("/api/projection/compute", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ datasetId, method: "pca", seed: seed + "::proj" }) }),
        fetch("/api/partition/compute", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ datasetId, k, seed: seed + "::kmeans" }) }),
      ]);
      const pj = await projR.json();
      const pt = await partR.json();
      setProj(pj.points ?? []);
      setPartition(pt);
    } finally {
      setBusy(false);
    }
  }

  const voronoiSvg = useMemo(() => {
    if (proj.length < 3) return null;
    const xs = proj.map(p => p.x);
    const ys = proj.map(p => p.y);
    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const minY = Math.min(...ys), maxY = Math.max(...ys);
    const pad = 0.05;
    const w = 900, h = 520;

    const sx = (x: number) => ((x - minX) / (maxX - minX + 1e-9)) * (w * (1 - 2*pad)) + w * pad;
    const sy = (y: number) => ((y - minY) / (maxY - minY + 1e-9)) * (h * (1 - 2*pad)) + h * pad;

    const delaunay = Delaunay.from(proj, p => sx(p.x), p => sy(p.y));
    const vor = delaunay.voronoi([0,0,w,h]);

    const cells: string[] = [];
    for (let i = 0; i < proj.length; i++) {
      const p = vor.renderCell(i);
      if (p) cells.push(p);
    }

    const edgesPath = delaunay.render();
    return { w, h, cells, edgesPath, sx, sy };
  }, [proj]);

  const rf = useMemo(() => {
    if (!partition?.dualEdges) return { nodes: [] as Node[], edges: [] as Edge[] };
    const nodes: Node[] = [];
    const edges: Edge[] = [];
    const n = partition.k as number;
    const radius = 220;

    for (let i = 0; i < n; i++) {
      const ang = (2 * Math.PI * i) / n;
      nodes.push({
        id: String(i),
        position: { x: radius * Math.cos(ang), y: radius * Math.sin(ang) },
        data: { label: `C${i}` },
        style: { background: "rgba(255,255,255,0.08)", border: "1px solid rgba(255,255,255,0.15)", color: "#e5e7eb", borderRadius: 12, padding: 8 },
      });
    }

    for (const e of partition.dualEdges as any[]) {
      edges.push({
        id: `${e.a}-${e.b}`,
        source: String(e.a),
        target: String(e.b),
        label: String(e.support),
        style: { stroke: "rgba(255,255,255,0.35)" },
        labelStyle: { fill: "#cbd5e1", fontSize: 10 },
      });
    }

    return { nodes, edges };
  }, [partition]);

  return (
    <div className="space-y-4">
      <div className="text-2xl font-semibold tracking-tight">Geometry View</div>

      <div className="grid grid-cols-3 gap-4">
        <Card title="Compute">
          <div className="space-y-2">
            <div className="text-xs text-white/60">Dataset</div>
            <Select value={datasetId} onChange={(e) => setDatasetId(e.target.value)}>
              {datasets.map(d => <option key={d.id} value={d.id}>{d.name} · {d.id}</option>)}
            </Select>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <div className="text-xs text-white/60">k (centroids)</div>
                <Input type="number" value={k} onChange={(e) => setK(parseInt(e.target.value || "2", 10))} />
              </div>
              <div>
                <div className="text-xs text-white/60">seed</div>
                <Input value={seed} onChange={(e) => setSeed(e.target.value)} />
              </div>
            </div>
            <Button onClick={compute} disabled={busy}>{busy ? "Computing…" : "Compute"}</Button>
            <div className="text-xs text-white/60">
              Voronoi partitions render from projected latent points, with Delaunay triangulation overlay and centroid dual adjacency.
            </div>
          </div>
        </Card>

        <Card title="Why this matters">
          <div className="space-y-2 text-sm">
            Voronoi partitions define region membership; Delaunay encodes the adjacency dual. Transition sequences across regions
            become path problems on the dual graph.
          </div>
        </Card>

        <Card title="Output">
          {partition ? (
            <div className="text-sm space-y-1">
              <div>k: <b>{partition.k}</b> · iters: <b>{partition.iters}</b></div>
              <div>inertia: <b>{partition.inertia.toFixed(3)}</b></div>
              <div>dual edges: <b>{(partition.dualEdges ?? []).length}</b></div>
            </div>
          ) : (
            <div className="text-sm text-white/70">Compute to populate.</div>
          )}
        </Card>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Card title="Voronoi + Delaunay (projection plane)">
          <div className="h-[540px] overflow-auto">
            {voronoiSvg ? (
              <svg width={voronoiSvg.w} height={voronoiSvg.h} style={{ background: "rgba(0,0,0,0.2)", borderRadius: 12 }}>
                <g opacity={0.55}>
                  {voronoiSvg.cells.map((d, i) => (
                    <path key={i} d={d} fill="none" stroke="rgba(255,255,255,0.12)" strokeWidth={1} />
                  ))}
                </g>
                <path d={voronoiSvg.edgesPath} fill="none" stroke="rgba(255,255,255,0.20)" strokeWidth={1} />
                {proj.map((p) => (
                  <circle key={p.id} cx={voronoiSvg.sx(p.x)} cy={voronoiSvg.sy(p.y)} r={2} fill="rgba(255,255,255,0.7)" />
                ))}
              </svg>
            ) : (
              <div className="text-sm text-white/70">Compute to render.</div>
            )}
          </div>
        </Card>

        <Card title="Dual graph over centroids (high-D approx)">
          <div className="h-[540px]">
            <ReactFlow nodes={rf.nodes} edges={rf.edges} fitView>
              <Background />
              <Controls />
            </ReactFlow>
          </div>
        </Card>
      </div>
    </div>
  );
}
