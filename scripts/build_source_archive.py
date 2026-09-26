"""Build a clean source archive for versioning and transfer.

Distinct from `build_package.py`, which emits installable bundles. This emits
the *tree* — what you would hand to another machine, or keep as the snapshot a
version number refers to.

What is excluded, and why it matters: a source archive that carries `.git`
carries the whole history including anything ever committed and later removed,
`.venv` carries platform-specific compiled binaries that will not run on the
target machine, and `dist/` carries build outputs that should be rebuilt rather
than trusted. Shipping any of the three makes the archive larger than the
project and less trustworthy than the repository.

Inclusion is decided by `scripts/_packaging.collect`, which derives it from
`git ls-files` rather than from a hand-maintained exclusion list. The two
lists this file and `build_package.py` used to keep disagreed with each other
and with `.gitignore`; the fix was to stop keeping lists.

A MANIFEST.txt is written into the archive recording the commit, the tree state
and the test baseline at build time, so an extracted copy can say where it came
from. An archive that cannot identify itself is the thing this project exists
to argue against.

**A dirty tree fails the build.** A MANIFEST that says `DIRTY` describes an
archive that corresponds to no commit, and so cannot be verified against one by
anybody who later receives it. That rule used to live in the operator's head
while `main()` wrote the zip anyway; it now lives in the exit code. Local
iteration passes `--allow-dirty`, which is a decision rather than an accident,
and the manifest still records what it is.

    python scripts/build_source_archive.py [--version 0.2.0] [--allow-dirty]
"""
from __future__ import annotations

import argparse
import hashlib
import pathlib
import subprocess
import sys
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _packaging import collect, scan_for_secrets  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[1]
OUT = REPO / "dist"


def git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=REPO, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unavailable"


def manifest(selection, version: str, *, dirty: str, allow_dirty: bool) -> str:
    total = sum(p.stat().st_size for p in selection.files)
    files = selection.files
    state = "clean"
    if dirty:
        state = "DIRTY — uncommitted changes present"
        if allow_dirty:
            state += " (built with --allow-dirty; matches no commit)"
    lines = [
        "Maxey0-SuperSpace source archive",
        "=" * 34,
        "",
        f"version       : {version}",
        f"commit        : {git('rev-parse', 'HEAD')}",
        f"subject       : {git('log', '-1', '--format=%s')}",
        f"branch        : {git('rev-parse', '--abbrev-ref', 'HEAD')}",
        f"tree state    : {state}",
        f"files         : {len(files)}",
        f"uncompressed  : {total / 1048576:.2f} MiB",
        f"selected by   : {selection.source}",
        f"secret scan   : clean ({len(files)} files read)",
        "",
        "Contents are every file `git ls-files` reports as tracked, plus the",
        "built MCP App bundle, minus anything matching a credential path. So",
        "`.git`, `.venv`, `__pycache__`, `node_modules`, caches, compiled",
        "artefacts, `.env*` and `config/credentials.json` are all absent — not",
        "because a list says so, but because `.gitignore` does and this archive",
        "is derived from it.",
        "",
        "To use:",
        "  python -m venv .venv",
        "  .venv/Scripts/pip install -e .          (Windows)",
        "  .venv/bin/pip install -e .              (POSIX)",
        "  .venv/Scripts/python -m pytest -q",
        "",
        "Installable bundles are built separately with scripts/build_package.py.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default=None, help="Label for the archive name")
    parser.add_argument(
        "--allow-dirty", action="store_true",
        help="build from an uncommitted tree; the manifest records that it "
             "corresponds to no commit",
    )
    args = parser.parse_args(argv)

    version = args.version
    if version is None:
        text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.startswith("version"):
                version = line.split("=", 1)[1].strip().strip('"')
                break
        version = version or "0.0.0"

    dirty = git("status", "--porcelain")
    if dirty and dirty != "unavailable" and not args.allow_dirty:
        print("FAILED — the working tree is dirty. Nothing written.\n",
              file=sys.stderr)
        print(dirty, file=sys.stderr)
        print("\nA MANIFEST that says DIRTY describes an archive that "
              "corresponds to no\ncommit. Commit, stash, or pass "
              "--allow-dirty to build one anyway.", file=sys.stderr)
        return 1

    selection = collect(REPO)
    if selection.missing_artifacts:
        for rel in selection.missing_artifacts:
            print(f"FAILED — required build artifact missing: {rel}",
                  file=sys.stderr)
        print("\nRun: cd mcp_apps/super_space_react && npm run build",
              file=sys.stderr)
        return 1
    for rel, reason in selection.refused:
        print(f"  [refused] {rel} — {reason}")
    if not selection.files:
        print("no files collected", file=sys.stderr)
        return 1

    leaks = scan_for_secrets(selection.files, REPO)
    if leaks:
        print("FAILED — credential-shaped content in files about to be "
              "archived. Nothing written.\n", file=sys.stderr)
        for finding in leaks:
            print(f"  {finding}", file=sys.stderr)
        return 1

    OUT.mkdir(exist_ok=True)
    target = OUT / f"maxey0-{version}-source.zip"
    body = manifest(selection, version, dirty=dirty, allow_dirty=args.allow_dirty)

    root = f"maxey0-{version}"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr(f"{root}/MANIFEST.txt", body)
        for path in selection.files:
            archive.write(path, f"{root}/{path.relative_to(REPO).as_posix()}")

    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    print(body)
    print(f"wrote {target.relative_to(REPO)}  ({target.stat().st_size / 1048576:.2f} MiB)")
    print(f"sha256 {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
