"""MCP entry point: the Context plane (`maxey0-context`).

Structured Context Windows: partition the window, bind each role to a region, and let the runtime decide what it can read.

Launched by `.claude-plugin/plugin.json` and by the standalone connector
manifest in `plugins/maxey0-context/`. Run it directly to debug:

    python server/context_server.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# The plane modules are a package under `server/`, and the vendored runtime
# they import is a package under `server/vendor/`. Both have to be importable
# before anything else runs, and `bootstrap.prepare()` cannot put itself on
# the path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from planes.context_plane import main  # noqa: E402

if __name__ == "__main__":
    main()
