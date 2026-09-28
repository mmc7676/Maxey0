"""The suite runs against code defaults, not against this machine's deployment.

`maxey0_ss/__init__.py` loads `.env` into the process at import time — it has to,
because `AuthConfig.load()`, `is_public_deployment()` and the cache all resolve
at construction and a `.env` read later is a `.env` never read. That is correct
for a running server and wrong for the test suite: the moment an operator points
this checkout at a live deployment — `MAXEY0_PUBLIC=1`, `MAXEY0_AUTH_MODE=bearer`,
a real `MAXEY0_MCP_TOKENS`, the cache switched off — the suite inherits it and
tests that assert the trusted-local defaults fail, not because the code changed
but because the machine did. On a clean checkout there is no `.env` and nothing
leaks, so the failures appear only on a developer's own machine and vanish in CI,
which is the worst place for a failure to live.

So every variable this project's own `.env` would inject is removed for the
duration of each test. A test that needs a specific deployment posture sets it
itself with `monkeypatch.setenv`, which runs after this fixture and wins. Nothing
here reaches production; it only refuses to let a local `.env` decide what the
suite measures.
"""
from __future__ import annotations

import pytest

from maxey0_ss.settings import DEFAULT_ENV_FILE, load_env_file

#: The keys the tracked `.env` (if any) declares. Reading the file back is how
#: this stays correct as the file grows: a switch added to `.env` tomorrow is
#: neutralized here without editing this list. `load_env_file` only sets keys it
#: does not find already set, so calling it here is idempotent — the package
#: import already ran it — and it returns the full key set either way.
_DOTENV_KEYS: tuple[str, ...] = (
    tuple(load_env_file(DEFAULT_ENV_FILE)) if DEFAULT_ENV_FILE.exists() else ()
)


@pytest.fixture(autouse=True)
def _trusted_local_environment(monkeypatch):
    """Strip `.env`-injected deployment config so tests see code defaults."""
    for key in _DOTENV_KEYS:
        monkeypatch.delenv(key, raising=False)
