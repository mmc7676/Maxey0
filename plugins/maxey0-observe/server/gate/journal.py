"""The gate's own hash-chained log, and why it is not the runtime's.

The obvious thing to do is append gate records to `~/.scw/events.jsonl` next to
the runtime's. That was measured, and it destroys the log.

`scw_runtime.events.EventLog` starts every writer at `seq = 0` with
`prev = GENESIS`, and `verify_records` resets its expectations at every
`run_id` boundary. Two processes appending to one file therefore produce a
sequence that can never verify again: the record bytes stay individually valid
while the file as a whole is permanently broken. `split_runs` partitions on
*consecutive* `run_id`, so an interleaved file also shatters each run into
fragments, and `replay` — which takes the last fragment and requires it to open
with `window.init` — fails outright. The Studio's live mirror returns `ok:
false` from that point on.

Worse, `EventLog`'s `run_id` counter is a per-process global, so two processes
starting in the same millisecond mint the *same* run id and the corruption
becomes invisible instead of loud. A gate hook is a short-lived process spawned
once per tool call, hundreds of times a session. This is not a rare race.

So the gate gets its own stream, and the two are bound rather than merged:

* **Own chain.** Single-writer per file is the only property that makes a hash
  chain mean anything, and each record carries a ``stream`` id built from the
  pid and a random suffix so two gate processes can never collide.
* **Anchored to the runtime run.** Each gate record records the runtime log's
  head — its ``run_id`` and record count at the time of writing — so a gate
  stream can be shown to belong to a particular run instead of merely sitting
  next to it. This copies the ``prev_run`` back-link the runtime already uses.
* **Locked.** The runtime has no locking, no `fsync`, and no append atomicity;
  records in the real logs on this machine already exceed the 8 KB buffer, so a
  multi-syscall write can be torn by a concurrent writer. Since the gate is by
  construction many concurrent short-lived writers, it takes an exclusive lock
  around every append.
* **Read defensively.** `scw_runtime.events.iter_records` calls bare
  `json.loads` and dies on a torn line with a `JSONDecodeError` that is not an
  `SCWError` and so escapes every handler above it. This reader skips a
  malformed line and *counts* it, because a dropped record is a gap in the
  evidence and the count is what makes the gap visible.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Iterator, Optional

try:  # imported as `gate.journal` by hooks, or top-level by some tools
    from .privacy import redact
except ImportError:  # pragma: no cover
    from privacy import redact  # type: ignore[no-redef]

GENESIS = "0" * 64

#: Bumped when the record body shape changes incompatibly.
JOURNAL_VERSION = 1

#: The gate's event vocabulary. Deliberately disjoint from the runtime's
#: `EVENT_TYPES` — these describe an *interception*, not a runtime operation,
#: and conflating the two would let a reader mistake "the gate saw an attempt"
#: for "the runtime enforced a boundary". They are different claims.
GATE_EVENT_TYPES: tuple[str, ...] = (
    "gate.attempt",      # a tool call was intercepted
    "gate.allowed",      # evaluated and in scope
    "gate.denied",       # evaluated and refused
    "gate.observed",     # recorded without a decision (observe mode, host, unattributed)
    "gate.fail_open",    # the gate could not evaluate and let it through anyway
    "gate.actor_start",  # a delegated actor began
    "gate.actor_stop",   # a delegated actor finished
    "gate.policy",       # a role policy was declared
    "gate.error",        # the gate itself failed
)


def _digest(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def journal_path() -> Path:
    """Where the gate stream lives. Never the runtime's log — see the module docstring."""
    override = os.environ.get("MAXEY0_GATE_LOG")
    if override:
        path = Path(override)
    else:
        home = Path(os.environ.get("SCW_HOME") or (Path.home() / ".scw"))
        path = home / "gate.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# an exclusive append lock that works on both platforms
# ---------------------------------------------------------------------------


class _FileLock:
    """Exclusive lock on a sidecar file, held only for the duration of an append.

    Sidecar rather than the journal itself because Windows' `msvcrt.locking`
    locks a byte range from the current offset, and taking that on a file being
    appended to is fiddly in a way a lock has no business being.

    A lock that cannot be acquired is *not* an error: the gate must never break
    a session. It gives up after a short spin and the caller writes anyway,
    recording that it did so, because a possibly-torn record that announces the
    risk is better evidence than a dropped one that does not.
    """

    def __init__(self, target: Path, timeout: float = 2.0) -> None:
        self.path = target.with_suffix(target.suffix + ".lock")
        self.timeout = timeout
        self._fh = None
        self.acquired = False

    def __enter__(self) -> "_FileLock":
        deadline = time.time() + self.timeout
        try:
            self._fh = self.path.open("a+b")
        except Exception:  # noqa: BLE001
            return self
        while time.time() < deadline:
            try:
                if os.name == "nt":
                    import msvcrt
                    self._fh.seek(0)
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.acquired = True
                return self
            except OSError:
                time.sleep(0.005)
            except Exception:  # noqa: BLE001 - platform module missing, etc.
                return self
        return self

    def __exit__(self, *exc: Any) -> None:
        if self._fh is None:
            return
        try:
            if self.acquired:
                if os.name == "nt":
                    import msvcrt
                    self._fh.seek(0)
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        except Exception:  # noqa: BLE001
            pass
        try:
            self._fh.close()
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# writing
# ---------------------------------------------------------------------------


