"""The single Maxey0-SuperSpace MCP surface, shared by every transport.

One definition of the tools and resources lives here. Transports adapt it:

- ``mcp_public_server``  — MCP 2026-07-28 stateless Streamable HTTP (``POST /mcp``)
- ``mcp_stdio_server``   — classic stdio MCP, for hosts that still open a session

Keeping the surface in one module is what makes the two transports honest: a
tool added for the remote endpoint cannot silently go missing from the local
one, because neither transport owns the list.
"""
from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path

from .auth.config import AuthConfig
from .auth.policy import (
    OBSERVE_READ,
    SCW_ADMIT,
    SCW_CREATE,
    SCW_READ,
    Authorizer,
)
from .observability.bridge import observability_tools
from .providers import ProviderError, ProviderRefused
from .providers import public_manifest as providers_manifest
from .providers import registry as provider_registry
from .distribution import public_manifest as distribution_manifest
from .cache import (
    NEVER_CACHE,
    CacheConfig,
    MaxeyCache,
    Namespace,
    SERVER_SCOPE,
    SemanticPlane,
    assert_cacheable,
)
from .cache.policy import MCPMetadataCache
from .gating.address import EnforceableAddress
from .gating.semantic import SemanticGateProvider, select_semantic_gate
from .semantic.runtime import UnanchoredWindow, validate_threshold, validate_vector
from .host_window import HostWindowObserver
from .mcp_2026 import Resource, Tool
from .ratelimit import RateLimiter
from .scw_deployer import deploy_default_scw
from .containment import GENESIS, AttestationLog
from .settings import settings as _deployment_settings
from .tasks import TaskError, TaskStore, _OWNER
from .system import SuperSpaceSystem

SERVER_NAME = "Maxey0-SuperSpace"
from . import __version__ as SERVER_VERSION  # noqa: E402  (one literal)
SUPER_SPACE_URI = "ui://maxey0-ss/super-space.html"

#: Where the MCP App is looked for, in priority order. The source tree beside
#: the package comes first, so a checkout, an editable install and the
#: container image (which copies both files to /app/mcp_apps) serve exactly what they sit
#: next to, as they always have. An installed wheel has no source tree -- the
#: package's parent is site-packages -- so it serves the copy setup.py writes
#: into the package at build time.
_SOURCE_APP_ROOT = Path(__file__).resolve().parents[1] / "mcp_apps"
_BUNDLED_APP_ROOT = Path(__file__).resolve().parent / "_bundled" / "mcp_apps"
_APP_BUILT_NAME = Path("super_space_react", "dist", "mcp-app.html")
_APP_FALLBACK_NAME = Path("super_space.html")


def _app_root() -> Path:
    """The first App directory holding either file; the source tree if none does."""
    for root in (_SOURCE_APP_ROOT, _BUNDLED_APP_ROOT):
        if (root / _APP_BUILT_NAME).is_file() or (root / _APP_FALLBACK_NAME).is_file():
            return root
    return _SOURCE_APP_ROOT


#: Where the MCP App artifact is read from, in priority order.
_APP_ROOT = _app_root()
_APP_BUILT = _APP_ROOT / _APP_BUILT_NAME
_APP_FALLBACK = _APP_ROOT / _APP_FALLBACK_NAME

#: Served when neither file exists anywhere: a partial checkout, or a package
#: built without the App. `health` reports the artifact and is public, so
#: raising FileNotFoundError there took the whole health check down with the
#: App. This page says what is missing instead, and the artifact reports
#: `fallback-stub` with a `reason`, which deployment verification already
#: treats as the App not being the one we built.
_MISSING_APP_REASON = (
    "neither mcp_apps/super_space_react/dist/mcp-app.html nor "
    "mcp_apps/super_space.html was found beside the maxey0_ss package or "
    "inside it under _bundled/"
)
_MISSING_APP_HTML = (
    "<!doctype html>\n<html><head><meta charset=\"utf-8\">"
    "<title>Maxey0-SuperSpace</title></head><body>\n"
    "<p>The Maxey0-SuperSpace MCP App is not installed with this server: "
    f"{_MISSING_APP_REASON}.</p>\n</body></html>\n"
)


#: (path, mtime_ns, size) -> (artifact description, the exact text served).
#: See `_read_artifact`.
_ARTIFACT_MEMO: dict[tuple[str, int, int], tuple[dict[str, object], str]] = {}


