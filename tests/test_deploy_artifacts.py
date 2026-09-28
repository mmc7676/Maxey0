"""The origin container artifacts, checked without Docker.

`Dockerfile`, `.dockerignore` and `deploy/entrypoint.sh` put the origin on the
internet behind a Cloudflare Tunnel. Every property that makes that safe is a
line in one of them that a later edit can drop without any other test
noticing: a `.env` admitted to the build context is baked into an image layer
and then loaded as configuration by `settings.py`; an EXPOSEd port gives the
container a door around Cloudflare; a CRLF entrypoint fails only after the
deploy has replaced the running container. So each one is asserted here, and the
entrypoint's refusals are executed rather than read.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import sys
import tomllib
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _env import ROOT  # noqa: E402

DOCKERFILE = ROOT / "Dockerfile"
DOCKERIGNORE = ROOT / ".dockerignore"
ENTRYPOINT = ROOT / "deploy" / "entrypoint.sh"
CONSTRAINTS = ROOT / "deploy" / "constraints.txt"

#: Variable names that carry credentials. None may have a value in a file that
#: is committed; all of them arrive from the host's secret store at runtime.
SECRET_NAME = re.compile(r"TOKEN|SECRET|PASSWORD|API_KEY|CREDENTIAL", re.IGNORECASE)


# ---------------------------------------------------------------------------
# .dockerignore, evaluated the way the Docker builder evaluates it
# ---------------------------------------------------------------------------


def _ignore_rules() -> list[tuple[bool, re.Pattern[str]]]:
    """(negated, regex) per rule, in file order.

    Docker's matcher is Go's `filepath.Match` plus `**`; a rule that matches a
    directory excludes everything below it, and the last matching rule wins.
    """
    rules = []
    for raw in DOCKERIGNORE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        negated = line.startswith("!")
        pattern = line[1:] if negated else line
        pattern = pattern.strip("/")
        regex, i = "", 0
        while i < len(pattern):
            if pattern.startswith("**/", i):
                regex, i = regex + "(?:.*/)?", i + 3
            elif pattern.startswith("**", i):
                regex, i = regex + ".*", i + 2
            elif pattern[i] == "*":
                regex, i = regex + "[^/]*", i + 1
            elif pattern[i] == "?":
                regex, i = regex + "[^/]", i + 1
            else:
                regex, i = regex + re.escape(pattern[i]), i + 1
        rules.append((negated, re.compile(regex)))
    return rules


def _in_context(rel_posix: str) -> bool:
    parts = rel_posix.split("/")
    prefixes = ["/".join(parts[: n + 1]) for n in range(len(parts))]
    included = True
    for negated, regex in _ignore_rules():
        if any(regex.fullmatch(p) for p in prefixes):
            included = negated
    return included


def _copy_instructions() -> list[tuple[list[str], str]]:
    """(sources, destination) for every COPY/ADD in the Dockerfile."""
    out = []
    for line in DOCKERFILE.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s*(COPY|ADD)\s+(.*)$", line, re.IGNORECASE)
        if not match:
            continue
        args = [a for a in match.group(2).split() if not a.startswith("--")]
        out.append((args[:-1], args[-1]))
    return out


class TestBuildContextKeepsSecretsOut(unittest.TestCase):

    def test_secret_files_never_reach_the_context(self):
        for rel in (
            ".env",
            ".env.local",
            ".env.production",
            "server/.env",
            "server/maxey0_studio/.env",
            "config/credentials.json",
            "anything/credentials.json",
            ".cloudflared/cert.pem",
            ".cloudflared/0000-tunnel.json",
        ):
            with self.subTest(path=rel):
                self.assertFalse(_in_context(rel), f"{rel} would be in the build context")

    def test_env_example_stays_in_the_context(self):
        self.assertTrue(_in_context(".env.example"))

    def test_local_state_and_build_output_are_excluded(self):
        for rel in (
            ".git/HEAD",
            ".venv/Scripts/python.exe",
            ".claude/settings.json",
            ".pytest_cache/v/cache",
            "maxey0_ss/__pycache__/settings.cpython-311.pyc",
            "maxey0_ss/settings.pyc",
            "mcp_apps/super_space_react/node_modules/react/index.js",
            "workers/mcp-edge/node_modules/wrangler/package.json",
            "mcp_apps/super_space_react/dist/mcp-app.html",
            "dist/maxey0-0.3.0.zip",
            "experiments/exp-001/run.json",
            "maxey0.egg-info/PKG-INFO",
        ):
            with self.subTest(path=rel):
                self.assertFalse(_in_context(rel), f"{rel} would be in the build context")

    def test_every_copied_source_is_in_the_context_and_exists(self):
        """An ignore rule that swallowed a COPY source fails the build late."""
        copies = _copy_instructions()
        self.assertTrue(copies)
        for sources, _ in copies:
            for src in sources:
                rel = src.rstrip("/")
                with self.subTest(source=src):
                    self.assertTrue((ROOT / rel).exists(), f"{src} does not exist")
                    probe = rel + "/x.py" if (ROOT / rel).is_dir() else rel
                    self.assertTrue(_in_context(probe), f"{src} is excluded by .dockerignore")


# ---------------------------------------------------------------------------
# Dockerfile
# ---------------------------------------------------------------------------


class TestDockerfile(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.text = DOCKERFILE.read_text(encoding="utf-8")

    def test_never_copies_the_whole_tree_or_a_secret(self):
        for sources, dest in _copy_instructions():
            for src in sources:
                with self.subTest(source=src):
                    self.assertNotIn(src.rstrip("/"), {".", "./", "*"})
                    name = src.rstrip("/").rsplit("/", 1)[-1]
                    self.assertFalse(name.startswith(".env"), src)
                    self.assertNotEqual(name, "credentials.json")
                    self.assertNotIn(".cloudflared", src)
            self.assertFalse(dest.rsplit("/", 1)[-1].startswith(".env"), dest)

    def test_no_build_argument_or_env_default_is_a_secret(self):
        for match in re.finditer(r"^\s*ARG\s+([A-Za-z_][A-Za-z0-9_]*)", self.text, re.MULTILINE):
            with self.subTest(arg=match.group(1)):
                self.assertIsNone(SECRET_NAME.search(match.group(1)))
        for name in self._env_defaults():
            with self.subTest(env=name):
                self.assertIsNone(SECRET_NAME.search(name))

    def _env_defaults(self) -> dict[str, str]:
        joined = re.sub(r"\\\n", " ", self.text)
        env: dict[str, str] = {}
        for line in joined.splitlines():
            if re.match(r"^\s*ENV\s", line):
                for key, value in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)=(\S+)", line):
                    env[key] = value
        return env

    def test_container_defaults_are_the_fail_closed_ones(self):
        env = self._env_defaults()
        self.assertEqual(env.get("MAXEY0_PUBLIC"), "1")
        self.assertEqual(env.get("MAXEY0_AUTH_MODE"), "bearer")
        self.assertEqual(env.get("MAXEY0_HOST"), "127.0.0.1")
        self.assertEqual(env.get("MAXEY0_ENV"), "production")
        self.assertEqual(env.get("SCW_HOME"), "/data/scw")
        self.assertEqual(env.get("PYTHONDONTWRITEBYTECODE"), "1")
        self.assertEqual(env.get("PYTHONUNBUFFERED"), "1")

    def test_workloads_run_as_dedicated_unprivileged_users(self):
        """No USER line: the entrypoint drops root itself, per process.

        The last USER, if one is ever added, must not be root either.
        """
        users = dict(re.findall(r"useradd\b[^;\n]*--uid (\d+)[^;\n]*\s([a-z][a-z0-9_-]*);", self.text))
        users = {name: int(uid) for uid, name in users.items()}
        self.assertEqual(set(users), {"maxey0", "cloudflared"})
        for name, uid in users.items():
            with self.subTest(user=name):
                self.assertGreaterEqual(uid, 1000)
        self.assertEqual(len(set(users.values())), 2, "one uid per process")
        user_lines = re.findall(r"^\s*USER\s+(\S+)", self.text, re.MULTILINE)
        if user_lines:
            self.assertNotIn(user_lines[-1].split(":")[0], {"root", "0"})

    def test_tini_is_init_and_runs_the_entrypoint(self):
        self.assertRegex(
            self.text,
            r'ENTRYPOINT \["/usr/bin/tini", "-s", "--", "/app/deploy/entrypoint\.sh"\]',
        )

    def test_cloudflared_is_pinned_and_checksum_verified(self):
        version = re.search(r"^ARG CLOUDFLARED_VERSION=(\S+)$", self.text, re.MULTILINE)
        digest = re.search(r"^ARG CLOUDFLARED_SHA256=(\S+)$", self.text, re.MULTILINE)
        self.assertIsNotNone(version)
        self.assertIsNotNone(digest)
        self.assertRegex(version.group(1), r"^\d{4}\.\d+\.\d+$")
        self.assertRegex(digest.group(1), r"^[0-9a-f]{64}$")
        self.assertIn("sha256sum -c", self.text)
        self.assertIn(f"releases/tag/{version.group(1)}", self.text,
                      "the comment must cite the release the digest came from")

    def test_base_image_is_python_3_11_slim(self):
        self.assertRegex(self.text, r"(?m)^FROM python:3\.11-slim")

    def test_the_image_has_the_paths_the_origin_resolves(self):
        """settings, mcp_surface and the bridge resolve paths from the source tree.

        So the image reproduces the tree's layout under /app and runs from it,
        rather than installing a site-packages copy that would find neither
        mcp_apps/ nor server/.
        """
        from maxey0_ss import mcp_surface
        from maxey0_ss.observability import bridge

        self.assertRegex(self.text, r"(?m)^WORKDIR /app$")
        self.assertEqual(self._env_defaults().get("PYTHONPATH"), "/app")
        destinations = {dest.rstrip("/") for _, dest in _copy_instructions()}
        for path in (mcp_surface._APP_BUILT, mcp_surface._APP_FALLBACK):
            with self.subTest(path=path.name):
                self.assertIn(path.relative_to(ROOT).as_posix(), destinations)
        self.assertIn((bridge._ROOT / "server").relative_to(ROOT).as_posix(), destinations)
        self.assertIn("maxey0_ss", destinations)

    def test_the_app_bundle_is_the_tracked_edge_copy(self):
        """The origin serves the bytes the edge advertises."""
        sources = {dest.rstrip("/"): srcs for srcs, dest in _copy_instructions()}
        self.assertEqual(
            sources["mcp_apps/super_space_react/dist/mcp-app.html"],
            ["workers/mcp-edge/src/generated/super-space.html"],
        )


# ---------------------------------------------------------------------------
# deploy/entrypoint.sh
# ---------------------------------------------------------------------------


class TestEntrypointText(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.raw = ENTRYPOINT.read_bytes()
        cls.text = cls.raw.decode("utf-8")

    def test_lf_line_endings_and_a_posix_shebang(self):
        self.assertNotIn(b"\r", self.raw)
        self.assertTrue(self.raw.startswith(b"#!/bin/sh\n"))

    def test_git_checks_it_out_with_lf_on_every_platform(self):
        out = subprocess.run(
            ["git", "check-attr", "eol", "--", "deploy/entrypoint.sh", "Dockerfile"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout
        self.assertIn("deploy/entrypoint.sh: eol: lf", out)
        self.assertIn("Dockerfile: eol: lf", out)

    def test_the_tunnel_token_is_never_on_a_command_line(self):
        """cloudflared reads TUNNEL_TOKEN itself; `--token` would show it in `ps`."""
        code = "\n".join(
            line for line in self.text.splitlines() if not line.lstrip().startswith("#")
        )
        self.assertNotRegex(code, r"--token")
        # The script expands the token exactly once: to test that it is set.
        self.assertEqual(re.findall(r"\$\{?TUNNEL_TOKEN[^}\s\"]*\}?", code), ["${TUNNEL_TOKEN:-}"])
        self.assertRegex(code, r"cloudflared tunnel --no-autoupdate \\\n\s+--grace-period \S+ run")

    def test_the_origin_does_not_inherit_the_tunnel_token(self):
        self.assertRegex(self.text, r"env -u TUNNEL_TOKEN python -m maxey0_ss\.public_server")

    def test_every_workload_drops_root(self):
        launches = re.findall(r"^\s*\(?\s*run_as \"\$(\w+)\" (\S+)", self.text, re.MULTILINE)
        self.assertEqual(sorted(u for u, _ in launches), ["ORIGIN_USER", "TUNNEL_USER"])
        self.assertIn('setpriv --reuid="$user" --regid="$user" --init-groups --no-new-privs', self.text)
        self.assertIn("ORIGIN_USER=maxey0", self.text)
        self.assertIn("TUNNEL_USER=cloudflared", self.text)

    def _function(self, name: str) -> str:
        match = re.search(rf"(?ms)^{name}\(\) \{{\n.*?^\}}\n", self.text)
        self.assertIsNotNone(match, name)
        return match.group(0)

    def _sh(self, script: str, env: dict[str, str]) -> subprocess.CompletedProcess:
        sh = _posix_sh()
        if sh is None:
            self.skipTest("no POSIX sh")
        base = {"PATH": os.pathsep.join([str(pathlib.Path(sh).parent), os.environ.get("PATH", "")])}
        if os.name == "nt":
            base["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", r"C:\Windows")
        return subprocess.run([sh, "-c", script], env={**base, **env},
                              capture_output=True, text=True, timeout=60)

    def test_cloudflared_gets_an_allowlisted_environment(self):
        """Unsetting MAXEY0_* left cloudflared every provider API key."""
        result = self._sh(self._function("tunnel_env") + "tunnel_env\nenv\n", {
            "HOME": "/root", "TUNNEL_TOKEN": "tok", "TUNNEL_LOGLEVEL": "info",
            "HTTPS_PROXY": "http://proxy:3128", "no_proxy": "localhost",
            "ANTHROPIC_API_KEY": "sk-leak", "OPENAI_API_KEY": "sk-leak2",
            "MAXEY0_MCP_TOKENS": "t:admin", "PLATFORM_API_TOKEN": "platform-leak",
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        names = set(re.findall(r"(?m)^([A-Za-z_][A-Za-z0-9_]*)=", result.stdout))
        self.assertTrue({"PATH", "HOME", "TUNNEL_TOKEN", "TUNNEL_LOGLEVEL",
                         "HTTPS_PROXY", "no_proxy"} <= names, names)
        allowed = {"PATH", "HOME", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
                   "http_proxy", "https_proxy", "no_proxy"}
        # The shell may export a few of its own (PWD, SHLVL, _); nothing given.
        self.assertFalse({n for n in names if n not in allowed and not n.startswith("TUNNEL_")}
                         & {"ANTHROPIC_API_KEY", "OPENAI_API_KEY", "MAXEY0_MCP_TOKENS",
                            "PLATFORM_API_TOKEN"})
        self.assertNotIn("leak", result.stdout)

    def test_the_tunnel_is_stopped_before_the_origin(self):
        """TERMed together, the origin went while cloudflared was draining."""
        # A log under the test's own temp dir: `mktemp` defaults to /tmp, which
        # a sandboxed or Git-for-Windows sh may not be allowed to write.
        log_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, log_dir, True)
        log_path = os.path.join(log_dir, "order.log").replace("\\", "/")
        script = (self._function("stop_within") + self._function("stop_children") + f"""
