"use client";

import { useState } from "react";
import { Card } from "@/lib/ui/Card";
import { Button } from "@/lib/ui/Button";
import { Input } from "@/lib/ui/Input";

type SeedRow = { scwId: string; label: string; text: string; vec: number[] };

export default function ScwSeedsPage() {
  const [scwId, setScwId] = useState("SCW0");
  const [label, setLabel] = useState("init");
  const [text, setText] = useState("Initialize SCW0 with strict observability and snapshot differencing.");
  const [rows, setRows] = useState<SeedRow[]>([]);
  const [dim, setDim] = useState<number | null>(null);

  async function ensureSeedSeries(): Promise<string> {
    const list = await fetch("/api/snapshots/series");
    const lj = await list.json();
    const found = (lj.series ?? []).find((s: any) => s.name === "__scw_seeds__");
    if (found) return found.id;
    const created = await fetch("/api/snapshots/series", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: "__scw_seeds__" }) });
    const cj = await created.json();
    return cj.id;
  }

  async function add() {
    const r = await fetch("/api/constitution");
    const constitution = await r.json();
    setDim(constitution.laws.length);

    const seriesId = await ensureSeedSeries();
    await fetch("/api/snapshots/record", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ seriesId, stepIndex: rows.length, label: `${scwId}:${label}`, text }),
    });

    const s = await fetch(`/api/snapshots/series/${seriesId}`);
    const sj = await s.json();
    const last = (sj.snapshots ?? [])[sj.snapshots.length - 1];
    setRows((prev) => [...prev, { scwId, label, text, vec: last.vec }]);
  }

  function exportJson() {
    const payload = {
      version: "0.1.0",
      dim,
      seeds: rows.map(r => ({
        scw_id: r.scwId,
        label: r.label,
        text: r.text,
        vec64: r.vec,
      })),
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "scw_seeds.json";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-4">
      <div className="text-2xl font-semibold tracking-tight">SCW Seeds</div>

      <div className="grid grid-cols-3 gap-4">
        <Card title="Create seed">
          <div className="space-y-2">
            <div className="grid grid-cols-2 gap-2">
              <div>
                <div className="text-xs text-white/60">SCW id</div>
                <Input value={scwId} onChange={(e) => setScwId(e.target.value)} />
              </div>
              <div>
                <div className="text-xs text-white/60">label</div>
                <Input value={label} onChange={(e) => setLabel(e.target.value)} />
              </div>
            </div>
            <div className="text-xs text-white/60">seed text → constitution-axis vector</div>
            <Input value={text} onChange={(e) => setText(e.target.value)} />
            <Button onClick={add}>Add seed</Button>
          </div>
        </Card>

        <Card title="Export">
          <div className="space-y-2">
            <Button onClick={exportJson} disabled={rows.length === 0}>Download seeds.json</Button>
            <div className="text-xs text-white/60">
              Vectors are embedded deterministically from text using your constitution weights.
            </div>
          </div>
        </Card>

        <Card title="Why">
          <div className="space-y-2 text-sm">
            Assign starting latent coordinates to SCWs so your runtime can place each SCW into the same address space used for snapshots.
          </div>
        </Card>
      </div>

      <Card title="Seeds">
        <div className="space-y-2 max-h-[560px] overflow-auto pr-1">
          {rows.map((r, i) => (
            <div key={i} className="rounded-lg border border-white/10 bg-black/20 p-3">
              <div className="text-sm font-semibold">{r.scwId} · {r.label}</div>
              <div className="mt-1 text-xs text-white/70">{r.text}</div>
              <div className="mt-2 text-xs text-white/60">vec64[{r.vec.length}]</div>
              <pre className="mt-1 overflow-auto rounded-lg bg-black/40 p-3 text-xs">{JSON.stringify(r.vec.slice(0, 16))} …</pre>
            </div>
          ))}
          {rows.length === 0 ? <div className="text-sm text-white/70">Add a seed to start.</div> : null}
        </div>
      </Card>
    </div>
  );
}
