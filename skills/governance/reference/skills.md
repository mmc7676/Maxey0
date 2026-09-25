# Governance — skills

The 5 skill(s) this concept owns, from the Maxey0 manifest. Each names the agent formation already bound to it: a `primary` that produces, a `checker` that verifies, and `support` roles around them.

That formation is why routing beats improvising. A pre-scoped formation for the matched skill is almost always cheaper and better targeted than a hand-written maker/checker pair.

## `constitutional-constraint-enforcement`

**Constitutional Constraint Enforcement**

Gates every proposed action against a versioned policy registry with cited allow/deny verdicts and audited enforcement.

memory tier: `persistent` · tags: `policy`, `gate`, `constraint`, `egress`, `deny`

| agent | role |
|---|---|
| Security Sentinel | `primary` |
| Compliance Auditor | `checker` |
| Policy Proxy | `support` |
| Cost Guard | `support` |

## `enterprise-agent-governance`

**Enterprise Agent Governance**

Governs agent deployments at organizational scale: approval workflows, audit logs, policy versioning, and rollback.

memory tier: `persistent` · tags: `enterprise`, `governance`, `approval`, `audit`, `rollback`

| agent | role |
|---|---|
| Security Sentinel | `primary` |
| Compliance Auditor | `checker` |
| Policy Proxy | `support` |
| SuperAgent Orchestrator | `support` |

## `enterprise-constitution-modeling`

**Enterprise Constitution Modeling**

Authors and versions the policy documents that enforcement gates read: law definitions, scope declarations, exception protocols.

memory tier: `persistent` · tags: `constitution`, `modeling`, `law`, `policy`, `authoring`

| agent | role |
|---|---|
| Compliance Auditor | `primary` |
| Security Sentinel | `checker` |
| Policy Proxy | `support` |
| Provenance Signer | `support` |

## `cross-organization-policy-negotiation`

**Cross-Organization Policy Negotiation**

Negotiates compatible policy scopes between organizations sharing agents or data: intersection finding, conflict resolution, escalation.

memory tier: `persistent` · tags: `cross-org`, `negotiation`, `policy`, `conflict`, `intersection`

| agent | role |
|---|---|
| Security Sentinel | `primary` |
| Compliance Auditor | `checker` |
| Policy Proxy | `support` |
| LangChain Adapter Agent | `support` |

## `enterprise-memory-isolation`

**Enterprise Memory Isolation**

Enforces memory isolation between organizational tenants: scope separation, access controls, and audit of cross-tenant operations.

memory tier: `persistent` · tags: `isolation`, `tenant`, `enterprise`, `memory`, `access-control`

| agent | role |
|---|---|
| Security Sentinel | `primary` |
| Compliance Auditor | `checker` |
| Working Memory Manager | `support` |
| Database Architect | `support` |
