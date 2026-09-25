"""One name per role, enforced in both directions.

At 0.2.0 this tree spelled its own product twelve ways: `Maxey0-SuperSpace`(31
files), `maxey0_ss`(67), `maxey0-ss`(47), `SuperSpace`(48), `SuperSpaceSystem`
(25), `Super Space`(21), `Maxey0SuperSpace`(5), `Maxey0System`(5), `Maxey0SS`(4),
`Maxey0-SS`(2), `M0-SS`(2), `maxey0-superspace`(2). Four of them were class
aliases exported from `maxey0_ss/__init__.py`, so a reader could not tell which
was real. The MCP surface was split too — twenty-six `maxey0-ss.*` tools and one
`scw.observe_host_window`.

A package that is about to be published under several distribution channels
cannot spell itself twelve ways: the plugin id, the PyPI name, the npm name, the
MCP namespace and the prose all have to agree, and every one of them is written
in a different file.

Both directions matter. A retired spelling that reappears fails here. A
canonical name that stops being used fails too, because a naming rule nothing
observes is the same defect as a config key nothing reads.
"""

from __future__ import annotations

import pathlib
import re
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _env import ROOT  # noqa: E402

#: role -> the one token that may be used for it.
CANONICAL = {
    "product": "Maxey0-SuperSpace",
    "short": "Maxey0",
    "python_package": "maxey0_ss",
    "mcp_namespace": "maxey0-ss",
    "distribution_id": "maxey0-superspace",
    "system_class": "SuperSpaceSystem",
}

#: Spelling -> why it was retired. Matched as a whole word.
RETIRED = {
    "Maxey0SuperSpace": "class alias for SuperSpaceSystem",
    "Maxey0SS": "class alias for SuperSpaceSystem",
    "Maxey0-SS": "abbreviation of the product name",
    "M0-SS": "abbreviation of the product name",
    "Maxey0System": "pre-rename compatibility alias",
    "Super Space": "the product is one word after Maxey0-, never two",
}

#: Files that record history and must keep the words they recorded. A changelog
#: that silently rewrites what a previous release was called is worse than an
#: inconsistent name.
HISTORY = {"CHANGELOG.md"}

#: Extensions worth checking. Generated bundles and lockfiles are excluded:
#: `workers/mcp-edge/src/generated/` is emitted by `export_mcp_surface.py` from
#: the surface this test already checks directly, so scanning it would report
#: the same fact twice and fail on minified variable names.
SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".md", ".json", ".toml", ".html", ".css"}

EXCLUDE_PARTS = {
    ".git", ".venv", "node_modules", "__pycache__", "dist", "build",
    ".pytest_cache", "generated", ".wrangler",
}


def _source_files() -> list[pathlib.Path]:
    out = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
            continue
        rel = path.relative_to(ROOT)
        if any(part in EXCLUDE_PARTS for part in rel.parts):
            continue
        if rel.name in HISTORY:
            continue
        # This file names every retired spelling on purpose.
        if rel.as_posix() == "tests/test_ontology.py":
            continue
        out.append(path)
    return out