def _read_artifact() -> tuple[dict[str, object], str]:
    """The App artifact: its identity and the exact text that will be served.

    One read, one decode, one hash — because two of them disagreed.
    `super_space_artifact` hashed `read_bytes()` while `super_space_html`
    returned `read_text()`, and `read_text` applies universal-newline
    translation. A bundle containing five CRLF sequences (which Vite emits
    depending on what is inlined) was therefore 475802 bytes when hashed and
    475797 bytes when served: the server published a SHA-256 of bytes it did
    not send, from the field a production verifier checks to decide whether the
    App it received is the App we built.

    It passed for months because the bundles happened to contain no CRLF. A
    check that is correct by luck is the same defect as a metric pinned at
    zero — it reads as evidence and measures nothing.

    `bytes.decode` is used rather than `Path.read_text` precisely because it
    does not translate newlines, so `text.encode("utf-8") == raw` holds and the
    digest describes what goes on the wire.
    """
    if _APP_BUILT.exists():
        path = _APP_BUILT
    elif _APP_FALLBACK.exists():
        path = _APP_FALLBACK
    else:
        # Not memoized: nothing is read from disk, and hashing a few hundred
        # bytes is not the amplification the memo exists to prevent.
        raw = _MISSING_APP_HTML.encode("utf-8")
        return {
            "kind": "fallback-stub",
            "path": None,
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "uri": SUPER_SPACE_URI,
            "reason": _MISSING_APP_REASON,
        }, _MISSING_APP_HTML
    stat = path.stat()
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    hit = _ARTIFACT_MEMO.get(key)
    if hit is not None:
        return dict(hit[0]), hit[1]
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    value: dict[str, object] = {
        "kind": "built" if path == _APP_BUILT else "fallback-stub",
        "path": path.name,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "uri": SUPER_SPACE_URI,
    }
    _ARTIFACT_MEMO.clear()  # only ever one live artifact; do not grow unbounded
    _ARTIFACT_MEMO[key] = (value, text)
    return dict(value), text


def super_space_artifact() -> dict[str, object]:
    """Identify the MCP App artifact actually being served.

    The server falls back to an unbuilt stub when the React bundle is missing,
    which otherwise fails silently and looks like a working App. Reporting the
    artifact identity makes that visible to production verification.

    Memoized by `_read_artifact` on the file's own (mtime_ns, size), because
    this is reached by `maxey0-ss.health`, which is public and
    uncapability-gated, and it read ~470 KB and computed a SHA-256 on every
    single call. That is cheap amplification on an unauthenticated path.

    Keyed on the stat rather than given a TTL on purpose. A TTL would trade
    correctness for latency — it would report a stale digest for the length of
    the window after a rebuild, which is precisely the question this function
    exists to answer during a deployment.
    """
    return _read_artifact()[0]


def super_space_html() -> str:
    """The exact text `app.artifact.sha256` is the digest of. See `_read_artifact`."""
    return _read_artifact()[1]


#: Runs `provider.complete` for callers that asked for an early task handle.
#: Module-level and small on purpose: a model round-trip is I/O-bound, and the
#: pool bounds how many egresses one process has in flight however many
#: callers ask for `async`. Excess submissions queue rather than spawn.
_TASK_WORKERS = ThreadPoolExecutor(max_workers=4, thread_name_prefix="maxey0-task")


#: Most attestations any single `evidence.attestations` call will return.
MAX_ATTESTATION_LIMIT = 1000
DEFAULT_ATTESTATION_LIMIT = 200
#: Records one evidence.verify call may hash. The tool is public.
MAX_VERIFY_RECORDS = 10_000


def _clamp_limit(
    raw: object,
    *,
    default: int = DEFAULT_ATTESTATION_LIMIT,
    maximum: int = MAX_ATTESTATION_LIMIT,
) -> int:
    """A record count, or the default. Never a value that inverts a slice.

    `evidence.attestations` did ``limit = int(args.get("limit") or 200)`` and
    then ``records[-limit:]``. A negative limit inverts the slice's meaning:
    ``limit=-5`` yields ``records[5:]``, which returns everything *except* the
    first five — far more than the cap, from the tool that discloses the
    containment record. A float or a non-numeric string raised out of `int()`
    and surfaced as -32603 "Tool execution failed", which is a confusing way to
    report a bad argument.
    """
    # 0 kept its original meaning. `int(args.get("limit") or 200)` made
    # zero select the default, and silently turning it into "return
    # nothing" would be a second behavior change riding along with a
    # bug fix. Only the genuine defects change anything here.
    if raw is None or raw == "" or raw == 0:
        return default
    if isinstance(raw, bool):  # bool is an int; `limit: true` is not a count
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(1, min(value, maximum))


def _drift_anchors(arguments: object) -> bool:
    """Whether a `scw.drift` call installs a baseline rather than measuring.

    One predicate for the handler and for the capability the call demands, so
    the two cannot disagree about what counts as anchoring. The stateless
    transport does not validate arguments against the schema, so `"anchor":
    "no"` is truthy there; if the handler anchors on it, it has to be
    authorized as an anchor.
    """
    return isinstance(arguments, dict) and bool(arguments.get("anchor"))


def _drift_capability(arguments: object) -> str | None:
    """`scw.drift` measures under scw.read; anchoring also needs scw.admit.

    Anchoring installs the baseline every later measurement is judged against,
    so a caller who may anchor can make a drifted window read as healthy by
    re-anchoring it where it now is. `/v1/context/scws/{id}/anchor` already
    demanded scw.admit; over MCP both halves needed only scw.read, so the same
    write was a tier cheaper through the other door.
    """
    return SCW_ADMIT if _drift_anchors(arguments) else None


