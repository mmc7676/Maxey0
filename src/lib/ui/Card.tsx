"use client";

export function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-white/10 bg-white/5 p-4">
      <div className="text-sm font-semibold text-white/90">{title}</div>
      <div className="mt-3 text-sm text-white/80">{children}</div>
    </section>
  );
}
