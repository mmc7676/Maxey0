"""What must never be in a distributable archive, asserted against real zips.

Every test here guards a defect that actually shipped, or would have. The
originating audit found four, all of them the same shape: two hand-maintained
exclusion lists, in `build_source_archive.py` and `build_package.py`, that
disagreed with each other and with `.gitignore`.

  - `config/credentials.json` is gitignored as "Real secrets" and was in
    neither list, while both builders walked the filesystem rather than git.
  - `.env` was matched by exact name, so `.env.local` and `.env.production` —
    the two files a real deployment creates — were never excluded.
  - `.egg-info` sat in a *file*-suffix set while naming a *directory*, so
    `maxey0_superspace.egg-info/` shipped in every source archive: 906 files
    against 899 tracked.
  - `.wrangler` was excluded from the source archive and not the marketplace
    archive.

`scripts/_packaging.py` replaced both lists with `git ls-files`, so these tests
exist to prove the replacement behaves — and to fail loudly if anybody adds a
third list.

**On the secret scanner.** A scanner that finds nothing because its patterns
match nothing is the same defect as a cache whose metrics are pinned at zero:
a green number that measures the wrong thing. So every scanner assertion here
has a *positive control* — a planted credential the scanner must catch — next
to the negative one. A clean release build then means the scanner looked, not
that it was never pointed at anything.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import unittest
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _env import ROOT, TMPDIR  # noqa: E402,F401

sys.path.insert(0, str(ROOT / "scripts"))
import _packaging  # noqa: E402
from _packaging import (  # noqa: E402
    REQUIRED_BUILD_ARTIFACTS,
    collect,
    never_package,
    scan_for_secrets,
)

PY = sys.executable


def _run(*args: str, cwd: pathlib.Path = ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PY, *args], cwd=cwd, capture_output=True, text=True,
    )


class TestNeverPackage(unittest.TestCase):
    """The denylist, independent of git. Belt to `git ls-files`'s braces."""

    def test_credentials_json_is_refused_by_path_and_by_name(self):
        self.assertIsNotNone(never_package("config/credentials.json"))
        # The same file reachable under any other path is still secrets.
        self.assertIsNotNone(never_package("deploy/credentials.json"))

    def test_every_dotenv_variant_is_refused(self):
        # The original bug: `.env` matched exactly, so these three did not.
        for name in (".env", ".env.local", ".env.production", ".env.staging"):
            with self.subTest(name=name):
                self.assertIsNotNone(never_package(name))
                self.assertIsNotNone(never_package(f"deploy/{name}"))

    def test_env_example_is_the_one_dotenv_that_ships(self):
        """It is the tracked documentation of every variable the code reads."""
        self.assertIsNone(never_package(".env.example"))

    def test_ordinary_source_is_not_refused(self):
        for rel in ("maxey0_ss/mcp_surface.py", "README.md",
                    "config/credentials.example.json", "Dockerfile"):
            with self.subTest(rel=rel):
                self.assertIsNone(never_package(rel))


class TestSelection(unittest.TestCase):
    """What `collect()` chooses for the real repository."""

    @classmethod
    def setUpClass(cls):
        cls.sel = collect(ROOT)
        cls.rel = set(cls.sel.relative())

    def test_selection_is_derived_from_git_not_from_a_list(self):
        self.assertEqual(self.sel.source, "git")

    def test_no_egg_info_directory_ships(self):
        """`.egg-info` was in EXCLUDE_SUFFIXES, which matches file suffixes."""
        offenders = [r for r in self.rel if ".egg-info/" in r]
        self.assertEqual(offenders, [], f"egg-info files selected: {offenders}")

    def test_no_wrangler_state_ships(self):
        offenders = [r for r in self.rel if ".wrangler" in r]
        self.assertEqual(offenders, [])

    def test_no_pycache_or_compiled_python_ships(self):
        offenders = [r for r in self.rel
                     if "__pycache__" in r or r.endswith((".pyc", ".pyo"))]
        self.assertEqual(offenders, [])

    def test_no_node_modules_or_venv_ships(self):
        offenders = [r for r in self.rel
                     if "node_modules/" in r or r.startswith(".venv/")]
        self.assertEqual(offenders, [])

    def test_the_built_mcp_app_is_selected(self):
        """The bundle is gitignored build output and is nonetheless the product.

        Without it the server falls back to an unbuilt stub and reports
        `app_artifact.kind == "fallback-stub"`, which the deployment checklist
        lists as a rollback trigger. An archive that guarantees its own
        rollback condition is a packaging bug, not a packaging preference.
        """
        for rel in REQUIRED_BUILD_ARTIFACTS:
            with self.subTest(rel=rel):
                self.assertIn(rel, self.rel)
        self.assertEqual(self.sel.missing_artifacts, [])

    def test_env_example_ships_and_no_other_dotenv_does(self):
        dotenvs = sorted(r for r in self.rel
                         if r.rsplit("/", 1)[-1].startswith(".env"))
        self.assertEqual(dotenvs, [".env.example"])

    def test_exclude_prefixes_narrow_the_selection(self):
        narrowed = collect(ROOT, exclude_prefixes=("plugins/",))
        self.assertEqual(
            [r for r in narrowed.relative() if r.startswith("plugins/")], [])
        self.assertLess(len(narrowed.files), len(self.sel.files))


