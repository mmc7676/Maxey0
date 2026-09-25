# Workload specs

A spec is the input to `/maxey0:experiment-run`. It says what work to do and how
to measure it. The harness ships with no workload of its own — swapping the spec
is the only change needed to run a different experiment.

Specs here are loadable by id (`maxey0-website`). A spec kept anywhere else on
disk is loadable by path, which is how a spec that lives in its own repository
gets run without copying it in.

## Shape

```jsonc
{
  "id": "my-workload",
  "label": "Short name for the run",
  "objective": "One sentence: what is being built and what is being measured.",

  // Each condition names a cell in the design. Three axes:
  //
  //   partition — WHERE the work runs
  //     scw   : each role bound to its own region, isolation enforced
  //     flat  : one shared region, every role bound to it (the control)
  //
  //   routing — HOW the formation was chosen  (default: "maxey0")
  //     maxey0   : execute the formation routing actually selected
  //     baseline : execute the spec's declared `baseline_loop`, and never
  //                let the control see Maxey0's decision
  //
  //   gating — WHETHER THE AGENTS WERE WATCHED  (default: "off")
  //     off      : the gate is inert. The pre-0.6.0 condition, kept as the
  //                default so an older spec keeps meaning what it meant.
  //                Every gate metric reports null — null is not zero; nothing
  //                was watching, so nothing was observed either way.
  //     observe  : every intercepted call recorded, none blocked. NOT a weaker
  //                `enforce` — it is the only way to measure how often a role
  //                ATTEMPTS to leave its partition, which is a property of the
  //                formation rather than of the enforcement.
  //     enforce  : out-of-scope calls refused, and the refusal reaches the model.
  //
  // A bare string is shorthand for
  // {"id": s, "partition": s, "routing": "maxey0", "gating": "off"}.
  "conditions": [
    { "id": "scw",  "partition": "scw",  "routing": "maxey0" },
    { "id": "flat", "partition": "flat", "routing": "maxey0" }
  ],

  // Required as soon as ANY condition sets gating != "off". It names how a tool
  // call will be tied back to the role that made it:
  //   "agent_id" : the host reports a per-actor id on the tool event
  //                (Claude Code and the Claude Agent SDK only)
  //   "cwd"      : each role is dispatched in its own working directory —
  //                portable to every host, and it resolves before the call
  // Without it the harness REFUSES the spec rather than degrading to "off",
  // because a gated run that cannot attribute anything would report
  // unattributed residue as though it were a gating measurement.
  "gate": { "attribution": "cwd" },

  // The leak probe. `sentinel` is the exact string that counts as a refusal,
  // and it must appear in `text` — a role cannot emit a token it was never
  // shown. Grading is on that one string; nothing else is scored as a refusal.
  // Omit `probe` entirely and every leakage field reports null, not zero.
  "probe": {
    "sentinel": "CANNOT: not in my scope",
    "text": "…the probe, containing the sentinel verbatim…"
  },

  // The units of work. Each routes independently, before any model call.
  "tasks": [
    {
      "id": "short-id",
      "title": "Human-readable title",
      "task": "What the role is being asked to do, in plain language.",
      "deliverable": "Optional: what to hand back.",

      // Required only when some condition uses routing:"baseline".
      // The control formation. Never derived from Maxey0's decision.
      "baseline_loop": "battery:l3-pipeline",

      // Optional. The set of formations you consider task-valid, S(T).
      // Declaring it turns on routing correctness:  R = 1[chosen ∈ valid].
      "valid_loops": ["pipeline:057-…", "battery:l3-pipeline"]
    }
  ]
}
```

## Rules the harness enforces

- `tasks` must be non-empty, and every task needs an `id` and a `task`.
- Every condition needs an `id`; `partition` must be `scw` or `flat`, and
  `routing` must be `maxey0` or `baseline`.
- If any condition uses `routing: "baseline"`, **every task must declare
  `baseline_loop`**. The harness will not quietly fall back to the routed loop —
  that would make the control a copy of the treatment and the comparison
  vacuous.
- If a probe has text, its `sentinel` must appear in that text.
- A task that routes to no loop produces no calls for that condition. It is
  reported as a `loop_coverage_gap` in the residue rather than reassigned to a
  substitute loop — an uncovered task is a finding about the library, not an
  error.

## On `valid_loops` and routing correctness

`valid_loops` is **your declared judgment** about which formations are
appropriate for a task. It is not derived from what routing does, on purpose:
grading a decision against itself measures nothing.

So a run can report `reliability: 0.0` while every task completes successfully.
That is not a failure of the harness — it is the measurement working. Routing
correctness and execution success are separate quantities, and a formation that
produced good output may still not be one you would have picked.

When they disagree, the useful next question is which side is wrong: your
declared set, or the routing. Both answers are findings.

## Shipped specs

| id | design | what it asks |
|---|---|---|
| `maxey0-website` | 2 cells, partition axis | Does WHERE change containment, cost and leakage? |
| `maxey0-routing-efficacy` | 2 cells, routing axis | Does Maxey0's HOW beat a control formation? |
| `maxey0-factorial` | 4 cells, both axes | Does WHERE change how well HOW works? |
| `maxey0-gating` | 3 cells, gating axis | What is containment worth once the agents are watched? |

The factorial reports pairwise deltas and tags which axes differ in each pair.
It does not collapse them into a score: the interaction term exists to expose a
tradeoff, and a composite would hide it.

`maxey0-gating` exists because of a measured gap. Through 0.5.0 every refusal in
the log had been provoked by the harness testing itself; not one came from an
agent attempting access, because nothing recorded what a delegated agent did.
The gating axis makes three quantities measurable for the first time:

| metric | what it is |
|---|---|
| `out_of_scope_attempt_rate` | how often a role reached outside its partition, whether or not it was stopped — a property of the **formation** |
| `agent_provoked_refusals` | refusals caused by an agent, as distinct from the synthetic negative controls the harness issues against itself |
| `unattributed_calls` / `gate_residue` | calls the gate saw but could not tie to a role, and calls it could not evaluate — reported separately, never folded into a rate |

The comparison of interest is **observe vs enforce**: `observe` measures what the
formation does, `enforce` measures what the boundary prevented, and a large gap
between them means the partition is doing work the prompt alone was not.
