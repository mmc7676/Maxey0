"""3D coordinates for the semantic plane -- by trilateration, not by decoration.

Every node's (x, y) is its weighted position in Maxey0's own anchor field
(`data/anchors.json`: four anchors at fixed coordinates, each with a real tag
vocabulary). A node's tags are scored against each anchor's tags, and the node
lands at the score-weighted centroid of the anchors it resonates with. This is
the same operation the `maxey0_trilaterate` MCP tool performs -- so a cluster on
screen means the nodes genuinely share anchor vocabulary, not that a layout
algorithm happened to put them together.

`z` is the hierarchy level, which is the one axis that is assigned rather than
measured: concepts sit above skills sit above agents. That is a statement about
the hierarchy, and it is labeled as such in the UI.

Nodes matching no anchor vocabulary get `unanchored: true` and are placed on a
deterministic ring at the field's edge rather than being silently dropped at the
origin, where they would read as "maximally central" -- the opposite of the truth.
"""

from __future__ import annotations

import math
import re
from typing import Any, Iterable

LEVEL_Z = {"concept": 120.0, "skill": 0.0, "agent": -120.0}
RING_RADIUS = 190.0


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2}


def _score_against(anchor: dict, tags: Iterable[str], text: str) -> float:
    """Exact tag match is worth 2.0, a substring appearance 0.5 -- the same
    weighting Maxey0's manifest tag scoring uses everywhere else."""
    tagset = {t.lower() for t in tags}
    haystack = text.lower()
    score = 0.0
    for anchor_tag in anchor.get("tags", []):
        at = anchor_tag.lower()
        if at in tagset:
            score += 2.0
        elif re.search(rf"\b{re.escape(at)}\b", haystack):
            score += 1.0
        elif at in haystack:
            score += 0.5
    return score


def place(anchors: list[dict], tags: Iterable[str], text: str,
          level: str, ring_index: int, ring_total: int) -> dict:
    """Weighted-centroid trilateration against the anchor field."""
    tags = list(tags)
    scores = [(a, _score_against(a, tags, text)) for a in anchors]
    total = sum(s for _, s in scores)

    if total <= 0:
        angle = (2 * math.pi * ring_index) / max(ring_total, 1)
        return {
            "x": round(RING_RADIUS * math.cos(angle), 2),
            "y": round(RING_RADIUS * math.sin(angle), 2),
            "z": LEVEL_Z[level],
            "unanchored": True,
            "anchor_scores": {},
            "dominant": None,
        }

    x = sum(a["x"] * s for a, s in scores) / total
    y = sum(a["y"] * s for a, s in scores) / total
    dominant = max(scores, key=lambda pair: pair[1])[0]["id"]

    return {
        "x": round(x, 2),
        "y": round(y, 2),
        "z": LEVEL_Z[level],
        "unanchored": False,
        "anchor_scores": {a["id"]: round(s, 2) for a, s in scores if s > 0},
        "dominant": dominant,
    }


def _jitter(nodes: list[dict], min_sep: float = 7.0, passes: int = 60) -> None:
    """Separate exactly-coincident nodes without moving them meaningfully.

    Nodes with identical tag vectors trilaterate to identical points and would
    render as one dot. This nudges them apart deterministically (seeded by index,
    no randomness) so the count you see matches the count that exists. Movement
    is capped well under anchor spacing, so it never changes which cluster a
    node reads as belonging to.
    """
    for _ in range(passes):
        moved = False
        for i, a in enumerate(nodes):
            for b in nodes[i + 1:]:
                if a["z"] != b["z"]:
                    continue
                dx, dy = b["x"] - a["x"], b["y"] - a["y"]
                dist = math.hypot(dx, dy)
                if dist >= min_sep:
                    continue
                if dist < 1e-6:
                    angle = 2 * math.pi * (i % 12) / 12.0
                    dx, dy, dist = math.cos(angle), math.sin(angle), 1.0
                push = (min_sep - dist) / 2.0
                ux, uy = dx / dist, dy / dist
                a["x"] -= ux * push
                a["y"] -= uy * push
                b["x"] += ux * push
                b["y"] += uy * push
                moved = True
        if not moved:
            break
    for n in nodes:
        n["x"], n["y"] = round(n["x"], 2), round(n["y"], 2)


