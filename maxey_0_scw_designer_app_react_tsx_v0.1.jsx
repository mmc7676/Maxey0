import React, { useEffect, useMemo, useRef, useState } from "react";

/**
 * maxey0-scw-designer (!app)
 * - Self-contained (no external deps)
 * - Drag/drop + pan/zoom + edges
 * - SCWs are visual containers; Agents can live inside/outside SCWs
 * - Add Agent / Add SCW spawns next ordinal (+1), but ordinals are editable
 * - Maxey00 supported as superposition/observability agent
 * - 32-color palette + 32 default agent specializations + parameterized SCW runtime features
 * - Latent-space framing: nodes have high-D latent vectors; UI projects to 2D w/ depth (z) cues
 */

type Maxey0NodeKind = "agent" | "scw" | "maxey00";

type Maxey0MemoryScope = "sp" | "ep" | "pr" | "pm";

type Maxey0AgentSpecKey =
  | "Orchestrator"
  | "Planner"
  | "Recursor"
  | "Validator"
  | "TypeScriptDev"
  | "PythonDev"
  | "RustDev"
  | "GoDev"
  | "CSharpDev"
  | "DevOps"
  | "Security"
  | "Observability"
  | "DataEngineer"
  | "GraphEngineer"
  | "VectorSearch"
  | "RAG"
  | "PromptEngineer"
  | "ToolingEngineer"
  | "UIUX"
  | "Product"
  | "TestEngineer"
  | "Performance"
  | "DistributedSystems"
  | "APIDesign"
  | "DatabaseTuning"
  | "Kubernetes"
  | "Terraform"
  | "IncidentCommander"
  | "Compliance"
  | "Research"
  | "SyntheticData"
  | "MemoryEngineer";

type Maxey0AgentSpec = {
  key: Maxey0AgentSpecKey;
  label: string;
  description: string;
  defaultTools: string[];
};

type Maxey0ScwRuntimePreset = {
  /** container image/tag, or runtime descriptor */
  runtime: "python" | "node" | "dotnet" | "rust" | "go" | "container";
  /** determinism mode */
  determinismPolicy: "strict" | "best-effort" | "strict+hash-chain";
  /** logging */
  tickLoggingRequired: boolean;
  runHeaderRequired: boolean;
  verificationBlockRequired: boolean;
  /** resources */
  cpu: number; // vCPU
  memoryMb: number;
  diskMb: number;
  network: "none" | "egress" | "egress+ingress";
  /** adapters */
  toolAdapters: string[];
  /** time source */
  timeSource: "monotonic+wall" | "monotonic" | "wall";
};

type Maxey0Latent = {
  // high-D (fixed length) but only some dims used for projection
  v: number[]; // length 16
};

type Maxey0Node = {
  id: string;
  kind: Maxey0NodeKind;

  /** display label on node */
  label: string;

  /** Optional deterministic ordinal label. Editable and NOT coupled to specialization. */
  deterministicOrdinal?: number; // e.g. 9 => "Maxey9" or "SCW9"

  /** If present, rendered as "Maxey#" / "SCW#" and used for deterministic pipelines on export */
  deterministicEnabled: boolean;

  colorHex: string;

  // world (canvas) coords
  x: number;
  y: number;
  w: number;
  h: number;

  // latent space
  latent: Maxey0Latent;

  tags: string[];
  properties: Record<string, string | number | boolean | null>;

  // containment
  parentScwId?: string | null;

  agent?: {
    specializationKey: Maxey0AgentSpecKey;
    specializationLabel: string;
    specializationDescription: string;
    tools: string[];
    memoryScope: Maxey0MemoryScope;
    notes: string;
  };

  scw?: {
    purpose: string;
    runtimePreset: Maxey0ScwRuntimePreset;
  };

  maxey00?: {
    // observability radius (purely visual + edge semantics)
    observability: "global" | "multi-scw" | "local";
    notes: string;
  };
};

type Maxey0EdgeKind =
  | "calls"
  | "routes_to"
  | "promotes_to"
  | "logs_to"
  | "reads_from"
  | "writes_to"
  | "depends_on"
  | "observes";

type Maxey0Edge = {
  id: string;
  sourceId: string;
  targetId: string;
  kind: Maxey0EdgeKind;
  label: string;
  properties: Record<string, string | number | boolean | null>;
};

type ExportPayload = {
  version: "2.0.0";
  exportedAtIso: string;
  nodes: Maxey0Node[];
  edges: Maxey0Edge[];
  ui: {
    panX: number;
    panY: number;
    zoom: number;
    latentZScale: number;
    latentDepthMode: "shadow" | "parallax";
  };
  /** optional deterministic mapping: user can enforce deterministic IDs externally */
  deterministic?: {
    agents?: Record<string, number>; // nodeId->Maxey#
    scws?: Record<string, number>; // nodeId->SCW#
  };
};

const MAXEY0_STORAGE_KEY = "maxey0_scw_designer_app_v2";

const PALETTE_32: ReadonlyArray<{ id: string; name: string; hex: string }> = Object.freeze([
  { id: "c01", name: "Neon Green", hex: "#00FF7F" },
  { id: "c02", name: "Electric Blue", hex: "#00A3FF" },
  { id: "c03", name: "Hot Magenta", hex: "#FF00F5" },
  { id: "c04", name: "Cyber Yellow", hex: "#FFE600" },
  { id: "c05", name: "Signal Orange", hex: "#FF6A00" },
  { id: "c06", name: "Crimson", hex: "#FF2D55" },
  { id: "c07", name: "Aqua", hex: "#00FFD5" },
  { id: "c08", name: "Violet", hex: "#8B5CFF" },
  { id: "c09", name: "Lime", hex: "#B6FF00" },
  { id: "c10", name: "Sky", hex: "#4CC9FF" },
  { id: "c11", name: "Rose", hex: "#FF4D8D" },
  { id: "c12", name: "Amber", hex: "#FFB300" },
  { id: "c13", name: "Mint", hex: "#2EFEB7" },
  { id: "c14", name: "Indigo", hex: "#3B5BFF" },
  { id: "c15", name: "Fuchsia", hex: "#E800FF" },
  { id: "c16", name: "Chartreuse", hex: "#7CFF00" },
  { id: "c17", name: "Cyan", hex: "#00E5FF" },
  { id: "c18", name: "Purple", hex: "#B000FF" },
  { id: "c19", name: "Gold", hex: "#FFD166" },
  { id: "c20", name: "Coral", hex: "#FF7A59" },
  { id: "c21", name: "Teal", hex: "#00C2A8" },
  { id: "c22", name: "Azure", hex: "#0077FF" },
  { id: "c23", name: "Pink", hex: "#FF3CAC" },
  { id: "c24", name: "Sunset", hex: "#FF5E3A" },
  { id: "c25", name: "Acid", hex: "#A8FF00" },
  { id: "c26", name: "Ice", hex: "#7AE7FF" },
  { id: "c27", name: "Lilac", hex: "#C77DFF" },
  { id: "c28", name: "Copper", hex: "#FF9F1C" },
  { id: "c29", name: "Seafoam", hex: "#64FFDA" },
  { id: "c30", name: "Ultramarine", hex: "#1C4FFF" },
  { id: "c31", name: "Infrared", hex: "#FF0033" },
  { id: "c32", name: "Plasma", hex: "#FF00A8" }
]);

const MAXEY0_AGENT_SPECS: ReadonlyArray<Maxey0AgentSpec> = Object.freeze([
  {
    key: "Orchestrator",
    label: "Orchestrator Agent",
    description: "Coordinates multi-agent execution, enforces routing/precedence, and maintains deterministic run control.",
    defaultTools: ["route.classify", "plan.compile", "run.dispatch"]
  },
  {
    key: "Planner",
    label: "Planner Agent",
    description: "Converts objectives into a stepwise plan with dependencies, milestones, and acceptance criteria.",
    defaultTools: ["plan.decompose", "plan.validate"]
  },
  {
    key: "Recursor",
    label: "Recursor Agent",
    description: "Performs depth-first exploration of design space, enumerating alternatives with bounded branching.",
    defaultTools: ["search.tree", "prune.rank"]
  },
  {
    key: "Validator",
    label: "Validator Agent",
    description: "Checks invariants, schemas, determinism rules, and refuses unverifiable claims.",
    defaultTools: ["schema.validate", "diff.check", "policy.enforce"]
  },
  {
    key: "TypeScriptDev",
    label: "TypeScript/React Developer Agent",
    description: "You are a world-class TypeScript/React/JavaScript engineer who produces production-grade UI code.",
    defaultTools: ["ts.build", "ui.review", "bundle.optimize"]
  },
  {
    key: "PythonDev",
    label: "Python Developer Agent",
    description: "Builds production-grade Python services, CLIs, and data pipelines with tests and determinism controls.",
    defaultTools: ["py.build", "py.test", "py.lint"]
  },
  {
    key: "RustDev",
    label: "Rust Systems Agent",
    description: "Implements high-performance, memory-safe components (FFI, parsers, networking) in Rust.",
    defaultTools: ["rust.build", "bench", "ffi.gen"]
  },
  {
    key: "GoDev",
    label: "Go Backend Agent",
    description: "Builds concurrent Go services, CLIs, and distributed components with strong observability.",
    defaultTools: ["go.build", "go.test", "otel.instrument"]
  },
  {
    key: "CSharpDev",
    label: "C#/.NET Agent",
    description: "Develops .NET services, plugins, and enterprise integrations (identity, Graph, Azure).",
    defaultTools: ["dotnet.build", "dotnet.test", "nuget.pack"]
  },
  {
    key: "DevOps",
    label: "DevOps Agent",
    description: "Owns CI/CD, Docker, release automation, and environment reproducibility.",
    defaultTools: ["ci.generate", "docker.build", "release.cut"]
  },
  {
    key: "Security",
    label: "Security Agent",
    description: "Threat models designs, applies least privilege, secret handling, and secure-by-default configs.",
    defaultTools: ["threat.model", "secrets.scan", "policy.enforce"]
  },
  {
    key: "Observability",
    label: "Observability Agent",
    description: "Designs traces/logs/metrics, defines SLOs, and builds verification-grade run transcripts.",
    defaultTools: ["otel.instrument", "trace.grade", "log.schema"]
  },
  {
    key: "DataEngineer",
    label: "Data Engineering Agent",
    description: "Builds ETL/ELT, streaming pipelines, and robust data contracts.",
    defaultTools: ["etl.design", "schema.evolve", "pipeline.verify"]
  },
  {
    key: "GraphEngineer",
    label: "Neo4j/Graph Agent",
    description: "Designs property graphs, Cypher lineage, and graph-resident workflows.",
    defaultTools: ["cypher.model", "index.tune", "lineage.emit"]
  },
  {
    key: "VectorSearch",
    label: "Vector Search Agent",
    description: "Designs vector indexing, ANN parameters, recall/latency tradeoffs, and evaluation.",
    defaultTools: ["vector.index", "ann.tune", "eval.retrieval"]
  },
  {
    key: "RAG",
    label: "RAG Agent",
    description: "Builds retrieval-augmented generation pipelines with chunking, reranking, and guardrails.",
    defaultTools: ["chunk.plan", "rerank", "grounding.check"]
  },
  {
    key: "PromptEngineer",
    label: "Prompt/Instruction Engineer",
    description: "Authors reliable prompting contracts, tool calling protocols, and control tokens.",
    defaultTools: ["prompt.compile", "tool.schema", "eval.prompt"]
  },
  {
    key: "ToolingEngineer",
    label: "Tooling/SDK Agent",
    description: "Designs tool interfaces, adapters, and runtime contracts for agents.",
    defaultTools: ["tool.contract", "adapter.gen", "sandbox.harden"]
  },
  {
    key: "UIUX",
    label: "UI/UX Agent",
    description: "Creates coherent dashboard UX with information architecture and interaction patterns.",
    defaultTools: ["ux.map", "ui.audit", "accessibility.check"]
  },
  {
    key: "Product",
    label: "Product Agent",
    description: "Defines requirements, user journeys, and acceptance criteria for agentic systems.",
    defaultTools: ["reqs.write", "journey.map", "acceptance.spec"]
  },
  {
    key: "TestEngineer",
    label: "Test Engineer Agent",
    description: "Creates test strategies, fixtures, integration tests, and replayable validations.",
    defaultTools: ["test.plan", "fixture.gen", "replay.verify"]
  },
  {
    key: "Performance",
    label: "Performance Agent",
    description: "Profiles latency/cost, tunes hot paths, and enforces performance budgets.",
    defaultTools: ["profile", "optimize", "budget.enforce"]
  },
  {
    key: "DistributedSystems",
    label: "Distributed Systems Agent",
    description: "Designs robust distributed protocols, consistency strategies, and failure handling.",
    defaultTools: ["consensus.model", "failure.sim", "partition.plan"]
  },
  {
    key: "APIDesign",
    label: "API Design Agent",
    description: "Designs stable APIs, versioning, contracts, and client ergonomics.",
    defaultTools: ["api.schema", "version.plan", "client.gen"]
  },
  {
    key: "DatabaseTuning",
    label: "Database Tuning Agent",
    description: "Optimizes queries, indexes, schemas, and ensures predictable performance.",
    defaultTools: ["query.profile", "index.suggest", "cache.plan"]
  },
  {
    key: "Kubernetes",
    label: "Kubernetes Agent",
    description: "Authors K8s manifests/Helm, resource policies, and cluster operational patterns.",
    defaultTools: ["k8s.render", "policy.validate", "hpa.tune"]
  },
  {
    key: "Terraform",
    label: "Terraform/IaC Agent",
    description: "Builds deterministic IaC with drift detection, state hygiene, and modularity.",
    defaultTools: ["tf.plan", "tf.validate", "drift.check"]
  },
  {
    key: "IncidentCommander",
    label: "Incident Commander Agent",
    description: "Owns incident response playbooks, escalation, and postmortem workflow.",
    defaultTools: ["runbook.exec", "timeline.build", "postmortem.write"]
  },
  {
    key: "Compliance",
    label: "Compliance Agent",
    description: "Maps controls to system behavior, audit evidence, and retention policies.",
    defaultTools: ["control.map", "evidence.pack", "policy.audit"]
  },
  {
    key: "Research",
    label: "Research Agent",
    description: "Conducts research synthesis, compares approaches, and tracks references/assumptions.",
    defaultTools: ["lit.review", "compare", "assumption.log"]
  },
  {
    key: "SyntheticData",
    label: "Synthetic Data Agent",
    description: "Generates synthetic datasets, labeling policies, and evaluative distributions.",
    defaultTools: ["data.gen", "label.policy", "dist.fit"]
  },
  {
    key: "MemoryEngineer",
    label: "Memory Systems Agent",
    description: "Designs multi-tier memory (scratch/episodic/persistent/permanent), promotion rules, and retrieval.",
    defaultTools: ["memory.schema", "promotion.rules", "retrieval.eval"]
  }
]);

