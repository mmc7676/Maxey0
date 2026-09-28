"""Build the distributable archives.

Emits, into dist/:

    maxey0-<version>.zip           marketplace archive -- clone-equivalent,
                                    for `/plugin marketplace add <local path>`
                                    without git. Root has marketplace.json and
                                    every plugins/* directory, same shape as
                                    the repository.
    maxey0-<version>-plugin.zip    ONE plugin, self-contained -- plugins/
                                    maxey0/ zipped with its own
                                    .claude-plugin/plugin.json at the archive
                                    root. This is what a "drag a zip in to
                                    install a plugin" control expects; the
                                    marketplace zip above does not satisfy it,
                                    because that control looks for
                                    plugin.json at the top (or one wrapping
                                    folder in) and does not know how to walk
                                    into a marketplace's plugins/ subtree.
    maxey0-<version>.mcpb          MCP Bundle -- manifest.json at the
                                    archive root, for Claude Desktop
    maxey0-<version>.dxt           byte-identical copy of the .mcpb

`.dxt` is simply the former name of the same zip-plus-manifest format; the
upstream project renamed DXT to MCPB and ".dxt files are now .mcpb files".
Both are written because older Claude Desktop builds only offer `.dxt` in
their file picker, and shipping one archive under two names is honest -- they
really are the same bytes, which this script asserts before finishing.

    python scripts/build_package.py
    python scripts/build_package.py --check    # verify only, write nothing

Version comes from .claude-plugin/marketplace.json and every other manifest
must agree with it; a mismatch fails the build rather than shipping four
archives that disagree about what they are.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _packaging import collect, dirty_tree_problem, scan_for_secrets  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
PLUGIN_ROOT = ROOT / "plugins" / "maxey0"
PLUGIN_PREFIX = "plugins/maxey0/"

#: Inclusion is derived from `git ls-files` by `scripts/_packaging.collect`,
#: not from a hand-maintained exclusion list. The list this file used to keep
#: disagreed with `build_source_archive.py`'s and with `.gitignore`: `.wrangler`
#: was excluded from one archive and not the other, and `.egg-info` sat in a
#: *file*-suffix set while naming a directory, so `maxey0_superspace.egg-info/`
#: shipped in every source archive. `.gitignore` already declares all of this
#: once; deriving from it is the only way the two can never disagree again.
#:
#: `.claude` matters more than it looks, and git covers it: a `git worktree`
#: under `.claude/` is a second, complete copy of this repository, and through
#: 0.6.0 every archive shipped one -- `dist/maxey0-0.6.0.mcpb` contained each
#: documentation file twice, from two different commits. A bundle that carries
#: two versions of its own documentation cannot say which one it is.

#: Repo-relative prefixes dropped from the marketplace archive. Run output is
#: created by the code on first real use; shipping someone else's run as if it
#: were ours would make the archive claim evidence it never produced. Both are
#: also gitignored, so this is belt-and-braces rather than the mechanism.
EXCLUDE_PATH_PREFIXES = (
    "experiments/cross-window/",
    "experiments/exp-",
)

#: Additionally excluded from the Desktop `.mcpb`/`.dxt` only. The manifest
#: declares the UV runtime, which provisions Python and every dependency
#: itself, so `server/lib`/`server/venv` (a bundled, platform-pinned copy)
#: is forbidden; `plugins/` holds the plugin-marketplace units, each with its
#: own full copy of `server/`, which the Desktop bundle -- built from the
#: repository root directly -- has no use for and would ship four times over.
MCPB_EXTRA_EXCLUDE_PREFIXES = ("server/lib/", "server/venv/", "plugins/")


def included_files():
    """Every file for the marketplace archive: the repository as it stands."""
    return collect(ROOT, exclude_prefixes=EXCLUDE_PATH_PREFIXES)


def mcpb_files():
    """Every file for the Desktop bundle: the root, without plugins/.

    This bundle now carries `mcp_apps/super_space_react/dist/mcp-app.html`.
    It did not before: `dist/` is gitignored build output and sat in the old
    exclusion list, so every installed `.mcpb` fell back to the unbuilt stub
    and reported `app.artifact.kind == "fallback-stub"` -- which the deployment
    checklist lists as a *rollback trigger*. The packaging guaranteed the
    condition the checklist rolls back for. `_packaging.REQUIRED_BUILD_ARTIFACTS`
    adds it explicitly and fails the build when it is absent.
    """
    return collect(ROOT, exclude_prefixes=EXCLUDE_PATH_PREFIXES + MCPB_EXTRA_EXCLUDE_PREFIXES)


def plugin_zip_files():
    """Every file for the single-plugin archive: `plugins/maxey0/` alone.

    Selected from the repository root and then narrowed, rather than walked
    from `PLUGIN_ROOT`, so that this archive is decided by the same `git
    ls-files` as the other two. Walking the plugin directory directly would
    reach no `.git` and silently fall back to a filesystem walk.
    """
    whole = collect(ROOT, include_build_artifacts=False)
    whole.files = [
        p for p in whole.files
        if p.relative_to(ROOT).as_posix().startswith(PLUGIN_PREFIX)
    ]
    return whole


def check_planes() -> list[str]:
    """Refuse to package plugin trees that no longer match their source.

    `plugins/**` is generated from the repo-root `server/` tree by
    `scripts/build_planes.py`. Nothing in the packaging path invoked its
    `--check`, so this script zipped `plugins/maxey0/` exactly as it sat on
    disk: a hand-edit to `server/` that was never regenerated shipped silently,
    and `check_manifests()` -- which verifies version agreement and entry-point
    existence -- would not have noticed.
    """
    script = Path(__file__).resolve().parent / "build_planes.py"
    try:
        proc = subprocess.run(
            [sys.executable, str(script), "--check"],
            cwd=ROOT, capture_output=True, text=True,
        )
    except OSError as exc:  # pragma: no cover - environment failure
        return [f"could not run build_planes.py --check: {exc}"]
    if proc.returncode == 0:
        return []
    detail = (proc.stdout or proc.stderr).strip().splitlines()
    return ["generated plugin trees have drifted from server/:"] + [
        f"    {line}" for line in detail
    ]


def check_distributions() -> list[str]:
    """Refuse to package distribution manifests that have drifted.

    Same argument as `check_planes`: `distributions/**` is generated from
    `maxey0_ss/distribution/registry.py`, and a manifest edited by hand ships
    silently. A connector descriptor naming the wrong server, or a plugin id
    that disagrees with the package name, fails for a user at install with no
    diagnostic rather than failing here.
    """
    script = Path(__file__).resolve().parent / "build_distributions.py"
    try:
        proc = subprocess.run(
            [sys.executable, str(script), "--check"],
            cwd=ROOT, capture_output=True, text=True,
        )
    except OSError as exc:  # pragma: no cover - environment failure
        return [f"could not run build_distributions.py --check: {exc}"]
    if proc.returncode == 0:
        return []
    detail = (proc.stdout or proc.stderr).strip().splitlines()
    return ["generated distribution manifests have drifted:"] + [
        f"    {line}" for line in detail
    ]


def check_validator() -> list[str]:
    """Refuse to package a tree the documented plugin validator rejects.

    `validate_plugin.py` is the check the docs tell a contributor to run, and
    nothing in the packaging path ran it: release/0.3.0 packaged cleanly while
    the validator reported FAILED on an unregistered skill directory.
    """
    script = Path(__file__).resolve().parent / "validate_plugin.py"
    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
    except OSError as exc:  # pragma: no cover - environment failure
        return [f"could not run validate_plugin.py: {exc}"]
    if proc.returncode == 0:
        return []
    detail = [line for line in (proc.stdout or proc.stderr).strip().splitlines()
              if line.strip().startswith("-") or "FAILED" in line]
    return ["validate_plugin.py reports problems:"] + [f"    {line}" for line in detail]


def read_versions() -> tuple[str, dict[str, str]]:
    """The marketplace's version, plus every other manifest's claimed version.

    The marketplace is the one thing that is always at the repository root —
    `plugins/maxey0/.claude-plugin/plugin.json` is a generated, installable
    unit like every other plugin under `plugins/`, not the version anchor.
    """
    marketplace = json.loads(
        (ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
    )
    version = marketplace["metadata"]["version"]
    others = {
        "plugins/maxey0/.claude-plugin/plugin.json": json.loads(
            (ROOT / "plugins" / "maxey0" / ".claude-plugin" / "plugin.json")
            .read_text(encoding="utf-8")
        )["version"],
        "manifest.json": json.loads(
            (ROOT / "manifest.json").read_text(encoding="utf-8")
        )["version"],
    }
    return version, others


def check_manifests() -> list[str]:
    """Problems that would ship a broken or self-contradicting archive."""
    problems: list[str] = []

    version, others = read_versions()
    for name, claimed in others.items():
        if claimed != version:
            problems.append(
                f"{name} says version {claimed!r} but "
                f".claude-plugin/marketplace.json says {version!r}")

    mcpb = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    for key in ("manifest_version", "name", "version", "description",
                "author", "server"):
        if key not in mcpb:
            problems.append(f"manifest.json missing required key {key!r}")
    entry = (mcpb.get("server") or {}).get("entry_point")
    if entry and not (ROOT / entry).exists():
        problems.append(f"manifest.json entry_point missing: {ROOT / entry}")

    if not (ROOT / "README.md").exists():
        problems.append("README.md missing")
    if not (ROOT / "requirements.txt").exists():
        problems.append("requirements.txt missing")

    if mcpb.get("server", {}).get("type") == "uv":
        pyproject = ROOT / "pyproject.toml"
        if not pyproject.exists():
            problems.append("manifest.json declares server.type 'uv' but "
                            "pyproject.toml is missing")
        elif 'attr = "maxey0_ss.__version__"' not in pyproject.read_text(encoding="utf-8"):
            problems.append("pyproject.toml must derive its version from "
                            "maxey0_ss.__version__")
        for forbidden in ("server/lib", "server/venv"):
            if (ROOT / forbidden).exists():
                problems.append(f"{forbidden}/ exists but the UV runtime "
                                "forbids shipping a bundled dependency copy")

    return problems


def write_zip(target: Path, files: list[Path], base: Path = ROOT) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(path, path.relative_to(base).as_posix())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="validate manifests and exit without writing")
    parser.add_argument("--allow-dirty", action="store_true",
                        help="package an uncommitted tree; the archive will "
                             "correspond to no commit, and untracked files "
                             "will be missing from it")
    args = parser.parse_args(argv)

    print("Maxey0 package build\n")

    # The dirty check runs first, and the order is load-bearing rather than
    # tidy. Contents are selected with `git ls-files`, so every other check
    # below is an answer about a tree that may not be the one being packaged.
    # It also produces the better diagnostic: regenerating `plugins/` or
    # `distributions/` is the single most likely reason this tree is dirty, so
    # reporting the drift first tells an operator to run a generator when what
    # they actually need to do is commit what the generator already wrote.
    dirty = None if args.allow_dirty else dirty_tree_problem(ROOT)
    if dirty:
        print(f"  [FAIL] working tree is dirty: {dirty}")
        print("\nFAILED - contents are selected with `git ls-files`, so a "
              "dirty tree\nproduces an archive matching neither the commit "
              "nor the working tree.\nCommit, or pass --allow-dirty.")
        return 1
    print("  [OK  ] working tree is clean; git selection matches HEAD"
          if not args.allow_dirty else
          "  [WARN] --allow-dirty: untracked files will be absent")

    problems = (check_manifests() + check_planes() + check_distributions()
                + check_validator())
    for problem in problems:
        print(f"  [FAIL] {problem}")
    if problems:
        print(f"\nFAILED - {len(problems)} problem(s). Nothing written.")
        return 1
    print("  [OK  ] manifests agree and every entry point exists")
    print("  [OK  ] generated plugin trees match server/ (build_planes --check)")
    print("  [OK  ] distribution manifests match the registry")
    print("  [OK  ] validate_plugin.py passes")

    version, _ = read_versions()
    market = included_files()
    plugin = plugin_zip_files()
    desktop = mcpb_files()
    selections = (("marketplace archive", market),
                  ("single-plugin archive", plugin),
                  ("Desktop bundle", desktop))

    missing = sorted({rel for _, sel in selections for rel in sel.missing_artifacts})
    if missing:
        for rel in missing:
            print(f"  [FAIL] required build artifact missing: {rel}")
        print("\nFAILED - run: cd mcp_apps/super_space_react && npm run build")
        return 1

    refused = sorted({(rel, why) for _, sel in selections for rel, why in sel.refused})
    for rel, why in refused:
        print(f"  [refused] {rel} - {why}")

    for label, sel in selections:
        total = sum(f.stat().st_size for f in sel.files) / 1_048_576
        print(f"  [OK  ] {label}: {len(sel.files)} files, "
              f"{total:.1f} MiB uncompressed (selected by {sel.source})")

    # Measure the archive rather than restate the intent behind it. The
    # exclusion rules are the mechanism; this is the check that they worked,
    # and it reads the bytes of every file about to be zipped.
    scanned = sorted({f for _, sel in selections for f in sel.files})
    leaks = scan_for_secrets(scanned, ROOT)
    if leaks:
        print("\nFAILED - credential-shaped content in files about to be "
              "archived. Nothing written.")
        for finding in leaks:
            print(f"  {finding}")
        return 1
    print(f"  [OK  ] secret scan clean across {len(scanned)} distinct files")

    if args.check:
        print("\nCHECK ONLY - nothing written.")
        return 0

    market_files = market.files
    plugin_files = plugin.files
    mcpb_files_ = desktop.files

    DIST.mkdir(parents=True, exist_ok=True)
    zip_path = DIST / f"maxey0-{version}.zip"
    plugin_zip_path = DIST / f"maxey0-{version}-plugin.zip"
    mcpb_path = DIST / f"maxey0-{version}.mcpb"
    dxt_path = DIST / f"maxey0-{version}.dxt"

    write_zip(zip_path, market_files)
    write_zip(plugin_zip_path, plugin_files, base=PLUGIN_ROOT)
    write_zip(mcpb_path, mcpb_files_)
    dxt_path.write_bytes(mcpb_path.read_bytes())

    # Every archive's own defining claim, asserted rather than trusted:
    # marketplace.json/plugin.json/manifest.json each have to sit at the
    # exact spot the thing that reads them looks for, and the .dxt claim is
    # only honest if it really is the same bytes as the .mcpb.
    with zipfile.ZipFile(zip_path) as zf:
        if ".claude-plugin/marketplace.json" not in zf.namelist():
            print("\nFAILED — marketplace.json is not at the marketplace "
                  "archive root.")
            return 1
    with zipfile.ZipFile(plugin_zip_path) as zf:
        if ".claude-plugin/plugin.json" not in zf.namelist():
            print("\nFAILED — plugin.json is not at the single-plugin "
                  "archive root.")
            return 1
    with zipfile.ZipFile(mcpb_path) as zf:
        names = zf.namelist()
        if "manifest.json" not in names:
            print("\nFAILED — manifest.json is not at the .mcpb archive root.")
            return 1
        if "pyproject.toml" not in names:
            print("\nFAILED — pyproject.toml missing from the archive; the "
                  "declared UV runtime needs it to install dependencies.")
            return 1
    if mcpb_path.read_bytes() != dxt_path.read_bytes():
        print("\nFAILED — .dxt is not byte-identical to .mcpb.")
        return 1

    print()
    for path in (zip_path, plugin_zip_path, mcpb_path, dxt_path):
        print(f"  wrote {path.relative_to(ROOT).as_posix()}  "
              f"({path.stat().st_size / 1_048_576:.2f} MiB)")

    print(f"\nPASS — v{version} packaged four ways.")
    print("  .zip          marketplace, git-less: `/plugin marketplace add "
          "<extracted path>`")
    print("  -plugin.zip   ONE self-contained plugin — the file to drag into "
          "a single-plugin \"Add\" control")
    print("  .mcpb         drag-and-drop into Claude Desktop")
    print("  .dxt          same bytes as .mcpb, former name, for older "
          "Desktop builds")
    print("\nThe manifest declares the UV runtime (server.type: \"uv\"), so"
          " Claude\nDesktop installs Python and every dependency \u2014 including"
          " pydantic, a\ncompiled package the old bundled-Python type could"
          " not portably ship \u2014\nitself. Nothing to pip install by hand on"
          " a machine that has never\nseen this project before.\n\n"
          "Installing the Claude Code plugin from the marketplace is separate"
          "\nand still needs the `maxey0` package on the interpreter that"
          "\n`python` resolves to:\n\n    python -m pip install maxey0"
          "\n\nNamed as a package, not as a file. The single-plugin archive"
          " contains\nno requirements.txt at all.\n`server/_preflight.py` names"
          " the individual missing modules (such as\n`mcp` and `pydantic`) on"
          " the only start-up failure path; installing\n`maxey0` provides"
          " them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
