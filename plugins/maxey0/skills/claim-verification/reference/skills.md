# Claim Verification — skills

The 4 skill(s) this concept owns, from the Maxey0 manifest. Each names the agent formation already bound to it: a `primary` that produces, a `checker` that verifies, and `support` roles around them.

That formation is why routing beats improvising. A pre-scoped formation for the matched skill is almost always cheaper and better targeted than a hand-written maker/checker pair.

## `claim-lineage-analysis`

**Claim Lineage Analysis**

Records signed generation-time provenance, classifies every claim by its support, and answers lineage queries end to end.

memory tier: `episodic` · tags: `claim`, `provenance`, `lineage`, `citation`, `evidence`

| agent | role |
|---|---|
| Provenance Logger | `primary` |
| Compliance Auditor | `checker` |
| Provenance Signer | `support` |
| Conversation Ingestor | `support` |

## `hallucination-localization`

**Hallucination Localization**

Localizes hallucinations to specific spans: which part of the output is unsupported, at what evidence level.

memory tier: `episodic` · tags: `hallucination`, `localization`, `span`, `unsupported`, `evidence`

| agent | role |
|---|---|
| Provenance Logger | `primary` |
| Compliance Auditor | `checker` |
| Provenance Querier | `support` |
| Provenance Signer | `support` |

## `hallucination-attribution`

**Hallucination Attribution**

Attributes hallucinations to their cause: retrieval failure, inference error, context gap, or compression loss.

memory tier: `episodic` · tags: `hallucination`, `attribution`, `cause`, `retrieval`, `inference`

| agent | role |
|---|---|
| Provenance Logger | `primary` |
| Compliance Auditor | `checker` |
| Provenance Querier | `support` |
| Conversation Ingestor | `support` |

## `reasoning-path-instrumentation`

**Reasoning Path Instrumentation**

Instruments the reasoning path: which steps led to which claims, so reasoning audits are replayable.

memory tier: `episodic` · tags: `reasoning`, `path`, `instrument`, `audit`, `replay`

| agent | role |
|---|---|
| Debugger Agent | `primary` |
| Provenance Logger | `checker` |
| OTel Collector Agent | `support` |
| Provenance Signer | `support` |
