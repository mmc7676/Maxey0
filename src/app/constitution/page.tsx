"use client";

import { useEffect, useMemo, useState } from "react";
import { Card } from "@/lib/ui/Card";
import { Button } from "@/lib/ui/Button";
import { Input } from "@/lib/ui/Input";
import type { Constitution, Law } from "@/lib/constitution";

function clamp(n: number, lo: number, hi: number) { return Math.max(lo, Math.min(hi, n)); }

export default function ConstitutionPage() {
  const [loading, setLoading] = useState(true);
  const [constitution, setConstitution] = useState<Constitution | null>(null);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    (async () => {
      const r = await fetch("/api/constitution");
      const j = await r.json();
      setConstitution(j);
      setLoading(false);
    })();
  }, []);

  const laws = useMemo(() => {
    const xs = constitution?.laws ?? [];
    if (!filter.trim()) return xs;
    const q = filter.toLowerCase();
    return xs.filter(l => (l.label + " " + l.desc + " " + (l.keywords ?? []).join(" ")).toLowerCase().includes(q));
  }, [constitution, filter]);

  const tierCounts = useMemo(() => {
    const m = new Map<number, number>();
    for (const l of constitution?.laws ?? []) m.set(l.tier, (m.get(l.tier) ?? 0) + 1);
    return [...m.entries()].sort((a,b)=>a[0]-b[0]);
  }, [constitution]);

  async function save() {
    if (!constitution) return;
    await fetch("/api/constitution", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(constitution) });
    alert("Saved.");
  }

  if (loading) return <div>Loading…</div>;
  if (!constitution) return <div>Failed to load constitution.</div>;

  return (
    <div className="space-y-4">
      <div className="text-2xl font-semibold tracking-tight">Constitution Designer</div>

      <div className="grid grid-cols-3 gap-4">
        <Card title="Controls">
          <div className="space-y-2">
            <div className="text-xs text-white/60">Filter</div>
            <Input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="search laws..." />
            <div className="flex gap-2">
              <Button onClick={save}>Save</Button>
              <Button variant="ghost" onClick={() => setFilter("")}>Clear</Button>
            </div>
            <div className="mt-3 text-xs text-white/60">
              Loaded: <b>{constitution.laws.length}</b> laws · tiers:{" "}
              {tierCounts.map(([t,c]) => <span key={t} className="mr-2">T{t}:{c}</span>)}
            </div>
          </div>
        </Card>

        <Card title="Axis semantics">
          <div className="space-y-2 text-sm">
            Each axis is a law score in <b>[-1, 1]</b> scaled by its weight.
            Default embedding uses token overlap (deterministic). Replace with your own embedding provider if desired.
          </div>
        </Card>

        <Card title="Notes">
          <div className="space-y-2 text-sm">
            The source file includes 62 laws; two additional laws were appended to reach 64 (editable).
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-3">
        {laws.map((law) => (
          <LawRow
            key={law.id}
            law={law}
            onChange={(next) => {
              setConstitution((prev) => {
                if (!prev) return prev;
                return { ...prev, laws: prev.laws.map((x) => (x.id === law.id ? next : x)) };
              });
            }}
          />
        ))}
      </div>
    </div>
  );
}

function LawRow({ law, onChange }: { law: Law; onChange: (l: Law) => void }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-sm font-semibold">{law.label} <span className="text-xs text-white/60">({law.id})</span></div>
          <div className="mt-1 text-xs text-white/70">{law.desc}</div>
        </div>

        <div className="flex items-center gap-3">
          <label className="text-xs text-white/70">Tier</label>
          <input
            type="number"
            value={law.tier}
            min={1}
            max={12}
            onChange={(e) => onChange({ ...law, tier: clamp(parseInt(e.target.value || "1", 10), 1, 12) })}
            className="w-16 rounded-lg border border-white/10 bg-black/30 px-2 py-1 text-sm"
          />
          <label className="text-xs text-white/70">Weight</label>
          <input
            type="number"
            value={law.weight}
            min={0}
            max={100}
            onChange={(e) => onChange({ ...law, weight: clamp(parseFloat(e.target.value || "0"), 0, 100) })}
            className="w-20 rounded-lg border border-white/10 bg-black/30 px-2 py-1 text-sm"
          />
          <label className="text-xs text-white/70">Enabled</label>
          <input
            type="checkbox"
            checked={law.enabled}
            onChange={(e) => onChange({ ...law, enabled: e.target.checked })}
          />
        </div>
      </div>

      <div className="mt-3">
        <div className="text-xs text-white/60">Keywords (comma-separated)</div>
        <input
          value={(law.keywords ?? []).join(", ")}
          onChange={(e) => onChange({ ...law, keywords: e.target.value.split(",").map(s => s.trim()).filter(Boolean).slice(0, 128) })}
          className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm"
        />
      </div>
    </div>
  );
}
