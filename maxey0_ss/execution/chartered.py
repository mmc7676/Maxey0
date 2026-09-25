"""Put the charter in the path of a real agent run.

The gap this closes: SCWs enforced boundaries that no agent ever actually ran
behind. A formation dispatched through the host's own subagent mechanism was
contained by that mechanism, not by any charter, and the containment report in
the plugin's cross-window module inspected prompts the module had written
itself rather than anything that was sent.

A `CharteredFormation` assembles each agent's brief *through the gate*. Content
is deposited into a window; an agent's brief is built by asking the containment
provider, artifact by artifact, whether that agent may read that window. What is
refused is not included — not because the agent was asked to ignore it, but
because it never reaches the agent's input at all.

That distinction is the whole point:

    Enforcement by construction, not by instruction.

An agent cannot exceed its charter by disregarding it, because the charter
decides what exists in its context in the first place. The model is never
consulted about its own boundary, which is what makes the result evidence rather
than testimony.

**What this attests, precisely.** The chain records what each agent was
*supplied* and what was *withheld*, with a reason for each. It does not record
what the model did with what it received — no external mechanism can observe
that. A containment claim that stayed inside the agent would be unfalsifiable;
this one is checkable, and narrower for being so.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..containment.hierarchy import Constitution, ConstitutionTree
from ..containment.protocol import Operation
from ..containment.structural import StructuralContainment
from ..identity import spec_id_of
from ..models import SCWInstance, SemanticAddress


@dataclass(frozen=True)
class Artifact:
    """One piece of content residing in a window."""

    scw_id: str
    name: str
    content: str

    @property
    def tokens(self) -> int:
        """Approximate size. Used for accounting, never for a decision."""
        return max(0, len(self.content) // 4)


@dataclass
class Brief:
    """What one agent was given, and what it was refused.

    `withheld` is the part that matters. A refusal leaves no trace inside an
    agent — not seeing something produces no event — so it has to be recorded
    here, where it is a positive fact rather than an absence.
    """

    agent_scw: str
    task: str
    supplied: list[Artifact] = field(default_factory=list)
    withheld: list[tuple[str, str]] = field(default_factory=list)

    @property
    def supplied_tokens(self) -> int:
        return sum(a.tokens for a in self.supplied)

    def render(self) -> str:
        """The agent's actual input. Contains only what the charter granted."""
        parts = [f"TASK: {self.task}", ""]
        for artifact in self.supplied:
            parts.append(f"--- {artifact.name} (from {artifact.scw_id}) ---")
            parts.append(artifact.content)
            parts.append("")
        return "\n".join(parts)

    def manifest(self) -> dict[str, object]:
        return {
            "agent_scw": self.agent_scw,
            "supplied": [
                {"scw": a.scw_id, "name": a.name, "tokens": a.tokens} for a in self.supplied
            ],
            "withheld": [{"scw": s, "name": n} for s, n in self.withheld],
            "supplied_tokens": self.supplied_tokens,
        }


class CharteredFormation:
    """A chartered SCW hierarchy that real agents are dispatched behind."""

    def __init__(self, root: str = "SCW0", reach: set[str] | None = None, **caps) -> None:
        self.tree = ConstitutionTree()
        # The provider owns the log, so it must exist before the grant is made.
        # Chartering the root straight onto the tree left the one decision that
        # bounds every crossing below it out of the chain, and the chain still
        # verified as intact — an unbounded root was indistinguishable from a
        # bounded one in the exported evidence.
        self.provider = StructuralContainment(tree=self.tree)
        self.provider.charter_root(
            root, Constitution(reach=frozenset(reach) if reach is not None else None, **caps)
        )
        self.root = root
        self.artifacts: list[Artifact] = []
        self._register(root, readable=set())

    # -- shape --------------------------------------------------------------

    def _register(self, scw_id: str, readable: set[str]) -> None:
        self.provider.register(
            SCWInstance(
                id=scw_id,
                spec_id=spec_id_of(scw_id),
                owner=self.root,
                runtime_id="chartered",
                address=SemanticAddress("maxey0", "context", "formation", spec_id_of(scw_id)),
                readable=set(readable),
                writable={scw_id},
            )
        )

    def charter(self, scw_id: str, reach: set[str], parent: str | None = None) -> Constitution:
        """Add a window under the root (or another window) with a bounded reach.

        `reach` is both the constitution and the declared read set, so a window
        cannot be chartered wide and then declared narrow, or the reverse.
        """
        granted = self.provider.charter(
            scw_id, parent or self.root, Constitution(reach=frozenset(reach))
        )
        self._register(scw_id, readable=set(reach))
        return granted

    # -- content ------------------------------------------------------------

    def deposit(self, scw_id: str, name: str, content: str) -> Artifact:
        """Place content in a window. It is reachable only per the charter."""
        artifact = Artifact(scw_id, name, content)
        for index, existing in enumerate(self.artifacts):
            if (existing.scw_id, existing.name) == (scw_id, name):
                # Replace rather than append. accounting() keys distinct content
                # by (scw, name), so a second artifact under the same name was
                # billed in the total and dropped from distinct — reporting real
                # content as duplication.
                self.artifacts[index] = artifact
                return artifact
        self.artifacts.append(artifact)
        return artifact

    def brief(self, agent_scw: str, task: str) -> Brief:
        """Assemble an agent's input through the gate.

        Every artifact is a separate decision, so the chain records the shape of
        what each agent could see rather than one summary judgement about it.
        """
        brief = Brief(agent_scw=agent_scw, task=task)
        for artifact in self.artifacts:
            decision = self.provider.decide(Operation.READ, agent_scw, artifact.scw_id)
            if decision.allowed:
                brief.supplied.append(artifact)
            else:
                brief.withheld.append((artifact.scw_id, artifact.name))
        return brief

    # -- evidence -----------------------------------------------------------

    def evidence(self) -> dict[str, object]:
        """The chain summary, plus whether it verifies."""
        summary = self.provider.log.summary()
        return {**summary, "verified": self.provider.log.verify().ok}

    def crossings(self) -> list[dict[str, object]]:
        return [entry.decision.as_dict() for entry in self.provider.log.entries()]

    def accounting(self, briefs: list[Brief]) -> dict[str, object]:
        """What the partition cost, and what it withheld.

        `duplicated_tokens` is the copying overhead: content supplied to more
        than one window is paid for once per window. It is reported rather than
        optimized away, because the alternative — sharing a region across
        windows — is exactly what the charter refuses.
        """
        seen: dict[tuple[str, str], int] = {}
        total = 0
        for brief in briefs:
            for artifact in brief.supplied:
                key = (artifact.scw_id, artifact.name)
                seen[key] = seen.get(key, 0) + 1
                total += artifact.tokens
        distinct = sum(
            next(a.tokens for a in self.artifacts if (a.scw_id, a.name) == key) for key in seen
        )
        return {
            "supplied_tokens_total": total,
            "distinct_tokens": distinct,
            "duplicated_tokens": total - distinct,
            "withheld_count": sum(len(b.withheld) for b in briefs),
        }


__all__ = ["Artifact", "Brief", "CharteredFormation"]
