import React, { useState } from "react";

type TierId = 0 | 1 | 2 | 3 | 4;

interface MaxeyAgent {
  id: string;
  name: string;
  role: string;
  tier: TierId;
  notes: string;
  color: string;
}

interface WorkflowStep {
  id: string;
  agentId: string;
  label: string;
  stage: string;
}

interface MaxeyWorkflow {
  id: string;
  name: string;
  purpose: string;
  entryPoint: string;
  steps: WorkflowStep[];
}

const TIERS: { id: TierId; label: string; description: string }[] = [
  { id: 0, label: "Tier 0 · SCW Shell", description: "Entry, routing, and surface IO." },
  { id: 1, label: "Tier 1 · Scratchpad", description: "Transient reasoning, local transforms." },
  { id: 2, label: "Tier 2 · Episodic", description: "Per-session memory and narrative state." },
  { id: 3, label: "Tier 3 · Persistent", description: "Long-lived structures and registries." },
  { id: 4, label: "Tier 4 · Permanent", description: "Schemas, policies, invariants." }
];

function randomPastel(): string {
  const hue = Math.floor(Math.random() * 360);
  return `hsl(${hue}, 70%, 70%)`;
}

function createId(prefix: string = "id"): string {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
}

const INITIAL_AGENTS: MaxeyAgent[] = [
  {
    id: "maxey00",
    name: "Maxey00 · Superposition",
    role: "Latent mapping, superposition, interpretability hub.",
    tier: 0,
    notes: "Anchors SCWs, triangulates agents, and observes flows.",
    color: randomPastel()
  },
  {
    id: "maxey10",
    name: "Maxey10 · SCW Orchestrator",
    role: "Builds and manages Structured Context Windows.",
    tier: 1,
    notes: "Spawns and configures SCWs for specific tasks.",
    color: randomPastel()
  },
  {
    id: "maxey200",
    name: "Maxey200 · Memory Router",
    role: "Routes signals across scratchpad, episodic, persistent, permanent.",
    tier: 2,
    notes: "Applies promotion/demotion policies and gating.",
    color: randomPastel()
  },
  {
    id: "maxey350",
    name: "Maxey350 · Neo4j Bridge",
    role: "Bridges Maxey0 to graph DBs.",
    tier: 3,
    notes: "Maintains property graph views of agents and flows.",
    color: randomPastel()
  },
  {
    id: "maxey600",
    name: "Maxey600 · Observability",
    role: "Traces workflows and generates visualizations.",
    tier: 3,
    notes: "Produces spans, timelines, and usage overlays.",
    color: randomPastel()
  }
];

const INITIAL_WORKFLOWS: MaxeyWorkflow[] = [
  {
    id: "wf_scw_build",
    name: "SCW Build & Run",
    purpose: "Build a Structured Context Window, route a task through Maxey agents, and materialize results.",
    entryPoint: "User prompt → SCW0 gateway",
    steps: [
      {
        id: createId("step"),
        agentId: "maxey00",
        label: "Superposition mapping",
        stage: "Latent triangulation of task and available agents."
      },
      {
        id: createId("step"),
        agentId: "maxey10",
        label: "SCW instantiation",
        stage: "Create and parameterize a SCW for the task."
      },
      {
        id: createId("step"),
        agentId: "maxey200",
        label: "Memory routing",
        stage: "Configure memory tier promotions and filters."
      },
      {
        id: createId("step"),
        agentId: "maxey600",
        label: "Trace and visualize",
        stage: "Emit spans and a final workflow visualization."
      }
    ]
  }
];

