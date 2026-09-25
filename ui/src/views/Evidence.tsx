/**
 * The Evidence view — containment, tested rather than declared.
 *
 * The one thing this component must never do is render a computation and an
 * attempt the same way. `evidence.pure` distinguishes them, and every block
 * below labels which it is showing. "The closure does not contain region Y" is
 * a statement about a data structure; "role X asked for region Y and the
 * runtime refused, here is the event" is a statement about the system.
 */

import { useCallback, useEffect, useState } from "react";

import { studio, TransportError } from "../api/client";
import {
  isProjection,
  isRefusal,
  type AttemptsResponse,
  type ContainmentResponse,
  type IsolationLevel,
  type IsolationResponse,
  type StreamResponse,
} from "../api/types";

const LEVELS: readonly IsolationLevel[] = [
  "L0_none",
  "L1_logical",
  "L2_execution",
  "L3_observed",
];

function Problem({ children }: { children: React.ReactNode }) {
  return <div className="refusal">{children}</div>;
}

/** A refusal is a result. Show the runtime's own words, never a paraphrase. */
function useEndpoint<T>(load: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setFailure(null);
      setData(await load());
    } catch (error) {
      setFailure(
        error instanceof TransportError ? error.message : String(error),
      );
    }
  }, [load]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { data, failure, refresh };
}

