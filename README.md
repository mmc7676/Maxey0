# Maxey0 Research Platform

Maxey0 is a modular research platform for latent-representation and agent-behavior tooling.

**Latent Space Lab** is the first application in the platform.

## Repository shape

```text
Maxey0/
├─ apps/
│  └─ latent-space-lab/
├─ datasets/
├─ docs/
├─ research/
├─ scripts/
├─ systems/
└─ README.md
```

> For compatibility, the current Latent Space Lab implementation is still in the root Next.js workspace (`src/`, `data/`, `docs/`, `scripts/`).

## Latent Space Lab quickstart

```bash
npm install
npm run dev
```

Open `http://localhost:3000`.

## Latent Space Lab pages

1. **Constitution Designer** (`/constitution`) — edit and weight all 64 latent axes.
2. **Latent Space Mapper** (`/mapper`) — project latent points, place SCW nodes, and animate trajectories.
3. **Experiment Runner** (`/experiments`) — run experiments and record sequence snapshots.
4. **Geometry View** (`/dual-graph`) — render Voronoi partitions and Delaunay overlays.
5. **Dataset Generator** (`/datasets`) — generate/export trajectory datasets.
6. **Observability** (`/observability`) — replay snapshot transitions.

## Research artifacts policy

- Do not delete experimental or research artifacts unless explicitly instructed.
- Prefer simple research-tool architecture over production SaaS architecture.
- Keep the repository easy to explore for researchers and developers unfamiliar with the project.

## Data and persistence

- Demo latent states: `data/demo_latent_states.json` (available in mapper dataset list as `demo_latent_states`).
- SQLite database: `data/latentlab.sqlite`.
- Default constitution: `data/constitution.default.json`.

Optional helpers:

```bash
npm run db:reset
npm run demo:seed
```
