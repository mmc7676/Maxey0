"""``scw`` — command line for the SCW runtime.

    scw serve                     run the MCP server over stdio
    scw demo [--out FILE]         run the reference loop and write an event log
    scw verify LOG                check the hash chain
    scw replay LOG [--json]       rebuild state from the log and print it
    scw inspect LOG               region map, cache ledger, advisories, as text
    scw ui [--log FILE]           serve the inspector (replay + live tail)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

from .errors import SCWError
from .events import iter_records, verify_records
from .replay import replay

BAR = "█"


def enable_unicode_output() -> None:
    """Make stdout/stderr UTF-8.

    Windows consoles default to a legacy code page, which turns the box drawing
    and arrows in this tool's output into a ``UnicodeEncodeError``. Examples
    call this too, so a fresh clone prints correctly on every platform.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):  # pragma: no cover - exotic streams
                pass


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def ui_path() -> Path:
    """Locate ``inspector.html``: env override, installed package, then checkout."""
    override = os.environ.get("SCW_UI")
    if override:
        return Path(override)
    packaged = Path(__file__).with_name("ui") / "inspector.html"
    if packaged.exists():
        return packaged
    checkout = Path(__file__).resolve().parents[2] / "ui" / "inspector.html"
    return checkout


def default_log() -> Path:
    return Path(os.environ.get("SCW_EVENT_LOG") or (Path.home() / ".scw" / "events.jsonl"))


def _fmt(n: int) -> str:
    return f"{n:,}"


def _bar(fraction: float, width: int = 24) -> str:
    filled = max(0, min(width, round(fraction * width)))
    return BAR * filled + "·" * (width - filled)


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------
def cmd_serve(args: argparse.Namespace) -> int:
    try:
        from .server import main as serve_main
    except ImportError:
        print(
            "The MCP server needs the SDK: pip install 'scw-runtime[mcp]'",
            file=sys.stderr,
        )
        return 2
    serve_main()
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    records = list(iter_records(args.log))
    try:
        verify_records(records, strict_runs=args.strict)
    except SCWError as exc:
        print(f"chain INVALID: {exc.message}", file=sys.stderr)
        return 1
    runs = [r for r in records if r.get("type") == "window.init"]
    linked = sum(1 for r in runs if r.get("payload", {}).get("prev_run"))
    names = sorted({r.get("run_id") for r in records})
    print(f"chain OK — {len(records)} events, {len(names)} run(s): {', '.join(map(str, names))}")
    if args.strict:
        print("  strict: every run after the first back-links to its predecessor")
    elif len(names) > 1 and linked < len(names) - 1:
        missing = len(names) - 1 - linked
        print(
            f"  note: {missing} run boundary/ies carry no prev_run back-link.\n"
            f"        Per-run tamper-evidence holds; a whole run could be removed\n"
            f"        or reordered undetectably. Re-run with --strict to require them.",
            file=sys.stderr,
        )
    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    window = replay(list(iter_records(args.log)))
    state = window.inspect(include_content=args.content)
    if args.json:
        print(json.dumps(state, indent=2))
    else:
        _print_state(state)
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    window = replay(list(iter_records(args.log)))
    _print_state(window.inspect())
    return 0


