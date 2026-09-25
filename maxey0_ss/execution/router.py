"""Choosing a skill for a task, and saying honestly how the choice was made.

Until 0.2.0 this module imported `weighted_semantic_distance` and never called
it, scored candidates purely on keyword and category matches, and returned
`GateDecision(..., "semantic match", ...)` — a decision whose own reason string
claimed a semantic computation the code did not perform. `SkillRecord.embedding`
was populated by the HTTP API and by the worked example, and read by nothing;
this was the reader it was missing, sitting one import away.

Both halves are connected here, and the decision now says which one it used.
"""
from __future__ import annotations

from ..models import GateDecision
from ..semantic.math import cosine_distance

#: How a lexical score is composed when no embedding is available.
LEXICAL_WEIGHTS = {"name": 0.5, "concept": 0.3, "topic": 0.2}

#: How much of a blended score comes from the embedding when one exists. The
#: categorical signals stay in the mix: a skill whose vector is close but whose
#: concept is wrong is usually the wrong skill.
EMBEDDING_WEIGHT = 0.6


def _lexical(task: dict, skill) -> float:
    # `.lower()` on a non-string skill (an int from a JSON body) raised a 500.
    query = str(task.get("skill") or "").lower()
    return (
        LEXICAL_WEIGHTS["name"] * (1.0 if query and query in skill.name.lower() else 0.0)
        + LEXICAL_WEIGHTS["concept"] * (1.0 if task.get("concept") == skill.concept else 0.0)
        + LEXICAL_WEIGHTS["topic"] * (1.0 if task.get("topic") == skill.topic else 0.0)
    )


class ExecutionRouter:
    def choose_skill(self, task: dict, candidates: list, context: dict) -> GateDecision:
        """Rank candidates and admit the best one above the minimum score.

        `task["embedding"]` opts into semantic ranking. Without it — or against
        a candidate carrying no embedding, or one of a different dimension —
        the score is lexical, and `source` says `"lexical"` rather than
        claiming a match that was never computed.
        """
        query_vector = task.get("embedding")
        usable = (
            isinstance(query_vector, list)
            and len(query_vector) > 0
            and any(
                isinstance(getattr(s, "embedding", None), list)
                and len(s.embedding) == len(query_vector)
                for s in candidates
            )
        )

        ranked = []
        for skill in candidates:
            lexical = _lexical(task, skill)
            vector = getattr(skill, "embedding", None)
            comparable = (
                usable and isinstance(vector, list) and len(vector) == len(query_vector)
            )
            if comparable:
                similarity = 1.0 - cosine_distance(query_vector, vector)
                score = EMBEDDING_WEIGHT * similarity + (1 - EMBEDDING_WEIGHT) * lexical
            else:
                score = lexical
            ranked.append((score, skill, comparable))

        if not ranked:
            return GateDecision(
                False, "none", "no semantic candidate", 1.0, 1.0, "context"
            )

        score, skill, comparable = max(ranked, key=lambda x: (x[0], x[1].id))
        distance = 1.0 - score
        allowed = score >= context.get("minimum_score", 0.5)
        source = "semantic" if comparable else "lexical"
        if allowed:
            reason = (
                "semantic match against skill embedding" if comparable
                else "lexical match; no comparable embedding, so no semantic "
                     "distance was computed"
            )
        else:
            reason = "below threshold"
        return GateDecision(allowed, skill.gate_id, reason, score, distance, source)
