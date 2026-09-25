# maxey0-ui

The typed client and React views for the Maxey0 Studio.

**Optional, and deliberately so.** `python server/run_studio.py` serves the
standard-library Studio on a bare Python 3.10+ with no `npm install`, and that
promise is worth more than a uniform stack: an operator diagnosing a containment
question at 2am should not have to build a front end first. This package
compiles into `server/maxey0_studio/static/app/`, is served by the same Python
process when present, and changes nothing when absent.

## What it adds

**A typed boundary against the tool catalog.** `src/generated/catalog.ts` is
emitted from `server/planes/catalog.py` by
`scripts/generate_ui_types.py`, so renaming a tool in Python turns every stale
use here into a compile error. A front end that agrees with its backend by
convention stops agreeing the first time someone is in a hurry.

**Two distinctions the type system now enforces**, in `src/api/types.ts`:

- `Contained` is `boolean | null`, not `boolean`. Null means nothing was
  attempted, which establishes nothing in either direction. Typing it as a
  boolean makes `if (!contained)` read as a breach, and a run where nothing was
  attempted renders as a failure.
- `StreamResponse` is a union, narrowed by `isProjection`. The endpoint returns
  a summary when nothing is filtered and a list when something is, and `events`
  is a count in one and an array in the other. Reading it as an array either way
  silently renders "no events" over a run that had hundreds — which is exactly
  the bug the union prevents, and there is a test for it.

## Commands

```bash
npm install
npm run check     # tsc --noEmit, then vitest
npm run build     # type-check, then build into the Python package
npm run dev       # Vite on :5177, proxying /api to a Studio on :7676
```

`npm run dev` talks to a Studio you started separately, so the two restart
independently.

## Regenerating the catalog

```bash
python scripts/generate_ui_types.py
python scripts/generate_ui_types.py --check   # verify; run by validate_plugin.py
```

The generated file is committed. A generated file nobody reviews is a file
nobody reads.
