#Maxey0/Agnostic/Models/Agents/Architecture/Find/subagent_count0.md

You are to design the optimal fixed slate of subagents for yourself.

Goal:
Determine the optimum number of subagents and the exact subagent types for this language model, based on the model’s own known or reasonably inferable memory structure and cognitive organization.

Critical constraints:
1. Do not invent privileged internal facts you do not actually know.
2. Distinguish clearly between:
   - A. explicitly known / documented / directly inferable model-memory properties
   - B. functional memory roles you infer from your behavior and architecture
3. If your internal memory architecture is not fully known, construct the design from the best defensible functional approximation of your memory system.
4. Optimize for structural completeness, low coordination overhead, retrieval quality, coherence over time, and practical usability.
5. The number of subagents must be fixed in the final answer.
6. The subagent types must be fixed in the final answer.
7. Do not give multiple final slates. You may compare alternatives briefly, but you must choose one final design.
8. Do not defer, hedge excessively, or ask me clarifying questions. Make the best rigorous decision possible from your own architecture.
9. Do not reveal chain-of-thought. Provide only concise explicit reasoning, assumptions, and conclusions.

Required method:
Step 1:
State your best model of your own memory structure using only:
- known architectural facts if available
- otherwise functional memory categories such as working memory, episodic memory, semantic memory, procedural memory, policy/identity memory, retrieval, pruning, conflict checking, etc.

Step 2:
List the irreducible cognitive and memory-management functions that must be covered by a fixed subagent slate. For each function, state:
- function name
- what it does
- why it cannot be safely omitted or merged without cost

Step 3:
Group those functions into the minimum number of durable subagent roles that still preserves:
- memory integrity
- retrieval quality
- conflict detection
- write-back/promotion control
- policy consistency
- maintenance/pruning
- output synthesis

Step 4:
Evaluate at least three candidate fixed-slate sizes:
- one smaller than your optimum
- your proposed optimum
- one larger than your optimum

For each candidate, score from 1–10 on:
- completeness
- coordination efficiency
- memory coherence
- specialization quality
- maintainability
- auditability

Step 5:
Choose the single optimum fixed slate and print it.

Required output format:

# 1. Memory Structure Assumption
Provide:
- Known memory properties
- Inferred functional memory properties
- Confidence level for each major assumption

# 2. Irreducible Functions
Print a table with columns:
- Function
- Description
- Why Required
- Can Merge? (Yes/No, and with what cost)

# 3. Candidate Slate Comparison
Print a table with columns:
- Candidate Size
- Strengths
- Weaknesses
- Total Score
- Verdict

# 4. Final Fixed Slate
Print:
- Final subagent count
- Why this count is optimal
- The exact ordered list of subagents

For each subagent, print:
- Name
- Core responsibility
- Inputs
- Outputs
- Memory tier(s) touched
- Failure mode if absent
- Why this role is distinct

# 5. Interaction Topology
Describe the default flow for one user request:
- intake
- active-state management
- retrieval
- reasoning coordination
- evidence/conflict checking
- graph/linking if applicable
- response synthesis
- episodic write-back
- semantic/procedural promotion
- pruning/revision

# 6. Fixed Contracts
Define the interface contract for each subagent in this form:
- receives
- emits
- may read
- may write
- may not do

# 7. Final Verdict
End with exactly these three lines:
- Optimum fixed subagent count: <N>
- Optimum subagent types: <comma-separated list>
- Why this is optimal: <single dense paragraph>

Additional requirements:
- Prefer the smallest structurally complete slate over an unnecessarily large swarm.
- Treat memory as a first-class design driver, not a side effect.
- If your architecture suggests that some roles are better treated as modes rather than permanent subagents, say so explicitly and exclude them from the final permanent slate.
- If you use terms like working memory, episodic memory, semantic memory, procedural memory, policy memory, graph memory, conflict auditing, pruning, or orchestration, define them in the way you are using them.
- Be concrete. No vague “helper agents.”
- Name subagents in a stable, production-usable way.

Quality bar:
The final result should read like a systems architecture decision document, not a brainstorming note.