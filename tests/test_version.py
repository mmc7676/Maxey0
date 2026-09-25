"""Every version declaration in the tree, against the one literal.

Nine files declared `"1.0.0"` independently at `a31ee45`:
`.claude-plugin/marketplace.json`, `manifest.json`, `pyproject.toml`, `maxey0_ss/mcp_surface.py`, `maxey0_ss/mcp_2026.py`,
`maxey0_ss/api/app.py`, `maxey0_ss/a2a_server.py`,
`server/maxey0_studio/__init__.py` and `workers/mcp-edge/package.json`.

`build_package.check_manifests()` compared three of them. So
`mcp_2026.build_router` could answer `server/discover` with a
`serverInfo.version` that disagreed with `mcp_surface.SERVER_VERSION`, and the
build would pass — the same "written down rather than derived" defect the suite
already refuses elsewhere (`test_counts_are_computed_not_written_down`), applied
to the number that identifies the artifact.

There is now one literal, `maxey0_ss.__version__`. These tests are what stop a
tenth declaration appearing beside it.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _env import ROOT  # noqa: E402

import maxey0_ss  # noqa: E402

VERSION = maxey0_ss.__version__


class TestOneVersionLiteral(unittest.TestCase):

    def test_the_version_is_a_release_candidate_not_a_release(self):
        """0.2.0-rc.1: explicitly not 1.0.0, and explicitly not final 0.2.0."""
        self.assertRegex(VERSION, r"^\d+\.\d+\.\d+(-[0-9A-Za-z.\-]+)?$")
        self.assertNotEqual(VERSION, "1.0.0")

    def test_pyproject_agrees(self):
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn(f'version = "{VERSION}"', text)

    def test_every_json_manifest_agrees(self):
        for rel, path in (
            (".claude-plugin/marketplace.json", ("metadata", "version")),
            ("manifest.json", ("version",)),
        ):
            with self.subTest(file=rel):
                node = json.loads((ROOT / rel).read_text(encoding="utf-8"))
                for key in path:
                    node = node[key]
                self.assertEqual(node, VERSION)

    def test_every_package_json_in_the_tree_agrees(self):
        """Discovered, not listed. A list is exactly what failed here.

        0.2.0 fixed "ten files declared 1.0.0 independently and the build
        compared three" -- and fixed it with another list, naming
        `workers/mcp-edge/package.json` and no other package.json. Three
        survived on their own numbers: the MCP App and the TypeScript SDK on
        2.0.0, the UI on 0.7.2, while the product shipped 0.3.0.

        A check written as an enumeration only ever covers what its author
        remembered. This walks the tree.
        """
        found = [
            p for p in ROOT.rglob("package.json")
            if "node_modules" not in p.parts and ".venv" not in p.parts
            and "plugins" not in p.parts and "dist" not in p.parts
        ]
        self.assertGreaterEqual(len(found), 4, "discovery found suspiciously few")
        for path in sorted(found):
            with self.subTest(file=path.relative_to(ROOT).as_posix()):
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(
                    data.get("version"), VERSION,
                    f"{path.relative_to(ROOT).as_posix()} carries its own version",
                )

    def test_no_package_lock_disagrees_with_its_manifest(self):
        """A lockfile's own `version` field is a fourth place to drift."""
        for lock in ROOT.rglob("package-lock.json"):
            if "node_modules" in lock.parts or ".venv" in lock.parts:
                continue
            data = json.loads(lock.read_text(encoding="utf-8"))
            with self.subTest(file=lock.relative_to(ROOT).as_posix()):
                self.assertEqual(data.get("version"), VERSION)

    def test_every_generated_plugin_manifest_agrees(self):
        for plugin in sorted((ROOT / "plugins").iterdir()):
            manifest = plugin / ".claude-plugin" / "plugin.json"
            if not manifest.exists():
                continue
            with self.subTest(plugin=plugin.name):
                data = json.loads(manifest.read_text(encoding="utf-8"))
                self.assertEqual(data["version"], VERSION)

    def test_the_studio_agrees(self):
        text = (ROOT / "server" / "maxey0_studio" / "__init__.py").read_text(
            encoding="utf-8")
        self.assertIn(f'__version__ = "{VERSION}"', text)

    def test_the_exported_edge_surface_agrees(self):
        surface = json.loads(
            (ROOT / "workers" / "mcp-edge" / "src" / "generated" / "surface.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(
            surface["serverVersion"], VERSION,
            "re-run scripts/export_mcp_surface.py",
        )

    def test_server_discover_reports_the_same_version_as_the_surface(self):
        """These were two independent literals and could disagree silently."""
        from maxey0_ss.mcp_surface import SERVER_VERSION

        self.assertEqual(SERVER_VERSION, VERSION)

    def test_no_python_module_restates_a_version_literal(self):
        """The guard against a tenth declaration appearing."""
        pattern = re.compile(r'version\s*=\s*"\d+\.\d+\.\d+')
        offenders = []
        for path in (ROOT / "maxey0_ss").rglob("*.py"):
            if "__pycache__" in path.parts or "tests" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                offenders.append(f"{path.relative_to(ROOT).as_posix()}:{line}")
        self.assertEqual(
            offenders, [],
            f"hardcoded version literal; import maxey0_ss.__version__: {offenders}",
        )

    def test_the_package_build_check_sees_the_same_number(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        from build_package import read_versions

        version, others = read_versions()
        self.assertEqual(version, VERSION)
        for name, claimed in others.items():
            with self.subTest(manifest=name):
                self.assertEqual(claimed, VERSION)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
