"""Deployment settings and provider sockets.

`.env.example` declared 21 placeholders. Thirteen of them were read by nothing:
setting `MAXEY0_NEO4J_URI` or `MAXEY0_SEMANTIC_GATE_API_KEY` had no effect at
all, and no part of the system said so. A socket that silently ignores what you
plug into it is worse than no socket, because it looks configured.

This module makes every declared variable real in one of two honest ways:

1. It is **consumed** — host, port, A2A secret, auth settings.
2. It is a **provider socket** — recorded, reported, and explicitly marked
   ``implemented: false`` until a provider backs it. Configuring one of these
   raises a visible warning rather than doing nothing quietly.

A deployment supplies the provider. `ProviderSocket.implemented` is the single
place that flips when a real backend arrives.

Where `.env` and `config/credentials.json` are read from
--------------------------------------------------------
From a source tree -- a checkout, an editable install, or the Fly image, which
lays the tree out under /app -- both are read from the repository root, as they
always were, so a server started from any directory still finds the checkout's
configuration.

An installed package (`pip install` of the wheel, from PyPI or from the git
URL) has no repository root: the directory above `maxey0_ss/` is
site-packages, and a `.env` there would be one no user put there on purpose.
So an installed package reads both files from the **current working
directory**, resolved once when this module is imported. A host that spawns
`maxey0-ss-mcp` configures it by the directory it starts the process in, or by
setting the variables in the process environment, which always win over the
file.
"""
from __future__ import annotations

import json
import os
import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: This package's directory, and the directory that holds it.
PACKAGE_DIR = Path(__file__).resolve().parent
_PARENT = PACKAGE_DIR.parent

_DISTRIBUTION_NAME = re.compile(r'(?m)^name\s*=\s*"maxey0"\s*$')


def _is_source_tree(root: Path) -> bool:
    """Whether `root` is this project's source tree rather than site-packages.

    A checkout, an editable install and the Fly image (whose Dockerfile copies
    pyproject.toml into /app beside the package) all keep this project's
    pyproject.toml next to `maxey0_ss/`; an installed wheel does not. The
    distribution name is checked rather than the file's mere presence, so a
    stray pyproject.toml that some other package left in site-packages cannot
    make an installed copy take site-packages for a checkout.
    """
    try:
        text = (root / "pyproject.toml").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return bool(_DISTRIBUTION_NAME.search(text))


#: The source tree this package runs from, or None for an installed package.
SOURCE_ROOT: Path | None = _PARENT if _is_source_tree(_PARENT) else None


def _config_root() -> Path:
    """Where `.env` and `config/credentials.json` live. See the module docstring."""
    if SOURCE_ROOT is not None:
        return SOURCE_ROOT
    try:
        return Path.cwd()
    except OSError:
        # The working directory was removed out from under the process. The
        # package directory holds neither file, so nothing is loaded -- which
        # is the truth -- instead of the import failing on a missing cwd.
        return PACKAGE_DIR


CONFIG_ROOT = _config_root()
DEFAULT_ENV_FILE = CONFIG_ROOT / ".env"
DEFAULT_CREDENTIALS_FILE = CONFIG_ROOT / "config" / "credentials.json"


class ConfiguredButUnimplemented(UserWarning):
    """A provider was given credentials but nothing consumes them yet."""


def load_env_file(path: Path | None = None, *, override: bool = False) -> dict[str, str]:
    """Read a `.env` file into the environment.

    Nothing in the package did this, so every secret had to be exported by hand
    before launching — which a host spawning a stdio server cannot do.
    Without `path`, reads `DEFAULT_ENV_FILE`; see the module docstring for
    where that is.
    """
    path = path or DEFAULT_ENV_FILE
    loaded: dict[str, str] = {}
    if not path.exists():
        return loaded
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if not key:
            continue
        loaded[key] = value
        if override or key not in os.environ:
            os.environ[key] = value
    return loaded


def load_credentials_file(path: Path | None = None) -> dict[str, Any]:
    """Read `config/credentials.json`, the non-env alternative.

    `config/credentials.example.json` shipped as documentation for a file no
    code ever opened. This is the loader that makes it mean something. The file
    itself is gitignored; only the example is tracked.
    """
    path = path or DEFAULT_CREDENTIALS_FILE
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class ProviderSocket:
    """An external dependency a deployment may provide.

    `configured` means credentials are present. `implemented` means code exists
    to use them. The two are tracked separately on purpose: the gap between them
    is exactly what a deployer needs to know.
    """

    name: str
    settings: dict[str, str]
    implemented: bool = False
    secret_keys: frozenset[str] = field(default_factory=frozenset)

    #: Values that mean "no provider", not "a provider named this".
    #: Without this, `MAXEY0_SEMANTIC_GATE_PROVIDER=disabled` is a truthy string
    #: and the socket reports itself configured when it is explicitly switched off.
    INERT_VALUES = frozenset({"", "disabled", "none", "off", "false", "0"})

    @property
    def configured(self) -> bool:
        return any(v.strip().lower() not in self.INERT_VALUES for v in self.settings.values())

    @property
    def active(self) -> bool:
        return self.configured and self.implemented

    def public_manifest(self) -> dict[str, Any]:
        """Report shape and status. Never values."""
        return {
            "configured": self.configured,
            "implemented": self.implemented,
            "active": self.active,
            "settings": sorted(self.settings),
            "secrets_present": sorted(k for k in self.secret_keys if self.settings.get(k)),
            "values_exposed": False,
        }


