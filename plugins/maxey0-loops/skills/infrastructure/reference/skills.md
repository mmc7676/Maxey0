# Infrastructure — skills

The 5 skill(s) this concept owns, from the Maxey0 manifest. Each names the agent formation already bound to it: a `primary` that produces, a `checker` that verifies, and `support` roles around them.

That formation is why routing beats improvising. A pre-scoped formation for the matched skill is almost always cheaper and better targeted than a hand-written maker/checker pair.

## `agent-runtime-engineering`

**Agent Runtime Engineering**

Executes agent code inside enforced resource and isolation contracts, priced by risk budget, with purge-on-completion state discipline.

memory tier: `working` · tags: `runtime`, `execute`, `sandbox`, `resource`, `limit`

| agent | role |
|---|---|
| Code Interpreter Agent | `primary` |
| Security Scanner | `checker` |
| Sandbox Runner | `support` |
| Backup & Restore | `support` |

## `agent-infrastructure-engineering`

**Agent Infrastructure Engineering**

Designs and provisions the infrastructure layer for agent deployments: compute, networking, secret management, and health monitoring.

memory tier: `working` · tags: `infrastructure`, `provision`, `networking`, `secret`, `health`

| agent | role |
|---|---|
| Code Interpreter Agent | `primary` |
| Security Scanner | `checker` |
| Integration Engineer | `support` |
| API Gateway Agent | `support` |

## `agent-platform-engineering`

**Agent Platform Engineering**

Builds the platform abstractions agents run on: scheduling, load balancing, autoscaling, and the observability integrations the platform provides.

memory tier: `working` · tags: `platform`, `schedule`, `autoscale`, `balancing`, `observability`

| agent | role |
|---|---|
| Code Interpreter Agent | `primary` |
| Security Scanner | `checker` |
| API Gateway Agent | `support` |
| Incident Commander | `support` |

## `multi-tenant-agent-infrastructure`

**Multi-Tenant Agent Infrastructure**

Provisions and isolates agent infrastructure across tenants: resource quotas, network separation, and tenant-scoped secret stores.

memory tier: `working` · tags: `tenant`, `isolation`, `quota`, `network-separation`, `provisioning`

| agent | role |
|---|---|
| Context Boundary Warden | `primary` |
| Security Scanner | `checker` |
| Code Interpreter Agent | `support` |
| Security Sentinel | `support` |

## `distributed-agent-runtime-engineering`

**Distributed Agent Runtime Engineering**

Operates agent runtimes across distributed compute: work distribution, fault tolerance, state coherence, and split-brain prevention.

memory tier: `working` · tags: `distributed`, `fault-tolerance`, `coherence`, `split-brain`, `work-distribution`

| agent | role |
|---|---|
| Code Interpreter Agent | `primary` |
| Security Scanner | `checker` |
| Backup & Restore | `support` |
| Incident Commander | `support` |
