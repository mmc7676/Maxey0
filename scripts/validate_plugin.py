"""Validate the plugin end to end before anyone tries to install it.

Checks the things that actually break an install, in the order they break:
manifest shape, declared files existing, every Python entry point importing,
the vendored copy matching source, and the runtime genuinely enforcing
isolation rather than merely reporting that it does.

    python scripts/validate_plugin.py

Exit 0 = installable. Any failure is printed with the specific path involved.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
failures: list[str] = []
notes: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'OK ' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))
    if not ok:
        failures.append(f"{label}: {detail}")


def main() -> int:
    print("Maxey0 plugin validation\n")

    # -- 1. marketplace + the full-stack plugin manifest -------------------
    # The repository root is the marketplace only -- `.claude-plugin/
    # plugin.json` lives at `plugins/maxey0/`, a generated, installable unit
    # like every other directory under `plugins/`, not the root itself. That
    # is what keeps this plugin's own installed file tree from recursively
    # containing four other plugins' manifests, which no other marketplace
    # checked against this one (Anthropic's own included) ever does.
    print("manifest")
    marketplace_path = ROOT / ".claude-plugin" / "marketplace.json"
    check(".claude-plugin/marketplace.json exists", marketplace_path.exists(),
          str(marketplace_path))
    if not marketplace_path.exists():
        print("\nFAILED: this is the error a bad zip gives you.")
        return 1
    try:
        json.loads(marketplace_path.read_text(encoding="utf-8"))
        check("marketplace.json parses", True)
    except json.JSONDecodeError as exc:
        check("marketplace.json parses", False, str(exc))
        return 1

    plugin_root = ROOT / "plugins" / "maxey0"
    manifest_path = plugin_root / ".claude-plugin" / "plugin.json"
    check("plugins/maxey0/.claude-plugin/plugin.json exists",
          manifest_path.exists(), str(manifest_path))
    if not manifest_path.exists():
        print("\nFAILED: this is the error a bad zip gives you.")
        return 1

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        check("plugin.json parses", False, str(exc))
        return 1
    check("plugin.json parses", True)

    for key in ("name", "version", "description"):
        check(f"manifest has {key!r}", key in manifest and bool(manifest[key]))

    for name, cfg in (manifest.get("mcpServers") or {}).items():
        args = cfg.get("args") or []
        for arg in args:
            if "${CLAUDE_PLUGIN_ROOT}" not in arg:
                continue
            resolved = Path(arg.replace("${CLAUDE_PLUGIN_ROOT}", str(plugin_root)))
            check(f"mcp {name!r} entry point exists", resolved.exists(), str(resolved))
        for env_key, env_val in (cfg.get("env") or {}).items():
            if "${CLAUDE_PLUGIN_ROOT}" in env_val:
                resolved = Path(env_val.replace("${CLAUDE_PLUGIN_ROOT}", str(plugin_root)))
                check(f"mcp {name!r} env {env_key} resolves", resolved.exists(),
                      str(resolved))

    # -- 2. declared components ------------------------------------------
    print("\ncomponents")
    for label, path, required in [
        ("commands/", ROOT / "commands", True),
        ("agents/", ROOT / "agents", True),
        ("skills/scw/SKILL.md", ROOT / "skills" / "scw" / "SKILL.md", True),
        ("hooks/hooks.json", ROOT / "hooks" / "hooks.json", True),
        ("README.md", ROOT / "README.md", True),
    ]:
        check(label, path.exists() if required else True, str(path))

    for md in sorted((ROOT / "commands").glob("*.md")):
        text = md.read_text(encoding="utf-8")
        has_fm = text.startswith("---") and "description:" in text.split("---")[1]
        check(f"command {md.name} has frontmatter+description", has_fm)

    for md in sorted((ROOT / "agents").glob("*.md")):
        text = md.read_text(encoding="utf-8")
        block = text.split("---")[1] if text.startswith("---") else ""
        check(f"agent {md.name} declares name+description",
              "name:" in block and "description:" in block)

    skill_dirs = sorted(p.name for p in (ROOT / "skills").iterdir() if p.is_dir())
    # scw-default-deployer is the skill agents/scw-deployer.md names; it is
    # not a concept skill, so it is counted on its own rather than by bumping
    # the concept total and letting any stray directory pass as the 18th.
    check("skills/ has scw + scw-default-deployer + one per Maxey0 concept (18 total)",
          len(skill_dirs) == 18 and "scw" in skill_dirs
          and "scw-default-deployer" in skill_dirs, str(skill_dirs))
    for name in skill_dirs:
        md = ROOT / "skills" / name / "SKILL.md"
        check(f"skills/{name}/SKILL.md exists and has frontmatter", md.exists()
              and md.read_text(encoding="utf-8").startswith("---"))
        # A skill directory holding one file has nothing for the plugin UI's
        # Contents tab to show, which is exactly what 0.6.0 shipped.
        bundled = [q for q in (ROOT / "skills" / name).rglob("*") if q.is_file()]
        check(f"skills/{name} bundles reference material", len(bundled) >= 2,
              f"{len(bundled)} file(s)")

    for label, cmd in [
        ("concept skills match the manifest",
         [sys.executable, str(ROOT / "scripts" / "generate_concept_skills.py"), "--check"]),
        ("plugin directories match the root",
         [sys.executable, str(ROOT / "scripts" / "build_planes.py"), "--check"]),
        ("lexicon: one name per thing",
         [sys.executable, str(ROOT / "scripts" / "check_lexicon.py")]),
        ("ui types match the catalog",
         [sys.executable, str(ROOT / "scripts" / "generate_ui_types.py"), "--check"]),
    ]:
        r = subprocess.run(cmd, capture_output=True, text=True)
        check(label, r.returncode == 0,
              (r.stdout or r.stderr).strip().splitlines()[-1] if (r.stdout or r.stderr) else "")

    hooks_path = ROOT / "hooks" / "hooks.json"
    if hooks_path.exists():
        hooks = json.loads(hooks_path.read_text(encoding="utf-8"))
        for event, entries in (hooks.get("hooks") or {}).items():
            for entry in entries:
                for hook in entry.get("hooks", []):
                    cmd = hook.get("command", "")
                    if "${CLAUDE_PLUGIN_ROOT}" in cmd:
                        target = cmd.split("${CLAUDE_PLUGIN_ROOT}")[1]
                        target = target.strip('" ').lstrip("/\\")
                        check(f"hook {event} script exists",
                              (ROOT / target).exists(), str(ROOT / target))

    # -- 3. vendored copy -------------------------------------------------
    print("\nvendored runtime")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "sync_vendor.py"), "--check"],
        capture_output=True, text=True)
    if result.returncode == 2:
        notes.append("upstream repos absent — vendored copy could not be diffed "
                     "against source (fine for a standalone install)")
        print("  [NOTE] upstream source not present; skipping drift check")
    else:
        check("vendored copy matches upstream", result.returncode == 0,
              result.stdout.strip().splitlines()[-1] if result.stdout else "")

    # -- 4. entry points import ------------------------------------------
    print("\nentry points")
    env = dict(os.environ)
    env["MAXEY0_ROOT"] = str(ROOT / "server" / "vendor" / "maxey0")
    env["MAXEY0_LOOPS"] = str(ROOT / "server" / "vendor" / "data" / "loops.json")
    env["PYTHONIOENCODING"] = "utf-8"

    for label, code in [
        ("maxey0-context connector builds 32 tools",
         "import asyncio; from planes.context_plane import build; "
         "assert len(asyncio.run(build().list_tools())) == 32"),
        ("maxey0-loops connector builds 10 tools",
         "import asyncio; from planes.loops_plane import build; "
         "assert len(asyncio.run(build().list_tools())) == 10"),
        ("maxey0-observe connector builds 8 tools",
         "import asyncio; from planes.observe_plane import build; "
         "assert len(asyncio.run(build().list_tools())) == 8"),
        ("the Loop plane opens no ledger",
         "import os, tempfile, pathlib; "
         "d = tempfile.mkdtemp(); os.environ['SCW_EVENT_LOG'] = os.path.join(d, 'x.jsonl'); "
         "import planes.loops_plane as lp; lp.build(); "
         "assert not pathlib.Path(os.environ['SCW_EVENT_LOG']).exists(), "
         "'the Loop plane must hold no window state'"),
        ("the runtime loads from server/vendor/",
         "from planes import bootstrap; bootstrap.prepare(); "
         "p = bootstrap.provenance(); assert p['vendored'], p"),
        ("the Desktop bundle unions the planes",
         "import asyncio, importlib.util; "
         "spec = importlib.util.spec_from_file_location('mcpb', "
         f"r'{ROOT / 'server' / 'mcpb_entry.py'}'); "
         "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); "
         "assert len(asyncio.run(m.build().list_tools())) == 47"),
        ("Studio app imports", "from maxey0_studio import app; assert app.SESSION"),
        ("semantic field builds",
         "from maxey0_studio import app; f=app.field_payload(); assert f['stats']['nodes']>100"),
    ]:
        r = subprocess.run([sys.executable, "-c",
                            f"import sys; sys.path.insert(0, r'{ROOT / 'server'}'); {code}"],
                           capture_output=True, text=True, env=env)
        check(label, r.returncode == 0,
              (r.stderr.strip().splitlines() or [""])[-1] if r.returncode else "")

    # -- 5. isolation actually enforced ----------------------------------
    print("\nenforcement (the claim, actually tested)")
    probe = f"""
