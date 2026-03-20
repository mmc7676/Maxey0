"use client";

import { useEffect, useState } from "react";
import { Card } from "@/lib/ui/Card";
import { Button } from "@/lib/ui/Button";
import { Input } from "@/lib/ui/Input";

type DatasetRow = { id: string; name: string; createdAt: string };

export default function DatasetsPage() {
  const [datasets, setDatasets] = useState<DatasetRow[]>([]);
  const [name, setName] = useState("lab_dataset");
  const [seed, setSeed] = useState("maxey0");
  const [points, setPoints] = useState(400);
  const [stepsPerPoint, setStepsPerPoint] = useState(6);
  const [foldDim, setFoldDim] = useState(16);
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [details, setDetails] = useState<any | null>(null);

  async function refresh() {
    const r = await fetch("/api/dataset/list");
    const j = await r.json();
    setDatasets(j.datasets ?? []);
  }

  useEffect(() => { refresh(); }, []);

  async function generate() {
    setBusy(true);
    try {
      const r = await fetch("/api/dataset/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, seed, points, stepsPerPoint, foldDim }),
      });
      const j = await r.json();
      await refresh();
      setSelected(j.datasetId);
      await load(j.datasetId);
    } finally {
      setBusy(false);
    }
  }

  async function load(id: string) {
    const r = await fetch(`/api/dataset/${id}`);
    const j = await r.json();
    setDetails(j);
    setSelected(id);
  }

  return (
    <div className="space-y-4">
      <div className="text-2xl font-semibold tracking-tight">Dataset Generator</div>

      <div className="grid grid-cols-3 gap-4">
        <Card title="Generate synthetic dataset">
          <div className="space-y-2">
            <div className="text-xs text-white/60">Name</div>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
            <div className="text-xs text-white/60">Seed</div>
            <Input value={seed} onChange={(e) => setSeed(e.target.value)} />
            <div className="grid grid-cols-3 gap-2">
              <div>
                <div className="text-xs text-white/60">Points</div>
                <Input type="number" value={points} onChange={(e) => setPoints(parseInt(e.target.value || "1", 10))} />
              </div>
              <div>
                <div className="text-xs text-white/60">Steps/pt</div>
                <Input type="number" value={stepsPerPoint} onChange={(e) => setStepsPerPoint(parseInt(e.target.value || "1", 10))} />
              </div>
              <div>
                <div className="text-xs text-white/60">Fold dim</div>
                <Input type="number" value={foldDim} onChange={(e) => setFoldDim(parseInt(e.target.value || "2", 10))} />
              </div>
            </div>
            <Button onClick={generate} disabled={busy}>{busy ? "Generating…" : "Generate"}</Button>
            <div className="text-xs text-white/60">
              Folding simulates compression+reconstruction and logs per-step loss.
            </div>
          </div>
        </Card>

        <Card title="Existing datasets">
          <div className="space-y-1 max-h-[420px] overflow-auto pr-1">
            {datasets.map((d) => (
              <button
                key={d.id}
                onClick={() => load(d.id)}
                className={[
                  "w-full text-left rounded-lg border border-white/10 px-3 py-2 text-sm hover:bg-white/5",
                  selected === d.id ? "bg-white/10" : "bg-black/20",
                ].join(" ")}
              >
                <div className="font-semibold">{d.name}</div>
                <div className="text-xs text-white/60">{d.id} · {d.createdAt}</div>
              </button>
            ))}
          </div>
        </Card>

        <Card title="Export">
          {selected ? (
            <div className="space-y-2">
              <a
                className="inline-block rounded-lg border border-white/10 bg-white/10 px-3 py-2 text-sm hover:bg-white/15"
                href={`/api/export/dataset/${selected}/jsonl`}
              >
                Download JSONL
              </a>
              <div className="text-xs text-white/60">
                JSONL contains point vectors + per-point step metadata for training/analysis pipelines.
              </div>
            </div>
          ) : (
            <div className="text-sm text-white/70">Select a dataset to enable exports.</div>
          )}
        </Card>
      </div>

      <Card title="Dataset details">
        {details ? (
          <div className="space-y-2">
            <div className="text-xs text-white/60">Name: <b>{details.dataset?.name}</b> · Points loaded (UI cap): <b>{(details.points ?? []).length}</b></div>
            <div className="text-xs text-white/60">Config: <pre className="mt-1 overflow-auto rounded-lg bg-black/40 p-3 text-xs">{JSON.stringify(details.dataset?.config, null, 2)}</pre></div>
          </div>
        ) : (
          <div className="text-sm text-white/70">Generate or select a dataset.</div>
        )}
      </Card>
    </div>
  );
}
