# The three planes

Maxey0 is three planes. Each is a separately installable connector with its own MCP server, its own commands, and its own skills. Each is useful alone. The Observatory can see the other two, and neither of the other two can see it.

That asymmetry is the design rather than an accident. A boundary you can see through is not a boundary — so the resolution is not to let the orchestrator see inside every partition, it is to make the boundary itself the thing that is observable, from outside.

## Context — `maxey0-context`

*Partition the window and enforce who reads what.*

**Owns.** Structured Context Windows: regions, scopes, bridges, grants, harnesses, ticks, and the hash-chained ledger.

**Alone.** Partition a context window and enforce access without ever routing a task or watching an agent.

32 tools.

## Loop — `maxey0-loops`

*Decide who should act, and in what shape.*

**Owns.** The library — 16 concepts, 83 skills, 67 agents, 84 hardened loops — plus routing and cross-window topologies.

**Alone.** Route a task to a pre-scoped formation and run it against a fixed context scheme, with no enforcement engine installed.

10 tools.

## Observatory — `maxey0-observe`

*Record what happened, and refuse what left scope.*

**Owns.** The Gate, the event stream, correlated traces, isolation levels, and the Studio.

**Alone.** Attribute and refuse any delegated agent's tool calls — global workspace semantics — with no window and no library.

8 tools.

## The rule that assigns a tool to a plane

The window is process-local state. A tool in another process would act on a different window — so every tool that touches the live window lives on the Context plane, including the four containment assertions and the binding router. The Loop plane holds no window state at all, which is exactly what lets it run standalone. The Observatory reads both other planes as files, and replays the ledger when it needs structure rather than a record list.