#: Credential shapes for the positive controls, assembled at runtime rather
#: than written as literals.
#:
#: This is not squeamishness. The scanner reads the bytes of every file it is
#: about to archive, and this file is one of them — so a literal
#: `AKIA...`-shaped string here fails the release build, from the test that
#: proves the release build can detect one. The first instinct is to exempt
#: `tests/`, which is the wrong fix: a real credential pasted into a fixture
#: still ships. Assembling the value keeps the control genuine — the scanner is
#: handed a complete, matching key — while leaving no credential shape in the
#: repository at all, including in the test that proves we detect them.
def _planted(kind: str) -> str:
    if kind == "aws":
        return "AK" + "IA" + "IOSFODNN7EXAMPLE"
    if kind == "pem":
        return "-" * 5 + "BEGIN RSA PRIVATE" + " KEY" + "-" * 5
    if kind == "password":
        return "Tb7#qW2v" + "L9xR4mZ8"
    if kind == "anthropic":
        return "sk-" + "ant-api03-" + "A" * 40
    raise AssertionError(kind)


class TestSecretScanner(unittest.TestCase):
    """Positive controls first: prove the scanner can fail before trusting it."""

    def setUp(self):
        self.dir = TMPDIR / f"scan-{self.id().rsplit('.', 1)[-1]}"
        self.dir.mkdir(parents=True, exist_ok=True)

    def _scan(self, name: str, body: str) -> list[str]:
        path = self.dir / name
        path.write_text(body, encoding="utf-8")
        return scan_for_secrets([path], self.dir)

    def test_catches_a_planted_anthropic_key(self):
        found = self._scan("c.json", '{"api_key": "%s"}' % _planted("anthropic"))
        self.assertTrue(found, "scanner missed an Anthropic-shaped key")

    def test_catches_a_planted_aws_key_id(self):
        self.assertTrue(self._scan("aws.txt", _planted("aws")))

    def test_catches_a_planted_private_key_block(self):
        self.assertTrue(self._scan("id.pem", _planted("pem") + "\nMIIE...\n"))

    def test_catches_a_populated_password_field(self):
        self.assertTrue(self._scan(
            "creds.json", '{"neo4j_password": "%s"}' % _planted("password")))

    def test_this_file_carries_no_credential_shape_of_its_own(self):
        """The controls above are assembled, not written down. See `_planted`.

        Exempting `tests/` from the scan would have been the easy fix and the
        wrong one: a real credential pasted into a fixture still ships.
        """
        self.assertEqual(scan_for_secrets([pathlib.Path(__file__)], ROOT), [])

    def test_the_generic_field_pattern_has_a_credential_shape_gate(self):
        """Directly, so the gate is testable without going through a file.

        The repository contains two `secret`-ish fields that are correct code:
        a payload-leak test using `"do-not-leak"` and a key-masking test using
        `"short-key"`. Both matched the generic pattern before the gate existed.
        A release check that a reader learns to dismiss is worse than none.
        """
        for noise in ("do-not-leak", "short-key", "n/a", "true", "disabled"):
            with self.subTest(value=noise):
                self.assertFalse(_packaging.looks_like_a_credential(noise))
        for real in (_planted("password"), "a" * 32, "S3cr3t-" + "P@ssw0rd!"):
            with self.subTest(value=real):
                self.assertTrue(_packaging.looks_like_a_credential(real))

    def test_the_two_known_test_fixtures_do_not_fire(self):
        """Named, so a future loosening of the gate fails here rather than in CI."""
        for rel in ("maxey0_ss/tests/test_tasks.py",
                    "tests/test_live_session_and_client.py"):
            with self.subTest(rel=rel):
                self.assertEqual(scan_for_secrets([ROOT / rel], ROOT), [])

    def test_catches_a_filled_in_credentials_file(self):
        """The exact payload `config/credentials.example.json` describes."""
        filled = (ROOT / "config" / "credentials.example.json").read_text(
            encoding="utf-8"
        ).replace('"api_key": ""', '"api_key": "%s"' % _planted("anthropic"))
        self.assertTrue(self._scan("credentials.json", filled))

    def test_does_not_fire_on_empty_or_placeholder_values(self):
        """A scanner that cries wolf is a scanner somebody switches off."""
        for body in (
            '{"client_secret": ""}',
            '{"client_secret": "REPLACE_ME"}',
            '{"api_key": "sk-ant-PLACEHOLDER"}',
            '{"issuer": "https://issuer.example.invalid"}',
            '{"password": "<your-password-here>"}',
        ):
            with self.subTest(body=body):
                self.assertEqual(self._scan("x.json", body), [])

    def test_does_not_fire_on_the_tracked_example_file(self):
        example = ROOT / "config" / "credentials.example.json"
        self.assertEqual(scan_for_secrets([example], ROOT), [])

    def test_the_whole_repository_selection_is_clean(self):
        """The release claim, measured rather than asserted."""
        sel = collect(ROOT)
        self.assertEqual(scan_for_secrets(sel.files, ROOT), [])


