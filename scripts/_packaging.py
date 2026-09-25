"""One source of truth for what belongs in a distributable archive.

Until 0.2.0 there were two hand-maintained exclusion lists — one in
`build_source_archive.py`, one in `build_package.py` — that disagreed with each
other and with `.gitignore`. Three consequences, all measured rather than
supposed:

1. `config/credentials.json` is marked in `.gitignore` as "Real secrets. Only
   the .example files are tracked." Neither list excluded it, and both builders
   walked the filesystem rather than git, so a deployment that followed the
   documented setup would have packaged its own secrets. Latent, because only
   the `.example` existed.
2. `.egg-info` sat in `EXCLUDE_SUFFIXES`, which matches *file* suffixes.
   `maxey0_superspace.egg-info/` is a *directory*, so its six files shipped in
   every source archive — 906 files against 899 tracked.
3. `.wrangler` was excluded from the source archive and not from the
   marketplace archive, so local Wrangler dev state shipped in one and not the
   other.

The structural fix is not a third list. It is to stop maintaining a list at
all: **git already knows**, because `.gitignore` is the declaration and
`git ls-files` is its evaluation. A file that is tracked belongs in the
archive; a file that is ignored does not. The two can never drift, because
there is now only one of them.

Two deliberate exceptions to "tracked == shipped", each an explicit, named
list rather than a pattern:

- :data:`REQUIRED_BUILD_ARTIFACTS` — gitignored build output that *is* the
  product. The MCP App bundle is the leading case: it is generated, so it is
  correctly untracked, but an archive without it makes the server fall back to
  an unbuilt stub and report ``kind: "fallback-stub"`` — which the deployment
  checklist lists as a *rollback trigger*. Shipping an archive that guarantees
  its own rollback condition is not a packaging preference, it is a bug. These
  are added explicitly and their absence **fails the build**.

- :data:`NEVER_PACKAGE` — secret-bearing paths, excluded even when tracked.
  Belt and braces: `git ls-files` already omits them, but the one failure mode
  that would defeat that is somebody running `git add -f config/credentials.json`
  once. The cost of the second check is a set lookup.

Nothing here trusts that the rules worked. :func:`scan_for_secrets` reads the
bytes of every file about to be archived and looks for credential shapes, so
the claim "no secrets shipped" is a measurement of the archive rather than a
restatement of the intent behind it.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------
# What ships
# --------------------------------------------------------------------------

#: Repo-relative paths that are gitignored build output but are nonetheless
#: part of the product. Missing one fails the build rather than shipping an
#: archive that silently degrades.
REQUIRED_BUILD_ARTIFACTS: tuple[str, ...] = (
    "mcp_apps/super_space_react/dist/mcp-app.html",
)

#: Never packaged, whatever git says. Matched against the repo-relative POSIX
#: path (exact) or the bare filename.
NEVER_PACKAGE_PATHS: frozenset[str] = frozenset({
    "config/credentials.json",
})

NEVER_PACKAGE_NAMES: frozenset[str] = frozenset({
    "credentials.json",
    ".DS_Store",
    "Thumbs.db",
})

#: `.env` was previously matched by exact name, so `.env.local` and
#: `.env.production` — the two files a real deployment actually creates —
#: slipped through. Matched as a prefix now.
NEVER_PACKAGE_PREFIXES: tuple[str, ...] = (".env",)

#: `.env.example` is the tracked documentation of every variable the code
#: reads. It is the one `.env*` file that must ship.
NEVER_PACKAGE_EXCEPTIONS: frozenset[str] = frozenset({".env.example"})


def never_package(rel_posix: str) -> str | None:
    """Why this repo-relative path must not ship, or None if it may."""
    name = rel_posix.rsplit("/", 1)[-1]
    if name in NEVER_PACKAGE_EXCEPTIONS:
        return None
    if rel_posix in NEVER_PACKAGE_PATHS:
        return "listed in NEVER_PACKAGE_PATHS (gitignored as real secrets)"
    if name in NEVER_PACKAGE_NAMES:
        return f"filename {name!r} is never packaged"
    if any(name.startswith(p) for p in NEVER_PACKAGE_PREFIXES):
        return f"{name!r} matches a dotenv prefix; only .env.example ships"
    return None


# --------------------------------------------------------------------------
# Fallback walk, for a tree with no git
# --------------------------------------------------------------------------

#: Only consulted when git cannot answer — building from an extracted source
#: archive, which has no `.git`. Kept deliberately close to `.gitignore` and
#: reported as `source="filesystem"` so a manifest never claims git-derived
#: precision it did not have.
FALLBACK_EXCLUDE_DIRS: frozenset[str] = frozenset({
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", "node_modules", "dist", "build", ".idea", ".vscode",
    ".wrangler", ".turbo", ".claude", ".smoke",
})

FALLBACK_EXCLUDE_SUFFIXES: frozenset[str] = frozenset({
    ".pyc", ".pyo", ".pyd", ".so", ".dylib", ".log", ".mcpb", ".dxt", ".zip",
})

#: Directory-name suffixes. `.egg-info` was in the *file*-suffix list and so
#: never matched the directory it names.
FALLBACK_EXCLUDE_DIR_SUFFIXES: tuple[str, ...] = (".egg-info",)


def _fallback_walk(root: Path) -> list[Path]:
    out: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        parts = rel.parts
        if any(p in FALLBACK_EXCLUDE_DIRS for p in parts):
            continue
        if any(p.endswith(FALLBACK_EXCLUDE_DIR_SUFFIXES) for p in parts[:-1]):
            continue
        if path.suffix in FALLBACK_EXCLUDE_SUFFIXES:
            continue
        out.append(path)
    return out


def git_status(root: Path) -> str | None:
    """`git status --porcelain`, or None when git cannot answer for this tree."""
    if not (root / ".git").exists():
        return None
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root, capture_output=True, text=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None
    return proc.stdout.strip()


def dirty_tree_problem(root: Path) -> str | None:
    """Why a git-derived archive must not be built from this tree, or None.

    Both builders now select their contents with `git ls-files`, which makes a
    dirty tree a correctness problem rather than a labeling one. An untracked
    file is *absent* from the archive and a deleted-but-tracked file is
    *missing from disk*, so the archive describes neither the commit nor the
    working tree — it describes a third thing that never existed.

    This is not hypothetical. Regenerating `plugins/**` with
    `scripts/build_planes.py` in this release deleted two stale generated files
    and created three new ones. Packaged from that tree without committing, the
    marketplace archive would have shipped plugin trees missing three files
    that `build_planes.py --check` had just declared correct: the check passes,
    the archive is wrong, and nothing connects the two. Generate, commit, then
    package.
    """
    status = git_status(root)
    if status is None or not status:
        return None
    lines = status.splitlines()
    untracked = [l[3:] for l in lines if l.startswith("??")]
    modified = [l[3:] for l in lines if not l.startswith("??")]
    parts = []
    if untracked:
        parts.append(f"{len(untracked)} untracked file(s) would be absent "
                     f"from the archive")
    if modified:
        parts.append(f"{len(modified)} tracked file(s) differ from HEAD")
    return "; ".join(parts)


def git_tracked(root: Path) -> list[Path] | None:
    """Every tracked file, or None when git cannot answer for this tree."""
    if not (root / ".git").exists():
        return None
    try:
        proc = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=root, capture_output=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None
    names = [n for n in proc.stdout.decode("utf-8", "replace").split("\0") if n]
    # A tracked-but-deleted path is still listed; the archive writer would
    # raise on it, which is a confusing way to report a dirty tree.
    return [root / n for n in names if (root / n).is_file()]


# --------------------------------------------------------------------------
# Selection
# --------------------------------------------------------------------------


@dataclass
class Selection:
    """The files an archive will contain, and how that was decided."""

    files: list[Path]
    root: Path
    #: "git" when derived from `git ls-files`, "filesystem" when walked.
    source: str
    #: Paths refused by :func:`never_package`, with the reason. Empty is the
    #: expected state; a non-empty list is worth printing, because it means
    #: something secret-shaped was tracked.
    refused: list[tuple[str, str]] = field(default_factory=list)
    #: Required build artifacts that were not on disk.
    missing_artifacts: list[str] = field(default_factory=list)

    def relative(self) -> list[str]:
        return [p.relative_to(self.root).as_posix() for p in self.files]


def collect(
    root: Path,
    *,
    exclude_prefixes: tuple[str, ...] = (),
    include_build_artifacts: bool = True,
) -> Selection:
    """Every file that belongs in an archive rooted at `root`.

    `exclude_prefixes` are repo-relative POSIX path prefixes dropped on top of
    the git/ignore decision — the Desktop bundle uses this to omit `plugins/`,
    which is four more complete copies of a `server/` tree it already carries.
    """
    root = root.resolve()
    tracked = git_tracked(root)
    source = "git"
    if tracked is None:
        tracked, source = _fallback_walk(root), "filesystem"

    selected: list[Path] = []
    refused: list[tuple[str, str]] = []
    seen: set[str] = set()

    def consider(path: Path) -> None:
        rel = path.relative_to(root).as_posix()
        if rel in seen:
            return
        reason = never_package(rel)
        if reason is not None:
            refused.append((rel, reason))
            return
        if any(rel.startswith(p) for p in exclude_prefixes):
            return
        seen.add(rel)
        selected.append(path)

    for path in tracked:
        consider(path)

    # Probe for the secret paths rather than waiting to be offered one.
    # `git ls-files` never lists `config/credentials.json` because it is
    # gitignored, so the denylist above would never fire on the real repository
    # and `refused` would be permanently empty -- a check that reports success
    # because it was never reached. The operator of a configured deployment
    # should see "found your credentials file and did not ship it", not
    # silence indistinguishable from "you have no credentials file".
    for rel in sorted(NEVER_PACKAGE_PATHS):
        if (root / rel).is_file() and rel not in seen:
            already = any(r == rel for r, _ in refused)
            if not already:
                refused.append((rel, never_package(rel) or "denylisted"))

    missing: list[str] = []
    if include_build_artifacts:
        for rel in REQUIRED_BUILD_ARTIFACTS:
            if any(rel.startswith(p) for p in exclude_prefixes):
                continue
            path = root / rel
            if path.is_file():
                consider(path)
            else:
                missing.append(rel)

    return Selection(
        files=sorted(selected),
        root=root,
        source=source,
        refused=sorted(refused),
        missing_artifacts=missing,
    )


# --------------------------------------------------------------------------
# Verification — measure the archive, do not restate the intent
# --------------------------------------------------------------------------

#: Values that mean "nobody filled this in". A scanner that fires on the
#: project's own documented placeholders is a scanner that gets switched off.
PLACEHOLDER_MARKERS: tuple[str, ...] = (
    "replace_me", "placeholder", "changeme", "example.invalid",
    "your-", "your_", "xxxx", "notreal", "dummy", "fake",
)

#: Template syntax. Anything still wearing its braces or angle brackets is a
#: form to fill in, not a filled-in form.
_TEMPLATE = re.compile(r"\$\{[^}]*\}|<[^>]{1,40}>|\{\{[^}]*\}\}")

#: Credential shapes, each with what it is. Deliberately specific: a generic
#: entropy heuristic fires on every minified bundle and base64 asset in the
#: tree, and a check that cries wolf on `mcp-app.html` is a check that gets
#: suppressed rather than read.
SECRET_PATTERNS: tuple[tuple[str, "re.Pattern[str]"], ...] = (
    ("Anthropic API key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("OpenAI API key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{32,}")),
    ("GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}")),
    ("GitHub fine-grained PAT", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{60,}")),
    ("AWS access key id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("JSON web token", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")),
    # What `scripts/mint_token.py` mints. The prefix exists so this line can
    # recognize one; the `sha256:<hex>` entry that stands in for it in
    # MAXEY0_MCP_TOKEN_HASHES is not a credential and does not match.
    ("Maxey0 bearer token", re.compile(r"\bm0ss_[A-Za-z0-9_\-]{20,}")),
    # A real home directory names a person and leaks their machine layout into
    # every artifact. Placeholders such as `C:\Users\...` do not match, because
    # "." is not a name character here.
    ("absolute user home path",
     re.compile(r"[A-Za-z]:[\\/]{1,2}Users[\\/]{1,2}[A-Za-z0-9_\-]{2,}|/home/[a-z][a-z0-9_\-]+/")),
    (
        "populated password/secret field",
        re.compile(
            r"""["']?(?:password|passwd|secret|api_key|apikey|access_token|"""
            r"""client_secret|shared_secret|bearer_token)["']?\s*[:=]\s*"""
            r"""["']([^"'\s]{8,})["']""",
            re.IGNORECASE,
        ),
    ),
)

