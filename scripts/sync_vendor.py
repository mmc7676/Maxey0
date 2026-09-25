"""Vendor the runtime + knowledge the plugin needs, so it installs standalone.

The plugin must work on a machine with no other checkout present. So the
pieces it actually imports are copied in here, from named source paths, by
this script -- never hand-edited in place. Re-run it after changing the
runtime engine or the Maxey0 knowledge base:

    python scripts/sync_vendor.py

`--check` verifies the vendored copy matches the source and exits non-zero if it
drifted, which is the thing you want in CI rather than a silent stale bundle.

Source of truth stays in the engineering checkout. If a developer HAS it,
environment variables (SCW_RUNTIME_SRC / MAXEY0_ROOT / MAXEY0_LOOPS) override
the vendored copy at runtime -- see server/maxey0_studio/state.py.
"""

from __future__ import annotations

import argparse
import filecmp
import hashlib
import json
import shutil
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
VENDOR = PLUGIN_ROOT / "server" / "vendor"

# The plugin lives at <workspace>/Maxey0, so the workspace is 1 up.
WORKSPACE = PLUGIN_ROOT.parent
SCW_RUNTIME = WORKSPACE / "scw-runtime"
MAXEY0 = WORKSPACE / "Maxey0" / "Maxey0"

#: (source, destination-relative-to-vendor, kind)
PLAN: list[tuple[Path, str, str]] = [
    # -- the SCW enforcement runtime itself (pure stdlib, no deps) -----------
    (SCW_RUNTIME / "src" / "scw_runtime", "scw_runtime", "tree"),
    # -- the loop-composition DSL the designer and experiment harness use ---
    (SCW_RUNTIME / "loops" / "d4" / "harness_dsl.py", "d4/harness_dsl.py", "file"),
    (SCW_RUNTIME / "loops" / "d4" / "compositions.py", "d4/compositions.py", "file"),
    (SCW_RUNTIME / "loops" / "lib" / "harness_kit.py", "loopkit/harness_kit.py", "file"),
    # -- the hardened agentic-loop dataset ----------------------------------
    (SCW_RUNTIME / "loops" / "dataset" / "loops.json", "data/loops.json", "file"),
    # -- the Maxey0 concept/skill/agent hierarchy ---------------------------
    (MAXEY0 / "manifest.json", "maxey0/manifest.json", "file"),
    (MAXEY0 / "registry" / "registry.json", "maxey0/registry.json", "file"),
    (MAXEY0 / "data" / "team_mapping.csv", "maxey0/team_mapping.csv", "file"),
    (MAXEY0 / "data" / "maxey0_subagents.csv", "maxey0/maxey0_subagents.csv", "file"),
    (MAXEY0 / "data" / "anchors.json", "maxey0/anchors.json", "file"),
    (MAXEY0 / "data" / "complexity-map.json", "maxey0/complexity-map.json", "file"),
]

IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".git", ".pytest_cache")


def _content_bytes(path: Path) -> bytes:
    """File bytes, with line endings normalized to LF.

    The source checkout and the vendored copy can sit on different platforms
    (a Windows working tree checked out through git's CRLF normalization vs.
    a raw source directory that is not a git checkout at all). Hashing raw
    bytes then reports every file as drifted on line endings alone, which
    trains the same "ignore the check" reflex a false-positive assertion
    does anywhere else in this product. A real content change survives
    normalization; a checkout artifact does not.
    """
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8").replace("\r\n", "\n").encode("utf-8")
    except UnicodeDecodeError:
        return raw  # binary file: compare as-is


def _digest_tree(path: Path) -> str:
    h = hashlib.sha256()
    if path.is_file():
        h.update(_content_bytes(path))
        return h.hexdigest()
    for item in sorted(p for p in path.rglob("*") if p.is_file()):
        if "__pycache__" in item.parts or item.suffix == ".pyc":
            continue
        h.update(item.relative_to(path).as_posix().encode())
        h.update(_content_bytes(item))
    return h.hexdigest()


def sync(check_only: bool = False) -> int:
    missing = [str(src) for src, _, _ in PLAN if not src.exists()]
    present = [(src, rel, kind) for src, rel, kind in PLAN if src.exists()]

    if not present:
        print("FAIL - no source paths found (is this the workspace checkout?):")
        for m in missing:
            print("  " + m)
        return 2

    drift: list[str] = []
    manifest: dict[str, str] = {}

    for src, rel, kind in present:
        dest = VENDOR / rel
        digest = _digest_tree(src)
        manifest[rel] = digest

        if check_only:
            if not dest.exists() or _digest_tree(dest) != digest:
                drift.append(rel)
            continue

        dest.parent.mkdir(parents=True, exist_ok=True)
        if kind == "tree":
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest, ignore=IGNORE)
        else:
            shutil.copy2(src, dest)

    if check_only:
        if missing:
            print(f"NOTE - {len(missing)}/{len(PLAN)} source path(s) not found, "
                  "not checked (is this the workspace checkout?):")
            for m in missing:
                print("  " + m)
        if drift:
            print("FAIL - vendored copy has drifted from source:")
            for d in drift:
                print("  " + d)
            print("\nRun: python scripts/sync_vendor.py")
            return 1
        if missing:
            print(f"OK - {len(present)}/{len(PLAN)} checked vendored path(s) match "
                  f"their source; {len(missing)} source(s) absent")
            return 2
        print(f"OK - all {len(PLAN)} vendored paths match their source")
        return 0

    # `d4` and `loopkit` are imported as packages; give them __init__.py.
    for pkg in ("d4", "loopkit"):
        init = VENDOR / pkg / "__init__.py"
        init.parent.mkdir(parents=True, exist_ok=True)
        if not init.exists():
            init.write_text(
                f'"""Vendored package: {pkg}. '
                'Regenerate with scripts/sync_vendor.py."""\n',
                encoding="utf-8",
            )

    # A missing source leaves its old digest in place rather than dropping it,
    # so a partial sync (some upstream checkouts absent) never erases evidence
    # for the paths it could not touch.
    vendor_json = VENDOR / "VENDOR.json"
    previous_digests: dict[str, str] = {}
    if vendor_json.exists():
        try:
            previous_digests = json.loads(vendor_json.read_text(encoding="utf-8")).get("digests", {})
        except json.JSONDecodeError:
            pass
    vendor_json.write_text(
        json.dumps(
            {
                "note": "Generated by scripts/sync_vendor.py -- do not hand-edit. "
                        "Digests let `--check` detect drift from the engineering source.",
                "digests": {**previous_digests, **manifest},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    total = sum(
        f.stat().st_size for f in VENDOR.rglob("*") if f.is_file()
    )
    if missing:
        print(f"NOTE - {len(missing)}/{len(PLAN)} source path(s) not found, left "
              "untouched (is this the workspace checkout?):")
        for m in missing:
            print("  " + m)
    print(f"OK - vendored {len(present)}/{len(PLAN)} path(s), {total / 1024:.0f} KB "
          "into server/vendor/")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="verify the vendored copy matches source; do not write")
    args = parser.parse_args()
    raise SystemExit(sync(check_only=args.check))