def build_field(knowledge: Any) -> dict:
    """The full three-level semantic field, ready for the 3D view."""
    anchors = knowledge.anchors
    nodes: list[dict] = []
    edges: list[dict] = []

    # -- level 1: concepts --------------------------------------------------
    concepts = knowledge.concepts
    for i, concept in enumerate(concepts):
        pos = place(anchors, concept.get("tags", []),
                    f"{concept['id']} {concept.get('title', '')}",
                    "concept", i, len(concepts))
        nodes.append({
            "id": f"concept:{concept['id']}",
            "label": concept.get("title", concept["id"]),
            "level": "concept",
            "ref": concept["id"],
            "tags": concept.get("tags", []),
            "meta": {"concept_type": concept.get("concept_type", "")},
            **pos,
        })

    # -- level 2: skills ----------------------------------------------------
    skills = knowledge.skills
    for i, skill in enumerate(skills):
        pos = place(anchors, skill.get("tags", []),
                    f"{skill['id']} {skill.get('title', '')} "
                    f"{skill.get('description', '')}",
                    "skill", i, len(skills))
        nodes.append({
            "id": f"skill:{skill['id']}",
            "label": skill.get("title", skill["id"]),
            "level": "skill",
            "ref": skill["id"],
            "tags": skill.get("tags", []),
            "meta": {"concept": skill.get("concept", ""),
                     "memory_tier": skill.get("memory_tier", "")},
            **pos,
        })
        if skill.get("concept"):
            edges.append({"source": f"concept:{skill['concept']}",
                          "target": f"skill:{skill['id']}", "kind": "has_skill"})

    # -- level 3: agents ----------------------------------------------------
    agents = knowledge.agents
    for i, agent in enumerate(agents):
        assignments = agent.get("assignments", [])
        agent_tags: list[str] = []
        for assignment in assignments:
            skill_id = assignment.get("skill", "")
            match = next((s for s in skills if s["id"] == skill_id), None)
            if match:
                agent_tags.extend(match.get("tags", []))
        text = (f"{agent.get('name', '')} {agent.get('specialization', '')} "
                + " ".join(a.get("concept", "") for a in assignments))
        pos = place(anchors, agent_tags, text, "agent", i, len(agents))
        nodes.append({
            "id": f"agent:{agent['registry_index']}",
            "label": f"{agent['registry_index']} {agent.get('name', '')}",
            "level": "agent",
            "ref": agent["registry_index"],
            "tags": sorted(set(agent_tags))[:12],
            "meta": {"specialization": agent.get("specialization", ""),
                     "provenance": agent.get("provenance", ""),
                     "assignments": len(assignments)},
            **pos,
        })
        for assignment in assignments:
            if assignment.get("skill"):
                edges.append({
                    "source": f"skill:{assignment['skill']}",
                    "target": f"agent:{agent['registry_index']}",
                    "kind": "performed_by",
                    "role": assignment.get("role", ""),
                })

    for level in ("concept", "skill", "agent"):
        _jitter([n for n in nodes if n["level"] == level])

    known = {n["id"] for n in nodes}
    resolved = [e for e in edges if e["source"] in known and e["target"] in known]

    return {
        "ok": True,
        "anchors": [
            {"id": a["id"], "x": float(a["x"]), "y": float(a["y"]),
             "z": 0.0, "color": a.get("c", "#888"), "tags": a.get("tags", [])}
            for a in anchors
        ],
        "levels": [
            {"level": "concept", "z": LEVEL_Z["concept"], "label": "Concepts"},
            {"level": "skill", "z": LEVEL_Z["skill"], "label": "Skills"},
            {"level": "agent", "z": LEVEL_Z["agent"], "label": "Agents"},
        ],
        "nodes": nodes,
        "edges": resolved,
        "stats": {
            "nodes": len(nodes),
            "edges": len(resolved),
            "dropped_edges": len(edges) - len(resolved),
            "unanchored": sum(1 for n in nodes if n.get("unanchored")),
        },
        "method": "weighted-centroid trilateration against data/anchors.json; "
                  "z is the assigned hierarchy level, not a measured dimension",
    }
