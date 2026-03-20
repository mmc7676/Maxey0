"use client";

import { useEffect, useMemo, useState } from "react";
import { Card } from "@/lib/ui/Card";
import { Button } from "@/lib/ui/Button";
import { Input } from "@/lib/ui/Input";
import { Select } from "@/lib/ui/Select";
import { ScatterChart, Scatter, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

type DatasetRow = { id: string; name: string; createdAt: string };
type MapperPoint = { id: string; label: string; x: number; y: number };
type ScwNode = { id: string; x: number; y: number };

export default function MapperPage() {
  const [datasets, setDatasets] = useState<DatasetRow[]>([]);
  const [datasetId, setDatasetId] = useState<string>("");
  const [method, setMethod] = useState<"pca" | "umap">("pca");
  const [seed, setSeed] = useState("maxey0-proj");
  const [busy, setBusy] = useState(false);
  const [points, setPoints] = useState<MapperPoint[]>([]);
  const [trajectoryStep, setTrajectoryStep] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [scwNodes, setScwNodes] = useState<ScwNode[]>([]);

  async function refreshDatasets() {
    const r = await fetch("/api/dataset/list");
    const j = await r.json();
    const ds = j.datasets ?? [];
    setDatasets(ds);
    if (!datasetId && ds.length) setDatasetId(ds[0].id);
  }

  useEffect(() => {
    refreshDatasets();
  }, []);

  useEffect(() => {
    if (!playing || points.length < 2) return;
    const timer = window.setInterval(() => {
      setTrajectoryStep((prev) => (prev + 1) % points.length);
    }, 450);
    return () => window.clearInterval(timer);
  }, [playing, points.length]);

  async function compute() {
    if (!datasetId) return;
    setBusy(true);
    try {
      const r = await fetch("/api/projection/compute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ datasetId, method, seed, umap: { nNeighbors: 15, minDist: 0.1, spread: 1.0 } }),
      });
      const j = await r.json();
      const nextPoints = j.points ?? [];
      setPoints(nextPoints);
      setTrajectoryStep(0);
      setPlaying(false);
      setScwNodes([]);
    } finally {
      setBusy(false);
    }
  }

  const data = useMemo(() => points.map((p) => ({ ...p })), [points]);
  const trajectory = useMemo(() => points.slice(0, Math.max(trajectoryStep + 1, 1)), [points, trajectoryStep]);

  const nearestForNode = useMemo(() => {
    if (!points.length) return [] as { nodeId: string; pointId: string; pointLabel: string; distance: number }[];
    return scwNodes.map((node) => {
      let best = { pointId: "", pointLabel: "", distance: Number.POSITIVE_INFINITY };
      for (const p of points) {
        const d = Math.hypot(p.x - node.x, p.y - node.y);
        if (d < best.distance) best = { pointId: p.id, pointLabel: p.label, distance: d };
      }
      return { nodeId: node.id, ...best };
    });
  }, [points, scwNodes]);

  function handleChartClick(evt: any) {
    if (!evt || typeof evt.xValue !== "number" || typeof evt.yValue !== "number") return;
    const id = `SCW_${String(scwNodes.length + 1).padStart(2, "0")}`;
    setScwNodes((prev) => [...prev, { id, x: Number(evt.xValue), y: Number(evt.yValue) }]);
  }

  return (
    <div className="space-y-4">
      <div className="text-2xl font-semibold tracking-tight">Latent Space Mapper</div>

      <div className="grid grid-cols-3 gap-4">
        <Card title="Projection">
          <div className="space-y-2">
            <div className="text-xs text-white/60">Dataset</div>
            <Select value={datasetId} onChange={(e) => setDatasetId(e.target.value)}>
              {datasets.map((d) => (
                <option key={d.id} value={d.id}>{d.name} · {d.id}</option>
              ))}
            </Select>
            <div className="text-xs text-white/60">Method</div>
            <Select value={method} onChange={(e) => setMethod(e.target.value as "pca" | "umap")}>
              <option value="pca">PCA (fast, linear)</option>
              <option value="umap">UMAP (nonlinear neighborhoods)</option>
            </Select>
            <div className="text-xs text-white/60">Seed</div>
            <Input value={seed} onChange={(e) => setSeed(e.target.value)} />
            <Button onClick={compute} disabled={busy}>{busy ? "Computing…" : "Compute projection"}</Button>
          </div>
        </Card>

        <Card title="Latent trajectory">
          <div className="space-y-2 text-sm">
            <div>Animate the ordered latent sequence and inspect state progression.</div>
            <div className="flex gap-2">
              <Button variant="ghost" onClick={() => setPlaying((s) => !s)} disabled={points.length < 2}>
                {playing ? "Pause" : "Play"}
              </Button>
              <Button variant="ghost" onClick={() => setTrajectoryStep(0)} disabled={!points.length}>Reset</Button>
            </div>
            <div className="text-xs text-white/60">Step: {trajectoryStep} / {Math.max(points.length - 1, 0)}</div>
          </div>
        </Card>

        <Card title="SCW nodes + distance">
          <div className="space-y-2 text-sm">
            <div>Click in the chart to place SCW nodes and measure nearest latent point distance.</div>
            <Button variant="ghost" onClick={() => setScwNodes([])} disabled={!scwNodes.length}>Clear SCW nodes</Button>
            <div className="max-h-28 overflow-auto space-y-1 text-xs">
              {nearestForNode.map((row) => (
                <div key={row.nodeId}>{row.nodeId} → {row.pointLabel} ({row.distance.toFixed(3)})</div>
              ))}
            </div>
          </div>
        </Card>
      </div>

      <Card title="Interactive latent space canvas">
        <div className="h-[560px]">
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart onClick={handleChartClick}>
              <XAxis dataKey="x" type="number" name="x" tick={{ fill: "#cbd5e1" }} />
              <YAxis dataKey="y" type="number" name="y" tick={{ fill: "#cbd5e1" }} />
              <Tooltip cursor={{ strokeDasharray: "3 3" }} contentStyle={{ background: "#0b1020", border: "1px solid rgba(255,255,255,0.1)" }} />
              <Scatter data={data} fill="rgba(148,163,184,0.7)" />
              <Scatter data={trajectory} fill="rgba(96,165,250,0.95)" line={{ stroke: "rgba(96,165,250,0.9)", strokeWidth: 2 }} shape="circle" />
              <Scatter data={scwNodes} fill="rgba(34,197,94,0.95)" />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      </Card>
    </div>
  );
}