class TestBuildersRefuseSecrets(unittest.TestCase):
    """End-to-end: plant the file the audit warned about, then build.

    The audit's acceptance criterion, verbatim: "Create a dummy
    `config/credentials.json`, run both builders, and assert the string does
    not appear in either archive's namelist."
    """

    PLANTED = ROOT / "config" / "credentials.json"

    def setUp(self):
        if self.PLANTED.exists():  # never clobber a real deployment's file
            self.skipTest("config/credentials.json exists; refusing to touch it")
        self.PLANTED.write_text(
            '{"semantic_gate": {"api_key": "%s"}}' % _planted("anthropic"),
            encoding="utf-8",
        )

    def tearDown(self):
        self.PLANTED.unlink(missing_ok=True)

    def test_credentials_json_is_not_selected_for_any_archive(self):
        for prefixes in ((), ("plugins/",)):
            with self.subTest(prefixes=prefixes):
                sel = collect(ROOT, exclude_prefixes=prefixes)
                self.assertNotIn("config/credentials.json", sel.relative())
                self.assertTrue(
                    any(rel == "config/credentials.json"
                        for rel, _ in sel.refused),
                    "the file must be refused explicitly, not merely absent",
                )

    def test_package_check_still_passes_with_secrets_on_disk(self):
        """Refusal, not failure: a real deployment has this file and must build.

        `--allow-dirty` because this test plants a file, which by construction
        makes the tree dirty. The dirty gate itself is covered below.
        """
        proc = _run("scripts/build_package.py", "--check", "--allow-dirty")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("refused", proc.stdout)


