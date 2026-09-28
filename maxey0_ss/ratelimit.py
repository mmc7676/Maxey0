"""Origin-side rate limiting and request caps.

Every door on the origin -- stateless ``POST /mcp``, ``/mcp/session``, ``/v1`` --
answered as fast as a caller could send. Nothing counted: not requests per
client, not bearer guesses, not sessions opened, not request bytes. The edge
Worker performs no authorization by design and forwards ``authorization``
verbatim, so every limit that matters has to hold at the origin, where the
credential is actually checked.

What this module owns:

- `RateLimitConfig` -- the variables, read once, with a default for every one.
- `TokenBuckets` -- one keyed family of token buckets, bounded in memory.
- `RateLimiter` -- the per-app state: four bucket families, the trusted-proxy
  rule that decides who a client *is*, and the counters `auth.manifest` reports.
- `RateLimitMiddleware` -- the pure-ASGI layer `api/app.py` runs outermost.

Scope is one process. Buckets live in memory and reset on restart. That is the
deployment's limit only because the origin is one uvicorn process on one
host; a second worker or host would multiply every number here, and the manifest says
"per-process" so nobody reads it as a global guarantee.

`MAXEY0_RATE_LIMIT_STORE=sqlite:<path>` swaps the in-memory buckets for
`SQLiteTokenBuckets`: state in one SQLite file, so it survives a restart
(a crash loop no longer hands every caller a fresh bucket) and is shared by
every process on the host that names the same file. It is still not shared
across hosts. Empty or `memory` keeps the in-memory default.

The limiter itself is standard library only; the middleware borrows
starlette's threadpool to resolve credentials off the event loop.
"""
from __future__ import annotations

import inspect
import ipaddress
import json
import math
import os
import sqlite3
import threading
import time
from collections import OrderedDict
from dataclasses import asdict, dataclass
from typing import Any, Awaitable, Callable, MutableMapping

from starlette.concurrency import run_in_threadpool

from .auth.config import normalize_mode
from .auth.policy import AuthError, is_public_deployment

ENABLED_VAR = "MAXEY0_RATE_LIMIT_ENABLED"
IP_PER_MIN_VAR = "MAXEY0_RATE_LIMIT_IP_PER_MIN"
PRINCIPAL_PER_MIN_VAR = "MAXEY0_RATE_LIMIT_PRINCIPAL_PER_MIN"
SESSION_OPEN_PER_MIN_VAR = "MAXEY0_RATE_LIMIT_SESSION_OPEN_PER_MIN"
AUTH_FAILURES_PER_HOUR_VAR = "MAXEY0_RATE_LIMIT_AUTH_FAILURES_PER_HOUR"
MAX_KEYS_VAR = "MAXEY0_RATE_LIMIT_MAX_KEYS"
STORE_VAR = "MAXEY0_RATE_LIMIT_STORE"
TRUSTED_PROXIES_VAR = "MAXEY0_TRUSTED_PROXY_IPS"
MAX_REQUEST_BYTES_VAR = "MAXEY0_MAX_REQUEST_BYTES"
SESSION_MAX_VAR = "MAXEY0_SESSION_MAX"
SESSION_IDLE_TIMEOUT_VAR = "MAXEY0_SESSION_IDLE_TIMEOUT_S"

#: The four bucket families, named the way a 429 names the limit it hit.
IP = "ip"
PRINCIPAL = "principal"
SESSION_OPEN = "session_open"
AUTH_FAILURES = "auth_failures"
NAMESPACES = (IP, PRINCIPAL, SESSION_OPEN, AUTH_FAILURES)

#: Set by Cloudflare on tunnel traffic to the connecting client's address,
#: replacing any value the client sent. Believed only from a trusted peer.
CLIENT_IP_HEADER = "cf-connecting-ip"
#: What `public_server.main` passes to uvicorn, and so what the manifest
#: reports. uvicorn's default (True) rewrites `scope["client"]` from
#: X-Forwarded-For before any middleware runs, which erases the one fact the
#: trust rule below depends on: which peer actually connected.
UVICORN_PROXY_HEADERS = False
#: JSON-RPC code for a rate-limited request. -32001..-32004 are taken by the
#: authorization and gate refusals; -32010/-32011 by the edge.
RATE_LIMITED_CODE = -32005
SCOPE = "per-process, in-memory, resets on restart"
SQLITE_SCOPE = "per-host, sqlite, survives restart"

