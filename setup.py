"""Carry `server/` and the MCP App inside the wheel.

Package metadata lives in pyproject.toml. This file adds one build step.

`maxey0_ss` reads two trees that sit beside it in the repository rather than
inside it: `server/`, the engineering-observation plane behind the observe and
gate tools, and `mcp_apps/`, the MCP App the server serves and hashes. The
wheel used to contain `maxey0_ss/` alone, so an installed package listed 19 of
its 29 tools and `super_space_artifact()` raised FileNotFoundError. This step
copies both into `maxey0_ss/_bundled/` in the build directory, which is where
the runtime looks when no source tree sits beside the package.

The copy is made at build time rather than committed under `maxey0_ss/`, so the
repository keeps one `server/` -- the tree scripts/build_planes.py copies into
the plugins and the Dockerfile copies into the image -- instead of a second
one that could drift from it. MANIFEST.in puts the same files in the sdist,
because `python -m build` builds the wheel from the sdist, not the checkout.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py
from setuptools.errors import FileError

HERE = Path(__file__).resolve().parent

#: Where the runtime looks for the copy, relative to the build directory.
BUNDLE = Path("maxey0_ss", "_bundled")

#: The MCP App: the built bundle, and the stub served when it is absent.
APP_FILES = (
    "mcp_apps/super_space.html",
    "mcp_apps/super_space_react/dist/mcp-app.html",
)

#: A wheel without these installs cleanly and then quietly serves a smaller
#: surface or the stub App, which is the failure this step exists to end, so
#: their absence fails the build instead.
REQUIRED = ("server/planes/observe_impl.py", *APP_FILES)

#: Kept in step with IGNORE in scripts/build_planes.py, so the bundled
#: `server/` is the same tree the plugins ship: no bytecode, no test caches, no
#: `app` (the built ui/ front end, gitignored output the Studio runs without),
#: no source maps. Tests never belong in a runtime copy.
IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", "*.pyo", ".pytest_cache", "app", "*.map", "tests",
)


class build_py_with_bundle(build_py):
    """`build_py`, plus the copy of `server/` and the App into the package."""

    def run(self) -> None:
        # An editable install runs from the source tree, which the runtime
        # prefers anyway, so a copy there would only be a second, staler tree.
        editable = getattr(self, "editable_mode", False)
        if not editable:
            missing = [rel for rel in REQUIRED if not (HERE / rel).is_file()]
            if missing:
                raise FileError(
                    "cannot build a complete maxey0 wheel; missing: "
                    + ", ".join(missing)
                    + ". Build from a full checkout or from the sdist (the App "
                    "bundle is produced by `npm run build` in "
                    "mcp_apps/super_space_react)."
                )
        super().run()
        if editable:
            return
        target = Path(self.build_lib) / BUNDLE
        # A reused build directory must not keep a file that was since
        # removed from the source tree.
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(HERE / "server", target / "server", ignore=IGNORE)
        for rel in APP_FILES:
            dest = target / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            # Byte-for-byte: the App's sha256 is its published identity.
            shutil.copyfile(HERE / rel, dest)


setup(cmdclass={"build_py": build_py_with_bundle})
