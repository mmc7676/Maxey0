"""MCP entry point: the Loop plane (`maxey0-loops`).

The Maxey0 library and the routing decision over it. Holds no window state, so it runs against a fixed context scheme on its own.

Launched by `.claude-plugin/plugin.json` and by the standalone connector
manifest in `plugins/maxey0-loops/`. Run it directly to debug:

    python server/loops_server.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# The plane modules are a package under `server/`, and the vendored runtime
# they import is a package under `server/vendor/`. Both have to be importable
# before anything else runs, and `bootstrap.prepare()` cannot put itself on
# the path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from planes.loops_plane import main  # noqa: E402

if __name__ == "__main__":
    main()
