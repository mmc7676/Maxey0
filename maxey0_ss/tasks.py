"""MCP Tasks extension (`io.modelcontextprotocol/tasks`, SEP-2663).

Durable state machines for long-running work, polled with `tasks/get` rather
than blocked on. This module is transport-neutral for the same reason
`mcp_surface` is: the HTTP adapter, the stdio server and the edge Worker must
all see one task model, not three.

Maxey0 fit: a task is *application state above the transport*, exactly like an
SCW. The protocol carries a handle; the state lives here.

Wire contract taken from SEP-2663:

- `tasks/get`    params `{taskId}` -> task object with `resultType`
- `tasks/update` params `{taskId, inputResponses}`
- `tasks/cancel` params `{taskId}`
- `subscriptions/listen` params `{notifications: {taskIds: [...]}}`
- statuses: working | input_required | completed | failed | canceled
- `resultType`: "task" (a handle) | "complete" (terminal payload attached)

Servers may return a task handle unsolicited; SEP-2663 removed per-request
opt-in, so a caller does not ask for a task, it receives one.
"""
from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterator

#: Extension identifier declared in server capabilities.
TASKS_EXTENSION = "io.modelcontextprotocol/tasks"

#: Methods this extension adds. Used by every transport to route.
TASK_METHODS = ("tasks/get", "tasks/update", "tasks/cancel")
SUBSCRIBE_METHOD = "subscriptions/listen"
ACK_NOTIFICATION = "notifications/subscriptions/acknowledged"

DEFAULT_TTL_MS = 3_600_000
DEFAULT_POLL_INTERVAL_MS = 5_000

#: The subject of the principal whose call is running, set by a transport
#: around a tool handler. Handlers take only their arguments, so this is how a
#: task raised deep inside one learns who asked for it without every handler
#: growing a principal parameter.
_OWNER: ContextVar[str | None] = ContextVar("maxey0_task_owner", default=None)


@contextmanager
def owned_by(subject: str | None) -> Iterator[None]:
    """Tasks created inside this block belong to `subject`."""
    token = _OWNER.set(subject)
    try:
        yield
    finally:
        _OWNER.reset(token)


class TaskStatus(str, Enum):
    WORKING = "working"
    INPUT_REQUIRED = "input_required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"

    @property
    def terminal(self) -> bool:
        return self in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELED}


class TaskError(ValueError):
    """Raised for an unknown, expired, or illegally-transitioned task."""


def _now_iso(ms: int | None = None) -> str:
    seconds = (ms if ms is not None else int(time.time() * 1000)) / 1000
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(seconds))


@dataclass
class Task:
    task_id: str
    status: TaskStatus
    created_ms: int
    last_updated_ms: int
    ttl_ms: int = DEFAULT_TTL_MS
    poll_interval_ms: int = DEFAULT_POLL_INTERVAL_MS
    status_message: str | None = None
    #: Present only while `status == input_required`.
    input_requests: dict[str, Any] = field(default_factory=dict)
    #: Terminal payload. Attached on completion, surfaced with resultType "complete".
    result: Any = None
    error: dict[str, Any] | None = None
    #: Maxey0 linkage. A task raised by a governed call carries its SCW address,
    #: so task state and application state stay addressable together.
    scw_address: str | None = None
    tool_name: str | None = None
    #: Subject of the principal that created it, or None for a task raised
    #: outside any authenticated call. A task carries its tool's result, and
    #: `observe` -- the capability the task methods demand -- is held by every
    #: viewer, so without an owner any viewer holding a task id could read or
    #: cancel another caller's result. Never serialized.
    owner: str | None = None

    def expired(self, now_ms: int) -> bool:
        return self.ttl_ms > 0 and (now_ms - self.last_updated_ms) >= self.ttl_ms

    def as_result(self, *, result_type: str) -> dict[str, Any]:
        """Serialize to the SEP-2663 wire shape."""
        out: dict[str, Any] = {
            "resultType": result_type,
            "taskId": self.task_id,
            "status": self.status.value,
            "createdAt": _now_iso(self.created_ms),
            "lastUpdatedAt": _now_iso(self.last_updated_ms),
            "ttlMs": self.ttl_ms,
            "pollIntervalMs": self.poll_interval_ms,
        }
        if self.status_message:
            out["statusMessage"] = self.status_message
        if self.status is TaskStatus.INPUT_REQUIRED and self.input_requests:
            out["inputRequests"] = self.input_requests
        if self.status is TaskStatus.COMPLETED and self.result is not None:
            out["result"] = self.result
        if self.status is TaskStatus.FAILED and self.error is not None:
            out["error"] = self.error
        if self.scw_address:
            out.setdefault("_meta", {})["maxey0/scwAddress"] = self.scw_address
        return out


