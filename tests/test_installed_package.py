"""An installed package serves the whole surface, not just what sits inside maxey0_ss/.

The wheel used to carry `maxey0_ss/` alone. `observability/bridge.py` found the
engineering-observation plane in `server/` beside the package, and
`mcp_surface.py` found the MCP App in `mcp_apps/` beside it; site-packages has
neither. So an installed package listed 19 of its 29 tools, and
`super_space_artifact()` -- which the public `health` tool calls -- raised
FileNotFoundError. Every other test runs from the checkout, where both trees
sit exactly where the code looks, so none of them could see it.

The tests that need `build` do what a release does: build the sdist from the
checkout and the wheel from the sdist (`python -m build`), install the wheel
into a fresh virtual environment outside the repository, and drive it from a
directory outside the repository with the checkout's configuration stripped
from the environment. Dependencies are pinned by `deploy/constraints.txt`, the
set the suite passes with, so a new upstream release cannot fail this test for
a reason that has nothing to do with packaging. The sdist step refreshes the
gitignored `maxey0.egg-info/` in the checkout, as any sdist build
does; nothing tracked is written.

The rest pin the resolution order and the degraded paths without building.
"""
from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pytest

from maxey0_ss import mcp_surface, settings
from maxey0_ss.observability import bridge

ROOT = Path(__file__).resolve().parents[1]
#: The App the edge serves. The origin's copy is asserted byte-identical to it
#: elsewhere, so an installed package must serve these bytes too.
EDGE_APP = ROOT / "workers" / "mcp-edge" / "src" / "generated" / "super-space.html"
CONSTRAINTS = ROOT / "deploy" / "constraints.txt"
BUNDLE = "maxey0_ss/_bundled/"
APP_FILES = ("mcp_apps/super_space.html", "mcp_apps/super_space_react/dist/mcp-app.html")
#: Every tool the bridge contributes. The installed surface is compared with
#: the checkout's, and these being in the checkout's is what stops that
#: comparison from passing with both of them short.
BRIDGE_TOOLS = bridge.HOST_STATE_READS | bridge.HOST_STATE_WRITES | bridge.HOST_INDEPENDENT
CONSOLE_SCRIPTS = ("maxey0-ss", "maxey0-ss-api", "maxey0-ss-public", "maxey0-ss-mcp", "maxey0-verify")

needs_build = pytest.mark.skipif(
    importlib.util.find_spec("build") is None,
    reason="building the wheel needs the `build` package: pip install build",
)

