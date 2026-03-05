"use client";

import { useEffect, useState } from "react";
import { Card } from "@/lib/ui/Card";
import { Button } from "@/lib/ui/Button";
import { Input } from "@/lib/ui/Input";
import { Select } from "@/lib/ui/Select";

export default function ExperimentsPage() {
  const [datasets, setDatasets] = useState<{ id: string; name: string; createdAt: string }[]>([]);
  const [datasetId, setDatasetId] = useState("");
  const [k, setK] = useState(8);
  const [seed, setSeed] = useState("maxey0-exp");
  const [sequenceName, setSequenceName] = useState("exp_sequence");
  const [steps, setSteps] = useState(16);
  const [result, setResult] = useState<any>(null);

  async function refreshDatasets() {
    const r = await fetch("/api/dataset/list");
    const j = await r.json();
    const ds = j.datasets ?? [];
    setDatasets(ds);
    if (!datasetId && ds.length) setDatasetId(ds[0].id);
  }
  useEffect(() => { refreshDatasets(); }, []);

  async function runTrilateration() {
    if (!datasetId) return;

    const ds = await (await fetch(`/api/dataset/${datasetId}`)).json();
    const points = (ds.points ?? []).map((p: any) => p.vec as number[]);
    if (points.length < 20) { alert("Need more points."); return; }

    const anchors = points.slice(0, k);
    const target = points[points.length - 1];
    const distances = anchors.map((a: number[]) => Math.hypot(...a.map((v, i) => target[i] - v)));

    const r = await fetch("/api/experiments/trilateration", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ anchors, distances, dim: target.length, seed, steps: 250, lr: 0.05, lambda: 1e-4, target }),
    });
    const j = await r.json();
    setResult(j);
  }

  async function runSequenceAndSnapshot() {
    if (!datasetId) return;
    const ds = await (await fetch(`/api/dataset/${datasetId}`)).json();
    const pts = (ds.points ?? []).slice(0, Math.max(steps, 2));
    if (!pts.length) return;

    const seriesRes = await fetch("/api/snapshots/series", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: sequenceName }),
    });
    const series = await seriesRes.json();

    for (let i = 0; i < pts.length; i++) {
      await fetch("/api/snapshots/record", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          seriesId: series.id,
          stepIndex: i,
          label: pts[i].label,
          text: pts[i].text ?? `sequence step ${i}`,
        }),
      });
    }

    setResult({ sequenceSeriesId: series.id, recorded: pts.length, message: "Sequence snapshots recorded into SQLite + KV-aware APIs." });
  }

  return (
    <div className="space-y-4">
      <div className="text-2xl font-semibold tracking-tight">Experiment Runner</div>

      <div className="grid grid-cols-3 gap-4">
        <Card title="Dataset">
          <div className="space-y-2">
            <div className="text-xs text-white/60">Dataset</div>
            <Select value={datasetId} onChange={(e) => setDatasetId(e.target.value)}>
              {datasets.map((d) => <option key={d.id} value={d.id}>{d.name} · {d.id}</option>)}
            </Select>
            <div className="text-xs text-white/60">seed</div>
            <Input value={seed} onChange={(e) => setSeed(e.target.value)} />
          </div>
        </Card>

        <Card title="Run sequences">
          <div className="space-y-2">
            <div className="text-xs text-white/60">Series name</div>
            <Input value={sequenceName} onChange={(e) => setSequenceName(e.target.value)} />
            <div className="text-xs text-white/60">Steps</div>
            <Input type="number" value={steps} onChange={(e) => setSteps(parseInt(e.target.value || "2", 10))} />
            <Button onClick={runSequenceAndSnapshot}>Record sequence snapshots</Button>
          </div>
        </Card>

        <Card title="Anchor-based trilateration">
          <div className="space-y-2">
            <div className="text-xs text-white/60">anchors (k)</div>
            <Input type="number" value={k} onChange={(e) => setK(parseInt(e.target.value || "3", 10))} />
            <Button onClick={runTrilateration}>Run trilateration</Button>
          </div>
        </Card>
      </div>

      <Card title="Result">
        <pre className="overflow-auto rounded-lg bg-black/40 p-3 text-xs">{JSON.stringify(result, null, 2)}</pre>
      </Card>
    </div>
  );
}
