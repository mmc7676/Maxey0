/**
 * The React front end for the Maxey0 Studio.
 *
 * It is deliberately additive. `python server/run_studio.py` serves the
 * standard-library Studio on a bare Python 3.10+ with no `npm install`, and
 * that promise is worth more than a uniform stack: an operator diagnosing a
 * containment question at 2am should not first have to build a front end.
 * So this compiles into `static/app/`, is served by the same Python process
 * when present, and changes nothing when absent.
 *
 * What it adds is a typed boundary. `src/generated/catalog.ts` is emitted from
 * `server/planes/catalog.py`, so renaming a tool in Python turns every stale
 * use here into a compile error rather than a runtime surprise.
 */

import { useState } from "react";

import {
  CONNECTORS,
  COUNTS,
  PLANES,
  toolsFor,
  type ConnectorId,
  type PlaneId,
} from "./generated/catalog";
import { Evidence } from "./views/Evidence";

const PLANE_IDS: readonly PlaneId[] = ["execution", "context", "engineering"];
const CONNECTOR_IDS: readonly ConnectorId[] = ["context", "loops", "observe"];

function Planes() {
  return (
    <section className="view">
      <div className="card">
        <h2>Three planes</h2>
        <p className="muted small">
          A plane is what the system is. A connector is what installs. Maxey0
          owns two of the three planes — the Execution plane belongs to the
          host, and the Gate stands at its boundary rather than inside it.
        </p>
        <table className="rep">
          <thead>
            <tr>
              <th>plane</th>
              <th>owner</th>
              <th>holds</th>
              <th>Maxey0&rsquo;s part</th>
              <th>connectors</th>
            </tr>
          </thead>
          <tbody>
            {PLANE_IDS.map((id) => {
              const plane = PLANES[id];
              return (
                <tr key={id}>
                  <td>
                    <b>{plane.title}</b>
                  </td>
                  <td>{plane.owner}</td>
                  <td>{plane.holds}</td>
                  <td>{plane.maxey0}</td>
                  <td>{plane.connectors || <span className="em">none</span>}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2>Three connectors, {COUNTS.total} tools</h2>
        <p className="muted small">
          Each installs on its own and is useful alone.
        </p>
        {CONNECTOR_IDS.map((id) => {
          const meta = CONNECTORS[id];
          const tools = toolsFor(id);
          return (
            <div key={id}>
              <h3>
                <code>{meta.connector}</code> ({tools.length}) &mdash; serves the{" "}
                {PLANES[meta.plane].title} plane
              </h3>
              <p className="em">{meta.tagline}</p>
              <p className="muted small">
                <b>Alone:</b> {meta.alone}
              </p>
              <table className="rep">
                <thead>
                  <tr>
                    <th>tool</th>
                    <th>writes</th>
                    <th>does</th>
                  </tr>
                </thead>
                <tbody>
                  {tools.map((t) => (
                    <tr key={t.name}>
                      <td>
                        <code>{t.name}</code>
                      </td>
                      <td>{t.mutates ? "yes" : "no"}</td>
                      <td>{t.summary}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        })}
      </div>
    </section>
  );
}

type Tab = "evidence" | "planes";

export function App() {
  const [tab, setTab] = useState<Tab>("evidence");

  return (
    <>
      <header className="brand">
        <h1>Maxey0</h1>
        <span className="em">
          {COUNTS.context} context · {COUNTS.loops} loops · {COUNTS.observe}{" "}
          observe
        </span>
      </header>
      <nav className="tabs">
        <button
          className={tab === "evidence" ? "active" : ""}
          onClick={() => setTab("evidence")}
        >
          Evidence
        </button>
        <button
          className={tab === "planes" ? "active" : ""}
          onClick={() => setTab("planes")}
        >
          Planes
        </button>
      </nav>
      {tab === "evidence" ? <Evidence /> : <Planes />}
    </>
  );
}
