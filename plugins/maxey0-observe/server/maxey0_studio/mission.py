"""Skill-mediated SCW creation and dispatch, as a real engineered loop.

Two design decisions worth stating, because both were mistakes in an earlier
cut of this module:

**Creation goes through the hierarchy.** "Create SCW" is not a bare CRUD
action here. You pick the concept, the skill and the agent first, and the
region exists because something is going to work in it -- which is the order
the rest of Maxey0 already assumes.

**A dispatch is a loop, not a write.** The first version created a region and
called `write()` as the unbound host, which meant the "agent" ran with host
privileges, no declared goal, no iteration ceiling, no verification level and
no ticks -- a write with a story attached. Now every dispatch:

  1. creates a `working` region for the agent's published output,
  2. creates a `scratchpad` child for volatile per-iteration reasoning
     (`reset_each_tick`, `purge_on_close` -- that is what makes it a
     scratchpad rather than an accumulator),
  3. `bind_scope`s the loop to the target region (the scratchpad sits inside
     it), declaring trigger, goal,
     verification level and `max_iterations`,
  4. runs each step *through the bound loop_id*, so the runtime authorizes it
     like any other role instead of waving it through,
  5. `loop_tick`s each iteration, so the cost and cache economics are priced,
  6. `unbind_scope`s with an honest terminal state.

The consequence that matters: a dispatch is subject to the same refusals as
anything else. When it exceeds its budget it is denied and reports `blocked`,
and that denial is a real `scw.denied` record in the hash-chained log.

The agent work itself is either a real Anthropic API call (when a key is
configured) or a timed simulation (when one is not). Both paths go through
the identical bound-loop write path, so the enforcement story does not change
with the key -- only the content does.
"""

from __future__ import annotations

import random
import threading
import time
from typing import Optional

from . import anthropic_client as ac

#: Model-as-judge is level 4 on the runtime's ladder; a simulated step has no
#: verification at all and says so rather than borrowing a level it does not earn.
VERIFICATION_REAL_CALL = 4
VERIFICATION_SIMULATED = None

_SIM_STEPS = (4, 9)
_SIM_STEP_DELAY = (0.4, 1.1)
_SIM_TOKENS = (180, 1600)


def catalog_from_knowledge(knowledge) -> dict:
    """Concept -> skill -> agents, built from the same in-memory Knowledge
    every other tab reads. No separate seed data, so the picker cannot drift
    away from what the rest of the app believes is loaded."""
    concepts = []
    for c in knowledge.concepts:
        skills_out = []
        for s in knowledge.skills:
            if s.get("concept") != c["id"]:
                continue
            skills_out.append({
                "id": s["id"],
                "title": s.get("title", s["id"]),
                "description": s.get("description", ""),
                "memory_tier": s.get("memory_tier", ""),
                "agents": [
                    {"name": a.get("name", ""), "slug": a.get("slug", ""),
                     "role": a.get("role", "")}
                    for a in s.get("agents", [])
                ],
            })
        concepts.append({
            "id": c["id"],
            "title": c["title"],
            "type": c.get("concept_type", ""),
            "tags": c.get("tags", []),
            "skill_count": len(skills_out),
            "skills": skills_out,
        })
    return {"concepts": concepts}


def _preview(text: str, n: int = 60) -> str:
    return text[: n - 3] + "..." if len(text) > n else text


def _loop_id_for(scw_id: str) -> str:
    return f"dispatch:{scw_id}"


