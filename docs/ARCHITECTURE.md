# Architecture

What Maxey0 is, what it is made of, and why the pieces are separated the way
they are. This document is the reference the rest of the repo defers to.

---

## The finding that produced this version

Through v0.5.0 the runtime enforced a real partition. Regions were typed, scopes
were closed, bridges expired, verdicts were refused when a judge was not
provably disjoint, and every one of those decisions landed in a hash-chained log
that replays to an identical window.

Then we counted what was actually in the log.

From `~/.scw/events.jsonl` — 554 records over 98 runs of the real Claude Code
session window:

| event | count |
|---|---|
| `scw.denied` | 210 |
| `window.init` | 105 |
| `scw.create` | 96 |
| `bridge.open` | 80 |
| `loop.bind` | 41 |
| `harness.create` | 8 |
| `route.*` | 11 |
| `criterion.pin` | 1 |
| **`scw.write`** | **2** |
| **`scw.read`** | **0** |
| **`loop.tick`** | **0** |
| **`window.render`** | **0** |

Forty-one loops were bound. Ninety-six regions were created. Eighty grants were
minted. Zero reads were performed.

The Studio's own log (`~/.scw/studio.jsonl`, 5 411 records) has the same shape
with the volume turned up: 479 `window.render` against 21 `scw.read` and 12
`loop.tick`.

Two things follow, and both are load-bearing.

**Every refusal in the log was provoked by the harness, not by an agent.** All
2 838 `op: bridge` denials are `expect_refusal: true` negative controls that
`server/vendor/d4/harness_dsl.py` emits by construction: for each ordered pair
of roles it attempts a pad-to-pad grant and expects the runtime to refuse. That
is a legitimate self-test of the enforcement engine. It is not evidence about
any agent, because no agent was involved.

**Every read an agent actually performed happened somewhere the window cannot
see.** The subagent transcripts on this machine
(`~/.claude/projects/<project>/<session>/subagents/agent-<id>.jsonl`) record
115 real tool calls across 17 subagents — 63 `Read`, 39 `Bash`, 6 `Grep`,
6 `WebFetch`, 1 `Glob`, 4 MCP calls. None of them appear anywhere in the SCW
log.

So the honest statement of where v0.5.0 stood:

> The partition is real and enforced **for calls that go through it**. The
> agents do not go through it. What was measured was the runtime, not the
> agents.

`window.render` exceeding `scw.read` by more than twenty to one is the
signature of the whole problem: the **host** renders scope-true material and
hands it to a subagent as text, and from that moment the subagent is working in
a context the runtime has no address for. The partition was functioning as a
prompt-construction device, not as an execution boundary.

There is a second hole in the same wall. `agents/agent-role.md` granted
`Read, Glob, Grep`. A role bound to a 2 048-token scratchpad could read any file
on the disk. The partition governs regions; it never governed the filesystem.
That side channel was not merely unenforced — it was **unmeasured**, which is
worse, because a containment number computed without it is quietly wrong.

v0.6.0 exists to close this. Everything below is organized around it.

---

## The structural fact

The instinct on discovering this is to give the orchestrator more reach: let
Maxey0 see inside the subagent, instrument it from above, orchestrate its steps.

That instinct is wrong, and the reason it is wrong is the architecture.

**If the orchestrator could see inside every partition, there would be no
partition.** Isolation and observability pull against each other by
construction. A boundary you can see through is not a boundary. The resolution
is not to pierce the boundary; it is to **make the boundary itself the thing
that is observable.**

So Maxey0 does not orchestrate inside an SCW. It orchestrates the network *of*
SCWs. What happens inside one is that SCW's own business, and it needs its own
orchestrator — a `Maxey#` bound to that window, which can address its own
sub-windows and nothing above them.

This is the load-bearing claim of the design, and every layer below follows from
it.

---

## The three planes

> Most agent infrastructure primarily adds capability to the **execution
> plane**. Maxey0 makes the contextual environment surrounding agentic
> execution an independently structured, routable, partitionable, and
> observable **plane**, while providing an **engineering plane** that can
> observe and tune both.