function maxey0ColorByIndex(idx: number): string {
  const safe = Math.abs(idx) % PALETTE_32.length;
  return PALETTE_32[safe]!.hex;
}

function uid(prefix: string): string {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
}

function clamp(n: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, n));
}

function deepCopy<T>(x: T): T {
  return JSON.parse(JSON.stringify(x)) as T;
}

function randLatent16(seed?: number): Maxey0Latent {
  // deterministic-ish if seed provided; otherwise random
  const v: number[] = [];
  let s = seed ?? Math.floor(Math.random() * 2 ** 31);
  for (let i = 0; i < 16; i++) {
    // LCG
    s = (1103515245 * s + 12345) % 2 ** 31;
    const r = (s / (2 ** 31 - 1)) * 2 - 1;
    v.push(r);
  }
  return { v };
}

function defaultScwPreset(): Maxey0ScwRuntimePreset {
  return {
    runtime: "container",
    determinismPolicy: "strict",
    tickLoggingRequired: true,
    runHeaderRequired: true,
    verificationBlockRequired: true,
    cpu: 2,
    memoryMb: 2048,
    diskMb: 1024,
    network: "egress",
    toolAdapters: ["shell", "http", "browser"],
    timeSource: "monotonic+wall"
  };
}

function tryLoadSaved(): ExportPayload | null {
  try {
    const raw = localStorage.getItem(MAXEY0_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as ExportPayload;
    if (!parsed || parsed.version !== "2.0.0") return null;
    if (!Array.isArray(parsed.nodes) || !Array.isArray(parsed.edges) || !parsed.ui) return null;
    return parsed;
  } catch {
    return null;
  }
}

function saveNow(payload: ExportPayload): void {
  localStorage.setItem(MAXEY0_STORAGE_KEY, JSON.stringify(payload));
}

function exportPayload(nodes: Maxey0Node[], edges: Maxey0Edge[], ui: ExportPayload["ui"]): ExportPayload {
  // Provide optional deterministic mappings based on each node's deterministicOrdinal
  const detAgents: Record<string, number> = {};
  const detScws: Record<string, number> = {};
  for (const n of nodes) {
    if (!n.deterministicEnabled || n.deterministicOrdinal == null) continue;
    if (n.kind === "agent") detAgents[n.id] = n.deterministicOrdinal;
    if (n.kind === "scw") detScws[n.id] = n.deterministicOrdinal;
  }

  const payload: ExportPayload = {
    version: "2.0.0",
    exportedAtIso: new Date().toISOString(),
    nodes: deepCopy(nodes),
    edges: deepCopy(edges),
    ui: deepCopy(ui),
    deterministic: {
      agents: Object.keys(detAgents).length ? detAgents : undefined,
      scws: Object.keys(detScws).length ? detScws : undefined
    }
  };

  return payload;
}

function toCanvasPoint(clientX: number, clientY: number, rect: DOMRect, ui: ExportPayload["ui"]): { x: number; y: number } {
  const sx = clientX - rect.left;
  const sy = clientY - rect.top;
  const x = (sx - ui.panX) / ui.zoom;
  const y = (sy - ui.panY) / ui.zoom;
  return { x, y };
}

function center(n: Maxey0Node): { x: number; y: number } {
  return { x: n.x + n.w / 2, y: n.y + n.h / 2 };
}

function nearestHandlePoint(n: Maxey0Node, toward: { x: number; y: number }): { x: number; y: number } {
  const c = center(n);
  const left = { x: n.x, y: c.y };
  const right = { x: n.x + n.w, y: c.y };
  const dL = (toward.x - left.x) ** 2 + (toward.y - left.y) ** 2;
  const dR = (toward.x - right.x) ** 2 + (toward.y - right.y) ** 2;
  return dL < dR ? left : right;
}

function edgePath(src: { x: number; y: number }, dst: { x: number; y: number }): string {
  const dx = Math.max(90, Math.abs(dst.x - src.x) * 0.55);
  const c1 = { x: src.x + dx, y: src.y };
  const c2 = { x: dst.x - dx, y: dst.y };
  return `M ${src.x} ${src.y} C ${c1.x} ${c1.y} ${c2.x} ${c2.y} ${dst.x} ${dst.y}`;
}

function classNames(...xs: Array<string | false | null | undefined>): string {
  return xs.filter(Boolean).join(" ");
}

function within(n: Maxey0Node, p: { x: number; y: number }): boolean {
  return p.x >= n.x && p.x <= n.x + n.w && p.y >= n.y && p.y <= n.y + n.h;
}

function formatDeterministicLabel(n: Maxey0Node): string {
  if (!n.deterministicEnabled || n.deterministicOrdinal == null) return "";
  if (n.kind === "agent") return `Maxey${n.deterministicOrdinal}`;
  if (n.kind === "scw") return `SCW${n.deterministicOrdinal}`;
  if (n.kind === "maxey00") return "Maxey00";
  return "";
}

function pickSpecByKey(key: Maxey0AgentSpecKey): Maxey0AgentSpec {
  return (MAXEY0_AGENT_SPECS.find((s) => s.key === key) ?? MAXEY0_AGENT_SPECS[0]!) as Maxey0AgentSpec;
}

function autoFitScw(scw: Maxey0Node, children: Maxey0Node[]): Maxey0Node {
  if (scw.kind !== "scw") return scw;
  if (!children.length) return scw;
  // Ensure padding around children
  const pad = 28;
  let minX = Infinity,
    minY = Infinity,
    maxX = -Infinity,
    maxY = -Infinity;
  for (const c of children) {
    minX = Math.min(minX, c.x);
    minY = Math.min(minY, c.y);
    maxX = Math.max(maxX, c.x + c.w);
    maxY = Math.max(maxY, c.y + c.h);
  }
  // Expand scw to contain children if needed
  const nextX = Math.min(scw.x, minX - pad);
  const nextY = Math.min(scw.y, minY - pad);
  const nextW = Math.max(scw.x + scw.w, maxX + pad) - nextX;
  const nextH = Math.max(scw.y + scw.h, maxY + pad) - nextY;
  return { ...scw, x: nextX, y: nextY, w: Math.max(nextW, 340), h: Math.max(nextH, 220) };
}

export default function App() {
  const canvasRef = useRef<HTMLDivElement | null>(null);

  const [ui, setUi] = useState<ExportPayload["ui"]>(() => {
    const saved = tryLoadSaved();
    return (
      saved?.ui ?? {
        panX: 0,
        panY: 0,
        zoom: 1,
        latentZScale: 0.75,
        latentDepthMode: "shadow"
      }
    );
  });

  const [nodes, setNodes] = useState<Maxey0Node[]>(() => {
    const saved = tryLoadSaved();
    if (saved) return saved.nodes;

    const seed: Maxey0Node[] = [];

    // seed SCW0 container
    seed.push({
      id: "scw_0",
      kind: "scw",
      label: "Core Orchestration Window",
      deterministicEnabled: true,
      deterministicOrdinal: 0,
      colorHex: maxey0ColorByIndex(12),
      x: 360,
      y: 120,
      w: 520,
      h: 360,
      latent: randLatent16(1001),
      tags: ["scw", "foundation"],
      properties: { tier: "foundation", retention: "ephemeral" },
      parentScwId: null,
      scw: {
        purpose: "Orchestration scratchpad and deterministic tick log",
        runtimePreset: defaultScwPreset()
      }
    });

    const specTS = pickSpecByKey("TypeScriptDev");
    seed.push({
      id: "agent_1",
      kind: "agent",
      label: "UI Builder",
      deterministicEnabled: true,
      deterministicOrdinal: 1,
      colorHex: maxey0ColorByIndex(1),
      x: 420,
      y: 180,
      w: 240,
      h: 110,
      latent: randLatent16(2001),
      tags: ["agent", "ui"],
      properties: { concurrencyClass: "serial" },
      parentScwId: "scw_0",
      agent: {
        specializationKey: specTS.key,
        specializationLabel: specTS.label,
        specializationDescription: specTS.description,
        tools: deepCopy(specTS.defaultTools),
        memoryScope: "sp",
        notes: ""
      }
    });

    const specObs = pickSpecByKey("Observability");
    seed.push({
      id: "agent_2",
      kind: "agent",
      label: "Trace Grader",
      deterministicEnabled: true,
      deterministicOrdinal: 2,
      colorHex: maxey0ColorByIndex(11),
      x: 420,
      y: 320,
      w: 240,
      h: 110,
      latent: randLatent16(2002),
      tags: ["agent", "observability"],
      properties: { concurrencyClass: "parallel" },
      parentScwId: "scw_0",
      agent: {
        specializationKey: specObs.key,
        specializationLabel: specObs.label,
        specializationDescription: specObs.description,
        tools: deepCopy(specObs.defaultTools),
        memoryScope: "ep",
        notes: ""
      }
    });

    // seed Maxey00
    seed.push({
      id: "maxey00",
      kind: "maxey00",
      label: "Superposition Observability",
      deterministicEnabled: true,
      deterministicOrdinal: 0,
      colorHex: "#E4E4E7",
      x: 980,
      y: 90,
      w: 300,
      h: 120,
      latent: randLatent16(9900),
      tags: ["superposition", "observability"],
      properties: { scope: "global" },
      parentScwId: null,
      maxey00: {
        observability: "global",
        notes: "Observes across SCWs; edges represent observability/lineage and verification."
      }
    });

    return seed;
  });

  const [edges, setEdges] = useState<Maxey0Edge[]>(() => {
    const saved = tryLoadSaved();
    if (saved) return saved.edges;
    return [
      { id: "e1", sourceId: "agent_1", targetId: "scw_0", kind: "writes_to", label: "writes_to", properties: { channel: "sp" } },
      { id: "e2", sourceId: "agent_2", targetId: "scw_0", kind: "logs_to", label: "logs_to", properties: { required: true } },
      { id: "e3", sourceId: "maxey00", targetId: "scw_0", kind: "observes", label: "observes", properties: { mode: "global" } },
      { id: "e4", sourceId: "maxey00", targetId: "agent_2", kind: "observes", label: "observes", properties: { mode: "audit" } }
    ];
  });

  const [selected, setSelected] = useState<{ kind: "node"; id: string } | { kind: "edge"; id: string } | null>(null);

  const selectedNode = useMemo(() => (selected?.kind === "node" ? nodes.find((n) => n.id === selected.id) ?? null : null), [selected, nodes]);
  const selectedEdge = useMemo(() => (selected?.kind === "edge" ? edges.find((e) => e.id === selected.id) ?? null : null), [selected, edges]);

  // Next ordinals (editable after creation)
  const [nextAgentOrdinal, setNextAgentOrdinal] = useState<number>(() => {
    const saved = tryLoadSaved();
    if (saved) {
      const max = Math.max(
        0,
        ...saved.nodes
          .filter((n) => n.kind === "agent" && typeof n.deterministicOrdinal === "number")
          .map((n) => n.deterministicOrdinal as number)
      );
      return max + 1;
    }
    return 3; // seed already created Maxey1 and Maxey2
  });

  const [nextScwOrdinal, setNextScwOrdinal] = useState<number>(() => {
    const saved = tryLoadSaved();
    if (saved) {
      const max = Math.max(
        -1,
        ...saved.nodes
          .filter((n) => n.kind === "scw" && typeof n.deterministicOrdinal === "number")
          .map((n) => n.deterministicOrdinal as number)
      );
      return max + 1;
    }
    return 1; // seed SCW0
  });

  const [tab, setTab] = useState<"catalog" | "add">("catalog");
  const [q, setQ] = useState("");

  // Add-panel state
  const [addKind, setAddKind] = useState<"agent" | "scw">("agent");
  const [addSpec, setAddSpec] = useState<Maxey0AgentSpecKey>("Orchestrator");
  const [addSpecDescOverride, setAddSpecDescOverride] = useState<string>(pickSpecByKey("Orchestrator").description);
  const [addScwPurpose, setAddScwPurpose] = useState<string>("New runtime container");
  const [addScwPreset, setAddScwPreset] = useState<Maxey0ScwRuntimePreset>(defaultScwPreset());
  const [edgeCreateKind, setEdgeCreateKind] = useState<Maxey0EdgeKind>("depends_on");

  // Dragging nodes
  const dragState = useRef<
    | null
    | {
        nodeId: string;
        startClientX: number;
        startClientY: number;
        startX: number;
        startY: number;
      }
  >(null);

  // Panning
  const panState = useRef<null | { startClientX: number; startClientY: number; startPanX: number; startPanY: number }>(null);

  // Creating edges
  const linkState = useRef<null | { sourceId: string; kind: Maxey0EdgeKind; label: string; toX: number; toY: number }>(null);

  // Derived maps
  const nodeById = useMemo(() => {
    const m = new Map<string, Maxey0Node>();
    for (const n of nodes) m.set(n.id, n);
    return m;
  }, [nodes]);

  const scws = useMemo(() => nodes.filter((n) => n.kind === "scw"), [nodes]);

  // Keep SCW containers logically consistent: ensure they contain their children (auto-fit)
  useEffect(() => {
    setNodes((prev) => {
      const byId = new Map(prev.map((n) => [n.id, n] as const));
      let changed = false;
      for (const scw of prev.filter((n) => n.kind === "scw")) {
        const children = prev.filter((n) => n.kind === "agent" && n.parentScwId === scw.id);
        const fitted = autoFitScw(scw, children);
        if (fitted.x !== scw.x || fitted.y !== scw.y || fitted.w !== scw.w || fitted.h !== scw.h) {
          byId.set(scw.id, fitted);
          changed = true;
        }
      }
      if (!changed) return prev;
      return Array.from(byId.values());
    });
  }, [nodes.length]);

  function clearSelection() {
    setSelected(null);
  }

  function setZoom(nextZoom: number, anchorClientX?: number, anchorClientY?: number) {
    const z = clamp(nextZoom, 0.35, 2.5);
    if (!canvasRef.current || anchorClientX == null || anchorClientY == null) {
      setUi((u) => ({ ...u, zoom: z }));
      return;
    }
    const rect = canvasRef.current.getBoundingClientRect();
    const before = toCanvasPoint(anchorClientX, anchorClientY, rect, ui);
    const nextUi = { ...ui, zoom: z };
    const after = toCanvasPoint(anchorClientX, anchorClientY, rect, nextUi);
    const dx = (after.x - before.x) * z;
    const dy = (after.y - before.y) * z;
    setUi((u) => ({ ...u, zoom: z, panX: u.panX + dx, panY: u.panY + dy }));
  }

  function saveLocal() {
    const payload = exportPayload(nodes, edges, ui);
    saveNow(payload);
    alert("Saved to localStorage.");
  }

  function loadLocal() {
    const saved = tryLoadSaved();
    if (!saved) {
      alert("No saved state found.");
      return;
    }
    setNodes(saved.nodes);
    setEdges(saved.edges);
    setUi(saved.ui);
    setSelected(null);

    const maxAgent = Math.max(
      0,
      ...saved.nodes
        .filter((n) => n.kind === "agent" && typeof n.deterministicOrdinal === "number")
        .map((n) => n.deterministicOrdinal as number)
    );
    const maxScw = Math.max(
      -1,
      ...saved.nodes
        .filter((n) => n.kind === "scw" && typeof n.deterministicOrdinal === "number")
        .map((n) => n.deterministicOrdinal as number)
    );
    setNextAgentOrdinal(maxAgent + 1);
    setNextScwOrdinal(maxScw + 1);
  }

  function clearAll() {
    setNodes([]);
    setEdges([]);
    setSelected(null);
    setUi({ panX: 0, panY: 0, zoom: 1, latentZScale: 0.75, latentDepthMode: "shadow" });
    setNextAgentOrdinal(1);
    setNextScwOrdinal(0);
    localStorage.removeItem(MAXEY0_STORAGE_KEY);
  }

  function exportJsonToClipboard() {
    const payload = exportPayload(nodes, edges, ui);
    const json = JSON.stringify(payload, null, 2);
    void navigator.clipboard
      .writeText(json)
      .then(() => alert("Export copied to clipboard."))
      .catch(() => alert("Clipboard write failed (permissions)."));
  }

  function importJsonFromText(txt: string) {
    try {
      const parsed = JSON.parse(txt) as ExportPayload;
      if (!parsed || (parsed.version !== "2.0.0" && parsed.version !== "1.0.0")) throw new Error("Unsupported version");

      // Migrate v1 -> v2 minimally
      if (parsed.version === "1.0.0") {
        const anyParsed: any = parsed;
        const migratedNodes: Maxey0Node[] = (anyParsed.nodes as any[]).map((n, i) => {
          const kind: Maxey0NodeKind = n.kind === "agent" ? "agent" : n.kind === "scw" ? "scw" : "agent";
          const latent = randLatent16(5000 + i);
          const base: Maxey0Node = {
            id: n.id,
            kind,
            label: n.label ?? (kind === "agent" ? "New Agent" : "New SCW"),
            deterministicEnabled: false,
            deterministicOrdinal: undefined,
            colorHex: n.color_hex ?? n.colorHex ?? maxey0ColorByIndex(i),
            x: n.x ?? 100 + (i % 4) * 260,
            y: n.y ?? 120 + Math.floor(i / 4) * 160,
            w: kind === "agent" ? 240 : 520,
            h: kind === "agent" ? 110 : 320,
            latent,
            tags: Array.isArray(n.tags) ? n.tags : [],
            properties: n.properties ?? {},
            parentScwId: null
          };
          if (kind === "agent") {
            const spec = pickSpecByKey("Orchestrator");
            base.agent = {
              specializationKey: spec.key,
              specializationLabel: spec.label,
              specializationDescription: spec.description,
              tools: deepCopy(spec.defaultTools),
              memoryScope: "sp",
              notes: ""
            };
          } else {
            base.scw = { purpose: "Imported SCW", runtimePreset: defaultScwPreset() };
          }
          return base;
        });

        const migratedEdges: Maxey0Edge[] = (anyParsed.edges as any[]).map((e: any, idx: number) => ({
          id: e.id ?? `imp_edge_${idx}`,
          sourceId: e.source ?? e.sourceId,
          targetId: e.target ?? e.targetId,
          kind: (e.kind ?? "depends_on") as Maxey0EdgeKind,
          label: e.label ?? (e.kind ?? "depends_on"),
          properties: e.properties ?? {}
        }));

        const migratedUi: ExportPayload["ui"] = {
          panX: anyParsed.viewport?.x ?? 0,
          panY: anyParsed.viewport?.y ?? 0,
          zoom: anyParsed.viewport?.zoom ?? 1,
          latentZScale: 0.75,
          latentDepthMode: "shadow"
        };

        setNodes(migratedNodes);
        setEdges(migratedEdges);
        setUi(migratedUi);
        setSelected(null);

        // Next ordinals remain user-controlled; do not attach by default.
        const maxAgent = Math.max(0, ...migratedNodes.filter((n) => n.kind === "agent" && typeof n.deterministicOrdinal === "number").map((n) => n.deterministicOrdinal as number));
        const maxScw = Math.max(-1, ...migratedNodes.filter((n) => n.kind === "scw" && typeof n.deterministicOrdinal === "number").map((n) => n.deterministicOrdinal as number));
        setNextAgentOrdinal(maxAgent + 1);
        setNextScwOrdinal(maxScw + 1);
        return;
      }

      if (!Array.isArray(parsed.nodes) || !Array.isArray(parsed.edges) || !parsed.ui) throw new Error("Invalid schema");

      // Honor deterministic mapping ONLY if provided
      const nextNodes = parsed.nodes.map((n) => {
        const nn: Maxey0Node = { ...n };
        if (!nn.latent?.v || nn.latent.v.length !== 16) nn.latent = randLatent16();
        // Do not force deterministic ordinals unless explicitly enabled in node
        if (!nn.deterministicEnabled) nn.deterministicOrdinal = undefined;
        return nn;
      });

      setNodes(nextNodes);
      setEdges(parsed.edges);
      setUi(parsed.ui);
      setSelected(null);

      const maxAgent = Math.max(
        0,
        ...nextNodes.filter((n) => n.kind === "agent" && typeof n.deterministicOrdinal === "number").map((n) => n.deterministicOrdinal as number)
      );
      const maxScw = Math.max(
        -1,
        ...nextNodes.filter((n) => n.kind === "scw" && typeof n.deterministicOrdinal === "number").map((n) => n.deterministicOrdinal as number)
      );
      setNextAgentOrdinal(maxAgent + 1);
      setNextScwOrdinal(maxScw + 1);

      alert("Imported.");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Unknown error";
      alert(`Import failed: ${msg}`);
    }
  }

  function updateNode(nodeId: string, patch: Partial<Maxey0Node>) {
    setNodes((xs) => xs.map((n) => (n.id === nodeId ? { ...n, ...patch } : n)));
  }

  function deleteNode(nodeId: string) {
    setNodes((xs) => xs.filter((n) => n.id !== nodeId));
    setEdges((es) => es.filter((e) => e.sourceId !== nodeId && e.targetId !== nodeId));
    setSelected((s) => (s?.kind === "node" && s.id === nodeId ? null : s));
  }

  function updateEdge(edgeId: string, patch: Partial<Maxey0Edge>) {
    setEdges((xs) => xs.map((e) => (e.id === edgeId ? { ...e, ...patch } : e)));
  }

  function deleteEdge(edgeId: string) {
    setEdges((xs) => xs.filter((e) => e.id !== edgeId));
    setSelected((s) => (s?.kind === "edge" && s.id === edgeId ? null : s));
  }

  function beginEdgeCreate(sourceId: string, kind: Maxey0EdgeKind) {
    linkState.current = { sourceId, kind, label: kind, toX: 0, toY: 0 };
    setSelected({ kind: "node", id: sourceId });
  }

  function endEdgeCreate(targetId: string) {
    const st = linkState.current;
    if (!st) return;
    if (st.sourceId === targetId) {
      linkState.current = null;
      return;
    }
    const id = uid("edge");
    const edge: Maxey0Edge = {
      id,
      sourceId: st.sourceId,
      targetId,
      kind: st.kind,
      label: st.label,
      properties: {}
    };
    setEdges((es) => [...es, edge]);
    setSelected({ kind: "edge", id });
    linkState.current = null;
  }

  function reparentAgentIfNeeded(agentId: string) {
    setNodes((prev) => {
      const agent = prev.find((n) => n.id === agentId);
      if (!agent || agent.kind !== "agent") return prev;

      const c = center(agent);

      // Find top-most SCW that contains the agent center
      const containers = prev
        .filter((n) => n.kind === "scw")
        .sort((a, b) => (a.w * a.h < b.w * b.h ? -1 : 1));

      let parent: Maxey0Node | null = null;
      for (const scw of containers) {
        if (within(scw, c)) {
          parent = scw;
          break;
        }
      }

      const nextParent = parent?.id ?? null;
      if ((agent.parentScwId ?? null) === nextParent) return prev;

      return prev.map((n) => (n.id === agentId ? { ...n, parentScwId: nextParent } : n));
    });
  }

  function addAgentAtDefault(specKey: Maxey0AgentSpecKey) {
    const spec = pickSpecByKey(specKey);
    const id = uid("agent");
    const ordinal = nextAgentOrdinal;
    setNextAgentOrdinal((n) => n + 1);

    const color = maxey0ColorByIndex(ordinal - 1);
    const latent = randLatent16(7000 + ordinal);

    const n: Maxey0Node = {
      id,
      kind: "agent",
      label: "New Agent",
      deterministicEnabled: true,
      deterministicOrdinal: ordinal,
      colorHex: color,
      x: 180,
      y: 160 + (ordinal % 6) * 140,
      w: 240,
      h: 110,
      latent,
      tags: ["agent", "maxey0"],
      properties: { concurrencyClass: ordinal % 2 === 0 ? "parallel" : "serial" },
      parentScwId: null,
      agent: {
        specializationKey: spec.key,
        specializationLabel: spec.label,
        specializationDescription: spec.description,
        tools: deepCopy(spec.defaultTools),
        memoryScope: "sp",
        notes: ""
      }
    };

    setNodes((xs) => [...xs, n]);
    setSelected({ kind: "node", id });
  }

  function addScwAtDefault() {
    const id = uid("scw");
    const ordinal = nextScwOrdinal;
    setNextScwOrdinal((n) => n + 1);

    const color = maxey0ColorByIndex((ordinal + 16) % 32);
    const latent = randLatent16(8000 + ordinal);

    const n: Maxey0Node = {
      id,
      kind: "scw",
      label: "New SCW Container",
      deterministicEnabled: true,
      deterministicOrdinal: ordinal,
      colorHex: color,
      x: 560,
      y: 140 + (ordinal % 5) * 140,
      w: 520,
      h: 320,
      latent,
      tags: ["scw", "runtime"],
      properties: { tier: ordinal < 10 ? "foundation" : ordinal < 20 ? "workflow" : "verification" },
      parentScwId: null,
      scw: {
        purpose: addScwPurpose,
        runtimePreset: deepCopy(addScwPreset)
      }
    };

    setNodes((xs) => [...xs, n]);
    setSelected({ kind: "node", id });
  }

  function addMaxey00IfMissing() {
    if (nodes.some((n) => n.kind === "maxey00")) {
      alert("Maxey00 already exists.");
      return;
    }
    const n: Maxey0Node = {
      id: "maxey00",
      kind: "maxey00",
      label: "Superposition Observability",
      deterministicEnabled: true,
      deterministicOrdinal: 0,
      colorHex: "#E4E4E7",
      x: 980,
      y: 90,
      w: 300,
      h: 120,
      latent: randLatent16(9900),
      tags: ["superposition", "observability"],
      properties: { scope: "global" },
      parentScwId: null,
      maxey00: { observability: "global", notes: "Observes across SCWs." }
    };
    setNodes((xs) => [...xs, n]);
    setSelected({ kind: "node", id: n.id });
  }

  function onCanvasMouseDown(ev: React.MouseEvent) {
    // Pan with middle mouse or space+left
    if (ev.button === 1 || (ev.button === 0 && ev.getModifierState(" "))) {
      ev.preventDefault();
      panState.current = { startClientX: ev.clientX, startClientY: ev.clientY, startPanX: ui.panX, startPanY: ui.panY };
      return;
    }

    if ((ev.target as HTMLElement).dataset.role === "canvas") {
      clearSelection();
    }
  }

  function onCanvasMouseMove(ev: React.MouseEvent) {
    const ps = panState.current;
    if (ps) {
      const dx = ev.clientX - ps.startClientX;
      const dy = ev.clientY - ps.startClientY;
      setUi((u) => ({ ...u, panX: ps.startPanX + dx, panY: ps.startPanY + dy }));
      return;
    }

    const ls = linkState.current;
    if (ls && canvasRef.current) {
      const rect = canvasRef.current.getBoundingClientRect();
      const p = toCanvasPoint(ev.clientX, ev.clientY, rect, ui);
      ls.toX = p.x;
      ls.toY = p.y;
      setUi((u) => ({ ...u }));
    }

    const ds = dragState.current;
    if (ds && canvasRef.current) {
      const rect = canvasRef.current.getBoundingClientRect();
      const p0 = toCanvasPoint(ds.startClientX, ds.startClientY, rect, ui);
      const p1 = toCanvasPoint(ev.clientX, ev.clientY, rect, ui);
      const dx = p1.x - p0.x;
      const dy = p1.y - p0.y;

      const node = nodeById.get(ds.nodeId);
      if (!node) return;

      const nx = ds.startX + dx;
      const ny = ds.startY + dy;
      updateNode(ds.nodeId, { x: nx, y: ny });
    }
  }

  function onCanvasMouseUp() {
    panState.current = null;

    if (dragState.current) {
      const nodeId = dragState.current.nodeId;
      dragState.current = null;
      reparentAgentIfNeeded(nodeId);
    } else {
      dragState.current = null;
    }

    if (linkState.current) {
      linkState.current = null;
      setUi((u) => ({ ...u }));
    }
  }

  function onWheel(ev: React.WheelEvent) {
    if (!canvasRef.current) return;
    if (ev.ctrlKey) {
      ev.preventDefault();
      const factor = ev.deltaY < 0 ? 1.08 : 0.92;
      setZoom(ui.zoom * factor, ev.clientX, ev.clientY);
      return;
    }
    setUi((u) => ({ ...u, panX: u.panX - ev.deltaX, panY: u.panY - ev.deltaY }));
  }

  function onDrop(ev: React.DragEvent) {
    ev.preventDefault();
    // drag-drop disabled for now; use Add panel for deterministic +1 semantics
  }

  function onDragOver(ev: React.DragEvent) {
    ev.preventDefault();
    ev.dataTransfer.dropEffect = "move";
  }

  // Render order: SCWs first (containers), then Agents, then Maxey00 on top
  const renderOrder = useMemo(() => {
    const scwNodes = nodes.filter((n) => n.kind === "scw");
    const agentNodes = nodes.filter((n) => n.kind === "agent");
    const m00Nodes = nodes.filter((n) => n.kind === "maxey00");
    return { scwNodes, agentNodes, m00Nodes };
  }, [nodes]);

  const edgeSegments = useMemo(() => {
    const segments: Array<{
      edge: Maxey0Edge;
      d: string;
      labelX: number;
      labelY: number;
    }> = [];

    for (const e of edges) {
      const s = nodeById.get(e.sourceId);
      const t = nodeById.get(e.targetId);
      if (!s || !t) continue;
      const sc = center(s);
      const tc = center(t);
      const src = nearestHandlePoint(s, tc);
      const dst = nearestHandlePoint(t, sc);
      const d = edgePath(src, dst);
      const labelX = (src.x + dst.x) / 2;
      const labelY = (src.y + dst.y) / 2;
      segments.push({ edge: e, d, labelX, labelY });
    }

    return segments;
  }, [edges, nodeById]);

  const linkPreview = useMemo(() => {
    const st = linkState.current;
    if (!st) return null;
    const s = nodeById.get(st.sourceId);
    if (!s) return null;
    const src = nearestHandlePoint(s, { x: st.toX, y: st.toY });
    const dst = { x: st.toX, y: st.toY };
    return { d: edgePath(src, dst), label: st.label, labelX: (src.x + dst.x) / 2, labelY: (src.y + dst.y) / 2 };
  }, [ui, nodeById]);

  // Latent 3D projection cues
  function latentZ(n: Maxey0Node): number {
    // Use dims 2 and 7 as "depth" signal
    const z = (n.latent?.v?.[2] ?? 0) * 0.65 + (n.latent?.v?.[7] ?? 0) * 0.35;
    return z;
  }

  function depthStyle(n: Maxey0Node): { boxShadow: string; filter?: string; transform?: string } {
    const z = latentZ(n);
    const depth = clamp((z + 1) / 2, 0, 1); // 0..1
    const k = ui.latentZScale;
    const lift = (depth - 0.5) * 18 * k;
    const glow = 0.12 + depth * 0.22;

    if (ui.latentDepthMode === "parallax") {
      return {
        transform: `translateZ(0) translateY(${-lift}px)`,
        boxShadow: `0 0 0 1px ${n.colorHex}22, 0 ${12 + depth * 18}px ${30 + depth * 30}px rgba(0,0,0,0.55)`
      };
    }

    return {
      boxShadow: `0 0 0 1px ${n.colorHex}22, 0 ${12 + depth * 18}px ${30 + depth * 30}px rgba(0,0,0,0.55), 0 0 ${Math.round(18 * glow)}px ${n.colorHex}20`
    };
  }

  const importBoxRef = useRef<HTMLTextAreaElement | null>(null);

  // Sidebar catalog is now specialization + SCW preset parameterization
  const filteredSpecs = useMemo(() => {
    const query = q.trim().toLowerCase();
    if (!query) return MAXEY0_AGENT_SPECS;
    return MAXEY0_AGENT_SPECS.filter((s) => `${s.label} ${s.key} ${s.description}`.toLowerCase().includes(query));
  }, [q]);

  return (
    <div className="h-screen w-screen bg-zinc-950 text-zinc-100">
      {/* Topbar */}
      <div className="flex items-center justify-between gap-3 border-b border-zinc-800 bg-zinc-950 p-3">
        <div className="flex items-baseline gap-3">
          <div className="text-sm font-semibold">maxey0-scw-designer (!app)</div>
          <div className="text-xs text-zinc-500">SCWs are containers • Agents live in/out • Maxey00 observes • latent-space projection cues</div>
        </div>

        <div className="flex items-center gap-2">
          <button className="rounded-xl border border-zinc-800 bg-zinc-100 px-3 py-2 text-sm font-medium text-zinc-900 hover:bg-white" onClick={saveLocal}>
            Save
          </button>
          <button className="rounded-xl border border-zinc-800 bg-transparent px-3 py-2 text-sm font-medium text-zinc-200 hover:bg-zinc-900" onClick={loadLocal}>
            Load
          </button>
          <button className="rounded-xl border border-zinc-800 bg-transparent px-3 py-2 text-sm font-medium text-zinc-200 hover:bg-zinc-900" onClick={exportJsonToClipboard}>
            Copy Export
          </button>
          <button className="rounded-xl border border-red-900/60 bg-red-500/10 px-3 py-2 text-sm font-medium text-red-200 hover:bg-red-500/20" onClick={clearAll}>
            Clear
          </button>
        </div>
      </div>

      <div className="flex h-[calc(100vh-56px)] min-h-0">
        {/* Left panel */}
        <div className="w-[380px] shrink-0 border-r border-zinc-800 bg-zinc-950">
          <div className="p-3">
            <div className="flex items-center gap-2 rounded-2xl border border-zinc-800 bg-zinc-950 p-1">
              <button
                className={classNames(
                  "flex-1 rounded-2xl px-3 py-2 text-sm transition",
                  tab === "catalog" ? "bg-zinc-100 text-zinc-900" : "text-zinc-200 hover:bg-zinc-900"
                )}
                onClick={() => setTab("catalog")}
              >
                Catalog
              </button>
              <button
                className={classNames(
                  "flex-1 rounded-2xl px-3 py-2 text-sm transition",
                  tab === "add" ? "bg-zinc-100 text-zinc-900" : "text-zinc-200 hover:bg-zinc-900"
                )}
                onClick={() => setTab("add")}
              >
                Add
              </button>
            </div>
          </div>

          <div className="px-3 pb-3">
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search (specializations / text)"
              className="w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600 outline-none focus:border-zinc-600"
            />
          </div>

          <div className="h-[calc(100%-140px)] overflow-auto p-3">
            {tab === "catalog" && (
              <>
                <div className="rounded-2xl border border-zinc-800 bg-zinc-900/20 p-3 text-xs text-zinc-400">
                  <div className="font-semibold text-zinc-200">Default Agent Specializations (32)</div>
                  <div className="mt-1">These are decoupled from Maxey# ordinals; ordinals are optional + editable per node.</div>
                </div>

                <div className="mt-3 grid grid-cols-1 gap-2">
                  {filteredSpecs.map((s) => (
                    <div key={s.key} className="rounded-2xl border border-zinc-800 bg-zinc-900/30 p-3">
                      <div className="flex items-center justify-between gap-2">
                        <div className="text-sm font-semibold">{s.label}</div>
                        <span className="inline-flex items-center rounded-full border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-[10px] text-zinc-200">{s.key}</span>
                      </div>
                      <div className="mt-2 text-xs text-zinc-400">{s.description}</div>
                      <div className="mt-2 flex flex-wrap gap-1">
                        {s.defaultTools.slice(0, 6).map((t) => (
                          <span key={t} className="inline-flex items-center rounded-full border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-[10px] text-zinc-300">
                            {t}
                          </span>
                        ))}
                      </div>
                      <button
                        className="mt-3 w-full rounded-xl border border-zinc-800 bg-zinc-100 px-3 py-2 text-sm font-medium text-zinc-900 hover:bg-white"
                        onClick={() => addAgentAtDefault(s.key)}
                        title={`Spawns next agent: Maxey${nextAgentOrdinal}`}
                      >
                        Add Agent (next: Maxey{nextAgentOrdinal})
                      </button>
                    </div>
                  ))}
                </div>

                <div className="mt-6 rounded-2xl border border-zinc-800 bg-zinc-900/20 p-3 text-xs text-zinc-400">
                  <div className="font-semibold text-zinc-200">SCW Templates</div>
                  <div className="mt-1">Use the Add tab to parameterize a new SCW runtime container and spawn SCW{nextScwOrdinal}.</div>
                  <button
                    className="mt-3 w-full rounded-xl border border-zinc-800 bg-zinc-100 px-3 py-2 text-sm font-medium text-zinc-900 hover:bg-white"
                    onClick={() => {
                      setTab("add");
                      setAddKind("scw");
                    }}
                  >
                    Open Add → SCW
                  </button>
                </div>
              </>
            )}

            {tab === "add" && (
              <>
                <div className="rounded-2xl border border-zinc-800 bg-zinc-900/20 p-3 text-xs text-zinc-400">
                  <div className="font-semibold text-zinc-200">Spawn new node (+1 ordinal)</div>
                  <div className="mt-1">Agent spawn: Maxey{nextAgentOrdinal}. SCW spawn: SCW{nextScwOrdinal}.</div>
                </div>

                <div className="mt-3 rounded-2xl border border-zinc-800 bg-zinc-900/30 p-3">
                  <div className="text-sm font-semibold">Node Type</div>
                  <div className="mt-2 flex gap-2">
                    <button
                      className={classNames(
                        "flex-1 rounded-xl border px-3 py-2 text-sm font-medium",
                        addKind === "agent" ? "border-zinc-200 bg-zinc-100 text-zinc-900" : "border-zinc-800 bg-transparent text-zinc-200 hover:bg-zinc-900"
                      )}
                      onClick={() => setAddKind("agent")}
                    >
                      Agent
                    </button>
                    <button
                      className={classNames(
                        "flex-1 rounded-xl border px-3 py-2 text-sm font-medium",
                        addKind === "scw" ? "border-zinc-200 bg-zinc-100 text-zinc-900" : "border-zinc-800 bg-transparent text-zinc-200 hover:bg-zinc-900"
                      )}
                      onClick={() => setAddKind("scw")}
                    >
                      SCW
                    </button>
                  </div>

                  {addKind === "agent" && (
                    <>
                      <div className="mt-4 text-xs text-zinc-500">Specialization (AgentSpecialization)</div>
                      <select
                        className="mt-1 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-600"
                        value={addSpec}
                        onChange={(e) => {
                          const key = e.target.value as Maxey0AgentSpecKey;
                          setAddSpec(key);
                          setAddSpecDescOverride(pickSpecByKey(key).description);
                        }}
                      >
                        {MAXEY0_AGENT_SPECS.map((s) => (
                          <option key={s.key} value={s.key}>
                            {s.label}
                          </option>
                        ))}
                      </select>

                      <div className="mt-3 text-xs text-zinc-500">Description (auto-loads for defaults; editable)</div>
                      <textarea
                        className="mt-1 h-24 w-full rounded-2xl border border-zinc-800 bg-zinc-950 p-3 text-sm text-zinc-100 outline-none focus:border-zinc-600"
                        value={addSpecDescOverride}
                        onChange={(e) => setAddSpecDescOverride(e.target.value)}
                      />

                      <button
                        className="mt-3 w-full rounded-xl border border-zinc-800 bg-zinc-100 px-3 py-2 text-sm font-medium text-zinc-900 hover:bg-white"
                        onClick={() => {
                          const spec = pickSpecByKey(addSpec);
                          // allow user-defined specialization description
                          const override = addSpecDescOverride.trim();
                          const spec2: Maxey0AgentSpec = {
                            ...spec,
                            description: override.length ? override : spec.description
                          };
                          addAgentAtDefault(spec2.key);

                          // After spawn, patch spawned node's spec description to override.
                          setTimeout(() => {
                            setNodes((prev) => {
                              const last = [...prev].reverse().find((n) => n.kind === "agent" && n.deterministicOrdinal === nextAgentOrdinal - 1);
                              if (!last || !last.agent) return prev;
                              const updated: Maxey0Node = {
                                ...last,
                                agent: {
                                  ...last.agent,
                                  specializationDescription: spec2.description,
                                  tools: deepCopy(spec2.defaultTools),
                                  specializationLabel: spec2.label
                                }
                              };
                              return prev.map((n) => (n.id === last.id ? updated : n));
                            });
                          }, 0);
                        }}
                      >
                        Add Agent (spawns Maxey{nextAgentOrdinal})
                      </button>
                    </>
                  )}

                  {addKind === "scw" && (
                    <>
                      <div className="mt-4 text-xs text-zinc-500">SCW Purpose</div>
                      <input
                        className="mt-1 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-600"
                        value={addScwPurpose}
                        onChange={(e) => setAddScwPurpose(e.target.value)}
                      />

                      <div className="mt-4 rounded-2xl border border-zinc-800 bg-zinc-950 p-3">
                        <div className="text-sm font-semibold text-zinc-100">Runtime Preset (parameterized)</div>
                        <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
                          <div>
                            <div className="text-[10px] uppercase text-zinc-500">Runtime</div>
                            <select
                              className="mt-1 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-100 outline-none focus:border-zinc-600"
                              value={addScwPreset.runtime}
                              onChange={(e) => setAddScwPreset((p) => ({ ...p, runtime: e.target.value as any }))}
                            >
                              <option value="container">container</option>
                              <option value="python">python</option>
                              <option value="node">node</option>
                              <option value="dotnet">dotnet</option>
                              <option value="rust">rust</option>
                              <option value="go">go</option>
                            </select>
                          </div>
                          <div>
                            <div className="text-[10px] uppercase text-zinc-500">Determinism</div>
                            <select
                              className="mt-1 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-100 outline-none focus:border-zinc-600"
                              value={addScwPreset.determinismPolicy}
                              onChange={(e) => setAddScwPreset((p) => ({ ...p, determinismPolicy: e.target.value as any }))}
                            >
                              <option value="strict">strict</option>
                              <option value="best-effort">best-effort</option>
                              <option value="strict+hash-chain">strict+hash-chain</option>
                            </select>
                          </div>
                          <div>
                            <div className="text-[10px] uppercase text-zinc-500">CPU</div>
                            <input
                              type="number"
                              className="mt-1 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-100 outline-none focus:border-zinc-600"
                              value={addScwPreset.cpu}
                              min={1}
                              max={64}
                              onChange={(e) => setAddScwPreset((p) => ({ ...p, cpu: clamp(Number(e.target.value), 1, 64) }))}
                            />
                          </div>
                          <div>
                            <div className="text-[10px] uppercase text-zinc-500">Memory (MB)</div>
                            <input
                              type="number"
                              className="mt-1 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-100 outline-none focus:border-zinc-600"
                              value={addScwPreset.memoryMb}
                              min={128}
                              max={262144}
                              onChange={(e) => setAddScwPreset((p) => ({ ...p, memoryMb: clamp(Number(e.target.value), 128, 262144) }))}
                            />
                          </div>
                          <div>
                            <div className="text-[10px] uppercase text-zinc-500">Network</div>
                            <select
                              className="mt-1 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-100 outline-none focus:border-zinc-600"
                              value={addScwPreset.network}
                              onChange={(e) => setAddScwPreset((p) => ({ ...p, network: e.target.value as any }))}
                            >
                              <option value="none">none</option>
                              <option value="egress">egress</option>
                              <option value="egress+ingress">egress+ingress</option>
                            </select>
                          </div>
                          <div>
                            <div className="text-[10px] uppercase text-zinc-500">Time source</div>
                            <select
                              className="mt-1 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-100 outline-none focus:border-zinc-600"
                              value={addScwPreset.timeSource}
                              onChange={(e) => setAddScwPreset((p) => ({ ...p, timeSource: e.target.value as any }))}
                            >
                              <option value="monotonic+wall">monotonic+wall</option>
                              <option value="monotonic">monotonic</option>
                              <option value="wall">wall</option>
                            </select>
                          </div>
                        </div>

                        <div className="mt-3 text-xs text-zinc-500">Tool adapters (comma-separated)</div>
                        <input
                          className="mt-1 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-100 outline-none focus:border-zinc-600"
                          value={addScwPreset.toolAdapters.join(",")}
                          onChange={(e) =>
                            setAddScwPreset((p) => ({
                              ...p,
                              toolAdapters: e.target.value
                                .split(",")
                                .map((x) => x.trim())
                                .filter(Boolean)
                            }))
                          }
                        />

                        <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
                          <label className="flex items-center gap-2 rounded-2xl border border-zinc-800 bg-zinc-900/20 p-2">
                            <input
                              type="checkbox"
                              checked={addScwPreset.runHeaderRequired}
                              onChange={(e) => setAddScwPreset((p) => ({ ...p, runHeaderRequired: e.target.checked }))}
                            />
                            <span className="text-zinc-300">Run header</span>
                          </label>
                          <label className="flex items-center gap-2 rounded-2xl border border-zinc-800 bg-zinc-900/20 p-2">
                            <input
                              type="checkbox"
                              checked={addScwPreset.tickLoggingRequired}
                              onChange={(e) => setAddScwPreset((p) => ({ ...p, tickLoggingRequired: e.target.checked }))}
                            />
                            <span className="text-zinc-300">Tick logging</span>
                          </label>
                          <label className="flex items-center gap-2 rounded-2xl border border-zinc-800 bg-zinc-900/20 p-2">
                            <input
                              type="checkbox"
                              checked={addScwPreset.verificationBlockRequired}
                              onChange={(e) => setAddScwPreset((p) => ({ ...p, verificationBlockRequired: e.target.checked }))}
                            />
                            <span className="text-zinc-300">Verify block</span>
                          </label>
                        </div>
                      </div>

                      <button
                        className="mt-3 w-full rounded-xl border border-zinc-800 bg-zinc-100 px-3 py-2 text-sm font-medium text-zinc-900 hover:bg-white"
                        onClick={addScwAtDefault}
                      >
                        Add SCW (spawns SCW{nextScwOrdinal})
                      </button>
                    </>
                  )}

                  <div className="mt-6 rounded-2xl border border-zinc-800 bg-zinc-900/20 p-3 text-xs text-zinc-400">
                    <div className="font-semibold text-zinc-200">Maxey00</div>
                    <div className="mt-1">Superposition agent with observability edges and global properties.</div>
                    <button
                      className="mt-3 w-full rounded-xl border border-zinc-800 bg-zinc-100 px-3 py-2 text-sm font-medium text-zinc-900 hover:bg-white"
                      onClick={addMaxey00IfMissing}
                    >
                      Add Maxey00
                    </button>
                  </div>

                  <div className="mt-6 rounded-2xl border border-zinc-800 bg-zinc-900/20 p-3 text-xs text-zinc-400">
                    <div className="font-semibold text-zinc-200">Edge kind for new edges</div>
                    <div className="mt-2">
                      <select
                        className="w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-100 outline-none focus:border-zinc-600"
                        value={edgeCreateKind}
                        onChange={(e) => setEdgeCreateKind(e.target.value as any)}
                      >
                        <option value="calls">calls</option>
                        <option value="routes_to">routes_to</option>
                        <option value="promotes_to">promotes_to</option>
                        <option value="logs_to">logs_to</option>
                        <option value="reads_from">reads_from</option>
                        <option value="writes_to">writes_to</option>
                        <option value="depends_on">depends_on</option>
                        <option value="observes">observes</option>
                      </select>
                    </div>
                    <div className="mt-2 text-[10px] text-zinc-500">Click a node’s right handle to start an edge, then click a target node.</div>
                  </div>

                  <div className="mt-6 rounded-2xl border border-zinc-800 bg-zinc-900/20 p-3 text-xs text-zinc-400">
                    <div className="font-semibold text-zinc-200">Import JSON</div>
                    <textarea
                      ref={importBoxRef}
                      className="mt-2 h-28 w-full rounded-2xl border border-zinc-800 bg-zinc-950 p-3 text-xs text-zinc-200 outline-none focus:border-zinc-600"
                      placeholder="Paste exported JSON here"
                    />
                    <button
                      className="mt-2 w-full rounded-xl border border-zinc-800 bg-zinc-100 px-3 py-2 text-sm font-medium text-zinc-900 hover:bg-white"
                      onClick={() => importJsonFromText(importBoxRef.current?.value ?? "")}
                    >
                      Import
                    </button>

                    <div className="mt-4 rounded-2xl border border-zinc-800 bg-zinc-950 p-3">
                      <div className="text-sm font-semibold text-zinc-100">Latent-space UI</div>
                      <div className="mt-2 text-xs text-zinc-500">Depth scale</div>
                      <input
                        type="range"
                        min={0}
                        max={1.5}
                        step={0.05}
                        value={ui.latentZScale}
                        onChange={(e) => setUi((u) => ({ ...u, latentZScale: Number(e.target.value) }))}
                        className="mt-2 w-full"
                      />
                      <div className="mt-3 text-xs text-zinc-500">Depth mode</div>
                      <select
                        className="mt-1 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-100 outline-none focus:border-zinc-600"
                        value={ui.latentDepthMode}
                        onChange={(e) => setUi((u) => ({ ...u, latentDepthMode: e.target.value as any }))}
                      >
                        <option value="shadow">shadow</option>
                        <option value="parallax">parallax</option>
                      </select>
                    </div>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>

        {/* Canvas */}
        <div className="relative min-w-0 flex-1 bg-zinc-950">
          <div
            ref={canvasRef}
            data-role="canvas"
            className="absolute inset-0"
            onMouseDown={onCanvasMouseDown}
            onMouseMove={onCanvasMouseMove}
            onMouseUp={onCanvasMouseUp}
            onMouseLeave={onCanvasMouseUp}
            onWheel={onWheel}
            onDrop={onDrop}
            onDragOver={onDragOver}
          >
            {/* Latent-space background: multi-layer grid + radial gradient */}
            <div
              className="absolute inset-0"
              style={{
                background:
                  "radial-gradient(1200px 700px at 65% 30%, rgba(0,163,255,0.10), transparent 60%), radial-gradient(900px 600px at 30% 70%, rgba(255,0,245,0.08), transparent 60%), radial-gradient(700px 400px at 20% 20%, rgba(0,255,127,0.06), transparent 55%), #09090b"
              }}
            />
            <div
              className="absolute inset-0"
              style={{
                backgroundImage:
                  "linear-gradient(to right, rgba(39,39,42,0.30) 1px, transparent 1px), linear-gradient(to bottom, rgba(39,39,42,0.30) 1px, transparent 1px)",
                backgroundSize: `${20 * ui.zoom}px ${20 * ui.zoom}px`,
                backgroundPosition: `${ui.panX}px ${ui.panY}px`
              }}
            />

            {/* Edges */}
            <svg
              className="absolute inset-0"
              style={{
                transform: `translate(${ui.panX}px, ${ui.panY}px) scale(${ui.zoom})`,
                transformOrigin: "0 0"
              }}
            >
              <defs>
                <marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="5" orient="auto">
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="#A1A1AA" />
                </marker>
              </defs>

              {edgeSegments.map((seg) => {
                const isSel = selectedEdge?.id === seg.edge.id;
                const isObserve = seg.edge.kind === "observes";
                const stroke = isSel ? "#E4E4E7" : isObserve ? "#7AE7FF" : "#A1A1AA";
                const dash = isObserve ? "7 5" : "";

                return (
                  <g key={seg.edge.id}>
                    <path
                      d={seg.d}
                      fill="none"
                      stroke={stroke}
                      strokeWidth={isSel ? 2.2 : 1.6}
                      markerEnd="url(#arrow)"
                      strokeDasharray={dash}
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelected({ kind: "edge", id: seg.edge.id });
                      }}
                      style={{ cursor: "pointer" }}
                    />
                    <g
                      transform={`translate(${seg.labelX}, ${seg.labelY})`}
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelected({ kind: "edge", id: seg.edge.id });
                      }}
                      style={{ cursor: "pointer" }}
                    >
                      <rect x={-44} y={-12} width={88} height={24} rx={12} ry={12} fill="#09090b" stroke="#27272a" />
                      <text x={0} y={4} textAnchor="middle" fontSize={10} fill="#E4E4E7">
                        {seg.edge.label}
                      </text>
                    </g>
                  </g>
                );
              })}

              {linkPreview && (
                <g>
                  <path d={linkPreview.d} fill="none" stroke="#E4E4E7" strokeWidth={1.6} markerEnd="url(#arrow)" strokeDasharray="6 4" />
                  <g transform={`translate(${linkPreview.labelX}, ${linkPreview.labelY})`}>
                    <rect x={-44} y={-12} width={88} height={24} rx={12} ry={12} fill="#09090b" stroke="#3f3f46" />
                    <text x={0} y={4} textAnchor="middle" fontSize={10} fill="#E4E4E7">
                      {linkPreview.label}
                    </text>
                  </g>
                </g>
              )}
            </svg>

            {/* Nodes */}
            <div
              className="absolute inset-0"
              style={{
                transform: `translate(${ui.panX}px, ${ui.panY}px) scale(${ui.zoom})`,
                transformOrigin: "0 0"
              }}
            >
              {/* SCW containers */}
              {renderOrder.scwNodes.map((n) => {
                const isSelected = selected?.kind === "node" && selected.id === n.id;
                const border = isSelected ? "border-zinc-200" : "border-zinc-800";
                const det = formatDeterministicLabel(n);
                const ds = depthStyle(n);

                return (
                  <div
                    key={n.id}
                    className={classNames("absolute rounded-2xl border bg-zinc-950/70", border)}
                    style={{
                      left: n.x,
                      top: n.y,
                      width: n.w,
                      height: n.h,
                      ...ds
                    }}
                    onMouseDown={(ev) => {
                      ev.stopPropagation();
                      if (ev.button !== 0) return;
                      setSelected({ kind: "node", id: n.id });
                      dragState.current = { nodeId: n.id, startClientX: ev.clientX, startClientY: ev.clientY, startX: n.x, startY: n.y };
                    }}
                    onClick={(ev) => {
                      ev.stopPropagation();
                      setSelected({ kind: "node", id: n.id });
                    }}
                  >
                    <div className="flex items-start justify-between gap-3 p-3">
                      <div className="flex items-start gap-3">
                        <span className="mt-1 h-3 w-3 rounded" style={{ backgroundColor: n.colorHex }} />
                        <div className="leading-tight">
                          <div className="text-sm font-semibold text-zinc-100">{n.label}</div>
                          <div className="text-xs text-zinc-400">{n.scw?.purpose ?? "Structured Context Window"}</div>
                        </div>
                      </div>
                      <div className="flex flex-col items-end gap-1">
                        <span className="inline-flex items-center rounded-full border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-[10px] text-zinc-200">SCW</span>
                        {det && <span className="text-[10px] text-zinc-500">{det}</span>}
                        <span className="text-[10px] text-zinc-500">{n.scw?.runtimePreset.determinismPolicy ?? "strict"}</span>
                      </div>
                    </div>

                    <div className="px-3 pb-3">
                      <div className="flex flex-wrap gap-1">
                        {(n.tags || []).slice(0, 8).map((t) => (
                          <span key={t} className="inline-flex items-center rounded-full border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-[10px] text-zinc-300">
                            {t}
                          </span>
                        ))}
                      </div>
                    </div>

                    {/* Handles */}
                    <div
                      className="absolute left-[-6px] top-1/2 h-3 w-3 -translate-y-1/2 rounded-full border-2 border-zinc-950"
                      style={{ backgroundColor: n.colorHex }}
                      title="Target handle"
                      onMouseDown={(ev) => ev.stopPropagation()}
                      onClick={(ev) => {
                        ev.stopPropagation();
                        const st = linkState.current;
                        if (st) endEdgeCreate(n.id);
                        else setSelected({ kind: "node", id: n.id });
                      }}
                    />
                    <div
                      className="absolute right-[-6px] top-1/2 h-3 w-3 -translate-y-1/2 rounded-full border-2 border-zinc-950"
                      style={{ backgroundColor: n.colorHex }}
                      title="Source handle"
                      onMouseDown={(ev) => ev.stopPropagation()}
                      onClick={(ev) => {
                        ev.stopPropagation();
                        beginEdgeCreate(n.id, edgeCreateKind);
                      }}
                    />

                    {/* Light projection overlay */}
                    <div
                      className="pointer-events-none absolute inset-0 rounded-2xl"
                      style={{
                        background: `linear-gradient(135deg, ${n.colorHex}10, transparent 60%)`
                      }}
                    />
                  </div>
                );
              })}

              {/* Agents */}
              {renderOrder.agentNodes.map((n) => {
                const isSelected = selected?.kind === "node" && selected.id === n.id;
                const border = isSelected ? "border-zinc-200" : "border-zinc-800";
                const det = formatDeterministicLabel(n);
                const ds = depthStyle(n);
                const scw = n.parentScwId ? nodeById.get(n.parentScwId) : null;

                // If inside SCW, ensure agent stays visually within (soft constraint)
                let ax = n.x;
                let ay = n.y;
                if (scw && scw.kind === "scw") {
                  const pad = 24;
                  ax = clamp(ax, scw.x + pad, scw.x + scw.w - n.w - pad);
                  ay = clamp(ay, scw.y + 66, scw.y + scw.h - n.h - pad);
                  if (ax !== n.x || ay !== n.y) {
                    // apply correction
                    setTimeout(() => updateNode(n.id, { x: ax, y: ay }), 0);
                  }
                }

                return (
                  <div
                    key={n.id}
                    className={classNames("absolute rounded-2xl border bg-zinc-950/90", border)}
                    style={{ left: ax, top: ay, width: n.w, height: n.h, ...ds }}
                    onMouseDown={(ev) => {
                      ev.stopPropagation();
                      if (ev.button !== 0) return;
                      setSelected({ kind: "node", id: n.id });
                      dragState.current = { nodeId: n.id, startClientX: ev.clientX, startClientY: ev.clientY, startX: ax, startY: ay };
                    }}
                    onClick={(ev) => {
                      ev.stopPropagation();
                      setSelected({ kind: "node", id: n.id });
                    }}
                  >
                    <div className="flex items-start justify-between gap-3 p-3">
                      <div className="flex items-start gap-3">
                        <span className="mt-1 h-3 w-3 rounded-full" style={{ backgroundColor: n.colorHex }} />
                        <div className="leading-tight">
                          <div className="text-sm font-semibold text-zinc-100">{n.label}</div>
                          <div className="text-xs text-zinc-400">{n.agent?.specializationLabel ?? "Agent"}</div>
                        </div>
                      </div>
                      <div className="flex flex-col items-end gap-1">
                        <span className="inline-flex items-center rounded-full border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-[10px] text-zinc-200">AGENT</span>
                        {det && <span className="text-[10px] text-zinc-500">{det}</span>}
                        <span className="text-[10px] text-zinc-500">{(n.agent?.memoryScope ?? "sp").toUpperCase()}</span>
                      </div>
                    </div>

                    <div className="px-3 pb-3">
                      <div className="flex flex-wrap gap-1">
                        {(n.tags || []).slice(0, 6).map((t) => (
                          <span key={t} className="inline-flex items-center rounded-full border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-[10px] text-zinc-300">
                            {t}
                          </span>
                        ))}
                      </div>
                    </div>

                    {/* Handles */}
                    <div
                      className="absolute left-[-6px] top-1/2 h-3 w-3 -translate-y-1/2 rounded-full border-2 border-zinc-950"
                      style={{ backgroundColor: n.colorHex }}
                      title="Target handle"
                      onMouseDown={(ev) => ev.stopPropagation()}
                      onClick={(ev) => {
                        ev.stopPropagation();
                        const st = linkState.current;
                        if (st) endEdgeCreate(n.id);
                        else setSelected({ kind: "node", id: n.id });
                      }}
                    />
                    <div
                      className="absolute right-[-6px] top-1/2 h-3 w-3 -translate-y-1/2 rounded-full border-2 border-zinc-950"
                      style={{ backgroundColor: n.colorHex }}
                      title="Source handle"
                      onMouseDown={(ev) => ev.stopPropagation()}
                      onClick={(ev) => {
                        ev.stopPropagation();
                        beginEdgeCreate(n.id, edgeCreateKind);
                      }}
                    />
                  </div>
                );
              })}

              {/* Maxey00 on top */}
              {renderOrder.m00Nodes.map((n) => {
                const isSelected = selected?.kind === "node" && selected.id === n.id;
                const border = isSelected ? "border-zinc-200" : "border-zinc-700";
                const det = "Maxey00";
                const ds = depthStyle(n);

                return (
                  <div
                    key={n.id}
                    className={classNames("absolute rounded-2xl border bg-zinc-950/90", border)}
                    style={{ left: n.x, top: n.y, width: n.w, height: n.h, ...ds }}
                    onMouseDown={(ev) => {
                      ev.stopPropagation();
                      if (ev.button !== 0) return;
                      setSelected({ kind: "node", id: n.id });
                      dragState.current = { nodeId: n.id, startClientX: ev.clientX, startClientY: ev.clientY, startX: n.x, startY: n.y };
                    }}
                    onClick={(ev) => {
                      ev.stopPropagation();
                      setSelected({ kind: "node", id: n.id });
                    }}
                  >
                    <div className="flex items-start justify-between gap-3 p-3">
                      <div className="flex items-start gap-3">
                        <span className="mt-1 h-3 w-3 rounded-full" style={{ backgroundColor: n.colorHex }} />
                        <div className="leading-tight">
                          <div className="text-sm font-semibold text-zinc-100">{n.label}</div>
                          <div className="text-xs text-zinc-400">Superposition / Observability</div>
                        </div>
                      </div>
                      <div className="flex flex-col items-end gap-1">
                        <span className="inline-flex items-center rounded-full border border-zinc-700 bg-zinc-900 px-2 py-0.5 text-[10px] text-zinc-100">MAXEY00</span>
                        <span className="text-[10px] text-zinc-500">{det}</span>
                        <span className="text-[10px] text-zinc-500">{n.maxey00?.observability ?? "global"}</span>
                      </div>
                    </div>

                    <div className="px-3 pb-3 text-xs text-zinc-400">
                      {n.maxey00?.notes ?? "Observes across SCWs"}
                    </div>

                    {/* Handles */}
                    <div
                      className="absolute left-[-6px] top-1/2 h-3 w-3 -translate-y-1/2 rounded-full border-2 border-zinc-950"
                      style={{ backgroundColor: "#7AE7FF" }}
                      title="Target handle"
                      onMouseDown={(ev) => ev.stopPropagation()}
                      onClick={(ev) => {
                        ev.stopPropagation();
                        const st = linkState.current;
                        if (st) endEdgeCreate(n.id);
                        else setSelected({ kind: "node", id: n.id });
                      }}
                    />
                    <div
                      className="absolute right-[-6px] top-1/2 h-3 w-3 -translate-y-1/2 rounded-full border-2 border-zinc-950"
                      style={{ backgroundColor: "#7AE7FF" }}
                      title="Source handle"
                      onMouseDown={(ev) => ev.stopPropagation()}
                      onClick={(ev) => {
                        ev.stopPropagation();
                        beginEdgeCreate(n.id, "observes");
                      }}
                    />

                    {/* Observability halo */}
                    <div
                      className="pointer-events-none absolute inset-0 rounded-2xl"
                      style={{
                        boxShadow: "0 0 0 1px rgba(122,231,255,0.18), 0 0 40px rgba(122,231,255,0.12)"
                      }}
                    />
                  </div>
                );
              })}
            </div>

            {/* HUD */}
            <div className="pointer-events-none absolute bottom-3 left-3 rounded-2xl border border-zinc-800 bg-zinc-950/80 p-3 text-xs text-zinc-300">
              <div className="flex items-center gap-2">
                <span className="inline-flex items-center rounded-full border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-[10px] text-zinc-200">{nodes.length} nodes</span>
                <span className="inline-flex items-center rounded-full border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-[10px] text-zinc-200">{edges.length} edges</span>
                <span className="inline-flex items-center rounded-full border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-[10px] text-zinc-200">zoom {ui.zoom.toFixed(2)}</span>
                <span className="inline-flex items-center rounded-full border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-[10px] text-zinc-200">depth {ui.latentZScale.toFixed(2)}</span>
              </div>
              <div className="mt-2 text-[10px] text-zinc-500">Ctrl+wheel zoom • middle mouse pan • space+drag pan • right-handle edge</div>
            </div>
          </div>
        </div>

        {/* Inspector */}
        <div className="w-[420px] shrink-0 border-l border-zinc-800 bg-zinc-950">
          <div className="p-3">
            <div className="text-sm font-semibold">Inspector</div>
            <div className="mt-1 text-xs text-zinc-500">Edit node ordinals (Maxey#/SCW#), specialization, runtime parameters, and observability edges.</div>
          </div>

          <div className="h-[calc(100%-76px)] overflow-auto p-3 pt-0">
            {!selected && (
              <div className="rounded-2xl border border-zinc-800 bg-zinc-900/20 p-3 text-sm text-zinc-300">
                <div className="font-semibold text-zinc-200">Nothing selected</div>
                <div className="mt-2 text-xs text-zinc-400">Click a node or edge on the canvas.</div>
              </div>
            )}

            {selectedNode && (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="text-sm font-semibold">Node</div>
                  <button
                    className="rounded-xl border border-red-900/60 bg-red-500/10 px-3 py-2 text-sm font-medium text-red-200 hover:bg-red-500/20"
                    onClick={() => deleteNode(selectedNode.id)}
                    disabled={selectedNode.kind === "maxey00" && selectedNode.id === "maxey00"}
                    title={selectedNode.kind === "maxey00" ? "Delete Maxey00 by removing from export/import (or clear all)." : "Delete node"}
                  >
                    Delete
                  </button>
                </div>

                <div className="rounded-2xl border border-zinc-800 bg-zinc-900/20 p-3">
                  <div className="text-xs text-zinc-500">Label</div>
                  <input
                    className="mt-1 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-600"
                    value={selectedNode.label}
                    onChange={(e) => updateNode(selectedNode.id, { label: e.target.value })}
                  />

                  <div className="mt-3 text-xs text-zinc-500">Deterministic ordinal</div>
                  <div className="mt-2 flex items-center gap-2">
                    <label className="flex items-center gap-2 rounded-2xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-200">
                      <input
                        type="checkbox"
                        checked={selectedNode.deterministicEnabled}
                        disabled={selectedNode.kind === "maxey00"}
                        onChange={(e) =>
                          updateNode(selectedNode.id, {
                            deterministicEnabled: e.target.checked,
                            deterministicOrdinal: e.target.checked ? selectedNode.deterministicOrdinal ?? 0 : undefined
                          })
                        }
                      />
                      <span>Enable deterministic</span>
                    </label>

                    {(selectedNode.kind === "agent" || selectedNode.kind === "scw") && (
                      <input
                        type="number"
                        className="w-[120px] rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-100 outline-none focus:border-zinc-600"
                        value={selectedNode.deterministicOrdinal ?? ""}
                        placeholder={selectedNode.kind === "agent" ? "Maxey#" : "SCW#"}
                        onChange={(e) => {
                          const v = e.target.value.trim();
                          updateNode(selectedNode.id, {
                            deterministicOrdinal: v.length ? clamp(Number(v), 0, 100000) : undefined
                          });
                        }}
                        disabled={!selectedNode.deterministicEnabled}
                      />
                    )}

                    <div className="text-xs text-zinc-400">{formatDeterministicLabel(selectedNode) || "(none)"}</div>
                  </div>

                  <div className="mt-3 text-xs text-zinc-500">Color</div>
                  <select
                    className="mt-1 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-600"
                    value={selectedNode.colorHex}
                    onChange={(e) => updateNode(selectedNode.id, { colorHex: e.target.value })}
                  >
                    {PALETTE_32.map((c) => (
                      <option key={c.id} value={c.hex}>
                        {c.name} ({c.hex})
                      </option>
                    ))}
                  </select>

                  <div className="mt-3 text-xs text-zinc-500">Tags (comma-separated)</div>
                  <input
                    className="mt-1 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-600"
                    value={selectedNode.tags.join(",")}
                    onChange={(e) =>
                      updateNode(selectedNode.id, {
                        tags: e.target.value
                          .split(",")
                          .map((x) => x.trim())
                          .filter(Boolean)
                      })
                    }
                  />

                  {/* Container assignment */}
                  {selectedNode.kind === "agent" && (
                    <>
                      <div className="mt-3 text-xs text-zinc-500">Contained in SCW</div>
                      <select
                        className="mt-1 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-600"
                        value={selectedNode.parentScwId ?? ""}
                        onChange={(e) => updateNode(selectedNode.id, { parentScwId: e.target.value ? e.target.value : null })}
                      >
                        <option value="">(outside)</option>
                        {scws.map((s) => (
                          <option key={s.id} value={s.id}>
                            {s.label} {formatDeterministicLabel(s) ? `(${formatDeterministicLabel(s)})` : ""}
                          </option>
                        ))}
                      </select>
                    </>
                  )}

                  {/* Agent-specific */}
                  {selectedNode.kind === "agent" && selectedNode.agent && (
                    <div className="mt-4 rounded-2xl border border-zinc-800 bg-zinc-950 p-3">
                      <div className="text-sm font-semibold text-zinc-100">Agent Specialization</div>

                      <div className="mt-2 text-xs text-zinc-500">Specialization</div>
                      <select
                        className="mt-1 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-600"
                        value={selectedNode.agent.specializationKey}
                        onChange={(e) => {
                          const key = e.target.value as Maxey0AgentSpecKey;
                          const spec = pickSpecByKey(key);
                          updateNode(selectedNode.id, {
                            agent: {
                              ...selectedNode.agent!,
                              specializationKey: key,
                              specializationLabel: spec.label,
                              specializationDescription: spec.description,
                              tools: deepCopy(spec.defaultTools)
                            }
                          });
                        }}
                      >
                        {MAXEY0_AGENT_SPECS.map((s) => (
                          <option key={s.key} value={s.key}>
                            {s.label}
                          </option>
                        ))}
                      </select>

                      <div className="mt-3 text-xs text-zinc-500">Description (auto-loaded for defaults; editable)</div>
                      <textarea
                        className="mt-1 h-24 w-full rounded-2xl border border-zinc-800 bg-zinc-950 p-3 text-sm text-zinc-100 outline-none focus:border-zinc-600"
                        value={selectedNode.agent.specializationDescription}
                        onChange={(e) =>
                          updateNode(selectedNode.id, {
                            agent: { ...selectedNode.agent!, specializationDescription: e.target.value }
                          })
                        }
                      />

                      <div className="mt-3 text-xs text-zinc-500">Tools (comma-separated)</div>
                      <input
                        className="mt-1 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-600"
                        value={selectedNode.agent.tools.join(",")}
                        onChange={(e) =>
                          updateNode(selectedNode.id, {
                            agent: {
                              ...selectedNode.agent!,
                              tools: e.target.value
                                .split(",")
                                .map((x) => x.trim())
                                .filter(Boolean)
                            }
                          })
                        }
                      />

                      <div className="mt-3 text-xs text-zinc-500">Memory scope</div>
                      <select
                        className="mt-1 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-600"
                        value={selectedNode.agent.memoryScope}
                        onChange={(e) => updateNode(selectedNode.id, { agent: { ...selectedNode.agent!, memoryScope: e.target.value as any } })}
                      >
                        <option value="sp">sp</option>
                        <option value="ep">ep</option>
                        <option value="pr">pr</option>
                        <option value="pm">pm</option>
                      </select>

                      <div className="mt-3 text-xs text-zinc-500">Notes</div>
                      <textarea
                        className="mt-1 h-20 w-full rounded-2xl border border-zinc-800 bg-zinc-950 p-3 text-sm text-zinc-100 outline-none focus:border-zinc-600"
                        value={selectedNode.agent.notes}
                        onChange={(e) => updateNode(selectedNode.id, { agent: { ...selectedNode.agent!, notes: e.target.value } })}
                      />
                    </div>
                  )}

                  {/* SCW-specific */}
                  {selectedNode.kind === "scw" && selectedNode.scw && (
                    <div className="mt-4 rounded-2xl border border-zinc-800 bg-zinc-950 p-3">
                      <div className="text-sm font-semibold text-zinc-100">SCW Runtime (containerized)</div>

                      <div className="mt-2 text-xs text-zinc-500">Purpose</div>
                      <input
                        className="mt-1 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-600"
                        value={selectedNode.scw.purpose}
                        onChange={(e) => updateNode(selectedNode.id, { scw: { ...selectedNode.scw!, purpose: e.target.value } })}
                      />

                      <div className="mt-3 text-xs text-zinc-500">Runtime preset parameters</div>
                      <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
                        <div>
                          <div className="text-[10px] uppercase text-zinc-500">Runtime</div>
                          <select
                            className="mt-1 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-100 outline-none focus:border-zinc-600"
                            value={selectedNode.scw.runtimePreset.runtime}
                            onChange={(e) =>
                              updateNode(selectedNode.id, {
                                scw: { ...selectedNode.scw!, runtimePreset: { ...selectedNode.scw!.runtimePreset, runtime: e.target.value as any } }
                              })
                            }
                          >
                            <option value="container">container</option>
                            <option value="python">python</option>
                            <option value="node">node</option>
                            <option value="dotnet">dotnet</option>
                            <option value="rust">rust</option>
                            <option value="go">go</option>
                          </select>
                        </div>
                        <div>
                          <div className="text-[10px] uppercase text-zinc-500">Determinism</div>
                          <select
                            className="mt-1 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-100 outline-none focus:border-zinc-600"
                            value={selectedNode.scw.runtimePreset.determinismPolicy}
                            onChange={(e) =>
                              updateNode(selectedNode.id, {
                                scw: {
                                  ...selectedNode.scw!,
                                  runtimePreset: { ...selectedNode.scw!.runtimePreset, determinismPolicy: e.target.value as any }
                                }
                              })
                            }
                          >
                            <option value="strict">strict</option>
                            <option value="best-effort">best-effort</option>
                            <option value="strict+hash-chain">strict+hash-chain</option>
                          </select>
                        </div>
                        <div>
                          <div className="text-[10px] uppercase text-zinc-500">CPU</div>
                          <input
                            type="number"
                            className="mt-1 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-100 outline-none focus:border-zinc-600"
                            value={selectedNode.scw.runtimePreset.cpu}
                            min={1}
                            max={64}
                            onChange={(e) =>
                              updateNode(selectedNode.id, {
                                scw: {
                                  ...selectedNode.scw!,
                                  runtimePreset: { ...selectedNode.scw!.runtimePreset, cpu: clamp(Number(e.target.value), 1, 64) }
                                }
                              })
                            }
                          />
                        </div>
                        <div>
                          <div className="text-[10px] uppercase text-zinc-500">Memory (MB)</div>
                          <input
                            type="number"
                            className="mt-1 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-100 outline-none focus:border-zinc-600"
                            value={selectedNode.scw.runtimePreset.memoryMb}
                            min={128}
                            max={262144}
                            onChange={(e) =>
                              updateNode(selectedNode.id, {
                                scw: {
                                  ...selectedNode.scw!,
                                  runtimePreset: { ...selectedNode.scw!.runtimePreset, memoryMb: clamp(Number(e.target.value), 128, 262144) }
                                }
                              })
                            }
                          />
                        </div>
                        <div>
                          <div className="text-[10px] uppercase text-zinc-500">Network</div>
                          <select
                            className="mt-1 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-100 outline-none focus:border-zinc-600"
                            value={selectedNode.scw.runtimePreset.network}
                            onChange={(e) =>
                              updateNode(selectedNode.id, {
                                scw: { ...selectedNode.scw!, runtimePreset: { ...selectedNode.scw!.runtimePreset, network: e.target.value as any } }
                              })
                            }
                          >
                            <option value="none">none</option>
                            <option value="egress">egress</option>
                            <option value="egress+ingress">egress+ingress</option>
                          </select>
                        </div>
                        <div>
                          <div className="text-[10px] uppercase text-zinc-500">Time source</div>
                          <select
                            className="mt-1 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-100 outline-none focus:border-zinc-600"
                            value={selectedNode.scw.runtimePreset.timeSource}
                            onChange={(e) =>
                              updateNode(selectedNode.id, {
                                scw: { ...selectedNode.scw!, runtimePreset: { ...selectedNode.scw!.runtimePreset, timeSource: e.target.value as any } }
                              })
                            }
                          >
                            <option value="monotonic+wall">monotonic+wall</option>
                            <option value="monotonic">monotonic</option>
                            <option value="wall">wall</option>
                          </select>
                        </div>
                      </div>

                      <div className="mt-3 text-xs text-zinc-500">Tool adapters (comma-separated)</div>
                      <input
                        className="mt-1 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-100 outline-none focus:border-zinc-600"
                        value={selectedNode.scw.runtimePreset.toolAdapters.join(",")}
                        onChange={(e) =>
                          updateNode(selectedNode.id, {
                            scw: {
                              ...selectedNode.scw!,
                              runtimePreset: {
                                ...selectedNode.scw!.runtimePreset,
                                toolAdapters: e.target.value
                                  .split(",")
                                  .map((x) => x.trim())
                                  .filter(Boolean)
                              }
                            }
                          })
                        }
                      />

                      <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
                        <label className="flex items-center gap-2 rounded-2xl border border-zinc-800 bg-zinc-900/20 p-2">
                          <input
                            type="checkbox"
                            checked={selectedNode.scw.runtimePreset.runHeaderRequired}
                            onChange={(e) =>
                              updateNode(selectedNode.id, {
                                scw: {
                                  ...selectedNode.scw!,
                                  runtimePreset: { ...selectedNode.scw!.runtimePreset, runHeaderRequired: e.target.checked }
                                }
                              })
                            }
                          />
                          <span className="text-zinc-300">Run header</span>
                        </label>
                        <label className="flex items-center gap-2 rounded-2xl border border-zinc-800 bg-zinc-900/20 p-2">
                          <input
                            type="checkbox"
                            checked={selectedNode.scw.runtimePreset.tickLoggingRequired}
                            onChange={(e) =>
                              updateNode(selectedNode.id, {
                                scw: {
                                  ...selectedNode.scw!,
                                  runtimePreset: { ...selectedNode.scw!.runtimePreset, tickLoggingRequired: e.target.checked }
                                }
                              })
                            }
                          />
                          <span className="text-zinc-300">Tick logging</span>
                        </label>
                        <label className="flex items-center gap-2 rounded-2xl border border-zinc-800 bg-zinc-900/20 p-2">
                          <input
                            type="checkbox"
                            checked={selectedNode.scw.runtimePreset.verificationBlockRequired}
                            onChange={(e) =>
                              updateNode(selectedNode.id, {
                                scw: {
                                  ...selectedNode.scw!,
                                  runtimePreset: { ...selectedNode.scw!.runtimePreset, verificationBlockRequired: e.target.checked }
                                }
                              })
                            }
                          />
                          <span className="text-zinc-300">Verify block</span>
                        </label>
                      </div>
                    </div>
                  )}

                  {/* Maxey00-specific */}
                  {selectedNode.kind === "maxey00" && selectedNode.maxey00 && (
                    <div className="mt-4 rounded-2xl border border-zinc-800 bg-zinc-950 p-3">
                      <div className="text-sm font-semibold text-zinc-100">Maxey00 Observability</div>
                      <div className="mt-2 text-xs text-zinc-500">Scope</div>
                      <select
                        className="mt-1 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-600"
                        value={selectedNode.maxey00.observability}
                        onChange={(e) => updateNode(selectedNode.id, { maxey00: { ...selectedNode.maxey00!, observability: e.target.value as any } })}
                      >
                        <option value="global">global</option>
                        <option value="multi-scw">multi-scw</option>
                        <option value="local">local</option>
                      </select>

                      <div className="mt-3 text-xs text-zinc-500">Notes</div>
                      <textarea
                        className="mt-1 h-20 w-full rounded-2xl border border-zinc-800 bg-zinc-950 p-3 text-sm text-zinc-100 outline-none focus:border-zinc-600"
                        value={selectedNode.maxey00.notes}
                        onChange={(e) => updateNode(selectedNode.id, { maxey00: { ...selectedNode.maxey00!, notes: e.target.value } })}
                      />

                      <div className="mt-3 rounded-2xl border border-zinc-800 bg-zinc-900/20 p-3 text-xs text-zinc-400">
                        <div className="font-semibold text-zinc-200">Observability semantics</div>
                        <div className="mt-1">Use edge kind <span className="text-zinc-200">observes</span> to represent Maxey00 visibility across SCWs/agents.</div>
                      </div>
                    </div>
                  )}

                  {/* Properties */}
                  <div className="mt-4 rounded-2xl border border-zinc-800 bg-zinc-950 p-3">
                    <div className="text-sm font-semibold text-zinc-100">Properties</div>
                    <div className="mt-2 text-xs text-zinc-500">Key=Value lines (string/number/bool/null)</div>
                    <textarea
                      className="mt-2 h-28 w-full rounded-2xl border border-zinc-800 bg-zinc-950 p-3 text-xs text-zinc-200 outline-none focus:border-zinc-600"
                      value={Object.entries(selectedNode.properties)
                        .map(([k, v]) => `${k}=${String(v)}`)
                        .join("\n")}
                      onChange={(e) => {
                        const next: Record<string, any> = {};
                        for (const line of e.target.value.split("\n")) {
                          const trimmed = line.trim();
                          if (!trimmed) continue;
                          const idx = trimmed.indexOf("=");
                          if (idx <= 0) continue;
                          const k = trimmed.slice(0, idx).trim();
                          const raw = trimmed.slice(idx + 1).trim();
                          let v: any = raw;
                          if (/^true$/i.test(raw)) v = true;
                          else if (/^false$/i.test(raw)) v = false;
                          else if (/^null$/i.test(raw)) v = null;
                          else if (!Number.isNaN(Number(raw)) && raw !== "") v = Number(raw);
                          next[k] = v;
                        }
                        updateNode(selectedNode.id, { properties: next });
                      }}
                    />
                  </div>

                  {/* Latent vector */}
                  <div className="mt-4 rounded-2xl border border-zinc-800 bg-zinc-950 p-3">
                    <div className="text-sm font-semibold text-zinc-100">Latent vector (16D)</div>
                    <div className="mt-2 text-xs text-zinc-500">Edit dim[2] and dim[7] to change visual depth.</div>
                    <div className="mt-2 grid grid-cols-4 gap-2 text-xs">
                      {selectedNode.latent.v.map((val, i) => (
                        <div key={i} className="rounded-xl border border-zinc-800 bg-zinc-900/20 p-2">
                          <div className="text-[10px] uppercase text-zinc-500">d{i}</div>
                          <input
                            className="mt-1 w-full rounded-lg border border-zinc-800 bg-zinc-950 px-2 py-1 text-xs text-zinc-100 outline-none focus:border-zinc-600"
                            value={val.toFixed(3)}
                            onChange={(e) => {
                              const raw = e.target.value.trim();
                              const num = Number(raw);
                              if (Number.isNaN(num)) return;
                              const next = [...selectedNode.latent.v];
                              next[i] = clamp(num, -1, 1);
                              updateNode(selectedNode.id, { latent: { v: next } });
                            }}
                          />
                        </div>
                      ))}
                    </div>
                    <button
                      className="mt-3 w-full rounded-xl border border-zinc-800 bg-zinc-100 px-3 py-2 text-sm font-medium text-zinc-900 hover:bg-white"
                      onClick={() => updateNode(selectedNode.id, { latent: randLatent16() })}
                    >
                      Re-roll latent
                    </button>
                  </div>
                </div>

                <div className="rounded-2xl border border-zinc-800 bg-zinc-900/20 p-3 text-xs text-zinc-400">
                  <div className="font-semibold text-zinc-200">Edge creation</div>
                  <div className="mt-1">Use right handle to start edge (kind set in Add tab). Click target to finish.</div>
                </div>
              </div>
            )}

            {selectedEdge && (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="text-sm font-semibold">Edge</div>
                  <button
                    className="rounded-xl border border-red-900/60 bg-red-500/10 px-3 py-2 text-sm font-medium text-red-200 hover:bg-red-500/20"
                    onClick={() => deleteEdge(selectedEdge.id)}
                  >
                    Delete
                  </button>
                </div>

                <div className="rounded-2xl border border-zinc-800 bg-zinc-900/20 p-3">
                  <div className="text-xs text-zinc-500">Label</div>
                  <input
                    className="mt-1 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-600"
                    value={selectedEdge.label}
                    onChange={(e) => updateEdge(selectedEdge.id, { label: e.target.value })}
                  />

                  <div className="mt-3 text-xs text-zinc-500">Kind</div>
                  <select
                    className="mt-1 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-600"
                    value={selectedEdge.kind}
                    onChange={(e) => updateEdge(selectedEdge.id, { kind: e.target.value as any, label: e.target.value })}
                  >
                    <option value="calls">calls</option>
                    <option value="routes_to">routes_to</option>
                    <option value="promotes_to">promotes_to</option>
                    <option value="logs_to">logs_to</option>
                    <option value="reads_from">reads_from</option>
                    <option value="writes_to">writes_to</option>
                    <option value="depends_on">depends_on</option>
                    <option value="observes">observes</option>
                  </select>

                  <div className="mt-3 rounded-2xl border border-zinc-800 bg-zinc-950 p-3 text-xs text-zinc-400">
                    <div className="text-[10px] uppercase text-zinc-500">Source → Target</div>
                    <div className="mt-1 text-zinc-200">
                      {selectedEdge.sourceId} → {selectedEdge.targetId}
                    </div>
                  </div>

                  <div className="mt-4 rounded-2xl border border-zinc-800 bg-zinc-950 p-3">
                    <div className="text-sm font-semibold text-zinc-100">Properties</div>
                    <div className="mt-2 text-xs text-zinc-500">Key=Value lines (string/number/bool/null)</div>
                    <textarea
                      className="mt-2 h-28 w-full rounded-2xl border border-zinc-800 bg-zinc-950 p-3 text-xs text-zinc-200 outline-none focus:border-zinc-600"
                      value={Object.entries(selectedEdge.properties)
                        .map(([k, v]) => `${k}=${String(v)}`)
                        .join("\n")}
                      onChange={(e) => {
                        const next: Record<string, any> = {};
                        for (const line of e.target.value.split("\n")) {
                          const trimmed = line.trim();
                          if (!trimmed) continue;
                          const idx = trimmed.indexOf("=");
                          if (idx <= 0) continue;
                          const k = trimmed.slice(0, idx).trim();
                          const raw = trimmed.slice(idx + 1).trim();
                          let v: any = raw;
                          if (/^true$/i.test(raw)) v = true;
                          else if (/^false$/i.test(raw)) v = false;
                          else if (/^null$/i.test(raw)) v = null;
                          else if (!Number.isNaN(Number(raw)) && raw !== "") v = Number(raw);
                          next[k] = v;
                        }
                        updateEdge(selectedEdge.id, { properties: next });
                      }}
                    />
                  </div>
                </div>

                <div className="rounded-2xl border border-zinc-800 bg-zinc-900/20 p-3 text-xs text-zinc-400">
                  <div className="font-semibold text-zinc-200">Observability</div>
                  <div className="mt-1">Use <span className="text-zinc-200">observes</span> edges (usually from Maxey00) to represent cross-SCW visibility/verification.</div>
                </div>
              </div>
            )}
          </div>

          <div className="border-t border-zinc-800 p-3 text-xs text-zinc-500">
            <div className="flex items-center justify-between">
              <div>Local-only state • Export includes optional deterministic maps</div>
              <div className="flex items-center gap-2">
                <button
                  className="rounded-xl border border-zinc-800 bg-transparent px-3 py-2 text-xs font-medium text-zinc-200 hover:bg-zinc-900"
                  onClick={() => setUi({ ...ui, panX: 0, panY: 0, zoom: 1 })}
                >
                  Reset View
                </button>
                <button
                  className="rounded-xl border border-zinc-800 bg-transparent px-3 py-2 text-xs font-medium text-zinc-200 hover:bg-zinc-900"
                  onClick={() => setZoom(ui.zoom * 1.12)}
                >
                  +
                </button>
                <button
                  className="rounded-xl border border-zinc-800 bg-transparent px-3 py-2 text-xs font-medium text-zinc-200 hover:bg-zinc-900"
                  onClick={() => setZoom(ui.zoom * 0.9)}
                >
                  -
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Global click to end edge create if active */}
      <div
        className="hidden"
        onClick={() => {
          if (linkState.current) linkState.current = null;
        }}
      />
    </div>
  );
}
