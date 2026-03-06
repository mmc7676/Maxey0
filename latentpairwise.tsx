import React, { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";

/**
 * MaxeyLatentLab.tsx
 * One-file Claude Artifact app for latent pairwise experiments + 3D triangulation.
 * - No external dep on three/examples; includes a minimal OrbitControls.
 * - Implements A2A beacons, pairwise distances, triangulation, paths, mini-map.
 * - Latent lab: User0 input → deterministic vector; snapshot pre/post; Δ; attribution; PCA; export.
 * - All computations client-side. No placeholders.
 */

// ---------- Constants ----------
const GRAVITY_M_S2 = 9.80665;
const MAP_BOUNDS: [[number, number, number], [number, number, number]] = [
  [0, 0, 0],
  [1000, 1000, 200],
];
const BEACON_HZ = 2.0;
const COMM_RANGE = 500;
const MAX_PATH_POINTS = 600;
const DEFAULT_LATENT_DIM = 128; // used for seeded vectors if none provided

// ---------- Minimal OrbitControls (no three/examples) ----------
class OrbitControls {
  private camera: THREE.PerspectiveCamera;
  private dom: HTMLElement;
  public enabled = true;
  public enableDamping = true;
  public dampingFactor = 0.1;

  private spherical = new THREE.Spherical();
  private sphericalDelta = new THREE.Spherical();
  private scale = 1;
  private rotateStart = new THREE.Vector2();
  private rotateEnd = new THREE.Vector2();
  private rotateDelta = new THREE.Vector2();
  private state = { NONE: -1, ROTATE: 0, DOLLY: 1 };
  private currentState = this.state.NONE;
  private target = new THREE.Vector3();

  constructor(camera: THREE.PerspectiveCamera, dom: HTMLElement) {
    this.camera = camera;
    this.dom = dom;
    this.bind();
    this.update();
  }

  private bind() {
    const onMouseDown = (e: MouseEvent) => {
      if (!this.enabled) return;
      if (e.button === 0) {
        this.currentState = this.state.ROTATE;
        this.rotateStart.set(e.clientX, e.clientY);
      }
    };
    const onMouseMove = (e: MouseEvent) => {
      if (!this.enabled) return;
      if (this.currentState === this.state.ROTATE) {
        this.rotateEnd.set(e.clientX, e.clientY);
        this.rotateDelta.subVectors(this.rotateEnd, this.rotateStart).multiplyScalar(0.01);
        this.sphericalDelta.theta -= this.rotateDelta.x;
        this.sphericalDelta.phi -= this.rotateDelta.y;
        this.rotateStart.copy(this.rotateEnd);
      }
    };
    const onMouseUp = () => (this.currentState = this.state.NONE);
    const onWheel = (e: WheelEvent) => {
      if (!this.enabled) return;
      e.preventDefault();
      this.scale *= e.deltaY < 0 ? 0.95 : 1 / 0.95;
    };
    this.dom.addEventListener("mousedown", onMouseDown);
    this.dom.addEventListener("mousemove", onMouseMove);
    this.dom.addEventListener("mouseup", onMouseUp);
    this.dom.addEventListener("wheel", onWheel);
    // store to instance for disposal
    (this as any)._handlers = { onMouseDown, onMouseMove, onMouseUp, onWheel };
  }

  public update() {
    const pos = this.camera.position;
    const offset = new THREE.Vector3().copy(pos).sub(this.target);
    this.spherical.setFromVector3(offset);
    this.spherical.theta += this.sphericalDelta.theta;
    this.spherical.phi += this.sphericalDelta.phi;
    this.spherical.phi = Math.max(0.01, Math.min(Math.PI - 0.01, this.spherical.phi));
    this.spherical.radius *= this.scale;
    offset.setFromSpherical(this.spherical);
    pos.copy(this.target).add(offset);
    this.camera.lookAt(this.target);
    if (this.enableDamping) {
      this.sphericalDelta.theta *= 1 - this.dampingFactor;
      this.sphericalDelta.phi *= 1 - this.dampingFactor;
    } else {
      this.sphericalDelta.set(0, 0, 0);
    }
    this.scale = 1;
  }

  public dispose() {
    const h = (this as any)._handlers;
    if (!h) return;
    this.dom.removeEventListener("mousedown", h.onMouseDown);
    this.dom.removeEventListener("mousemove", h.onMouseMove);
    this.dom.removeEventListener("mouseup", h.onMouseUp);
    this.dom.removeEventListener("wheel", h.onWheel);
  }
}

// ---------- Math / Utils ----------
const clampBounds = (p: [number, number, number]) => {
  const [[xmin, ymin, zmin], [xmax, ymax, zmax]] = MAP_BOUNDS;
  return [
    Math.min(Math.max(p[0], xmin), xmax),
    Math.min(Math.max(p[1], ymin), ymax),
    Math.min(Math.max(p[2], zmin), zmax),
  ] as [number, number, number];
};

const distance3D = (a: [number, number, number], b: [number, number, number]) => {
  const dx = a[0] - b[0];
  const dy = a[1] - b[1];
  const dz = a[2] - b[2];
  return Math.sqrt(dx * dx + dy * dy + dz * dz);
};

const dot = (a: number[], b: number[]) => a.reduce((s, v, i) => s + v * b[i], 0);
const norm = (a: number[]) => Math.sqrt(dot(a, a));
const subVec = (a: number[], b: number[]) => a.map((v, i) => v - b[i]);
const addVec = (a: number[], b: number[]) => a.map((v, i) => v + b[i]);
const mulVec = (a: number[], s: number) => a.map((v) => v * s);
const cosineSim = (a: number[], b: number[]) => {
  const na = norm(a);
  const nb = norm(b);
  if (na === 0 || nb === 0) return 0;
  return dot(a, b) / (na * nb);
};

// Triangulation (3D) using orthonormal basis method; returns null if degenerate
const trilaterate3D = (
  p1: [number, number, number],
  p2: [number, number, number],
  p3: [number, number, number],
  r1: number,
  r2: number,
  r3: number
): [number, number, number] | null => {
  const subV = (a: number[], b: number[]) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
  const nrm = (a: number[]) => Math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2]);
  const mul = (a: number[], s: number) => [a[0] * s, a[1] * s, a[2] * s];
  const add = (a: number[], b: number[]) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
  const dot3 = (a: number[], b: number[]) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const cross = (a: number[], b: number[]) => [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  ];

  const ex0 = subV(p2, p1);
  const d = nrm(ex0);
  if (d < 1e-6) return null;
  const ex = mul(ex0, 1 / d);
  const p3p1 = subV(p3, p1);
  const i = dot3(ex, p3p1);
  const temp = subV(p3p1, mul(ex, i));
  const tempn = nrm(temp);
  if (tempn < 1e-6) return null;
  const ey = mul(temp, 1 / tempn);
  const ez = cross(ex, ey);
  const j = dot3(ey, p3p1);
  const x = (r1 * r1 - r2 * r2 + d * d) / (2 * d);
  const y = (r1 * r1 - r3 * r3 + i * i + j * j - 2 * i * x) / (2 * j);
  const z2 = r1 * r1 - x * x - y * y;
  if (z2 < -1e-3) return null;
  const z = Math.sqrt(Math.max(0, z2));
  const p = add(p1, add(mul(ex, x), add(mul(ey, y), mul(ez, z)))) as [number, number, number];
  return clampBounds(p);
};