function Containment() {
  const load = useCallback(() => studio.containment(), []);
  const { data, failure, refresh } = useEndpoint(load);

  if (failure) return <Problem>{failure}</Problem>;
  if (!data) return <p className="muted">Loading…</p>;
  if (isRefusal(data)) {
    return (
      <Problem>
        <b>{data.error}</b>
        <p>{data.message}</p>
        <p className="em">
          No roles are bound, so there is nothing to contain. That is not a
          clean result — it is no result.
        </p>
      </Problem>
    );
  }

  const { containment, probed } = data as ContainmentResponse & { ok: true };
  const roles = Object.keys(probed.matrix);
  const firstRole = roles[0];
  const regions = firstRole ? Object.keys(probed.matrix[firstRole] ?? {}) : [];

  return (
    <>
      <button className="ghost" onClick={() => void refresh()}>
        Refresh
      </button>

      <div className={containment.bound_holds ? "allowed" : "refusal"}>
        <b>bound_holds = {String(containment.bound_holds)}</b>
        <p>{containment.verdict}</p>
        {containment.breaches.map((b) => (
          <p key={b.loop}>
            BREACH: <code>{b.loop}</code> reached {b.reached.join(", ")}
          </p>
        ))}
      </div>
      <p className="em">
        Computed over the region graph — a statement about a data structure.
      </p>

      <h3>Probed — a real read attempted per cell</h3>
      <div className="statgrid">
        <div className="stat">
          <b>{probed.refused}</b>
          <span>refused</span>
        </div>
        <div className="stat">
          <b>{probed.granted}</b>
          <span>authorized</span>
        </div>
        <div className="stat">
          <b>{probed.cells}</b>
          <span>cells</span>
        </div>
      </div>

      {regions.length > 0 && (
        <table className="rep">
          <thead>
            <tr>
              <th>role</th>
              {regions.map((r) => (
                <th key={r}>{r}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {roles.map((role) => (
              <tr key={role}>
                <td>
                  <b>{role}</b>
                </td>
                {regions.map((region) => {
                  const allowed = probed.matrix[role]?.[region] ?? false;
                  return (
                    <td key={region} className={allowed ? "" : "bad"}>
                      {allowed ? "read" : "refused"}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="em">
        Each refusal above was produced by the enforcement layer and is a record
        in the ledger that replay reproduces.
      </p>

      <div className={probed.closure_disagreements.length ? "refusal" : "allowed"}>
        <b>closure disagreements: {probed.closure_disagreements.length}</b>
        {probed.closure_disagreements.length === 0 ? (
          <p>Every cell agrees with its closure.</p>
        ) : (
          <>
            <p>
              The computation and the attempt disagree. One of them is wrong,
              and that is a defect rather than a measurement.
            </p>
            {probed.closure_disagreements.map((d) => (
              <p key={`${d.loop}:${d.region}`}>
                <code>{d.loop}</code> → <code>{d.region}</code>: call said{" "}
                {String(d.call)}, closure said {String(d.closure)}
              </p>
            ))}
          </>
        )}
      </div>
    </>
  );
}

function Isolation() {
  const [declared, setDeclared] = useState<string>("");
  const load = useCallback(() => studio.isolation(declared || undefined), [declared]);
  const { data, failure } = useEndpoint(load);

  return (
    <>
      <div className="row spread">
        <h2>Isolation level</h2>
        <select value={declared} onChange={(e) => setDeclared(e.target.value)}>
          <option value="">— declared —</option>
          {LEVELS.map((l) => (
            <option key={l} value={l}>
              {l}
            </option>
          ))}
        </select>
      </div>
      <p className="muted small">
        A level is earned from evidence, never asserted. Declare L3 and get L1 —
        three roles dispatched into one shared context, the partition existing
        only in the prompt — and nothing else in the stack would notice.
      </p>

      {failure && <Problem>{failure}</Problem>}
      {data && isRefusal(data) && (
        <Problem>
          <b>{data.error}</b>
          <p>{data.message}</p>
        </Problem>
      )}
      {data && !isRefusal(data) && <IsolationBody data={data} />}
    </>
  );
}

function IsolationBody({ data }: { data: IsolationResponse }) {
  const shortfall = data.shortfall;
  const lines =
    shortfall === undefined
      ? []
      : Array.isArray(shortfall)
        ? shortfall
        : [shortfall];

  return (
    <>
      <div className="statgrid">
        <div className="stat">
          <b>{data.evidenced}</b>
          <span>evidenced</span>
        </div>
        <div className="stat">
          <b>{data.declared ?? "—"}</b>
          <span>declared</span>
        </div>
      </div>
      {lines.length > 0 && (
        <div className="refusal">
          <b>Shortfall</b>
          {lines.map((line) => (
            <p key={line}>{line}</p>
          ))}
        </div>
      )}
    </>
  );
}

function Stream() {
  const [kind, setKind] = useState("");
  const [role, setRole] = useState("");
  const [region, setRegion] = useState("");

  const load = useCallback(
    () =>
      Promise.all([
        studio.stream({ kinds: kind, role, region }),
        role || region ? studio.attempts(role, region) : Promise.resolve(null),
      ]),
    [kind, role, region],
  );
  const { data, failure } = useEndpoint(load);

  return (
    <>
      <div className="row spread">
        <h2>Event stream</h2>
        <div className="row">
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">all kinds</option>
            {["access", "refusal", "scope", "bridge", "utilization", "audit", "routing"].map(
              (k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ),
            )}
          </select>
          <input
            value={role}
            placeholder="role"
            onChange={(e) => setRole(e.target.value)}
          />
          <input
            value={region}
            placeholder="region"
            onChange={(e) => setRegion(e.target.value)}
          />
        </div>
      </div>

      {failure && <Problem>{failure}</Problem>}
      {data && (
        <>
          {data[1] && !isRefusal(data[1]) && <Attempts data={data[1]} />}
          {isRefusal(data[0]) ? (
            <Problem>
              <b>{data[0].error}</b>
            </Problem>
          ) : (
            <StreamBody data={data[0]} />
          )}
        </>
      )}
    </>
  );
}

function Attempts({ data }: { data: AttemptsResponse }) {
  // Three-valued on purpose. null is not a pass.
  const { contained } = data;
  const className =
    contained === true ? "allowed" : contained === false ? "refusal" : "";
  return (
    <div className={className}>
      <b>contained = {contained === null ? "null" : String(contained)}</b>
      {contained === null && (
        <p>No attempt was recorded. This establishes nothing either way.</p>
      )}
    </div>
  );
}

function StreamBody({ data }: { data: StreamResponse }) {
  if (!isProjection(data)) {
    const kinds = Object.entries(data.by_kind);
    const refusals = Object.entries(data.refusals_by_loop);
    return (
      <>
        <div className="statgrid">
          <div className="stat">
            <b>{data.events}</b>
            <span>events</span>
          </div>
          <div className="stat">
            <b>{refusals.reduce((n, [, v]) => n + v, 0)}</b>
            <span>refusals</span>
          </div>
          <div className="stat">
            <b>{Object.keys(data.regions_refused).length}</b>
            <span>regions refused</span>
          </div>
        </div>
        {kinds.length > 0 && (
          <table className="rep">
            <thead>
              <tr>
                <th>kind</th>
                <th>events</th>
              </tr>
            </thead>
            <tbody>
              {kinds.map(([k, v]) => (
                <tr key={k}>
                  <td>{k}</td>
                  <td>{v}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="em">
          Summary of the whole run. Filter by kind, role or region for the
          individual events.
        </p>
      </>
    );
  }

  if (data.events.length === 0) {
    return (
      <p className="muted">
        No events match this filter. An empty stream is not evidence of
        containment; it is an absence of evidence.
      </p>
    );
  }

  return (
    <>
      <p className="em">
        {data.matched} matched, {data.returned} shown.
      </p>
      <table className="rep">
        <thead>
          <tr>
            <th>seq</th>
            <th>kind</th>
            <th>type</th>
            <th>role</th>
            <th>region</th>
          </tr>
        </thead>
        <tbody>
          {[...data.events].reverse().slice(0, 120).map((e) => (
            <tr key={e.seq}>
              <td>{e.seq}</td>
              <td>{e.kind}</td>
              <td>
                <code>{e.type}</code>
              </td>
              <td>{e.loop_id ?? "—"}</td>
              <td>{e.scw_id ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

export function Evidence() {
  return (
    <section className="view" data-view="evidence">
      <div className="card">
        <div className="row spread">
          <h2>Containment</h2>
        </div>
        <p className="muted small">
          Two of the four assertions attempt a <strong>real read</strong> through
          the real authorization path, so a refusal is an event the ledger
          records and replay reproduces. The other two compute over the region
          graph. Every row says which you are looking at, because a set
          computation is a weaker claim than an attempt the runtime actually
          refused.
        </p>
        <Containment />
      </div>

      <div className="card">
        <Isolation />
      </div>

      <div className="card">
        <Stream />
      </div>
    </section>
  );
}
