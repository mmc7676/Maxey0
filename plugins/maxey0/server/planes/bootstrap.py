"""Shared start-up for the three plane servers.

Every plane needs the same four things before it can register a tool: the
vendored packages on `sys.path`, the two data-root environment variables set,
the `mcp` dependency confirmed, and — for any plane that opens the ledger —
a failure at that moment reported in words rather than as a traceback the host
swallows.

That last one matters more than it looks. `scw_runtime.server` constructs its
session at *import* time, which creates `~/.scw/` and opens `events.jsonl` for
append. When that fails — a read-only home, a roaming profile lock, antivirus
holding the handle, `SCW_EVENT_LOG` pointed somewhere impossible — the process
dies during import and the host reports `CONNECTION_CLOSED` with nothing else.
The operator then has a server that will not start and no way to find out why.
`open_runtime()` turns that into a named cause and a suggested fix on stderr,
which is where MCP hosts collect diagnostics.
"""

from __future__ import annotations

import os
import sys

try:  # observe/gate tools show paths to callers: never the username
    from gate.privacy import shorten_home
except ImportError:  # pragma: no cover
    def shorten_home(text: str) -> str:  # type: ignore[misc]
        # Degraded, never raw: still hide the current user's home.
        home = os.path.expanduser("~")
        return text.replace(home, "~") if home and home != "~" else text

from pathlib import Path
from typing import Any

SERVER_DIR = Path(__file__).resolve().parent.parent
VENDOR_DIR = SERVER_DIR / "vendor"
PLUGIN_ROOT = SERVER_DIR.parent


#: Packages this plugin vendors and must load from its own tree.
VENDORED = ("scw_runtime", "d4", "loopkit")


def _drop_editable_finders() -> list[str]:
    """Stop an editable install elsewhere on the machine from shadowing the vendored runtime.

    `server/vendor/` exists so the plugin installs standalone, and
    `scripts/sync_vendor.py` is the only thing allowed to write it. A developer
    with `pip install -e` of the same runtime breaks that guarantee in a way
    ordinary path ordering cannot fix: modern editable installs register a
    `MetaPathFinder`, and `sys.meta_path` is consulted **before** `sys.path`, so
    prepending the vendored directory does not win. The plugin then silently
    runs code that is not the code it shipped, and a drift check that passes
    proves nothing.

    So the finders are removed, unless `SCW_RUNTIME_SRC` is set — that variable
    is the supported way to say "use my checkout on purpose", and it is
    honored. Returns what was dropped, so `/maxey0:doctor` can report it rather
    than changing the import graph silently.
    """
    if os.environ.get("SCW_RUNTIME_SRC"):
        return []

    dropped: list[str] = []
    for finder in list(sys.meta_path):
        name = getattr(finder, "__name__", type(finder).__name__)
        if "editable" not in name.lower():
            continue
        mapping = getattr(finder, "MAPPING", None)
        if isinstance(mapping, dict) and any(pkg in mapping for pkg in VENDORED):
            sys.meta_path.remove(finder)
            dropped.append(f"{name}({', '.join(sorted(mapping))})")
    return dropped


#: Editable-install finders removed at start-up, reported by `/maxey0:doctor`.
SHADOWED: list[str] = []


def prepare() -> None:
    """Put the vendored packages on the path and pin the data roots.

    Both must happen before anything that reads them is imported, so this is
    called at module scope in each plane entry point, not inside `main()`.
    """
    global SHADOWED
    SHADOWED = _drop_editable_finders()

    for extra in (str(VENDOR_DIR), str(SERVER_DIR)):
        if extra not in sys.path:
            sys.path.insert(0, extra)

    os.environ.setdefault("MAXEY0_ROOT", str(VENDOR_DIR / "maxey0"))
    os.environ.setdefault("MAXEY0_LOOPS", str(VENDOR_DIR / "data" / "loops.json"))


