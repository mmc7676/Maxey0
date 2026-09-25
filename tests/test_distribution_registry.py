"""Every distribution target, against the artifact it promises.

`distributions/` was nineteen files at 0.2.0 — eleven READMEs, four one-line
requirements files, two small JSON — describing what each distribution *would*
contain. A distribution matrix whose rows are READMEs is a label for a
distribution matrix.

The registry replaced that, and these tests are what make a row a promise rather
than a claim. A row says an artifact exists, an install command works and a
manifest is well-formed; each of those is checked here. The one thing that
cannot be checked from inside this repository is whether a platform has listed
us, which is why `status` has exactly two values and "listed" is not one.

The drift this guards against is not hypothetical. `pyproject.toml` declared
harness extras for four adapters while the package shipped six, and
`maxey0-ss.distribution` returned a written-down list naming the same four.
Three places, two answers, no failure.
"""

from __future__ import annotations

import json
import pathlib
import sys
import tomllib
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _env import ROOT  # noqa: E402

from maxey0_ss import __version__  # noqa: E402
from maxey0_ss.adapters.harnesses import ADAPTERS  # noqa: E402
from maxey0_ss.distribution import (  # noqa: E402
    BY_ID,
    HARNESSES,
    TARGETS,
    public_manifest,
)
from maxey0_ss.distribution import registry as reg  # noqa: E402