def _stream_id() -> str:
    """A writer identity that cannot collide.

    The runtime's `run_id` counter is a per-process global and two processes
    starting in the same millisecond mint the same id. Since the gate is many
    short-lived processes, the pid and a random suffix are both required.
    """
    return f"gate-{os.getpid()}-{uuid.uuid4().hex[:8]}"


#: The anchor is a pointer to the runtime run, not a measurement of it, so it
#: is computed once per process and reused. The first version recomputed it on
#: every `emit` by reading and counting the whole runtime log -- an O(file)
#: scan on the hot path, paid once per tool call, against a file that is 5 MB
#: on the machine this was written on. Besides being slow, the contention it
#: created was enough to push the append lock past its timeout and drop a
#: record from the chain roughly one run in six.
_ANCHOR_CACHE: dict[str, dict] = {}


def _tail_line(path: Path, window: int = 65_536) -> Optional[str]:
    """The last non-empty line, read from the end rather than by scanning.

    A gate record only needs the runtime's *latest* identity, and seeking to
    the end costs the same whether the log holds a hundred records or a
    million.
    """
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            fh.seek(max(0, size - window))
            chunk = fh.read().decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return None
    lines = [line for line in chunk.splitlines() if line.strip()]
    return lines[-1] if lines else None


def _runtime_anchor() -> dict:
    """The runtime log's head, so a gate record can be tied to a runtime run.

    Read with no chain verification: this is a *pointer*, and verifying a chain
    on the hot path would be paid on every tool call to add nothing. Whether
    the runtime chain verifies is a separate question, asked separately.
    """
    override = os.environ.get("SCW_EVENT_LOG")
    path = Path(override) if override else (Path.home() / ".scw" / "events.jsonl")
    key = str(path)
    if key in _ANCHOR_CACHE:
        return _ANCHOR_CACHE[key]

    anchor: dict = {"run_id": None, "log": key}
    last = _tail_line(path) if path.exists() else None
    if last:
        try:
            parsed = json.loads(last)
            anchor["run_id"] = parsed.get("run_id")
            anchor["digest"] = parsed.get("digest")
            anchor["at_seq"] = parsed.get("seq")
        except Exception:  # noqa: BLE001 - a torn tail is not fatal here
            pass
    _ANCHOR_CACHE[key] = anchor
    return anchor


def _tail_chain(path: Path) -> tuple[int, str]:
    """The last record's ``(seq, digest)`` for this stream, or genesis.

    The gate chains per *file*, not per process, so a stream restarted by a new
    hook process continues the file's chain rather than resetting it to zero —
    which is exactly the reset that destroys the runtime log when two writers
    share a file.
    """
    if not path.exists():
        return 0, GENESIS
    # Read backwards from the end rather than scanning the whole file. This runs
    # inside the exclusive lock on every append, so an O(file) scan here is paid
    # by every concurrent hook process and grows with the journal -- the same
    # contention that was removed from the anchor path for the same reason.
    last_chained = None
    try:
        size = path.stat().st_size
        window = 65_536
        while True:
            start = max(0, size - window)
            with path.open("rb") as fh:
                fh.seek(start)
                chunk = fh.read().decode("utf-8", errors="replace")
            lines = chunk.splitlines()
            # A window that does not begin at byte 0 almost certainly cuts its
            # first line in half; drop it rather than parse a fragment.
            if start > 0 and lines:
                lines = lines[1:]
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                except Exception:  # noqa: BLE001 - torn or partial line
                    continue
                # Records that took no place in the chain carry seq=None on
                # purpose; treating one as the tail would link the next record
                # to a position never claimed.
                if parsed.get("seq") is None:
                    continue
                last_chained = parsed
                break
            if last_chained is not None or start == 0:
                break
            window *= 4
    except Exception:  # noqa: BLE001
        return 0, GENESIS
    if not last_chained:
        return 0, GENESIS
    try:
        return int(last_chained["seq"]) + 1, last_chained.get("digest", GENESIS)
    except (TypeError, ValueError, KeyError):
        return 0, GENESIS


