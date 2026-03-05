import fs from "fs";
import path from "path";
import Database from "better-sqlite3";

const ROOT = process.cwd();
const DATA_DIR = path.join(ROOT, "data");
const DB_PATH = path.join(DATA_DIR, "latentlab.sqlite");

function ensureDir(p) {
  if (!fs.existsSync(p)) fs.mkdirSync(p, { recursive: true });
}

function migrate(db) {
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

function readJson(p) {
  return JSON.parse(fs.readFileSync(p, "utf-8"));
}

function upsertConstitution(db) {
  const id = "active";
  const p = path.join(DATA_DIR, "constitution.default.json");
  const constitution = readJson(p);
  const now = Date.now();
  db.prepare("INSERT OR REPLACE INTO constitution(id, value_json, created_at) VALUES(?,?,?)")
    .run(id, JSON.stringify(constitution), now);
}

function seedDataset(db) {
  const demoPath = path.join(DATA_DIR, "demo_latent_states.json");
  if (!fs.existsSync(demoPath)) {
    throw new Error(`Missing demo dataset: ${demoPath}`);
  }
  const demo = readJson(demoPath);

  const datasetId = "demo";
  const now = Date.now();

  const config = {
    kind: "demo_import",
    name: demo.name,
    seed: demo.seed,
    dimension_count: demo.dimension_count,
    source_file: "data/demo_latent_states.json",
    createdAt: demo.createdAt
  };

  db.prepare("INSERT OR REPLACE INTO datasets(id, name, config_json, created_at) VALUES(?,?,?,?)")
    .run(datasetId, demo.name || "Demo Latent States", JSON.stringify(config), now);

  const insert = db.prepare(`
    INSERT OR REPLACE INTO dataset_points(dataset_id, point_id, label, text, vec_json, meta_json, created_at)
    VALUES(?,?,?,?,?,?,?)
  `);

  const pts = Array.isArray(demo.points) ? demo.points : [];
  for (const p of pts) {
    const pointId = String(p.id);
    const label = p.label ?? null;
    const text = p.text ?? null;
    const vec = Array.isArray(p.vec) ? p.vec : Array.isArray(p.vector) ? p.vector : [];
    const meta = p.meta ?? {};
    insert.run(datasetId, pointId, label, text, JSON.stringify(vec), JSON.stringify(meta), now);
  }

  return { datasetId, points: pts.length };
}

function main() {
  ensureDir(DATA_DIR);

  const db = new Database(DB_PATH);
  try {
    migrate(db);
    upsertConstitution(db);
    const seeded = seedDataset(db);
    console.log(JSON.stringify({ ok: true, db: DB_PATH, ...seeded }, null, 2));
  } finally {
    db.close();
  }
}

main();