// Deterministic PRNG from string (xorshift32 variant)
const hash32 = (s: string) => {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619) >>> 0;
  }
  return h >>> 0;
};
const rndStream = (seed: number) => {
  let x = seed || 123456789;
  return () => {
    x ^= x << 13;
    x ^= x >>> 17;
    x ^= x << 5;
    return (x >>> 0) / 4294967296;
  };
};

// PCA via power iteration (top k components), deflation on covariance
function pcaPower(X: number[][], k: number): { comps: number[][]; proj: number[][]; mean: number[] } {
  const n = X.length;
  if (n === 0) return { comps: [], proj: [], mean: [] };
  const d = X[0].length;
  // mean-center
  const mean = Array(d).fill(0);
  for (const row of X) for (let j = 0; j < d; j++) mean[j] += row[j];
  for (let j = 0; j < d; j++) mean[j] /= n;
  const C = X.map((row) => row.map((v, j) => v - mean[j])); // n x d

  // covariance implicit multiplication: v -> (C^T C / (n-1)) v
  const covMul = (v: number[]) => {
    const Ct_v: number[] = Array(d).fill(0);
    for (let i = 0; i < n; i++) {
      const s = dot(C[i], v);
      for (let j = 0; j < d; j++) Ct_v[j] += C[i][j] * s;
    }
    const scale = 1 / Math.max(1, n - 1);
    return Ct_v.map((x) => x * scale);
  };

  const comps: number[][] = [];
  const maxIter = 200;
  const tol = 1e-6;

  // power iteration with deflation
  for (let c = 0; c < Math.min(k, d); c++) {
    // start vector
    let v = Array(d)
      .fill(0)
      .map(() => Math.random() - 0.5);
    // orthogonalize against previous components
    const orth = (vv: number[]) => {
      let u = vv.slice();
      for (const pc of comps) {
        const coeff = dot(u, pc);
        for (let j = 0; j < d; j++) u[j] -= coeff * pc[j];
      }
      const nrm = norm(u);
      if (nrm === 0) return vv.slice();
      return u.map((x) => x / nrm);
    };
    v = orth(v);
    let eigen = 0;
    for (let it = 0; it < maxIter; it++) {
      // multiply with covariance
      let w = covMul(v);
      // deflate contributions of previous comps in multiply space
      for (const pc of comps) {
        const lam_pc = dot(pc, covMul(pc));
        const proj = dot(w, pc);
        for (let j = 0; j < d; j++) w[j] -= proj * pc[j]; // simple Gram-Schmidt in cov-space
        // avoid using lam_pc directly (stability)
      }
      const nrmw = norm(w);
      if (nrmw === 0) break;
      const vNext = w.map((x) => x / nrmw);
      const diff = Math.sqrt(vNext.reduce((s, x, j) => s + (x - v[j]) * (x - v[j]), 0));
      v = vNext;
      eigen = nrmw; // Rayleigh quotient approx not strictly computed, sufficient for direction
      if (diff < tol) break;
    }
    comps.push(v);
  }

  // project
  const proj = C.map((row) => comps.map((pc) => dot(row, pc)));
  return { comps, proj, mean };
}

// CSV/JSON parser for latent vectors: expects rows like "name, v1, v2, ..." or JSON {name:string, vector:number[]}
function parseLatentInput(text: string): Record<string, number[]> {
  const out: Record<string, number[]> = {};
  const t = text.trim();
  if (!t) return out;
  if (t.startsWith("{") || t.startsWith("[")) {
    // JSON array or object
    const obj = JSON.parse(t);
    if (Array.isArray(obj)) {
      for (const o of obj) {
        if (o && typeof o.name === "string" && Array.isArray(o.vector)) out[o.name] = o.vector.map(Number);
      }
    } else {
      for (const k of Object.keys(obj)) {
        const v = (obj as any)[k];
        if (Array.isArray(v)) out[k] = v.map(Number);
      }
    }
  } else {
    // CSV lines
    const lines = t.split(/\r?\n/).filter((l) => l.trim().length);
    for (const line of lines) {
      const parts = line.split(",").map((x) => x.trim());
      if (parts.length >= 2) {
        const name = parts[0];
        const vec = parts.slice(1).map(Number);
        if (name && vec.every((n) => Number.isFinite(n))) out[name] = vec;
      }
    }
  }
  return out;
}

// Attribution: correlate delta with marker basis
function attributionScores(delta: number[], markerBasis: Record<string, number[]>): Record<string, number> {
  const scores: Record<string, number> = {};
  for (const [k, basis] of Object.entries(markerBasis)) scores[k] = cosineSim(delta, basis);
  return scores;
}

// ---------- Data Models ----------
type DroneId = 1 | 2 | 3;
type AgentDrone = {
  id: DroneId;
  name: string;
  specialization: string;
  color: number;
  pos: [number, number, number];
  vel: [number, number, number];
  path: [number, number, number][];
};

