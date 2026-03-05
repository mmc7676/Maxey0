import { db } from "@/server/db";

export function kvGet(key: string): unknown | null {
  const row = db().prepare("SELECT value_json, expires_at FROM kv_cache WHERE key = ?").get(key) as { value_json: string; expires_at: number | null } | undefined;
  if (!row) return null;
  if (row.expires_at !== null && Date.now() > row.expires_at) {
    db().prepare("DELETE FROM kv_cache WHERE key = ?").run(key);
    return null;
  }
  return JSON.parse(row.value_json);
}

export function kvSet(key: string, value: unknown, ttlSeconds?: number): void {
  const now = Date.now();
  const expiresAt = ttlSeconds ? now + ttlSeconds * 1000 : null;
  db().prepare(`
    INSERT INTO kv_cache(key, value_json, created_at, expires_at)
    VALUES(?,?,?,?)
    ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, created_at=excluded.created_at, expires_at=excluded.expires_at
  `).run(key, JSON.stringify(value), now, expiresAt);
}

export function kvStats(): { count: number; expiredCleared: number } {
  const now = Date.now();
  const del = db().prepare("DELETE FROM kv_cache WHERE expires_at IS NOT NULL AND expires_at < ?").run(now);
  const row = db().prepare("SELECT COUNT(*) AS c FROM kv_cache").get() as { c: number };
  return { count: row.c, expiredCleared: del.changes };
}
