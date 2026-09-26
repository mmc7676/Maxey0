import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useApp, useHostStyles } from "@modelcontextprotocol/ext-apps/react";

type Segment = { segment_id: string; start: number; end: number; label: string };

/**
 * Gate outcome.
 *
 * `invalid` exists so that a client-side JSON parse failure is NOT reported as
 * a gate denial. In this system a denial is a recorded architectural event;
 * a malformed textarea is not one, and conflating them made the UI contradict
 * the containment model.
 *
 * Transport and execution failures (origin unreachable, -32010) set the state
 * back to `not_checked` rather than `denied`: a call that never reached the
 * gate produced no gate decision, and claiming one would be a fabrication.
 */
type GateDecision = "not_checked" | "allowed" | "denied" | "invalid";

/** Shape of an MCP CallToolResult, as far as this App relies on it. */
type ToolResult = {
  isError?: boolean;
  content?: Array<{ type: string; text?: string }>;
  structuredContent?: unknown;
};

type Spec = {
  parent_id?: string | null;
  concept?: string;
  skills?: string[];
  drift_threshold?: number;
};

type DescribePayload = {
  specifications?: Record<string, Spec>;
  scw_instances?: Record<string, unknown>;
};

const DEFAULT_ADDRESS = "scw://maxey0/context/observation/host-window/SCW0";

const SEGMENTS_PLACEHOLDER = `[
  {
    "segment_id": "seg-1",
    "start": 0,
    "end": 240,
    "label": "system-preamble"
  }
]`;