@dataclass(frozen=True)
class Settings:
    """Everything the deployment was told, and what is actually wired."""

    host: str = "127.0.0.1"
    port: int = 8765
    environment: str = "development"
    a2a_shared_secret: str = ""
    trace_endpoint: str = ""
    providers: dict[str, ProviderSocket] = field(default_factory=dict)

    @classmethod
    def load(cls, *, env_file: Path | None = None, warn: bool = True) -> "Settings":
        load_env_file(env_file)
        creds = load_credentials_file()

        def cred(section: str, key: str) -> str:
            return str((creds.get(section) or {}).get(key) or "")

        providers = {
            "graph": ProviderSocket(
                "graph",
                {
                    "MAXEY0_NEO4J_URI": _env("MAXEY0_NEO4J_URI") or cred("storage", "neo4j_uri"),
                    "MAXEY0_NEO4J_USERNAME": _env("MAXEY0_NEO4J_USERNAME") or cred("storage", "neo4j_username"),
                    "MAXEY0_NEO4J_PASSWORD": _env("MAXEY0_NEO4J_PASSWORD") or cred("storage", "neo4j_password"),
                },
                implemented=False,
                secret_keys=frozenset({"MAXEY0_NEO4J_PASSWORD"}),
            ),
            "shared_cache": ProviderSocket(
                "shared_cache",
                {"MAXEY0_REDIS_URL": _env("MAXEY0_REDIS_URL") or cred("storage", "redis_url")},
                implemented=False,
                secret_keys=frozenset({"MAXEY0_REDIS_URL"}),
            ),
            "vector_store": ProviderSocket(
                "vector_store",
                {"MAXEY0_VECTOR_STORE_URL": _env("MAXEY0_VECTOR_STORE_URL") or cred("storage", "vector_store_url")},
                implemented=False,
                secret_keys=frozenset({"MAXEY0_VECTOR_STORE_URL"}),
            ),
            "storage": ProviderSocket(
                "storage",
                {"MAXEY0_STORAGE_URL": _env("MAXEY0_STORAGE_URL") or cred("storage", "database_url")},
                implemented=False,
                secret_keys=frozenset({"MAXEY0_STORAGE_URL"}),
            ),
            "semantic_gate": ProviderSocket(
                "semantic_gate",
                {
                    # The "disabled" default is truthy, so putting it first made
                    # the credentials fallback unreachable: a provider named in
                    # config/credentials.json was never read.
                    "MAXEY0_SEMANTIC_GATE_PROVIDER": _env("MAXEY0_SEMANTIC_GATE_PROVIDER")
                    or cred("semantic_gate", "provider")
                    or "disabled",
                    "MAXEY0_SEMANTIC_GATE_ENDPOINT": _env("MAXEY0_SEMANTIC_GATE_ENDPOINT") or cred("semantic_gate", "endpoint"),
                    "MAXEY0_SEMANTIC_GATE_API_KEY": _env("MAXEY0_SEMANTIC_GATE_API_KEY") or cred("semantic_gate", "api_key"),
                },
                implemented=False,
                secret_keys=frozenset({"MAXEY0_SEMANTIC_GATE_API_KEY"}),
            ),
        }

        settings = cls(
            host=_env("MAXEY0_HOST", "127.0.0.1"),
            port=int(_env("MAXEY0_PORT", "8765") or 8765),
            environment=_env("MAXEY0_ENV", "development"),
            a2a_shared_secret=_env("MAXEY0_A2A_SHARED_SECRET") or cred("a2a", "shared_secret"),
            trace_endpoint=_env("MAXEY0_TRACE_ENDPOINT"),
            providers=providers,
        )
        if warn:
            settings.warn_about_inert_configuration()
        return settings

    def warn_about_inert_configuration(self) -> None:
        """Say so when credentials were supplied that nothing will use."""
        for socket in self.providers.values():
            if socket.configured and not socket.implemented:
                warnings.warn(
                    f"{socket.name}: credentials are configured but no provider is "
                    f"implemented in this build, so they will not be used. This is the "
                    f"provider socket — supply a provider, or unset "
                    f"{sorted(k for k, v in socket.settings.items() if v)}.",
                    ConfiguredButUnimplemented,
                    stacklevel=3,
                )
        if self.trace_endpoint:
            warnings.warn(
                "MAXEY0_TRACE_ENDPOINT is set but no exporter is implemented in this build.",
                ConfiguredButUnimplemented,
                stacklevel=3,
            )

    @property
    def a2a_secured(self) -> bool:
        return bool(self.a2a_shared_secret)

    def public_manifest(self) -> dict[str, Any]:
        """Deployment shape without a single secret value."""
        return {
            "environment": self.environment,
            "bind": {"host": self.host, "port": self.port},
            "a2a": {"secured": self.a2a_secured, "values_exposed": False},
            "trace_endpoint_configured": bool(self.trace_endpoint),
            "providers": {name: s.public_manifest() for name, s in self.providers.items()},
            "inert": sorted(
                name for name, s in self.providers.items() if s.configured and not s.implemented
            ),
        }


_CACHED: Settings | None = None


def settings(refresh: bool = False) -> Settings:
    global _CACHED
    if _CACHED is None or refresh:
        _CACHED = Settings.load()
    return _CACHED