def _print_state(state: dict) -> None:
    meta = state["window"]
    print(f"\n  window {meta['name']!r}  run {meta['run_id']}")
    used = meta["used_tokens"]
    if meta["total_budget"]:
        print(
            f"  {_fmt(used)}/{_fmt(meta['total_budget'])} tokens "
            f"[{_bar(used / meta['total_budget'])}]  tick {meta['tick']}"
        )
    else:
        print(f"  {_fmt(used)} tokens · tick {meta['tick']} · {meta['event_count']} events")
    print(f"  tokenizer {meta['tokenizer']}\n")

    print("  REGIONS")
    for region in state["regions"]:
        indent = "    " + "  " * region["depth"]
        budget = region["policy"]["token_budget"]
        budget_text = f"/{_fmt(budget)}" if budget else ""
        occupants = ",".join(region["occupants"])
        occupied = f"  ◀ {occupants}" if occupants else ""
        print(
            f"{indent}{region['scw_id']:<22} {region['region_type']:<10} "
            f"{region['policy']['mutability']:<8} {region['activity']:<7} "
            f"{_fmt(region['subtree_tokens']):>8}{budget_text} tok{occupied}"
        )

    cache = state["cache"]
    print("\n  CACHE (next tick)")
    print(
        f"    cached {_fmt(cache['cached_tokens'])} · reprocessed "
        f"{_fmt(cache['reprocessed_tokens'])} · hit {cache['cache_hit_ratio']:.0%}"
    )
    print(f"    breakpoint after: {cache['breakpoint_scw_id'] or '(nothing cacheable yet)'}")
    if cache["recoverable_tokens"]:
        print(f"    recoverable by reordering: {_fmt(cache['recoverable_tokens'])} tokens/iteration")

    if state["loops"]:
        print("\n  LOOPS")
        for loop in state["loops"]:
            ledger = loop["ledger"]
            print(
                f"    {loop['loop_id']:<16} -> {loop['scw_id']:<20} "
                f"iter {loop['iteration']:<4} {loop['status']:<10} "
                f"r{loop['reads']} w{loop['writes']} denied {loop['denials']}"
            )
            print(
                f"      ledger: cached {_fmt(ledger['cached_tokens'])} · "
                f"reprocessed {_fmt(ledger['reprocessed_tokens'])} · "
                f"hit {ledger['cache_hit_ratio']:.0%} · "
                f"recoverable {_fmt(ledger['recoverable_tokens'])}"
            )

    open_bridges = [b for b in state["bridges"] if b["status"] == "open"]
    if state["bridges"]:
        print(f"\n  BRIDGES ({len(open_bridges)} open of {len(state['bridges'])})")
        for bridge in state["bridges"]:
            ttl = f"ttl {bridge['ttl_ticks']}" if bridge["ttl_ticks"] else "no ttl"
            print(
                f"    {bridge['bridge_id']:<6} {bridge['from_scw_id']} → {bridge['to_scw_id']} "
                f"[{bridge['mode']}] {bridge['status']:<8} {ttl}  {bridge['reason']}"
            )

    if state["advisories"]:
        print("\n  ADVISORIES")
        for advisory in state["advisories"]:
            mark = {"error": "!!", "warn": " !", "info": "  "}.get(advisory["severity"], "  ")
            print(f"   {mark} [{advisory['code']}] {advisory['message']}")
            print(f"        → {advisory['remedy']}")
    print()