That sentence is the architecture. Three planes, and Maxey0 deliberately owns
only two of them.

| plane | owner | holds | Maxey0's part |
|---|---|---|---|
| **Execution** | the host | Agents, agentic loops, LLM calls, tool calls, working memory, generated output | **Adds no capability here.** Constrains it at the tool call and records what crossed. |
| **Context** | Maxey0 | Concepts, Skills, SCWs, regions, scopes, admission gates, routing, provenance | Makes it structured, routable, partitionable and addressable, instead of a string assembled just before a call. |
| **Engineering** | Maxey0 | The Gate, the hash-chained ledger, the three correlated traces, the isolation ladder, the Studio | Observes and tunes the other two. Sees both; neither sees it. |

### Owning two planes is the design, not a gap

Every other agent framework competes on the execution plane: better tools, more
autonomy, longer loops, cheaper calls. That plane is crowded and Maxey0 is not
in it. What it adds instead is a plane everyone else treats as a formatting
step — the context is a string somebody concatenated before the call, and after
the call nobody can say which part of it produced what.

Making that plane addressable is what turns a prompt into an engineering
surface: a region has a type and a budget, a role has a scope the runtime
enforces, a crossing needs a grant, and every one of those decisions is an
event with an address.

### Planes are not connectors

A plane is what the system **is**. A connector is what **installs**. They are
different decompositions and the mapping is many-to-one:

| connector | serves | carries |
|---|---|---|
| `maxey0-context` | Context plane | the state machinery — regions, scopes, bridges, the ledger, the assertions |
| `maxey0-loops` | Context plane | the semantic machinery — Concepts, Skills, routing, formations |
| `maxey0-observe` | Engineering plane | the Gate, the traces, the isolation ladder, the Studio |
| *(none)* | Execution plane | owned by the host; the Gate stands at its boundary rather than inside it |

Through 0.7.0 the documentation said "three planes, each a connector," which
collapsed those two decompositions into one and lost the plane Maxey0 does not
own — the plane whose absence is the entire differentiation.

### What decides which connector a tool belongs to

Not subject matter. One mechanical fact: **the window is process-local state.**

A tool in another process acts on a different window, so every tool that reads
or writes the live window has to live in the process that owns it. Two
consequences look wrong until you see why:

- The four containment assertions are **`maxey0-context`** tools. They are the
  strongest evidence the product produces precisely because they perform a real
  read through the real authorization path — and that read has to happen where
  the window is.
- `context_route_bind` is a **`maxey0-context`** tool although routing is the
  library's subject. `loops_route` scores and explains; `context_route_bind`
  asks the same question and commits. One reads, the other writes.

And one that is the whole point:

- **`maxey0-observe` holds no window at all.** It reads the ledger from disk and
  replays it when it needs the region graph. It therefore sees every scope and
  every closure while being structurally unable to write any of them.

That is the resolution of the tension below, made concrete. If the Engineering
plane reached *into* the other two it would be piercing the boundary it exists
to measure. It does not reach in. It reads what the boundary wrote down.

---

## Private, not disjoint

The obvious formalization of isolation is wrong, and shipping it meant the
product's own assertion failed the product's own formation.

`read_closure(a) ∩ read_closure(b) = ∅` is too strong. A checker is *supposed*
to read the maker's published draft; every role is *supposed* to read the
concept's constitution. A formation whose roles can never share anything cannot
do work. The claim that matters is narrower:

```
Private(a) ∩ Private(b) = ∅        must hold
Admitted(a → b) ≠ ∅                is the point of the formation
```

So `context_assert_disjoint` classifies an overlapping region instead of
counting it:

| class | meaning | fails the assertion |
|---|---|---|
| `private_overlap` | a `bridgeable=False` working pad both roles reach | **yes** — a containment breach |
| `admitted` | one role writes it, the other reads it: a declared handoff | no — the formation working |
| `shared_reference` | no bound role can write it | no — a region nobody writes cannot carry state between them |

