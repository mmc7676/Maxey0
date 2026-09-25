---
name: orchestration
description: "Orchestration — an architecture concept covering orchestrate, route, delegate, hierarchy, plan. Use when the user's task concerns orchestration, or matches: orchestrate, route, delegate, hierarchy, plan, swarm. Route with loops_route first — this concept's 5 skills and 14 loops are listed in reference/, and a coherent hit often names a different concept's formation."
---

# Orchestration

**Architecture concept** · 5 skill(s) · 14 loop(s) tagged `orchestration`

Vocabulary: `orchestrate`, `route`, `delegate`, `hierarchy`, `plan`, `swarm`

## When this applies

A task concerns `orchestration` when it matches that vocabulary — but matching the vocabulary is not the same as belonging here. Route first and let the decision be examinable.

## What to do

1. **Route.** Call `loops_route(task="...")` with the task in plain language. It scores the task across concepts, skills and agents and returns the evidence for its decision — what it considered, what it rejected, and why. It binds nothing.
2. **Browse what already exists.** `loops_catalog(concept="orchestration")` returns the same loops with their live status. Prefer one of them to anything hand-built.
3. **Bind, if you are going to run it.** `context_route_bind` asks the same question and commits: it binds the matching loop's partition in this session's own window. Without the Context plane installed, routing still answers; it just cannot be followed by a bind.

## What ships with this skill

| file | contents |
|---|---|
| [reference/skills.md](reference/skills.md) | the 5 skill(s) under this concept, each with the agent formation bound to it |
| [reference/loops.md](reference/loops.md) | the 14 loop(s) tagged `orchestration`, with provenance, status and hardening record |
| [reference/agents.md](reference/agents.md) | the registry agents that appear in those loops, and what each specializes in |

14 loop(s) in the library are tagged `orchestration` (1 partial, 13 validated). They are listed with their hardening records in [reference/loops.md](reference/loops.md).

## The rule that carries

A refusal is a result. If the runtime refuses a read, report it with its own message and hint rather than routing around it — the hint names the bridge that would make the access legal, and whether that access is justified is a decision to make explicitly.

See [skills/scw](../scw/SKILL.md) for how partitioning and routing actually work.