#: Which cache plane a tool's result belongs to. Absent means "do not cache",
#: which together with `NEVER_CACHE` makes caching opt-in: a tool added later
#: is uncached until somebody decides where it belongs, rather than cached by
#: default and found to be wrong afterwards.
#:
#: Only tools whose result is a pure function of server state appear here. The
#: SCW-bound tools are in `NEVER_CACHE` for reasons that are correctness, not
#: performance, and `_wire_cache` asserts that rather than assuming it.
CACHEABLE_PLANES: dict[str, SemanticPlane] = {
    "maxey0-ss.health": SemanticPlane.PROTOCOL,
    "maxey0-ss.distribution": SemanticPlane.PROTOCOL,
    "maxey0-ss.app.artifact": SemanticPlane.PROTOCOL,
}


def _wire_cache(tools: list[Tool], app_cache: MaxeyCache) -> None:
    """Give the application cache a write path.

    `MaxeyCache` was constructed, invalidated on `scw.close`, and reported by
    `cache.status` — but nothing ever called `put`, so no `CacheView` was ever
    created, `get` was never reached, `_entries` was permanently empty,
    `invalidate_scw` always dropped 0, and every metric in `cache.status` was
    structurally pinned at zero. That is the failure mode this project keeps
    producing in its sharpest form: a live-looking observability block that is
    incapable of ever being non-zero, published from a tool whose whole purpose
    is to report the truth about caching.

    `assert_cacheable`/`NEVER_CACHE` had the same problem from the other side:
    a correctness artifact — a list of results that would be *bugs* to cache,
    each with its reason — enforced at zero call sites. The wiring here is what
    makes that list mean something, and the hit rate is beside the point. Every
    tool selected for caching is passed through `assert_cacheable` first, so
    the two lists cannot disagree: adding a tool to `CACHEABLE_PLANES` that is
    also in `NEVER_CACHE` raises at import, not in production.

    Wrapping happens here rather than in either transport deliberately. Both
    `mcp_2026.build_router` and `mcp_stdio_server.build_server` call
    `tool.handler(arguments)`, so wiring a transport would mean two copies of
    the policy that could drift — which is the argument this module exists to
    make about the tool list itself.
    """
    for index, tool in enumerate(tools):
        plane = CACHEABLE_PLANES.get(tool.name)
        if plane is None:
            continue
        # Refuses at construction if this name is on the never-cache list.
        assert_cacheable(tool.name)
        view = app_cache.view(Namespace(plane))
        inner = tool.handler
        name = tool.name

        def cached(arguments: dict, *, _view=view, _inner=inner, _name=name):
            hit = _view.get(_name, arguments)
            if hit is not None:
                return hit
            value = _inner(arguments)
            _view.put(_name, arguments, value=value)
            return value

        tools[index] = replace(tool, handler=cached)


class AlreadyRunning(ValueError):
    """The specification already has an open instance on this runtime.

    A ValueError for the MCP transports; its own type so HTTP answers 409.
    Starting again re-registered the same instance id with containment and
    replaced the live window's state, silently discarding what it had admitted.
    """


def start_instance(system: SuperSpaceSystem, scw_id: str, owner: str,
                   app_cache: MaxeyCache | None = None) -> dict:
    """Start `scw_id` for `owner`. Shared by the MCP tool and /v1."""
    if scw_id not in system.context.graph.scw_specs:
        raise ValueError(f"Unknown SCW specification: {scw_id}")
    running = [
        iid for iid, inst in system.context.instances.items()
        if inst.spec_id == scw_id and inst.open
        and inst.runtime_id == system.scw_runtime.runtime_id
    ]
    if running:
        raise AlreadyRunning(f"{scw_id} is already running as {running[0]}")
    instance = system.scw_runtime.start(scw_id, owner)
    dropped = 0
    if app_cache is not None:
        # A reused identifier must not answer from the previous window's cache.
        dropped = app_cache.invalidate_scw(scw_id) + app_cache.invalidate_scw(instance.id)
    system.observatory.record("scw.start", "maxey0-ss", scw=instance.id, owner=owner)
    return {"started": instance.id, "scw_id": scw_id, "owner": owner,
            "runtime": instance.runtime_id, "address": instance.address.key(),
            "cache_entries_dropped": dropped}


@dataclass
class Surface:
    """Everything a transport needs, and nothing transport-specific."""

    tools: list[Tool]
    resources: list[Resource]
    cache: MCPMetadataCache
    system: SuperSpaceSystem
    #: Namespaced application cache, partitioned by semantic plane and SCW.
    app_cache: MaxeyCache | None = None
    #: MCP Tasks extension store (SEP-2663). Application state, like an SCW.
    tasks: TaskStore | None = None
    #: The one Authorizer every transport and the /v1 middleware resolve
    #: callers with. Each used to build its own -- /v1 a fresh one per request
    #: -- so `auth.manifest` described an instance that decided nothing, and
    #: the rate limiter would have been a fifth opinion about who was calling.
    authorizer: Authorizer | None = None
    #: Rate limits and request caps. Enforced only by the HTTP app that wraps
    #: itself in `RateLimitMiddleware`; reported by `auth.manifest` either way.
    rate_limiter: RateLimiter | None = None