That last row is the one worth stating plainly: **a read-only region is shared
context without being a channel.** Both roles read the constitution; neither can
put anything in it; so it cannot carry the maker's framing to the judge. The
contamination people warn about needs a writer.

An assertion that fails a correct partition trains an operator to ignore it,
which is worse than not having the assertion at all.

---

## Egress: `context_admit`

Everything above enforces **ingress** — what a role may reach. Scope decides
it at bind time; a bridge decides it explicitly and briefly; the Gate (below)
decides it at every tool call. None of them decide what a role's own output
is allowed to become once it exists. A maker's draft is either fully visible
to whatever reads the handoff region or not visible at all, because reach is
binary. That is the gap `context_admit` closes.

`context_admit(from_role, to_role, from_region, to_region, rule)` gates a
handoff the partition already declared. It does not mint reach — `to_region`
still has to be in `to_role`'s read closure and `from_role`'s write closure
before the call succeeds, exactly like an ordinary write — it governs what of
`from_region`'s content actually lands there:

| rule | what crosses |
|---|---|
| `approve` | everything, unchanged |
| `summarize` | each entry, deterministically truncated with a length marker — never an invented summary |
| `redact` | every entry except those whose key names something the caller declared off-limits |
| `reject` | nothing |

A real, authorized read of `from_region` happens under every rule, including
`reject` — the gate has to see what it is deciding about, and that read is
itself a recorded event. Every outcome, `reject` included, is recorded as a
`promote` event tagged `payload.gate == "admit"`: a decision not to admit
something is still a decision, and it belongs in the ledger on the same terms
as one that moved content.

`context_assert_admitted(from_role, to_role)` is what makes the record
checkable rather than merely present. It computes the regions `from_role`
could hand to `to_role` — the same write-closure/read-closure intersection
`context_assert_disjoint` calls `admitted` — and asks whether the ledger holds
a tagged `promote` event for each one. A region with the structural reach but
no recorded decision is `unadmitted`: not on its own a breach, since the
region may hold nothing yet, but a containment claim that cannot name a
recorded reason for every path capable of carrying content is a narrower
claim than "contained," and this is the assertion that finds the gap between
the two.

---

## The address strata

Maxey0 answers two questions about a task, and keeps them separate:

```
T --Maxey0--> (SCW, Formation) --Harness--> Execution --LLM--> Behavior
              └─ WHERE ─┘  └─ HOW ─┘
```

**WHERE** is an address in the context window. **HOW** is a formation of roles.
They are chosen by different logic, measured on different axes, and must not be
collapsed into one score.

Five **strata**, each addressable, each with its own identity space.

These are not the three product planes. A stratum is a level of the
address space; a plane is a connector you install. The word "plane" meant
both through 0.6.0, which is why a reader could not tell whether "the skill
plane" was something to install or something to address. See
[LEXICON.md](LEXICON.md).

### Stratum 0 — the window

The session's context window **is** SCW0. Not an analogy: the root region. Every
other region is a descendant of it, and the token budget of the window is the
budget SCW0 partitions.

### Stratum 1 — regions (WHERE)

SCW0 subdivides into SCW1..n, and those subdivide again. The runtime already
supports this: regions carry `parent_id` and `children`
(`server/vendor/scw_runtime/model.py:179`), loops carry `parent_loop_id`
(`model.py:300`), and `context_scope_bind` enforces containment, depth limits and cycle
detection through `NestingViolation`
(`server/vendor/scw_runtime/window.py:1040`).

Maxey0 addresses SCWs. It does not address what is inside them.

### Stratum 2 — concepts (WHAT)

An SCW is scoped to exactly one **Concept**. This is the reading that makes the
acronym do double duty:

> **An SCW is scoped to exactly one Concept, so the concept **is** the shared
> context of the loop bound to it.**

The constitution of an SCW is written for its Concept. That is not decoration;
it is what makes the shared context of a loop coherent. If a maker, a checker
and a judge are all working on the same concept, then the concept **is** their
shared context — the thing they may all see, that none of them may edit, and
that the judge grades against. A maker specialized in producing X, a checker
specialized in checking X, and a judge specialized in judging X are one
formation precisely because X is common to all three and private to none.

