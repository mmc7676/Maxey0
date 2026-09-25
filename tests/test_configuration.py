"""`.env.example` and `credentials.example.json` against the code that reads them.

`settings.py` opens with the finding these tests exist to prevent recurring:
".env.example declared 21 placeholders. Thirteen of them were read by nothing:
setting MAXEY0_NEO4J_URI or MAXEY0_SEMANTIC_GATE_API_KEY had no effect at all,
and no part of the system said so. A socket that silently ignores what you plug
into it is worse than no socket, because it looks configured."

`ProviderSocket` fixed the *reporting* half of that — `configured` and
`implemented` are now separate and a populated-but-inert socket warns. It did
not fix the *documentation* half, and it could not, because nothing compared
the file to the code. At 0.2.0 six variables the code read were missing from
`.env.example`, including every `MAXEY0_CACHE_TTL_MS_*` and all three the edge
Worker consumes.

So this checks both directions and neither is optional:

- a variable the code reads and the file does not declare is undiscoverable;
- a variable the file declares and nothing reads is the original defect, a
  placeholder that looks like configuration.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _env import ROOT  # noqa: E402

ENV_EXAMPLE = ROOT / ".env.example"
CREDENTIALS_EXAMPLE = ROOT / "config" / "credentials.example.json"

#: Where configuration is read from. `server/` is the plane-server tree, which
#: has its own runtime variables.
PYTHON_SOURCES = ("maxey0_ss", "scripts")
EDGE_SOURCE = ROOT / "workers" / "mcp-edge" / "src" / "index.ts"

#: Prefixes built at runtime rather than named literally. `CacheConfig.from_env`
#: composes `MAXEY0_CACHE_TTL_MS_{plane.name}` for each plane, so the literal in
#: the source is a fragment; the file declares the five real names.
_DYNAMIC_PREFIXES = ("MAXEY0_CACHE_TTL_MS_",)


def _declared() -> set[str]:
    return {
        m.group(1)
        for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
        if (m := re.match(r"^([A-Z][A-Z0-9_]*)=", line))
    }


#: Every literal environment-variable name the code reads.
#:
#: Two patterns, because the tree has two conventions. `MAXEY0_*` names are
#: matched anywhere, since several are composed or documented in comments.
#: Everything else has to be an actual `os.environ.get("NAME")` or
#: `os.getenv("NAME")` — vendor variables like `ANTHROPIC_API_KEY` are ordinary
#: identifiers that would otherwise match prose, and a completeness check that
#: fires on a docstring is a completeness check people stop reading.
_ENV_READ = re.compile(
    r"""os\.(?:environ\.get|getenv)\(\s*["']([A-Z][A-Z0-9_]*)["']"""
)


def _declared_by_providers() -> set[str]:
    """Credential variables the provider layer declares it reads.

    Derived from `ProviderCapabilities.credential_env` rather than pattern
    matched, because the Hugging Face provider reads its three accepted names
    out of a tuple in a loop and no regex over the source would find them. A
    provider that declares what it reads is the authority on what it reads.
    """
    from maxey0_ss.providers import PROVIDERS

    names: set[str] = set()
    for constructor in PROVIDERS.values():
        names |= set(constructor.capabilities.credential_env)
    return names


def _read_by_python() -> set[str]:
    names: set[str] = _declared_by_providers()
    for package in PYTHON_SOURCES:
        for path in (ROOT / package).rglob("*.py"):
            if "__pycache__" in path.parts or "tests" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            names |= set(re.findall(r"MAXEY0_[A-Z0-9_]+", text))
            names |= set(_ENV_READ.findall(text))
    return names


def _read_by_edge() -> set[str]:
    return set(re.findall(r"env\.([A-Z][A-Z0-9_]*)", EDGE_SOURCE.read_text(encoding="utf-8")))


class TestEnvExampleIsComplete(unittest.TestCase):

    def test_every_variable_python_reads_is_documented(self):
        missing = set()
        declared = _declared()
        for name in _read_by_python():
            if name in declared:
                continue
            if any(name.startswith(p) or p.startswith(name) for p in _DYNAMIC_PREFIXES):
                continue
            missing.add(name)
        self.assertEqual(
            missing, set(),
            f"read by the code, absent from .env.example: {sorted(missing)}",
        )

    def test_every_variable_the_edge_worker_reads_is_documented(self):
        """Three were missing entirely; MAXEY0_ORIGIN gates the whole deployment."""
        missing = _read_by_edge() - _declared()
        self.assertEqual(missing, set(), f"edge reads, undocumented: {sorted(missing)}")

    def test_every_dynamic_cache_ttl_plane_is_declared(self):
        from maxey0_ss.cache.identity import SemanticPlane

        declared = _declared()
        for plane in SemanticPlane:
            with self.subTest(plane=plane.name):
                self.assertIn(f"MAXEY0_CACHE_TTL_MS_{plane.name}", declared)

    def test_nothing_is_declared_that_nothing_reads(self):
        """The original defect: thirteen placeholders read by nothing."""
        known = _read_by_python() | _read_by_edge()
        orphans = {
            name for name in _declared()
            if name not in known
            and not any(name.startswith(p) for p in _DYNAMIC_PREFIXES)
        }
        self.assertEqual(
            orphans, set(),
            f"declared in .env.example, read by nothing: {sorted(orphans)}",
        )

    def test_the_file_ships_with_no_value_filled_in(self):
        """It is documentation, not a deployment. Every line is `NAME=` or a default."""
        safe_defaults = {
            "MAXEY0_HOST": "127.0.0.1", "MAXEY0_PORT": "8765",
            "MAXEY0_ENV": "development", "MAXEY0_AUTH_MODE": "disabled",
            "MAXEY0_SEMANTIC_GATE_PROVIDER": "disabled",
            "MAXEY0_CONTAINMENT_PROVIDER": "structural",
            # Credential placeholders: refused if left in place (see the
            # placeholder tests), never a working value.
            "ANTHROPIC_API_KEY": "<API_KEY>", "OPENAI_API_KEY": "<API_KEY>",
            "HF_TOKEN": "<API_KEY>",
            "MAXEY0_MCP_DEFAULT_BEARER_TOKEN": "<BEARER_TOKEN>",
            "MAXEY0_A2A_SHARED_SECRET": "<BEARER_TOKEN>",
        }
        for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^([A-Z][A-Z0-9_]*)=(.*)$", line)
            if not m:
                continue
            name, value = m.group(1), m.group(2).strip()
            with self.subTest(name=name):
                self.assertEqual(value, safe_defaults.get(name, ""))

    def test_each_marker_section_is_present(self):
        text = ENV_EXAMPLE.read_text(encoding="utf-8")
        for marker in ("[WIRED]", "[SOCKET]", "[EDGE]"):
            self.assertIn(marker, text)


class TestCredentialsExample(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(CREDENTIALS_EXAMPLE.read_text(encoding="utf-8"))

    def test_every_section_names_its_reader(self):
        """`mcp` and `oauth` had none at all; the file documented a fiction."""
        for name, section in self.data.items():
            if name.startswith("_"):
                continue
            with self.subTest(section=name):
                self.assertIn("_read_by", section,
                              f"{name!r} must name the code that reads it")

    def test_the_named_readers_exist(self):
        """A docstring claim, checked rather than trusted."""
        import importlib

        for name, section in self.data.items():
            if name.startswith("_"):
                continue
            for claim in re.findall(r"maxey0_ss[\w.]+", section["_read_by"]):
                with self.subTest(section=name, reader=claim):
                    parts = claim.split(".")
                    obj = None
                    for split in range(len(parts), 1, -1):
                        try:
                            obj = importlib.import_module(".".join(parts[:split]))
                        except ModuleNotFoundError:
                            continue
                        for attr in parts[split:]:
                            obj = getattr(obj, attr)
                        break
                    self.assertIsNotNone(obj, f"{claim} does not resolve")

    def test_no_value_is_populated(self):
        for name, section in self.data.items():
            if name.startswith("_"):
                continue
            for key, value in section.items():
                if key.startswith("_"):
                    continue
                with self.subTest(section=name, key=key):
                    self.assertIn(value, ("", {}, "disabled"),
                                  f"{name}.{key} ships with a value")

    def test_the_mcp_and_oauth_sections_now_have_a_reader(self):
        from maxey0_ss.auth.config import AuthConfig

        cfg = AuthConfig.load({
            "mcp": {"default_bearer_token": "T"},
            "oauth": {"client_id": "C", "client_secret": "S"},
        })
        self.assertEqual(cfg.default_bearer_token, "T")
        self.assertEqual(cfg.client_id, "C")
        self.assertEqual(cfg.client_secret, "S")

    def test_the_semantic_gate_warning_states_the_fail_closed_behavior(self):
        warning = self.data["semantic_gate"]["_warning"]
        self.assertIn("FAIL CLOSED", warning)


class TestNoRealSecretsInTheTree(unittest.TestCase):
    """The release claim, measured against the bytes rather than asserted."""

    def test_the_packaged_selection_contains_no_credential_shapes(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        from _packaging import collect, scan_for_secrets

        selection = collect(ROOT)
        self.assertEqual(scan_for_secrets(selection.files, ROOT), [])

    def test_the_real_credentials_file_is_not_tracked(self):
        import subprocess

        tracked = subprocess.run(
            ["git", "ls-files", "config/credentials.json"],
            cwd=ROOT, capture_output=True, text=True,
        ).stdout.strip()
        self.assertEqual(tracked, "")

    def test_no_dotenv_but_the_example_is_tracked(self):
        import subprocess

        tracked = subprocess.run(
            ["git", "ls-files", ".env*"], cwd=ROOT,
            capture_output=True, text=True,
        ).stdout.split()
        self.assertEqual(sorted(tracked), [".env.example"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
