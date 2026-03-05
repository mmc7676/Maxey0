# Latent Space Theory (Maxey0 Latent Space Lab)

This document describes the geometric framework used in the Maxey0 Latent Space Lab.

---

## Latent Space

Modern AI models represent information in high-dimensional vector spaces called **latent spaces**.

Each point in the latent space corresponds to a representation of a concept, token, or model state.

Nearby points represent semantically or functionally similar states.

The lab provides tools for mapping and observing trajectories through these spaces.

---

## Constitutional Axes

The system defines a human-interpretable coordinate system using **64 constitutional axes**.

Each axis represents a conceptual dimension such as:

- helpfulness
- safety
- reasoning depth
- alignment
- abstraction

These axes act as an interpretable basis for positioning model states in a designed latent coordinate system.

---

## Latent Trajectories

Model reasoning or agent workflows can be interpreted as **paths through latent space**.

Tracking these paths enables:

- experiment replay
- trajectory analysis
- dataset generation
- state transition analysis

Trajectories allow researchers to observe how systems move between conceptual regions of representation space.

---

## Voronoi Partitions

Voronoi partitions divide a space into regions around a set of seed points.

In the latent lab they represent **nearest-concept regions**.

Each Voronoi cell corresponds to the area of latent space closest to a particular reference state.

This allows visualization of conceptual boundaries between model states.

---

## Delaunay Triangulation

The **Delaunay triangulation** is the dual graph of a Voronoi partition.

It connects points whose regions share a boundary.

In the latent lab it is used to represent:

- possible transitions between states
- neighborhood structure
- latent topology

The resulting graph provides a structural map of nearby states in representation space.

---

## Experiment Observability

The system captures snapshots of latent states and stores them in a KV cache.

These snapshots allow:

- replay of model reasoning
- trajectory inspection
- training dataset generation
- experiment reproducibility

Snapshots make it possible to analyze how latent states evolve over time during experiments.

---

## Research Goal

The Maxey0 Latent Space Lab is intended as a research environment for:

- interpretable representation design
- latent space geometry exploration
- dataset generation for representation learning models
- experiment observability for AI systems

The project aims to provide an experimental platform for studying how AI systems move through representation space and how those movements can be measured, visualized, and reused for training data.