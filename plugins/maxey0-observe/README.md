# maxey0-observe

**Observatory plane** — Record what happened, and refuse what left scope.

The Observatory plane, alone. The Gate stands at every tool call — the only moment an agent in a delegated context has to ask its host for something, and so the only place an outside observer can stand. It attributes each call to the role that made it, records it in its own hash-chained journal, and in enforce mode refuses the ones reaching outside that role's declared scope. That is global workspace semantics, and it needs no window and no library to be useful. It reads the Context plane's ledger from disk when one exists, so it can report what the evidence supports across a process boundary; a run carrying residue — an unattributed call, a fail-open, a lost record — reports its containment as not claimable rather than clean. Installs inert: the default mode records and blocks nothing. 8 tools and the Studio.

## What it owns

The Gate, the event stream, correlated traces, isolation levels, and the Studio.

## Worth installing alone because

Attribute and refuse any delegated agent's tool calls — global workspace semantics — with no window and no library.

## The 8 tools

| tool | writes | does |
|---|---|---|
| `observe_events` | no | The Context plane's ledger as a typed, queryable stream. |
| `observe_attempts` | no | Did this role attempt this region, and what happened. contained is three-valued; null means nothing was attempted. |
| `observe_traces` | no | The context, execution and state traces, correlated causally. |
| `observe_gate_mode` | yes | Read or set the Gate: enforce, observe, or off. |
| `observe_gate_policy` | yes | Declare what a bound role may reach outside the window. |
| `observe_gate_activity` | no | What the delegated agents actually did, per role, from the journal. |
| `observe_isolation_level` | no | Which of L0-L3 the evidence supports, and the shortfall where it is below what was declared. |
| `observe_studio` | no | The Studio's address and start command. |

## Commands

- `/maxey0-observe:gate`
- `/maxey0-observe:studio`

## Install

```bash
/plugin marketplace add mmc7676/Maxey0
/plugin install maxey0-observe@maxey0
```

Requires Python 3.10+ with the `mcp` package on the interpreter that `python` resolves to.

## This directory is generated

`scripts/build_planes.py` builds it from the repository root, where the commands, agents, hooks and skills have their single source of truth, and `server/` is copied whole rather than shimmed, because an installed plugin cannot read a file outside its own directory. Do not edit anything here; edit the root and regenerate.

See [docs/LEXICON.md](../../docs/LEXICON.md) for the naming rules and [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) for why the planes divide where they do.
