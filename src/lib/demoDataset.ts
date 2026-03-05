import fs from "node:fs";
import path from "node:path";

type DemoPoint = {
  id: string;
  label: string;
  text?: string;
  vec: number[];
  meta?: Record<string, unknown>;
};

type DemoDataset = {
  name: string;
  seed: string;
  dimension_count: number;
  createdAt: string;
  points: DemoPoint[];
};

const DEMO_ID = "demo_latent_states";

export function demoDatasetId() {
  return DEMO_ID;
}

export function loadDemoDataset(): DemoDataset {
  const filePath = path.join(process.cwd(), "data", "demo_latent_states.json");
  const raw = fs.readFileSync(filePath, "utf8");
  return JSON.parse(raw) as DemoDataset;
}