log='{log_path}'
: > "$log"
sh -c 'trap "sleep 1; echo tunnel-exited >> $0; exit 0" TERM; while :; do sleep 0.1; done' "$log" &
tunnel_pid=$!
sh -c 'trap "echo origin-termed >> $0; exit 0" TERM; while :; do sleep 0.1; done' "$log" &
origin_pid=$!
TUNNEL_STOP_S=10
ORIGIN_STOP_S=10
sleep 0.5
stop_children
cat "$log"
""")
        result = self._sh(script, {})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.split(), ["tunnel-exited", "origin-termed"])

    def test_the_shutdown_budget_fits_the_kill_timeout(self):
        budget = {k: int(v) for k, v in re.findall(
            r"(?m)^(TUNNEL_GRACE_S|TUNNEL_STOP_S|ORIGIN_STOP_S)=(\d+)$", self.text)}
        # The host's stop timeout, which deploy/entrypoint.sh documents as 40 s.
        kill_timeout = 40
        self.assertLess(budget["TUNNEL_GRACE_S"], budget["TUNNEL_STOP_S"])
        self.assertLess(budget["TUNNEL_STOP_S"] + budget["ORIGIN_STOP_S"], kill_timeout)
        self.assertIn('--grace-period "${TUNNEL_GRACE_S}s"', self.text)

    def test_the_mcp_token_names_it_mentions_are_real(self):
        """The warnings name variables; a renamed variable would silence them."""
        example = (ROOT / ".env.example").read_text(encoding="utf-8")
        for name in set(re.findall(r"MAXEY0_MCP_[A-Z_]+", self.text)):
            with self.subTest(name=name):
                self.assertRegex(example, rf"(?m)^{name}=")


def _posix_sh() -> str | None:
    """A POSIX sh: on PATH, or the one Git for Windows ships beside git."""
    found = shutil.which("sh")
    if found:
        return found
    git = shutil.which("git")
    if git:
        candidate = pathlib.Path(git).resolve().parents[1] / "usr" / "bin" / "sh.exe"
        if candidate.is_file():
            return str(candidate)
    return None


@unittest.skipIf(_posix_sh() is None, "no POSIX sh on PATH")
class TestEntrypointRefuses(unittest.TestCase):
    """Run the real script in configurations it must refuse.

    Every case fails a check that precedes launching anything, so no origin or
    tunnel is started. The environment is built from nothing but PATH, so a
    token exported in the developer's shell cannot make a case pass.
    """

    BASE = {
        "MAXEY0_PUBLIC": "1",
        "MAXEY0_AUTH_MODE": "bearer",
        "MAXEY0_HOST": "127.0.0.1",
        "TUNNEL_TOKEN": "test-tunnel-value",
    }

    def run_entrypoint(self, **overrides: str | None) -> subprocess.CompletedProcess:
        # The shell's own directory first, so `tr` and `id` are its siblings.
        # Without them `lower` would print nothing and every value would be
        # refused -- for the wrong reason, which these cases would not notice
        # but test_the_public_check_matches_the_policy_it_guards would.
        sh = _posix_sh()
        env = {"PATH": os.pathsep.join([str(pathlib.Path(sh).parent), os.environ.get("PATH", "")])}
        if os.name == "nt":
            env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", r"C:\Windows")
        env.update(self.BASE)
        for key, value in overrides.items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        return subprocess.run(
            [_posix_sh(), "deploy/entrypoint.sh"],
            cwd=ROOT, env=env, capture_output=True, text=True, timeout=60,
        )

    def assertRefused(self, result: subprocess.CompletedProcess, names: str) -> None:
        self.assertEqual(result.returncode, 78, result.stderr)
        self.assertIn("refusing to start", result.stderr)
        self.assertIn(names, result.stderr)
        self.assertNotIn("origin started", result.stderr)

    def test_public_unset(self):
        self.assertRefused(self.run_entrypoint(MAXEY0_PUBLIC=None), "MAXEY0_PUBLIC")

    def test_public_false(self):
        for value in ("0", "", "false", "no"):
            with self.subTest(value=value):
                self.assertRefused(self.run_entrypoint(MAXEY0_PUBLIC=value), "MAXEY0_PUBLIC")

    def test_auth_disabled_or_unset(self):
        for value in ("disabled", "", "none", "bearr"):
            with self.subTest(value=value):
                self.assertRefused(self.run_entrypoint(MAXEY0_AUTH_MODE=value), "MAXEY0_AUTH_MODE")
        self.assertRefused(self.run_entrypoint(MAXEY0_AUTH_MODE=None), "MAXEY0_AUTH_MODE")

    def test_no_tunnel_token(self):
        self.assertRefused(self.run_entrypoint(TUNNEL_TOKEN=None), "TUNNEL_TOKEN")
        self.assertRefused(self.run_entrypoint(TUNNEL_TOKEN=""), "TUNNEL_TOKEN")

    def test_tunnel_switch_takes_only_on_or_off(self):
        self.assertRefused(self.run_entrypoint(MAXEY0_TUNNEL="maybe"), "MAXEY0_TUNNEL")

    def test_wide_bind_with_the_tunnel_on(self):
        self.assertRefused(self.run_entrypoint(MAXEY0_HOST="0.0.0.0"), "MAXEY0_HOST")

    def test_the_public_check_matches_the_policy_it_guards(self):
        """Every value the entrypoint accepts, the process also treats as public."""
        from maxey0_ss.auth import policy

        for value in ("1", "true", "YES", "On"):
            with self.subTest(value=value):
                # Passes the public check, then stops at the next one.
                result = self.run_entrypoint(MAXEY0_PUBLIC=value, MAXEY0_AUTH_MODE="disabled")
                self.assertRefused(result, "MAXEY0_AUTH_MODE")
                previous = os.environ.get("MAXEY0_PUBLIC")
                os.environ["MAXEY0_PUBLIC"] = value
                try:
                    self.assertTrue(policy.is_public_deployment())
                finally:
                    if previous is None:
                        os.environ.pop("MAXEY0_PUBLIC", None)
                    else:
                        os.environ["MAXEY0_PUBLIC"] = previous


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


class TestDependencies(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        cls.pins = {}
        for line in CONSTRAINTS.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name, sep, version = line.partition("==")
            cls.pins[re.sub(r"[-_.]+", "-", name).lower()] = (sep, version)

    def test_mcp_is_a_core_dependency(self):
        """`maxey0_ss.api.app` needs it at import; an extra is not enough."""
        core = self.project["dependencies"]
        self.assertIn("mcp>=1.19.0,<2", core)
        self.assertIn("mcp>=1.19.0,<2", self.project["optional-dependencies"]["mcp"])

    def test_every_constraint_is_an_exact_pin(self):
        for name, (sep, version) in self.pins.items():
            with self.subTest(package=name):
                self.assertEqual(sep, "==")
                self.assertRegex(version, r"^[0-9][0-9A-Za-z.+!-]*$")

    def test_nothing_local_or_windows_only_is_pinned(self):
        text = CONSTRAINTS.read_text(encoding="utf-8")
        self.assertNotRegex(text, r"(?m)^\s*-e\b")
        self.assertNotIn("maxey0", self.pins)
        self.assertNotIn("pywin32", self.pins)
        self.assertNotIn("colorama", self.pins)

    def test_every_core_dependency_is_pinned(self):
        for requirement in self.project["dependencies"]:
            name = re.sub(r"[-_.]+", "-", re.match(r"[A-Za-z0-9_.-]+", requirement).group(0)).lower()
            with self.subTest(requirement=requirement):
                self.assertIn(name, self.pins)

    def test_the_linux_runtime_closure_is_pinned(self):
        """Every package the image installs, not only the four it names.

        Walks the installed metadata from the core dependencies with Linux
        markers, because that is what `pip install` inside the image resolves.
        A dependency added by an `mcp` upgrade and missing here would be
        installed at whatever version PyPI serves on the day of the deploy.
        """
        try:
            import importlib.metadata as md

            from packaging.requirements import Requirement
            from packaging.markers import default_environment
        except ImportError:  # pragma: no cover - packaging ships with pytest
            self.skipTest("packaging is not installed")

        env = default_environment()
        env.update({"sys_platform": "linux", "platform_system": "Linux", "os_name": "posix",
                    "platform_machine": "x86_64", "python_version": "3.11"})
        todo = [Requirement(r) for r in self.project["dependencies"]]
        seen: set[tuple[str, tuple[str, ...]]] = set()
        unpinned = set()
        while todo:
            req = todo.pop()
            name = re.sub(r"[-_.]+", "-", req.name).lower()
            if (name, tuple(sorted(req.extras))) in seen:
                continue
            seen.add((name, tuple(sorted(req.extras))))
            if name not in self.pins:
                unpinned.add(name)
            try:
                requires = md.distribution(req.name).requires or []
            except md.PackageNotFoundError:
                self.skipTest(f"{req.name} is not installed here, so its dependencies are unknown")
            for raw in requires:
                sub = Requirement(raw)
                extras = sorted(req.extras) or [""]
                if sub.marker is None or any(sub.marker.evaluate({**env, "extra": e}) for e in extras):
                    todo.append(sub)
        self.assertEqual(unpinned, set(), "regenerate deploy/constraints.txt")

    def test_the_mcp_pin_satisfies_the_declared_bound(self):
        major, minor, *_ = (int(p) for p in self.pins["mcp"][1].split("."))
        self.assertTrue((1, 19) <= (major, minor) < (2, 0), self.pins["mcp"])


# ---------------------------------------------------------------------------
# The whole set, against the release secret scanner
# ---------------------------------------------------------------------------


class TestNoCredentialShapes(unittest.TestCase):

    def test_scanner_finds_nothing_in_the_deploy_files(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        from _packaging import scan_for_secrets

        files = [DOCKERFILE, DOCKERIGNORE, ENTRYPOINT, CONSTRAINTS,
                 pathlib.Path(__file__).resolve()]
        self.assertEqual(scan_for_secrets(files, ROOT), [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
