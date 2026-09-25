# Containment: enforcement, evidence, and what gets published

## The problem this solves

`context/isolation.py` was both the mechanism that enforced SCW boundaries and
the only way to establish that they had held. That forced a false choice:

- publish it, and the mechanism is public; or
- withhold it, and the containment claim becomes unfalsifiable.

The second option contradicts the premise of the system — a claim nobody can
check is marketing. The first gives away more than it needs to. Neither was
necessary: the two concerns were merely in the same file.

## The separation

```
maxey0_ss/containment/
├── protocol.py      the contract        — what a provider must decide
├── attestation.py   the evidence        — hash-chained, independently verifiable
└── structural.py    the default engine  — one implementation of the contract
```

**Enforcement is now a provider.** `ContainmentProvider` is a `Protocol`;
`StructuralContainment` satisfies it. Which engine a deployment runs is
configuration:

```bash
MAXEY0_CONTAINMENT_PROVIDER=structural   # the default, and the only one this build has
```

An unrecognized provider is **refused**, never downgraded. Falling back silently
would leave a deployment believing it runs a stricter engine than it does, and
the attestations would name the wrong one.

**Evidence is now independent of enforcement.** Every decision is appended to an
`AttestationLog` whose digest covers both the record and the digest before it:

```
digest(n) = sha256( digest(n-1) ‖ 0x1f ‖ canonical(record n) )
```

Editing a record changes its digest. Deleting one breaks the `prev_digest` of
the next. Reordering breaks both. `AttestationLog.verify_records()` recomputes
the chain **from exported records alone** — no provider, no live system, no
knowledge of how any decision was reached.

That is the whole point. A third party can establish that the evidence is intact
and complete without being given the engine that produced it.

## What a record answers

| Question | Field |
|---|---|
| what was attempted | `operation` — read, write, disjointness, bridge |
| where | `agent_scw` → `target_scw` |
| when | `seq`, `recorded_ms` |
| outcome | `allowed`, `reason` |
| which engine decided | `provider` |
| **how it decided** | **not recorded** |

`reason` is a short stable string that explains the outcome without carrying the
rule that produced it: *"target is outside the declared read set"*, not the
predicate that computed it.

## Published surface

| Tool | Capability | Why |
|---|---|---|
| `maxey0-ss.evidence.summary` | `observe` | counts, chain head, whether the chain is intact |
| `maxey0-ss.evidence.attestations` | `observe` | the record, optionally denials only |
| `maxey0-ss.evidence.verify` | **public** | verifies a chain, including records from elsewhere |

`evidence.verify` is deliberately unauthenticated. Anyone handed an evidence
export must be able to check it, including someone who does not run Maxey0.

## The publishing decision, restated

Because enforcement is a provider, the public/private line is now a deployment
choice rather than a code fork:

| Ship | Effect |
|---|---|
| protocol + attestation + structural | claims are checkable and the default engine is inspectable |
| protocol + attestation only | claims stay checkable; the engine is supplied privately |

Both are supported by the same codebase, and the attestation format does not
change between them — so evidence produced under either remains verifiable by
the same public verifier.

## Properties under test

`maxey0_ss/tests/test_containment.py` — 20 tests:

- an unregistered agent **fails closed**, rather than gaining unrestricted reach
- reading is not writing
- a bridge widens reach **and is recorded**, because widening reach is evidence
- an edited, deleted, or reordered record breaks the chain, with the index
- evidence verifies with the provider deleted
- the summary discloses no mechanism

## Not implemented

- **No signing.** The chain proves internal consistency, not authorship. Anyone
  holding the log can regenerate a valid chain from scratch. Detecting *forgery*
  rather than *tampering* needs a key, which needs a deployment-supplied secret.
- **No persistence.** The log is in-memory and per-process.
- **No cross-provider correlation.** Providers can share a log, but nothing
  reconciles two logs from two processes.