class TestDirtyTreeIsAGate(unittest.TestCase):
    """A dirty tree is a correctness problem, not a labeling one.

    Both builders select contents with `git ls-files`. An untracked file is
    therefore *absent* from the archive and a deleted-but-tracked file is
    *missing from disk*, so an archive built from a dirty tree describes
    neither the commit nor the working tree.

    Measured, not hypothetical: regenerating `plugins/**` in this release
    deleted two stale generated files and created three new ones. Packaged
    without committing, the marketplace archive would have shipped plugin
    trees missing three files that `build_planes.py --check` had *just*
    declared correct.
    """

    #: A file this test creates and removes, so the dirty state is made rather
    #: than waited for.
    #:
    #: These tests used to skip when the tree happened to be clean — which is
    #: exactly the state a release build runs in, so the gate guarding the
    #: release was unexercised by every release. A skipped test reads as a
    #: passing one in the summary line and is neither.
    MARKER = ROOT / ".dirty-tree-probe.tmp"

    def _dirty(self):
        self.MARKER.write_text("probe\n", encoding="utf-8")
        self.addCleanup(self.MARKER.unlink, True)

    def _is_dirty(self) -> bool:
        return bool(subprocess.run(
            ["git", "status", "--porcelain"], cwd=ROOT,
            capture_output=True, text=True,
        ).stdout.strip())

    def test_source_archive_refuses_a_dirty_tree(self):
        self._dirty()
        proc = _run("scripts/build_source_archive.py")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("dirty", (proc.stdout + proc.stderr).lower())

    def test_package_build_refuses_a_dirty_tree(self):
        self._dirty()
        proc = _run("scripts/build_package.py", "--check")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("dirty", (proc.stdout + proc.stderr).lower())

    def test_allow_dirty_gets_past_the_gate_it_names(self):
        self._dirty()
        proc = _run("scripts/build_package.py", "--check", "--allow-dirty")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("allow-dirty", proc.stdout)

    def test_both_builders_document_the_same_escape_hatch(self):
        for name in ("build_source_archive.py", "build_package.py"):
            with self.subTest(script=name):
                src = (ROOT / "scripts" / name).read_text(encoding="utf-8")
                self.assertIn("--allow-dirty", src)
                self.assertIn("allow_dirty", src)

    def test_the_problem_report_names_untracked_and_modified_separately(self):
        """An operator needs to know which failure mode they are in."""
        self._dirty()
        problem = _packaging.dirty_tree_problem(ROOT)
        self.assertIsNotNone(problem)
        self.assertIn("untracked", problem)

    def test_a_clean_tree_reports_no_problem(self):
        """Proved against this repository when it is clean, not only in the abstract."""
        if not self._is_dirty():
            self.assertIsNone(_packaging.dirty_tree_problem(ROOT))
        scratch = TMPDIR / "clean-probe"
        scratch.mkdir(parents=True, exist_ok=True)
        # No .git at all: git cannot answer, so there is nothing to refuse.
        self.assertIsNone(_packaging.dirty_tree_problem(scratch))

    def test_an_untracked_file_really_would_be_absent_from_the_archive(self):
        """Why the gate exists, rather than that the gate exists.

        Regenerating `plugins/**` in this release deleted two stale generated
        files and created three new ones. Packaged without committing, the
        marketplace archive would have shipped plugin trees missing three files
        that `build_planes.py --check` had just declared correct.
        """
        self._dirty()
        selected = collect(ROOT).relative()
        self.assertNotIn(self.MARKER.name, selected)
        self.assertTrue(self.MARKER.exists())


class TestPluginTreesAreVerifiedBeforePackaging(unittest.TestCase):
    """`plugins/**` is generated; packaging used to zip it unverified.

    At `a31ee45` fifteen generated files had already drifted from `server/`
    and every v1.0.0 archive shipped them, because `build_package.py` called
    neither `build_planes.py` nor its `--check`.
    """

    def test_generated_plugin_trees_match_their_source(self):
        proc = _run("scripts/build_planes.py", "--check")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_build_package_invokes_the_check(self):
        src = (ROOT / "scripts" / "build_package.py").read_text(encoding="utf-8")
        self.assertIn("check_planes", src)
        self.assertIn("build_planes.py", src)