class TestEveryRowIsAPromise(unittest.TestCase):

    def test_every_declared_artifact_exists(self):
        for target in TARGETS:
            for rel in target.artifacts:
                with self.subTest(target=target.id, artifact=rel):
                    self.assertTrue(
                        (ROOT / rel).exists(),
                        f"{target.id} declares {rel}, which is not on disk",
                    )

    def test_every_generated_file_exists_and_is_current(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        from build_distributions import wanted

        for path, text in wanted().items():
            rel = path.relative_to(ROOT).as_posix()
            with self.subTest(file=rel):
                self.assertTrue(path.exists(), f"{rel} has not been generated")
                self.assertEqual(
                    path.read_text(encoding="utf-8"), text,
                    f"{rel} has drifted; run scripts/build_distributions.py",
                )

    def test_status_has_exactly_two_values(self):
        """There is no third status. A target with no artifact has no row."""
        self.assertEqual(
            {t.status for t in TARGETS}, {"shipped", "external"},
        )

    def test_nothing_is_marked_planned_or_coming_soon(self):
        blob = json.dumps(public_manifest()).lower()
        for word in ("planned", "coming soon", "tbd", "todo", "not implemented"):
            with self.subTest(word=word):
                self.assertNotIn(word, blob)

    def test_target_ids_are_unique_and_url_safe(self):
        ids = [t.id for t in TARGETS]
        self.assertEqual(len(ids), len(set(ids)))
        for tid in ids:
            with self.subTest(id=tid):
                self.assertRegex(tid, r"^[a-z0-9][a-z0-9\-]*$")


class TestOneIdentityAcrossEveryManifest(unittest.TestCase):
    """A plugin id that disagrees with the package name fails at install."""

    def test_the_mcp_namespace_is_the_one_in_the_surface(self):
        from maxey0_ss.mcp_surface import build_surface

        for tool in build_surface().tools:
            with self.subTest(tool=tool.name):
                self.assertTrue(tool.name.startswith(reg.MCP_NAMESPACE + "."))

    def test_pyproject_publishes_the_distribution_id(self):
        data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(data["project"]["name"], reg.DISTRIBUTION_ID)
        self.assertEqual(data["project"]["version"], __version__)

    def test_every_generated_json_manifest_carries_this_version(self):
        for path in (ROOT / "distributions").rglob("*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            if "version" not in data:
                continue
            with self.subTest(file=path.name):
                self.assertEqual(data["version"], __version__)

    #: Hosts this project shipped in a manifest and has stopped serving.
    #: `maxey0-ss-mcp.maxey0.workers.dev` answered until the Custom Domain was
    #: attached to the Worker; Cloudflare disables the workers.dev route once a
    #: custom domain is attached, so it now returns HTTP 404 on every path.
    RETIRED_HOSTS = ("maxey0-ss-mcp.maxey0.workers.dev",)

    def test_no_manifest_names_a_host_that_does_not_answer(self):
        """A manifest naming a host nobody serves fails at install, once, with a
        404 or a DNS error and no diagnostic.

        This was `assertNotIn("mcp.maxey0.com", text)` — one dead hostname
        written down as a string literal. It guarded against exactly one mistake
        and it expired the day the Custom Domain went live: the forbidden literal
        became the only host that answers, and the workers.dev name it was
        protecting started returning 404. The guarantee worth keeping is that no
        generated file names a host this project has retired.
        """
        for path in (ROOT / "distributions").rglob("*"):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            rel = path.relative_to(ROOT).as_posix()
            for dead in self.RETIRED_HOSTS:
                with self.subTest(file=rel, retired=dead):
                    self.assertNotIn(
                        dead, text,
                        f"{rel} still names {dead}, which no longer answers; "
                        f"run scripts/build_distributions.py",
                    )

    def test_every_remote_manifest_points_at_the_observed_endpoint(self):
        for name in ("claude-remote-connector/connector.json",
                     "chatgpt-app/openai-connector.json"):
            data = json.loads((ROOT / "distributions" / name).read_text(encoding="utf-8"))
            blob = json.dumps(data)
            with self.subTest(file=name):
                self.assertIn(reg.REMOTE_MCP_HOST, blob)


class TestHarnessesAgreeEverywhere(unittest.TestCase):
    """Three places declared the harness list and two of them said four."""

    def test_the_registry_and_the_adapter_package_agree(self):
        self.assertEqual(
            sorted(h.id for h in HARNESSES), sorted(ADAPTERS),
        )

    def test_every_harness_adapter_module_exists_and_imports(self):
        import importlib

        for harness in HARNESSES:
            module = harness.extra["module"]
            with self.subTest(harness=harness.id):
                importlib.import_module(
                    f"maxey0_ss.adapters.harnesses.{module}")

    def test_pyproject_has_an_extra_for_each_harness(self):
        data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        extras = data["project"]["optional-dependencies"]
        for harness in HARNESSES:
            with self.subTest(harness=harness.id):
                self.assertIn(
                    harness.id, extras,
                    f"pip install {reg.DISTRIBUTION_ID}[{harness.id}] is "
                    f"advertised by the registry and does not exist",
                )

    def test_the_all_harnesses_extra_covers_every_one(self):
        data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        combined = set(data["project"]["optional-dependencies"]["all-harnesses"])
        for harness in HARNESSES:
            with self.subTest(harness=harness.id):
                self.assertIn(harness.optional_dependency, combined)

    def test_no_harness_dependency_is_a_hard_requirement(self):
        """Vendoring a harness would make every install carry six SDKs."""
        data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        required = " ".join(data["project"]["dependencies"])
        for harness in HARNESSES:
            with self.subTest(harness=harness.id):
                self.assertNotIn(harness.optional_dependency, required)

    def test_each_adapter_binds_an_agent_to_a_window(self):
        """The binding is the whole point; an adapter that cannot is a label."""
        for name, adapter in ADAPTERS.items():
            with self.subTest(harness=name):
                instance = adapter()
                self.assertTrue(hasattr(instance, "bind_agent"))
                self.assertTrue(hasattr(instance, "build_a2a_request"))
                self.assertEqual(instance.capabilities.name, name)


class TestGeneratedManifestsAreWellFormed(unittest.TestCase):

    def test_every_json_file_parses(self):
        for path in (ROOT / "distributions").rglob("*.json"):
            with self.subTest(file=path.name):
                json.loads(path.read_text(encoding="utf-8"))

    def test_the_a2a_agent_card_has_what_the_spec_requires(self):
        card = json.loads(
            (ROOT / "distributions" / "a2a" / "agent-card.json").read_text(encoding="utf-8"))
        for key in ("protocolVersion", "name", "description", "url",
                    "version", "capabilities", "defaultInputModes",
                    "defaultOutputModes", "skills"):
            with self.subTest(key=key):
                self.assertIn(key, card)
        self.assertTrue(card["skills"])
        for skill in card["skills"]:
            for key in ("id", "name", "description", "tags"):
                self.assertIn(key, skill)

    def test_the_chatgpt_app_manifest_declares_its_mcp_server(self):
        app = json.loads(
            (ROOT / "distributions" / "chatgpt-app" / "app.json").read_text(encoding="utf-8"))
        self.assertEqual(app["mcp"]["protocol_version"], reg.MCP_PROTOCOL)
        self.assertGreater(app["mcp"]["tools"], 0)
        self.assertEqual(app["schema_version"], "v1")

    def test_the_openai_connector_requires_approval(self):
        """This surface opens windows and sends egress; silence defeats it."""
        conn = json.loads(
            (ROOT / "distributions" / "chatgpt-app" / "openai-connector.json")
            .read_text(encoding="utf-8"))
        self.assertEqual(conn["require_approval"], "always")

    def test_the_codex_fragment_is_valid_toml_and_names_the_server(self):
        text = (ROOT / "distributions" / "codex" / "config.toml").read_text(encoding="utf-8")
        data = tomllib.loads(text)
        key = reg.MCP_NAMESPACE.replace("-", "_")
        self.assertIn(key, data["mcp_servers"])
        self.assertEqual(data["mcp_servers"][key]["command"], "python")

    def test_every_mcp_json_fragment_is_loadable_by_a_host(self):
        for name in ("mcp-stdio/mcp.json", "mcp-http/mcp.json"):
            data = json.loads((ROOT / "distributions" / name).read_text(encoding="utf-8"))
            with self.subTest(file=name):
                self.assertIn(reg.MCP_NAMESPACE, data["mcpServers"])

    def test_every_generated_file_says_it_is_generated(self):
        for path in (ROOT / "distributions").rglob("*"):
            if not path.is_file() or path.suffix == ".json":
                continue
            with self.subTest(file=path.relative_to(ROOT).as_posix()):
                text = path.read_text(encoding="utf-8")
                self.assertIn("build_distributions.py", text)


class TestPackagingRefusesDrift(unittest.TestCase):

    def test_build_package_runs_the_distribution_check(self):
        src = (ROOT / "scripts" / "build_package.py").read_text(encoding="utf-8")
        self.assertIn("check_distributions", src)
        self.assertIn("build_distributions.py", src)

    def test_the_check_detects_a_hand_edited_manifest(self):
        """Proved by editing one, not by reading the code that would catch it."""
        import subprocess

        target = ROOT / "distributions" / "codex" / "config.toml"
        original = target.read_text(encoding="utf-8")
        try:
            target.write_text(original + "\n# hand edit\n", encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, "scripts/build_distributions.py", "--check"],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertEqual(proc.returncode, 1)
            self.assertIn("drifted", proc.stdout)
        finally:
            target.write_text(original, encoding="utf-8")

    def test_the_check_detects_an_orphan_file(self):
        """A file nobody generates is a file nobody maintains."""
        import subprocess

        orphan = ROOT / "distributions" / "leftover.md"
        try:
            orphan.write_text("stale\n", encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, "scripts/build_distributions.py", "--check"],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertEqual(proc.returncode, 1)
            self.assertIn("orphan", proc.stdout)
        finally:
            orphan.unlink(missing_ok=True)


class TestTheSurfaceReportsTheRegistry(unittest.TestCase):

    def test_the_distribution_tool_derives_its_answer(self):
        from maxey0_ss.mcp_surface import build_surface

        tool = next(t for t in build_surface().tools
                    if t.name == "maxey0-ss.distribution")
        reported = tool.handler({})
        self.assertEqual(len(reported["targets"]), len(TARGETS))
        self.assertEqual(sorted(reported["harnesses"]), sorted(ADAPTERS))
        self.assertEqual(reported["version"], __version__)

    def test_it_names_no_target_that_is_not_in_the_registry(self):
        from maxey0_ss.mcp_surface import build_surface

        tool = next(t for t in build_surface().tools
                    if t.name == "maxey0-ss.distribution")
        for row in tool.handler({})["targets"]:
            with self.subTest(target=row["id"]):
                self.assertIn(row["id"], BY_ID)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class TestTheMarketplaceAndTheRegistryAgree(unittest.TestCase):
    """Five installable plugins were offered; one was declared.

    `.claude-plugin/marketplace.json` ships `maxey0`, `maxey0-context`,
    `maxey0-loops`, `maxey0-observe` and `maxey0-lab`. The registry — whose
    docstring says it is "the only place a target is described" — declared the
    first. So a reader of DISTRIBUTION_MATRIX.md saw one Claude Code plugin and
    `/plugin marketplace add` offered five.

    Both directions, because both failures are real: a plugin the marketplace
    ships and the matrix omits is undiscoverable, and a target the matrix
    advertises and the marketplace does not ship fails at install.
    """

    @classmethod
    def setUpClass(cls):
        cls.marketplace = {
            p["name"] for p in json.loads(
                (ROOT / ".claude-plugin" / "marketplace.json")
                .read_text(encoding="utf-8"))["plugins"]
        }
        cls.declared = {
            t.id.replace("claude-code-plugin", "maxey0")
               .replace("claude-code-", "maxey0-")
            for t in TARGETS if t.platform == "claude-code"
        }

    def test_every_marketplace_plugin_has_a_registry_target(self):
        missing = self.marketplace - self.declared
        self.assertEqual(
            missing, set(),
            f"the marketplace ships {sorted(missing)} and the distribution "
            f"matrix does not list them",
        )

    def test_every_registry_plugin_target_is_in_the_marketplace(self):
        extra = self.declared - self.marketplace
        self.assertEqual(
            extra, set(),
            f"the matrix advertises {sorted(extra)}, which `/plugin install` "
            f"cannot resolve",
        )

    def test_every_marketplace_plugin_directory_exists_and_is_generated(self):
        for name in sorted(self.marketplace):
            manifest = ROOT / "plugins" / name / ".claude-plugin" / "plugin.json"
            with self.subTest(plugin=name):
                self.assertTrue(manifest.exists(), f"{name} has no plugin.json")
                self.assertEqual(
                    json.loads(manifest.read_text(encoding="utf-8"))["version"],
                    __version__,
                )

    def test_the_lab_plugin_says_it_is_not_part_of_the_product(self):
        """It ships, so it is declared; it is research, so it says so."""
        lab = BY_ID["claude-code-lab"]
        self.assertIn("not part of the product", lab.notes)
