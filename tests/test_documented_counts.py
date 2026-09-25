"""Numbers written in documentation, against the code they describe.

`docs/VERIFICATION.md` opens by saying it records "what this system's
behavior actually is, measured rather than described". At `a31ee45` its
baseline block said `439 passed` when the suite was 589, and `26 tools` — which
was right then and silently became wrong the moment the surface gained a 27th.

A page that records measurements has to be measured too. Only the parts that
*can* be checked are checked here: the tool and resource counts, and the
protocol version, all of which `build_surface()` answers directly. The suite
sizes are deliberately not asserted — a test that asserts its own suite's size
has to be edited every time a test is added, which trains people to edit it
without looking, and that is how a number drifts by 150 without anyone noticing.
"""

from __future__ import annotations

import pathlib
import re
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _env import ROOT  # noqa: E402

from maxey0_ss.mcp_surface import build_surface  # noqa: E402

VERIFICATION = ROOT / "docs" / "VERIFICATION.md"


class TestDocumentedSurfaceCounts(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.text = VERIFICATION.read_text(encoding="utf-8")
        cls.surface = build_surface()

    def test_the_documented_tool_and_resource_counts_are_current(self):
        match = re.search(
            r"^Surface:\s*(\d+) tools?, (\d+) resources?$", self.text, re.M,
        )
        self.assertIsNotNone(
            match, "VERIFICATION.md has no `Surface: N tools, M resources` line",
        )
        tools, resources = int(match.group(1)), int(match.group(2))
        self.assertEqual(
            tools, len(self.surface.tools),
            "VERIFICATION.md's tool count is stale; update the Surface: line",
        )
        self.assertEqual(
            resources, len(self.surface.resources),
            "VERIFICATION.md's resource count is stale",
        )

    def test_every_tool_the_surface_declares_has_a_unique_name(self):
        names = [t.name for t in self.surface.tools]
        self.assertEqual(len(names), len(set(names)), "duplicate tool name")

    def test_the_documented_protocol_version_matches_the_surface(self):
        health = next(t for t in self.surface.tools if t.name == "maxey0-ss.health")
        protocol = health.handler({})["mcp_protocol"]
        self.assertIn(protocol, self.text)

    def test_the_exported_edge_catalog_agrees_with_the_surface(self):
        """Parity, restated here so a stale export fails next to the doc check."""
        import json

        catalog = json.loads(
            (ROOT / "workers" / "mcp-edge" / "src" / "generated" / "surface.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(
            [t["name"] for t in catalog["tools"]],
            [t.name for t in self.surface.tools],
            "re-run scripts/export_mcp_surface.py",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
