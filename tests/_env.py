"""Shared test environment. Every test module imports this BEFORE maxey0_studio.

`state.py` resolves its event-log path once, at import time, from
`SCW_EVENT_LOG`. The first test module to import `maxey0_studio` therefore
freezes that path for the whole process. When each module set its own tempfile,
whichever one sorted first silently won and the other module's isolation
assertions failed against a path that was never going to be used.

So the decision is made here, once, and every module reads it from here.

EVENT LOG SAFETY (load-bearing): the assignments below are unconditional, not
`setdefault`. A developer with `SCW_EVENT_LOG` already exported — pointing at
`~/.scw/events.jsonl`, the append-only log this project treats as evidence —
must not have a test run append to it. `TestEventLogIsolation` in
`test_studio.py` asserts this actually took effect rather than trusting it.
"""

from __future__ import annotations

import atexit
import os
import pathlib
import shutil
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
VENDOR = ROOT / "server" / "vendor"

# Import path: server/ and server/vendor/, no install step.
for _extra in (ROOT / "server", VENDOR, ROOT / "tests"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

# One temp directory per process, shared by every test module. The guard env
# var is what makes a second import reuse the first import's directory.
_GUARD = "MAXEY0_TEST_TMPDIR"
if not os.environ.get(_GUARD):
    os.environ[_GUARD] = tempfile.mkdtemp(prefix="maxey0-tests-")
    atexit.register(shutil.rmtree, os.environ[_GUARD], True)

TMPDIR = pathlib.Path(os.environ[_GUARD])
EVENT_LOG = TMPDIR / "test-events.jsonl"

# Unconditional on purpose — see the module docstring.
os.environ["MAXEY0_ROOT"] = str(VENDOR / "maxey0")
os.environ["MAXEY0_LOOPS"] = str(VENDOR / "data" / "loops.json")
os.environ["SCW_RUNTIME_SRC"] = str(VENDOR)
os.environ["SCW_EVENT_LOG"] = str(EVENT_LOG)
