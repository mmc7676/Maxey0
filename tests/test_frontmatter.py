"""Command, skill and agent frontmatter must be valid YAML.

commands/crosswindow.md had an unquoted description containing ": ", which YAML
reads as a nested mapping. `claude plugin validate` rejected it and at runtime
the command loaded with its description and allowed-tools silently dropped.
"""
from __future__ import annotations

import re
import unittest

from _env import ROOT  # noqa: E402

_SCALAR = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):[ \t]+(.+)$")


def _frontmatter(text: str) -> list[str]:
    if not text.startswith("---"):
        return []
    end = text.find("\n---", 3)
    return text[3:end].strip("\n").splitlines() if end != -1 else []


class FrontmatterParses(unittest.TestCase):
    def test_no_unquoted_value_contains_a_mapping_separator(self):
        files = [*ROOT.glob("commands/*.md"), *ROOT.glob("agents/*.md"),
                 *ROOT.glob("skills/*/SKILL.md"), *ROOT.glob("plugins/*/commands/*.md"),
                 *ROOT.glob("plugins/*/agents/*.md"), *ROOT.glob("plugins/*/skills/*/SKILL.md")]
        self.assertTrue(files)
        bad = []
        for path in files:
            for line in _frontmatter(path.read_text(encoding="utf-8")):
                m = _SCALAR.match(line.rstrip())
                if not m:
                    continue
                value = m.group(2).strip()
                if value[:1] in "\"'[{>|":
                    continue
                if ": " in value or value.endswith(":"):
                    bad.append(f"{path.relative_to(ROOT)}: {line.strip()[:80]}")
        self.assertEqual(bad, [], "quote these frontmatter values:\n" + "\n".join(bad))


class AgentsShipTheSkillsTheyName(unittest.TestCase):
    def test_every_named_skill_is_in_the_plugin_that_ships_the_agent(self):
        """scw-deployer told the model to use `scw-default-deployer`, which no
        plugin shipped."""
        missing = []
        for agent in ROOT.glob("plugins/*/agents/*.md"):
            plugin = agent.parents[1]
            for skill in re.findall(r"`([a-z0-9-]+)` skill", agent.read_text(encoding="utf-8")):
                if (ROOT / "skills" / skill).is_dir() and not (plugin / "skills" / skill / "SKILL.md").is_file():
                    missing.append(f"{agent.relative_to(ROOT)} -> {skill}")
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