class TestPreflightNamesOnlyReachablePaths(unittest.TestCase):
    """Every path the start-up failure message prints must exist in a plugin.

    `_preflight.require` resolves `root` to the *plugin* root and used to print
    `pip install -r "<plugin>/requirements.txt"`. No plugin tree has ever
    contained a requirements.txt, so the one command on the one start-up
    failure path named a file the reader could not open.
    """

    PLUGINS = ("maxey0", "maxey0-context", "maxey0-loops", "maxey0-observe")

    def test_no_plugin_contains_a_requirements_file(self):
        """The premise. If this ever changes, the fix below can be revisited."""
        found = sorted(
            p.relative_to(ROOT).as_posix()
            for p in (ROOT / "plugins").rglob("requirements*.txt")
        )
        self.assertEqual(found, [])

    def test_preflight_does_not_name_a_requirements_file_in_its_message(self):
        for plugin in self.PLUGINS:
            path = ROOT / "plugins" / plugin / "server" / "_preflight.py"
            with self.subTest(plugin=plugin):
                self.assertTrue(path.exists())
                src = path.read_text(encoding="utf-8")
                # Strip comments: the fix is explained in one, by name.
                code = "\n".join(
                    line for line in src.splitlines()
                    if not line.lstrip().startswith("#")
                )
                self.assertNotIn("requirements.txt", code)
                self.assertIn("pip install {dists}", code)

    def test_every_filesystem_path_preflight_prints_exists_in_the_plugin(self):
        """Executes the real message path with a module that cannot be imported."""
        for plugin in self.PLUGINS:
            plugin_root = ROOT / "plugins" / plugin
            with self.subTest(plugin=plugin):
                proc = subprocess.run(
                    [PY, "-c",
                     "import sys, pathlib;"
                     f"sys.path.insert(0, r'{plugin_root / 'server'}');"
                     "import _preflight;"
                     "_preflight.require('a_module_that_cannot_exist')"],
                    capture_output=True, text=True,
                )
                self.assertEqual(proc.returncode, 1)
                message = proc.stderr
                self.assertIn("cannot start", message)
                # Any absolute path inside quotes is a path the user is being
                # told to act on. Every one of them must resolve.
                quoted = [
                    part for part in message.split('"')
                    if (":\\" in part or part.startswith("/")) and len(part) > 3
                ]
                self.assertTrue(quoted, f"no quoted path in message: {message}")
                for candidate in quoted:
                    path = pathlib.Path(candidate)
                    self.assertTrue(
                        path.exists(),
                        f"{plugin}: preflight prints {candidate!r}, which does "
                        f"not exist",
                    )


class TestArchiveContents(unittest.TestCase):
    """Build the real archives into a temp dist and inspect the namelists."""

    @classmethod
    def setUpClass(cls):
        cls.out = TMPDIR / "dist-check"
        cls.out.mkdir(parents=True, exist_ok=True)
        market = collect(ROOT, exclude_prefixes=("experiments/cross-window/",
                                                 "experiments/exp-"))
        desktop = collect(ROOT, exclude_prefixes=("experiments/cross-window/",
                                                  "experiments/exp-",
                                                  "server/lib/", "server/venv/",
                                                  "plugins/"))
        cls.zips = {}
        for label, sel in (("market", market), ("desktop", desktop)):
            target = cls.out / f"{label}.zip"
            with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
                for path in sel.files:
                    zf.write(path, path.relative_to(ROOT).as_posix())
            with zipfile.ZipFile(target) as zf:
                cls.zips[label] = set(zf.namelist())

    def test_no_archive_contains_a_credentials_file(self):
        for label, names in self.zips.items():
            with self.subTest(label=label):
                self.assertEqual(
                    [n for n in names if n.endswith("credentials.json")], [])

    def test_no_archive_contains_a_dotenv_other_than_the_example(self):
        for label, names in self.zips.items():
            with self.subTest(label=label):
                dotenvs = sorted(n for n in names
                                 if n.rsplit("/", 1)[-1].startswith(".env"))
                self.assertEqual(dotenvs, [".env.example"])

    def test_the_desktop_bundle_carries_the_built_app(self):
        """Without it, every installed .mcpb reports kind == fallback-stub."""
        self.assertIn("mcp_apps/super_space_react/dist/mcp-app.html",
                      self.zips["desktop"])

    def test_the_desktop_bundle_carries_no_plugin_copies(self):
        self.assertEqual(
            [n for n in self.zips["desktop"] if n.startswith("plugins/")], [])

    def test_the_marketplace_archive_carries_the_marketplace_manifest(self):
        self.assertIn(".claude-plugin/marketplace.json", self.zips["market"])

    def test_both_archives_are_clean_of_build_and_cache_noise(self):
        for label, names in self.zips.items():
            for pattern in ("__pycache__", ".egg-info/", ".wrangler",
                            "node_modules/", ".venv/", ".git/"):
                with self.subTest(label=label, pattern=pattern):
                    self.assertEqual([n for n in names if pattern in n], [])


