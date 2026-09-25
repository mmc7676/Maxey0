---
description: Run an externally defined workload spec to completion and report it — the harness supplies prompts, you supply the model calls
argument-hint: "[spec-id|spec-path|exp-id]"
allowed-tools: Bash, Task
---

Run a workload spec against the Maxey0 runtime and report what the runtime did:
**$ARGUMENTS**

This command has **no workload of its own.** `$ARGUMENTS` names one — a spec id,
a path to a spec file, or an existing run id to resume. If none is given, list
the available specs and stop.

## Why this is not part of the product

The three planes are a measurement instrument. This is the study. Shipping the
study inside the instrument makes the instrument's claims unfalsifiable, so the
harness lives here, in a connector you install on purpose, and nothing in the
three planes depends on it.

## The loop

Driven over HTTP against the Studio, not over MCP — the harness holds run state
across many model calls, which is a server's job rather than a tool's.

1. **List or load.**
   ```bash
   curl -s http://127.0.0.1:7676/api/experiments/specs
   ```
   Start the Studio first with `/maxey0:studio` if that fails.

2. **Create the run.**
   ```bash
   curl -s -X POST http://127.0.0.1:7676/api/experiments/create \
     -H 'content-type: application/json' -d '{"spec":"<spec-id>"}'
   ```

3. **Take the next call.**
   ```bash
   curl -s "http://127.0.0.1:7676/api/experiments/status?id=<exp-id>"
   ```
   It returns the next pending call and the prompt to send, already built for
   that condition. Send it **verbatim** as one subagent.

4. **Probe for leaks in the same turn.** If the call declares a sentinel, send
   the probe to the **same agent** immediately, in the same turn, with
   SendMessage. Agent transcripts do not survive: a probe sent promptly
   succeeds, and one sent later fails with "no transcript found" — which is a
   missing measurement, not a negative result.

5. **Ingest.**
   ```bash
   curl -s -X POST http://127.0.0.1:7676/api/experiments/ingest \
     -H 'content-type: application/json' \
     -d '{"id":"<exp-id>","call":"<call-id>","response":"<raw>"}'
   ```
   Ingest what came back. Editing a response on the way in edits the evidence.

6. **Repeat until nothing is pending, then report.**
   ```bash
   curl -s "http://127.0.0.1:7676/api/experiments/report?id=<exp-id>"
   ```

## Reporting rules

These are not style preferences. A measurement instrument that rounds its own
results in its own favor is worse than no instrument.

- **Never fabricate a number.** Every figure traces to a runtime call. If a
  quantity was not measured, it is missing, not zero.
- **Null is not zero.** It means the quantity was never established. It goes in
  the residue.
- **Report cost in call counts and tokens**, never in dollars.
- **Below three probes is `underpowered`.** Say so instead of reporting a rate.
- **A routing miss is a finding** about library coverage, not an error to hide.
- **A null result is a result.** Report it as one.
- **Success is earned.** Never convert `exhausted`, `incomplete` or
  `unverified` into `success`.

## The three axes a spec may declare

| axis | values |
|---|---|
| `partition` | `scw` / `flat` |
| `routing` | `maxey0` / `baseline` |
| `gating` | `off` / `observe` / `enforce` |

`observe` is the most informative gating cell, not the weakest: it measures how
often a role *attempts* to leave its partition, which is a property of the
formation rather than of the enforcement.
