# Maxey0 Platform Architecture

Maxey0 is a **research platform** containing multiple applications.

## Principle

- Treat **Latent Space Lab** as the first application, not the entire platform.
- Preserve experimental and research artifacts unless explicitly instructed to remove them.
- Keep repository navigation easy for researchers and developers unfamiliar with the project.

## Target platform layout

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

## Current state

The active Next.js implementation remains in the root workspace for backwards compatibility:

- UI/API code: `src/`
- deterministic data: `data/`
- references/theory: `docs/`
- utilities: `scripts/`

This keeps the lab runnable now while clarifying platform boundaries for future applications.
