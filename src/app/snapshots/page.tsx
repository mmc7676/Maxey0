"use client";

import { useEffect, useMemo, useState } from "react";
import { Card } from "@/lib/ui/Card";
import { Button } from "@/lib/ui/Button";
import { Input } from "@/lib/ui/Input";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

type SeriesRow = { id: string; name: string; createdAt: string };

export default function SnapshotsPage() {
  const [series, setSeries] = useState<SeriesRow[]>([]);
  const [activeSeries, setActiveSeries] = useState<string>("");
  const [seriesName, setSeriesName] = useState("run_1");
  const [stepIndex, setStepIndex] = useState(0);
  const [label, setLabel] = useState("pre");
  const [text, setText] = useState("snapshot text");
  const [snapshots, setSnapshots] = useState<any[]>([]);
  const [health, setHealth] = useState<any>(null);

  async function refresh() {
    const r = await fetch("/api/snapshots/series");
    const j = await r.json();
    setSeries(j.series ?? []);
    if (!activeSeries && (j.series ?? []).length) setActiveSeries(j.series[0].id);
  }

  async function loadSeries(id: string) {
    const r = await fetch(`/api/snapshots/series/${id}`);
    const j = await r.json();
    setSnapshots(j.snapshots ?? []);
    setActiveSeries(id);
    setStepIndex((j.snapshots ?? []).length);
  }

  async function createSeries() {
    const r = await fetch("/api/snapshots/series", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: seriesName }) });
    const j = await r.json();
    await refresh();
    await loadSeries(j.id);
  }

  async function record() {
    if (!activeSeries) return;
    await fetch("/api/snapshots/record", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ seriesId: activeSeries, stepIndex, label, text }),
    });
    await loadSeries(activeSeries);
  }

  async function loadHealth() {
    const r = await fetch("/api/health");
    const j = await r.json();
    setHealth(j);
  }

  useEffect(() => { refresh(); loadHealth(); }, []);

  const deltaSeries = useMemo(() => {
    const ds: { step: number; deltaL2: number }[] = [];
    for (let i = 1; i < snapshots.length; i++) {
      const a = snapshots[i-1].vec as number[];
      const b = snapshots[i].vec as number[];
      let s = 0;
      for (let k = 0; k < a.length; k++) { const d = b[k] - a[k]; s += d*d; }
      ds.push({ step: snapshots[i].stepIndex, deltaL2: Math.sqrt(s) });
    }
    return ds;
  }, [snapshots]);

  return (
    <div className="space-y-4">
      <div className="text-2xl font-semibold tracking-tight">Snapshots + KV Cache</div>

      <div className="grid grid-cols-3 gap-4">
        <Card title="Series">
          <div className="space-y-2">
            <div className="text-xs text-white/60">Create new series</div>
            <Input value={seriesName} onChange={(e) => setSeriesName(e.target.value)} />
            <Button onClick={createSeries}>Create</Button>
            <div className="mt-2 text-xs text-white/60">Load existing</div>
            <div className="max-h-[240px] overflow-auto pr-1 space-y-1">
              {series.map(s => (
                <button key={s.id} onClick={() => loadSeries(s.id)}
                  className={[
                    "w-full text-left rounded-lg border border-white/10 px-3 py-2 text-sm hover:bg-white/5",
                    activeSeries === s.id ? "bg-white/10" : "bg-black/20",
                  ].join(" ")}
                >
                  <div className="font-semibold">{s.name}</div>
                  <div className="text-xs text-white/60">{s.id}</div>
                </button>
              ))}
            </div>
          </div>
        </Card>

        <Card title="Record snapshot">
          <div className="space-y-2">
            <div className="grid grid-cols-2 gap-2">
              <div>
                <div className="text-xs text-white/60">step</div>
                <Input type="number" value={stepIndex} onChange={(e) => setStepIndex(parseInt(e.target.value || "0", 10))} />
              </div>
              <div>
                <div className="text-xs text-white/60">label</div>
                <Input value={label} onChange={(e) => setLabel(e.target.value)} />
              </div>
            </div>
            <div className="text-xs text-white/60">text (auto-embedded via constitution)</div>
            <Input value={text} onChange={(e) => setText(e.target.value)} />
            <Button onClick={record} disabled={!activeSeries}>Record</Button>
          </div>
        </Card>

        <Card title="KV cache status">
          <div className="space-y-2">
            <Button variant="ghost" onClick={loadHealth}>Refresh</Button>
            <pre className="overflow-auto rounded-lg bg-black/40 p-3 text-xs">{JSON.stringify(health, null, 2)}</pre>
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Card title="Snapshot list">
          <div className="max-h-[520px] overflow-auto pr-1 space-y-2">
            {snapshots.map(s => (
              <div key={s.id} className="rounded-lg border border-white/10 bg-black/20 p-3">
                <div className="text-sm font-semibold">{s.stepIndex}: {s.label}</div>
                <div className="mt-1 text-xs text-white/70">{s.text ?? ""}</div>
              </div>
            ))}
          </div>
        </Card>

        <Card title="ΔL2 over time">
          <div className="h-[520px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={deltaSeries}>
                <XAxis dataKey="step" tick={{ fill: "#cbd5e1" }} />
                <YAxis tick={{ fill: "#cbd5e1" }} />
                <Tooltip contentStyle={{ background: "#0b1020", border: "1px solid rgba(255,255,255,0.1)" }} />
                <Line type="monotone" dataKey="deltaL2" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>
    </div>
  );
}