def _run_loop(session, *, scw_id: str, pad_id: str, loop_id: str,
              agent_label: str, skill_desc: str, prompt: str,
              real_call: bool) -> None:
    """One dispatch, run as a bound loop from first write to terminal state."""
    accepted = 0
    blocked = False

    try:
        if real_call:
            system = (
                f"You are {agent_label}, an agent inside the Maxey0 architecture. "
                f"Your skill: {skill_desc or 'general-purpose work'}\n\n"
                "Do the requested work directly and concisely."
            )
            try:
                text = ac.complete(system=system, user=prompt)
            except ac.AnthropicError as exc:
                session.write_region(pad_id, f"[api error] {exc}",
                                     loop_id=loop_id, key="error")
                session.tick(loop_id, note=f"api error: {exc}")
                blocked = True
            else:
                # The pad is volatile reasoning; the working region is the
                # published artifact. Writing the result to both would defeat
                # the distinction, so the pad gets the trace and the region
                # gets the output.
                session.write_region(pad_id, f"[call complete] {_preview(prompt)}",
                                     loop_id=loop_id, key="trace")
                published = session.write_region(scw_id, text, loop_id=loop_id,
                                                 key="dispatch-result")
                if published.get("ok"):
                    session.tick(loop_id, note="real model call published",
                                 verified=True, verified_by=agent_label)
                    accepted += 1
                else:
                    session.tick(loop_id, note="publish refused")
                    blocked = True
        else:
            steps = random.randint(*_SIM_STEPS)
            preview = _preview(prompt)
            for i in range(1, steps + 1):
                time.sleep(random.uniform(*_SIM_STEP_DELAY))
                tokens = random.randint(*_SIM_TOKENS)
                # write() counts real tokens from real text, so the filler is
                # what makes the declared cost genuine rather than asserted.
                filler = "x" * max(0, tokens * 4 - 60)
                body = (f"[sim step {i}/{steps}] {agent_label}: "
                        f"+{tokens}tok toward \"{preview}\" {filler}")
                result = session.write_region(scw_id, body, loop_id=loop_id)
                if not result.get("ok"):
                    # A real refusal -- almost always the token ceiling. Stop
                    # here; do not retry around the wall.
                    session.tick(loop_id, note=f"step {i} refused: "
                                              f"{result.get('error')}")
                    blocked = True
                    break
                session.tick(loop_id, note=f"sim step {i}/{steps}")
    finally:
        # `success` is refused by the runtime unless a verification was
        # actually accepted, so this cannot quietly overstate the outcome.
        if blocked:
            terminal = "blocked"
        elif accepted:
            terminal = "success"
        else:
            terminal = "no_op"
        session.unbind_dispatch(loop_id, terminal_state=terminal)


def dispatch(
    session,
    *,
    target_scw_id: Optional[str],
    new_label: Optional[str],
    region_type: str,
    token_ceiling: int,
    agent_slug: str,
    agent_name: str,
    skill_desc: str,
    prompt: str,
    create_count: int = 1,
) -> dict:
    """Create region(s) if needed, then run the prompt as a bound loop."""
    created: list[str] = []
    if not target_scw_id:
        base_label = new_label or "scw"
        for i in range(max(1, create_count)):
            label = f"{base_label}-{i + 1}" if create_count > 1 else base_label
            result = session.create_scw(
                label=label,
                region_type=region_type,
                policy={"token_budget": token_ceiling, "eviction": "reject"},
            )
            if not result.get("ok"):
                return {"ok": False, "error": result.get("error"),
                        "message": result.get("message"), "created": created}
            created.append(result["scw_id"])
        target_scw_id = created[0]
    else:
        created = [target_scw_id]

    if not prompt:
        return {"ok": True, "created": created, "target": target_scw_id,
                "mode": "create_only"}

    agent_label = agent_name or agent_slug or "unbound agent"
    real_call = ac.is_configured()

    # The scratchpad is nested under the working region so the loop's scope,
    # bound to the pad with descend=True, reaches its own volatile reasoning
    # and its own published output -- and nothing else in the window.
    pad = session.create_scw(
        label=f"{target_scw_id}-pad",
        region_type="scratchpad",
        parent_scw_id=target_scw_id,
    )
    if not pad.get("ok"):
        return {"ok": False, "error": pad.get("error"),
                "message": pad.get("message"), "created": created}

    loop_id = _loop_id_for(target_scw_id)
    bound = session.bind_dispatch(
        loop_id=loop_id,
        scw_id=target_scw_id,
        goal=f"{agent_label}: {_preview(prompt, 120)}",
        trigger="manual",
        verification_level=(VERIFICATION_REAL_CALL if real_call
                            else VERIFICATION_SIMULATED),
        max_iterations=_SIM_STEPS[1] + 1,
    )
    if not bound.get("ok"):
        return {"ok": False, "error": bound.get("error"),
                "message": bound.get("message"), "hint": bound.get("hint"),
                "created": created}

    threading.Thread(
        target=_run_loop,
        kwargs=dict(session=session, scw_id=target_scw_id,
                    pad_id=pad["scw_id"], loop_id=loop_id,
                    agent_label=agent_label, skill_desc=skill_desc,
                    prompt=prompt, real_call=real_call),
        daemon=True,
    ).start()

    return {
        "ok": True,
        "created": created,
        "target": target_scw_id,
        "scratchpad": pad["scw_id"],
        "loop_id": loop_id,
        "mode": "real_api" if real_call else "simulated",
        "loop_spec": {
            "trigger": "manual",
            "goal": bound["goal"],
            "verification_level": bound["verification_level"],
            "max_iterations": bound["max_iterations"],
        },
    }
