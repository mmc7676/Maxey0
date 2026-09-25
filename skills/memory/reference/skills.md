# Memory — skills

The 8 skill(s) this concept owns, from the Maxey0 manifest. Each names the agent formation already bound to it: a `primary` that produces, a `checker` that verifies, and `support` roles around them.

That formation is why routing beats improvising. A pre-scoped formation for the matched skill is almost always cheaper and better targeted than a hand-written maker/checker pair.

## `multi-tier-memory-management`

**Multi-Tier Memory Management**

Classifies, stores, summarizes, and promotes memory items across the five tiers through typed API contracts with evidence-gated promotion.

memory tier: `semantic` · tags: `memory`, `tier`, `promotion`, `classify`, `api`

| agent | role |
|---|---|
| Memory Manager | `primary` |
| Promotion Policy Agent | `checker` |
| Working Memory Manager | `support` |
| Memory API Keeper | `support` |

## `episodic-memory-engineering`

**Episodic Memory Engineering**

Engineers the episodic tier: turn chains, session summaries, handoff state, and drift snapshots — all resumable, time-stamped, and summarized at session close.

memory tier: `episodic` · tags: `episodic`, `session`, `turn`, `summary`, `handoff`, `drift`

| agent | role |
|---|---|
| Conversation Importer Agent | `primary` |
| Promotion Policy Agent | `checker` |
| Conversation Store Agent | `support` |
| Session Store Manager | `support` |

## `working-memory-management`

**Working Memory Management**

Manages the working (scratchpad) tier: volatile in-flight state, TTL enforcement, and guaranteed purge at session close.

memory tier: `working` · tags: `working`, `scratchpad`, `volatile`, `ttl`, `purge`, `transient`

| agent | role |
|---|---|
| Working Memory Manager | `primary` |
| Promotion Policy Agent | `checker` |
| Session Store Manager | `support` |
| Memory API Keeper | `support` |

## `semantic-memory-engineering`

**Semantic Memory Engineering**

Engineers the semantic tier — the OKF bundle itself: concept extraction, graph construction, alias normalization, and the promotion gate that admits items from episodic.

memory tier: `semantic` · tags: `semantic`, `concept`, `graph`, `extraction`, `alias`, `okf`

| agent | role |
|---|---|
| Seed Agent Graph Agent | `primary` |
| Promotion Policy Agent | `checker` |
| QA Agent | `support` |
| Graph GNN Router | `support` |

## `persistent-memory-management`

**Persistent Memory Management**

Manages the persistent tier: durable agent facts, versioned preferences, long-term observations — written rarely, always with a promotion evidence chain.

memory tier: `persistent` · tags: `persistent`, `durable`, `version`, `preference`, `long-term`

| agent | role |
|---|---|
| Database Architect | `primary` |
| Promotion Policy Agent | `checker` |
| Graph Store Agent | `support` |
| Vector Store Agent | `support` |

## `memory-promotion-policy-engineering`

**Memory Promotion Policy Engineering**

Designs and enforces the gates that move items between tiers: relevance, evidence, consistency, reuse, and policy checks — with quarantine and repair paths for failures.

memory tier: `episodic` · tags: `promotion`, `gate`, `policy`, `quarantine`, `repair`, `consolidation`

| agent | role |
|---|---|
| Promotion Policy Agent | `primary` |
| Compliance Auditor | `checker` |
| Provenance Signer | `support` |
| Provenance Logger | `support` |

## `memory-context-compress`

**Memory Context Compress — Memory Concept Extraction & Context Window Compression**

Compiles a session transcript or account memory surface into a normalized, deduplicated memory checkpoint and a token-budgeted resume packet, so a fresh context window continues the work without replaying raw history.

memory tier: `episodic` · tags: `checkpoint`, `extraction`, `compression`, `resume`, `session`, `context-window`, `provenance`, `dedup`, `memory`, `memconext`

| agent | role |
|---|---|
| Memory Manager | `primary` |
| Cost Guard | `checker` |
| Context Window Architect | `support` |
| Promotion Policy Agent | `support` |

## `procedural-memory-engineering`

**Procedural Memory Engineering**

Engineers the procedural tier - the skill bundles as memory: creation = memorization, revision = consolidation, deprecation = forgetting, git history = lineage.

memory tier: `procedural` · tags: `memory`, `procedural`, `skill-lifecycle`, `consolidation`, `deprecation`, `versioning`

| agent | role |
|---|---|
| Memory Manager | `primary` |
| QA Agent | `checker` |
| Promotion Policy Agent | `support` |
| Provenance Signer | `support` |
