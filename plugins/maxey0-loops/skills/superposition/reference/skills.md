# Superposition — skills

The 5 skill(s) this concept owns, from the Maxey0 manifest. Each names the agent formation already bound to it: a `primary` that produces, a `checker` that verifies, and `support` roles around them.

That formation is why routing beats improvising. A pre-scoped formation for the matched skill is almost always cheaper and better targeted than a hand-written maker/checker pair.

## `superposition-observation`

**Superposition Observation**

Maxey00's standing mirror: read-only shadow observation of every run, annotating quality, latency, cost, and drift without touching the observed workflow.

memory tier: `episodic` · tags: `mirror`, `shadow`, `observe`, `annotate`, `read-only`

| agent | role |
|---|---|
| Superposition Agent | `primary` |
| Anchor Metrics | `checker` |
| Drift Detector | `support` |
| Temporal Drift Agent | `support` |

## `same-tick-arbitration`

**Same-Tick Arbitration**

Receives outputs from two or more agents on the exact same logical tick and evaluates them against one shared state to test which output does X according to Y — real-time execution races, live integration checks, A/B at identical state.

memory tier: `episodic` · tags: `same-tick`, `arbitrate`, `a-b`, `race`, `shared-state`

| agent | role |
|---|---|
| Superposition Agent | `primary` |
| QA Agent | `checker` |
| Code Interpreter Agent | `support` |
| Cost Guard | `support` |

## `actor-critic-parallelism`

**Actor-Critic Parallelism**

Runs propose/critique agent pairs and symmetric mirror-mode parallels under an arbiter: one agent proposes, one critiques, promotion only through reconciliation.

memory tier: `episodic` · tags: `actor-critic`, `mirror-mode`, `propose`, `critique`, `arbiter`

| agent | role |
|---|---|
| SuperAgent Orchestrator | `primary` |
| Superposition Agent | `checker` |
| Agentic Runner Agent | `support` |
| QA Agent | `support` |

## `shared-state-synchronization`

**Shared-State Synchronization**

Engineers the tick discipline that makes agentic superposition real: parallel and multithreaded GPU execution such that compute ticks are shorter than latent state transitions, with barriers, warp-style consensus votes, and atomic promotion.

memory tier: `working` · tags: `tick`, `barrier`, `synchronize`, `warp`, `atomic`

| agent | role |
|---|---|
| Superposition Runtime Engineer | `primary` |
| Superposition Agent | `checker` |
| MCP Runner Agent | `support` |
| Code Interpreter Agent | `support` |

## `superposition-coordinate-mapping`

**Superposition Coordinate Mapping**

Logs, maps, and learns superposition coordinates from latent state transitions using state-vector-machine models, so simultaneous states become a navigable, learnable record.

memory tier: `semantic` · tags: `coordinate`, `state-vector`, `transition`, `map`, `learn`

| agent | role |
|---|---|
| State Vector Cartographer | `primary` |
| Anchor Metrics | `checker` |
| Magnitude Spectrum Mapper | `support` |
| Anchor Miner | `support` |
