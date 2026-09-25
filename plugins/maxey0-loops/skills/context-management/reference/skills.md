# Context Management — skills

The 5 skill(s) this concept owns, from the Maxey0 manifest. Each names the agent formation already bound to it: a `primary` that produces, a `checker` that verifies, and `support` roles around them.

That formation is why routing beats improvising. A pre-scoped formation for the matched skill is almost always cheaper and better targeted than a hand-written maker/checker pair.

## `structured-context-world-engineering`

**Structured Context World Engineering**

Designs and builds SCWs: schema-governed context packages with declared sections, budgets, and inclusion rationale. Primary mechanism for 75-85% per-turn token cost reduction by loading only task-relevant agents and knowledge.

memory tier: `working` · tags: `scw`, `schema`, `section`, `budget`, `token-cost`, `structured`

| agent | role |
|---|---|
| Context Window Architect | `primary` |
| QA Agent | `checker` |
| SCW ReasoningFrame Schema Agent | `support` |
| SCW Packing Schema Agent | `support` |

## `context-packing-optimization`

**Context Packing Optimization**

Optimizes what enters a context window against token budgets: selection, compression, ordering — every exclusion justified, every compression lossless for contract fields.

memory tier: `working` · tags: `packing`, `token-budget`, `compression`, `selection`, `ordering`

| agent | role |
|---|---|
| SCW Packing Schema Agent | `primary` |
| Cost Guard | `checker` |
| Context Window Architect | `support` |
| SCW ReasoningFrame Schema Agent | `support` |

## `context-lineage-tracking`

**Context Lineage Tracking**

Tracks where every context element came from: source, transformation chain, inclusion rationale — so any packed context can answer provenance queries element by element.

memory tier: `episodic` · tags: `lineage`, `provenance`, `element`, `inclusion`, `query`

| agent | role |
|---|---|
| Provenance Logger | `primary` |
| Compliance Auditor | `checker` |
| Provenance Querier | `support` |
| Provenance Signer | `support` |

## `context-persistence-engineering`

**Context Persistence Engineering**

Persists and restores context state across sessions: what survives session close, in which tier, and how restoration reconstructs a working context faithfully.

memory tier: `episodic` · tags: `persistence`, `session`, `restore`, `checkpoint`, `tier`

| agent | role |
|---|---|
| Working Memory Manager | `primary` |
| QA Agent | `checker` |
| Vector Store Agent | `support` |
| Artifact Store | `support` |

## `context-boundary-engineering`

**Context Boundary Engineering**

Engineers the boundaries between contexts: isolation between agents, scopes, and tenants; declared crossings only; leakage as a first-class failure.

memory tier: `working` · tags: `boundary`, `isolation`, `scope`, `tenant`, `leakage`

| agent | role |
|---|---|
| Context Boundary Warden | `primary` |
| Security Sentinel | `checker` |
| Policy Proxy | `support` |
| Working Memory Manager | `support` |
