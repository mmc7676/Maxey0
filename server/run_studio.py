"""Launch the Studio without needing the package on PYTHONPATH.

    python server/run_studio.py [--port 7676] [--no-open]

Equivalent to `python -m maxey0_studio` from inside `server/`; this wrapper
exists so a launch config or a shortcut can name one absolute file path.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from maxey0_studio.app import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