def emit(event_type: str, payload: dict, actor: str = "gate",
         path: Optional[Path] = None) -> dict:
    """Append one gate record. Never raises.

    A gate that crashes must not break a session, so every failure path here
    returns a record marked ``persisted: False`` rather than propagating. The
    caller reports that as a fail-open, because a record the gate believes it
    wrote and did not is the one thing worse than no record at all.
    """
    target = path or journal_path()
    record = {
        "v": JOURNAL_VERSION,
        "stream": _stream_id(),
        "type": event_type if event_type in GATE_EVENT_TYPES else "gate.error",
        "actor": actor,
        "ts": time.time(),
        "pid": os.getpid(),
        # Redacted here, at the one point every gate record passes through:
        # home paths, transcript paths and secret-shaped values never reach
        # disk. Decisions were already made on the real values.
        "anchor": redact(_runtime_anchor()),
        "payload": redact(payload),
    }
    if event_type not in GATE_EVENT_TYPES:
        record["payload"] = {"unknown_type": event_type, "original": payload}

    try:
        with _FileLock(target) as lock:
            record["locked"] = lock.acquired
            if lock.acquired:
                seq, prev = _tail_chain(target)
                record["seq"] = seq
                record["prev"] = prev
            else:
                # Without the lock, two writers can read the same tail and mint
                # the same `seq`, which shows up later as a hole in the chain and
                # discredits records that were in fact written correctly. So an
                # unlocked write takes NO position in the chain: it is still
                # recorded -- losing the observation would be worse -- but it is
                # reported as residue rather than pretending to a place in the
                # sequence it cannot have earned.
                record["seq"] = None
                record["prev"] = None
                record["chain_skipped"] = True
            record["digest"] = _digest(record)
            with target.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                fh.flush()
        record["persisted"] = True
    except Exception as exc:  # noqa: BLE001
        record["persisted"] = False
        record["write_error"] = f"{type(exc).__name__}: {exc}"
    return record


# ---------------------------------------------------------------------------
# reading
# ---------------------------------------------------------------------------


def iter_records(path: Optional[Path] = None) -> Iterator[dict]:
    """Every parseable record, skipping torn lines rather than dying on one.

    Use :func:`read_all` when the count of skipped lines matters, which is
    whenever a containment figure is being computed over the result.
    """
    for record, _ in _iter_with_damage(path):
        yield record


def _iter_with_damage(path: Optional[Path] = None) -> Iterator[tuple[dict, bool]]:
    target = path or journal_path()
    if not target.exists():
        return
    try:
        with target.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line), False
                except Exception:  # noqa: BLE001
                    yield {}, True
    except Exception:  # noqa: BLE001
        return


def read_all(path: Optional[Path] = None) -> dict:
    """Records plus the damage report.

    ``damaged`` is not diagnostic noise. A torn line is a tool call whose record
    was lost, so any containment claim over this stream is missing that many
    observations and has to say so.
    """
    records: list[dict] = []
    damaged = 0
    for record, is_damaged in _iter_with_damage(path):
        if is_damaged:
            damaged += 1
        else:
            records.append(record)
    # Returned to observe tools and shown to callers: never the username.
    return {"records": records, "damaged": damaged,
            "path": redact(str(path or journal_path()))}


def verify(records: list[dict], damaged: int = 0) -> dict:
    """Check the chain in file order.

    **The file is the chain, not the process.** A gate hook is a new OS process
    per tool call, so chaining per writer would give every chain exactly one
    record and prove nothing. Instead each append takes the exclusive lock,
    reads the file's own tail, and links to it — which makes the file
    single-writer-at-a-time even though it has many writers over its life.
    ``stream`` is therefore *provenance* (which process wrote this record), not
    a chain key.

    That is the opposite of the runtime's arrangement, and deliberately so: the
    runtime gives each process its own ``seq`` counter starting at zero, which
    is exactly what makes two runtime writers destroy a shared file.

    A gap or a bad link is reported with the seq it happened at rather than
    raising, because a damaged tail should still let the intact prefix be read —
    the alternative is that one torn line makes an entire run's evidence
    unreadable.
    """
    # Records written without the lock took no position in the chain (see
    # `emit`). They are counted as residue, never as a gap.
    chained = [r for r in records if r.get("seq") is not None]
    skipped = len(records) - len(chained)

    ordered = sorted(chained, key=lambda r: r.get("seq", 0))
    broken: list[dict] = []
    prev = GENESIS
    expected = 0
    for record in ordered:
        seq = record.get("seq")
        if seq != expected:
            broken.append({"seq": seq, "expected": expected, "why": "sequence gap"})
            break
        if record.get("prev") != prev:
            broken.append({"seq": seq, "why": "broken link"})
            break
        body = {k: v for k, v in record.items()
                if k not in ("digest", "persisted", "write_error")}
        if _digest(body) != record.get("digest"):
            broken.append({"seq": seq, "why": "digest mismatch"})
            break
        prev = record.get("digest", GENESIS)
        expected += 1

    return {
        # A torn tail leaves a wholly consistent prefix, so the chain alone
        # cannot see it: read_all() counts the damage and verify() must be told,
        # or a caller reading `ok` calls a lossy stream intact.
        "ok": (not broken) and damaged == 0,
        "chain_intact": not broken,
        "damaged": damaged,
        "records": len(records),
        "chained": len(chained),
        "writers": len({r.get("stream") for r in records}),
        "verified_prefix": expected,
        "broken": broken,
        "unlocked_writes": skipped,
        "note": "; ".join(filter(None, [
            (f"{skipped} record(s) were written without the append lock and hold "
             "no place in the chain; they are residue, not evidence" if skipped else ""),
            (f"{damaged} line(s) were unparseable and are simply lost" if damaged else ""),
        ])),
    }