import sys, json
sys.path.insert(0, r'{ROOT / "server"}')
from maxey0_studio import state as st
s = st.Session()
loop = next(l for l in s.knowledge.loops
            if l.get('execution_mode') == 'in-window'
            and l.get('status') == 'validated'
            and len(l.get('agent_stages') or []) >= 3)
b = s.bind_loop(loop['id'])
assert b['ok'], b
roles = b['roles']
last, first = roles[-1], roles[0]
own = s.region_detail(s.window.loops[last].scw_id, as_loop=last)
foreign = s.region_detail(s.window.loops[first].scw_id, as_loop=last)
chain = s.verify_chain()
print(json.dumps({{
  'negative_controls_refused': b['refused_negative_controls'],
  'own_pad_allowed': own['scope_check']['allowed'],
  'foreign_pad_allowed': foreign['scope_check']['allowed'],
  'foreign_error': foreign['scope_check'].get('error'),
  'chain_verified': chain['verified'],
  'replay_identical': chain['replay_identical'],
}}))
"""
    r = subprocess.run([sys.executable, "-c", probe],
                       capture_output=True, text=True, env=env)
    if r.returncode != 0:
        check("isolation probe runs", False,
              (r.stderr.strip().splitlines() or [""])[-1])
    else:
        data = json.loads(r.stdout.strip().splitlines()[-1])
        check("negative controls were refused", data["negative_controls_refused"] > 0,
              f"{data['negative_controls_refused']} refused")
        check("a role can read its own region", data["own_pad_allowed"] is True)
        check("a role is REFUSED another role's private pad",
              data["foreign_pad_allowed"] is False, data.get("foreign_error") or "")
        check("hash chain verifies", data["chain_verified"] is True)
        check("log replays to an identical window", data["replay_identical"] is True)

    # -- 6. cross-window leak detection actually detects a leak -----------
    print("\ncross-window (does the leak check catch a real leak, not just report clean)")
    cw_probe = f"""
