---
description: The Maxey0 control surface — every plane, connector, tool, command and view, rendered from the registry
argument-hint: "[menu|context|loops|observe|commands|views|planes]"
allowed-tools: mcp__maxey0-loops__loops_menu
---

Print the Maxey0 control surface. Section: **$ARGUMENTS** (default `menu`).

## Do exactly this

1. Call `loops_menu(section="$ARGUMENTS")`, or `loops_menu()` when `$ARGUMENTS`
   is empty.
2. Render what it returned as a table. Stop.

## The one rule

**Do not describe the surface from this file.** This command used to be 296
lines of prose that told you to render the surface from a tool call, with
its own text as the fallback — so when the connectors were down it transcribed
its own instructions and appended a caveat. That is why the menu is now a tool
over the registry: what it prints is what the product registers, and it cannot
say otherwise.

If the call fails, say the Loop plane is not reachable, show the error, and
suggest `/maxey0:doctor`. Do not substitute a remembered list. An empty answer
is a finding; a confident wrong answer is a defect.

## Sections

`menu` (everything, grouped by plane) · `context` · `loops` · `observe` ·
`commands` · `views` · `planes`.

`planes` is the one to reach for when something is not working: it reports, per
plane, whether that plane's implementation actually imports in this
environment.