def build_surface(
    system: SuperSpaceSystem | None = None,
    *,
    semantic_gate: SemanticGateProvider | None = None,
    authorizer: Authorizer | None = None,
    rate_limiter: RateLimiter | None = None,
) -> Surface:
    system = system or SuperSpaceSystem()
    observer = HostWindowObserver()
    auth = authorizer or Authorizer(AuthConfig.load())
    limiter = rate_limiter or RateLimiter()
    cache = MCPMetadataCache()
    app_cache = MaxeyCache(CacheConfig.from_env())
    task_store = TaskStore()
    # The gate the surface reports on is the gate configuration selected,
    # not a fresh default: `gate.inspect` must answer for the same provider
    # the transports enforce with.
    semantic_gate = semantic_gate or select_semantic_gate()
    # The system's runtime, not a second one. The surface used to build its
    # own, so a baseline anchored over MCP was invisible to /v1 drift and the
    # reverse: two stores answering the same question differently.
    drift_runtime = system.drift_runtime
    # Providers share the containment log the rest of the surface writes to,
    # so `evidence.attestations` returns one ordered record of everything
    # that crossed a boundary -- including the calls that left the process.
    providers = provider_registry(
        log=system.context.isolation.log,
        gate=semantic_gate,
        containment=system.context.isolation,
    )

    def health(_: dict):
        return {
            "ok": True,
            "service": "maxey0-ss",
            "mcp_protocol": "2026-07-28",
            "app_artifact": super_space_artifact(),
        }

    def distribution(_: dict):
        """Every way this product is installed, derived from the registry.

        This returned four written-down lists, and the harness list named four
        adapters while the package shipped six. A tool whose job is to say what
        exists has to read what exists: `maxey0_ss.distribution.registry` is the
        one declaration, `scripts/build_distributions.py` generates every
        manifest from it, and packaging refuses to run if they have drifted.
        """
        return distribution_manifest()

    def auth_manifest(_: dict):
        """Authorization posture, including whether this origin is admin-open.

        This returned `AuthConfig.public_manifest()`, which describes what
        was *configured* and not what is *enforced*. `Authorizer.manifest()`
        -- which adds `public_deployment`, `enforced` and now `admin_open` --
        had exactly one caller in the whole repository, and it was a test.
        So the one fact the deployment checklist turns on ("auth.manifest
        reporting admin-open on an internet-reachable origin" is a listed
        rollback trigger) was computed and never reported by the tool whose
        entire purpose is to report it.

        `rate_limit` is here rather than in a tool of its own because it is
        the other half of the same question -- what stops a caller -- and it
        is counts and configuration only, never an address, key or subject.
        """
        manifest = auth.manifest()
        manifest["rate_limit"] = limiter.report(public_deployment=auth.public_deployment)
        return manifest

    def cache_status(_: dict):
        """Describe caching without exposing cache contents.

        Keys are digests of prompts and application state, so neither keys nor
        values appear here.

        `policy` used to be the literals `{"default_ttl_ms": 300000,
        "default_scope": "server"}`, written down rather than derived, while
        the suite enforces the opposite principle elsewhere
        (`test_counts_are_computed_not_written_down`). It is now read from the
        same `CacheConfig` the cache actually uses, so a changed TTL is a
        changed report.
        """
        config = app_cache.config
        return {
            "entries": len(cache.entries),
            "policy": {
                "default_ttl_ms": config.ttl_for(SemanticPlane.PROTOCOL),
                "default_scope": SERVER_SCOPE,
                "ttl_ms_by_plane": {p.value: config.ttl_for(p) for p in SemanticPlane},
                "active": config.active,
            },
            "external_cache_supported": ["redis", "cdn", "host-cache"],
            "application_cache": app_cache.status(),
        }

    def gate_inspect(args: dict):
        """Report what the gate would decide, by asking the gate.

        This returned a dict literal with `"allowed": True` and
        `"semantic_provider": "disabled"` hardcoded. It parsed the address and
        then reimplemented the gate's output rather than calling it, so: the
        `SemanticGateProvider` Protocol had no implementor on this path,
        `GateDecision`'s score/semantic_distance/gate_id/source fields had no
        producer anything read, and a deployment that populated
        `semantic_gate.provider` was told `"disabled"` no matter what it had
        configured. The one tool named for inspecting the gate was the one
        place that never consulted it.
        """
        try:
            address = EnforceableAddress.parse(args.get("scw_address", ""))
        except ValueError as exc:
            # Structural failure. The address never parsed, so there is nothing
            # for a semantic provider to evaluate and no decision was produced.
            return {
                "allowed": False,
                "reason": str(exc),
                "stage": "address",
                "semantic_provider": getattr(semantic_gate, "name", type(semantic_gate).__name__),
            }
        decision = semantic_gate.evaluate(
            address=address.uri(), capability="maxey0-ss.gate.inspect",
            metadata={"tool": "gate.inspect"},
        )
        return {
            **decision.__dict__,
            "address": address.uri(),
            "stage": "semantic",
            "mode": "structural-public-gate",
            "semantic_provider": getattr(semantic_gate, "name", type(semantic_gate).__name__),
        }

    def observe_window(args: dict):
        return observer.observe(args.get("segments", []))

    def create_scw(args: dict):
        scw_id = args.get("scw_id", "SCW0")
        task = args.get("task", "Maxey0 SuperSpace task")
        concept = args.get("concept", "Task")
        parent_id = args.get("parent_id")
        if scw_id in system.context.graph.scw_specs:
            raise ValueError(f"SCW specification already exists: {scw_id}")
        spec = deploy_default_scw(task, scw_id=scw_id, parent_id=parent_id, concept=concept)
        system.create_scw(spec)
        return spec.__dict__

    def describe_scws(_: dict):
        return system.context.snapshot()["scw_instances"] | {
            "specifications": {
                k: {
                    "parent_id": v.parent_id,
                    "concept": v.concept,
                    "skills": v.skills,
                    "drift_threshold": v.drift_threshold,
                }
                for k, v in system.context.graph.scw_specs.items()
            }
        }

    def close_scw(args: dict):
        scw_id = args.get("scw_id")
        if not isinstance(scw_id, str) or not scw_id:
            raise ValueError("scw_id is required")
        if scw_id in system.context.instances:
            system.scw_runtime.stop(scw_id)
            # Dependency-aware invalidation: a reopened identifier must not
            # inherit the closed SCW's cached answers.
            dropped = app_cache.invalidate_scw(scw_id)
            return {"closed": scw_id, "kind": "instance", "cache_entries_dropped": dropped}
        if scw_id in system.context.graph.scw_specs:
            return {
                "closed": False,
                "scw_id": scw_id,
                "kind": "specification",
                "reason": "Only instantiated SCWs can be closed.",
            }
        raise ValueError(f"Unknown SCW: {scw_id}")

    def start_scw(args: dict):
        """Instantiate a specification on this system's SCW runtime.

        The owner is the authenticated caller -- the subject the transport set
        with `owned_by` -- and never an argument, so a caller cannot start a
        window in somebody else's name. "local" is an in-process call with no
        transport around it.
        """
        scw_id = args.get("scw_id")
        if not isinstance(scw_id, str) or not scw_id:
            raise ValueError("scw_id is required")
        return start_instance(system, scw_id, _OWNER.get() or "local", app_cache)

    def app_artifact(_: dict):
        return super_space_artifact()

    def deployment(_: dict):
        """Report which provider sockets are configured, and which are inert.

        The gap between `configured` and `implemented` is the provider boundary:
        credentials can be supplied for a provider this build does not yet use,
        and this is where that is visible instead of silent.

        Two kinds of socket, reported together because a deployer needs one
        answer. `storage` names backends this build records and does not call.
        `models` names the three it does call -- and separates "no credential"
        from "a credential that is still the template", which every truthiness
        check in the world reports identically.
        """
        base = _deployment_settings().public_manifest()
        base["models"] = providers_manifest(log=system.context.isolation.log)
        base["rate_limit"] = limiter.summary()
        # Read-only here: the bounds come from the environment at system
        # construction, and no tool takes an argument that could widen them.
        base["root_bounds"] = system.root_bounds.as_dict()
        return base

    def provider_complete(args: dict):
        """Send a prompt to a model provider, gated and attested.

        The egress is described, admitted by the semantic gate, and written to
        the hash-chained log before a byte leaves -- refusals included. The
        prompt itself is digested, never recorded: the containment record is
        published through `evidence.attestations`, and a published record
        carrying prompts would be a published record of user data.
        """
        name = args.get("provider")
        if name not in providers:
            raise ValueError(
                f"unknown provider {name!r}; this build has "
                f"{', '.join(sorted(providers))}"
            )
        prompt = args.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt is required")
        provider = providers[name]
        kwargs: dict[str, object] = {}
        for key in ("model", "system", "max_tokens", "temperature", "scw_id"):
            if args.get(key) is not None:
                kwargs[key] = args[key]
        early = args.get("async", False)
        if not isinstance(early, bool):
            raise ValueError("async must be a boolean")

        # A model round-trip is the one genuinely long-running thing on this
        # surface, so it is the one that raises a task. SEP-2663 removed
        # per-request opt-in: a caller does not ask for a task, it receives one.
        task = task_store.create(
            tool_name="maxey0-ss.provider.complete",
            scw_address=args.get("scw_id"),
            status_message=f"egress to {name}",
        )
        if early:
            # Opt-in early return: the handle goes back while the task is still
            # WORKING and `tasks/get` delivers the result. Without it a caller
            # whose client times out before the model answers could only wait.
            _TASK_WORKERS.submit(_run_complete, task.task_id, provider, prompt, kwargs, name)
            return {"ok": True, "pending": True, "provider": name,
                    "task": task_store.get(task.task_id).as_result(
                        result_type="task")}
        try:
            result = provider.complete(prompt, **kwargs)
        except ProviderRefused as exc:
            task_store.fail(task.task_id, {"code": -32003, "message": str(exc)},
                            message="refused by the gate")
            return {"ok": False, "refused": True, "reason": str(exc),
                    "provider": name,
                    "task": task_store.get(task.task_id).as_result(
                        result_type="complete")}
        except ProviderError as exc:
            # A missing or placeholder credential is a configuration answer, not
            # a crash. -32603 "Tool execution failed" would send the caller
            # looking for a bug in this server.
            task_store.fail(task.task_id, {"code": -32004, "message": str(exc)},
                            message="provider not configured")
            return {"ok": False, "refused": False, "reason": str(exc),
                    "provider": name,
                    "hint": "call maxey0-ss.deployment to see which providers "
                            "are configured",
                    "task": task_store.get(task.task_id).as_result(
                        result_type="complete")}
        payload = result.as_dict()
        task_store.complete(task.task_id, payload, message="egress completed")
        # `resultType: "complete"` -- a terminal payload attached, which is the
        # second of the two shapes SEP-2663 defines. The first, a handle
        # returned before the work finishes, needs a job runner this build does
        # not have, so it is not claimed. What this does give a caller is a
        # durable handle: the result stays fetchable by `tasks/get` for its TTL,
        # which is what makes a timed-out client recoverable rather than lost.
        return {"ok": True, **payload,
                "task": task_store.get(task.task_id).as_result(
                    result_type="complete")}

    def _run_complete(task_id, provider, prompt, kwargs, name):
        """Worker body for an early-return task. Terminal state only via the store."""
        try:
            try:
                result = provider.complete(prompt, **kwargs)
            except ProviderRefused as exc:
                task_store.fail(task_id, {"code": -32003, "message": str(exc)},
                                message="refused by the gate")
            except ProviderError as exc:
                task_store.fail(task_id, {"code": -32004, "message": str(exc)},
                                message="provider not configured")
            except Exception as exc:  # noqa: BLE001 - a worker must not die silently
                task_store.fail(task_id, {"code": -32603, "message": type(exc).__name__},
                                message=f"egress to {name} failed")
            else:
                task_store.complete(task_id, result.as_dict(), message="egress completed")
        except TaskError:
            # Canceled or expired while the egress was in flight; the caller
            # already has a terminal answer and this result has nowhere to go.
            pass

    def provider_status(_: dict):
        """Which providers are callable, which are inert, and why."""
        return providers_manifest(log=system.context.isolation.log)

    def _attestations() -> AttestationLog:
        return system.context.isolation.log

    def evidence_summary(_: dict):
        """Counts and chain head. Discloses no mechanism."""
        return _attestations().summary()

    def evidence_attestations(args: dict):
        """The containment record: what was attempted, where, when, and the outcome.

        Published deliberately. A containment claim that cannot be inspected is
        not a claim, and these records disclose the decision, not the algorithm.
        """
        log = _attestations()
        full = log.export()
        records = log.denials() if args.get("denials_only") else full
        limit = _clamp_limit(args.get("limit"))
        window = records[-limit:] if limit else []
        # A slice is only verifiable against the entry before it, so the anchor
        # travels with the evidence. Without it every exported view failed
        # verification, because the verifier assumed a chain starting at GENESIS.
        by_digest = {r.get("digest"): i for i, r in enumerate(full)}
        if window and not args.get("denials_only"):
            first = window[0]
            anchor = first.get("prev_digest", GENESIS)
            start_seq = first.get("seq", 0)
            contiguous = True
        else:
            anchor, start_seq, contiguous = GENESIS, 0, not bool(window)
        return {
            "attestations": window,
            "total": len(log),
            "head": log.head,
            "anchor_prev_digest": anchor,
            "start_seq": start_seq,
            # A denials-only view is a filter, not a segment: the entries are not
            # adjacent, so it cannot be chain-verified. Saying so is better than
            # handing back something that will be reported as broken.
            "chain_verifiable": contiguous,
        }

    def evidence_verify(args: dict):
        """Verify exported records handed in by the caller.

        Records are required. With no argument this used to verify the *live*
        log and return its entry count and chain head — the same facts
        `evidence.summary` gates behind OBSERVE_READ — from a tool declared
        public. Third-party verification is the public capability; reading this
        system's chain is not.
        """
        records = args.get("records")
        if not isinstance(records, list) or not records:
            return {
                "ok": False,
                "error": "records is required",
                "detail": (
                    "Pass the 'attestations' array from maxey0-ss.evidence.attestations, "
                    "with its 'anchor_prev_digest' and 'start_seq'. Verifying this "
                    "system's live chain requires the observe capability."
                ),
            }
        # Caller-supplied input on a public tool: malformed shapes used to raise
        # inside the hashing code and surface as an HTTP 500 carrying the
        # exception text. Refuse them as input errors instead, and bound the
        # hashing work one anonymous request can demand.
        if len(records) > MAX_VERIFY_RECORDS:
            return {"ok": False, "error": f"at most {MAX_VERIFY_RECORDS} records per call"}
        if not all(isinstance(record, dict) for record in records):
            return {"ok": False, "error": "every record must be an object"}
        anchor = args.get("anchor_prev_digest") or GENESIS
        if not isinstance(anchor, str):
            return {"ok": False, "error": "anchor_prev_digest must be a string"}
        start_seq = args.get("start_seq") or 0
        if isinstance(start_seq, bool) or not isinstance(start_seq, int) or start_seq < 0:
            return {"ok": False, "error": "start_seq must be a non-negative integer"}
        expected_head = args.get("expected_head")
        if expected_head is not None and not isinstance(expected_head, str):
            return {"ok": False, "error": "expected_head must be a string"}
        expected_entries = args.get("expected_entries")
        if expected_entries is not None and (
            isinstance(expected_entries, bool) or not isinstance(expected_entries, int)
            or expected_entries < 0
        ):
            return {"ok": False, "error": "expected_entries must be a non-negative integer"}
        # Without these a truncated chain verified clean: any prefix of a valid
        # chain is valid. The verifier supported both; the tool never passed them.
        try:
            result = AttestationLog.verify_records(
                records, expected_prev=anchor, start_seq=start_seq,
                expected_head=expected_head, expected_entries=expected_entries,
            )
        except (AttributeError, TypeError, ValueError):
            return {"ok": False, "error": "records are not attestation records"}
        return result.as_dict()

    def tasks_status(_: dict):
        """Describe the MCP Tasks extension state without exposing task payloads.

        Purges first. `purge_expired` had no caller, so a TTL that every task
        carried and every `as_result` reported was never enforced: the store
        grew without bound and `by_status` counted tasks that had expired hours
        earlier. A TTL nothing applies is a number in a payload.
        """
        expired = task_store.purge_expired()
        return {**task_store.status_summary(), "purged_on_read": expired}

    def scw_drift(args: dict):
        """Anchor or measure semantic drift for one SCW.

        `SemanticRuntime` is a complete drift implementation — anchored
        baselines, cosine distance, `UnanchoredWindow` raised rather than
        answering 0.0 — and until 0.2.0 nothing in any transport called it, so
        `SCWSpec.drift_threshold` was the declared input to an engine with no
        caller. Both ends of that wire are connected here: the threshold
        defaults to the spec's own `drift_threshold`, and `inspect` finally has
        a way to be reached.

        `anchor=true` installs a baseline. Measuring against an un-anchored
        window is refused rather than answered, because with no baseline there
        is nothing to measure against and reporting 0.0 would call an
        arbitrarily drifted window healthy.
        """
        scw_id = args.get("scw_id")
        if not isinstance(scw_id, str) or not scw_id:
            raise ValueError("scw_id is required")
        vector = args.get("vector")
        if not isinstance(vector, list) or not vector:
            raise ValueError("vector is required and must be a non-empty array")
        try:
            vector = [float(v) for v in vector]
        except (TypeError, ValueError) as exc:
            raise ValueError(f"vector must contain numbers: {exc}") from exc
        # float() accepts "nan", "inf" and "1e400". Refuse them here, before
        # anchor() stores anything, rather than let a NaN distance report a
        # drifted window as healthy and then fail the JSON response.
        vector = validate_vector(vector)

        spec = system.context.graph.scw_specs.get(scw_id)
        if spec is None:
            raise ValueError(f"Unknown SCW specification: {scw_id}")

        # Authorized as a write before this handler ran; see `_drift_capability`.
        if _drift_anchors(args):
            drift_runtime.anchor(scw_id, vector)
            return {
                "scw_id": scw_id, "anchored": True,
                "dimension": len(vector),
                "threshold": spec.drift_threshold,
            }

        raw = args.get("threshold")
        threshold = validate_threshold(spec.drift_threshold if raw is None else float(raw))
        try:
            record = drift_runtime.inspect(scw_id, vector, threshold)
        except UnanchoredWindow as exc:
            return {
                "scw_id": scw_id, "anchored": False, "drifted": None,
                "reason": str(exc),
                "threshold_source": "spec" if raw is None else "argument",
                "threshold": threshold,
            }
        return {
            **record.__dict__,
            "anchored": True,
            "threshold_source": "spec" if raw is None else "argument",
        }

    app_meta = {
        "ui": {"resourceUri": SUPER_SPACE_URI},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    }
    tools = [
        Tool("maxey0-ss.health", "Return service and protocol health.", {"type": "object", "properties": {}}, health),
        Tool("maxey0-ss.distribution", "Describe the public Maxey0 planes and delivery surfaces.", {"type": "object", "properties": {}}, distribution),
        Tool("maxey0-ss.auth.manifest", "Describe authorization configuration without exposing credentials.", {"type": "object", "properties": {}}, auth_manifest),
        Tool("maxey0-ss.cache.status", "Describe Maxey0 MCP metadata caching without exposing cache contents.", {"type": "object", "properties": {}}, cache_status),
        Tool("maxey0-ss.app.artifact", "Identify the SuperSpace MCP App artifact actually being served.", {"type": "object", "properties": {}}, app_artifact),
        Tool("maxey0-ss.evidence.summary", "Containment evidence counts and chain head.", {"type": "object", "properties": {}}, evidence_summary, capability=OBSERVE_READ),
        Tool("maxey0-ss.evidence.attestations", "The containment record: what was attempted across SCW boundaries, and the outcome.", {"type": "object", "properties": {"denials_only": {"type": "boolean"}, "limit": {"type": "integer"}}}, evidence_attestations, capability=OBSERVE_READ),
        Tool("maxey0-ss.evidence.verify", "Verify the containment chain. Pass exported records to verify evidence from elsewhere.", {"type": "object", "properties": {"records": {"type": "array"}, "anchor_prev_digest": {"type": "string"}, "start_seq": {"type": "integer"}, "expected_head": {"type": "string", "description": "Chain head the records must end at; detects entries removed from the end."}, "expected_entries": {"type": "integer", "minimum": 0, "description": "Number of records expected; detects truncation."}}, "required": ["records"]}, evidence_verify),
        Tool("maxey0-ss.deployment", "Report deployment shape and provider sockets without exposing any secret value.", {"type": "object", "properties": {}}, deployment),
        Tool("maxey0-ss.tasks.status", "Describe MCP Tasks extension state without exposing task payloads.", {"type": "object", "properties": {}}, tasks_status),
        Tool("maxey0-ss.gate.inspect", "Validate an explicit Maxey0 SCW enforceable address.", {"type": "object", "properties": {"scw_address": {"type": "string"}}, "required": ["scw_address"]}, gate_inspect),
        Tool("maxey0-ss.super_space", "Open the Maxey0-SuperSpace MCP App.", {"type": "object", "properties": {}}, lambda _: {"app": SUPER_SPACE_URI}, app_meta),
        Tool("maxey0-ss.scw.create", "Create an explicit Maxey0 SCW specification without creating a protocol session.", {"type": "object", "properties": {"scw_id": {"type": "string"}, "task": {"type": "string"}, "concept": {"type": "string"}, "parent_id": {"type": "string"}}, "required": ["scw_id", "task"]}, create_scw, capability=SCW_CREATE),
        Tool("maxey0-ss.scw.describe", "Describe Maxey0 SCW specifications and instantiated SCWs.", {"type": "object", "properties": {}}, describe_scws, capability=SCW_READ),
        Tool("maxey0-ss.scw.start", "Instantiate an SCW specification on the SCW runtime, owned by the caller.", {"type": "object", "properties": {"scw_id": {"type": "string"}}, "required": ["scw_id"]}, start_scw, capability=SCW_ADMIT),
        Tool("maxey0-ss.scw.close", "Close an instantiated Maxey0 SCW by explicit application identifier.", {"type": "object", "properties": {"scw_id": {"type": "string"}}, "required": ["scw_id"]}, close_scw, capability=SCW_ADMIT),
        Tool("maxey0-ss.scw.observe_host_window", "Observe host-supplied context partitions without claiming access to hidden model context.", {"type": "object", "properties": {"scw_address": {"type": "string", "description": "Explicit Maxey0 SCW enforceable address."}, "segments": {"type": "array"}}, "required": ["scw_address", "segments"]}, observe_window, app_meta, True, capability=OBSERVE_READ),
        Tool("maxey0-ss.provider.status", "Report which model providers are configured, which hold a placeholder credential, and which are unset.", {"type": "object", "properties": {}}, provider_status, capability=OBSERVE_READ),
        Tool("maxey0-ss.provider.complete", "Send a prompt to a model provider. The egress is gated and written to the containment chain before it leaves; the prompt is digested, never recorded.", {"type": "object", "properties": {"provider": {"type": "string", "enum": ["anthropic", "openai", "huggingface"]}, "prompt": {"type": "string"}, "model": {"type": "string"}, "system": {"type": "string"}, "max_tokens": {"type": "integer"}, "temperature": {"type": "number"}, "scw_id": {"type": "string", "description": "The window this egress belongs to. Recorded as the source of the call."}, "async": {"type": "boolean", "description": "Return the task handle while it is still working; fetch the result with tasks/get."}}, "required": ["provider", "prompt"]}, provider_complete, capability=SCW_ADMIT),
        Tool("maxey0-ss.scw.drift", "Anchor or measure semantic drift for one SCW against its declared threshold. Measuring requires scw.read; anchor=true installs a baseline and also requires scw.admit.", {"type": "object", "properties": {"scw_id": {"type": "string"}, "vector": {"type": "array", "items": {"type": "number"}}, "anchor": {"type": "boolean", "description": "Install this vector as the baseline instead of measuring against one. Requires scw.admit."}, "threshold": {"type": "number", "description": "Overrides the SCW specification's drift_threshold."}}, "required": ["scw_id", "vector"]}, scw_drift, capability=SCW_READ, argument_capability=_drift_capability),
    ]

    # The engineering-observation plane. Implemented in server/planes/ and,
    # until now, reachable from no transport we ship.
    tools.extend(observability_tools())

    _wire_cache(tools, app_cache)

    resources = [
        Resource(SUPER_SPACE_URI, "Maxey0-SuperSpace", "Interactive SCW host-window observer.", "text/html;profile=mcp-app", super_space_html, {"ui": {"prefersBorder": True}}),
        Resource("maxey0-ss://super-space/host-window", "SuperSpace host-window contract", "Contract for host-visible context partition metadata.", "application/json", lambda: {"scope": "host-supplied", "hidden_model_context_access": False}),
        Resource("maxey0-ss://architecture/planes", "Maxey0 planes", "Context, execution, engineering/observation plane model.", "application/json", lambda: distribution({})["planes"]),
    ]
    return Surface(tools=tools, resources=resources, cache=cache, system=system,
                   app_cache=app_cache, tasks=task_store, authorizer=auth,
                   rate_limiter=limiter)
