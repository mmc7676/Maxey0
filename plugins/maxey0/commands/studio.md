---
description: Start the Maxey0 Studio — the browser app for the library, partitions, the Gate, and the semantic field
argument-hint: "[port]"
allowed-tools: mcp__maxey0-observe__observe_studio, Bash
---

Start the Studio and hand the user its address.

## Steps

1. Call `observe_studio()` for the address and start command. Default port
   `7676`; use `$ARGUMENTS` if a port was given.
2. Health-check before starting a second copy:

   ```bash
   curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:7676/api/knowledge
   ```

   `200` means it is already running — hand over the URL and stop.
3. Otherwise start it in the background:

   ```bash
   python server/run_studio.py --port 7676
   ```

4. Give the user the URL. Do not summarize the views unless asked; the app
   shows them.

## The nine views

| view | shows |
|---|---|
| **Overview** | Route a task in plain language and watch the decision |
| **Mission Control** | Walk concept to skill to agent to dispatch against the live window |
| **Concepts** | The 16 concepts and their loop coverage |
| **Loops** | All 84, filterable, each with its hardening record |
| **Designer** | Compose a formation and harden it before it can be saved |
| **Window** | The region map, read through any role's scope |
| **Semantic** | Concepts, skills and agents placed in the anchor field, in 3D |
| **Evidence** | Containment assertions, the event stream, isolation level |
| **Gate** | What the delegated agents actually did, per role |

## Two things to say once

The Studio binds to **loopback with no authentication**, and it renders the
contents of live regions. Do not expose the port.

It holds **its own window**, separate from the one this session's Context plane
tools act on. The Gate view is the exception: it reads the Gate's journal,
which is the same journal your session writes.
