import { z } from "zod";

export const zLaw = z.object({
  index: z.number().int().nonnegative(),
  id: z.string().min(1),
  tier: z.number().int().min(1).max(12),
  defaultWeight: z.number(),
  weight: z.number(),
  enabled: z.boolean(),
  label: z.string().min(1),
  desc: z.string().default(""),
  keywords: z.array(z.string()).default([]),
  source: z.string().default("unknown"),
});

export const zConstitution = z.object({
  version: z.string(),
  createdAt: z.string(),
  count: z.number().int().nonnegative(),
  laws: z.array(zLaw),
});

export type Law = z.infer<typeof zLaw>;
export type Constitution = z.infer<typeof zConstitution>;

export function tokenize(s: string): string[] {
  return (s.toLowerCase().match(/[a-z0-9]+/g) ?? []).slice(0, 4096);
}

export function lawTokenSet(law: Law): Set<string> {
  const toks = new Set<string>();
  for (const t of tokenize(law.label + " " + law.desc)) toks.add(t);
  for (const t of law.keywords ?? []) toks.add(t.toLowerCase());
  return toks;
}

export function cosineBinaryOverlap(a: Set<string>, b: Set<string>): number {
  if (a.size === 0 || b.size === 0) return 0;
  let overlap = 0;
  for (const t of a) if (b.has(t)) overlap++;
  return overlap / Math.sqrt(a.size * b.size);
}

/**
 * Deterministic “constitution-axis” embedding:
 * - Returns a 64D vector where each dimension is a law score in [-1, 1] scaled by its weight.
 */
export function embedByConstitution(text: string, constitution: Constitution): number[] {
  const laws = constitution.laws;
  if (laws.length === 0) return [];
  const textSet = new Set(tokenize(text));
  const out: number[] = new Array(laws.length).fill(0);
  for (let i = 0; i < laws.length; i++) {
    const law = laws[i];
    if (!law.enabled) { out[i] = 0; continue; }
    const s = cosineBinaryOverlap(textSet, lawTokenSet(law)); // [0..1]
    const scaled = (2 * s - 1); // [-1..1]
    const w = (law.weight ?? law.defaultWeight ?? 0) / 100;
    out[i] = scaled * w;
  }
  return out;
}
