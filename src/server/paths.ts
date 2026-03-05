import path from "path";
import fs from "fs";

export function ensureDataDir(): string {
  const p = path.join(process.cwd(), "data");
  if (!fs.existsSync(p)) fs.mkdirSync(p, { recursive: true });
  return p;
}

export function dbPath(): string {
  return path.join(ensureDataDir(), "latentlab.sqlite");
}
