---
description: Route a task against the Maxey0 library and report the decision — binds nothing
argument-hint: <task description>
allowed-tools: mcp__maxey0-loops__loops_route, mcp__maxey0-loops__loops_catalog, mcp__maxey0-loops__loops_concepts, mcp__maxey0-loops__loops_skills, mcp__maxey0-loops__loops_agents
---

Route this task and explain the decision: **$ARGUMENTS**

This command commits nothing. It answers "what *would* happen", so it is safe
to run before you have decided anything. `/maxey0:run` is the same question
followed by the binding.

## Do this

1. Call `loops_route(task="$ARGUMENTS")`.
2. Report the outcome plainly:

   - **`loop_hit`** — a hardened loop already covers this. Name it, its status
     (`validated` / `partial` / `draft-unexecuted`), its formation, and what
     each role does. Then say: `/maxey0:run` binds this partition.
   - **`fallback_skill` / `fallback_agent`** — nothing in the library covered
     it. Say so directly. **That gap is a real finding about library coverage,
     not a failure to hide.** Name the closest skills or agents and what a
     hand-built formation would have to look like.

3. Report the evidence the router returned — what it considered, what it
   rejected, and why. A routing decision nobody can interrogate is not
   explainable, and the whole point of this plane is that the choice is
   examinable, not just the execution.

## Why routing first is not a formality

One measured case: a documentation-audit task routed to a pre-scoped four-agent
formation at roughly 10,800 tokens. The same task run as two improvised
subagents with hand-written personas cost 253,481 — about 23× more, for a
worse-scoped result.

Use `loops_catalog`, `loops_concepts`, `loops_skills` and `loops_agents` to
browse when the user wants to see the library rather than route against it.
