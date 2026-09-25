# maxey0-loops

**Loop plane** — Decide who should act, and in what shape.

The Loop plane, alone. Route a task against 16 concepts, 83 skills, 67 agents and 84 hardened loops, and get the formation that was already built for it instead of an improvised maker/checker pair — in one measured case, 10,800 tokens against 253,000 for the same task done by hand. Every loop carries its real hardening record, so a design that has never been executed says so. This plane holds no window state at all, which is what lets it run against an entirely fixed context scheme with nothing else installed. 10 tools, including the cross-window runner that checks isolation by grepping the actual dispatched prompts rather than asserting it held.

## What it owns

The library — 16 concepts, 83 skills, 67 agents, 84 hardened loops — plus routing and cross-window topologies.

## Worth installing alone because

Route a task to a pre-scoped formation and run it against a fixed context scheme, with no enforcement engine installed.

## The 10 tools

| tool | writes | does |
|---|---|---|
| `loops_menu` | no | The whole Maxey0 control surface, rendered from the registry. |
| `loops_concepts` | no | The 16 concepts, their tag vocabularies, and their loop coverage. |
| `loops_skills` | no | The 83 skills, grouped by concept, with the agents each one binds. |
| `loops_agents` | no | The 67 registry agents and their specializations. |
| `loops_catalog` | no | The 84 hardened loops, filterable, each with its hardening record. |
| `loops_route` | no | Score a task against the library and explain the decision. Binds nothing — use context_route_bind to commit. |
| `loops_crosswindow_create` | yes | Plan a cross-window run over one of the five topologies. |
| `loops_crosswindow_status` | no | The next pending call in a cross-window run. |
| `loops_crosswindow_ingest` | yes | Record one participant's real response and splice it downstream. |
| `loops_crosswindow_report` | no | Grep every dispatched prompt for other participants' markers. Real leak detection, not an assertion that there was none. |

## Commands

- `/maxey0-loops:menu`
- `/maxey0-loops:doctor`
- `/maxey0-loops:route`
- `/maxey0-loops:crosswindow`

## Skills

16 skill(s): `agentic-loops`, `claim-verification`, `context-management`, `evaluation`, `governance`, `infrastructure`, `io-contract`, `knowledge-graph`, `latent`, `memory`, `observability`, `orchestration`, `protocol`, `reasoning`, `registry`, `superposition`

## Install

```bash
/plugin marketplace add mmc7676/Maxey0
/plugin install maxey0-loops@maxey0
```

Requires Python 3.10+ with the `mcp` package on the interpreter that `python` resolves to.

## This directory is generated

`scripts/build_planes.py` builds it from the repository root, where the commands, agents, hooks and skills have their single source of truth, and `server/` is copied whole rather than shimmed, because an installed plugin cannot read a file outside its own directory. Do not edit anything here; edit the root and regenerate.

See [docs/LEXICON.md](../../docs/LEXICON.md) for the naming rules and [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) for why the planes divide where they do.
