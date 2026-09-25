"""Hash-chained JSONL event log.

Every state change in the runtime is emitted here first and applied second, so
the log is a *complete* description of the window rather than a commentary on
it. :mod:`scw_runtime.replay` reconstructs full state from nothing but this
stream, and the inspector UI consumes exactly the same bytes. A test asserts
live state and replayed state are identical, which is what makes the UI
trustworthy.

Record shape (one JSON object per line, no trailing commas, UTF-8)::

    {"seq": 7, "ts": 1761350400.0, "run_id": "run-...", "type": "scw.write",
     "actor": "loop:refine", "payload": {...}, "prev": "<sha256>",
     "digest": "<sha256>"}

``digest = sha256(canonical_json(record_without_digest))`` and ``prev`` is the
previous record's digest, so any edit, reorder, or deletion in the middle of a
log is detectable by :func:`verify_records`.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import os
import time
from pathlib import Path
from typing import Callable, Iterable, Iterator

from .errors import ChainBroken

GENESIS = "0" * 64

# Distinguishes runs started inside the same millisecond, so several runs
# appended to one file always restart the chain at a detectable boundary.
_RUN_COUNTER = itertools.count(1)

# --- event type registry -----------------------------------------------------
# Kept explicit so the UI, the docs and the reducer cannot silently disagree.
EVENT_TYPES = (
    "window.init",       # a new window/run begins; carries budgets + tokenizer
    "window.reset",      # the window was torn down and re-initialized
    "window.seal",       # setup ended; the privileged unbound path closed
    "scw.create",        # a region was created (possibly nested)
    "scw.write",         # content appended/replaced in a region
    "scw.read",          # a region was read (records the reader's scope)
    "scw.denied",        # an operation was refused: isolation or policy
    "scw.evict",         # entries dropped to respect a token budget
    "scw.close",         # a region was sealed
    "scw.purge",         # a region's content was destroyed on close
    "loop.bind",         # a loop's execution scope was bound to a region
    "loop.tick",         # one iteration boundary; carries cache economics
    "loop.unbind",       # the loop released its scope
    "bridge.open",       # an explicit cross-region grant was minted
    "bridge.close",      # a grant was revoked or expired
    "promote",           # content crossed a tier boundary under a gate
    "window.render",     # the window was materialized into prompt text
    "prompt.create",     # a prompt-layer instruction artifact was declared
    "prompt.revise",     # a prompt was edited; version incremented, history kept
    "prompt.render",     # a prompt was materialized against variable bindings
    "harness.create",    # a harness profile (architecture, skills, guardrails) was declared
    "harness.call",      # a loop invoked a named skill under a harness profile
    "criterion.pin",     # a region was frozen as an acceptance criterion, with its signature
    "criterion.unpin",   # a pinned criterion was released by the host
    "evidence.attest",   # external evidence (command, exit code, output digest) was recorded
    "partition.check",   # a maker/judge disjointness decision, allowed or refused
    "route.hit",         # a task matched an existing loop-dataset record; its SCW was bound
    "route.fallback_skill",  # no loop matched; the task was routed to Maxey0 skills instead
    "route.fallback_agent",  # no loop or skill matched; the task was routed to Maxey0 agents instead
)


try:  # imported as `gate.journal` by hooks, or top-level by some tools
    from .privacy import redact
except ImportError:  # pragma: no cover
    from privacy import redact  # type: ignore[no-redef]

def canonical(obj: object) -> str:
    """Stable JSON encoding used for hashing."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(body: dict) -> str:
    return hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()