function pretty(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

/**
 * Unwrap a CallToolResult to the server's own payload.
 *
 * The server returns plain dicts; the MCP layer wraps them as
 * `structuredContent`. Reading fields directly off the CallToolResult — as
 * `inspectGate` previously did with `"allowed" in result` — always missed,
 * because `allowed` lives one level down.
 */
function payloadOf(result: unknown): unknown {
  if (result && typeof result === "object" && "structuredContent" in result) {
    const structured = (result as ToolResult).structuredContent;
    if (structured !== undefined) return structured;
  }
  return result;
}

/**
 * A tool-level failure is reported as `isError` on a *successful* JSON-RPC
 * response. It does not throw, so it has to be checked explicitly.
 */
function isToolError(result: unknown): boolean {
  return Boolean(
    result && typeof result === "object" && (result as ToolResult).isError === true,
  );
}

function toolErrorText(result: unknown): string {
  const blocks = (result as ToolResult | undefined)?.content ?? [];
  const text = blocks
    .map((block) => block?.text)
    .filter((value): value is string => Boolean(value))
    .join("\n")
    .trim();
  return text || "The tool reported an error without detail.";
}

function messageOf(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}

const TABS = [
  { id: "observe", label: "Observe" },
  { id: "windows", label: "Windows" },
  { id: "evidence", label: "Evidence" },
  { id: "providers", label: "Providers" },
  { id: "posture", label: "Posture" },
] as const;

type TabId = (typeof TABS)[number]["id"];

/**
 * Per-panel request state.
 *
 * Split into status / result / error deliberately. One variable held idle
 * text, progress, JSON and errors and rendered all four identically, so on
 * every tab but the first an error was indistinguishable from a success.
 */
type PanelState = {
  status: string;
  result: string;
  error: string | null;
  busy: boolean;
};

const IDLE: PanelState = { status: "Ready", result: "", error: null, busy: false };

export function App() {
  const { app, isConnected, error } = useApp({
    appInfo: { name: "Maxey0-SuperSpace", version: "0.3.1" },
    capabilities: {},
  });
  useHostStyles(app, app?.getHostContext() ?? null);

  const [tab, setTab] = useState<TabId>("observe");
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  // -- observe ---------------------------------------------------------------
  const [address, setAddress] = useState(DEFAULT_ADDRESS);
  const [segmentsText, setSegmentsText] = useState("");
  const [decision, setDecision] = useState<GateDecision>("not_checked");
  const [gateDetail, setGateDetail] = useState<Record<string, unknown> | null>(null);
  const [observe, setObserve] = useState<PanelState>(IDLE);

  // -- windows ---------------------------------------------------------------
  const [scwId, setScwId] = useState("SCW1");
  const [task, setTask] = useState("Maxey0-SuperSpace workspace");
  const [specs, setSpecs] = useState<Record<string, Spec>>({});
  const [instances, setInstances] = useState<Record<string, unknown>>({});
  const [selected, setSelected] = useState<string | null>(null);
  const [confirmingClose, setConfirmingClose] = useState(false);
  const [driftVector, setDriftVector] = useState("[1.0, 0.0, 0.0]");
  const [windows, setWindows] = useState<PanelState>(IDLE);

  // -- the read-only panels --------------------------------------------------
  const [evidence, setEvidence] = useState<PanelState>(IDLE);
  const [providers, setProviders] = useState<PanelState>(IDLE);
  const [posture, setPosture] = useState<PanelState>(IDLE);
  const [providerName, setProviderName] = useState("anthropic");
  const [prompt, setPrompt] = useState("");
  const [attestLimit, setAttestLimit] = useState("50");

  const segments = useMemo<
    { ok: true; value: Segment[] } | { ok: false; message: string }
  >(() => {
    const raw = segmentsText.trim();
    if (raw === "") return { ok: true, value: [] };
    try {
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) {
        return { ok: false, message: "Segments must be a JSON array." };
      }
      return { ok: true, value: parsed as Segment[] };
    } catch (e) {
      return { ok: false, message: `Segments are not valid JSON — ${messageOf(e)}` };
    }
  }, [segmentsText]);

  const call = useCallback(
    async (name: string, args: Record<string, unknown> = {}) => {
      if (!app || !isConnected) {
        throw new Error("MCP App is not connected to its host.");
      }
      return app.callServerTool({ name, arguments: args });
    },
    [app, isConnected],
  );

  /**
   * Run one tool into one panel.
   *
   * Every read-only panel goes through this, so the three outcomes a tool call
   * has — a result, a tool-level `isError`, and a transport failure that never
   * reached the server — are distinguished identically everywhere. Hand-written
   * per-panel handlers is how `observe` came to treat `isError: true` as
   * success: the catch never fired, because a tool error does not throw.
   */
  const run = useCallback(
    async (
      set: (next: PanelState) => void,
      name: string,
      args: Record<string, unknown>,
      progress: string,
    ): Promise<unknown | null> => {
      set({ status: progress, result: "", error: null, busy: true });
      try {
        const result = await call(name, args);
        if (isToolError(result)) {
          set({
            status: `${name} reported an error.`,
            result: "",
            error: toolErrorText(result),
            busy: false,
          });
          return null;
        }
        const payload = payloadOf(result);
        set({
          status: `${name} answered.`,
          result: pretty(payload),
          error: null,
          busy: false,
        });
        return payload;
      } catch (e) {
        set({
          status: "The call did not reach the server.",
          result: "",
          error: messageOf(e),
          busy: false,
        });
        return null;
      }
    },
    [call],
  );

  // -- observe actions -------------------------------------------------------

  async function inspectGate() {
    setObserve({ ...IDLE, status: "Asking the gate…", busy: true });
    try {
      const result = await call("maxey0-ss.gate.inspect", { scw_address: address });
      if (isToolError(result)) {
        setDecision("denied");
        setGateDetail(null);
        setObserve({
          status: "The gate call failed.",
          result: "",
          error: toolErrorText(result),
          busy: false,
        });
        return;
      }
      const payload = payloadOf(result) as Record<string, unknown> | null;
      const allowed = Boolean(payload && payload.allowed);
      setDecision(allowed ? "allowed" : "denied");
      setGateDetail(payload);
      setObserve({
        status: allowed ? "The gate allowed the address." : "The gate denied the address.",
        result: pretty(payload),
        error: null,
        busy: false,
      });
    } catch (e) {
      // A call that never reached the gate produced no decision.
      setDecision("not_checked");
      setGateDetail(null);
      setObserve({
        status: "The call did not reach the gate.",
        result: "",
        error: messageOf(e),
        busy: false,
      });
    }
  }

  async function observeWindow() {
    if (!segments.ok) {
      setDecision("invalid");
      setObserve({
        status: "Nothing was sent — the segments field could not be parsed.",
        result: "",
        error: segments.message,
        busy: false,
      });
      return;
    }
    setObserve({ ...IDLE, status: "Requesting host-visible context…", busy: true });
    try {
      const result = await call("maxey0-ss.scw.observe_host_window", {
        scw_address: address,
        segments: segments.value,
      });
      if (isToolError(result)) {
        setDecision("denied");
        setObserve({
          status: "The observation was refused.",
          result: "",
          error: toolErrorText(result),
          busy: false,
        });
        return;
      }
      setDecision("allowed");
      setObserve({
        status: `Observed ${segments.value.length} host-supplied segment(s).`,
        result: pretty(payloadOf(result)),
        error: null,
        busy: false,
      });
    } catch (e) {
      setDecision("not_checked");
      setObserve({
        status: "The call did not reach the gate.",
        result: "",
        error: messageOf(e),
        busy: false,
      });
    }
  }

  // -- window actions --------------------------------------------------------

  const refreshWindows = useCallback(async () => {
    const payload = (await run(
      setWindows, "maxey0-ss.scw.describe", {}, "Reading the window directory…",
    )) as DescribePayload | null;
    if (!payload) return;
    const found = payload.specifications ?? {};
    setSpecs(found);
    setInstances(payload.scw_instances ?? {});
    setSelected((current) => (current && current in found ? current : null));
    setWindows((s) => ({
      ...s,
      status: `${Object.keys(found).length} specification(s).`,
    }));
  }, [run]);

  async function createWindow() {
    const ok = await run(
      setWindows, "maxey0-ss.scw.create",
      { scw_id: scwId, task, concept: "Task" }, `Creating ${scwId}…`,
    );
    if (ok) await refreshWindows();
  }

  async function closeWindow() {
    if (!selected) return;
    setConfirmingClose(false);
    const ok = await run(
      setWindows, "maxey0-ss.scw.close", { scw_id: selected }, `Closing ${selected}…`,
    );
    if (ok) await refreshWindows();
  }

  async function measureDrift(anchor: boolean) {
    if (!selected) return;
    let vector: unknown;
    try {
      vector = JSON.parse(driftVector);
    } catch (e) {
      setWindows({
        status: "Nothing was sent — the vector could not be parsed.",
        result: "", error: messageOf(e), busy: false,
      });
      return;
    }
    await run(
      setWindows, "maxey0-ss.scw.drift",
      anchor ? { scw_id: selected, vector, anchor: true } : { scw_id: selected, vector },
      anchor ? `Anchoring ${selected}…` : `Measuring drift for ${selected}…`,
    );
  }

  // -- keyboard --------------------------------------------------------------

  function onTabKey(event: React.KeyboardEvent) {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const index = TABS.findIndex((t) => t.id === tab);
    const next = TABS[
      (index + (event.key === "ArrowRight" ? 1 : TABS.length - 1)) % TABS.length
    ].id;
    setTab(next);
    tabRefs.current[next]?.focus();
  }

  useEffect(() => {
    if (tab === "windows" && Object.keys(specs).length === 0 && !windows.busy) {
      void refreshWindows();
    }
  }, [tab, specs, windows.busy, refreshWindows]);

  // -- render ----------------------------------------------------------------

  if (error) {
    return (
      <main className="space">
        <h1>Maxey0-SuperSpace</h1>
        <div className="error" role="alert">{error.message}</div>
      </main>
    );
  }
  if (!isConnected) {
    return (
      <main className="space">
        <h1>Maxey0-SuperSpace</h1>
        <p className="muted" role="status">Connecting to MCP host…</p>
      </main>
    );
  }

  const specEntries = Object.entries(specs);

  return (
    <main className="space">
      <header>
        <div>
          <div className="eyebrow">Maxey0-SuperSpace</div>
          <h1>Governed context and execution</h1>
          <p className="muted">
            MCP 2026-07-28 · stateless transport · explicit SCW application state
          </p>
        </div>
        <span
          className={`pill ${decision}`}
          role="status"
          aria-label={`Gate decision: ${decision.replace("_", " ")}`}
        >
          {decision.replace("_", " ")}
        </span>
      </header>

      <div className="tabs" role="tablist" aria-label="Sections">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            id={`tab-${t.id}`}
            ref={(el) => { tabRefs.current[t.id] = el; }}
            aria-selected={tab === t.id}
            aria-controls={`panel-${t.id}`}
            tabIndex={tab === t.id ? 0 : -1}
            onClick={() => setTab(t.id)}
            onKeyDown={onTabKey}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* ---------------------------------------------------------- observe */}
      <Panel id="observe" active={tab}>
        <div className="grid">
          <section className="card" aria-labelledby="h-address">
            <h2 id="h-address">SCW address</h2>
            <input
              aria-label="SCW address"
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              spellCheck={false}
            />
            <p className="muted">
              The address is application state. It is not a claim of access to
              hidden model context.
            </p>
            <div className="actions">
              <button onClick={inspectGate} disabled={observe.busy}>
                {observe.busy ? "Working…" : "Inspect gate"}
              </button>
              <button onClick={observeWindow} disabled={observe.busy}>
                {observe.busy ? "Working…" : "Observe host window"}
              </button>
            </div>
          </section>

          <section className="card" aria-labelledby="h-admission">
            <h2 id="h-admission">Admission</h2>
            <dl>
              <dt>Capability</dt>
              <dd>maxey0-ss.scw.observe_host_window</dd>
              <dt>Decision</dt>
              <dd>{decision.replace("_", " ")}</dd>
              <dt>Provider</dt>
              <dd>{String(gateDetail?.semantic_provider ?? "—")}</dd>
              <dt>Stage</dt>
              <dd>{String(gateDetail?.stage ?? "—")}</dd>
            </dl>
            {gateDetail?.reason ? (
              <p className="muted">{String(gateDetail.reason)}</p>
            ) : null}
          </section>
        </div>

        <div className="grid">
          <section className="card" aria-labelledby="h-segments">
            <h2 id="h-segments">Host-visible segments</h2>
            <textarea
              aria-label="Host-visible segments JSON"
              aria-invalid={!segments.ok}
              aria-describedby={segments.ok ? undefined : "segments-problem"}
              placeholder={SEGMENTS_PLACEHOLDER}
              value={segmentsText}
              onChange={(e) => setSegmentsText(e.target.value)}
              spellCheck={false}
            />
            {!segments.ok && (
              <p className="notice" id="segments-problem">{segments.message}</p>
            )}
            <p className="muted">
              Only context the host explicitly supplied is observable here.
              Empty means no segments.
            </p>
          </section>
          <Result title="Request result" state={observe} />
        </div>
      </Panel>

      {/* ---------------------------------------------------------- windows */}
      <Panel id="windows" active={tab}>
        <div className="grid">
          <section className="card" aria-labelledby="h-create">
            <h2 id="h-create">Create specification</h2>
            <label htmlFor="scw-id">SCW ID</label>
            <input id="scw-id" value={scwId} spellCheck={false}
                   onChange={(e) => setScwId(e.target.value)} />
            <label htmlFor="scw-task">Task</label>
            <input id="scw-task" value={task}
                   onChange={(e) => setTask(e.target.value)} />
            <div className="actions">
              <button onClick={createWindow} disabled={windows.busy || !scwId.trim()}>
                {windows.busy ? "Working…" : "Create"}
              </button>
              <button onClick={() => void refreshWindows()} disabled={windows.busy}>
                Refresh
              </button>
            </div>
          </section>

          <section className="card" aria-labelledby="h-directory">
            <h2 id="h-directory">Directory</h2>
            {specEntries.length === 0 ? (
              <p className="empty">No specifications. Create one, or Refresh.</p>
            ) : (
              <ul className="scw-list">
                {specEntries.map(([id, spec]) => (
                  <li key={id}>
                    <button
                      className="scw-item"
                      aria-pressed={selected === id}
                      onClick={() => {
                        setSelected(selected === id ? null : id);
                        setConfirmingClose(false);
                      }}
                    >
                      <span className="scw-id">{id}</span>
                      <span className="scw-meta">
                        {spec.concept ?? "—"}
                        {spec.parent_id ? ` · parent ${spec.parent_id}` : " · root"}
                        {id in instances ? " · instantiated" : " · specification only"}
                        {typeof spec.drift_threshold === "number"
                          ? ` · drift ${spec.drift_threshold}` : ""}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <div className="actions">
              <button
                className="danger"
                onClick={() => setConfirmingClose(true)}
                disabled={windows.busy || !selected || confirmingClose}
              >
                {selected ? `Close ${selected}` : "Close — select one first"}
              </button>
            </div>
            {confirmingClose && selected && (
              <div className="notice" role="alertdialog"
                   aria-label={`Confirm closing ${selected}`}>
                <p style={{ margin: "0 0 8px" }}>
                  Close <strong>{selected}</strong>? This stops the instance and
                  drops its cached answers. The specification remains.
                </p>
                <div className="actions" style={{ marginTop: 0 }}>
                  <button className="danger" onClick={closeWindow} disabled={windows.busy}>
                    Confirm close
                  </button>
                  <button onClick={() => setConfirmingClose(false)}>Cancel</button>
                </div>
              </div>
            )}
          </section>
        </div>

        <div className="grid">
          <section className="card" aria-labelledby="h-drift">
            <h2 id="h-drift">Semantic drift</h2>
            <p className="muted">
              Anchor a baseline, then measure against it. An un-anchored window
              is refused rather than answered — with no baseline there is
              nothing to measure against.
            </p>
            <label htmlFor="drift-vector">Vector</label>
            <input id="drift-vector" value={driftVector} spellCheck={false}
                   onChange={(e) => setDriftVector(e.target.value)} />
            <div className="actions">
              <button onClick={() => void measureDrift(true)}
                      disabled={windows.busy || !selected}>
                Anchor
              </button>
              <button onClick={() => void measureDrift(false)}
                      disabled={windows.busy || !selected}>
                Measure
              </button>
            </div>
          </section>
          <Result title="Latest operation" state={windows} />
        </div>
      </Panel>

      {/* --------------------------------------------------------- evidence */}
      <Panel id="evidence" active={tab}>
        <div className="grid">
          <section className="card" aria-labelledby="h-evidence">
            <h2 id="h-evidence">Containment record</h2>
            <p className="muted">
              What was attempted across every boundary, and the outcome. The
              chain is hash-linked, so a removed entry is detectable rather than
              invisible.
            </p>
            <label htmlFor="attest-limit">Limit</label>
            <input id="attest-limit" value={attestLimit} spellCheck={false}
                   onChange={(e) => setAttestLimit(e.target.value)} />
            <div className="actions">
              <button
                onClick={() => void run(setEvidence, "maxey0-ss.evidence.summary", {},
                                        "Reading counts and chain head…")}
                disabled={evidence.busy}
              >
                Summary
              </button>
              <button
                onClick={() => void run(setEvidence, "maxey0-ss.evidence.attestations",
                                        { limit: Number(attestLimit) || 50 },
                                        "Reading attestations…")}
                disabled={evidence.busy}
              >
                Attestations
              </button>
              <button
                onClick={() => void run(setEvidence, "maxey0-ss.observe.events", {},
                                        "Reading observed events…")}
                disabled={evidence.busy}
              >
                Events
              </button>
            </div>
          </section>
          <Result title="Evidence" state={evidence} />
        </div>
      </Panel>

      {/* -------------------------------------------------------- providers */}
      <Panel id="providers" active={tab}>
        <div className="grid">
          <section className="card" aria-labelledby="h-providers">
            <h2 id="h-providers">Model egress</h2>
            <p className="muted">
              Every call is admitted by the gate and written to the containment
              chain before it leaves. The prompt is digested, never recorded.
            </p>
            <label htmlFor="provider-name">Provider</label>
            <select id="provider-name" value={providerName}
                    onChange={(e) => setProviderName(e.target.value)}>
              <option value="anthropic">anthropic</option>
              <option value="openai">openai</option>
              <option value="huggingface">huggingface</option>
            </select>
            <label htmlFor="provider-prompt">Prompt</label>
            <textarea id="provider-prompt" value={prompt} spellCheck={false}
                      placeholder="Sent to the selected provider."
                      onChange={(e) => setPrompt(e.target.value)} />
            <div className="actions">
              <button
                onClick={() => void run(setProviders, "maxey0-ss.provider.status", {},
                                        "Reading provider configuration…")}
                disabled={providers.busy}
              >
                Status
              </button>
              <button
                onClick={() => void run(setProviders, "maxey0-ss.provider.complete",
                                        { provider: providerName, prompt },
                                        `Sending to ${providerName}…`)}
                disabled={providers.busy || !prompt.trim()}
              >
                {providers.busy ? "Working…" : "Send"}
              </button>
            </div>
          </section>
          <Result title="Provider" state={providers} />
        </div>
      </Panel>

      {/* ---------------------------------------------------------- posture */}
      <Panel id="posture" active={tab}>
        <div className="grid">
          <section className="card" aria-labelledby="h-posture">
            <h2 id="h-posture">Deployment posture</h2>
            <p className="muted">
              <strong>admin_open</strong> is the one to read. It is true when
              every caller is admin — correct for a trusted local install, a
              critical finding on anything internet-reachable.
            </p>
            <div className="actions">
              <button
                onClick={() => void run(setPosture, "maxey0-ss.auth.manifest", {},
                                        "Reading authorization posture…")}
                disabled={posture.busy}
              >
                Authorization
              </button>
              <button
                onClick={() => void run(setPosture, "maxey0-ss.deployment", {},
                                        "Reading provider sockets…")}
                disabled={posture.busy}
              >
                Deployment
              </button>
              <button
                onClick={() => void run(setPosture, "maxey0-ss.health", {},
                                        "Reading health…")}
                disabled={posture.busy}
              >
                Health
              </button>
              <button
                onClick={() => void run(setPosture, "maxey0-ss.cache.status", {},
                                        "Reading cache status…")}
                disabled={posture.busy}
              >
                Cache
              </button>
              <button
                onClick={() => void run(setPosture, "maxey0-ss.distribution", {},
                                        "Reading the distribution registry…")}
                disabled={posture.busy}
              >
                Distribution
              </button>
            </div>
          </section>
          <Result title="Posture" state={posture} />
        </div>
      </Panel>

      <footer>
        Maxey0 owns the application-level window, routing, gating and
        observability boundary. The model and the agent harness remain external.
      </footer>
    </main>
  );
}

function Panel(
  { id, active, children }: {
    id: TabId; active: TabId; children: React.ReactNode;
  },
) {
  return (
    <section
      role="tabpanel"
      id={`panel-${id}`}
      aria-labelledby={`tab-${id}`}
      hidden={active !== id}
    >
      {children}
    </section>
  );
}

function Result({ title, state }: { title: string; state: PanelState }) {
  return (
    <section className="card" aria-labelledby={`h-${title.replace(/\s+/g, "-")}`}>
      <h2 id={`h-${title.replace(/\s+/g, "-")}`}>{title}</h2>
      {state.error && <div className="error" role="alert">{state.error}</div>}
      <p className="status-line" role="status" aria-live="polite">{state.status}</p>
      <pre aria-live="polite" aria-busy={state.busy}>
        {state.result || "No result yet."}
      </pre>
    </section>
  );
}
