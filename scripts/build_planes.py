"""Generate the installable plugin directories under `plugins/`.

Maxey0 is three planes, and 0.6.0 shipped them fused into one plugin declaring
two MCP servers. You could not install the Context plane without the loop
library, or the Gate without either, even though each is useful alone — and the
plugin UI's "Connectors" tab showed two servers whose names (`maxey0`,
`worlds`) did not correspond to any boundary a user could act on.

So each plane is also its own marketplace entry, installable by itself:

    plugins/maxey0            the full stack: every plane, every command
    plugins/maxey0-context    the window, and the only writer of it
    plugins/maxey0-loops      the library and the routing decision
    plugins/maxey0-observe    the Gate, the evidence, and the Studio
    plugins/maxey0-lab        the experiment harness — research tooling,
                              explicitly not part of the product

Every one of these is a **complete, self-contained copy** — its own `server/`
tree, not a shim into the repository root. An installed plugin is copied into
an isolated cache directory and cannot read a file outside it; a shim that
resolved `../../../server` worked only for the one person who cloned the
whole repository, and silently failed for anyone who installed a single
connector on its own, which is the exact case this packaging exists to serve.
Commands, agents, hooks and skills have exactly one source of truth at the
repository root; this script copies the subset each unit owns, so a command
cannot say one thing in the full stack and another in a standalone connector.

Through 0.7.1 the repository root doubled as both the marketplace and the
`maxey0` plugin itself (`"source": "./"`), so the full stack's own installed
file tree recursively contained four other plugins' `.claude-plugin/
plugin.json` manifests nested inside it — an arrangement no other marketplace
checked against this one (including Anthropic's own) ever exhibits. The root
is now the marketplace *only*; `plugins/maxey0/` is the plugin, generated like
every other installable unit here.

    python scripts/build_planes.py
    python scripts/build_planes.py --check   # verify, write nothing
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGINS = ROOT / "plugins"
SERVER_SRC = ROOT / "server"

sys.path.insert(0, str(ROOT / "server"))
from planes import catalog  # noqa: E402

VERSION = json.loads(
    (ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
)["metadata"]["version"]

AUTHOR = {"name": "mmc7676", "url": "https://github.com/mmc7676"}

#: What never gets copied into a generated plugin.
#:
#: `static/app` is the built `ui/` front end. `.gitignore` excludes it at the
#: repository root, and says why: "a committed bundle would be one more thing
#: that can drift from the source it was built from". But this copies `server/`
#: wholesale, so the moment anyone ran `npm run build` in `ui/` the bundle
#: landed in four plugin trees where nothing ignored it -- and was committed,
#: four times, exactly the thing the root rule exists to prevent. A gitignore
#: rule is not inherited by a `copytree`.
IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", ".pytest_cache", "app", "*.map",
)

#: Which skills each plane carries. One skill lives in exactly one place.
PLANE_SKILLS = {
    "context": ["scw"],
    "loops": None,   # every concept skill; resolved from the manifest
    "observe": [],
}

#: MCP server entry points a unit's `server/` copy actually runs, and the env
#: every one of them needs to find the vendored runtime inside its own copy.
SERVER_ENV = {
    "PYTHONUNBUFFERED": "1",
    "MAXEY0_ROOT": "${CLAUDE_PLUGIN_ROOT}/server/vendor/maxey0",
    "MAXEY0_LOOPS": "${CLAUDE_PLUGIN_ROOT}/server/vendor/data/loops.json",
}

MCP_ENTRY = {
    "context": ("maxey0-context", "server/context_server.py"),
    "loops": ("maxey0-loops", "server/loops_server.py"),
    "observe": ("maxey0-observe", "server/observe_server.py"),
}

DESCRIPTIONS = {
    "context": (
        "The Context plane, alone. Partition the context window into typed, "
        "policy-enforced regions and bind each role to one — the runtime "
        "decides what a role can read, not the prompt. A region declares what "
        "it is (reference, durable, episodic, working, scratchpad) and the "
        "runtime holds every call against it: a bound role reads its own "
        "region and is refused elsewhere, a read-only reference region refuses "
        "the role that consumes it, and a verdict is refused unless the "
        "judge's read closure provably excludes the maker's write closure. "
        "Every decision lands in a hash-chained ledger that replays to an "
        "identical window. `context_admit` gates what actually crosses a "
        "declared handoff — approve, summarize, redact, or reject — and "
        "`context_assert_admitted` finds any handoff a scope permits that no "
        "such decision has ever governed. 32 tools. No library, no Gate."
    ),
    "loops": (
        "The Loop plane, alone. Route a task against 16 concepts, 83 skills, "
        "67 agents and 84 hardened loops, and get the formation that was "
        "already built for it instead of an improvised maker/checker pair — in "
        "one measured case, 10,800 tokens against 253,000 for the same task "
        "done by hand. Every loop carries its real hardening record, so a "
        "design that has never been executed says so. This plane holds no "
        "window state at all, which is what lets it run against an entirely "
        "fixed context scheme with nothing else installed. 10 tools, including "
        "the cross-window runner that checks isolation by grepping the actual "
        "dispatched prompts rather than asserting it held."
    ),
    "observe": (
        "The Observatory plane, alone. The Gate stands at every tool call — "
        "the only moment an agent in a delegated context has to ask its host "
        "for something, and so the only place an outside observer can stand. "
        "It attributes each call to the role that made it, records it in its "
        "own hash-chained journal, and in enforce mode refuses the ones "
        "reaching outside that role's declared scope. That is global workspace "
        "semantics, and it needs no window and no library to be useful. It "
        "reads the Context plane's ledger from disk when one exists, so it can "
        "report what the evidence supports across a process boundary; a run "
        "carrying residue — an unattributed call, a fail-open, a lost record — "
        "reports its containment as not claimable rather than clean. Installs "
        "inert: the default mode records and blocks nothing. 8 tools and the "
        "Studio."
    ),
    "lab": (
        "Research tooling, and explicitly not part of the product. The "
        "spec-driven experiment harness: workload specs, conditions, leak "
        "probes, and reports. It shipped inside the plugin through 0.6.0 while "
        "the roadmap said since 0.3.0 that experiment protocol and analysis "
        "belong in a consumer repository — a measurement instrument that ships "
        "the study it was used for is a lab notebook with an installer. "
        "Install this only if you are running a study. Nothing in the three "
        "planes depends on it."
    ),
    "maxey0": (
        "Most agent infrastructure primarily adds capability to the execution "
        "plane. Maxey0 makes the contextual environment surrounding agentic "
        "execution an independently structured, routable, partitionable, and "
        "observable plane, while providing an engineering plane that can "
        "observe and tune both.\n\n"
        "The full stack: all three planes, {command_count} slash commands, the "
        "role-agent slate, the Gate, and the Studio. {tool_count} tools. Start here "
        "unless you know you want one plane."
    ),
}


def describe(plane: str) -> str:
    """The plane description with its counts filled from the registry.

    The literals drifted: the text said "nine slash commands" while
    catalog.COMMANDS declared ten, so the next rebuild would have republished a
    wrong count over a correct one. A number that describes the registry should
    be read from the registry.
    """
    from planes import catalog

    return DESCRIPTIONS[plane].format(
        command_count=_number(len(catalog.COMMANDS)),
        tool_count=len(catalog.ALL),
    )


_NUMBERS = {
    1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
    7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve",
}


def _number(value: int) -> str:
    return _NUMBERS.get(value, str(value))


KEYWORDS = {
    "context": ["scw", "structured-context-window", "context-engineering",
                "isolation", "partition", "maxey0"],
    "loops": ["routing", "agentic-loops", "formations", "multi-agent",
              "orchestration", "maxey0"],
    "observe": ["observability", "interpretability", "explainability", "gate",
                "hooks", "audit", "maxey0"],
    "lab": ["experiment", "measurement", "research", "maxey0"],
    "maxey0": ["scw", "context-engineering", "agentic-loops", "isolation",
               "observability", "interpretability", "explainability", "gate",
               "maxey0"],
}


def concept_skills() -> list[str]:
    manifest = json.loads(
        (ROOT / "server" / "vendor" / "maxey0" / "manifest.json").read_text(encoding="utf-8")
    )
    return sorted(c["id"] for c in manifest["concepts"] if c["id"] != "scw")


def agent_skills() -> list[str]:
    """Repo skills an agent names as "`<skill>` skill"."""
    named = set()
    for src in (ROOT / "agents").glob("*.md"):
        named.update(re.findall(r"`([a-z0-9-]+)` skill", src.read_text(encoding="utf-8")))
    return sorted(s for s in named if (ROOT / "skills" / s / "SKILL.md").is_file())


def readme(plane: str, connector: str, commands: list[str], skills: list[str]) -> str:
    meta = catalog.CONNECTORS.get(plane)
    lines = [f"# {connector}", ""]
    if meta:
        lines += [
            f"**{meta['title']} plane** — {meta['tagline']}", "",
            describe(plane), "",
            "## What it owns", "", meta["owns"], "",
            "## Worth installing alone because", "", meta["alone"], "",
            f"## The {len(catalog.BY_CONNECTOR[plane])} tools", "",
            "| tool | writes | does |", "|---|---|---|",
        ]
        for t in catalog.BY_CONNECTOR[plane]:
            lines.append(f"| `{t.name}` | {'yes' if t.mutates else 'no'} | {t.summary} |")
        lines.append("")
    else:
        lines += [describe(plane), ""]

    if commands:
        lines += ["## Commands", ""]
        lines += [f"- `/{connector}:{c}`" for c in commands]
        lines.append("")
    if skills:
        lines += ["## Skills", "", f"{len(skills)} skill(s): " +
                  ", ".join(f"`{s}`" for s in skills), ""]

    lines += [
        "## Install", "",
        "```bash",
        "/plugin marketplace add mmc7676/Maxey0",
        f"/plugin install {connector}@maxey0",
        "```", "",
        "Requires Python 3.10+ with the `mcp` package on the interpreter that "
        "`python` resolves to.", "",
        "## This directory is generated", "",
        "`scripts/build_planes.py` builds it from the repository root, where "
        "the commands, agents, hooks and skills have their single source of "
        "truth, and `server/` is copied whole rather than shimmed, because an "
        "installed plugin cannot read a file outside its own directory. Do "
        "not edit anything here; edit the root and regenerate.", "",
        "See [docs/LEXICON.md](../../docs/LEXICON.md) for the naming rules "
        "and [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) for why the "
        "planes divide where they do.", "",
    ]
    return "\n".join(lines)


def text_files_for(plane: str) -> dict[Path, str]:
    """Commands, skills, and the README — every plain-text file a unit owns."""
    connector = f"maxey0-{plane}" if plane != "maxey0" else "maxey0"
    commands = [name for name, owner, _ in catalog.COMMANDS
                if plane == "maxey0" or owner == plane]
    skills = concept_skills() if plane in ("maxey0", "loops") else PLANE_SKILLS.get(plane, [])
    if plane == "maxey0":
        # The unit that ships the agents also ships every skill an agent tells
        # the model to use. scw-deployer named `scw-default-deployer`, which no
        # plugin carried, so the agent pointed at nothing once installed.
        skills = sorted(set(skills) | set(agent_skills()))

    files: dict[Path, str] = {
        Path("README.md"): readme(plane, connector, commands, skills),
    }
    for name in commands:
        files[Path("commands") / f"{name}.md"] = (
            ROOT / "commands" / f"{name}.md"
        ).read_text(encoding="utf-8")
    for skill in skills:
        for src in sorted((ROOT / "skills" / skill).rglob("*")):
            if src.is_file():
                rel = src.relative_to(ROOT / "skills")
                files[Path("skills") / rel] = src.read_text(encoding="utf-8")
    if plane == "maxey0":
        for src in sorted((ROOT / "agents").glob("*.md")):
            files[Path("agents") / src.name] = src.read_text(encoding="utf-8")
        files[Path("hooks/hooks.json")] = (ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8")
        files[Path("hooks/session_notice.py")] = (
            ROOT / "hooks" / "session_notice.py"
        ).read_text(encoding="utf-8")
    if plane == "observe":
        # The Gate is a hook, not a server call, so the Observatory needs it
        # to be the thing CONNECTORS.md already claims it is when installed
        # alone: "attributes and can refuse any delegated agent's tool
        # calls -- global workspace semantics -- with no window and no
        # library." Without the hook there is no Gate running at all.
        files[Path("hooks/hooks.json")] = (ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8")
        # hooks.json registers SessionStart as hooks/session_notice.py. Shipping
        # the manifest without the script made every session start of an
        # observe-only install run python on a missing file (exit 2).
        files[Path("hooks/session_notice.py")] = (
            ROOT / "hooks" / "session_notice.py"
        ).read_text(encoding="utf-8")

    return files


_PLUGIN_ROOT_REF = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}[/\\]([^\"'\s\\]+)")


def missing_plugin_paths(plugin_dir: Path) -> list[str]:
    """Paths a plugin's hooks.json or plugin.json name that the plugin lacks.

    Comparing the tree with the builder's own output cannot catch this: when
    the builder forgets a file, the expected tree and the written tree agree
    and both are broken. So --check also resolves every ${CLAUDE_PLUGIN_ROOT}
    reference the host will actually execute and requires it to exist.
    """
    missing: list[str] = []
    for manifest in (plugin_dir / "hooks" / "hooks.json",
                     plugin_dir / ".claude-plugin" / "plugin.json"):
        if not manifest.exists():
            continue
        for rel in _PLUGIN_ROOT_REF.findall(manifest.read_text(encoding="utf-8")):
            if not (plugin_dir / rel).exists():
                missing.append(f"{manifest.relative_to(plugin_dir).as_posix()} -> {rel}")
    return missing


def plugin_manifest(plane: str) -> dict:
    connector = f"maxey0-{plane}" if plane != "maxey0" else "maxey0"
    manifest: dict = {
        "name": connector,
        "version": VERSION,
        "description": describe(plane),
        "author": AUTHOR,
        "homepage": "https://maxey0.com",
        "repository": "https://github.com/mmc7676/Maxey0",
        "license": "Apache-2.0",
        "keywords": KEYWORDS[plane],
    }
    if plane == "maxey0":
        manifest["mcpServers"] = {
            name: {
                "command": "python",
                "args": [f"${{CLAUDE_PLUGIN_ROOT}}/{entry}"],
                "env": dict(SERVER_ENV),
            }
            for name, entry in MCP_ENTRY.values()
        }
    elif plane in MCP_ENTRY:
        name, entry = MCP_ENTRY[plane]
        manifest["mcpServers"] = {
            name: {
                "command": "python",
                "args": [f"${{CLAUDE_PLUGIN_ROOT}}/{entry}"],
                "env": dict(SERVER_ENV),
            }
        }
    return manifest


def lab_files() -> dict[Path, str]:
    """The experiment harness, packaged as the thing it actually is."""
    files = {
        Path("README.md"): readme("lab", "maxey0-lab", ["experiment-run"], []),
    }
    src = ROOT / "plugins" / "_lab" / "experiment-run.md"
    if src.exists():
        files[Path("commands/experiment-run.md")] = src.read_text(encoding="utf-8")
    return files


#: Path parts and suffixes `_server_digest` skips, kept in step with `IGNORE`.
#:
#: The check has to ignore exactly what the copy ignores, or `--check` can never
#: pass: the source tree holds `maxey0_studio/static/app` (the built `ui/` front
#: end) and the copies deliberately do not, so a digest over everything reports
#: permanent drift and the guard becomes noise somebody learns to run past.
_DIGEST_SKIP_PARTS = frozenset({"__pycache__", "app"})
_DIGEST_SKIP_SUFFIXES = frozenset({".pyc", ".map"})


def _server_digest(path: Path) -> str:
    h = hashlib.sha256()
    for item in sorted(p for p in path.rglob("*") if p.is_file()):
        rel = item.relative_to(path)
        if _DIGEST_SKIP_PARTS & set(rel.parts):
            continue
        if item.suffix in _DIGEST_SKIP_SUFFIXES:
            continue
        h.update(rel.as_posix().encode())
        h.update(item.read_bytes())
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    #: plane -> generated text files (relative to that plane's plugin root)
    text_wanted: dict[str, dict[Path, str]] = {
        plane: text_files_for(plane) for plane in ("maxey0", "context", "loops", "observe")
    }
    text_wanted["lab"] = lab_files()

    manifests: dict[str, dict] = {
        plane: plugin_manifest(plane)
        for plane in ("maxey0", "context", "loops", "observe", "lab")
    }

    #: planes that carry their own complete copy of server/
    needs_server = ("maxey0", "context", "loops", "observe")

    if args.check:
        drift: list[str] = []
        for plane, files in text_wanted.items():
            target_dir = PLUGINS / (f"maxey0-{plane}" if plane != "maxey0" else "maxey0")
            manifest_path = target_dir / ".claude-plugin" / "plugin.json"
            current = (json.loads(manifest_path.read_text(encoding="utf-8"))
                       if manifest_path.exists() else None)
            if current != manifests[plane]:
                drift.append(str(manifest_path.relative_to(PLUGINS)))
            for rel, text in files.items():
                target = target_dir / rel
                existing = target.read_text(encoding="utf-8") if target.exists() else None
                if existing != text:
                    drift.append(str(target.relative_to(PLUGINS)))
            existing_files = {
                p.relative_to(target_dir)
                for p in target_dir.rglob("*")
                if p.is_file()
                and "server" not in p.relative_to(target_dir).parts
                and ".claude-plugin" not in p.relative_to(target_dir).parts
            } if target_dir.exists() else set()
            orphans = existing_files - set(files)
            drift += [str((target_dir / o).relative_to(PLUGINS)) for o in orphans]
            if target_dir.exists():
                drift += [f"{target_dir.name}: references missing {m}"
                          for m in missing_plugin_paths(target_dir)]

            if plane in needs_server:
                server_dir = target_dir / "server"
                if not server_dir.exists() or _server_digest(server_dir) != _server_digest(SERVER_SRC):
                    drift.append(str(server_dir.relative_to(PLUGINS)) + "/ (server copy)")

        if drift:
            for d in sorted(set(drift)):
                print(f"  drifted: {d}")
            print("\nrun: python scripts/build_planes.py")
            return 1
        print(f"plugins: {sum(len(f) for f in text_wanted.values())} text files, "
              f"{len(needs_server)} server copies match the root")
        return 0

    for plane in ("maxey0", "context", "loops", "observe", "lab"):
        target_dir = PLUGINS / (f"maxey0-{plane}" if plane != "maxey0" else "maxey0")
        if target_dir.exists():
            shutil.rmtree(target_dir)
        target_dir.mkdir(parents=True)

        manifest_path = target_dir / ".claude-plugin" / "plugin.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifests[plane], indent=2) + "\n", encoding="utf-8")

        for rel, text in text_wanted[plane].items():
            dest = target_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(text, encoding="utf-8")

        if plane in needs_server:
            shutil.copytree(SERVER_SRC, target_dir / "server", ignore=IGNORE)

    total_text = sum(len(f) for f in text_wanted.values())
    print(f"wrote {total_text} text files, {len(manifests)} manifests, and "
          f"{len(needs_server)} full server/ copies across 5 plugin directories")
    return 0


if __name__ == "__main__":
    sys.exit(main())