#: Variables that would let the checkout stand in for the installed package.
_PATH_VARIABLES = frozenset({"PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "VIRTUAL_ENV"})


def _environment(home: Path | None = None) -> dict[str, str]:
    """This process's environment, minus anything that could mask the install.

    MAXEY0_* and SCW_* are this machine's deployment configuration; conftest
    strips what `.env` injected per test, and the module fixture below runs
    before that. The path variables would put the checkout on the installed
    interpreter's path, which would prove nothing. With `home`, every state
    path the plane falls back to (`~/.scw`) lands in the throwaway directory
    instead of this machine's.
    """
    env = {
        key: value for key, value in os.environ.items()
        if not key.upper().startswith(("MAXEY0_", "SCW_"))
        and key.upper() not in _PATH_VARIABLES
    }
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if home is not None:
        env.update(HOME=str(home), USERPROFILE=str(home), SCW_HOME=str(home / ".scw"))
    return env


def _run(args: list[object], *, cwd: Path, env: dict[str, str], timeout: int = 900) -> str:
    proc = subprocess.run(
        [str(arg) for arg in args], cwd=cwd, env=env, capture_output=True,
        text=True, encoding="utf-8", errors="replace", timeout=timeout,
    )
    assert proc.returncode == 0, (
        f"{' '.join(str(a) for a in args[:4])} ... exited {proc.returncode}\n"
        f"--- stdout ---\n{proc.stdout[-4000:]}\n--- stderr ---\n{proc.stderr[-4000:]}"
    )
    return proc.stdout


def _checkout_tool_names() -> list[str]:
    return sorted(t.name for t in mcp_surface.build_surface().tools)


@dataclass(frozen=True)
class Installation:
    sdist: Path
    wheel: Path
    venv: Path
    run_dir: Path
    home: Path

    @property
    def python(self) -> Path:
        return self.venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

    def script(self, name: str) -> Path:
        if os.name == "nt":
            return self.venv / "Scripts" / f"{name}.exe"
        return self.venv / "bin" / name

    def env(self) -> dict[str, str]:
        return _environment(self.home)

    def probe(self, code: str) -> dict:
        """Run `code` in the installed interpreter, outside the repository.

        The code prints one JSON object as its last line of output.
        """
        out = _run([self.python, "-c", code], cwd=self.run_dir, env=self.env(), timeout=300)
        return json.loads(out.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def installed(tmp_path_factory):
    work = tmp_path_factory.mktemp("installed-package")
    env = _environment()
    dist = work / "dist"
    # The release path: the sdist from the checkout, then the wheel from the
    # sdist, so a file MANIFEST.in forgets is missing here as it would be there.
    _run([sys.executable, "-m", "build", "--outdir", dist, ROOT], cwd=work, env=env)
    [sdist] = dist.glob("*.tar.gz")
    [wheel] = dist.glob("*.whl")

    venv = work / "venv"
    _run([sys.executable, "-m", "venv", venv], cwd=work, env=env)
    installation = Installation(
        sdist=sdist, wheel=wheel, venv=venv,
        run_dir=work / "elsewhere", home=work / "home",
    )
    _run([
        installation.python, "-m", "pip", "install", "--disable-pip-version-check",
        "--no-compile", "-c", CONSTRAINTS, wheel,
    ], cwd=work, env=env)

    installation.run_dir.mkdir()
    installation.home.mkdir()
    # An installed package reads .env from the working directory, so give it
    # one that proves which file was read.
    (installation.run_dir / ".env").write_text(
        "MAXEY0_ENV=from-the-working-directory\n", encoding="utf-8",
    )
    yield installation
    # A venv is tens of megabytes, and pytest keeps its last three base
    # directories; do not leave one behind per run.
    shutil.rmtree(venv, ignore_errors=True)


# --- built and installed ------------------------------------------------------


@needs_build
def test_the_sdist_carries_what_the_wheel_is_built_from(installed):
    with tarfile.open(installed.sdist) as sdist:
        names = {
            member.name.split("/", 1)[1]
            for member in sdist.getmembers() if member.isfile() and "/" in member.name
        }
    for rel in ("setup.py", "MANIFEST.in", "server/planes/observe_impl.py",
                "server/vendor/data/loops.json", *APP_FILES):
        assert rel in names, f"{rel} is missing from the sdist"
    secrets = [
        n for n in names
        if (n.rsplit("/", 1)[-1].startswith(".env") and not n.endswith(".env.example"))
        or n.endswith("credentials.json")
    ]
    assert not secrets, f"the sdist carries configuration: {secrets}"


@needs_build
def test_the_wheel_carries_every_tracked_server_file_and_the_app(installed):
    with zipfile.ZipFile(installed.wheel) as whl:
        bundled = {n[len(BUNDLE):] for n in whl.namelist() if n.startswith(BUNDLE)}
        served = whl.read(BUNDLE + "mcp_apps/super_space_react/dist/mcp-app.html")

    stray = sorted(
        n for n in bundled
        if "__pycache__" in n or "/tests/" in n or "/static/app/" in n
        or n.endswith((".pyc", ".pyo", ".map"))
    )
    assert not stray, f"build output or tests in the bundle: {stray}"
    for rel in APP_FILES:
        assert rel in bundled, f"{rel} is missing from the wheel"
    assert served == EDGE_APP.read_bytes(), "the bundled App is not the App the edge serves"

    proc = subprocess.run(
        ["git", "ls-files", "-z", "server"], cwd=ROOT, capture_output=True,
    )
    if proc.returncode != 0:
        pytest.skip("git cannot list the tracked server/ files here")
    tracked = {n for n in proc.stdout.decode("utf-8").split("\0") if n}
    assert tracked, "git listed no server/ files"
    missing = sorted(tracked - bundled)
    assert not missing, f"tracked server/ files missing from the wheel: {missing}"


@needs_build
def test_the_installed_package_serves_the_whole_surface(installed):
    checkout = _checkout_tool_names()
    assert BRIDGE_TOOLS <= set(checkout), "the checkout itself is missing the bridge tools"

    result = installed.probe(
        "import hashlib, json, sys\n"
        "import maxey0_ss\n"
        "from maxey0_ss import mcp_surface, settings\n"
        "from maxey0_ss.observability import bridge\n"
        "surface = mcp_surface.build_surface()\n"
        "art = mcp_surface.super_space_artifact()\n"
        "served = mcp_surface.super_space_html().encode('utf-8')\n"
        "print(json.dumps({\n"
        "    'package': maxey0_ss.__file__,\n"
        "    'tools': sorted(t.name for t in surface.tools),\n"
        "    'artifact': art,\n"
        "    'served_sha256': hashlib.sha256(served).hexdigest(),\n"
        "    'plane': sys.modules['planes.observe_impl'].__file__,\n"
        "    'unavailable': bridge.unavailable_reason(),\n"
        "    'source_root': None if settings.SOURCE_ROOT is None else str(settings.SOURCE_ROOT),\n"
        "    'config_root': str(settings.CONFIG_ROOT),\n"
        "    'environment': settings.settings().environment,\n"
        "}))\n"
    )

    venv = installed.venv.resolve()
    # The installed copy answered, not the checkout.
    assert Path(result["package"]).resolve().is_relative_to(venv), result["package"]
    assert Path(result["plane"]).resolve().is_relative_to(
        venv / ("Lib" if os.name == "nt" else "lib")
    ) and "_bundled" in Path(result["plane"]).parts, result["plane"]

    assert result["unavailable"] is None
    assert result["tools"] == checkout, (
        f"installed {len(result['tools'])} tools, checkout {len(checkout)}; "
        f"missing {sorted(set(checkout) - set(result['tools']))}"
    )

    art = result["artifact"]
    edge_sha = hashlib.sha256(EDGE_APP.read_bytes()).hexdigest()
    assert art["kind"] == "built", art
    assert art["sha256"] == edge_sha == result["served_sha256"]

    # Configuration comes from the working directory, never from site-packages.
    assert result["source_root"] is None
    assert Path(result["config_root"]).resolve() == installed.run_dir.resolve()
    assert result["environment"] == "from-the-working-directory"


@needs_build
def test_the_stdio_console_script_lists_every_tool(installed):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    script = installed.script("maxey0-ss-mcp")
    assert script.is_file(), f"{script.name} was not installed"

    async def session() -> dict:
        params = StdioServerParameters(
            command=str(script), args=[], cwd=str(installed.run_dir), env=installed.env(),
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()
                tools = (await client.list_tools()).tools
                health = await client.call_tool("maxey0-ss.health", {})
                # A bridged tool answering, not merely listed: it reads the
                # Gate policy under the throwaway home.
                gate = await client.call_tool("maxey0-ss.observe.gate_mode", {})
                return {
                    "tools": sorted(t.name for t in tools),
                    "kind": (health.structuredContent or {}).get("app_artifact", {}).get("kind"),
                    "gate_error": gate.isError,
                }

    result = asyncio.run(asyncio.wait_for(session(), timeout=180))
    assert result["tools"] == _checkout_tool_names()
    assert result["kind"] == "built"
    assert result["gate_error"] is False


@needs_build
def test_the_http_app_and_every_console_entry_point_load(installed):
    for name in CONSOLE_SCRIPTS:
        assert installed.script(name).is_file(), f"{name} was not installed"

    # Loaded rather than run: the HTTP entry points bind a port.
    result = installed.probe(
        "import json\n"
        "from importlib.metadata import distribution\n"
        "from fastapi.testclient import TestClient\n"
        "from maxey0_ss.api.app import app\n"
        "eps = [e for e in distribution('maxey0').entry_points\n"
        "       if e.group == 'console_scripts']\n"
        "loaded = {e.name: callable(e.load()) for e in eps}\n"
        "with TestClient(app) as client:\n"
        "    response = client.get('/health')\n"
        "print(json.dumps({'status': response.status_code, 'body': response.json(),\n"
        "                  'entry_points': loaded}))\n"
    )
    assert result["status"] == 200 and result["body"]["ok"] is True
    assert result["entry_points"] == {name: True for name in CONSOLE_SCRIPTS}


# --- resolution order and degraded paths, without building --------------------


def test_a_checkout_resolves_everything_from_the_source_tree():
    """The repository, editable installs and the Fly image behave as before."""
    assert settings.SOURCE_ROOT == ROOT
    assert settings.CONFIG_ROOT == ROOT
    assert settings.DEFAULT_ENV_FILE == ROOT / ".env"
    assert bridge._ROOT == ROOT
    assert mcp_surface._APP_ROOT == ROOT / "mcp_apps"


def test_only_this_projects_pyproject_marks_a_source_tree(tmp_path):
    assert settings._is_source_tree(ROOT)
    assert not settings._is_source_tree(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "some-other-distribution"\n', encoding="utf-8",
    )
    assert not settings._is_source_tree(tmp_path)


def test_without_a_source_tree_the_bundled_copies_are_used(monkeypatch, tmp_path):
    source, bundled = tmp_path / "site-packages", tmp_path / "maxey0_ss" / "_bundled"
    plane = bundled / "server" / "planes" / "observe_impl.py"
    plane.parent.mkdir(parents=True)
    plane.write_text("", encoding="utf-8")
    monkeypatch.setattr(bridge, "_SOURCE_ROOT", source)
    monkeypatch.setattr(bridge, "_BUNDLED_ROOT", bundled)
    assert bridge._plane_root() == bundled

    app = bundled / "mcp_apps" / "super_space_react" / "dist" / "mcp-app.html"
    app.parent.mkdir(parents=True)
    app.write_text("<!doctype html>", encoding="utf-8")
    monkeypatch.setattr(mcp_surface, "_SOURCE_APP_ROOT", source / "mcp_apps")
    monkeypatch.setattr(mcp_surface, "_BUNDLED_APP_ROOT", bundled / "mcp_apps")
    assert mcp_surface._app_root() == bundled / "mcp_apps"


def test_with_no_app_anywhere_health_still_answers_and_says_why(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_surface, "_APP_BUILT", tmp_path / "absent" / "mcp-app.html")
    monkeypatch.setattr(mcp_surface, "_APP_FALLBACK", tmp_path / "absent" / "super_space.html")
    art = mcp_surface.super_space_artifact()
    served = mcp_surface.super_space_html().encode("utf-8")
    assert art["kind"] == "fallback-stub"
    assert art["path"] is None and "super_space.html" in art["reason"]
    assert art["sha256"] == hashlib.sha256(served).hexdigest()
    assert art["bytes"] == len(served)


def test_with_no_plane_anywhere_the_surface_shrinks_and_says_why(monkeypatch):
    monkeypatch.setattr(bridge, "_ROOT", None)
    with pytest.warns(RuntimeWarning, match="observe/gate tools unavailable"):
        assert bridge.observability_tools() == []
    assert bridge.available() is False
    assert "server/planes/observe_impl.py" in bridge.unavailable_reason()
