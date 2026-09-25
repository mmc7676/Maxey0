"""The prompt layer: declared, versioned instruction artifacts.

From Macedo, "Stop Hand-Holding Your Coding Agent" (arXiv:2607.00038): loop
engineering sits in "the progression from prompt to context to harness to
loop. Each layer subsumes the previous one." :mod:`scw_runtime.model` and
:mod:`scw_runtime.window` are the context layer and the loop layer. This
module is the prompt layer — "how to ask" — held as data with the same
discipline the runtime already gives the other three: addressable, versioned,
policy-enforced, and hash-chained into the same event log.

A prompt is not a region. A region holds what the agent *knows*; a prompt is
the instruction that tells it what to do with what it knows, and the two
should not be allowed to blur into each other — that blurring is what lets an
agent quietly rewrite its own instructions mid-run. So a :class:`PromptSpec`
is host-authored only: no bound loop may create or revise one, under any
bridge, ever. That is the prompt-layer analogue of a `reference` region's
read-only wall, and it is enforced the same way the check-editing anti-pattern
is refused in the context layer — as a structural impossibility, not a
convention.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

SLOT = re.compile(r"\{\{(\w+)\}\}")


def declared_variables(template: str) -> tuple[str, ...]:
    """Slot names referenced in a template, in first-occurrence order."""
    seen: list[str] = []
    for name in SLOT.findall(template):
        if name not in seen:
            seen.append(name)
    return tuple(seen)


def fill(template: str, bindings: dict[str, str]) -> str:
    """Substitute `{{slot}}` placeholders. Unbound slots render as empty."""
    return SLOT.sub(lambda m: str(bindings.get(m.group(1), "")), template)


@dataclass
class PromptRevision:
    """One superseded version of a prompt, kept for provenance."""

    version: int
    template: str
    revised_seq: int

    def to_dict(self) -> dict:
        return {"version": self.version, "template": self.template, "revised_seq": self.revised_seq}


@dataclass
class PromptSpec:
    """A versioned instruction artifact — the prompt-layer unit.

    Attributes
    ----------
    template:
        Text with `{{slot}}` placeholders. Rendered against bindings at
        `render_prompt` time; never against region content directly, so a
        prompt cannot accidentally absorb untrusted context as instruction.
    variables:
        Declared slot names, taken from the template unless overridden.
        `render_prompt` refuses a binding for a name outside this set.
    locked:
        Once true, no further revision is possible — a prompt that has
        shipped and should not move under a loop's feet mid-run.
    version:
        Increments on every `revise_prompt`. A loop that bound to this
        prompt records the version it saw; the runtime flags it if the
        prompt moves out from under a still-bound loop.
    """

    prompt_id: str
    label: str
    template: str
    variables: tuple[str, ...]
    created_seq: int
    version: int = 1
    locked: bool = False
    history: list[PromptRevision] = field(default_factory=list)
    render_count: int = 0

    def to_dict(self) -> dict:
        return {
            "prompt_id": self.prompt_id,
            "label": self.label,
            "template": self.template,
            "variables": list(self.variables),
            "version": self.version,
            "locked": self.locked,
            "revisions": len(self.history),
            "render_count": self.render_count,
        }
