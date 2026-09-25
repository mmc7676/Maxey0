---
name: agentic-loops
description: "Agentic Loops — an architecture concept covering loop, chain, pipeline, scw, partition. Use when the user's task concerns agentic loops, or matches: loop, chain, pipeline, scw, partition, isolation, battery, hardening. Route with loops_route first — this concept's 2 skills and 0 loops are listed in reference/, and a coherent hit often names a different concept's formation."
---

# Agentic Loops

**Architecture concept** · 2 skill(s) · 0 loop(s) tagged `agentic-loops`

Vocabulary: `loop`, `chain`, `pipeline`, `scw`, `partition`, `isolation`, `battery`, `hardening`

## When this applies

A task concerns `agentic-loops` when it matches that vocabulary — but matching the vocabulary is not the same as belonging here. Route first and let the decision be examinable.

## What to do

1. **Route.** Call `loops_route(task="...")` with the task in plain language. It scores the task across concepts, skills and agents and returns the evidence for its decision — what it considered, what it rejected, and why. It binds nothing.
2. **Expect a fallback.** Nothing is tagged `agentic-loops`, so `loops_route` will fall back to skills or agents. Say so plainly — a routing miss is information about the library, not an error to hide.
3. **Bind, if you are going to run it.** `context_route_bind` asks the same question and commits: it binds the matching loop's partition in this session's own window. Without the Context plane installed, routing still answers; it just cannot be followed by a bind.

## What ships with this skill

| file | contents |
|---|---|
| [reference/skills.md](reference/skills.md) | the 2 skill(s) under this concept, each with the agent formation bound to it |
| [reference/loops.md](reference/loops.md) | the 0 loop(s) tagged `agentic-loops`, with provenance, status and hardening record |
| [reference/agents.md](reference/agents.md) | the registry agents that appear in those loops, and what each specializes in |

**No loop in the library is tagged `agentic-loops` yet.** That is a real gap in library coverage rather than a reason to stop: the concept's 2 skill(s) still name real formations, and a task that routes here is worth recording as a miss.

## The rule that carries

A refusal is a result. If the runtime refuses a read, report it with its own message and hint rather than routing around it — the hint names the bridge that would make the access legal, and whether that access is justified is a decision to make explicitly.

See [skills/scw](../scw/SKILL.md) for how partitioning and routing actually work.