class EventLog:
    """Append-only event sink.

    Parameters
    ----------
    path:
        Where to append JSONL. ``None`` keeps the log in memory only.
    clock:
        Injectable time source; tests pass a deterministic counter.
    run_id:
        Identifier stamped on every record so several runs can share a file.
    subscriber:
        Optional callback invoked with each record after it is written; used by
        the live-tail server.
    """

    def __init__(
        self,
        path: str | os.PathLike[str] | None = None,
        clock: Callable[[], float] | None = None,
        run_id: str | None = None,
        subscriber: Callable[[dict], None] | None = None,
        prev_run: dict | None = None,
    ) -> None:
        self.path = Path(path) if path is not None else None
        self._clock = clock or time.time
        self._seq = 0
        self._prev = GENESIS
        self.records: list[dict] = []
        self.subscriber = subscriber
        # Back-link to the run this one continues from, when a file holds
        # several. Carried in `window.init` and checked by verify_records under
        # `strict_runs`. Without it the per-run chains float free of each
        # other, and whole runs can be deleted or reordered undetectably.
        self.prev_run = prev_run
        self.run_id = run_id or f"run-{int(self._clock() * 1000):x}-{next(_RUN_COUNTER)}"
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = self.path.open("a", encoding="utf-8")
        else:
            self._fh = None

    # -- writing --------------------------------------------------------
    def emit(self, type: str, actor: str, payload: dict) -> dict:
        """Append one record and return it (including its assigned ``seq``)."""
        if type not in EVENT_TYPES:
            raise ValueError(f"unknown event type {type!r}")
        body = {
            "seq": self._seq,
            "ts": round(float(self._clock()), 6),
            "run_id": self.run_id,
            "type": type,
            "actor": actor,
            # Never persist a home path, transcript path or secret-shaped value.
            "payload": redact(payload),
            "prev": self._prev,
        }
        record = {**body, "digest": _digest(body)}
        self._seq += 1
        self._prev = record["digest"]
        self.records.append(record)
        if self._fh is not None:
            self._fh.write(canonical(record) + "\n")
            self._fh.flush()  # keep `tail -f` and the live UI honest
        if self.subscriber is not None:
            self.subscriber(record)
        return record

    @property
    def next_seq(self) -> int:
        """The ``seq`` the next emitted record will receive."""
        return self._seq

    def head(self) -> dict | None:
        """This run's commitment: its id, its final digest, and its length.

        Hand it to the next :class:`EventLog` appending to the same file as
        ``prev_run``. That is what ties one run's chain to the next, and it is
        the difference between "every run is individually valid" and "this
        file has not had a run removed from it".
        """
        if not self.records:
            return None
        return {"run_id": self.run_id, "digest": self._prev, "length": len(self.records)}

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None

    # -- reading --------------------------------------------------------
    @staticmethod
    def load(path: str | os.PathLike[str]) -> list[dict]:
        return list(iter_records(path))

    def verify(self) -> None:
        verify_records(self.records)


def iter_records(path: str | os.PathLike[str]) -> Iterator[dict]:
    """Yield records from a JSONL log, skipping blank lines."""
    with Path(path).open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def verify_records(records: Iterable[dict], strict_runs: bool = False) -> None:
    """Raise :class:`ChainBroken` if the chain does not validate.

    Checks contiguous ``seq``, that each ``prev`` matches the prior digest, and
    that every digest matches a recomputation of its own body. Chains restart
    at :data:`GENESIS` whenever ``run_id`` changes, so a file holding several
    appended runs still verifies.

    That restart is also a seam. Within a run, any edit, deletion, or reorder
    is detected. *Across* runs it is not: each run's chain is independent, so
    deleting a whole run or reordering runs leaves every remaining block valid.

    ``strict_runs=True`` closes that. Every run after the first must carry a
    ``prev_run`` back-link in its ``window.init`` payload naming the preceding
    run's id, final digest, and length; the link is checked against what was
    actually just read. A deleted or reordered run breaks it.

    One residue is not closable from inside the file: truncating the *last*
    run, or dropping it entirely, leaves a wholly consistent prefix, because
    nothing later refers back to it. Detecting that needs a commitment kept
    somewhere the file cannot reach — record :meth:`EventLog.head` externally
    at the end of a run.
    """
    prev = GENESIS
    expected_seq = 0
    run_id = None
    seen_a_run = False
    last_head: dict | None = None
    length = 0

    for record in records:
        if record.get("run_id") != run_id:
            if seen_a_run:
                last_head = {"run_id": run_id, "digest": prev, "length": length}
            run_id = record.get("run_id")
            prev = GENESIS
            expected_seq = 0
            length = 0
            seen_a_run = True

            if strict_runs and last_head is not None:
                if record.get("type") != "window.init":
                    raise ChainBroken(
                        f"run {run_id!r} does not begin with window.init, so it carries no "
                        f"back-link to the run before it",
                        run_id=run_id,
                    )
                link = record.get("payload", {}).get("prev_run")
                if link is None:
                    raise ChainBroken(
                        f"run {run_id!r} declares no prev_run back-link; the run before it "
                        f"({last_head['run_id']!r}) could have been altered or removed without "
                        f"detection",
                        run_id=run_id,
                        expected=last_head,
                    )
                if link != last_head:
                    raise ChainBroken(
                        f"run {run_id!r} back-links to {link!r}, but the run that actually "
                        f"precedes it is {last_head!r} — a run has been deleted, reordered, "
                        f"or truncated",
                        run_id=run_id,
                        declared=link,
                        actual=last_head,
                    )

        if record.get("seq") != expected_seq:
            raise ChainBroken(
                f"sequence gap: expected {expected_seq}, found {record.get('seq')}",
                seq=record.get("seq"),
            )
        if record.get("prev") != prev:
            raise ChainBroken(f"broken link at seq {record.get('seq')}", seq=record.get("seq"))
        body = {k: v for k, v in record.items() if k != "digest"}
        if _digest(body) != record.get("digest"):
            raise ChainBroken(f"digest mismatch at seq {record.get('seq')}", seq=record.get("seq"))
        prev = record["digest"]
        expected_seq += 1
        length += 1