class TaskStore:
    """In-process task registry.

    Deliberately in-memory: task state is application state, and Maxey0 keeps
    application state above the transport rather than in a protocol session.
    A multi-instance deployment needs a shared backend, which is why the edge
    Worker forwards task methods to the origin instead of answering them.
    """

    def __init__(self, *, clock=None) -> None:
        self._clock = clock or (lambda: int(time.time() * 1000))
        self._tasks: dict[str, Task] = {}
        #: taskId -> set of subscriber ids that opted in for status notifications.
        self._subscriptions: dict[str, set[str]] = {}

    # -- lifecycle ----------------------------------------------------------

    def create(
        self,
        *,
        tool_name: str | None = None,
        scw_address: str | None = None,
        status_message: str | None = None,
        ttl_ms: int = DEFAULT_TTL_MS,
        poll_interval_ms: int = DEFAULT_POLL_INTERVAL_MS,
    ) -> Task:
        now = self._clock()
        task = Task(
            task_id=str(uuid.uuid4()),
            status=TaskStatus.WORKING,
            created_ms=now,
            last_updated_ms=now,
            ttl_ms=ttl_ms,
            poll_interval_ms=poll_interval_ms,
            status_message=status_message,
            scw_address=scw_address,
            tool_name=tool_name,
            owner=_OWNER.get(),
        )
        self._tasks[task.task_id] = task
        return task

    def _live(self, task_id: str) -> Task:
        task = self._tasks.get(task_id)
        if task is None:
            raise TaskError(f"Unknown task: {task_id}")
        if task.expired(self._clock()) and not task.status.terminal:
            raise TaskError(f"Task expired: {task_id}")
        return task

    def get(self, task_id: str) -> Task:
        return self._live(task_id)

    def _touch(self, task: Task) -> None:
        task.last_updated_ms = self._clock()

    def require_input(self, task_id: str, input_requests: dict[str, Any], message: str | None = None) -> Task:
        task = self._live(task_id)
        if task.status.terminal:
            raise TaskError(f"Task is already {task.status.value}: {task_id}")
        task.status = TaskStatus.INPUT_REQUIRED
        task.input_requests = input_requests
        task.status_message = message
        self._touch(task)
        return task

    def provide_input(self, task_id: str, input_responses: dict[str, Any]) -> Task:
        """`tasks/update` — client answers an outstanding input request."""
        task = self._live(task_id)
        if task.status is not TaskStatus.INPUT_REQUIRED:
            raise TaskError(
                f"Task is not awaiting input (status={task.status.value}): {task_id}"
            )
        unknown = set(input_responses) - set(task.input_requests)
        if unknown:
            raise TaskError(f"Unrequested input keys: {sorted(unknown)}")
        for key, response in input_responses.items():
            action = (response or {}).get("action")
            if action not in {"accept", "decline", "cancel"}:
                raise TaskError(f"Invalid action for {key!r}: {action!r}")
        if any((r or {}).get("action") == "cancel" for r in input_responses.values()):
            return self.cancel(task_id)
        task.input_requests = {}
        task.status = TaskStatus.WORKING
        task.status_message = None
        self._touch(task)
        return task

    def complete(self, task_id: str, result: Any, message: str | None = None) -> Task:
        task = self._live(task_id)
        if task.status.terminal:
            raise TaskError(f"Task is already {task.status.value}: {task_id}")
        task.status = TaskStatus.COMPLETED
        task.result = result
        task.status_message = message
        self._touch(task)
        return task

    def fail(self, task_id: str, error: dict[str, Any], message: str | None = None) -> Task:
        task = self._live(task_id)
        if task.status.terminal:
            raise TaskError(f"Task is already {task.status.value}: {task_id}")
        task.status = TaskStatus.FAILED
        task.error = error
        task.status_message = message
        self._touch(task)
        return task

    def cancel(self, task_id: str) -> Task:
        task = self._live(task_id)
        if task.status.terminal:
            return task  # canceling a finished task is a no-op, not an error
        task.status = TaskStatus.CANCELED
        task.input_requests = {}
        self._touch(task)
        return task

    # -- subscriptions ------------------------------------------------------

    def listen(self, subscriber: str, task_ids: list[str] | None) -> list[str]:
        """`subscriptions/listen` — opt in per task id.

        Returns only the ids actually accepted, which is what the server echoes
        in `notifications/subscriptions/acknowledged`. An unknown id is declined
        silently rather than failing the whole subscription.
        """
        accepted: list[str] = []
        for task_id in task_ids or []:
            if task_id in self._tasks:
                self._subscriptions.setdefault(task_id, set()).add(subscriber)
                accepted.append(task_id)
        return accepted

    def subscribers(self, task_id: str) -> set[str]:
        return set(self._subscriptions.get(task_id, set()))

    def acknowledgement(self, accepted: list[str]) -> dict[str, Any]:
        return {"method": ACK_NOTIFICATION, "params": {"notifications": {"taskIds": accepted}}}

    # -- reporting ----------------------------------------------------------

    def __len__(self) -> int:
        return len(self._tasks)

    def purge_expired(self) -> int:
        now = self._clock()
        dead = [t.task_id for t in self._tasks.values() if t.expired(now) and not t.status.terminal]
        for task_id in dead:
            del self._tasks[task_id]
            self._subscriptions.pop(task_id, None)
        return len(dead)

    def status_summary(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for task in self._tasks.values():
            counts[task.status.value] = counts.get(task.status.value, 0) + 1
        return {
            "tasks": len(self._tasks),
            "by_status": counts,
            "subscriptions": sum(len(s) for s in self._subscriptions.values()),
            "extension": TASKS_EXTENSION,
        }
