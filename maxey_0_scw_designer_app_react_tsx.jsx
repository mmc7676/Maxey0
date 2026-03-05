import React, { useEffect, useMemo, useRef, useState } from "react";

type Maxey0NodeKind = "agent" | "scw";

type Maxey0Node = {
  id: string;
  kind: Maxey0NodeKind;
  label: string;
  colorHex: string;
  x: number;
  y: number;
  w: number;
  h: number;
  tags: string[];
  properties: Record<string, string | number | boolean | null>;
  agentContract?: {
    agentId: string;
    role: string;
    tools: string[];
    memoryScope: "sp" | "ep" | "pr" | "pm";
    notes: string;
  };
  scwContract?: {
    scwId: string;
    purpose: string;
    runHeaderRequired: boolean;
    tickLoggingRequired: boolean;
    determinismPolicy: string;
    verificationBlockRequired: boolean;
  };
};

type Maxey0EdgeKind =
  | "calls"
  | "routes_to"
  | "promotes_to"
  | "logs_to"
  | "reads_from"
  | "writes_to"
  | "depends_on";

type Maxey0Edge = {
  id: string;
  sourceId: string;
  targetId: string;
  kind: Maxey0EdgeKind;
  label: string;
  properties: Record<string, string | number | boolean | null>;
};

type ExportPayload = {
  version: "1.0.0";
  exportedAtIso: string;
  nodes: Maxey0Node[];
  edges: Maxey0Edge[];
  ui: {
    panX: number;
    panY: number;
    zoom: number;
  };
};

const MAXEY0_STORAGE_KEY = "maxey0_scw_designer_app_v1";

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

function maxey0ColorByIndex(idx: number): string {
  const safe = Math.abs(idx) % PALETTE_32.length;
  return PALETTE_32[safe]!.hex;
}

function uid(prefix: string): string {
  // Deterministic-enough for local UI (no crypto dependency)
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
}

function clamp(n: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, n));
}

function deepCopy<T>(x: T): T {
  return JSON.parse(JSON.stringify(x)) as T;
}

function makeDefaultCatalog(): { agents: Maxey0Node[]; scws: Maxey0Node[] } {
  const agents: Maxey0Node[] = [];
  for (let i = 1; i <= 32; i++) {
    const agentId = `Maxey${i}`;
    const specialization = i % 4 === 0 ? "validator" : i % 4 === 1 ? "search" : i % 4 === 2 ? "selector" : "sorter";
    agents.push({
      id: `tpl_agent_${i}`,
      kind: "agent",
      label: agentId,
      colorHex: maxey0ColorByIndex(i - 1),
      x: 0,
      y: 0,
      w: 220,
      h: 92,
      tags: ["agent", "maxey0", specialization],
      properties: {
        specialization,
        concurrencyClass: i % 2 === 0 ? "parallel" : "serial"
      },
      agentContract: {
        agentId,
        role: specialization === "search" ? "Web Search" : specialization === "selector" ? "Selector" : specialization === "sorter" ? "Sorter" : "Validator",
        tools:
          specialization === "search"
            ? ["web.run"]
            : specialization === "validator"
              ? ["schema.validate", "diff.check"]
              : ["state.reduce"],
        memoryScope: i % 3 === 0 ? "ep" : i % 3 === 1 ? "sp" : "pr",
        notes: ""
      }
    });
  }

  const scws: Maxey0Node[] = [];
  for (let i = 0; i < 30; i++) {
    const scwId = `SCW${i}`;
    scws.push({
      id: `tpl_scw_${i}`,
      kind: "scw",
      label: scwId,
      colorHex: maxey0ColorByIndex((i + 32) % 32),
      x: 0,
      y: 0,
      w: 260,
      h: 122,
      tags: ["scw", "maxey0", i < 10 ? "foundation" : i < 20 ? "workflow" : "verification"],
      properties: {
        tier: i < 10 ? "foundation" : i < 20 ? "workflow" : "verification",
        retention: i % 2 === 0 ? "ephemeral" : "durable"
      },
      scwContract: {
        scwId,
        purpose:
          i === 0
            ? "Orchestration scratchpad and deterministic tick log"
            : i < 10
              ? "Core workflow context window"
              : i < 20
                ? "Domain workflow window"
                : "Verification and audit window",
        runHeaderRequired: true,
        tickLoggingRequired: true,
        determinismPolicy: i < 20 ? "strict" : "strict+hash-chain",
        verificationBlockRequired: i >= 20
      }
    });
  }

  return { agents, scws };
}