type RealTimeData = {
  positions: Record<number, [number, number, number]>;
  distances: Record<number, Record<number, number>>;
};

// ---------- Main Component ----------
const MaxeyLatentLab: React.FC = () => {
  // Tabs
  const [tab, setTab] = useState<"network" | "latent" | "markers" | "experiments">("network");

  // ----- User0 & Latent state -----
  const [userInput, setUserInput] = useState<string>("");
  const [latentDim, setLatentDim] = useState<number>(DEFAULT_LATENT_DIM);

  // Preloaded Maxey1–3 base vectors (deterministic small values)
  const baseVectors = useMemo<Record<string, number[]>>(() => {
    const mk = (seed: string) => {
      const r = rndStream(hash32(seed) || 1);
      return Array(latentDim).fill(0).map(() => r() * 2 - 1);
    };
    return {
      Maxey1: mk("Maxey1_superposition"),
      Maxey2: mk("Maxey2_gnn_router"),
      Maxey3: mk("Maxey3_a2a_streams"),
    };
  }, [latentDim]);

  // External pasted vectors
  const [externalText, setExternalText] = useState<string>("");
  const [externalVectors, setExternalVectors] = useState<Record<string, number[]>>({});
  const applyExternalVectors = () => {
    try {
      const parsed = parseLatentInput(externalText);
      // normalize dims
      const anyVec = Object.values(parsed)[0];
      if (anyVec && anyVec.length !== latentDim) setLatentDim(anyVec.length);
      setExternalVectors(parsed);
      alert("Vectors loaded.");
    } catch (e: any) {
      alert("Parse error: " + e?.message);
    }
  };

  // Deterministic User0 vector from input
  const user0Vector = useMemo<number[]>(() => {
    const seed = hash32(userInput || "User0");
    const r = rndStream(seed || 1);
    return Array(latentDim).fill(0).map(() => r() * 2 - 1);
  }, [userInput, latentDim]);

  // Marker basis (8 types), deterministic orthogonal-ish randoms; weights are adjustable
  const markerKeys = ["safety", "creativity", "logic", "memory", "attention", "reasoning", "emotion", "context"] as const;
  type MarkerKey = typeof markerKeys[number];
  const markerBasis = useMemo<Record<MarkerKey, number[]>>(() => {
    const out: any = {};
    markerKeys.forEach((k, idx) => {
      const r = rndStream(hash32("marker_" + k) + idx);
      out[k] = Array(latentDim).fill(0).map(() => r() * 2 - 1);
    });
    return out;
  }, [latentDim]);

  const [markerWeights, setMarkerWeights] = useState<Record<MarkerKey, number>>({
    safety: 0,
    creativity: 0,
    logic: 0,
    memory: 0,
    attention: 0,
    reasoning: 0,
    emotion: 0,
    context: 0,
  });

  // Latent catalog
  const latentCatalog = useMemo<Record<string, number[]>>(() => {
    return { ...baseVectors, ...externalVectors, User0: user0Vector };
  }, [baseVectors, externalVectors, user0Vector]);

  // Pairwise distances
  const names = useMemo(() => Object.keys(latentCatalog), [latentCatalog]);
  const [metric, setMetric] = useState<"l2" | "cosine">("l2");
  const distanceMatrix = useMemo(() => {
    const m: number[][] = [];
    for (let i = 0; i < names.length; i++) {
      m[i] = [];
      for (let j = 0; j < names.length; j++) {
        const a = latentCatalog[names[i]];
        const b = latentCatalog[names[j]];
        if (metric === "l2") {
          const d2 = subVec(a, b).reduce((s, v) => s + v * v, 0);
          m[i][j] = Math.sqrt(d2);
        } else {
          m[i][j] = 1 - cosineSim(a, b);
        }
      }
    }
    return m;
  }, [latentCatalog, names, metric]);

  // PCA projection to 3D & 2D
  const pca = useMemo(() => {
    const X = names.map((n) => latentCatalog[n]);
    return pcaPower(X, 3);
  }, [latentCatalog, names]);
  const proj3 = pca.proj; // N x 3
  const meanVec = pca.mean;

  // ----- Snapshots & Experiments -----
  type Snapshot = { timestamp: number; vectors: Record<string, number[]>; label: string };
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const takeSnapshot = (label: string) => {
    const snap: Snapshot = {
      timestamp: Date.now(),
      label,
      vectors: Object.fromEntries(Object.entries(latentCatalog).map(([k, v]) => [k, v.slice()])),
    };
    setSnapshots((s) => [...s, snap]);
    return snap;
  };

  // Apply markers to User0 (and optionally Maxey1 superposition), returns new vectors
  const applyMarkers = (): Record<string, number[]> => {
    const weighted = Object.entries(markerWeights).reduce((acc, [k, w]) => {
      const b = markerBasis[k as MarkerKey];
      return addVec(acc, mulVec(b, w));
    }, Array(latentDim).fill(0));
    const newUser0 = addVec(latentCatalog["User0"], weighted);
    const newMaxey1 = addVec(latentCatalog["Maxey1"], mulVec(weighted, 0.25)); // small superposition ripple
    const updated: Record<string, number[]> = { ...latentCatalog, User0: newUser0, Maxey1: newMaxey1 };
    return updated;
  };

  type ExperimentResult = {
    id: string;
    pre: Snapshot;
    post: Snapshot;
    deltas: Record<string, number[]>;
    attribution: Record<string, Record<string, number>>;
    notes: string;
  };
  const [history, setHistory] = useState<ExperimentResult[]>([]);
  const [expNotes, setExpNotes] = useState("");

  const runExperiment = () => {
    const pre = takeSnapshot("pre");
    // compute new vectors from markers
    const updated = applyMarkers();
    // replace current catalog (for UI immediacy)
    setExternalVectors((prev) => {
      const baseKeys = Object.keys(baseVectors);
      const ex: Record<string, number[]> = {};
      for (const [k, v] of Object.entries(updated)) {
        if (!baseKeys.includes(k) && k !== "User0") ex[k] = v; // store only non-bases; base & User0 are implicit
      }
      return ex;
    });
    const post = takeSnapshot("post");
    // delta + attribution (for User0 and Maxey1 as canonical)
    const keysOfInterest = ["User0", "Maxey1"];
    const deltas: Record<string, number[]> = {};
    const attribution: Record<string, Record<string, number>> = {};
    for (const k of keysOfInterest) {
      const dv = subVec(post.vectors[k], pre.vectors[k]);
      deltas[k] = dv;
      attribution[k] = attributionScores(dv, markerBasis);
    }
    const er: ExperimentResult = {
      id: `exp_${Date.now()}`,
      pre,
      post,
      deltas,
      attribution,
      notes: expNotes,
    };
    setHistory((h) => [er, ...h]);
  };

  const exportData = () => {
    const blob = new Blob(
      [
        JSON.stringify(
          {
            latentDim,
            names,
            vectors: latentCatalog,
            distanceMetric: metric,
            distanceMatrix,
            snapshots,
            history,
          },
          null,
          2
        ),
      ],
      { type: "application/json" }
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `maxey_latent_lab_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // ----- 3D Network (Maxey1–3) -----
  const mountRef = useRef<HTMLDivElement | null>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const animationRef = useRef<number | null>(null);

  const [isRunning, setIsRunning] = useState(false);
  const [simulationSpeed, setSimulationSpeed] = useState(1.0);
  const [showPaths, setShowPaths] = useState(true);
  const [showComm, setShowComm] = useState(true);
  const [selectedTarget, setSelectedTarget] = useState<DroneId>(1);
  const [triResult, setTriResult] = useState<{
    target: number;
    actual: [number, number, number];
    calc: [number, number, number];
    error: number;
  } | null>(null);
  const [commLines, setCommLines] = useState<{ from: [number, number, number]; to: [number, number, number]; strength: number }[]>([]);
  const [rt, setRt] = useState<RealTimeData>({ positions: {}, distances: {} });

  const [drones, setDrones] = useState<AgentDrone[]>([
    {
      id: 1,
      name: "Maxey1",
      specialization: "Superposition across latent subspaces",
      color: 0xff6b6b,
      pos: [200, 200, 80],
      vel: [14, 6, 1],
      path: [],
    },
    {
      id: 2,
      name: "Maxey2",
      specialization: "GNN routing / vector proximity",
      color: 0x4ecdc4,
      pos: [800, 250, 120],
      vel: [-10, 8, -2],
      path: [],
    },
    {
      id: 3,
      name: "Maxey3",
      specialization: "A2A streams / pub-sub memory",
      color: 0x45b7d1,
      pos: [450, 800, 100],
      vel: [6, -11, 0],
      path: [],
    },
  ]);

  // init 3D scene
  useEffect(() => {
    if (!mountRef.current) return;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0f172a);
    sceneRef.current = scene;

    const camera = new THREE.PerspectiveCamera(70, 1, 0.1, 5000);
    camera.position.set(900, 900, 500);
    camera.lookAt(500, 500, 60);
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(mountRef.current.clientWidth, mountRef.current.clientHeight);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    rendererRef.current = renderer;
    mountRef.current.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.15;
    controlsRef.current = controls;

    // lights
    const ambient = new THREE.AmbientLight(0xffffff, 0.35);
    scene.add(ambient);
    const dir = new THREE.DirectionalLight(0xffffff, 0.9);
    dir.position.set(1200, 1200, 900);
    dir.castShadow = true;
    dir.shadow.mapSize.width = 2048;
    dir.shadow.mapSize.height = 2048;
    scene.add(dir);

    // ground/grid
    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(MAP_BOUNDS[1][0], MAP_BOUNDS[1][1]),
      new THREE.MeshPhongMaterial({ color: 0x0b1220, side: THREE.DoubleSide })
    );
    ground.rotateX(Math.PI / 2);
    scene.add(ground);

    const grid = new THREE.GridHelper(MAP_BOUNDS[1][0], 20, 0x1f2937, 0x1f2937);
    (grid.material as THREE.Material).opacity = 0.35;
    (grid.material as any).transparent = true;
    scene.add(grid);

    // groups
    const dronesGroup = new THREE.Group();
    dronesGroup.name = "drones";
    scene.add(dronesGroup);

    const pathsGroup = new THREE.Group();
    pathsGroup.name = "paths";
    scene.add(pathsGroup);

    const commGroup = new THREE.Group();
    commGroup.name = "comm";
    scene.add(commGroup);

    const triGroup = new THREE.Group();
    triGroup.name = "tri";
    scene.add(triGroup);

    const onResize = () => {
      if (!rendererRef.current || !cameraRef.current || !mountRef.current) return;
      const w = mountRef.current.clientWidth;
      const h = mountRef.current.clientHeight;
      cameraRef.current.aspect = w / h;
      cameraRef.current.updateProjectionMatrix();
      rendererRef.current.setSize(w, h);
    };
    window.addEventListener("resize", onResize);
    onResize();

    return () => {
      window.removeEventListener("resize", onResize);
      controls.dispose();
      renderer.dispose();
      if (renderer.domElement && renderer.domElement.parentElement) {
        renderer.domElement.parentElement.removeChild(renderer.domElement);
      }
    };
  }, []);

  // draw drones initially & update on drones change
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;
    const group = scene.getObjectByName("drones") as THREE.Group;
    group.clear();
    const labelSprites: THREE.Sprite[] = [];

    drones.forEach((d) => {
      // drone body
      const body = new THREE.Mesh(
        new THREE.SphereGeometry(8, 16, 16),
        new THREE.MeshPhongMaterial({ color: d.color })
      );
      body.position.set(d.pos[0], d.pos[1], d.pos[2]);
      body.castShadow = true;
      body.userData = { id: d.id };
      group.add(body);

      // rotors (visual spin)
      const rotorGeo = new THREE.TorusGeometry(12, 1.5, 8, 32);
      const rotor = new THREE.Mesh(rotorGeo, new THREE.MeshPhongMaterial({ color: 0xffffff, transparent: true, opacity: 0.5 }));
      rotor.position.set(d.pos[0], d.pos[1], d.pos[2] + 6);
      rotor.rotateX(Math.PI / 2);
      rotor.userData = { id: d.id, rotor: true };
      group.add(rotor);

      // label
      const canvas = document.createElement("canvas");
      canvas.width = 256;
      canvas.height = 64;
      const ctx = canvas.getContext("2d")!;
      ctx.fillStyle = "rgba(0,0,0,0.6)";
      ctx.fillRect(0, 0, 256, 64);
      ctx.fillStyle = "white";
      ctx.font = "20px sans-serif";
      ctx.fillText(`${d.name}`, 8, 24);
      ctx.font = "14px sans-serif";
      ctx.fillStyle = "#a7f3d0";
      ctx.fillText(`${d.specialization}`, 8, 48);
      const tex = new THREE.CanvasTexture(canvas);
      const mat = new THREE.SpriteMaterial({ map: tex, transparent: true });
      const sprite = new THREE.Sprite(mat);
      sprite.position.set(d.pos[0], d.pos[1], d.pos[2] + 25);
      sprite.scale.set(70, 18, 1);
      group.add(sprite);
      labelSprites.push(sprite);
    });
  }, [drones]);

  // animation loop
  useEffect(() => {
    const scene = sceneRef.current;
    const camera = cameraRef.current;
    const renderer = rendererRef.current;
    const controls = controlsRef.current;
    if (!scene || !camera || !renderer || !controls) return;

    const pathsGroup = scene.getObjectByName("paths") as THREE.Group;
    const commGroup = scene.getObjectByName("comm") as THREE.Group;

    let last = performance.now();

    const animate = () => {
      animationRef.current = requestAnimationFrame(animate);
      const now = performance.now();
      const dt = Math.min(0.05, (now - last) / 1000) * simulationSpeed;
      last = now;

      // update physics
      if (isRunning) {
        setDrones((prev) =>
          prev.map((d) => {
            const v = [...d.vel] as [number, number, number];
            v[2] -= GRAVITY_M_S2 * dt;
            const p: [number, number, number] = [d.pos[0] + v[0] * dt, d.pos[1] + v[1] * dt, d.pos[2] + v[2] * dt];
            if (p[2] < 5) {
              p[2] = 5;
              v[2] = Math.abs(v[2]) * 0.25;
            }
            const clamped = clampBounds(p);
            const path = d.path.concat([clamped]).slice(-MAX_PATH_POINTS);
            return { ...d, pos: clamped, vel: v, path };
          })
        );
      }

      // rotate rotors, move meshes & labels
      const dg = scene.getObjectByName("drones") as THREE.Group;
      dg.children.forEach((obj) => {
        const id = obj.userData?.id as number | undefined;
        if (!id) return;
        const d = drones.find((dd) => dd.id === id);
        if (!d) return;
        if (obj instanceof THREE.Mesh) {
          if (obj.userData?.rotor) {
            obj.rotation.z += 0.5;
            obj.position.set(d.pos[0], d.pos[1], d.pos[2] + 6);
          } else {
            obj.position.set(d.pos[0], d.pos[1], d.pos[2]);
          }
        }
        if (obj instanceof THREE.Sprite) {
          obj.position.set(d.pos[0], d.pos[1], d.pos[2] + 25);
        }
      });

      // draw paths
      pathsGroup.clear();
      if (showPaths) {
        drones.forEach((d) => {
          if (d.path.length >= 2) {
            const geometry = new THREE.BufferGeometry();
            const positions = new Float32Array(d.path.length * 3);
            d.path.forEach((p, i) => {
              positions[i * 3 + 0] = p[0];
              positions[i * 3 + 1] = p[1];
              positions[i * 3 + 2] = p[2];
            });
            geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
            const material = new THREE.LineBasicMaterial({
              color: d.color,
              transparent: true,
              opacity: 0.5,
            });
            const line = new THREE.Line(geometry, material);
            pathsGroup.add(line);
          }
        });
      }

      // A2A beacons: every 1/BEACON_HZ seconds → update comm lines under COMM_RANGE
      const tms = performance.now();
      if (showComm && (tms % (1000 / BEACON_HZ)) < 40) {
        const lines: typeof commLines = [];
        for (let i = 0; i < drones.length; i++) {
          for (let j = i + 1; j < drones.length; j++) {
            const d1 = drones[i];
            const d2 = drones[j];
            const dist = distance3D(d1.pos, d2.pos);
            if (dist <= COMM_RANGE) {
              lines.push({ from: d1.pos, to: d2.pos, strength: Math.max(0.1, 1 - dist / COMM_RANGE) });
            }
          }
        }
        setCommLines(lines);
      }

      // commit comm lines
      commGroup.clear();
      if (showComm) {
        commLines.forEach((ln) => {
          const geom = new THREE.BufferGeometry();
          geom.setAttribute("position", new THREE.BufferAttribute(new Float32Array([ln.from[0], ln.from[1], ln.from[2], ln.to[0], ln.to[1], ln.to[2]]), 3));
          const mat = new THREE.LineBasicMaterial({ color: 0x00ffff, transparent: true, opacity: ln.strength * 0.55 });
          const obj = new THREE.Line(geom, mat);
          commGroup.add(obj);
        });
      }

      // real-time coordinates & distances
      const positions: RealTimeData["positions"] = {};
      const distances: RealTimeData["distances"] = {};
      drones.forEach((d) => {
        positions[d.id] = d.pos;
        distances[d.id] = {};
        drones.forEach((o) => {
          if (o.id !== d.id) distances[d.id][o.id] = distance3D(d.pos, o.pos);
        });
      });
      setRt({ positions, distances });

      controls.update();
      renderer.render(scene, camera);
    };

    animate();
    return () => {
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
    };
  }, [isRunning, simulationSpeed, showPaths, showComm, drones, commLines]);

  // triangulate selected target using other two as anchors
  const doTriangulate = () => {
    const target = drones.find((d) => d.id === selectedTarget)!;
    const others = drones.filter((d) => d.id !== selectedTarget);
    if (others.length < 2) return;
    const r1 = distance3D(others[0].pos, target.pos);
    const r2 = distance3D(others[1].pos, target.pos);
    const r3 = distance3D(others[others.length - 1].pos, target.pos);
    const est = trilaterate3D(others[0].pos, others[1].pos, others[others.length - 1].pos, r1, r2, r3);
    if (!est) return;
    setTriResult({ target: target.id, actual: target.pos, calc: est, error: distance3D(target.pos, est) });

    const scene = sceneRef.current!;
    const tri = scene.getObjectByName("tri") as THREE.Group;
    tri.clear();
    const m = new THREE.Mesh(new THREE.SphereGeometry(6, 16, 16), new THREE.MeshBasicMaterial({ color: 0xffff00, transparent: true, opacity: 0.9 }));
    m.position.set(est[0], est[1], est[2]);
    tri.add(m);
  };

  // ----- UI Rendering -----
  return (
    <div className="w-full h-screen text-white" style={{ fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system" }}>
      {/* Header */}
      <div className="px-4 py-3 bg-slate-900 flex items-center gap-3">
        <div className="text-lg font-semibold">⚡🤖 Maxey Latent Pairwise Lab</div>
        <div className="ml-auto flex items-center gap-2">
          <button className={`px-3 py-1 rounded ${tab === "network" ? "bg-cyan-600" : "bg-slate-700"}`} onClick={() => setTab("network")}>
            Network
          </button>
          <button className={`px-3 py-1 rounded ${tab === "latent" ? "bg-cyan-600" : "bg-slate-700"}`} onClick={() => setTab("latent")}>
            Latent Space
          </button>
          <button className={`px-3 py-1 rounded ${tab === "markers" ? "bg-cyan-600" : "bg-slate-700"}`} onClick={() => setTab("markers")}>
            Markers/Snapshots
          </button>
          <button className={`px-3 py-1 rounded ${tab === "experiments" ? "bg-cyan-600" : "bg-slate-700"}`} onClick={() => setTab("experiments")}>
            Experiments
          </button>
          <button className="px-3 py-1 rounded bg-emerald-600" onClick={exportData}>
            Export JSON
          </button>
        </div>
      </div>

      {/* User0 input bar */}
      <div className="px-4 py-3 bg-slate-800 flex items-center gap-2">
        <div className="text-sm text-slate-300">User0 input:</div>
        <input
          className="flex-1 px-3 py-2 bg-slate-900 rounded border border-slate-700 outline-none"
          placeholder="Type any text (seeds User0 latent vector deterministically)"
          value={userInput}
          onChange={(e) => setUserInput(e.target.value)}
        />
        <div className="text-sm ml-3 text-slate-400">Latent dim:</div>
        <input
          type="number"
          min={8}
          max={2048}
          className="w-24 px-2 py-1 bg-slate-900 rounded border border-slate-700"
          value={latentDim}
          onChange={(e) => setLatentDim(Math.max(8, Math.min(2048, Number(e.target.value) || DEFAULT_LATENT_DIM)))}
        />
      </div>

      {/* Tabs */}
      {tab === "network" && (
        <div className="flex h-[calc(100vh-112px)]">
          {/* 3D */}
          <div className="flex-1 relative bg-slate-950">
            <div ref={mountRef} className="absolute inset-0" />
            {/* overlay controls */}
            <div className="absolute top-3 left-3 bg-black/70 p-3 rounded max-w-sm text-sm space-y-2">
              <div className="flex gap-2">
                <button className={`px-3 py-2 rounded ${isRunning ? "bg-red-600" : "bg-green-600"}`} onClick={() => setIsRunning((v) => !v)}>
                  {isRunning ? "Stop" : "Start"}
                </button>
                <button className="px-3 py-2 rounded bg-blue-600 disabled:bg-slate-700" onClick={doTriangulate} disabled={!isRunning}>
                  Triangulate Drone {selectedTarget}
                </button>
              </div>
              <div className="flex items-center gap-2">
                <label>Target:</label>
                <select
                  className="bg-slate-800 rounded px-1 py-1"
                  value={selectedTarget}
                  onChange={(e) => setSelectedTarget(Number(e.target.value) as DroneId)}
                >
                  <option value={1}>Maxey1</option>
                  <option value={2}>Maxey2</option>
                  <option value={3}>Maxey3</option>
                </select>
              </div>
              <div className="flex items-center gap-2">
                <label>Speed:</label>
                <input
                  type="range"
                  min={0.1}
                  max={3}
                  step={0.1}
                  value={simulationSpeed}
                  onChange={(e) => setSimulationSpeed(Number(e.target.value))}
                />
                <span>{simulationSpeed.toFixed(1)}x</span>
              </div>
              <div className="flex items-center gap-3">
                <label className="flex items-center gap-1">
                  <input type="checkbox" checked={showPaths} onChange={(e) => setShowPaths(e.target.checked)} /> paths
                </label>
                <label className="flex items-center gap-1">
                  <input type="checkbox" checked={showComm} onChange={(e) => setShowComm(e.target.checked)} /> comm
                </label>
              </div>
              <div className="mt-2 text-xs text-slate-300">
                {triResult && (
                  <div className="space-y-1">
                    <div>Triangulated Drone {triResult.target}</div>
                    <div>Actual: [{triResult.actual.map((x) => x.toFixed(1)).join(", ")}]</div>
                    <div>Calc: &nbsp; [{triResult.calc.map((x) => x.toFixed(1)).join(", ")}]</div>
                    <div>Error: {triResult.error.toFixed(3)} m</div>
                  </div>
                )}
              </div>
            </div>

            {/* mini map */}
            <div className="absolute bottom-3 right-3 bg-black/70 p-2 rounded">
              <div className="text-[10px] text-center text-slate-300">Top-Down</div>
              <svg width="160" height="160">
                <rect x="0" y="0" width="160" height="160" fill="none" stroke="#334155" />
                {/* comm lines */}
                {showComm &&
                  commLines.map((ln, i) => {
                    const x1 = (ln.from[0] / MAP_BOUNDS[1][0]) * 160;
                    const y1 = 160 - (ln.from[1] / MAP_BOUNDS[1][1]) * 160;
                    const x2 = (ln.to[0] / MAP_BOUNDS[1][0]) * 160;
                    const y2 = 160 - (ln.to[1] / MAP_BOUNDS[1][1]) * 160;
                    return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke="cyan" strokeOpacity={ln.strength * 0.6} strokeWidth={1} />;
                  })}
                {/* drones */}
                {Object.entries(rt.positions).map(([id, p]) => {
                  const x = (p[0] / MAP_BOUNDS[1][0]) * 160;
                  const y = 160 - (p[1] / MAP_BOUNDS[1][1]) * 160;
                  const color = id === "1" ? "#ff6b6b" : id === "2" ? "#4ecdc4" : "#45b7d1";
                  return (
                    <g key={id}>
                      <circle cx={x} cy={y} r={4} fill={color} />
                      <text x={x + 6} y={y + 3} fontSize={10} fill="#e2e8f0">{id === "1" ? "Maxey1" : id === "2" ? "Maxey2" : "Maxey3"}</text>
                    </g>
                  );
                })}
              </svg>
            </div>
          </div>

          {/* right panel */}
          <div className="w-96 bg-slate-900 p-3 text-sm space-y-3 overflow-auto">
            <div className="font-semibold text-slate-200">Network Status</div>
            {Object.entries(rt.positions).map(([id, p]) => (
              <div key={id} className="p-2 bg-slate-800/70 rounded">
                <div className="text-slate-300">{id === "1" ? "Maxey1" : id === "2" ? "Maxey2" : "Maxey3"}</div>
                <div className="text-xs text-slate-400">
                  pos: [{p.map((x) => x.toFixed(1)).join(", ")}]
                </div>
                <div className="text-xs text-slate-400">
                  dists:{" "}
                  {Object.entries(rt.distances[Number(id)] || {})
                    .map(([oid, d]) => `→${oid}:${d.toFixed(1)}`)
                    .join("  ")}
                </div>
              </div>
            ))}
            <div className="text-xs text-slate-400">
              Beacons: {BEACON_HZ.toFixed(1)} Hz · Comm range: {COMM_RANGE}m
            </div>
          </div>
        </div>
      )}

      {tab === "latent" && (
        <div className="h-[calc(100vh-112px)] grid grid-cols-2 gap-0">
          {/* Distance + Controls */}
          <div className="p-3 bg-slate-900 overflow-auto">
            <div className="flex items-center gap-3 mb-3">
              <div className="font-semibold">Latent Space</div>
              <label className="text-sm flex items-center gap-2 ml-4">
                Metric:
                <select className="bg-slate-800 rounded px-2 py-1" value={metric} onChange={(e) => setMetric(e.target.value as any)}>
                  <option value="l2">L2</option>
                  <option value="cosine">Cosine (1 - sim)</option>
                </select>
              </label>
            </div>
            <div className="overflow-auto border border-slate-700 rounded">
              <table className="text-xs w-full border-collapse">
                <thead>
                  <tr>
                    <th className="sticky left-0 bg-slate-800 z-10 p-1 text-left">Name</th>
                    {names.map((n) => (
                      <th key={n} className="p-1 border-b border-slate-700">{n}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {names.map((row, i) => (
                    <tr key={row}>
                      <td className="sticky left-0 bg-slate-800 z-10 p-1">{row}</td>
                      {names.map((col, j) => {
                        const v = distanceMatrix[i][j];
                        const bg =
                          i === j ? "bg-slate-800" : metric === "l2"
                            ? v < 3 ? "bg-emerald-900/50" : v < 6 ? "bg-yellow-900/40" : "bg-rose-900/40"
                            : v < 0.3 ? "bg-emerald-900/50" : v < 0.6 ? "bg-yellow-900/40" : "bg-rose-900/40";
                        return (
                          <td key={col} className={`p-1 border-b border-slate-800 ${bg}`}>{v.toFixed(3)}</td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="mt-4">
              <div className="text-sm text-slate-300 mb-1">Paste CSV or JSON vectors (name, v1, v2, ...)</div>
              <textarea
                className="w-full h-32 bg-slate-950 border border-slate-700 rounded p-2 text-xs"
                placeholder='Maxey4, 0.1, -0.2, ...  or  [{"name":"A","vector":[...]}]'
                value={externalText}
                onChange={(e) => setExternalText(e.target.value)}
              />
              <div className="flex gap-2 mt-2">
                <button className="px-3 py-2 rounded bg-indigo-600" onClick={applyExternalVectors}>
                  Load Vectors
                </button>
                <div className="text-xs text-slate-400">Loaded: {Object.keys(externalVectors).length}</div>
              </div>
            </div>
          </div>

          {/* PCA projections (2D SVG + 3D-ish grid) */}
          <div className="p-3 bg-slate-950">
            <div className="font-semibold mb-2">PCA Projection (top-2)</div>
            <svg width="100%" height="280" viewBox="-120 -120 240 240" className="bg-slate-900 rounded border border-slate-700">
              {/* axes */}
              <line x1="-120" y1="0" x2="120" y2="0" stroke="#334155" />
              <line x1="0" y1="-120" x2="0" y2="120" stroke="#334155" />
              {proj3.map((p, i) => {
                const name = names[i];
                const x = p[0] * 100;
                const y = -p[1] * 100;
                const color = name === "Maxey1" ? "#ff6b6b" : name === "Maxey2" ? "#4ecdc4" : name === "Maxey3" ? "#45b7d1" : name === "User0" ? "#eab308" : "#94a3b8";
                return (
                  <g key={name}>
                    <circle cx={x} cy={y} r={3} fill={color} />
                    <text x={x + 4} y={y - 4} fontSize={10} fill="#cbd5e1">{name}</text>
                  </g>
                );
              })}
            </svg>

            <div className="text-xs text-slate-400 mt-3">
              N={names.length}, dim={latentDim}. Mean centered. Simple power-iteration PCA.
            </div>
          </div>
        </div>
      )}

      {tab === "markers" && (
        <div className="h-[calc(100vh-112px)] grid grid-cols-2">
          <div className="p-4 bg-slate-900">
            <div className="font-semibold mb-3">Marker Injection</div>
            <div className="grid grid-cols-2 gap-3">
              {markerKeys.map((k) => (
                <div key={k} className="p-2 bg-slate-800/70 rounded">
                  <div className="text-sm mb-1 capitalize">{k}</div>
                  <input
                    type="range"
                    min={-1}
                    max={1}
                    step={0.01}
                    value={markerWeights[k]}
                    onChange={(e) => setMarkerWeights((w) => ({ ...w, [k]: Number(e.target.value) }))}
                  />
                  <div className="text-xs text-slate-400">{markerWeights[k].toFixed(2)}</div>
                </div>
              ))}
            </div>
            <div className="mt-4 flex gap-2">
              <button className="px-3 py-2 bg-emerald-600 rounded" onClick={() => takeSnapshot("manual")}>
                Snapshot
              </button>
              <button
                className="px-3 py-2 bg-indigo-600 rounded"
                onClick={() => {
                  const updated = applyMarkers();
                  // store only non-base as "external" so UI reflects change
                  setExternalVectors((prev) => {
                    const baseKeys = Object.keys(baseVectors);
                    const ex: Record<string, number[]> = {};
                    for (const [k, v] of Object.entries(updated)) {
                      if (!baseKeys.includes(k) && k !== "User0") ex[k] = v;
                    }
                    return ex;
                  });
                }}
              >
                Apply Markers
              </button>
            </div>
            <div className="mt-4">
              <div className="font-semibold mb-2">Snapshots</div>
              <div className="space-y-2 max-h-72 overflow-auto">
                {snapshots.map((s) => (
                  <div key={s.timestamp} className="p-2 bg-slate-800/70 rounded text-xs">
                    <div>{s.label} — {new Date(s.timestamp).toLocaleTimeString()}</div>
                    <div className="text-slate-400">Vectors: {Object.keys(s.vectors).length}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="p-4 bg-slate-950">
            <div className="font-semibold mb-3">Attribution Preview (Δ vs marker basis)</div>
            {/* live attribution for current User0 vs Maxey1 delta if last two snapshots are pre/post */}
            {snapshots.length >= 2 ? (
              (() => {
                const pre = snapshots[snapshots.length - 2];
                const post = snapshots[snapshots.length - 1];
                const keys = ["User0", "Maxey1"];
                return (
                  <div className="space-y-4">
                    {keys.map((k) => {
                      const dv = subVec(post.vectors[k], pre.vectors[k]);
                      const scores = attributionScores(dv, markerBasis as any);
                      return (
                        <div key={k} className="p-2 bg-slate-800/70 rounded text-sm">
                          <div className="font-medium mb-2">{k} Δ attribution</div>
                          <table className="text-xs w-full">
                            <tbody>
                              {markerKeys.map((mk) => (
                                <tr key={mk}>
                                  <td className="capitalize p-1">{mk}</td>
                                  <td className="p-1">
                                    <div className="bg-slate-900 h-2 rounded">
                                      <div
                                        className={`h-2 rounded ${scores[mk] >= 0 ? "bg-emerald-600" : "bg-rose-600"}`}
                                        style={{ width: `${Math.min(100, Math.abs(scores[mk]) * 100)}%` }}
                                      />
                                    </div>
                                  </td>
                                  <td className="text-right w-16">{scores[mk].toFixed(3)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      );
                    })}
                  </div>
                );
              })()
            ) : (
              <div className="text-slate-400 text-sm">Take two snapshots to preview attribution.</div>
            )}
          </div>
        </div>
      )}

      {tab === "experiments" && (
        <div className="h-[calc(100vh-112px)] grid grid-cols-2">
          <div className="p-4 bg-slate-900">
            <div className="font-semibold mb-2">Run Experiment</div>
            <div className="text-sm text-slate-300 mb-1">
              1) Snapshot pre → 2) Apply markers → 3) Snapshot post, Δ + attribution computed
            </div>
            <div className="space-x-2 mb-3">
              <button className="px-3 py-2 bg-slate-700 rounded" onClick={() => takeSnapshot("pre")}>
                Pre Snapshot
              </button>
              <button className="px-3 py-2 bg-indigo-600 rounded" onClick={() => { setExternalVectors((_) => applyMarkers()); }}>
                Apply Markers
              </button>
              <button className="px-3 py-2 bg-slate-700 rounded" onClick={() => takeSnapshot("post")}>
                Post Snapshot
              </button>
            </div>
            <div className="mt-2">
              <div className="text-sm mb-1">Notes</div>
              <textarea
                className="w-full h-24 bg-slate-950 border border-slate-700 rounded p-2 text-sm"
                placeholder="Describe the experiment setup, expectations, etc."
                value={expNotes}
                onChange={(e) => setExpNotes(e.target.value)}
              />
            </div>
            <div className="mt-3">
              <button className="px-3 py-2 bg-emerald-600 rounded" onClick={runExperiment}>
                Run Full Experiment
              </button>
            </div>
          </div>

          <div className="p-4 bg-slate-950 overflow-auto">
            <div className="font-semibold mb-3">History</div>
            <div className="space-y-3">
              {history.map((h) => (
                <div key={h.id} className="p-2 bg-slate-800/70 rounded text-sm">
                  <div className="font-medium">{h.id}</div>
                  <div className="text-xs text-slate-400 mb-2">{h.notes || "—"}</div>
                  {(["User0", "Maxey1"] as const).map((k) => (
                    <div key={k} className="mb-2">
                      <div className="text-slate-300">{k} Δ-norm: {norm(h.deltas[k]).toFixed(4)}</div>
                      <table className="text-xs w-full">
                        <tbody>
                          {markerKeys.map((mk) => (
                            <tr key={mk}>
                              <td className="capitalize p-1">{mk}</td>
                              <td className="p-1">
                                <div className="bg-slate-900 h-2 rounded">
                                  <div
                                    className={`h-2 rounded ${h.attribution[k][mk] >= 0 ? "bg-emerald-600" : "bg-rose-600"}`}
                                    style={{ width: `${Math.min(100, Math.abs(h.attribution[k][mk]) * 100)}%` }}
                                  />
                                </div>
                              </td>
                              <td className="text-right w-16">{h.attribution[k][mk].toFixed(3)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ))}
                </div>
              ))}
              {history.length === 0 && <div className="text-slate-400 text-sm">No experiments yet.</div>}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default MaxeyLatentLab;
