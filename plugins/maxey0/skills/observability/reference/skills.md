# Observability — skills

The 4 skill(s) this concept owns, from the Maxey0 manifest. Each names the agent formation already bound to it: a `primary` that produces, a `checker` that verifies, and `support` roles around them.

That formation is why routing beats improvising. A pre-scoped formation for the matched skill is almost always cheaper and better targeted than a hand-written maker/checker pair.

## `ai-observability`

**AI Observability**

Instruments every boundary with spans under the a2a.* and maxey0.okf.* namespaces, assembles replayable trace trees, and diagnoses from them.

memory tier: `episodic` · tags: `trace`, `span`, `otel`, `telemetry`, `audit`

| agent | role |
|---|---|
| OTel Collector Agent | `primary` |
| Debugger Agent | `checker` |
| OTel Module Agent | `support` |
| Grafana Agent | `support` |

## `agent-trace-analysis`

**Agent Trace Analysis**

Consumes trace trees and produces causal diagnoses: failing paths, root causes, and minimal reproductions.

memory tier: `episodic` · tags: `trace`, `diagnosis`, `root-cause`, `analysis`, `replay`

| agent | role |
|---|---|
| Debugger Agent | `primary` |
| OTel Collector Agent | `checker` |
| OTel Module Agent | `support` |
| Grafana Agent | `support` |

## `memory-access-telemetry`

**Memory Access Telemetry**

Instruments tier reads and writes: access patterns, promotion events, and tier-crossing latencies — the data that makes memory policy auditable.

memory tier: `episodic` · tags: `memory`, `telemetry`, `access`, `pattern`, `tier`

| agent | role |
|---|---|
| OTel Collector Agent | `primary` |
| Promotion Policy Agent | `checker` |
| Debugger Agent | `support` |
| Provenance Logger | `support` |

## `context-utilization-analytics`

**Context Utilization Analytics**

Measures what entered a context window and how much of it was actually used: utilization ratios, dead-weight identification, and packing efficiency signals.

memory tier: `episodic` · tags: `context`, `utilization`, `analytics`, `efficiency`, `packing`

| agent | role |
|---|---|
| Debugger Agent | `primary` |
| OTel Collector Agent | `checker` |
| Context Window Architect | `support` |
| SCW Packing Schema Agent | `support` |