#: The one route that authenticates with its own shared secret rather than the
#: Authorizer. Its failures are counted from the response instead.
A2A_PATH = "/v1/a2a/message"
#: The session transport's mount. A request reaches the SDK's session manager
#: only under this prefix: `/mcp/session` without the slash is answered with a
#: 307 by the router and opens nothing.
SESSION_PREFIX = "/mcp/session/"
#: Methods whose body is read and capped. GET (the SSE stream) and DELETE
#: (session teardown) carry none and must reach the SDK untouched.
_BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})

_TRUE = frozenset({"1", "true", "on", "yes"})
_FALSE = frozenset({"0", "false", "off", "no"})
_LOOPBACK = ("127.0.0.1/32", "::1/128")


# ---------------------------------------------------------------------------
# configuration
# ---------------------------------------------------------------------------


def _raw(name: str) -> str:
    return os.getenv(name, "").strip()


def _positive_int(name: str, default: int, invalid: list[str]) -> int:
    """A positive integer, or the default.

    Zero and negatives are refused along with garbage: a per-minute limit of 0
    refuses every request, and a negative one is not a limit. Either would take
    the origin down from a typo, so the default applies and the variable is
    named under `invalid_settings` instead.
    """
    raw = _raw(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        invalid.append(name)
        return default
    if value <= 0:
        invalid.append(name)
        return default
    return value


def _positive_seconds(name: str, default: float, invalid: list[str]) -> float:
    raw = _raw(name)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        invalid.append(name)
        return default
    if not math.isfinite(value) or value <= 0:
        invalid.append(name)
        return default
    return value


def _network(value: str) -> ipaddress.IPv4Network | ipaddress.IPv6Network:
    """An address or CIDR as a network, IPv4-mapped IPv6 folded to IPv4."""
    net = ipaddress.ip_network(value.strip(), strict=False)
    if isinstance(net, ipaddress.IPv6Network) and net.prefixlen >= 96:
        mapped = net.network_address.ipv4_mapped
        if mapped is not None:
            return ipaddress.IPv4Network((mapped, net.prefixlen - 96))
    return net


def _trusted_proxies(invalid: list[str]) -> tuple[str, ...]:
    """The trusted peers, or loopback.

    All or nothing. Dropping the entry that failed to parse and keeping the
    rest can leave the list empty, and an empty list trusts nobody: every
    tunnel request would then be keyed by cloudflared's own loopback address,
    one bucket for the whole internet. A value with any bad entry is treated as
    unparseable, and the default -- where cloudflared actually connects from --
    applies.
    """
    raw = _raw(TRUSTED_PROXIES_VAR)
    entries = [e for e in (p.strip() for p in raw.split(",")) if e]
    if not entries:
        return _LOOPBACK
    try:
        return tuple(str(_network(e)) for e in entries)
    except ValueError:
        invalid.append(TRUSTED_PROXIES_VAR)
        return _LOOPBACK


def _store(invalid: list[str]) -> str:
    """The bucket store. Anything unrecognized falls back to memory and is
    reported, like every other variable here: limits keep being enforced."""
    raw = _raw(STORE_VAR)
    if raw.lower() in {"", "memory"}:
        return "memory"
    if raw.startswith("sqlite:") and raw[len("sqlite:"):].strip():
        return "sqlite:" + raw[len("sqlite:"):].strip()
    invalid.append(STORE_VAR)
    return "memory"


@dataclass(frozen=True)
class RateLimitConfig:
    """Everything in `.env.example`'s rate limiting block, resolved.

    Empty means the default, and so does a value that does not parse. That is
    deliberately not `cache.config._flag`, which reads empty as False: under
    that rule an empty `MAXEY0_RATE_LIMIT_ENABLED=` line -- exactly what
    `.env.example` ships -- would switch the limiter off on a public origin.
    """

    enabled: bool = False
    #: "env" when MAXEY0_RATE_LIMIT_ENABLED decided, "auto" when the
    #: deployment's posture did.
    source: str = "auto"
    ip_per_min: int = 120
    principal_per_min: int = 300
    session_open_per_min: int = 6
    auth_failures_per_hour: int = 20
    #: Bound on tracked keys in EACH bucket family. Past it the least recently
    #: seen key is evicted, so memory is bounded however many addresses call.
    max_keys: int = 10000
    trusted_proxies: tuple[str, ...] = _LOOPBACK
    max_request_bytes: int = 1048576
    session_max: int = 50
    session_idle_timeout_s: float = 600.0
    #: "memory", or "sqlite:<path>" from MAXEY0_RATE_LIMIT_STORE.
    store: str = "memory"
    #: Variables that were set to something unusable and fell back. Names only.
    invalid: tuple[str, ...] = ()

    @property
    def sqlite_path(self) -> str | None:
        return self.store[len("sqlite:"):] if self.store.startswith("sqlite:") else None

    @classmethod
    def from_env(cls) -> "RateLimitConfig":
        invalid: list[str] = []
        switch = _raw(ENABLED_VAR).lower()
        if switch in _TRUE:
            enabled, source = True, "env"
        elif switch in _FALSE:
            enabled, source = False, "env"
        else:
            if switch:
                invalid.append(ENABLED_VAR)
            # On wherever a caller can be somebody other than the operator:
            # an internet-reachable deployment, or any configured auth mode
            # (a misspelt one included -- it is not `disabled`). Off only for
            # the trusted-local default, where every caller is the operator
            # and the suite hammers endpoints from one client.
            enabled = (is_public_deployment()
                       or normalize_mode(os.getenv("MAXEY0_AUTH_MODE")) != "disabled")
            source = "auto"
        defaults = cls()
        return cls(
            enabled=enabled,
            source=source,
            ip_per_min=_positive_int(IP_PER_MIN_VAR, defaults.ip_per_min, invalid),
            principal_per_min=_positive_int(
                PRINCIPAL_PER_MIN_VAR, defaults.principal_per_min, invalid),
            session_open_per_min=_positive_int(
                SESSION_OPEN_PER_MIN_VAR, defaults.session_open_per_min, invalid),
            auth_failures_per_hour=_positive_int(
                AUTH_FAILURES_PER_HOUR_VAR, defaults.auth_failures_per_hour, invalid),
            max_keys=_positive_int(MAX_KEYS_VAR, defaults.max_keys, invalid),
            trusted_proxies=_trusted_proxies(invalid),
            max_request_bytes=_positive_int(
                MAX_REQUEST_BYTES_VAR, defaults.max_request_bytes, invalid),
            session_max=_positive_int(SESSION_MAX_VAR, defaults.session_max, invalid),
            session_idle_timeout_s=_positive_seconds(
                SESSION_IDLE_TIMEOUT_VAR, defaults.session_idle_timeout_s, invalid),
            store=_store(invalid),
            invalid=tuple(invalid),
        )

    def as_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["trusted_proxies"] = list(self.trusted_proxies)
        out["invalid"] = list(self.invalid)
        return out


# ---------------------------------------------------------------------------
# buckets
# ---------------------------------------------------------------------------


class TokenBuckets:
    """A keyed family of token buckets, bounded by `max_keys`.

    Each key holds `[tokens, stamp]`. Tokens refill continuously at
    `capacity / period_s` per second and are brought up to date on every
    read, so there is no timer and nothing to sweep. A key read is moved to
    the end of the order; inserting one past `max_keys` evicts the least
    recently seen. Without the bound, one caller rotating source addresses (an
    IPv6 /48 has 65,536 of the /64s this keys on) grows the table without end.

    The lock is a `threading.Lock`, not an asyncio one, so a bucket admits
    exactly its capacity whichever thread asks -- the event loop today, a
    threadpool handler if one ever charges a bucket. The critical section
    never awaits, so holding it on the loop costs no more than the arithmetic.
    """

    def __init__(self, capacity: int, period_s: float, max_keys: int,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.capacity = float(capacity)
        self.rate = capacity / period_s
        self.max_keys = max_keys
        self._clock = clock
        self._lock = threading.Lock()
        self._buckets: OrderedDict[str, list[float]] = OrderedDict()
        self.evictions = 0

    def __len__(self) -> int:
        return len(self._buckets)

    def check(self, key: str, cost: float = 1, consume: bool = True) -> float:
        """0.0 if `cost` tokens are available (taken when `consume`), else the
        seconds until they will be.

        A peek (`consume=False`) never inserts a key: an unseen key has a full
        bucket, and answering that needs no entry. Otherwise the lockout check
        every request makes would fill the table with keys that have never
        been charged, and evict the ones that have.
        """
        with self._lock:
            now = self._clock()
            entry = self._buckets.get(key)
            if entry is None:
                tokens = self.capacity
                if consume:
                    entry = [tokens, now]
                    self._buckets[key] = entry
                    if len(self._buckets) > self.max_keys:
                        self._buckets.popitem(last=False)
                        self.evictions += 1
            else:
                elapsed = max(0.0, now - entry[1])
                tokens = min(self.capacity, entry[0] + elapsed * self.rate)
                entry[0], entry[1] = tokens, now
                self._buckets.move_to_end(key)
            if tokens >= cost:
                if consume and entry is not None:
                    entry[0] = tokens - cost
                return 0.0
            return (cost - tokens) / self.rate


class SQLiteTokenBuckets:
    """`TokenBuckets` with its state in a SQLite file.

    Same refill arithmetic and the same `check` contract, but the clock is
    wall time: `time.monotonic` restarts with the process and is per-process,
    so a stamp written by one process means nothing to the next. Each check is
    one `BEGIN IMMEDIATE` transaction, which takes SQLite's write lock, so two
    processes charging the same key serialize instead of both spending the
    last token. Eviction past `max_keys` drops the least recently seen keys.
    """

    def __init__(self, path: str, family: str, capacity: int, period_s: float,
                 max_keys: int, clock: Callable[[], float] = time.time) -> None:
        self.capacity = float(capacity)
        self.rate = capacity / period_s
        self.max_keys = max_keys
        self.family = family
        self._clock = clock
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, timeout=5.0, isolation_level=None,
                                   check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS buckets (family TEXT NOT NULL, key TEXT NOT NULL,"
            " tokens REAL NOT NULL, stamp REAL NOT NULL, PRIMARY KEY (family, key))")
        self.evictions = 0

    def __len__(self) -> int:
        with self._lock:
            row = self._db.execute("SELECT COUNT(*) FROM buckets WHERE family = ?",
                                   (self.family,)).fetchone()
        return int(row[0])

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def check(self, key: str, cost: float = 1, consume: bool = True) -> float:
        """See `TokenBuckets.check`."""
        with self._lock:
            db = self._db
            db.execute("BEGIN IMMEDIATE")
            try:
                now = self._clock()
                row = db.execute("SELECT tokens, stamp FROM buckets WHERE family = ? AND key = ?",
                                 (self.family, key)).fetchone()
                if row is None:
                    tokens = self.capacity
                else:
                    elapsed = max(0.0, now - row[1])
                    tokens = min(self.capacity, row[0] + elapsed * self.rate)
                allowed = tokens >= cost
                # A peek at an unseen key writes nothing, as in `TokenBuckets`.
                if consume or row is not None:
                    left = tokens - cost if (consume and allowed) else tokens
                    db.execute("INSERT OR REPLACE INTO buckets VALUES (?, ?, ?, ?)",
                               (self.family, key, left, now))
                    if row is None:
                        over = db.execute("SELECT COUNT(*) FROM buckets WHERE family = ?",
                                          (self.family,)).fetchone()[0] - self.max_keys
                        if over > 0:
                            db.execute(
                                "DELETE FROM buckets WHERE rowid IN (SELECT rowid FROM buckets"
                                " WHERE family = ? ORDER BY stamp LIMIT ?)", (self.family, over))
                            self.evictions += over
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise
            return 0.0 if allowed else (cost - tokens) / self.rate


# ---------------------------------------------------------------------------
# who is calling
# ---------------------------------------------------------------------------


def _header(scope: MutableMapping[str, Any], name: bytes) -> str | None:
    """The first value of a header, decoded as Starlette decodes it."""
    for key, value in scope.get("headers") or ():
        if key == name:
            return value.decode("latin-1")
    return None


def _parse_ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        ip = ipaddress.ip_address(value.strip())
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        # ::ffff:203.0.113.7 is 203.0.113.7. Keyed apart, one client would
        # hold two buckets by switching address family on a dual-stack socket.
        return ip.ipv4_mapped
    return ip


def _group(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str:
    """The bucket key for an address: itself for IPv4, its /64 for IPv6.

    One IPv6 subscriber is routinely handed a whole /64, so keying on the full
    address gives that one caller 2**64 buckets.
    """
    if isinstance(ip, ipaddress.IPv6Address):
        return str(ipaddress.IPv6Network((ip, 64), strict=False))
    return str(ip)


# ---------------------------------------------------------------------------
# the limiter
# ---------------------------------------------------------------------------


class RateLimiter:
    """Per-app limiter state, shared by the middleware and the manifest."""

    def __init__(self, config: RateLimitConfig | None = None, *,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.config = config if config is not None else RateLimitConfig.from_env()
        c = self.config
        families = {
            IP: (c.ip_per_min, 60.0),
            PRINCIPAL: (c.principal_per_min, 60.0),
            SESSION_OPEN: (c.session_open_per_min, 60.0),
            AUTH_FAILURES: (c.auth_failures_per_hour, 3600.0),
        }
        path = c.sqlite_path
        self.scope = SQLITE_SCOPE if path else SCOPE
        self.buckets: dict[str, Any] = {
            ns: (SQLiteTokenBuckets(path, ns, cap, period, c.max_keys)
                 if path else TokenBuckets(cap, period, c.max_keys, clock))
            for ns, (cap, period) in families.items()
        }
        self._trusted = tuple(_network(n) for n in c.trusted_proxies)
        self._lock = threading.Lock()
        self._limited = dict.fromkeys(NAMESPACES, 0)
        self._auth_failures_total = 0
        self._too_large = 0
        self._degraded_keying = 0
        #: Set by `RateLimitMiddleware` when it wraps an app. A limiter that is
        #: configured on but wraps nothing -- the stdio transport builds the
        #: same surface -- enforces nothing, and the manifest must say so.
        self.attached = False
        #: What `mcp_session_server.build_session_manager` passed to the SDK.
        self.session_caps: dict[str, dict[str, Any]] | None = None

    # -- identity -----------------------------------------------------------

    def _is_trusted(self, ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
        return any(ip in net for net in self._trusted if net.version == ip.version)

    def _peer(self, scope: MutableMapping[str, Any]) -> tuple[str, Any]:
        client = scope.get("client")
        peer = str(client[0]) if client else ""
        return peer, (_parse_ip(peer) if peer else None)

    def client_key(self, scope: MutableMapping[str, Any]) -> str:
        """Who the bucket keys call this request's client.

        The raw peer, unless the peer is a trusted proxy asserting
        CF-Connecting-IP. Everything through the tunnel arrives from cloudflared
        on loopback, so without the header every client would share one bucket;
        believing the header from any peer would let a client name a fresh
        address per request and never be counted. A header that does not parse
        as an address is ignored rather than used as a key, for the same reason.
        A peer that is not an address at all (TestClient's "testclient") is
        its own key.
        """
        peer, peer_ip = self._peer(scope)
        if peer_ip is not None and self._is_trusted(peer_ip):
            asserted = _header(scope, CLIENT_IP_HEADER.encode())
            if asserted is not None:
                ip = _parse_ip(asserted)
                if ip is not None:
                    return _group(ip)
            # Counted, because this is the case that silently merges clients:
            # every caller behind a proxy that stopped sending the header (or
            # every local caller, when loopback is the trusted default) shares
            # the proxy's buckets, and one of them can exhaust all of theirs.
            with self._lock:
                self._degraded_keying += 1
        if peer_ip is None:
            return peer or "unknown-peer"
        return _group(peer_ip)

    def forwarded_scheme(self, scope: MutableMapping[str, Any]) -> str | None:
        """X-Forwarded-Proto from a trusted peer, the one thing kept from
        uvicorn's proxy handling.

        `proxy_headers=False` stops uvicorn rewriting the client, and also
        stops it setting the scheme. Behind the tunnel every request then looks
        like plain http, and the router's trailing-slash redirect -- which is
        how `/mcp/session` (no trailing slash) reaches the session mount
        -- would send session clients to an http:// Location. Same peers, same
        values uvicorn accepted.
        """
        peer, peer_ip = self._peer(scope)
        if peer_ip is None or not self._is_trusted(peer_ip):
            return None
        proto = _header(scope, b"x-forwarded-proto")
        if proto is None:
            return None
        proto = proto.strip().lower()
        return proto if proto in ("http", "https") else None

    # -- accounting ---------------------------------------------------------

    def record_auth_failure(self, client: str) -> None:
        """Charge one failed credential to `client`.

        Charged per client, and also counted globally. The global number is
        reported and never enforced: a global lockout would let anybody lock
        every legitimate caller out by sending bad tokens.
        """
        self.buckets[AUTH_FAILURES].check(client)
        with self._lock:
            self._auth_failures_total += 1

    def record_refusal(self, namespace: str) -> None:
        with self._lock:
            self._limited[namespace] += 1

    def record_too_large(self) -> None:
        with self._lock:
            self._too_large += 1

    # -- reporting ----------------------------------------------------------

    @property
    def enforced(self) -> bool:
        return self.config.enabled and self.attached

    def _session_caps(self) -> dict[str, dict[str, Any]]:
        if self.session_caps is not None:
            return {k: dict(v) for k, v in self.session_caps.items()}
        return {
            param: {"variable": var, "value": value, "applied": False,
                    "reason": "no session transport was built in this process"}
            for param, var, value in _session_cap_values(self.config)
        }

    def report(self, *, public_deployment: bool) -> dict[str, Any]:
        """The `rate_limit` block of `maxey0-ss.auth.manifest`.

        That tool is public, so this is counts and configuration only: never a
        client address, a bucket key, a subject or a token label. A table of
        who has been refused would be a list of who is calling.
        """
        c = self.config
        with self._lock:
            limited = dict(self._limited)
            auth_failures_total = self._auth_failures_total
            too_large = self._too_large
            degraded_keying = self._degraded_keying
        out: dict[str, Any] = {
            "enabled": c.enabled,
            "source": c.source,
            "enforced": self.enforced,
            "limits": {
                "ip_per_min": c.ip_per_min,
                "principal_per_min": c.principal_per_min,
                "session_open_per_min": c.session_open_per_min,
                "auth_failures_per_hour": c.auth_failures_per_hour,
                "max_keys_per_namespace": c.max_keys,
            },
            "request_caps": {
                "max_request_bytes": c.max_request_bytes,
                "max_request_bytes_enforced": self.enforced,
                "session": self._session_caps(),
            },
            "client_ip": {
                "header": "CF-Connecting-IP",
                "trusted_proxy_count": len(c.trusted_proxies),
                "uvicorn_proxy_headers": UVICORN_PROXY_HEADERS,
            },
            "scope": self.scope,
            "counters": {
                "limited": limited,
                "request_too_large": too_large,
                "auth_failures_total": auth_failures_total,
                "trusted_proxy_without_client_ip": degraded_keying,
                "tracked_keys": {ns: len(b) for ns, b in self.buckets.items()},
                "evictions": {ns: b.evictions for ns, b in self.buckets.items()},
            },
            "invalid_settings": list(c.invalid),
        }
        if public_deployment and not c.enabled:
            out["warning"] = (
                f"{ENABLED_VAR} switches rate limiting and request caps off on "
                f"this public deployment. Nothing limits requests per client, "
                f"bearer guesses, session opens or request size at the origin."
            )
        return out

    def summary(self) -> dict[str, Any]:
        """The short form `maxey0-ss.deployment` carries."""
        return {
            "enabled": self.config.enabled,
            "source": self.config.source,
            "enforced": self.enforced,
            "scope": self.scope,
            "detail": "maxey0-ss.auth.manifest",
        }


def _session_cap_values(config: RateLimitConfig) -> tuple[tuple[str, str, Any], ...]:
    """(SDK parameter, variable, value) for each cap the session manager takes."""
    return (
        ("max_sessions", SESSION_MAX_VAR, config.session_max),
        ("session_idle_timeout", SESSION_IDLE_TIMEOUT_VAR, config.session_idle_timeout_s),
        ("max_request_body_size", MAX_REQUEST_BYTES_VAR, config.max_request_bytes),
    )


def session_manager_caps(
    config: RateLimitConfig, manager_cls: type,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """(kwargs for `manager_cls`, the per-cap report `auth.manifest` shows).

    pyproject accepts mcp>=1.19 and these parameters are newer than that, so
    each is passed only if the installed SDK's constructor takes it -- and a
    cap that could not be passed is reported as not applied, with the reason,
    rather than dropped. A cap that silently is not there reads, from outside,
    exactly like one that is.
    """
    try:
        accepted = set(inspect.signature(manager_cls.__init__).parameters)
    except (TypeError, ValueError):
        accepted = set()
    kwargs: dict[str, Any] = {}
    report: dict[str, dict[str, Any]] = {}
    for param, var, value in _session_cap_values(config):
        entry: dict[str, Any] = {"variable": var, "value": value}
        if not config.enabled:
            entry.update(applied=False, reason=f"{ENABLED_VAR} is off; SDK defaults apply")
        elif param in accepted:
            kwargs[param] = value
            entry["applied"] = True
        else:
            entry.update(applied=False,
                         reason="the installed mcp SDK's session manager does not accept it")
        report[param] = entry
    return kwargs, report


# ---------------------------------------------------------------------------
# the middleware
# ---------------------------------------------------------------------------

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

_DISCONNECTED = object()


def _is_jsonrpc(path: str) -> bool:
    return path == "/mcp" or path.startswith("/mcp/")


async def _respond(send: Send, status: int, payload: dict[str, Any],
                   extra: tuple[tuple[bytes, bytes], ...] = ()) -> None:
    body = json.dumps(payload).encode("utf-8")
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [(b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")), *extra],
    })
    await send({"type": "http.response.body", "body": body})


def _replay(body: bytes, receive: Receive) -> Receive:
    """A receive that yields the buffered body once, then the real channel.

    Delegating afterwards matters: the session transport answers a POST with
    an SSE stream and listens on receive for the disconnect that ends it. A
    replay that returned the body forever would never deliver it.
    """
    delivered = False

    async def replayed() -> Message:
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}
        return await receive()

    return replayed


class RateLimitMiddleware:
    """Pure ASGI rather than `BaseHTTPMiddleware`, because `/mcp/session`
    streams SSE and `BaseHTTPMiddleware` interposes on the response body.

    Runs outermost, so a refusal here costs no routing, no body parsing and no
    credential check downstream. For each http request, in order:

    1. an Authorization header (except on the A2A route) is resolved with the
       app's shared Authorizer, in a worker thread -- an OIDC verifier may
       fetch a key set, and that must not stall the event loop;
    2. unless that credential authenticated, a client locked out by failed
       credentials gets 429; a failing credential is then charged to it;
    3. the client's address bucket, or 429;
    4. a body over `max_request_bytes` gets 413, from Content-Length before
       reading when it is declared, else by reading at most one byte past the
       cap; an accepted body is replayed to the app;
    5. a request reaching the session mount without Mcp-Session-Id opens a
       session, and takes from the session-open bucket, or 429;
    6. a charged request continues, so downstream still answers with its own
       401 or soft error; an authenticated principal takes from its own
       bucket, or 429 -- keyed by role and subject, so one token is one budget
       from every address it is used from;
    7. on the A2A route, a 401 answered to a request that carried a credential
       is charged to the client.

    A request with no Authorization header is never an auth failure: that is
    every anonymous call to a public tool.

    The lockout is keyed by client address, and an address is shared -- a NAT,
    or every caller behind a trusted proxy that omits CF-Connecting-IP. Checked
    before the credential was resolved, it let anyone sharing the address lock
    a valid token holder out by sending bad bearers. A credential that
    authenticates is therefore never locked out: it is limited by its own
    principal bucket instead, which an attacker without the token cannot
    drain. Anonymous requests and failing credentials stay subject to it.
    """

    def __init__(self, app: ASGIApp, *, limiter: RateLimiter, authorizer: Any = None) -> None:
        self.app = app
        self.limiter = limiter
        self.authorizer = authorizer
        limiter.attached = True

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limiter = self.limiter
        # Independent of the switch: public_server turns uvicorn's proxy
        # handling off whether or not anything here is enabled.
        scheme = limiter.forwarded_scheme(scope)
        if scheme is not None and scheme != scope.get("scheme"):
            scope = {**scope, "scheme": scheme}
        if not limiter.config.enabled:
            await self.app(scope, receive, send)
            return

        path = scope.get("path") or ""
        method = scope.get("method") or "GET"
        jsonrpc = _is_jsonrpc(path)
        client = limiter.client_key(scope)

        authorization = _header(scope, b"authorization")
        if authorization is not None and not authorization.strip():
            authorization = None
        principal_key: str | None = None
        failed = False
        if authorization is not None and path != A2A_PATH and self.authorizer is not None:
            principal_key, failed = await run_in_threadpool(self._resolve, authorization)

        if principal_key is None:
            wait = limiter.buckets[AUTH_FAILURES].check(client, consume=False)
            if wait:
                await self._too_many(send, AUTH_FAILURES, wait, jsonrpc)
                return
        if failed:
            limiter.record_auth_failure(client)
        wait = limiter.buckets[IP].check(client)
        if wait:
            await self._too_many(send, IP, wait, jsonrpc)
            return

        if method in _BODY_METHODS:
            body = await self._read_body(scope, receive)
            if body is _DISCONNECTED:
                return
            if body is None:
                await self._too_large(send, jsonrpc)
                return
            receive = _replay(body, receive)

        if path.startswith(SESSION_PREFIX) and _header(scope, b"mcp-session-id") is None:
            # Any method: the SDK admits a session and starts its server task
            # for every request without a session id, before it knows whether
            # the request is an initialize it can accept.
            wait = limiter.buckets[SESSION_OPEN].check(client)
            if wait:
                await self._too_many(send, SESSION_OPEN, wait, jsonrpc)
                return

        if principal_key is not None:
            wait = limiter.buckets[PRINCIPAL].check(principal_key)
            if wait:
                await self._too_many(send, PRINCIPAL, wait, jsonrpc)
                return
        if authorization is not None and path == A2A_PATH:
            send = self._watch_a2a(send, client)

        await self.app(scope, receive, send)

    def _resolve(self, authorization: str) -> tuple[str | None, bool]:
        """(principal bucket key or None, whether the credential failed).

        A key means the credential authenticated. Runs in a worker thread.
        """
        try:
            principal = self.authorizer.principal(authorization)
        except AuthError as exc:
            # -32001 is a credential that was presented and is wrong. -32004
            # is the deployment's own misconfiguration; charging callers for it
            # would lock every one of them out of an origin that is refusing
            # them anyway, and keep them out after the operator fixes it.
            return None, exc.code == -32001
        if not principal.authenticated or self.authorizer.mode == "disabled":
            # `disabled` resolves every caller to the same principal without
            # reading the header, so one bucket would be shared by everybody
            # who sends any Authorization value at all -- and any value at all
            # would buy a way past the lockout.
            return None, False
        return f"{principal.role}\n{principal.subject}", False

    def _watch_a2a(self, send: Send, client: str) -> Send:
        limiter = self.limiter

        async def watched(message: Message) -> None:
            if message.get("type") == "http.response.start" and message.get("status") == 401:
                limiter.record_auth_failure(client)
            await send(message)

        return watched

    async def _read_body(self, scope: Scope, receive: Receive) -> Any:
        """The whole body, None if it exceeds the cap, or _DISCONNECTED."""
        cap = self.limiter.config.max_request_bytes
        declared = _header(scope, b"content-length")
        if declared is not None and declared.strip().isdigit() and int(declared) > cap:
            return None
        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message.get("type") == "http.disconnect":
                return _DISCONNECTED
            chunk = message.get("body", b"") or b""
            size += len(chunk)
            if size > cap:
                return None
            chunks.append(chunk)
            if not message.get("more_body", False):
                return b"".join(chunks)

    async def _too_many(self, send: Send, limit: str, wait: float, jsonrpc: bool) -> None:
        self.limiter.record_refusal(limit)
        retry = max(1, math.ceil(wait))
        data = {"limit": limit, "retry_after_s": retry}
        if jsonrpc:
            payload: dict[str, Any] = {
                "jsonrpc": "2.0", "id": None,
                "error": {"code": RATE_LIMITED_CODE, "message": "Rate limit exceeded",
                          "data": data},
            }
        else:
            payload = {"detail": "rate limit exceeded", **data}
        await _respond(send, 429, payload, ((b"retry-after", str(retry).encode("ascii")),))

    async def _too_large(self, send: Send, jsonrpc: bool) -> None:
        self.limiter.record_too_large()
        cap = self.limiter.config.max_request_bytes
        if jsonrpc:
            payload: dict[str, Any] = {
                "jsonrpc": "2.0", "id": None,
                "error": {"code": -32600, "message": "Request body too large",
                          "data": {"limit_bytes": cap}},
            }
        else:
            payload = {"detail": "request body too large", "limit_bytes": cap}
        await _respond(send, 413, payload)