class TestRetiredSpellingsAreGone(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.files = _source_files()

    def test_no_retired_spelling_survives(self):
        for spelling, why in RETIRED.items():
            pattern = re.compile(rf"(?<![\w-]){re.escape(spelling)}(?![\w-])")
            offenders = []
            for path in self.files:
                text = path.read_text(encoding="utf-8", errors="replace")
                for match in pattern.finditer(text):
                    line = text.count("\n", 0, match.start()) + 1
                    offenders.append(f"{path.relative_to(ROOT).as_posix()}:{line}")
            with self.subTest(spelling=spelling):
                self.assertEqual(
                    offenders, [],
                    f"{spelling!r} was retired ({why}); use "
                    f"{CANONICAL['product']!r} or {CANONICAL['system_class']!r}",
                )

    def test_the_package_exports_exactly_one_system_name(self):
        import maxey0_ss

        self.assertEqual(
            sorted(maxey0_ss.__all__), ["SuperSpaceSystem", "__version__"],
        )
        for retired in ("Maxey0System", "Maxey0SuperSpace", "Maxey0SS"):
            with self.subTest(alias=retired):
                self.assertFalse(
                    hasattr(maxey0_ss, retired),
                    f"maxey0_ss.{retired} is a twelfth spelling that survives "
                    f"into the release it was meant to end",
                )


class TestMcpNamespaceIsSingular(unittest.TestCase):
    """Twenty-six tools were `maxey0-ss.*` and one was not."""

    @classmethod
    def setUpClass(cls):
        from maxey0_ss.mcp_surface import build_surface

        cls.surface = build_surface()

    def test_every_tool_is_in_the_one_namespace(self):
        prefix = CANONICAL["mcp_namespace"] + "."
        for tool in self.surface.tools:
            with self.subTest(tool=tool.name):
                self.assertTrue(
                    tool.name.startswith(prefix),
                    f"{tool.name} is outside the {prefix!r} namespace",
                )

    def test_every_resource_uri_is_in_the_one_namespace(self):
        ns = CANONICAL["mcp_namespace"]
        for resource in self.surface.resources:
            with self.subTest(uri=resource.uri):
                self.assertIn(ns, resource.uri)

    def test_no_tool_name_is_double_prefixed(self):
        """A namespace rename applied twice is its own kind of inconsistency."""
        ns = CANONICAL["mcp_namespace"]
        for tool in self.surface.tools:
            with self.subTest(tool=tool.name):
                self.assertNotIn(f"{ns}.{ns}.", tool.name)

    def test_the_never_cache_list_uses_current_tool_names(self):
        """It keys on tool names, so a rename silently unlists an entry."""
        from maxey0_ss.cache import NEVER_CACHE

        names = {t.name for t in self.surface.tools}
        for listed in NEVER_CACHE:
            with self.subTest(tool=listed):
                self.assertIn(
                    listed, names,
                    f"NEVER_CACHE names {listed!r}, which is not a tool; a "
                    f"never-cache rule keyed on a stale name enforces nothing",
                )


class TestCanonicalNamesAreActuallyUsed(unittest.TestCase):
    """The other direction: a rule nothing observes is not a rule."""

    @classmethod
    def setUpClass(cls):
        cls.blob = "\n".join(
            p.read_text(encoding="utf-8", errors="replace") for p in _source_files()
        )

    def test_each_canonical_token_appears_somewhere(self):
        for role, token in CANONICAL.items():
            with self.subTest(role=role):
                self.assertIn(token, self.blob)

    def test_the_distribution_id_is_what_pyproject_publishes(self):
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn(f'name = "{CANONICAL["distribution_id"]}"', text)

    def test_the_python_package_is_what_the_system_class_lives_in(self):
        module = sys.modules.get(CANONICAL["python_package"])
        if module is None:
            import importlib

            module = importlib.import_module(CANONICAL["python_package"])
        self.assertTrue(hasattr(module, CANONICAL["system_class"]))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class TestNothingShipsAsAStub(unittest.TestCase):
    """A distribution that describes what it would contain is a label.

    The rule this enforces: indicate future work in ROADMAP.md with capability
    names and outcomes, and leave nothing in the tree that hints at the shape of
    something unbuilt. A partial implementation marked TODO is a specification
    somebody else can ship first, and a `coming soon` in a shipped manifest is a
    promise the build has not earned.

    `implemented: false` on a provider socket is deliberately not caught here.
    That is a runtime fact about this build, reported through the same
    `configured`/`implemented` split everything else uses — it tells a deployer
    where the gap is rather than hinting at what fills it.
    """

    #: Code markers, matched case-SENSITIVELY as whole words. Lower case is
    #: deliberate to exclude: `"xxxx"` is a legitimate entry in the placeholder
    #: marker list that the credential checks match against, and a rule that
    #: fires on the thing it is meant to protect is a rule people delete.
    MARKERS = ("TODO", "FIXME", "XXX", "HACK")

    #: Prose, matched case-insensitively. These say "unfinished" in words.
    PHRASES = ("coming soon", "not implemented yet", "placeholder implementation",
               "to be implemented", "work in progress")

    #: Where unbuilt work is allowed to be described, and the two words that
    #: legitimately name a real runtime state rather than an unfinished one.
    #: Lockfiles are machine-generated dependency graphs; a hash in one is not
    #: a statement about this project.
    ALLOWED_PATHS = ("docs/", "CHANGELOG.md", "tests/", "maxey0_ss/tests/")
    ALLOWED_NAMES = ("package-lock.json", "poetry.lock", "uv.lock")
    ALLOWED_PHRASES = ("fallback-stub", "stub MCP App host", "stub host",
                       "maxey0-stub-host", "unbuilt stub", "the stub",
                       "a stub", "~33-line stub", "not a stub")

    def test_no_shipped_file_advertises_unfinished_work(self):
        import subprocess

        tracked = subprocess.run(
            ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
        ).stdout.split()
        offenders = []
        for rel in tracked:
            if rel.startswith(self.ALLOWED_PATHS):
                continue
            if rel.rsplit("/", 1)[-1] in self.ALLOWED_NAMES:
                continue
            if pathlib.Path(rel).suffix not in SOURCE_SUFFIXES:
                continue
            path = ROOT / rel
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            checks = (
                [(m, re.compile(rf"(?<![\w-]){m}(?![\w-])")) for m in self.MARKERS]
                + [(p, re.compile(re.escape(p), re.IGNORECASE)) for p in self.PHRASES]
            )
            for label, pattern in checks:
                for match in pattern.finditer(text):
                    line_no = text.count("\n", 0, match.start()) + 1
                    line = text.splitlines()[line_no - 1]
                    if any(ok.lower() in line.lower() for ok in self.ALLOWED_PHRASES):
                        continue
                    offenders.append(f"{rel}:{line_no}: {label}")
        self.assertEqual(
            offenders, [],
            f"shipped files advertising unfinished work: {offenders}. Describe "
            f"it in docs/ROADMAP.md instead, by outcome and without shape.",
        )

    def test_the_roadmap_names_no_file_paths_or_interfaces(self):
        """Future work is described by outcome, never by where it would go."""
        text = (ROOT / "docs" / "ROADMAP.md").read_text(encoding="utf-8")
        for pattern, why in (
            (r"maxey0_ss/[\w/]+\.py", "a module path"),
            (r"\bdef \w+\(", "a function signature"),
            (r"\bclass \w+[:(]", "a class declaration"),
        ):
            with self.subTest(pattern=why):
                self.assertIsNone(
                    re.search(pattern, text),
                    f"ROADMAP.md names {why}; describe the capability instead",
                )

    def test_the_roadmap_states_what_is_not_planned(self):
        """Absence reads as oversight unless it is stated."""
        text = (ROOT / "docs" / "ROADMAP.md").read_text(encoding="utf-8")
        self.assertIn("Not planned", text)