import sys, json
sys.path.insert(0, r'{ROOT / "server"}')
from maxey0_studio import cross_window as cw

clean = cw.CrossWindowRun.create('designer:01-horizontal-4way')
for _ in range(4):
    call = clean.next_call()
    clean.ingest(call['call_id'], f"independent response from {{call['maxey_id']}}")
clean_report = clean.report()

dirty = cw.CrossWindowRun.create('designer:03-fanin-scaling')
# ingest maker 1 normally, then deliberately paste its response into maker
# 2's own prompt before dispatch -- a real, constructed leak to confirm the
# checker actually catches rather than only ever reporting clean.
m1 = dirty.next_call(); dirty.ingest(m1['call_id'], 'maker1 proposal: use FIFO')
m2 = dirty.next_call()
for c in dirty.doc['calls']:
    if c['call_id'] == m2['call_id']:
        c['prompt'] += '\\n\\nFYI maker1 proposal: use FIFO'  # the injected leak
dirty.ingest(m2['call_id'], 'maker2 proposal: use LRU, having seen maker1s idea')
m3 = dirty.next_call(); dirty.ingest(m3['call_id'], 'maker3 proposal: use LFU')
judge = dirty.next_call(); dirty.ingest(judge['call_id'], 'picked maker2')
dirty_report = dirty.report()

print(json.dumps({{
  'clean_run_id': clean.run_id, 'dirty_run_id': dirty.run_id,
  'clean_bound_holds': clean_report['bound_holds'],
  'clean_leaks': len(clean_report['leaks']),
  'dirty_bound_holds': dirty_report['bound_holds'],
  'dirty_leaks': len(dirty_report['leaks']),
}}))
"""
    r = subprocess.run([sys.executable, "-c", cw_probe],
                       capture_output=True, text=True, env=env)
    probe_run_ids: list[str] = []
    if r.returncode != 0:
        check("cross-window probe runs", False, (r.stderr.strip().splitlines() or [""])[-1])
    else:
        data = json.loads(r.stdout.strip().splitlines()[-1])
        probe_run_ids = [data["clean_run_id"], data["dirty_run_id"]]
        check("a clean cross-window run reports bound_holds=true",
              data["clean_bound_holds"] is True and data["clean_leaks"] == 0)
        check("a run with a real injected leak is caught, not missed",
              data["dirty_bound_holds"] is False and data["dirty_leaks"] > 0,
              f"leaks found: {data['dirty_leaks']}")

    # These two runs exist only to prove the checker works both ways; unlike
    # a real run, they carry no evidence worth keeping.
    cw_dir = ROOT / "experiments" / "cross-window"
    for run_id in probe_run_ids:
        for suffix in (".json", ".report.json"):
            (cw_dir / f"{run_id}{suffix}").unlink(missing_ok=True)

    # -- verdict ----------------------------------------------------------
    print()
    for note in notes:
        print(f"  note: {note}")
    if failures:
        print(f"\nFAILED — {len(failures)} problem(s):")
        for f in failures:
            print("  - " + f)
        return 1
    print("PASS — plugin is installable and the runtime enforces what it claims.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
