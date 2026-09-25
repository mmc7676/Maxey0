"""Generate one skill per Maxey0 concept, with its reference material bundled.

Through 0.6.0 each concept shipped a ~33-line stub whose third step told the
reader to "read the real skill via the Maxey0 knowledge base
(`/<concept>/<concept>.md`)" — a path that exists nowhere in the plugin. All 16
stubs dead-ended their own instructions, and the plugin UI's Contents tab had
nothing to show because a skill directory holding one file has no contents to
browse.

So this script now emits the material instead of pointing at it. Every concept
gets a working SKILL.md plus three reference files rendered from the vendored
manifest and loop dataset:

    SKILL.md                what to do, and when this concept applies
    reference/skills.md     the concept's skills, each with its formation
    reference/loops.md      the loops tagged with it, with hardening records
    reference/agents.md     the agents that appear in those loops

Nothing here is placeholder prose and nothing is hand-written twice: every
field comes from `server/vendor/`. Regenerate after `scripts/sync_vendor.py`
picks up a knowledge-base change:

    python scripts/generate_concept_skills.py
    python scripts/generate_concept_skills.py --check   # verify, write nothing

`skills/scw/SKILL.md` is the one hand-written, load-bearing skill and this
script never touches it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "server" / "vendor"
SKILLS = ROOT / "skills"

#: Hand-written, never generated.
HAND_WRITTEN = {"scw"}


def _load() -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    root = Path(os.environ.get("MAXEY0_ROOT") or (VENDOR / "maxey0"))
    loops_path = Path(os.environ.get("MAXEY0_LOOPS") or (VENDOR / "data" / "loops.json"))
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    registry = json.loads((root / "registry.json").read_text(encoding="utf-8"))
    loops = json.loads(loops_path.read_text(encoding="utf-8"))["loops"]
    return manifest["concepts"], manifest["skills"], registry["agents"], loops


def _article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


# ---------------------------------------------------------------------------
# SKILL.md
# ---------------------------------------------------------------------------

def skill_md(concept: dict, skills: list[dict], loops: list[dict]) -> str:
    cid = concept["id"]
    title = concept.get("title", cid)
    ctype = concept.get("concept_type", "architecture")
    tags = concept.get("tags", [])
    head = ", ".join(tags[:5])

    description = (
        f"{title} — {_article(ctype)} {ctype} concept covering {head}. "
        f"Use when the user's task concerns {title.lower()}, or matches: "
        f"{', '.join(tags)}. Route with loops_route first — this concept's "
        f"{len(skills)} skills and {len(loops)} loops are listed in "
        f"reference/, and a coherent hit often names a different concept's "
        f"formation."
    )

    by_status = Counter(l.get("status", "unknown") for l in loops)
    status_line = ", ".join(f"{n} {s}" for s, n in sorted(by_status.items())) or "none yet"

    if loops:
        coverage = (
            f"{len(loops)} loop(s) in the library are tagged `{cid}` "
            f"({status_line}). They are listed with their hardening records in "
            f"[reference/loops.md](reference/loops.md)."
        )
        route_note = (
            f"2. **Browse what already exists.** "
            f"`loops_catalog(concept=\"{cid}\")` returns the same loops with "
            f"their live status. Prefer one of them to anything hand-built."
        )
    else:
        coverage = (
            f"**No loop in the library is tagged `{cid}` yet.** That is a real "
            f"gap in library coverage rather than a reason to stop: the "
            f"concept's {len(skills)} skill(s) still name real formations, and "
            f"a task that routes here is worth recording as a miss."
        )
        route_note = (
            f"2. **Expect a fallback.** Nothing is tagged `{cid}`, so "
            f"`loops_route` will fall back to skills or agents. Say so plainly "
            f"— a routing miss is information about the library, not an error "
            f"to hide."
        )

    lines = [
        "---",
        f"name: {cid}",
        f'description: "{description}"',
        "---",
        "",
        f"# {title}",
        "",
        f"**{ctype.title()} concept** · {len(skills)} skill(s) · "
        f"{len(loops)} loop(s) tagged `{cid}`",
        "",
        f"Vocabulary: {', '.join(f'`{t}`' for t in tags)}",
        "",
        "## When this applies",
        "",
        f"A task concerns `{cid}` when it matches that vocabulary — but matching "
        "the vocabulary is not the same as belonging here. Route first and let "
        "the decision be examinable.",
        "",
        "## What to do",
        "",
        '1. **Route.** Call `loops_route(task="...")` with the task in plain '
        "language. It scores the task across concepts, skills and agents and "
        "returns the evidence for its decision — what it considered, what it "
        "rejected, and why. It binds nothing.",
        route_note,
        "3. **Bind, if you are going to run it.** `context_route_bind` asks the "
        "same question and commits: it binds the matching loop's partition in "
        "this session's own window. Without the Context plane installed, "
        "routing still answers; it just cannot be followed by a bind.",
        "",
        "## What ships with this skill",
        "",
        "| file | contents |",
        "|---|---|",
        f"| [reference/skills.md](reference/skills.md) | the {len(skills)} "
        "skill(s) under this concept, each with the agent formation bound to it |",
        f"| [reference/loops.md](reference/loops.md) | the {len(loops)} loop(s) "
        "tagged `" + cid + "`, with provenance, status and hardening record |",
        "| [reference/agents.md](reference/agents.md) | the registry agents that "
        "appear in those loops, and what each specializes in |",
        "",
        coverage,
        "",
        "## The rule that carries",
        "",
        "A refusal is a result. If the runtime refuses a read, report it with "
        "its own message and hint rather than routing around it — the hint "
        "names the bridge that would make the access legal, and whether that "
        "access is justified is a decision to make explicitly.",
        "",
        "See [skills/scw](../scw/SKILL.md) for how partitioning and routing "
        "actually work.",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# reference/
# ---------------------------------------------------------------------------

def skills_md(concept: dict, skills: list[dict]) -> str:
    out = [f"# {concept.get('title', concept['id'])} — skills", ""]
    out += [
        f"The {len(skills)} skill(s) this concept owns, from the Maxey0 "
        "manifest. Each names the agent formation already bound to it: a "
        "`primary` that produces, a `checker` that verifies, and `support` "
        "roles around them.",
        "",
        "That formation is why routing beats improvising. A pre-scoped "
        "formation for the matched skill is almost always cheaper and better "
        "targeted than a hand-written maker/checker pair.",
        "",
    ]
    for s in skills:
        out.append(f"## `{s['id']}`")
        out.append("")
        out.append(f"**{s.get('title', s['id'])}**")
        out.append("")
        if s.get("description"):
            out.append(s["description"])
            out.append("")
        meta = []
        if s.get("memory_tier"):
            meta.append(f"memory tier: `{s['memory_tier']}`")
        if s.get("tags"):
            meta.append("tags: " + ", ".join(f"`{t}`" for t in s["tags"]))
        if meta:
            out.append(" · ".join(meta))
            out.append("")
        agents = s.get("agents") or []
        if agents:
            out.append("| agent | role |")
            out.append("|---|---|")
            for a in agents:
                out.append(f"| {a.get('name', '')} | `{a.get('role', '')}` |")
            out.append("")
    return "\n".join(out)


def loops_md(concept: dict, loops: list[dict]) -> str:
    cid = concept["id"]
    out = [f"# {concept.get('title', cid)} — loops", ""]
    if not loops:
        out += [
            f"No loop in the 84-entry library is tagged `{cid}`.",
            "",
            "That is recorded rather than hidden. A concept with skills but no "
            "hardened loop is a coverage gap: the formations exist, but no one "
            "has yet built and executed a partition for them against a live "
            "window. A task that routes here will fall back to skills or "
            "agents, and that fallback is the finding.",
            "",
        ]
        return "\n".join(out)

    out += [
        f"The {len(loops)} loop(s) tagged `{cid}`. Every entry is a real "
        "composition whose regions, roles and refusals were built against a "
        "live window before it was written down.",
        "",
        "**Status is evidence, not decoration.** `validated` means it was "
        "executed and the result recorded. `partial` means some of it was. "
        "`draft-unexecuted` means it has never run — treat it as a design, not "
        "a guarantee.",
        "",
    ]
    for l in loops:
        out.append(f"## `{l['id']}`")
        out.append("")
        out.append(f"**{l.get('title', '')}**")
        out.append("")
        out.append(
            f"status `{l.get('status', '')}` · provenance `{l.get('provenance', '')}` "
            f"· mode `{l.get('execution_mode', '')}` · topology "
            f"`{l.get('topology', '')}`"
        )
        out.append("")
        stages = l.get("agent_stages") or []
        if stages:
            out.append(f"{len(stages)} stage(s): " +
                       " → ".join(s.get("agent_name", "") for s in stages))
            out.append("")
        hard = l.get("hardening") or {}
        if hard:
            rows = [f"| {k} | {v} |" for k, v in hard.items()
                    if not isinstance(v, (dict, list))]
            if rows:
                out.append("| hardening | |")
                out.append("|---|---|")
                out += rows
                out.append("")
        if l.get("notes"):
            out.append(f"> {l['notes'][:400]}")
            out.append("")
    return "\n".join(out)


def agents_md(concept: dict, loops: list[dict], registry: list[dict]) -> str:
    cid = concept["id"]
    by_index = {a["registry_index"]: a for a in registry}
    seen: dict[str, int] = {}
    for l in loops:
        for s in l.get("agent_stages") or []:
            aid = s.get("agent_id")
            if aid:
                seen[aid] = seen.get(aid, 0) + 1

    out = [f"# {concept.get('title', cid)} — agents", ""]
    if not seen:
        out += [
            f"No loop is tagged `{cid}`, so no agent appears in one.",
            "",
            "The concept's skills still name their formations — see "
            "[skills.md](skills.md).",
            "",
        ]
        return "\n".join(out)

    out += [
        f"The {len(seen)} registry agent(s) that appear in loops tagged "
        f"`{cid}`, ordered by how often.",
        "",
        "These are library entries, not shipped Claude Code agents. A loop "
        "stage names one of these; the subagent it is dispatched as is one of "
        "the four role agents this plugin ships — `maxey0-maker`, "
        "`maxey0-checker`, `maxey0-judge`, `maxey0-role`.",
        "",
        "| agent | stages | specialization |",
        "|---|---|---|",
    ]
    for aid, n in sorted(seen.items(), key=lambda kv: (-kv[1], kv[0])):
        rec = by_index.get(aid, {})
        name = rec.get("name", aid)
        spec = (rec.get("specialization") or "").replace("|", "\\|")[:160]
        out.append(f"| {name} (`{aid}`) | {n} | {spec} |")
    out.append("")
    return "\n".join(out)



# ---------------------------------------------------------------------------
# skills/scw/reference/ — generated from the tool catalog, not the manifest
# ---------------------------------------------------------------------------

def _catalog():
    sys.path.insert(0, str(ROOT / "server"))
    from planes import catalog
    return catalog


NEWLINE = chr(10)


def scw_reference() -> dict[Path, str]:
    """The three reference files bundled with the hand-written `scw` skill.

    Generated from `server/planes/catalog.py` so the skill cannot describe a
    tool the product does not register.
    """
    cat = _catalog()

    planes = ["# The three planes", ""]
    planes += [
        "Maxey0 is three planes. Each is a separately installable connector "
        "with its own MCP server, its own commands, and its own skills. Each "
        "is useful alone. The Observatory can see the other two, and neither "
        "of the other two can see it.",
        "",
        "That asymmetry is the design rather than an accident. A boundary you "
        "can see through is not a boundary — so the resolution is not to let "
        "the orchestrator see inside every partition, it is to make the "
        "boundary itself the thing that is observable, from outside.",
        "",
    ]
    for pid in ("context", "loops", "observe"):
        meta = cat.CONNECTORS[pid]
        planes += [
            f"## {meta['title']} — `{meta['connector']}`",
            "",
            f"*{meta['tagline']}*",
            "",
            f"**Owns.** {meta['owns']}",
            "",
            f"**Alone.** {meta['alone']}",
            "",
            f"{len(cat.BY_CONNECTOR[pid])} tools.",
            "",
        ]
    planes += [
        "## The rule that assigns a tool to a plane",
        "",
        "The window is process-local state. A tool in another process would "
        "act on a different window — so every tool that touches the live "
        "window lives on the Context plane, including the four containment "
        "assertions and the binding router. The Loop plane holds no window "
        "state at all, which is exactly what lets it run standalone. The "
        "Observatory reads both other planes as files, and replays the "
        "ledger when it needs structure rather than a record list.",
        "",
    ]

    tools = [f"# The {len(cat.ALL)} tools", "",
             "Every tool name begins with its plane. Generated from the "
             "catalog, so this list is what the product registers.", ""]
    for pid in ("context", "loops", "observe"):
        meta = cat.CONNECTORS[pid]
        tools += [f"## {meta['title']} — `{meta['connector']}`", ""]
        groups: dict = {}
        for t in cat.BY_CONNECTOR[pid]:
            groups.setdefault(t.group, []).append(t)
        for group, entries in groups.items():
            tools += [f"### {group}", "", "| tool | writes | does |", "|---|---|---|"]
            for t in entries:
                tools.append(f"| `{t.name}` | {'yes' if t.mutates else 'no'} | {t.summary} |")
            tools.append("")

    mig = ["# Migration from 0.6.0", "",
           "Every retired name, and what replaced it. The old names are gone "
           "rather than aliased: an alias would double the surface and let the "
           "old vocabulary survive in transcripts, which is the drift 0.7.0 "
           "exists to end.", "",
           "| 0.6.0 | 0.7.0 |", "|---|---|"]
    for legacy, canonical in sorted(cat.RETIRED.items()):
        mig.append(f"| `{legacy}` | `{canonical}` |")
    mig += ["", "## Commands", "", "| 0.6.0 | 0.7.0 |", "|---|---|",
            "| `/maxey0:scw` | `/maxey0:window` |",
            "| `/maxey0:loop` | `/maxey0:run` |",
            "| `/maxey0:cross-window` | `/maxey0:crosswindow` |",
            "| `/maxey0:experiment-run` | removed from the product; see the "
            "`maxey0-lab` connector |",
            "", "## Connectors", "", "| 0.6.0 | 0.7.0 |", "|---|---|",
            "| `worlds` | `maxey0-context` (plus `maxey0-observe` for the Gate) |",
            "| `maxey0` | `maxey0-loops` |", "",
            "## Agents", "", "| 0.6.0 | 0.7.0 |", "|---|---|",
            "| `agent-role` | `maxey0-role`, and `maxey0-maker` / "
            "`maxey0-checker` for those positions |",
            "| `loop-judge` | `maxey0-judge` |", ""]

    return {
        Path("reference/planes.md"): NEWLINE.join(planes),
        Path("reference/tools.md"): NEWLINE.join(tools),
        Path("reference/migration.md"): NEWLINE.join(mig),
    }


# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="verify the generated tree matches the manifest; write nothing")
    args = ap.parse_args()

    concepts, all_skills, registry, all_loops = _load()
    drift: list[str] = []
    written = 0

    for concept in concepts:
        cid = concept["id"]
        if cid in HAND_WRITTEN:
            continue
        skills = [s for s in all_skills if s.get("concept") == cid]
        loops = [l for l in all_loops if cid in (l.get("concept_tags") or [])]

        files = {
            Path("SKILL.md"): skill_md(concept, skills, loops),
            Path("reference/skills.md"): skills_md(concept, skills),
            Path("reference/loops.md"): loops_md(concept, loops),
            Path("reference/agents.md"): agents_md(concept, loops, registry),
        }
        for rel, text in files.items():
            target = SKILLS / cid / rel
            if args.check:
                current = target.read_text(encoding="utf-8") if target.exists() else None
                if current != text:
                    drift.append(str(target.relative_to(ROOT)))
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
            written += 1

    for rel, text in scw_reference().items():
        target = SKILLS / "scw" / rel
        if args.check:
            current = target.read_text(encoding="utf-8") if target.exists() else None
            if current != text:
                drift.append(str(target.relative_to(ROOT)))
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
            written += 1

    if args.check:
        if drift:
            print("skill tree has drifted from the manifest:")
            for d in drift:
                print(f"  {d}")
            print("\nrun: python scripts/generate_concept_skills.py")
            return 1
        print(f"skills: {len(concepts) - len(HAND_WRITTEN)} concepts, generated tree matches the manifest")
        return 0

    print(f"wrote {written} files across "
          f"{len([c for c in concepts if c['id'] not in HAND_WRITTEN])} concepts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