function exportPayload(nodes: Maxey0Node[], edges: Maxey0Edge[], ui: { panX: number; panY: number; zoom: number }): ExportPayload {
  return {
    version: "1.0.0",
    exportedAtIso: new Date().toISOString(),
    nodes: deepCopy(nodes),
    edges: deepCopy(edges),
    ui: deepCopy(ui)
  };
}

function tryLoadSaved(): ExportPayload | null {
  try {
    const raw = localStorage.getItem(MAXEY0_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as ExportPayload;
    if (!parsed || parsed.version !== "1.0.0") return null;
    if (!Array.isArray(parsed.nodes) || !Array.isArray(parsed.edges) || !parsed.ui) return null;
    return parsed;
  } catch {
    return null;
  }
}

function saveNow(payload: ExportPayload): void {
  localStorage.setItem(MAXEY0_STORAGE_KEY, JSON.stringify(payload));
}

function toCanvasPoint(
  clientX: number,
  clientY: number,
  rect: DOMRect,
  ui: { panX: number; panY: number; zoom: number }
): { x: number; y: number } {
  // screen -> canvas coordinates
  const sx = clientX - rect.left;
  const sy = clientY - rect.top;
  const x = (sx - ui.panX) / ui.zoom;
  const y = (sy - ui.panY) / ui.zoom;
  return { x, y };
}

function edgePath(src: { x: number; y: number }, dst: { x: number; y: number }): string {
  // simple cubic bezier
  const dx = Math.max(80, Math.abs(dst.x - src.x) * 0.5);
  const c1 = { x: src.x + dx, y: src.y };
  const c2 = { x: dst.x - dx, y: dst.y };
  return `M ${src.x} ${src.y} C ${c1.x} ${c1.y} ${c2.x} ${c2.y} ${dst.x} ${dst.y}`;
}

function center(n: Maxey0Node): { x: number; y: number } {
  return { x: n.x + n.w / 2, y: n.y + n.h / 2 };
}

function nearestHandlePoint(n: Maxey0Node, toward: { x: number; y: number }): { x: number; y: number } {
  // pick left or right handle based on direction
  const c = center(n);
  const left = { x: n.x, y: c.y };
  const right = { x: n.x + n.w, y: c.y };
  const dL = (toward.x - left.x) ** 2 + (toward.y - left.y) ** 2;
  const dR = (toward.x - right.x) ** 2 + (toward.y - right.y) ** 2;
  return dL < dR ? left : right;
}

function classNames(...xs: Array<string | false | null | undefined>): string {
  return xs.filter(Boolean).join(" ");
}

export default function App() {
  // Attachment note: Some files you uploaded earlier in this chat expired, so this !app is self-contained.
  const catalog = useMemo(() => makeDefaultCatalog(), []);

  const [ui, setUi] = useState({ panX: 0, panY: 0, zoom: 1 });
  const [nodes, setNodes] = useState<Maxey0Node[]>(() => {
    const saved = tryLoadSaved();
    if (saved) return saved.nodes;
    // seed with a small starter graph
    const a1 = deepCopy(catalog.agents[0]!);
    const s0 = deepCopy(catalog.scws[0]!);
    const a4 = deepCopy(catalog.agents[3]!);
    const s20 = deepCopy(catalog.scws[20]!);

    return [
      { ...a1, id: "agent_1", x: 120, y: 140 },
      { ...s0, id: "scw_0", x: 440, y: 140 },
      { ...a4, id: "agent_4", x: 120, y: 320 },
      { ...s20, id: "scw_20", x: 440, y: 320 }
    ];
  });

  const [edges, setEdges] = useState<Maxey0Edge[]>(() => {
    const saved = tryLoadSaved();
    if (saved) return saved.edges;
    return [
      { id: "edge_1", sourceId: "agent_1", targetId: "scw_0", kind: "writes_to", label: "writes_to", properties: { channel: "sp" } },
      { id: "edge_2", sourceId: "agent_4", targetId: "scw_20", kind: "logs_to", label: "logs_to", properties: { required: true } }
    ];
  });

  useEffect(() => {
    const saved = tryLoadSaved();
    if (saved) setUi(saved.ui);
  }, []);

  const [tab, setTab] = useState<"agents" | "scws">("agents");
  const [q, setQ] = useState("");

  const [selected, setSelected] = useState<{ kind: "node"; id: string } | { kind: "edge"; id: string } | null>(null);

  const canvasRef = useRef<HTMLDivElement | null>(null);

  const selectedNode = useMemo(() => {
    if (!selected || selected.kind !== "node") return null;
    return nodes.find((n) => n.id === selected.id) ?? null;
  }, [selected, nodes]);

  const selectedEdge = useMemo(() => {
    if (!selected || selected.kind !== "edge") return null;
    return edges.find((e) => e.id === selected.id) ?? null;
  }, [selected, edges]);

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

  const filteredCatalog = useMemo(() => {
    const list = tab === "agents" ? catalog.agents : catalog.scws;
    const query = q.trim().toLowerCase();
    if (!query) return list;
    return list.filter((t) => {
      const s = `${t.label} ${t.kind} ${(t.tags || []).join(" ")}`.toLowerCase();
      return s.includes(query);
    });
  }, [catalog.agents, catalog.scws, tab, q]);

  function clearSelection() {
    setSelected(null);
  }

  function setZoom(nextZoom: number, anchorClientX?: number, anchorClientY?: number) {
    const z = clamp(nextZoom, 0.35, 2.5);
    if (!canvasRef.current) {
      setUi((u) => ({ ...u, zoom: z }));
      return;
    }
    if (anchorClientX == null || anchorClientY == null) {
      setUi((u) => ({ ...u, zoom: z }));
      return;
    }
    const rect = canvasRef.current.getBoundingClientRect();
    const before = toCanvasPoint(anchorClientX, anchorClientY, rect, ui);
    const nextUi = { ...ui, zoom: z };
    const after = toCanvasPoint(anchorClientX, anchorClientY, rect, nextUi);
    // adjust pan so anchor point stays under cursor
    const dx = (after.x - before.x) * z;
    const dy = (after.y - before.y) * z;
    setUi((u) => ({ ...u, zoom: z, panX: u.panX + dx, panY: u.panY + dy }));
  }

  function saveLocal() {
    const payload = exportPayload(nodes, edges, ui);
    saveNow(payload);
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
  }

  function clearAll() {
    setNodes([]);
    setEdges([]);
    setSelected(null);
    setUi({ panX: 0, panY: 0, zoom: 1 });
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
      if (!parsed || parsed.version !== "1.0.0") throw new Error("Invalid version");
      if (!Array.isArray(parsed.nodes) || !Array.isArray(parsed.edges) || !parsed.ui) throw new Error("Invalid schema");
      setNodes(parsed.nodes);
      setEdges(parsed.edges);
      setUi(parsed.ui);
      setSelected(null);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Unknown error";
      alert(`Import failed: ${msg}`);
    }
  }

  function addNodeFromTemplate(tpl: Maxey0Node, at: { x: number; y: number }) {
    const id = uid(tpl.kind);
    const n: Maxey0Node = {
      ...deepCopy(tpl),
      id,
      x: at.x,
      y: at.y
    };
    setNodes((xs) => [...xs, n]);
    setSelected({ kind: "node", id });
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

  function onCanvasMouseDown(ev: React.MouseEvent) {
    // Pan with middle mouse or space+left
    if (ev.button === 1 || (ev.button === 0 && ev.getModifierState(" "))) {
      ev.preventDefault();
      panState.current = { startClientX: ev.clientX, startClientY: ev.clientY, startPanX: ui.panX, startPanY: ui.panY };
      return;
    }

    // Clicking empty space clears selection
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
      // force redraw by ticking state cheaply
      setUi((u) => ({ ...u }));
    }

    const ds = dragState.current;
    if (ds && canvasRef.current) {
      const rect = canvasRef.current.getBoundingClientRect();
      const p0 = toCanvasPoint(ds.startClientX, ds.startClientY, rect, ui);
      const p1 = toCanvasPoint(ev.clientX, ev.clientY, rect, ui);
      const dx = p1.x - p0.x;
      const dy = p1.y - p0.y;
      updateNode(ds.nodeId, { x: ds.startX + dx, y: ds.startY + dy });
    }
  }

  function onCanvasMouseUp() {
    panState.current = null;
    dragState.current = null;
    if (linkState.current) {
      // if user released on empty canvas, cancel
      linkState.current = null;
      setUi((u) => ({ ...u }));
    }
  }

  function onWheel(ev: React.WheelEvent) {
    if (!canvasRef.current) return;
    if (ev.ctrlKey) {
      // zoom
      ev.preventDefault();
      const factor = ev.deltaY < 0 ? 1.08 : 0.92;
      setZoom(ui.zoom * factor, ev.clientX, ev.clientY);
      return;
    }
    // trackpad pan
    setUi((u) => ({ ...u, panX: u.panX - ev.deltaX, panY: u.panY - ev.deltaY }));
  }

  function onDrop(ev: React.DragEvent) {
    ev.preventDefault();
    const tplId = ev.dataTransfer.getData("application/maxey0-template-id");
    if (!tplId) return;
    const tpl = [...catalog.agents, ...catalog.scws].find((t) => t.id === tplId);
    if (!tpl || !canvasRef.current) return;

    const rect = canvasRef.current.getBoundingClientRect();
    const p = toCanvasPoint(ev.clientX, ev.clientY, rect, ui);
    addNodeFromTemplate(tpl, { x: p.x - tpl.w / 2, y: p.y - tpl.h / 2 });
  }

  function onDragOver(ev: React.DragEvent) {
    ev.preventDefault();
    ev.dataTransfer.dropEffect = "move";
  }

  const importBoxRef = useRef<HTMLTextAreaElement | null>(null);

  // Edge render helpers
  const nodeById = useMemo(() => {
    const m = new Map<string, Maxey0Node>();
    for (const n of nodes) m.set(n.id, n);
    return m;
  }, [nodes]);

  const edgeSegments = useMemo(() => {
    const segments: Array<{
      edge: Maxey0Edge;
      d: string;
      labelX: number;
      labelY: number;
      srcPt: { x: number; y: number };
      dstPt: { x: number; y: number };
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
      segments.push({ edge: e, d, labelX, labelY, srcPt: src, dstPt: dst });
    }

    return segments;
  }, [edges, nodeById]);

  const linkPreview = useMemo(() => {
    const st = linkState.current;
    if (!st) return null;
    const s = nodeById.get(st.sourceId);
    if (!s) return null;
    const sc = center(s);
    const src = nearestHandlePoint(s, { x: st.toX, y: st.toY });
    const dst = { x: st.toX, y: st.toY };
    return { d: edgePath(src, dst), label: st.label, labelX: (src.x + dst.x) / 2, labelY: (src.y + dst.y) / 2 };
  }, [ui, nodeById]);

  // Layout (tailwind)
  return (
    <div className="h-screen w-screen bg-zinc-950 text-zinc-100">
      {/* Topbar */}
      <div className="flex items-center justify-between gap-3 border-b border-zinc-800 bg-zinc-950 p-3">
        <div className="flex items-baseline gap-3">
          <div className="text-sm font-semibold">maxey0-scw-designer (!app)</div>
          <div className="text-xs text-zinc-500">drag • connect • inspect • export • local-first</div>
        </div>

        <div className="flex items-center gap-2">
          <button
            className="rounded-xl border border-zinc-800 bg-zinc-100 px-3 py-2 text-sm font-medium text-zinc-900 hover:bg-white"
            onClick={saveLocal}
          >
            Save
          </button>
          <button
            className="rounded-xl border border-zinc-800 bg-transparent px-3 py-2 text-sm font-medium text-zinc-200 hover:bg-zinc-900"
            onClick={loadLocal}
          >
            Load
          </button>
          <button
            className="rounded-xl border border-zinc-800 bg-transparent px-3 py-2 text-sm font-medium text-zinc-200 hover:bg-zinc-900"
            onClick={exportJsonToClipboard}
          >
            Copy Export
          </button>
          <button
            className="rounded-xl border border-red-900/60 bg-red-500/10 px-3 py-2 text-sm font-medium text-red-200 hover:bg-red-500/20"
            onClick={clearAll}
          >
            Clear
          </button>
        </div>
      </div>

      {/* Main */}
      <div className="flex h-[calc(100vh-56px)] min-h-0">
        {/* Sidebar */}
        <div className="w-[340px] shrink-0 border-r border-zinc-800 bg-zinc-950">
          <div className="p-3">
            <div className="flex items-center gap-2 rounded-2xl border border-zinc-800 bg-zinc-950 p-1">
              <button
                className={classNames(
                  "flex-1 rounded-2xl px-3 py-2 text-sm transition",
                  tab === "agents" ? "bg-zinc-100 text-zinc-900" : "text-zinc-200 hover:bg-zinc-900"
                )}
                onClick={() => setTab("agents")}
              >
                Agents (32)
              </button>
              <button
                className={classNames(
                  "flex-1 rounded-2xl px-3 py-2 text-sm transition",
                  tab === "scws" ? "bg-zinc-100 text-zinc-900" : "text-zinc-200 hover:bg-zinc-900"
                )}
                onClick={() => setTab("scws")}
              >
                SCWs (30)
              </button>
            </div>
          </div>

          <div className="px-3 pb-3">
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search templates..."
              className="w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600 outline-none focus:border-zinc-600"
            />
          </div>

          <div className="h-[calc(100%-140px)] overflow-auto p-3">
            <div className="grid grid-cols-1 gap-2">
              {filteredCatalog.map((t) => (
                <div
                  key={t.id}
                  draggable
                  onDragStart={(ev) => {
                    ev.dataTransfer.setData("application/maxey0-template-id", t.id);
                    ev.dataTransfer.effectAllowed = "move";
                  }}
                  className="cursor-grab rounded-2xl border border-zinc-800 bg-zinc-900/30 p-3 active:cursor-grabbing"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="h-3 w-3 rounded-full" style={{ backgroundColor: t.colorHex }} />
                      <div className="text-sm font-semibold">{t.label}</div>
                    </div>
                    <span className="inline-flex items-center rounded-full border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-[10px] text-zinc-200">
                      {t.kind.toUpperCase()}
                    </span>
                  </div>
                  <div className="mt-2 text-xs text-zinc-400">
                    {t.kind === "agent" ? t.agentContract?.role ?? "Agent" : t.scwContract?.purpose ?? "Structured Context Window"}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {(t.tags || []).slice(0, 6).map((x) => (
                      <span
                        key={x}
                        className="inline-flex items-center rounded-full border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-[10px] text-zinc-200"
                      >
                        {x}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-6 rounded-2xl border border-zinc-800 bg-zinc-900/20 p-3 text-xs text-zinc-400">
              <div className="font-semibold text-zinc-200">Canvas controls</div>
              <ul className="mt-2 list-disc space-y-1 pl-4">
                <li>Drag template → canvas to add.</li>
                <li>Drag node to reposition.</li>
                <li>Start edge: click node's right handle.</li>
                <li>Finish edge: click target node.</li>
                <li>Pan: middle mouse (or hold Space + drag).</li>
                <li>Zoom: Ctrl + mousewheel.</li>
              </ul>
              <div className="mt-3">
                <span className="text-zinc-300">Min requirements satisfied:</span> 32 colors, 32 agents, 30 SCWs, no Maxey00.
              </div>
            </div>
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
            {/* Grid */}
            <div
              className="absolute inset-0"
              style={{
                backgroundImage:
                  "linear-gradient(to right, rgba(39,39,42,0.35) 1px, transparent 1px), linear-gradient(to bottom, rgba(39,39,42,0.35) 1px, transparent 1px)",
                backgroundSize: `${20 * ui.zoom}px ${20 * ui.zoom}px`,
                backgroundPosition: `${ui.panX}px ${ui.panY}px`
              }}
            />

            {/* Edges SVG */}
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

              {edgeSegments.map((seg) => (
                <g key={seg.edge.id}>
                  <path
                    d={seg.d}
                    fill="none"
                    stroke={selectedEdge?.id === seg.edge.id ? "#E4E4E7" : "#A1A1AA"}
                    strokeWidth={selectedEdge?.id === seg.edge.id ? 2.2 : 1.6}
                    markerEnd="url(#arrow)"
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
                    <rect x={-40} y={-12} width={80} height={24} rx={12} ry={12} fill="#09090b" stroke="#27272a" />
                    <text x={0} y={4} textAnchor="middle" fontSize={10} fill="#E4E4E7">
                      {seg.edge.label}
                    </text>
                  </g>
                </g>
              ))}

              {linkPreview && (
                <g>
                  <path d={linkPreview.d} fill="none" stroke="#E4E4E7" strokeWidth={1.6} markerEnd="url(#arrow)" strokeDasharray="6 4" />
                  <g transform={`translate(${linkPreview.labelX}, ${linkPreview.labelY})`}>
                    <rect x={-40} y={-12} width={80} height={24} rx={12} ry={12} fill="#09090b" stroke="#3f3f46" />
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
              {nodes.map((n) => {
                const isSelected = selected?.kind === "node" && selected.id === n.id;
                const border = isSelected ? "border-zinc-200" : "border-zinc-800";

                return (
                  <div
                    key={n.id}
                    className={classNames(
                      "absolute rounded-2xl border bg-zinc-950/90 shadow-xl",
                      border
                    )}
                    style={{
                      left: n.x,
                      top: n.y,
                      width: n.w,
                      height: n.h,
                      boxShadow: `0 0 0 1px ${n.colorHex}22, 0 12px 30px #00000066`
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
                        <span className={n.kind === "agent" ? "mt-1 h-3 w-3 rounded-full" : "mt-1 h-3 w-3 rounded"} style={{ backgroundColor: n.colorHex }} />
                        <div className="leading-tight">
                          <div className="text-sm font-semibold text-zinc-100">{n.label}</div>
                          <div className="text-xs text-zinc-400">
                            {n.kind === "agent" ? n.agentContract?.role ?? "Agent" : n.scwContract?.purpose ?? "Structured Context Window"}
                          </div>
                        </div>
                      </div>

                      <div className="flex flex-col items-end gap-2">
                        <span className="inline-flex items-center rounded-full border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-[10px] text-zinc-200">
                          {n.kind.toUpperCase()}
                        </span>
                        {n.kind === "agent" && (
                          <span className="text-[10px] text-zinc-500">{(n.agentContract?.memoryScope ?? "sp").toUpperCase()}</span>
                        )}
                      </div>
                    </div>

                    <div className="px-3 pb-3">
                      <div className="flex flex-wrap gap-1">
                        {(n.tags || []).slice(0, 5).map((t) => (
                          <span
                            key={t}
                            className="inline-flex items-center rounded-full border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-[10px] text-zinc-300"
                          >
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
                      onMouseDown={(ev) => {
                        // stop drag-start
                        ev.stopPropagation();
                      }}
                      onClick={(ev) => {
                        ev.stopPropagation();
                        // if linking, allow finishing on node click
                        const st = linkState.current;
                        if (st) endEdgeCreate(n.id);
                        else setSelected({ kind: "node", id: n.id });
                      }}
                    />

                    <div
                      className="absolute right-[-6px] top-1/2 h-3 w-3 -translate-y-1/2 rounded-full border-2 border-zinc-950"
                      style={{ backgroundColor: n.colorHex }}
                      title="Source handle (click to start edge)"
                      onMouseDown={(ev) => {
                        ev.stopPropagation();
                      }}
                      onClick={(ev) => {
                        ev.stopPropagation();
                        beginEdgeCreate(n.id, "depends_on");
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
              </div>
              <div className="mt-2 text-[10px] text-zinc-500">Tip: Ctrl+wheel zoom • middle mouse pan • space+drag pan</div>
            </div>
          </div>
        </div>

        {/* Inspector */}
        <div className="w-[380px] shrink-0 border-l border-zinc-800 bg-zinc-950">
          <div className="p-3">
            <div className="text-sm font-semibold">Inspector</div>
            <div className="mt-1 text-xs text-zinc-500">Select a node or edge to edit. Changes are local until Save.</div>
          </div>

          <div className="h-[calc(100%-76px)] overflow-auto p-3 pt-0">
            {!selected && (
              <div className="rounded-2xl border border-zinc-800 bg-zinc-900/20 p-3 text-sm text-zinc-300">
                <div className="font-semibold text-zinc-200">Nothing selected</div>
                <div className="mt-2 text-xs text-zinc-400">Click a node or edge on the canvas.</div>

                <div className="mt-4 text-xs text-zinc-400">
                  <div className="font-semibold text-zinc-200">Import JSON</div>
                  <textarea
                    ref={importBoxRef}
                    className="mt-2 h-28 w-full rounded-2xl border border-zinc-800 bg-zinc-950 p-3 text-xs text-zinc-200 outline-none focus:border-zinc-600"
                    placeholder="Paste exported JSON here"
                  />
                  <button
                    className="mt-2 w-full rounded-xl border border-zinc-800 bg-zinc-100 px-3 py-2 text-sm font-medium text-zinc-900 hover:bg-white"
                    onClick={() => {
                      const txt = importBoxRef.current?.value ?? "";
                      importJsonFromText(txt);
                    }}
                  >
                    Import
                  </button>
                </div>
              </div>
            )}

            {selectedNode && (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="text-sm font-semibold">Node</div>
                  <button
                    className="rounded-xl border border-red-900/60 bg-red-500/10 px-3 py-2 text-sm font-medium text-red-200 hover:bg-red-500/20"
                    onClick={() => deleteNode(selectedNode.id)}
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

                  <div className="mt-3 text-xs text-zinc-500">Color (32-color palette)</div>
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

                  {selectedNode.kind === "agent" && selectedNode.agentContract && (
                    <div className="mt-4 rounded-2xl border border-zinc-800 bg-zinc-950 p-3">
                      <div className="text-sm font-semibold text-zinc-100">Agent Contract</div>
                      <div className="mt-2 text-xs text-zinc-500">Role</div>
                      <input
                        className="mt-1 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-600"
                        value={selectedNode.agentContract.role}
                        onChange={(e) =>
                          updateNode(selectedNode.id, {
                            agentContract: { ...selectedNode.agentContract!, role: e.target.value }
                          })
                        }
                      />

                      <div className="mt-3 text-xs text-zinc-500">Tools (comma-separated)</div>
                      <input
                        className="mt-1 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-600"
                        value={selectedNode.agentContract.tools.join(",")}
                        onChange={(e) =>
                          updateNode(selectedNode.id, {
                            agentContract: {
                              ...selectedNode.agentContract!,
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
                        value={selectedNode.agentContract.memoryScope}
                        onChange={(e) =>
                          updateNode(selectedNode.id, {
                            agentContract: { ...selectedNode.agentContract!, memoryScope: e.target.value as any }
                          })
                        }
                      >
                        <option value="sp">sp</option>
                        <option value="ep">ep</option>
                        <option value="pr">pr</option>
                        <option value="pm">pm</option>
                      </select>

                      <div className="mt-3 text-xs text-zinc-500">Notes</div>
                      <textarea
                        className="mt-1 h-20 w-full rounded-2xl border border-zinc-800 bg-zinc-950 p-3 text-sm text-zinc-100 outline-none focus:border-zinc-600"
                        value={selectedNode.agentContract.notes}
                        onChange={(e) =>
                          updateNode(selectedNode.id, {
                            agentContract: { ...selectedNode.agentContract!, notes: e.target.value }
                          })
                        }
                      />
                    </div>
                  )}

                  {selectedNode.kind === "scw" && selectedNode.scwContract && (
                    <div className="mt-4 rounded-2xl border border-zinc-800 bg-zinc-950 p-3">
                      <div className="text-sm font-semibold text-zinc-100">SCW Contract</div>
                      <div className="mt-2 text-xs text-zinc-500">Purpose</div>
                      <input
                        className="mt-1 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-600"
                        value={selectedNode.scwContract.purpose}
                        onChange={(e) =>
                          updateNode(selectedNode.id, {
                            scwContract: { ...selectedNode.scwContract!, purpose: e.target.value }
                          })
                        }
                      />

                      <div className="mt-3 text-xs text-zinc-500">Determinism policy</div>
                      <input
                        className="mt-1 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-600"
                        value={selectedNode.scwContract.determinismPolicy}
                        onChange={(e) =>
                          updateNode(selectedNode.id, {
                            scwContract: { ...selectedNode.scwContract!, determinismPolicy: e.target.value }
                          })
                        }
                      />

                      <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                        <label className="flex items-center gap-2 rounded-2xl border border-zinc-800 bg-zinc-900/20 p-2">
                          <input
                            type="checkbox"
                            checked={selectedNode.scwContract.runHeaderRequired}
                            onChange={(e) =>
                              updateNode(selectedNode.id, {
                                scwContract: { ...selectedNode.scwContract!, runHeaderRequired: e.target.checked }
                              })
                            }
                          />
                          <span className="text-zinc-300">Run header</span>
                        </label>
                        <label className="flex items-center gap-2 rounded-2xl border border-zinc-800 bg-zinc-900/20 p-2">
                          <input
                            type="checkbox"
                            checked={selectedNode.scwContract.tickLoggingRequired}
                            onChange={(e) =>
                              updateNode(selectedNode.id, {
                                scwContract: { ...selectedNode.scwContract!, tickLoggingRequired: e.target.checked }
                              })
                            }
                          />
                          <span className="text-zinc-300">Tick logging</span>
                        </label>
                        <label className="flex items-center gap-2 rounded-2xl border border-zinc-800 bg-zinc-900/20 p-2">
                          <input
                            type="checkbox"
                            checked={selectedNode.scwContract.verificationBlockRequired}
                            onChange={(e) =>
                              updateNode(selectedNode.id, {
                                scwContract: { ...selectedNode.scwContract!, verificationBlockRequired: e.target.checked }
                              })
                            }
                          />
                          <span className="text-zinc-300">Verification</span>
                        </label>
                        <div className="rounded-2xl border border-zinc-800 bg-zinc-900/20 p-2">
                          <div className="text-[10px] uppercase text-zinc-500">SCW ID</div>
                          <div className="text-zinc-200">{selectedNode.scwContract.scwId}</div>
                        </div>
                      </div>
                    </div>
                  )}

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
                </div>

                <div className="rounded-2xl border border-zinc-800 bg-zinc-900/20 p-3 text-xs text-zinc-400">
                  <div className="font-semibold text-zinc-200">Edge creation</div>
                  <div className="mt-1">Click the node’s right handle to start an edge, then click the target node to finish.</div>
                </div>

                <div className="rounded-2xl border border-zinc-800 bg-zinc-900/20 p-3 text-xs text-zinc-400">
                  <div className="font-semibold text-zinc-200">Import JSON</div>
                  <textarea
                    ref={importBoxRef}
                    className="mt-2 h-28 w-full rounded-2xl border border-zinc-800 bg-zinc-950 p-3 text-xs text-zinc-200 outline-none focus:border-zinc-600"
                    placeholder="Paste exported JSON here"
                  />
                  <button
                    className="mt-2 w-full rounded-xl border border-zinc-800 bg-zinc-100 px-3 py-2 text-sm font-medium text-zinc-900 hover:bg-white"
                    onClick={() => {
                      const txt = importBoxRef.current?.value ?? "";
                      importJsonFromText(txt);
                    }}
                  >
                    Import
                  </button>
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
                  <div className="font-semibold text-zinc-200">Import JSON</div>
                  <textarea
                    ref={importBoxRef}
                    className="mt-2 h-28 w-full rounded-2xl border border-zinc-800 bg-zinc-950 p-3 text-xs text-zinc-200 outline-none focus:border-zinc-600"
                    placeholder="Paste exported JSON here"
                  />
                  <button
                    className="mt-2 w-full rounded-xl border border-zinc-800 bg-zinc-100 px-3 py-2 text-sm font-medium text-zinc-900 hover:bg-white"
                    onClick={() => {
                      const txt = importBoxRef.current?.value ?? "";
                      importJsonFromText(txt);
                    }}
                  >
                    Import
                  </button>
                </div>
              </div>
            )}
          </div>

          <div className="border-t border-zinc-800 p-3 text-xs text-zinc-500">
            <div className="flex items-center justify-between">
              <div>Local-only state (Save/Load via localStorage)</div>
              <div className="flex items-center gap-2">
                <button
                  className="rounded-xl border border-zinc-800 bg-transparent px-3 py-2 text-xs font-medium text-zinc-200 hover:bg-zinc-900"
                  onClick={() => setUi({ panX: 0, panY: 0, zoom: 1 })}
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

      {/* Import Modal trigger removed intentionally (inspector includes import boxes). */}
    </div>
  );
}
