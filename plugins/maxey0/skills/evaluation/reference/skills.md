# Evaluation — skills

The 4 skill(s) this concept owns, from the Maxey0 manifest. Each names the agent formation already bound to it: a `primary` that produces, a `checker` that verifies, and `support` roles around them.

That formation is why routing beats improvising. A pre-scoped formation for the matched skill is almost always cheaper and better targeted than a hand-written maker/checker pair.

## `agent-evaluation`

**Agent Evaluation**

Mirrors runs read-only to produce evidence-chained EvalReports and frame-labeled DriftSignals across reference frames A, B, and D.

memory tier: `episodic` · tags: `evaluate`, `score`, `drift`, `shadow`, `compare`

| agent | role |
|---|---|
| Superposition Agent | `primary` |
| Anchor Metrics | `checker` |
| Drift Detector | `support` |
| Temporal Drift Agent | `support` |

## `swarm-evaluation`

**Swarm Evaluation**

Evaluates swarm outputs: coverage, contradiction rate, and convergence quality across the collected set.

memory tier: `episodic` · tags: `swarm`, `coverage`, `contradiction`, `convergence`, `eval`

| agent | role |
|---|---|
| Superposition Agent | `primary` |
| Anchor Metrics | `checker` |
| Cost Guard | `support` |
| DR Coordinator | `support` |

## `enterprise-constitution-evaluation`

**Enterprise Constitution Evaluation**

Evaluates whether deployed agents conform to their declared constitutional constraints — live compliance scoring, not just design-time analysis.

memory tier: `persistent` · tags: `constitution`, `compliance`, `conformance`, `enterprise`, `live`

| agent | role |
|---|---|
| Superposition Agent | `primary` |
| Compliance Auditor | `checker` |
| Security Sentinel | `support` |
| Anchor Metrics | `support` |

## `retrieval-attribution-evaluation`

**Retrieval Attribution Evaluation**

Scores retrieval quality by tracing outputs back to their sources: did the system surface the right items, were they actually used, were attributions correct?

memory tier: `episodic` · tags: `retrieval`, `attribution`, `recall`, `precision`, `sourcing`

| agent | role |
|---|---|
| Superposition Agent | `primary` |
| Provenance Logger | `checker` |
| Provenance Querier | `support` |
| Anchor Metrics | `support` |
