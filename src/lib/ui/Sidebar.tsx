"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/", label: "Overview" },
  { href: "/constitution", label: "1) Constitution Designer" },
  { href: "/mapper", label: "2) Latent Space Mapper" },
  { href: "/experiments", label: "3) Experiment Runner" },
  { href: "/dual-graph", label: "4) Geometry View" },
  { href: "/datasets", label: "5) Dataset Generator" },
  { href: "/observability", label: "6) Observability" },
  { href: "/snapshots", label: "Snapshots + KV Cache" },
  { href: "/scw-seeds", label: "SCW Seeds" },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="w-72 border-r border-white/10 bg-[#070b17] p-5">
      <div className="text-lg font-semibold tracking-tight">Maxey0 Latent Space Lab</div>
      <div className="mt-2 text-xs text-white/60">
        Snapshot-first observability · Voronoi partitions · Delaunay dual graph · KV cached measurements
      </div>

      <nav className="mt-6 space-y-1">
        {NAV.map((n) => {
          const active = pathname === n.href;
          return (
            <Link
              key={n.href}
              href={n.href}
              className={[
                "block rounded-lg px-3 py-2 text-sm",
                active ? "bg-white/10" : "hover:bg-white/5",
              ].join(" ")}
            >
              {n.label}
            </Link>
          );
        })}
      </nav>

      <div className="mt-6 rounded-lg border border-white/10 p-3 text-xs text-white/70">
        <div className="font-semibold text-white/85">Local-first</div>
        <div className="mt-1">
          Runs on your machine with SQLite persistence. No external embeddings required (deterministic scoring + pluggable providers).
        </div>
      </div>
    </aside>
  );
}
