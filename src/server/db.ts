import Database from "better-sqlite3";
import { dbPath, ensureDataDir } from "@/server/paths";

let dbSingleton: Database.Database | null = null;

function migrate(db: Database.Database) {
  db.exec(`
    PRAGMA journal_mode = WAL;
    PRAGMA synchronous = NORMAL;

    CREATE TABLE IF NOT EXISTS kv_cache (
      key TEXT PRIMARY KEY,
      value_json TEXT NOT NULL,
      created_at INTEGER NOT NULL,
      expires_at INTEGER
    );

    CREATE TABLE IF NOT EXISTS constitution (
      id TEXT PRIMARY KEY,
      value_json TEXT NOT NULL,
      created_at INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS datasets (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      config_json TEXT NOT NULL,
      created_at INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS dataset_points (
      dataset_id TEXT NOT NULL,
      point_id TEXT NOT NULL,
      label TEXT,
      text TEXT,
      vec_json TEXT NOT NULL,
      meta_json TEXT NOT NULL,
      created_at INTEGER NOT NULL,
      PRIMARY KEY(dataset_id, point_id)
    );

    CREATE TABLE IF NOT EXISTS snapshot_series (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      created_at INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS snapshots (
      id TEXT PRIMARY KEY,
      series_id TEXT NOT NULL,
      step_index INTEGER NOT NULL,
      label TEXT NOT NULL,
      text TEXT,
      vec_json TEXT NOT NULL,
      meta_json TEXT NOT NULL,
      created_at INTEGER NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_snapshots_series_step ON snapshots(series_id, step_index);
  `);
}

export function db(): Database.Database {
  if (dbSingleton) return dbSingleton;
  ensureDataDir();
  const d = new Database(dbPath());
  migrate(d);
  dbSingleton = d;
  return d;
}