Concretely, a Concept SCW holds:

| region | type | who may touch it |
|---|---|---|
| constitution | `reference`, readonly | everyone reads; nobody writes |
| criterion | `reference`, pinned | pinned before the run; the maker's write closure must exclude it |
| skills | `reference`, readonly | the gate surface (see Plane 3) |
| one pad per role | `scratchpad`, `bridgeable=false` | that role only, ever |
| one handoff per declared exposure | `durable` | the maker writes; the judge reads |

Loops and agents are pre-mapped to concepts **by the skills they use**. Assigning
loops to concepts is the central act of configuring Maxey0.

### Stratum 3 — skills, as gates

A Skill is not only a capability. A Skill is a **gate**: the addressable point at
which something inside an SCW can be reached from outside it, and at which
something inside reaches out.

This is the resolution of the communication problem. Maxey0 cannot see inside
SCW*n*, and must not. But it does not need to. It needs a finite, declared,
observable set of locations where crossings happen — and those locations are the
skills the concept exposes. A gate is a pivot vector between stratum 4 and
stratum 1.

### Stratum 4 — roles and loops (WHO, HOW)

Agents use Skills inside SCWs. Agents form loops. A loop binds to a partition.
The free tier ships exactly one formation — maker / checker / judge — and that
is a deliberate scope choice, not a limitation of the runtime.

---

## The Gate

Everything above is architecture. This is the mechanism, and it is the whole of
what v0.6.0 adds.

**In Claude Code, the gate location is the tool call.**

A tool call is the only moment at which an agent running inside a subagent
context becomes visible to anything outside it. Between two tool calls a
subagent is a sealed box. At a tool call it must ask the host for something, and
the host can watch, record, and refuse.

Claude Code exposes exactly this. `PreToolUse` and `PostToolUse` fire for tool
calls made *inside* subagents, and the hook payload carries `agent_id` and
`agent_type` — present only when the call originates in a subagent. `PreToolUse`
may return `permissionDecision: deny` with a reason that is surfaced to the
model. `SubagentStart` and `SubagentStop` bracket the subagent's life.

So one resident component sits at every tool call, in every SCW, at once. It:

1. **attributes** the call to a bound role, or records that it could not;
2. **records** it as a first-class runtime event with that attribution;
3. **decides** it against the role's declared scope — allow, or refuse with the
   runtime's own message and hint.

This is what the design has been calling superposition at the gates. It is not a
metaphor about a model: a hook is, by construction, present at every crossing in
every partition simultaneously. In this tier the gate observes and enforces. The
message-passing tier — an external agent reaching a `Maxey#` inside a specific
SCW through a specific skill gate — uses the same locations and is out of scope
for the open release.

### What the Gate makes true

| before | after |
|---|---|
| refusals are provoked by the harness testing itself | refusals are provoked by agents attempting access |
| `scw.read` = 0 while agents read 63 files | every agent read is an event with a role attached |
| the filesystem is an unmeasured side channel | reaching outside scope is a recorded refusal |
| containment is asserted about the runtime | containment is asserted about the agents |

On the evidence ladder this repo already committed to
(`docs/ROADMAP.md`, 0.4.0), it is the promotion that matters:

```
weakest    agent says "I cannot see that"
           agent requests it, the runtime rejects, the event is recorded
strongest  attempt -> enforcement -> denial -> event persisted
           -> replay reproduces the denial
```

v0.5.0 could only reach the strongest rung by having the *harness* make the
attempt. The Gate lets a real agent make it.

### Three modes

| mode | behavior | what it is for |
|---|---|---|
| `enforce` | out-of-scope calls are denied; the refusal reaches the model | production use |
| `observe` | everything recorded, nothing blocked | measuring what agents *would* do |
| `off` | gate inert | the control condition |

`observe` is not a lesser `enforce`. It is the only way to measure the rate at
which an agent *attempts* to leave its partition, which is a property of the
formation rather than of the enforcement — and it is the experiment's most
informative cell.

