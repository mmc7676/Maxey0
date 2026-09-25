---
description: What is up, what is down, and what is missing — connectors, ledger, Gate, runtime provenance
allowed-tools: mcp__maxey0-loops__loops_menu, mcp__maxey0-observe__observe_gate_mode, mcp__maxey0-observe__observe_events, mcp__maxey0-observe__observe_gate_activity, Bash
---

Report the health of this installation. Check each item, then give one table.

## 1. Which planes are reachable

Call `loops_menu(section="planes")`. For each plane report the connector name,
its tool count, and whether it imports here.

If `loops_menu` itself is unreachable, the Loop plane is down; say so and
continue with the rest rather than stopping.

## 2. The Context plane's ledger

Call `observe_events()`. Report `present` and `records`.

**`present: false` is not a failure.** It means nothing has been recorded at
that path, which establishes nothing in either direction. Say that, rather than
reporting zero containment.

## 3. The Gate

Call `observe_gate_mode()` for the mode, then `observe_gate_activity()`.

`available: false` means no subagent has run yet — the Gate records nothing
until there is a delegated call to intercept. That is the expected state on a
fresh install, not a fault.

If activity exists, report `chain` verification and `containment.claimable`
verbatim. If `claimable` is false, name the residue.

## 4. The runtime this process actually loaded

```bash
python -c "import sys; sys.path.insert(0,'server'); from planes import bootstrap; bootstrap.prepare(); import json; print(json.dumps(bootstrap.provenance(), indent=2))"
```

`vendored: true` is what you want. `false` means an editable install elsewhere
on the machine is shadowing `server/vendor/`, so the code running is not the
code that shipped. Report the path it actually loaded.

## 5. Interpreter

```bash
python -V && python -c "import mcp; print('mcp', mcp.__name__, 'ok')"
```

A connector that will not start is almost always one of three things: `python`
resolving to something that is not the interpreter you think (on Windows, the
Microsoft Store alias), `mcp` missing from that interpreter, or a stale entry in
your own MCP config pointing at a path that no longer exists. Name which one.

## Report

One table: component · state · evidence. Then, if anything is down, the single
next action — not a list of possibilities.