class TestOneSourceOfTruth(unittest.TestCase):
    """Guard against a third hand-maintained exclusion list appearing."""

    def test_neither_builder_keeps_its_own_exclusion_list(self):
        for name in ("build_package.py", "build_source_archive.py"):
            src = (ROOT / "scripts" / name).read_text(encoding="utf-8")
            with self.subTest(script=name):
                self.assertIn("from _packaging import", src)
                for banned in ("EXCLUDE_NAMES", "EXCLUDE_SUFFIXES",
                               "EXCLUDE_DIRS"):
                    self.assertNotIn(
                        f"{banned} = ", src,
                        f"{name} has grown its own {banned}; inclusion is "
                        f"derived from git in scripts/_packaging.py",
                    )

    def test_the_fallback_walk_is_reported_as_such(self):
        """A tree with no git must not claim git-derived precision."""
        scratch = TMPDIR / "no-git-tree"
        (scratch / "pkg").mkdir(parents=True, exist_ok=True)
        (scratch / "pkg" / "mod.py").write_text("x = 1\n", encoding="utf-8")
        (scratch / ".env.local").write_text("SECRET=1\n", encoding="utf-8")
        sel = collect(scratch, include_build_artifacts=False)
        self.assertEqual(sel.source, "filesystem")
        self.assertIn("pkg/mod.py", sel.relative())
        self.assertNotIn(".env.local", sel.relative())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class TestNoBuildOutputReachesAPluginTree(unittest.TestCase):
    """A gitignore rule is not inherited by a `copytree`.

    `.gitignore` excludes `server/maxey0_studio/static/app/` and says why: "a
    committed bundle would be one more thing that can drift from the source it
    was built from". `build_planes.py` copies `server/` wholesale into four
    plugin trees, where nothing ignored it — so the first `npm run build` in
    `ui/` put the bundle in four places that were then committed. Four copies of
    a bundle the root rule exists to keep out of one.
    """

    def test_no_plugin_tree_carries_the_built_front_end(self):
        offenders = sorted(
            p.relative_to(ROOT).as_posix()
            for p in (ROOT / "plugins").rglob("*")
            if p.is_file() and "static/app" in p.as_posix()
        )
        self.assertEqual(offenders, [], "built UI bundle copied into a plugin")

    def test_nothing_under_static_app_is_tracked_anywhere(self):
        import subprocess

        tracked = subprocess.run(
            ["git", "ls-files", "*static/app/*"], cwd=ROOT,
            capture_output=True, text=True,
        ).stdout.split()
        self.assertEqual(tracked, [])

    def test_the_generator_excludes_it_by_name(self):
        src = (ROOT / "scripts" / "build_planes.py").read_text(encoding="utf-8")
        self.assertIn('"app"', src)
        self.assertIn("ignore_patterns", src)

    def test_no_source_map_ships(self):
        """A .map is the source of a bundle, shipped beside the bundle."""
        offenders = sorted(
            p.relative_to(ROOT).as_posix()
            for p in (ROOT / "plugins").rglob("*.map")
        )
        self.assertEqual(offenders, [])


class TestEveryPluginReferenceExists(unittest.TestCase):
    """maxey0-observe registered a SessionStart hook for a script it did not
    ship, and --check passed because it compared the tree with the builder's
    own (equally incomplete) output."""

    def test_no_shipped_plugin_names_a_missing_file(self):
        import build_planes

        for plugin in sorted(p for p in (ROOT / "plugins").iterdir() if p.is_dir()):
            with self.subTest(plugin=plugin.name):
                self.assertEqual(build_planes.missing_plugin_paths(plugin), [])

    def test_the_check_detects_a_missing_hook_script(self):
        import tempfile

        import build_planes

        with tempfile.TemporaryDirectory() as tmp:
            hooks = pathlib.Path(tmp) / "hooks"
            hooks.mkdir()
            (hooks / "hooks.json").write_text(
                '{"hooks": {"SessionStart": [{"hooks": [{"type": "command", '
                '"command": "python \\"${CLAUDE_PLUGIN_ROOT}/hooks/gone.py\\""}]}]}}',
                encoding="utf-8")
            self.assertEqual(build_planes.missing_plugin_paths(pathlib.Path(tmp)),
                             ["hooks/hooks.json -> hooks/gone.py"])


class TestPackagingRunsThePluginValidator(unittest.TestCase):
    """build_package --check passed while validate_plugin.py reported FAILED."""

    def test_build_package_invokes_the_validator(self):
        src = (ROOT / "scripts" / "build_package.py").read_text(encoding="utf-8")
        self.assertIn("check_validator()", src)
        self.assertIn("validate_plugin.py", src)

    def test_every_skill_directory_bundles_reference_material(self):
        for skill in sorted(p for p in (ROOT / "skills").iterdir() if p.is_dir()):
            with self.subTest(skill=skill.name):
                files = [q for q in skill.rglob("*") if q.is_file()]
                self.assertGreaterEqual(len(files), 2)
