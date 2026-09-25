# maxey0

Most agent infrastructure primarily adds capability to the execution plane. Maxey0 makes the contextual environment surrounding agentic execution an independently structured, routable, partitionable, and observable plane, while providing an engineering plane that can observe and tune both.

The full stack: all three planes, ten slash commands, the role-agent slate, the Gate, and the Studio. 50 tools. Start here unless you know you want one plane.

## Commands

- `/maxey0:menu`
- `/maxey0:doctor`
- `/maxey0:window`
- `/maxey0:route`
- `/maxey0:run`
- `/maxey0:crosswindow`
- `/maxey0:gate`
- `/maxey0:assert`
- `/maxey0:studio`
- `/maxey0:scw-deploy`

## Skills

17 skill(s): `agentic-loops`, `claim-verification`, `context-management`, `evaluation`, `governance`, `infrastructure`, `io-contract`, `knowledge-graph`, `latent`, `memory`, `observability`, `orchestration`, `protocol`, `reasoning`, `registry`, `scw-default-deployer`, `superposition`

## Install

```bash
/plugin marketplace add mmc7676/Maxey0
/plugin install maxey0@maxey0
```

Requires Python 3.10+ with the `mcp` package on the interpreter that `python` resolves to.

## This directory is generated

`scripts/build_planes.py` builds it from the repository root, where the commands, agents, hooks and skills have their single source of truth, and `server/` is copied whole rather than shimmed, because an installed plugin cannot read a file outside its own directory. Do not edit anything here; edit the root and regenerate.

See [docs/LEXICON.md](../../docs/LEXICON.md) for the naming rules and [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) for why the planes divide where they do.