### The two rules the Gate must not break

**A broken gate must never break a session.** A hook that crashes, hangs or
cannot parse its input has to let the session continue.

**A gate that fails open must say so.** Silently allowing a call it could not
evaluate would manufacture containment out of a malfunction — precisely the
error this whole version exists to correct. Every fail-open is recorded as
such, and any containment figure computed over a window containing fail-opens
is reported with that residue attached.

The same discipline governs attribution. When the gate cannot map a call to a
role it records `actor: unattributed` and never guesses. Unattributed calls are
**residue that weakens a containment claim**, not noise to be dropped — a run
with unattributed calls has not established containment for those calls, and the
report must say so rather than average them away.

---

## What this repo is, and is not

> **Maxey0 provides the address space. Something else decides how to use and
> measure it.**

That rule decided what belongs here through v0.5.0 and still does. What changes
in v0.6.0 is the product framing, which had been understated:

> Maxey0 is a **semantic, observability, interpretability and explainability
> layer for context-engineered agentic loops.**

Partitioning is how it obtains the signal. The signal is the point. A partition
nobody can see the effects of is a configuration file; a partition whose every
crossing is attributable, recorded and replayable is an instrument.

The four words are not synonyms and each names a different question, answered by
a different mechanism. Stated in order, because each depends on the one above it:

| | the question | what answers it | without it |
|---|---|---|---|
| **Observability** | *What happened?* | The Gate. Every crossing recorded, attributed to a role, replayable. | You have a partition whose effects nobody can see. |
| **Interpretability** | *What does it mean?* | The partition itself, which gives each event a coordinate: this was role R reaching region Y, inside or outside its closure. | You have a log of tool calls, which is telemetry, not meaning. |
| **Explainability** | *Why was it allowed or refused?* | The runtime's own message and hint, carried on the refusal that produced them. | You have an outcome and a story about it, invented afterwards. |
| **Semantics** | *Why this shape at all?* | The concept graph and the anchor field: why this concept, this loop, these roles, this scope. | You can explain every decision inside a formation you cannot justify choosing. |

Semantics is the one that is easy to leave out and the one that makes the other
three about *Maxey0* rather than about logging in general. Observability tells
you role R read a file. Interpretability tells you it was outside R's closure.
Explainability gives you the refusal that stopped it. Only semantics answers why
R existed, why it was bound to that region, and why this concept's formation was
the right one for the task — and routing is half of what Maxey0 does, so a stack
without it can explain the execution while leaving the choice unexamined.

**Where semantics is split across the tiers**, because it has two distinct jobs:

- **Semantics as explanation — open.** Why this concept, why this loop, why this
  role got this scope. Already present: `loops_route` returns `where`, `how` and
  `evidence`, and the evidence names the precedence that decided it, the levels
  tried, what was considered, and what was rejected and why. A routing miss is
  reported as a finding about library coverage rather than hidden. This is
  static, read-only, and belongs in the open release because a routing decision
  nobody can interrogate is not explainable at all.

- **Semantics as address — not open.** The live gate-vector field: gate
  coordinates that *move* as the concept graph grows, so an external agent can
  resolve "where is the gate for skill S in concept C" at any moment, and so
  adding a concept re-places the entry points rather than invalidating them.
  That only matters once there are many concepts and agents outside the process
  addressing them, and it needs a server to be true continuously rather than at
  build time. It is a different product from a single well-instrumented loop.

---

## Portability

The architecture must survive outside Claude Code, so the Gate is specified as a
protocol before it is specified as a hook.

```
        ┌─────────────────────────────────────────┐
        │  gate_core   — host-agnostic decision    │
        │  decide(ToolEvent, WindowState) -> Decision │
        └─────────────────────────────────────────┘
             ▲              ▲              ▲
      claude_code       codex          generic
      (hooks.json)   (adapter)     (CLI / HTTP)
```