# ---------------------------------------------------------------------------
# inspector server
# ---------------------------------------------------------------------------
class _InspectorHandler(BaseHTTPRequestHandler):
    """Serves the inspector and tails event logs from one directory.

    Bound to loopback only. The ``log`` parameter is restricted to bare
    filenames resolved inside the served directory, so a query cannot walk out
    of it.
    """

    server_version = "scw-inspector"

    def __init__(self, *args, ui_file: Path, log_dir: Path, default_name: str, **kwargs):
        self.ui_file = ui_file
        self.log_dir = log_dir
        self.default_name = default_name
        super().__init__(*args, **kwargs)

    def log_message(self, fmt: str, *args) -> None:  # quieter console
        pass

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: dict, status: int = 200) -> None:
        self._send(status, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8")

    def _resolve(self, name: Optional[str]) -> Optional[Path]:
        candidate = name or self.default_name
        if not candidate or "/" in candidate or "\\" in candidate or candidate.startswith("."):
            return None
        path = (self.log_dir / candidate).resolve()
        if path.parent != self.log_dir.resolve() or path.suffix != ".jsonl":
            return None
        return path

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        if parsed.path in ("/", "/index.html"):
            if not self.ui_file.exists():
                self._send(404, b"inspector.html not found", "text/plain; charset=utf-8")
                return
            self._send(200, self.ui_file.read_bytes(), "text/html; charset=utf-8")
            return

        if parsed.path == "/api/logs":
            logs = []
            for path in sorted(self.log_dir.glob("*.jsonl")):
                stat = path.stat()
                logs.append({"name": path.name, "bytes": stat.st_size, "mtime": stat.st_mtime})
            self._json({"dir": str(self.log_dir), "logs": logs, "default": self.default_name})
            return

        if parsed.path == "/api/events":
            path = self._resolve((query.get("log") or [None])[0])
            if path is None or not path.exists():
                self._json({"error": "log not found"}, status=404)
                return
            start = int((query.get("from") or ["0"])[0])
            records = list(iter_records(path))
            self._json(
                {
                    "log": path.name,
                    "from": start,
                    "total": len(records),
                    "records": records[start:],
                }
            )
            return

        self._send(404, b"not found", "text/plain; charset=utf-8")


def cmd_ui(args: argparse.Namespace) -> int:
    inspector = ui_path()
    if not inspector.exists():
        print(f"inspector.html not found at {inspector}", file=sys.stderr)
        print("Set SCW_UI to its location, or run from a source checkout.", file=sys.stderr)
        return 2

    log = Path(args.log) if args.log else default_log()
    log_dir = log.parent if log.suffix == ".jsonl" else log
    log_dir.mkdir(parents=True, exist_ok=True)
    default_name = log.name if log.suffix == ".jsonl" else ""

    handler = partial(
        _InspectorHandler,
        ui_file=inspector,
        log_dir=log_dir,
        default_name=default_name,
    )
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"SCW inspector  {url}")
    print(f"  serving logs from {log_dir}")
    if default_name:
        print(f"  default log     {default_name}")
    print("  Ctrl-C to stop")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
    return 0


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scw", description=__doc__.split("\n")[0])
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("serve", help="run the MCP server over stdio").set_defaults(func=cmd_serve)

    demo = subparsers.add_parser("demo", help="run the reference loop and write an event log")
    demo.add_argument("--out", default=None, help="event log path (default: ./scw-demo.jsonl)")
    demo.add_argument("--quiet", action="store_true")
    demo.set_defaults(func=_cmd_demo)

    verify = subparsers.add_parser("verify", help="check a log's hash chain")
    verify.add_argument("log")
    verify.add_argument(
        "--strict",
        action="store_true",
        help="also require every run after the first to back-link to its predecessor, "
        "so a deleted or reordered run is detected (not just an edited record)",
    )
    verify.set_defaults(func=cmd_verify)

    rep = subparsers.add_parser("replay", help="rebuild state from a log")
    rep.add_argument("log")
    rep.add_argument("--json", action="store_true")
    rep.add_argument("--content", action="store_true", help="include region content")
    rep.set_defaults(func=cmd_replay)

    ins = subparsers.add_parser("inspect", help="print a log's final state as text")
    ins.add_argument("log")
    ins.set_defaults(func=cmd_inspect)

    ui = subparsers.add_parser("ui", help="serve the inspector")
    ui.add_argument("--log", default=None, help="event log file, or a directory of them")
    ui.add_argument("--port", type=int, default=7654)
    ui.add_argument("--no-open", action="store_true")
    ui.set_defaults(func=cmd_ui)

    return parser


def _cmd_demo(args: argparse.Namespace) -> int:
    """Run the packaged reference scenario."""
    from .scenarios import retrieval_refine_loop

    out = Path(args.out) if args.out else Path("scw-demo.jsonl")
    if out.exists():
        out.unlink()
    window = retrieval_refine_loop(out)
    if not args.quiet:
        _print_state(window.inspect())
    print(f"  event log: {out}  ({window.log.next_seq} events)")
    print(f"  inspect it: scw ui --log {out}")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    enable_unicode_output()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
