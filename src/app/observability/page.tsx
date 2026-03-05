"use client";

import { useEffect, useMemo, useState } from "react";
import { Card } from "@/lib/ui/Card";
import { Button } from "@/lib/ui/Button";
import { Select } from "@/lib/ui/Select";

export default function ObservabilityPage() {
  const [series, setSeries] = useState<{ id: string; name: string; createdAt: string }[]>([]);
  const [activeSeries, setActiveSeries] = useState("");
  const [snapshots, setSnapshots] = useState<any[]>([]);
  const [cursor, setCursor] = useState(0);
  const [playing, setPlaying] = useState(false);

  async function refresh() {
    const r = await fetch("/api/snapshots/series");
    const j = await r.json();
    setSeries(j.series ?? []);
    if (!activeSeries && j.series?.length) {
      setActiveSeries(j.series[0].id);
      await loadSeries(j.series[0].id);
    }
  }

  async function loadSeries(id: string) {
    const r = await fetch(`/api/snapshots/series/${id}`);
    const j = await r.json();
    setSnapshots(j.snapshots ?? []);
    setActiveSeries(id);
    setCursor(0);
    setPlaying(false);
  }

  useEffect(() => { refresh(); }, []);

  useEffect(() => {
    if (!playing || snapshots.length < 2) return;
    const timer = window.setInterval(() => setCursor((p) => (p + 1) % snapshots.length), 500);
    return () => window.clearInterval(timer);
  }, [playing, snapshots.length]);

  const current = snapshots[cursor];
  const transition = useMemo(() => {
    if (cursor === 0 || !snapshots[cursor - 1] || !current) return null;
    const prev = snapshots[cursor - 1].vec as number[];
    const next = current.vec as number[];
    let l2 = 0;
    for (let i = 0; i < prev.length; i++) {
      const d = next[i] - prev[i];
      l2 += d * d;
    }
    return { from: snapshots[cursor - 1].label, to: current.label, deltaL2: Math.sqrt(l2) };
  }, [snapshots, cursor, current]);

  return (
    <div className="space-y-4">
      <div className="text-2xl font-semibold tracking-tight">Observability</div>
      <div className="grid grid-cols-3 gap-4">
        <Card title="Replay control">
          <div className="space-y-2">
            <div className="text-xs text-white/60">Series</div>
            <Select value={activeSeries} onChange={(e) => loadSeries(e.target.value)}>
              {series.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </Select>
            <div className="flex gap-2">
              <Button variant="ghost" onClick={() => setPlaying((s) => !s)} disabled={snapshots.length < 2}>{playing ? "Pause" : "Play"}</Button>
              <Button variant="ghost" onClick={() => setCursor((c) => Math.max(c - 1, 0))}>Prev</Button>
              <Button variant="ghost" onClick={() => setCursor((c) => Math.min(c + 1, Math.max(snapshots.length - 1, 0)))}>Next</Button>
            </div>
          </div>
        </Card>
        <Card title="State transition">
          {transition ? (
            <div className="text-sm space-y-1">
              <div>{transition.from} → {transition.to}</div>
              <div>ΔL2: <b>{transition.deltaL2.toFixed(4)}</b></div>
            </div>
          ) : <div className="text-sm text-white/70">Move replay cursor to inspect transitions.</div>}
        </Card>
        <Card title="Snapshot detail">
          <div className="text-xs text-white/70">Step {current?.stepIndex ?? 0}: {current?.label ?? "n/a"}</div>
          <div className="mt-2 text-xs">{current?.text ?? "No snapshots yet."}</div>
        </Card>
      </div>
    </div>
  );
}