`gate_core` imports nothing host-specific. An adapter's only job is to normalize
its host's event into a `ToolEvent` and translate a `Decision` back into
whatever that host understands.

Hosts differ in what they can do with a decision, and the protocol degrades
honestly rather than pretending otherwise: a host that can block gets
`enforce`; a host that can only observe gets `observe` and is **reported as
observe-only**, never as enforcement. A host with no interception at all is
supported only in the degenerate sense that its runs are marked as
ungated — which is a valid experimental condition and an invalid containment
claim.

---

## Tiers

**v0.7.0 is the final free production release.** It is not a preview, a trial,
or a staging post — it is a finished instrument for one concept and one
formation, and it will keep working exactly as it does now.

### What the free release is

Everything on this page, and every claim it makes is one you can fail:

- **All three planes**, each installable on its own, 50 tools between them.
- **The full partition model** — five region types, scopes, bridges with TTLs,
  harnesses, and the `maker_checker` architecture that makes self-approval a
  refusal rather than a policy.
- **The Gate in all three modes**, with its own hash-chained journal, plus the
  Gate Protocol and its adapters for hosts that are not Claude Code.
- **Containment tested, not declared** — four assertions, two of which attempt a
  real read through the real authorization path, and an access matrix that
  probes every (role, region) pair.
- **The maker/checker/judge formation**, with a role agent per position.
- **The whole library, readable** — 16 concepts, 83 skills, 67 agents, 84
  hardened loops, each carrying its real hardening record.
- **The Studio**, nine views, no install required.
- **The ledger**, which replays to an identical window, and the honesty rules
  that govern every number it produces.

There is no metered call, no key to obtain, and nothing that stops working when
a subscription lapses, because there is no subscription. The Studio's optional
Anthropic client uses **your** key, or falls back to a simulation.

### What is deliberately not here

These are not features withheld to create an upgrade path. Each is a **different
product** that a single well-instrumented loop does not need, and shipping a
half-version of any of them would put code in this repository whose purpose is
to make a particular study succeed.

| | why it is elsewhere |
|---|---|
| **Scale across concepts** — routing and formation selection over a library that grows past what one person curates | Needs a service that stays true continuously rather than at build time. This repo's library is a fixed, inspectable dataset, which is the honest shape for a local install. |
| **Message-passing through gates** — an external agent reaching a `Maxey#` inside a specific SCW, through a specific skill gate | Requires the gate-vector field below, plus an addressing authority. Both are network concerns. |
| **The semantic gate-vector field** — gate coordinates that move as the concept graph grows, so adding a concept re-places entry points instead of invalidating them | Only matters once there are many concepts and agents outside the process addressing them. |
| **The nested MCP hierarchy** — `Maxey0` holding a 1:1 with a server, `Maxey1` in SCW1 doing the same, so an external agent can address a nested orchestrator directly | Entry *into* the plane from outside is a different security model from partitioning a window you already control. |
| **The experiment harness** | Moved to the `maxey0-lab` connector. A measurement instrument that ships the study it was used for is a lab notebook with an installer. |

The line is drawn where it is because scale across concepts and external entry
into the plane are different products from a single well-instrumented loop —
not because the single loop was crippled to make a point. Everything needed to
partition a window, bind roles, dispatch them, refuse what leaves scope, and
prove what actually happened is in this repository, under Apache-2.0.

---

## Standing constraints

Unchanged, and they govern this document too.

- **Never fabricate a number.** Every figure traces to a runtime call.
- **Null is not zero**, not false, not clean. It means the quantity was never
  established; it goes in the residue.
- **A refusal is evidence**, carrying its message, its hint, and the operation
  it prevented. Never route around one to make an operation succeed.
- **Success is earned.** Never convert `exhausted`, `incomplete` or
  `unverified` into `success`.
- **A routing miss is a finding** about library coverage, not an error to hide.
- **`server/vendor/` is generated.** Never hand-edit it; re-vendor instead.
- **Enforced information access is not proven representational independence.**
  Level 1 of the disjointness table is enforced; levels 2 and 3 are not, and no
  amount of gate telemetry changes that.