#: Suffixes whose bytes are not credential-bearing text. The App bundle is
#: 475 KB of minified JavaScript; scanning it costs time and finds nothing a
#: human would act on.
_BINARY_SUFFIXES = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".woff", ".woff2",
    ".ttf", ".otf", ".pdf", ".zip", ".gz", ".mcpb", ".dxt", ".pyc",
})


def _is_placeholder(value: str) -> bool:
    if not value.strip():
        return True
    lowered = value.lower()
    return any(m in lowered for m in PLACEHOLDER_MARKERS) or bool(
        _TEMPLATE.search(value)
    )


def looks_like_a_credential(value: str) -> bool:
    """Whether a `key: "value"` pair carries something with secret shape.

    Only the generic `password`/`secret`/`api_key` field pattern consults this.
    The named patterns above (``sk-ant-``, ``AKIA``, a PEM header) identify
    themselves and need no heuristic.

    The generic one cannot. Without a shape gate it fires on test fixtures —
    the repository has ``store.complete(tid, {"secret": "do-not-leak"})`` in a
    test that asserts the payload does *not* leak, and
    ``ANTHROPIC_API_KEY="short-key"`` in a key-masking test. Both are correct
    code. A release check that a reader learns to dismiss is worse than none,
    because the one real hit arrives in the same color as the noise.

    So: a credential is long and mixes character classes. ``do-not-leak`` and
    ``short-key`` are neither. The deliberate cost is that a genuinely weak
    secret — ``password123`` — is missed here; the path denylist and the named
    patterns are what actually guard `config/credentials.json`, and this is a
    backstop behind them rather than the mechanism.
    """
    if len(value) >= 32:
        return True
    if len(value) < 16:
        return False
    classes = sum((
        any(c.islower() for c in value),
        any(c.isupper() for c in value),
        any(c.isdigit() for c in value),
        any(not c.isalnum() for c in value),
    ))
    return classes >= 3


def scan_for_secrets(files: list[Path], root: Path) -> list[str]:
    """Credential shapes found in the bytes about to be archived.

    Returns one human-readable finding per hit. An empty list is the only
    acceptable result for a release build, and it is an *empty measurement*
    rather than an absent one: :func:`scan_for_secrets` is exercised by a test
    that plants a key and asserts it is caught, so a zero here means the
    scanner looked and found nothing rather than never having looked.
    """
    findings: list[str] = []
    for path in files:
        if path.suffix.lower() in _BINARY_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rel = path.relative_to(root).as_posix()
        for label, pattern in SECRET_PATTERNS:
            generic = pattern.groups > 0
            for match in pattern.finditer(text):
                captured = match.group(1) if generic else match.group(0)
                if _is_placeholder(captured):
                    continue
                if generic and not looks_like_a_credential(captured):
                    continue
                line = text.count("\n", 0, match.start()) + 1
                findings.append(f"{rel}:{line}: {label}")
                break  # one finding per pattern per file is enough to act on
    return sorted(findings)
