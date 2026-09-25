"""MCP entry point: the Observatory plane (`maxey0-observe`).

The Gate, the evidence it produces, and the Studio. Reads the other two planes from disk; neither can see it.

Launched by `.claude-plugin/plugin.json` and by the standalone connector
manifest in `plugins/maxey0-observe/`. Run it directly to debug:

    python server/observe_server.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# The plane modules are a package under `server/`, and the vendored runtime
# they import is a package under `server/vendor/`. Both have to be importable
# before anything else runs, and `bootstrap.prepare()` cannot put itself on
# the path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from planes.observe_plane import main  # noqa: E402

if __name__ == "__main__":
    main()
