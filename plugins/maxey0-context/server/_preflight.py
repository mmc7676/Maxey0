"""Fail helpfully when a dependency is missing, instead of cryptically.

An MCP server talks JSON-RPC over stdout, so it cannot print prose there — a
stray line corrupts the protocol and the host reports something unrelated to
the real problem. It *can* write to stderr, which both Claude Code and Claude
Desktop capture into their logs.

This matters most on the Claude Desktop path. A `.mcpb` bundle installs by
drag-and-drop, and the MCP SDK pulls `pydantic`, a compiled dependency that
cannot be portably bundled inside an archive. So the honest sequence is
"install the bundle, then install the requirements" — and a user who does the
first and not the second previously got:

    ImportError: No module named 'mcp'

which surfaces as a server that simply never starts. This module turns that
into a message naming the missing package, the exact command to fix it, and
the interpreter it needs to be installed for — because the usual cause is that
`pip` and the Python the host launched are not the same environment.

The Studio deliberately does not import this: it is standard-library only and
has no dependency to be missing.
"""

from __future__ import annotations

import sys
from pathlib import Path

#: Import name -> the distribution you install to get it.
_PACKAGES: dict[str, str] = {
    "mcp": "mcp",
    "pydantic": "pydantic",
}


def require(*modules: str, component: str = "This MCP server") -> None:
    """Exit with an actionable message if any of ``modules`` cannot be imported.

    Called before the real imports so the failure is reported once, in terms a
    user can act on, rather than as a traceback from somewhere deep in the
    import graph.
    """
    import importlib.util

    missing = [m for m in modules if importlib.util.find_spec(m) is None]
    if not missing:
        return

    root = Path(__file__).resolve().parent.parent
    dists = " ".join(_PACKAGES.get(m, m) for m in missing)

    # Every path printed below has to exist inside an *installed plugin*, not
    # only inside the repository. This message used to lead with
    # `pip install -r "<plugin>/requirements.txt"`, and `root` here resolves to
    # the plugin root, where no requirements.txt has ever existed: the four
    # generated plugin trees carry a `server/` copy and nothing else, so the
    # one command printed on the one start-up failure path named a file the
    # reader could not open. The package names come from `_PACKAGES`, which is
    # already the authority for what is missing, so naming them directly
    # removes a filesystem dependency instead of adding one.
    lines = [
        "",
        f"  {component} cannot start: missing {', '.join(repr(m) for m in missing)}.",
        "",
        "  Install with the SAME interpreter this server runs on:",
        "",
        f"    \"{sys.executable}\" -m pip install {dists}",
        "",
        "  The MCP SDK depends on pydantic, which is compiled and cannot be",
        "  bundled inside a portable archive, so a drag-and-drop install needs",
        "  this one step. The Studio needs nothing — it is standard library only:",
        "",
        f"    python \"{root / 'server' / 'run_studio.py'}\"",
        "",
    ]
    sys.stderr.write("\n".join(lines))
    sys.stderr.flush()
    raise SystemExit(1)
