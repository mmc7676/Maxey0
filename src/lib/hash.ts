import crypto from "crypto";

export function sha256Hex(input: string): string {
  return crypto.createHash("sha256").update(input).digest("hex");
}

export function stableJson(obj: unknown): string {
  return JSON.stringify(obj, (_k, v) => {
    if (v && typeof v === "object" && !Array.isArray(v)) {
      const entries = Object.entries(v as Record<string, unknown>).sort(([a],[b]) => a.localeCompare(b));
      return Object.fromEntries(entries);
    }
    return v;
  });
}