def provenance() -> dict:
    """Where the runtime this process is actually running came from.

    Reported rather than assumed. "The vendored copy" is a claim about the
    import system, and the import system is exactly what an editable install
    elsewhere on the machine changes.
    """
    try:
        import scw_runtime
    except ImportError as exc:
        return {"loaded": False, "error": str(exc)}

    path = Path(scw_runtime.__file__).resolve()
    vendored = VENDOR_DIR.resolve() in path.parents
    return {
        "loaded": True,
        "path": shorten_home(str(path)),
        "vendored": vendored,
        "override": os.environ.get("SCW_RUNTIME_SRC"),
        "shadowing_finders_removed": SHADOWED,
        "note": None if vendored else
                "The runtime did NOT load from server/vendor/. Set "
                "SCW_RUNTIME_SRC deliberately, or uninstall the editable "
                "package, so what runs is what ships.",
    }


def require_mcp(connector: str) -> None:
    """Confirm the one third-party dependency, in words the operator can act on."""
    from _preflight import require  # noqa: PLC0415 - after prepare() only

    require("mcp", component=f"The `{connector}` connector")


def ledger_path() -> Path:
    """Where the Context plane's hash-chained ledger lives."""
    return Path(os.environ.get("SCW_EVENT_LOG") or (Path.home() / ".scw" / "events.jsonl"))


def open_runtime() -> Any:
    """Import the SCW runtime server module, reporting a start-up failure clearly.

    Returns the module. Only the Context plane calls this — it is the plane
    that owns the live window, and the only one that may write the ledger.
    """
    try:
        from scw_runtime import server as runtime  # noqa: PLC0415
    except (OSError, PermissionError) as exc:
        path = ledger_path()
        sys.stderr.write(
            "\n"
            "The `maxey0-context` connector could not open its ledger.\n"
            f"\n    path:  {path}\n    cause: {exc}\n\n"
            "The Context plane appends every decision to a hash-chained ledger,\n"
            "and it opens that file while starting rather than on first use, so\n"
            "a run can never be half-recorded. The file above could not be\n"
            "created or opened.\n\n"
            "Point it somewhere writable and restart:\n\n"
            "    setx SCW_EVENT_LOG \"%USERPROFILE%\\maxey0\\events.jsonl\"   (Windows)\n"
            "    export SCW_EVENT_LOG=\"$HOME/maxey0/events.jsonl\"          (macOS, Linux)\n\n"
            "The Loop plane needs no ledger and starts regardless; the\n"
            "Observatory reads this file when it exists and reports it as\n"
            "missing when it does not.\n\n"
        )
        raise SystemExit(1) from exc
    return runtime


def read_ledger(limit: int | None = None) -> tuple[list[dict], dict]:
    """Read the Context plane's ledger from disk, without a window.

    This is what lets the Observatory see the Context plane across a process
    boundary: the ledger is JSONL on disk, so evidence about a run survives the
    process that produced it and does not require that process to be running.

    Returns the records and a status block naming what was actually read, so a
    caller can tell an empty ledger from an absent one. Those are different
    claims and the product refuses to collapse them.
    """
    from scw_runtime.events import iter_records  # noqa: PLC0415

    path = ledger_path()
    if not path.exists():
        return [], {
            "ledger": shorten_home(str(path)),
            "present": False,
            "records": 0,
            "note": "No ledger on disk. Nothing has been recorded at this path — "
                    "which establishes nothing either way about containment.",
        }

    records = list(iter_records(path))
    if limit is not None and len(records) > limit:
        records = records[-limit:]
    return records, {
        "ledger": shorten_home(str(path)),
        "present": True,
        "records": len(records),
    }


def register(mcp: Any, tool: Any, fn: Any) -> None:
    """Register one catalog entry onto a plane's server under its canonical name.

    The function object is the vendored implementation, unchanged. Renaming
    happens here and only here, so there is one implementation of each tool in
    this codebase and the lexicon is a property of the surface rather than a
    fork of the engine.
    """
    doc = (fn.__doc__ or "").strip()
    detail = f"{tool.summary}\n\n{doc}" if doc else tool.summary
    mcp.add_tool(fn, name=tool.name, description=detail)
