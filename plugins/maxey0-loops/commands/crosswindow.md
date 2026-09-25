---
description: "Run a cross-window topology: one separate subagent call per participant, zero shared context"
argument-hint: "<designer:NN-slug> [run-id]"
allowed-tools: mcp__maxey0-loops__loops_crosswindow_create, mcp__maxey0-loops__loops_crosswindow_status, mcp__maxey0-loops__loops_crosswindow_ingest, mcp__maxey0-loops__loops_crosswindow_report, Task
---

Run a cross-window topology to completion: **$ARGUMENTS**

Cross-window is a **different architecture** from the in-window runtime, not a
lesser one. There is no region, no scope, and no runtime refusal. Isolation
comes from one genuinely separate model call per participant with zero shared
token buffer — enforced by what *you* put in each prompt.

So treat every prompt you construct as a partition boundary. Here you are the
enforcement mechanism, and the report at the end is what checks your work.

## The loop

1. `loops_crosswindow_create(loop_id="<designer:NN-slug>")`, or resume with the
   run id if one was given.
2. `loops_crosswindow_status(run_id=...)` for the next pending call.
3. Dispatch that call's prompt **verbatim** as one subagent
   (`subagent_type: maxey0-role`). Never reuse a subagent across participants —
   a reused context is a shared context, and the topology is then a fiction.
4. `loops_crosswindow_ingest(run_id=..., call_id=..., response=<raw response>)`.
   Ingest the response as it came back; editing it on the way in edits the
   evidence.
5. Repeat until no calls are pending.
6. `loops_crosswindow_report(run_id=...)`.

## The report

It greps every dispatched prompt for the other participants' markers — real
leak detection over the actual text, not an assertion that there was none.

**A leak it finds is the finding, not a bug to quietly fix and rerun.** Report
it with the participant and the marker that leaked. A clean run reports
`bound_holds: true`; say which of the two you got.

## The five topologies

`designer:01-horizontal-4way` · `designer:02-vertical-chain` ·
`designer:03-star-broker` · `designer:04-mesh-consensus` ·
`designer:05-multiround-persistence`

Call `loops_crosswindow_create` with no valid slug to have the plane list them
rather than guessing.
