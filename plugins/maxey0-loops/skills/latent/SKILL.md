---
name: latent
description: "Latent Space — a research concept covering latent, embedding, anchor, subspace, disclosed-approximation. Use when the user's task concerns latent space, or matches: latent, embedding, anchor, subspace, disclosed-approximation, trilateration, sae. Route with loops_route first — this concept's 9 skills and 19 loops are listed in reference/, and a coherent hit often names a different concept's formation."
---

# Latent Space

**Research concept** · 9 skill(s) · 19 loop(s) tagged `latent`

Vocabulary: `latent`, `embedding`, `anchor`, `subspace`, `disclosed-approximation`, `trilateration`, `sae`

## When this applies

A task concerns `latent` when it matches that vocabulary — but matching the vocabulary is not the same as belonging here. Route first and let the decision be examinable.

## What to do

1. **Route.** Call `loops_route(task="...")` with the task in plain language. It scores the task across concepts, skills and agents and returns the evidence for its decision — what it considered, what it rejected, and why. It binds nothing.
2. **Browse what already exists.** `loops_catalog(concept="latent")` returns the same loops with their live status. Prefer one of them to anything hand-built.
3. **Bind, if you are going to run it.** `context_route_bind` asks the same question and commits: it binds the matching loop's partition in this session's own window. Without the Context plane installed, routing still answers; it just cannot be followed by a bind.

## What ships with this skill

| file | contents |
|---|---|
| [reference/skills.md](reference/skills.md) | the 9 skill(s) under this concept, each with the agent formation bound to it |
| [reference/loops.md](reference/loops.md) | the 19 loop(s) tagged `latent`, with provenance, status and hardening record |
| [reference/agents.md](reference/agents.md) | the registry agents that appear in those loops, and what each specializes in |

19 loop(s) in the library are tagged `latent` (19 validated). They are listed with their hardening records in [reference/loops.md](reference/loops.md).

## The rule that carries

A refusal is a result. If the runtime refuses a read, report it with its own message and hint rather than routing around it — the hint names the bridge that would make the access legal, and whether that access is justified is a decision to make explicitly.

See [skills/scw](../scw/SKILL.md) for how partitioning and routing actually work.
