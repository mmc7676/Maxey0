# maxey0-lab

Research tooling, and explicitly not part of the product. The spec-driven experiment harness: workload specs, conditions, leak probes, and reports. It shipped inside the plugin through 0.6.0 while the roadmap said since 0.3.0 that experiment protocol and analysis belong in a consumer repository — a measurement instrument that ships the study it was used for is a lab notebook with an installer. Install this only if you are running a study. Nothing in the three planes depends on it.

## Commands

- `/maxey0-lab:experiment-run`

## Install

```bash
/plugin marketplace add mmc7676/Maxey0
/plugin install maxey0-lab@maxey0
```

Requires Python 3.10+ with the `mcp` package on the interpreter that `python` resolves to.

## This directory is generated

`scripts/build_planes.py` builds it from the repository root, where the commands, agents, hooks and skills have their single source of truth, and `server/` is copied whole rather than shimmed, because an installed plugin cannot read a file outside its own directory. Do not edit anything here; edit the root and regenerate.

See [docs/LEXICON.md](../../docs/LEXICON.md) for the naming rules and [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) for why the planes divide where they do.
