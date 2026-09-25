# SCW0: when to deploy a window, and what it buys

SCW0 is the root of a formation — the window a task is chartered under. Every
window beneath it derives its constitution from SCW0's, and by induction cannot
reach outside it. This document says when that is worth doing, and what it does
and does not defend against.

## The deployment predicate

> **Deploy SCW0 when some process downstream of this work will need
> encapsulation or observability that cannot be reconstructed later.**

Concretely, deploy when any of these hold:

| Condition | Why it forces a window |
|---|---|
| **Encapsulation** — two or more consumers of context that must not see each other's content | Isolation has to be enforced outside the model. Asking an agent not to look is not a boundary. |
| **Observability** — someone downstream must later answer *why did this happen* | The answer must be recorded at the time. It cannot be recovered afterwards. |
| **Irreversibility** — the work produces an effect that cannot be undone | Evidence must exist *before* the effect, not after it. |

Do **not** deploy when the work has a single consumer, is reversible, and
nothing will ever interrogate it. There SCW0 is pure overhead: an address, a
gate and a chain, guarding a decision nobody will revisit.

### The expected-value form

Deploying costs a fixed setup plus a per-crossing record. Not deploying costs
whatever it costs to answer a later question without evidence:

```
    deploy  iff   C_scw  <  P(audit) × C_reconstruct  +  P(leak) × C_leak
```

The asymmetry that decides most real cases is in `C_reconstruct`. Without a
recorded decision, reconstructing what an agent could see is not *expensive* —
it is **impossible**. You can only guess, and a guess is not an audit. So the
term does not grow large as evidence gets thinner; it goes undefined.

Which collapses the formula to something usable:

> **If `P(audit) > 0` and the effect is irreversible, deploy. Otherwise compare
> honestly.**

### Why the cheap case is genuinely cheap

Most work fails all three conditions, and that is the point. A window you did
not need is the second most expensive thing in the system, after an improvised
formation. `/maxey0:effort` asks the encapsulation and observability questions
explicitly so the answer is recorded rather than assumed.

## What the hierarchy guarantees

Since `containment/hierarchy.py`, every SCW is chartered under a parent and its
constitution is *derived*. Derivation narrows and never widens, so:

```
    reach(descendant) ⊆ reach(root)     for every descendant, at any depth
```

This holds by induction: each charter is a subset of its parent's, and subset is
transitive. Containment of an entire spawned formation therefore reduces to a
single question — **what reach did SCW0 get?**

Three bounds are enforced, because reach alone is not containment:

- **Reach** — a child may narrow inherited reach, never widen it. A bridge
  cannot exceed the constitution either; that was the leak that made the
  hierarchy advisory.
- **Extent** — depth, direct children and total descendants are capped. The
  descendant cap is checked against *every* ancestor holding one, because
  testing only the immediate parent lets a chain grow forever: each new node has
  no descendants of its own at the moment it charters a child.
- **Persistence** — `DenialBreaker` reads the attestation chain back and refuses
  a window that keeps attempting refused crossings.

Widening is refused rather than clamped. Silently reducing a request to what the
parent allows would hide the attempt; refusing produces a decision, and the
decision is evidence.

## The swarm question, answered honestly

> *Could you contain, defend, learn from, or survive an agentic swarm attack if
> each SCW's constitution depends on the level above it?*

Four different properties. They do not come together.

| | Status | Why |
|---|---|---|
| **Contain** | **Yes** | The induction. Nothing beneath SCW0 reaches outside it, however deep it spawns, and extent is capped so it cannot exhaust the host while staying inside its rights. |
| **Defend** | **Partly** | `DenialBreaker` bounds persistence — repeated refused crossings stop being free. But a swarm that stays *inside* its granted reach is indistinguishable from legitimate work at the gate, and no amount of hierarchy changes that. |
| **Learn** | **No** | The breaker reads the chain, but policy does not update from it. Nothing tightens a constitution in response to what the evidence shows. This is the honest gap. |
| **Survive** | **Yes, conditionally** | Only if SCW0's own constitution is not mutable from below. `narrow()` can only narrow, so there is no upward escalation path — but a deployment that re-charters its own root at runtime has given that away. |

The load-bearing caveat: **containment is only as good as the reach SCW0 was
granted.** An SCW0 chartered with unbounded reach contains nothing, and the
induction still holds — it just proves a vacuous statement. The root grant is
the security decision; everything below it is arithmetic.

## Memory, instructions and knowledge

The same ceiling applies to what a window *holds*, not only what it can reach.
Three distinct things get conflated:

- **Instructions** are paid for by every window that receives them. An
  instruction sent to three agents is written once and billed three times.
  Optimize by *narrowing*, not by summarizing: send the three steps that are
  theirs, not a compressed version of all fourteen.
- **Knowledge** is reference material, and the duplication here is more specific
  than "copied per role". The 3× belongs to the **flat control arm**:
  `experiment.py:518-543` binds every role to one region, so all roles get
  byte-identical material. In the partitioned arm each role renders only its own
  reach, and `harness_kit.cost_model` reports `flat = whole × roles` against
  `partitioned = sum(per-role)`. **`flat_tokens` is a counterfactual baseline,
  not a bill** — the partition has already removed it.
- **Memory** is what survives the window. It is the only one of the three that
  should outlive a formation, and the only one where the attestation chain is
  the right storage — because it is the part that must still be true later.

### The cache plan is null everywhere

`window.render()` computes `cache_breakpoint_after` and a full segment plan
(`window.py:2566-2571`), and `cacheable` is a subset of the rendering role's
reach by construction (`window.py:2511-2516` — the plan is keyed per `loop_id`,
and both the region set and each signature are scope-filtered). Scope-safe
caching is therefore already achievable.

It never happens. `experiment.py:578` renders with `commit=False`, so
`_render_snapshots[loop_id]` is never written (`window.py:2561` is guarded by
`commit`). Every render then sees an empty snapshot, `is_stable(0, …)` fails
immediately (`cache.py:115-117`), the prefix is 0, and `breakpoint_scw_id` is
`None` (`cache.py:148`).

> **The cache plan is unconditionally null for every call in every arm** —
> including the flat arm, where N identical prompts are the ideal case for it.

The defensible minimal change is plumbing, not a client edit: carry
`cache_breakpoint_after` and `segments` onto the `Call` record at
`experiment.py:578` so the out-of-process dispatcher can set `cache_control` on
the shared prefix. It would have to land in all five byte-identical copies
(`server/` plus `plugins/maxey0{,-context,-loops,-observe}/server/`).

Nothing here has been measured against a live API.

## What this does not do

- It does not make an agent trustworthy. It makes agent behavior *bounded*,
  which is a different and weaker claim, and the only one enforceable from
  outside the model.
- It does not detect a leak that happens inside granted reach.
- It does not update policy from evidence. The chain is read by the breaker and
  by nothing else.
- Chartering is **opt-in**. A provider constructed without a tree behaves
  exactly as it did before, which means an unchartered deployment has none of
  the guarantees above.
