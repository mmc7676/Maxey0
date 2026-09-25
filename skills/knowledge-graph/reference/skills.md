# Knowledge Graph — skills

The 9 skill(s) this concept owns, from the Maxey0 manifest. Each names the agent formation already bound to it: a `primary` that produces, a `checker` that verifies, and `support` roles around them.

That formation is why routing beats improvising. A pre-scoped formation for the matched skill is almost always cheaper and better targeted than a hand-written maker/checker pair.

## `knowledge-graph-engineering`

**Knowledge Graph Engineering**

Maintains the OKF-serialized graph through diffable document edits, integrity verification, alias normalization, and structure-informed routing.

memory tier: `semantic` · tags: `graph`, `okf`, `link`, `frontmatter`, `serialize`

| agent | role |
|---|---|
| Seed Agent Graph Agent | `primary` |
| QA Agent | `checker` |
| Graph GNN Router | `support` |
| Neighborhood Graph Builder | `support` |

## `property-graph-memory-engineering`

**Property Graph Memory Engineering**

Engineers property graph representations for agent memory: node schemas, edge semantics, and traversal patterns.

memory tier: `semantic` · tags: `property-graph`, `schema`, `node`, `edge`, `traversal`

| agent | role |
|---|---|
| Seed Agent Graph Agent | `primary` |
| QA Agent | `checker` |
| Graph Store Agent | `support` |
| Graph GNN Router | `support` |

## `graph-memory-construction`

**Graph Memory Construction**

Constructs graph memories from raw agent outputs: entity extraction, relationship inference, and deduplication.

memory tier: `semantic` · tags: `graph`, `construction`, `extraction`, `entity`, `dedup`

| agent | role |
|---|---|
| Graph GNN Router | `primary` |
| QA Agent | `checker` |
| Seed Agent Graph Agent | `support` |
| Provenance Logger | `support` |

## `graph-neural-network-routing`

**Graph Neural Network Routing**

Routes agent selection and skill matching using GNN features over the knowledge graph: neighborhood density, hub centrality, path distance.

memory tier: `semantic` · tags: `gnn`, `routing`, `centrality`, `neighborhood`, `hub`

| agent | role |
|---|---|
| Latent GNN Router | `primary` |
| QA Agent | `checker` |
| Graph GNN Router | `support` |
| Neighborhood Graph Builder | `support` |

## `temporal-knowledge-graph-management`

**Temporal Knowledge Graph Management**

Manages time-stamped knowledge graph evolution: versioned edges, temporal queries, and change-event propagation.

memory tier: `semantic` · tags: `temporal`, `versioned`, `evolution`, `time-stamp`, `change`

| agent | role |
|---|---|
| Graph GNN Router | `primary` |
| QA Agent | `checker` |
| Temporal Drift Agent | `support` |
| Seed Agent Graph Agent | `support` |

## `memory-graph-evolution`

**Memory Graph Evolution**

Engineers how the knowledge graph grows and prunes over time: addition protocols, deprecation, and garbage collection.

memory tier: `semantic` · tags: `evolution`, `growth`, `pruning`, `deprecation`, `lifecycle`

| agent | role |
|---|---|
| Graph GNN Router | `primary` |
| Promotion Policy Agent | `checker` |
| QA Agent | `support` |
| Seed Agent Graph Agent | `support` |

## `hybrid-vector-graph-memory`

**Hybrid Vector-Graph Memory**

Combines vector search (fast approximate retrieval) with graph traversal (exact relational queries) into a unified memory access layer.

memory tier: `semantic` · tags: `hybrid`, `vector`, `graph`, `retrieval`, `combined`

| agent | role |
|---|---|
| Vector Store Agent | `primary` |
| QA Agent | `checker` |
| Seed Agent Graph Agent | `support` |
| Neighborhood Graph Builder | `support` |

## `research-paper-integration`

**Research Paper Integration**

Integrates a new research paper into the bundle: extract concepts, derive skills, map registry agents or propose new ones, enumerate operational topics, and materialize an application — the pipeline that produced this skill's examples/.

memory tier: `semantic` · tags: `paper`, `integration`, `ingest`, `extract`, `topics`

| agent | role |
|---|---|
| Seed Agent Graph Agent | `primary` |
| QA Agent | `checker` |
| Superposition Agent | `support` |
| Temporal Drift Agent | `support` |

## `knowledge-graph-federation`

**Knowledge Graph Federation**

Owns OKF-to-external-KG interoperability: node/edge/property mapping contracts, sync direction, and the MCP host/client bridge pattern with Claude as host holding 1:N connections.

memory tier: `semantic` · tags: `graph`, `federation`, `interop`, `mcp`, `host`, `client`, `mapping`, `neo4j`, `sparql`

| agent | role |
|---|---|
| MCP Bridge | `primary` |
| QA Agent | `checker` |
| Graph Store Agent | `support` |
| Retrieval Orchestrator | `support` |