export default function App() {
  const [agents, setAgents] = useState<MaxeyAgent[]>(INITIAL_AGENTS);
  const [workflows, setWorkflows] = useState<MaxeyWorkflow[]>(INITIAL_WORKFLOWS);
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string | null>(
    INITIAL_WORKFLOWS[0]?.id ?? null
  );

  const [newAgentName, setNewAgentName] = useState("");
  const [newAgentRole, setNewAgentRole] = useState("");
  const [newAgentTier, setNewAgentTier] = useState<TierId>(1);
  const [newAgentNotes, setNewAgentNotes] = useState("");

  const [newWorkflowName, setNewWorkflowName] = useState("");
  const [newWorkflowPurpose, setNewWorkflowPurpose] = useState("");
  const [newWorkflowEntry, setNewWorkflowEntry] = useState("");

  const [selectedAgentForStep, setSelectedAgentForStep] = useState<string>("");
  const [newStepLabel, setNewStepLabel] = useState("");
  const [newStepStage, setNewStepStage] = useState("");

  const selectedWorkflow = workflows.find((wf) => wf.id === selectedWorkflowId) ?? null;

  function addAgent() {
    const name = newAgentName.trim();
    const role = newAgentRole.trim();
    const notes = newAgentNotes.trim();
    if (!name || !role) return;

    const newAgent: MaxeyAgent = {
      id: createId("maxey"),
      name,
      role,
      tier: newAgentTier,
      notes,
      color: randomPastel()
    };

    setAgents((prev) => [...prev, newAgent]);
    setNewAgentName("");
    setNewAgentRole("");
    setNewAgentNotes("");
    setNewAgentTier(1);
  }

  function addWorkflow() {
    const name = newWorkflowName.trim();
    const purpose = newWorkflowPurpose.trim();
    const entry = newWorkflowEntry.trim();
    if (!name) return;

    const wf: MaxeyWorkflow = {
      id: createId("wf"),
      name,
      purpose: purpose || "No explicit purpose provided.",
      entryPoint: entry || "User input → SCW gateway",
      steps: []
    };

    setWorkflows((prev) => [...prev, wf]);
    setSelectedWorkflowId(wf.id);
    setNewWorkflowName("");
    setNewWorkflowPurpose("");
    setNewWorkflowEntry("");
  }

  function addStepToWorkflow() {
    if (!selectedWorkflow) return;
    const agentId = selectedAgentForStep || agents[0]?.id;
    if (!agentId) return;

    const label = newStepLabel.trim() || "Unnamed step";
    const stage = newStepStage.trim() || "No description provided.";

    const step: WorkflowStep = {
      id: createId("step"),
      agentId,
      label,
      stage
    };

    setWorkflows((prev) =>
      prev.map((wf) =>
        wf.id === selectedWorkflow.id
          ? { ...wf, steps: [...wf.steps, step] }
          : wf
      )
    );

    setSelectedAgentForStep("");
    setNewStepLabel("");
    setNewStepStage("");
  }

  function removeStep(workflowId: string, stepId: string) {
    setWorkflows((prev) =>
      prev.map((wf) =>
        wf.id === workflowId
          ? { ...wf, steps: wf.steps.filter((s) => s.id !== stepId) }
          : wf
      )
    );
  }

  function tierForAgent(agentId: string): TierId | null {
    const agent = agents.find((a) => a.id === agentId);
    return agent ? agent.tier : null;
  }

  function agentById(agentId: string): MaxeyAgent | undefined {
    return agents.find((a) => a.id === agentId);
  }

  const architectureJson = JSON.stringify(
    {
      agents: agents.map((a) => ({
        id: a.id,
        name: a.name,
        role: a.role,
        tier: a.tier,
        notes: a.notes
      })),
      workflows: workflows.map((wf) => ({
        id: wf.id,
        name: wf.name,
        purpose: wf.purpose,
        entryPoint: wf.entryPoint,
        steps: wf.steps.map((s) => ({
          id: s.id,
          agentId: s.agentId,
          label: s.label,
          stage: s.stage
        }))
      }))
    },
    null,
    2
  );

  return (
    <div
      style={{
        fontFamily:
          "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
        minHeight: "100vh",
        padding: "1.5rem",
        background:
          "radial-gradient(circle at top, #020617 0%, #020617 40%, #000000 100%)",
        color: "#e5e7eb",
        boxSizing: "border-box"
      }}
    >
      <div
        style={{
          maxWidth: "1240px",
          margin: "0 auto",
          display: "grid",
          gridTemplateColumns: "minmax(0, 1.1fr) minmax(0, 1.1fr) minmax(0, 1.1fr)",
          gap: "1rem",
          alignItems: "stretch"
        }}
      >
        <header
          style={{
            gridColumn: "1 / -1",
            marginBottom: "0.75rem",
            display: "flex",
            flexWrap: "wrap",
            justifyContent: "space-between",
            gap: "0.5rem"
          }}
        >
          <div>
            <h1
              style={{
                margin: 0,
                fontSize: "1.35rem",
                fontWeight: 600
              }}
            >
              Maxey0 Architecture & Workflow Studio
            </h1>
            <p
              style={{
                margin: "0.25rem 0 0",
                fontSize: "0.85rem",
                color: "#9ca3af",
                maxWidth: "780px"
              }}
            >
              Define Maxey agents, assign them to memory tiers, compose workflows, and
              see how tasks flow through the architecture.
            </p>
          </div>
          <div
            style={{
              textAlign: "right",
              fontSize: "0.8rem",
              color: "#94a3b8"
            }}
          >
            <div>SCW: Maxey0 · Architecture</div>
            <div>Mode: Design & Visualization</div>
          </div>
        </header>

        {/* Column 1: Agent & Tier Builder */}
        <section
          style={{
            borderRadius: "0.9rem",
            border: "1px solid #1f2937",
            background: "rgba(15,23,42,0.96)",
            padding: "1rem",
            boxShadow: "0 18px 45px rgba(0,0,0,0.7)",
            display: "flex",
            flexDirection: "column",
            minHeight: "480px"
          }}
        >
          <h2
            style={{
              fontSize: "0.95rem",
              margin: 0,
              marginBottom: "0.5rem"
            }}
          >
            Agents & Memory Tiers
          </h2>
          <p
            style={{
              margin: "0 0 0.75rem",
              fontSize: "0.78rem",
              color: "#9ca3af"
            }}
          >
            Register Maxey agents, place them into tiers, and annotate their roles.
          </p>

          <div
            style={{
              marginBottom: "0.75rem",
              padding: "0.75rem",
              borderRadius: "0.75rem",
              border: "1px solid #1f2937",
              background: "#020617"
            }}
          >
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: "0.5rem",
                marginBottom: "0.5rem"
              }}
            >
              <div style={{ flex: "1 1 160px" }}>
                <label
                  style={{
                    fontSize: "0.7rem",
                    textTransform: "uppercase",
                    letterSpacing: "0.06em",
                    color: "#9ca3af",
                    display: "block",
                    marginBottom: "0.2rem"
                  }}
                >
                  Agent Name
                </label>
                <input
                  type="text"
                  value={newAgentName}
                  onChange={(e) => setNewAgentName(e.target.value)}
                  placeholder="Maxey123 · Role"
                  style={{
                    width: "100%",
                    borderRadius: "0.6rem",
                    border: "1px solid #111827",
                    background: "#020617",
                    color: "#e5e7eb",
                    padding: "0.4rem 0.6rem",
                    fontSize: "0.8rem"
                  }}
                />
              </div>

              <div style={{ flex: "1 1 160px" }}>
                <label
                  style={{
                    fontSize: "0.7rem",
                    textTransform: "uppercase",
                    letterSpacing: "0.06em",
                    color: "#9ca3af",
                    display: "block",
                    marginBottom: "0.2rem"
                  }}
                >
                  Role
                </label>
                <input
                  type="text"
                  value={newAgentRole}
                  onChange={(e) => setNewAgentRole(e.target.value)}
                  placeholder="What does this agent do?"
                  style={{
                    width: "100%",
                    borderRadius: "0.6rem",
                    border: "1px solid #111827",
                    background: "#020617",
                    color: "#e5e7eb",
                    padding: "0.4rem 0.6rem",
                    fontSize: "0.8rem"
                  }}
                />
              </div>
            </div>

            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: "0.5rem",
                marginBottom: "0.5rem"
              }}
            >
              <div style={{ flex: "0 0 130px" }}>
                <label
                  style={{
                    fontSize: "0.7rem",
                    textTransform: "uppercase",
                    letterSpacing: "0.06em",
                    color: "#9ca3af",
                    display: "block",
                    marginBottom: "0.2rem"
                  }}
                >
                  Tier
                </label>
                <select
                  value={newAgentTier}
                  onChange={(e) =>
                    setNewAgentTier(Number(e.target.value) as TierId)
                  }
                  style={{
                    width: "100%",
                    borderRadius: "0.6rem",
                    border: "1px solid #111827",
                    background: "#020617",
                    color: "#e5e7eb",
                    padding: "0.4rem 0.5rem",
                    fontSize: "0.8rem"
                  }}
                >
                  {TIERS.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.label}
                    </option>
                  ))}
                </select>
              </div>

              <div style={{ flex: "1 1 180px" }}>
                <label
                  style={{
                    fontSize: "0.7rem",
                    textTransform: "uppercase",
                    letterSpacing: "0.06em",
                    color: "#9ca3af",
                    display: "block",
                    marginBottom: "0.2rem"
                  }}
                >
                  Notes
                </label>
                <input
                  type="text"
                  value={newAgentNotes}
                  onChange={(e) => setNewAgentNotes(e.target.value)}
                  placeholder="Gates memory, observes traces, etc."
                  style={{
                    width: "100%",
                    borderRadius: "0.6rem",
                    border: "1px solid #111827",
                    background: "#020617",
                    color: "#e5e7eb",
                    padding: "0.4rem 0.6rem",
                    fontSize: "0.8rem"
                  }}
                />
              </div>
            </div>

            <div style={{ textAlign: "right" }}>
              <button
                type="button"
                onClick={addAgent}
                style={{
                  borderRadius: "999px",
                  border: "1px solid #22c55e",
                  background:
                    "radial-gradient(circle at top left, #22c55e, #16a34a)",
                  color: "#020617",
                  fontSize: "0.8rem",
                  fontWeight: 600,
                  padding: "0.35rem 0.9rem",
                  cursor: "pointer",
                  boxShadow: "0 10px 22px rgba(34,197,94,0.25)"
                }}
              >
                Add Agent
              </button>
            </div>
          </div>

          <div
            style={{
              flex: 1,
              overflow: "auto",
              marginTop: "0.25rem",
              paddingRight: "0.25rem"
            }}
          >
            {TIERS.map((tier) => {
              const tierAgents = agents.filter((a) => a.tier === tier.id);
              return (
                <div
                  key={tier.id}
                  style={{
                    marginBottom: "0.6rem",
                    paddingBottom: "0.45rem",
                    borderBottom: "1px solid #111827"
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      marginBottom: "0.25rem"
                    }}
                  >
                    <div>
                      <div
                        style={{
                          fontSize: "0.8rem",
                          fontWeight: 600
                        }}
                      >
                        {tier.label}
                      </div>
                      <div
                        style={{
                          fontSize: "0.7rem",
                          color: "#9ca3af"
                        }}
                      >
                        {tier.description}
                      </div>
                    </div>
                    <div
                      style={{
                        fontSize: "0.7rem",
                        color: "#6b7280"
                      }}
                    >
                      {tierAgents.length} agent
                      {tierAgents.length === 1 ? "" : "s"}
                    </div>
                  </div>
                  {tierAgents.length === 0 ? (
                    <div
                      style={{
                        fontSize: "0.75rem",
                        color: "#4b5563",
                        fontStyle: "italic"
                      }}
                    >
                      No agents registered in this tier yet.
                    </div>
                  ) : (
                    <div
                      style={{
                        display: "flex",
                        flexWrap: "wrap",
                        gap: "0.35rem"
                      }}
                    >
                      {tierAgents.map((agent) => (
                        <div
                          key={agent.id}
                          style={{
                            borderRadius: "0.7rem",
                            border: "1px solid #111827",
                            background:
                              "linear-gradient(135deg, rgba(15,23,42,0.9), #020617)",
                            padding: "0.35rem 0.5rem",
                            fontSize: "0.72rem",
                            minWidth: "0",
                            display: "flex",
                            flexDirection: "column",
                            gap: "0.1rem"
                          }}
                        >
                          <div
                            style={{
                              display: "flex",
                              alignItems: "center",
                              gap: "0.35rem"
                            }}
                          >
                            <span
                              style={{
                                display: "inline-block",
                                width: "0.55rem",
                                height: "0.55rem",
                                borderRadius: "999px",
                                background: agent.color,
                                boxShadow: `0 0 0 1px rgba(15,23,42,0.8)`
                              }}
                            />
                            <span
                              style={{
                                fontWeight: 600,
                                whiteSpace: "nowrap"
                              }}
                            >
                              {agent.name}
                            </span>
                          </div>
                          <div
                            style={{
                              color: "#9ca3af",
                              lineHeight: 1.35
                            }}
                          >
                            {agent.role}
                          </div>
                          {agent.notes && (
                            <div
                              style={{
                                color: "#6b7280",
                                fontStyle: "italic"
                              }}
                            >
                              {agent.notes}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </section>

        {/* Column 2: Workflow Composer */}
        <section
          style={{
            borderRadius: "0.9rem",
            border: "1px solid #1f2937",
            background: "rgba(15,23,42,0.98)",
            padding: "1rem",
            boxShadow: "0 18px 45px rgba(0,0,0,0.7)",
            display: "flex",
            flexDirection: "column",
            minHeight: "480px"
          }}
        >
          <h2
            style={{
              fontSize: "0.95rem",
              margin: 0,
              marginBottom: "0.5rem"
            }}
          >
            Workflow Designer
          </h2>
          <p
            style={{
              margin: "0 0 0.75rem",
              fontSize: "0.78rem",
              color: "#9ca3af"
            }}
          >
            Compose ordered steps across agents to describe how a Maxey0 task should run.
          </p>

          <div
            style={{
              marginBottom: "0.75rem",
              padding: "0.75rem",
              borderRadius: "0.75rem",
              border: "1px solid #1f2937",
              background: "#020617"
            }}
          >
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: "0.5rem",
                marginBottom: "0.5rem"
              }}
            >
              <div style={{ flex: "1 1 160px" }}>
                <label
                  style={{
                    fontSize: "0.7rem",
                    textTransform: "uppercase",
                    letterSpacing: "0.06em",
                    color: "#9ca3af",
                    display: "block",
                    marginBottom: "0.2rem"
                  }}
                >
                  Workflow Name
                </label>
                <input
                  type="text"
                  value={newWorkflowName}
                  onChange={(e) => setNewWorkflowName(e.target.value)}
                  placeholder="Maxey0 · Research Pipeline"
                  style={{
                    width: "100%",
                    borderRadius: "0.6rem",
                    border: "1px solid #111827",
                    background: "#020617",
                    color: "#e5e7eb",
                    padding: "0.4rem 0.6rem",
                    fontSize: "0.8rem"
                  }}
                />
              </div>

              <div style={{ flex: "1 1 160px" }}>
                <label
                  style={{
                    fontSize: "0.7rem",
                    textTransform: "uppercase",
                    letterSpacing: "0.06em",
                    color: "#9ca3af",
                    display: "block",
                    marginBottom: "0.2rem"
                  }}
                >
                  Purpose
                </label>
                <input
                  type="text"
                  value={newWorkflowPurpose}
                  onChange={(e) => setNewWorkflowPurpose(e.target.value)}
                  placeholder="Why does this workflow exist?"
                  style={{
                    width: "100%",
                    borderRadius: "0.6rem",
                    border: "1px solid #111827",
                    background: "#020617",
                    color: "#e5e7eb",
                    padding: "0.4rem 0.6rem",
                    fontSize: "0.8rem"
                  }}
                />
              </div>
            </div>

            <div
              style={{
                marginBottom: "0.5rem"
              }}
            >
              <label
                style={{
                  fontSize: "0.7rem",
                  textTransform: "uppercase",
                  letterSpacing: "0.06em",
                  color: "#9ca3af",
                  display: "block",
                  marginBottom: "0.2rem"
                }}
              >
                Entry Point
              </label>
              <input
                type="text"
                value={newWorkflowEntry}
                onChange={(e) => setNewWorkflowEntry(e.target.value)}
                placeholder="User prompt → Maxey00 → SCW shell"
                style={{
                  width: "100%",
                  borderRadius: "0.6rem",
                  border: "1px solid #111827",
                  background: "#020617",
                  color: "#e5e7eb",
                  padding: "0.4rem 0.6rem",
                  fontSize: "0.8rem"
                }}
              />
            </div>

            <div style={{ textAlign: "right" }}>
              <button
                type="button"
                onClick={addWorkflow}
                style={{
                  borderRadius: "999px",
                  border: "1px solid #38bdf8",
                  background:
                    "radial-gradient(circle at top left, #38bdf8, #0ea5e9)",
                  color: "#020617",
                  fontSize: "0.8rem",
                  fontWeight: 600,
                  padding: "0.35rem 0.9rem",
                  cursor: "pointer",
                  boxShadow: "0 10px 22px rgba(56,189,248,0.25)"
                }}
              >
                Add Workflow
              </button>
            </div>
          </div>

          <div
            style={{
              marginBottom: "0.65rem",
              display: "flex",
              alignItems: "center",
              gap: "0.5rem"
            }}
          >
            <label
              style={{
                fontSize: "0.7rem",
                textTransform: "uppercase",
                letterSpacing: "0.06em",
                color: "#9ca3af"
              }}
            >
              Selected Workflow
            </label>
            <select
              value={selectedWorkflowId ?? ""}
              onChange={(e) =>
                setSelectedWorkflowId(e.target.value || null)
              }
              style={{
                flex: "1",
                borderRadius: "0.6rem",
                border: "1px solid #111827",
                background: "#020617",
                color: "#e5e7eb",
                padding: "0.4rem 0.5rem",
                fontSize: "0.8rem"
              }}
            >
              {workflows.map((wf) => (
                <option key={wf.id} value={wf.id}>
                  {wf.name}
                </option>
              ))}
            </select>
          </div>

          {selectedWorkflow ? (
            <>
              <div
                style={{
                  marginBottom: "0.6rem",
                  padding: "0.6rem 0.7rem",
                  borderRadius: "0.7rem",
                  border: "1px solid #111827",
                  background: "#020617"
                }}
              >
                <div
                  style={{
                    fontSize: "0.8rem",
                    fontWeight: 600,
                    marginBottom: "0.2rem"
                  }}
                >
                  {selectedWorkflow.name}
                </div>
                <div
                  style={{
                    fontSize: "0.76rem",
                    color: "#9ca3af",
                    marginBottom: "0.2rem"
                  }}
                >
                  {selectedWorkflow.purpose}
                </div>
                <div
                  style={{
                    fontSize: "0.74rem",
                    color: "#6b7280"
                  }}
                >
                  Entry: {selectedWorkflow.entryPoint}
                </div>
              </div>

              <div
                style={{
                  marginBottom: "0.6rem",
                  padding: "0.7rem",
                  borderRadius: "0.7rem",
                  border: "1px solid #111827",
                  background: "#020617"
                }}
              >
                <div
                  style={{
                    display: "flex",
                    flexWrap: "wrap",
                    gap: "0.5rem",
                    marginBottom: "0.5rem"
                  }}
                >
                  <div style={{ flex: "1 1 140px" }}>
                    <label
                      style={{
                        fontSize: "0.7rem",
                        textTransform: "uppercase",
                        letterSpacing: "0.06em",
                        color: "#9ca3af",
                        display: "block",
                        marginBottom: "0.2rem"
                      }}
                    >
                      Agent
                    </label>
                    <select
                      value={selectedAgentForStep}
                      onChange={(e) =>
                        setSelectedAgentForStep(e.target.value)
                      }
                      style={{
                        width: "100%",
                        borderRadius: "0.6rem",
                        border: "1px solid #111827",
                        background: "#020617",
                        color: "#e5e7eb",
                        padding: "0.4rem 0.5rem",
                        fontSize: "0.8rem"
                      }}
                    >
                      <option value="">
                        {agents.length === 0
                          ? "No agents defined"
                          : "Choose agent"}
                      </option>
                      {agents.map((a) => (
                        <option key={a.id} value={a.id}>
                          {a.name}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div style={{ flex: "1 1 140px" }}>
                    <label
                      style={{
                        fontSize: "0.7rem",
                        textTransform: "uppercase",
                        letterSpacing: "0.06em",
                        color: "#9ca3af",
                        display: "block",
                        marginBottom: "0.2rem"
                      }}
                    >
                      Step Label
                    </label>
                    <input
                      type="text"
                      value={newStepLabel}
                      onChange={(e) => setNewStepLabel(e.target.value)}
                      placeholder="What happens here?"
                      style={{
                        width: "100%",
                        borderRadius: "0.6rem",
                        border: "1px solid #111827",
                        background: "#020617",
                        color: "#e5e7eb",
                        padding: "0.4rem 0.6rem",
                        fontSize: "0.8rem"
                      }}
                    />
                  </div>
                </div>

                <div
                  style={{
                    marginBottom: "0.5rem"
                  }}
                >
                  <label
                    style={{
                      fontSize: "0.7rem",
                      textTransform: "uppercase",
                      letterSpacing: "0.06em",
                      color: "#9ca3af",
                      display: "block",
                      marginBottom: "0.2rem"
                    }}
                  >
                    Stage Description
                  </label>
                  <input
                    type="text"
                    value={newStepStage}
                    onChange={(e) => setNewStepStage(e.target.value)}
                    placeholder="Explain what this step does in the workflow."
                    style={{
                      width: "100%",
                      borderRadius: "0.6rem",
                      border: "1px solid #111827",
                      background: "#020617",
                      color: "#e5e7eb",
                      padding: "0.4rem 0.6rem",
                      fontSize: "0.8rem"
                    }}
                  />
                </div>

                <div style={{ textAlign: "right" }}>
                  <button
                    type="button"
                    onClick={addStepToWorkflow}
                    style={{
                      borderRadius: "999px",
                      border: "1px solid #a855f7",
                      background:
                        "radial-gradient(circle at top left, #a855f7, #8b5cf6)",
                      color: "#020617",
                      fontSize: "0.8rem",
                      fontWeight: 600,
                      padding: "0.35rem 0.9rem",
                      cursor: "pointer",
                      boxShadow: "0 10px 22px rgba(168,85,247,0.3)"
                    }}
                  >
                    Add Step
                  </button>
                </div>
              </div>

              <div
                style={{
                  flex: 1,
                  overflow: "auto",
                  paddingRight: "0.25rem"
                }}
              >
                {selectedWorkflow.steps.length === 0 ? (
                  <div
                    style={{
                      fontSize: "0.75rem",
                      color: "#4b5563",
                      fontStyle: "italic"
                    }}
                  >
                    No steps yet. Add steps to see the workflow path.
                  </div>
                ) : (
                  <ol
                    style={{
                      margin: 0,
                      paddingLeft: "1.1rem",
                      display: "flex",
                      flexDirection: "column",
                      gap: "0.4rem",
                      fontSize: "0.78rem"
                    }}
                  >
                    {selectedWorkflow.steps.map((step, index) => {
                      const agent = agentById(step.agentId);
                      return (
                        <li
                          key={step.id}
                          style={{
                            borderRadius: "0.55rem",
                            border: "1px solid #111827",
                            background:
                              "linear-gradient(135deg, rgba(15,23,42,0.96), #020617)",
                            padding: "0.4rem 0.55rem",
                            display: "flex",
                            flexDirection: "column",
                            gap: "0.15rem",
                            position: "relative"
                          }}
                        >
                          <div
                            style={{
                              display: "flex",
                              justifyContent: "space-between",
                              alignItems: "center",
                              gap: "0.35rem"
                            }}
                          >
                            <div
                              style={{
                                display: "flex",
                                alignItems: "center",
                                gap: "0.35rem"
                              }}
                            >
                              <span
                                style={{
                                  display: "inline-block",
                                  minWidth: "1.2rem",
                                  textAlign: "center",
                                  borderRadius: "999px",
                                  background: "#020617",
                                  border: "1px solid #1f2937",
                                  fontSize: "0.7rem",
                                  color: "#9ca3af"
                                }}
                              >
                                {index + 1}
                              </span>
                              {agent && (
                                <span
                                  style={{
                                    display: "inline-flex",
                                    alignItems: "center",
                                    gap: "0.25rem"
                                  }}
                                >
                                  <span
                                    style={{
                                      width: "0.55rem",
                                      height: "0.55rem",
                                      borderRadius: "999px",
                                      background: agent.color,
                                      boxShadow:
                                        "0 0 0 1px rgba(15,23,42,0.9)"
                                    }}
                                  />
                                  <span
                                    style={{
                                      fontWeight: 600
                                    }}
                                  >
                                    {agent.name}
                                  </span>
                                </span>
                              )}
                            </div>
                            <button
                              type="button"
                              onClick={() =>
                                removeStep(selectedWorkflow.id, step.id)
                              }
                              style={{
                                border: "none",
                                background: "transparent",
                                color: "#6b7280",
                                fontSize: "0.75rem",
                                cursor: "pointer"
                              }}
                            >
                              ✕
                            </button>
                          </div>
                          <div
                            style={{
                              color: "#e5e7eb",
                              fontWeight: 500
                            }}
                          >
                            {step.label}
                          </div>
                          <div
                            style={{
                              color: "#9ca3af"
                            }}
                          >
                            {step.stage}
                          </div>
                        </li>
                      );
                    })}
                  </ol>
                )}
              </div>
            </>
          ) : (
            <div
              style={{
                fontSize: "0.78rem",
                color: "#4b5563",
                fontStyle: "italic",
                marginTop: "0.5rem"
              }}
            >
              Create or select a workflow to design its path.
            </div>
          )}
        </section>

        {/* Column 3: Visualization & JSON */}
        <section
          style={{
            borderRadius: "0.9rem",
            border: "1px solid #1f2937",
            background: "rgba(15,23,42,0.98)",
            padding: "1rem",
            boxShadow: "0 18px 45px rgba(0,0,0,0.7)",
            display: "flex",
            flexDirection: "column",
            minHeight: "480px"
          }}
        >
          <h2
            style={{
              fontSize: "0.95rem",
              margin: 0,
              marginBottom: "0.5rem"
            }}
          >
            Flow Visualization & Export
          </h2>
          <p
            style={{
              margin: "0 0 0.75rem",
              fontSize: "0.78rem",
              color: "#9ca3af"
            }}
          >
            See how workflows traverse tiers, and export the architecture as JSON.
          </p>

          <div
            style={{
              marginBottom: "0.75rem",
              padding: "0.7rem",
              borderRadius: "0.7rem",
              border: "1px solid #111827",
              background: "#020617",
              maxHeight: "220px",
              overflow: "auto"
            }}
          >
            <div
              style={{
                fontSize: "0.8rem",
                fontWeight: 600,
                marginBottom: "0.35rem"
              }}
            >
              Tier Swimlanes
            </div>
            {TIERS.map((tier) => {
              const tierAgentIds = agents
                .filter((a) => a.tier === tier.id)
                .map((a) => a.id);
              const tierWorkflowSteps =
                selectedWorkflow?.steps.filter((s) =>
                  tierAgentIds.includes(s.agentId)
                ) ?? [];
              const hasAgents = tierAgentIds.length > 0;
              const isActive = tierWorkflowSteps.length > 0;

              return (
                <div
                  key={tier.id}
                  style={{
                    marginBottom: "0.45rem",
                    padding: "0.4rem 0.45rem",
                    borderRadius: "0.6rem",
                    border: `1px solid ${
                      isActive ? "#22c55e" : "#111827"
                    }`,
                    background: isActive
                      ? "linear-gradient(90deg, rgba(34,197,94,0.12), #020617)"
                      : "#020617"
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: "0.4rem",
                      marginBottom: "0.25rem"
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "0.35rem"
                      }}
                    >
                      <span
                        style={{
                          width: "0.55rem",
                          height: "0.55rem",
                          borderRadius: "999px",
                          background: isActive ? "#22c55e" : "#4b5563"
                        }}
                      />
                      <span
                        style={{
                          fontSize: "0.78rem",
                          fontWeight: 600
                        }}
                      >
                        {tier.label}
                      </span>
                    </div>
                    <div
                      style={{
                        fontSize: "0.7rem",
                        color: "#6b7280"
                      }}
                    >
                      {hasAgents ? `${tierAgentIds.length} agents` : "No agents"}
                    </div>
                  </div>
                  {hasAgents ? (
                    <div
                      style={{
                        fontSize: "0.75rem",
                        color: "#9ca3af"
                      }}
                    >
                      {tierWorkflowSteps.length > 0 ? (
                        <span>
                          Active in workflow at step
                          {tierWorkflowSteps.length > 1 ? "s " : " "}
                          {tierWorkflowSteps
                            .map((s) =>
                              selectedWorkflow
                                ? selectedWorkflow.steps.indexOf(s) + 1
                                : "?"
                            )
                            .join(", ")}
                          .
                        </span>
                      ) : (
                        <span>Not used in the selected workflow yet.</span>
                      )}
                    </div>
                  ) : (
                    <div
                      style={{
                        fontSize: "0.75rem",
                        color: "#4b5563"
                      }}
                    >
                      No agents in this tier.
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <div
            style={{
              flex: 1,
              borderRadius: "0.7rem",
              border: "1px solid #111827",
              background: "#020617",
              padding: "0.7rem",
              display: "flex",
              flexDirection: "column",
              overflow: "hidden"
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                gap: "0.5rem",
                marginBottom: "0.4rem"
              }}
            >
              <div
                style={{
                  fontSize: "0.8rem",
                  fontWeight: 600
                }}
              >
                Architecture JSON
              </div>
              <button
                type="button"
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(architectureJson);
                    alert("Architecture JSON copied to clipboard.");
                  } catch {
                    alert(
                      "Could not copy JSON automatically. Please select and copy manually."
                    );
                  }
                }}
                style={{
                  borderRadius: "999px",
                  border: "1px solid #4b5563",
                  background: "rgba(15,23,42,0.9)",
                  color: "#e5e7eb",
                  fontSize: "0.78rem",
                  padding: "0.3rem 0.7rem",
                  cursor: "pointer"
                }}
              >
                Copy JSON
              </button>
            </div>
            <div
              style={{
                flex: 1,
                overflow: "auto",
                borderRadius: "0.5rem",
                border: "1px solid #111827",
                background: "#020617"
              }}
            >
              <pre
                style={{
                  margin: 0,
                  padding: "0.5rem",
                  fontSize: "0.75rem",
                  lineHeight: 1.45,
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                  fontFamily:
                    "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
                  color: "#e5e7eb"
                }}
              >
                {architectureJson}
              </pre>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
