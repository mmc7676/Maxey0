"""MCP Tasks extension (SEP-2663) — state machine and wire contract.

The capability `io.modelcontextprotocol/tasks` is advertised by every transport,
so these tests exist to keep that advertisement true.
"""
import pytest
from fastapi.testclient import TestClient

from maxey0_ss.api.app import create_app
from maxey0_ss.tasks import TaskError, TaskStatus, TaskStore

V = "2026-07-28"


def headers(method: str, name: str = "") -> dict:
    h = {"MCP-Protocol-Version": V, "Mcp-Method": method}
    if name:
        h["Mcp-Name"] = name
    return h


def rpc(client, method, params=None, name=""):
    return client.post(
        "/mcp",
        headers=headers(method, name),
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
    )


# --- state machine ----------------------------------------------------------


def test_a_new_task_starts_working():
    task = TaskStore().create(tool_name="maxey0-ss.scw.create")
    assert task.status is TaskStatus.WORKING
    assert task.task_id


def test_the_wire_shape_matches_sep_2663():
    store = TaskStore()
    task = store.create(status_message="in progress")
    body = task.as_result(result_type="task")
    for key in ("resultType", "taskId", "status", "createdAt", "lastUpdatedAt", "ttlMs", "pollIntervalMs"):
        assert key in body, key
    assert body["resultType"] == "task"
    assert body["createdAt"].endswith("Z")


def test_a_terminal_task_reports_resultType_complete():
    store = TaskStore()
    task = store.create()
    store.complete(task.task_id, {"ok": True})
    assert store.get(task.task_id).status.terminal
    assert store.get(task.task_id).as_result(result_type="complete")["result"] == {"ok": True}


def test_input_required_carries_its_requests_and_clears_on_answer():
    store = TaskStore()
    task = store.create()
    store.require_input(task.task_id, {"name": {"type": "string"}})
    assert store.get(task.task_id).as_result(result_type="task")["inputRequests"]

    store.provide_input(task.task_id, {"name": {"action": "accept", "content": {"input": "Luca"}}})
    refreshed = store.get(task.task_id)
    assert refreshed.status is TaskStatus.WORKING
    assert "inputRequests" not in refreshed.as_result(result_type="task")


def test_update_is_refused_when_no_input_was_requested():
    store = TaskStore()
    task = store.create()
    with pytest.raises(TaskError, match="not awaiting input"):
        store.provide_input(task.task_id, {"name": {"action": "accept"}})


def test_update_refuses_keys_that_were_never_requested():
    store = TaskStore()
    task = store.create()
    store.require_input(task.task_id, {"name": {}})
    with pytest.raises(TaskError, match="Unrequested input keys"):
        store.provide_input(task.task_id, {"unexpected": {"action": "accept"}})


def test_a_cancel_action_cancels_the_task():
    store = TaskStore()
    task = store.create()
    store.require_input(task.task_id, {"name": {}})
    store.provide_input(task.task_id, {"name": {"action": "cancel"}})
    assert store.get(task.task_id).status is TaskStatus.CANCELED


def test_a_terminal_task_cannot_be_completed_twice():
    store = TaskStore()
    task = store.create()
    store.complete(task.task_id, {"first": True})
    with pytest.raises(TaskError, match="already completed"):
        store.complete(task.task_id, {"second": True})


def test_canceling_a_finished_task_is_a_no_op():
    store = TaskStore()
    task = store.create()
    store.complete(task.task_id, {})
    assert store.cancel(task.task_id).status is TaskStatus.COMPLETED


def test_a_task_expires_after_its_ttl():
    now = {"t": 1_000_000}
    store = TaskStore(clock=lambda: now["t"])
    task = store.create(ttl_ms=1_000)
    now["t"] += 1_001
    with pytest.raises(TaskError, match="expired"):
        store.get(task.task_id)


def test_subscriptions_accept_known_ids_and_decline_unknown_ones():
    store = TaskStore()
    task = store.create()
    accepted = store.listen("client-1", [task.task_id, "does-not-exist"])
    assert accepted == [task.task_id]
    assert store.acknowledgement(accepted)["method"] == "notifications/subscriptions/acknowledged"


# --- HTTP transport ---------------------------------------------------------


def test_the_tasks_extension_is_advertised():
    c = TestClient(create_app())
    body = rpc(c, "server/discover").json()
    assert "io.modelcontextprotocol/tasks" in body["result"]["capabilities"]["extensions"]


def test_task_methods_require_the_mcp_name_header():
    c = TestClient(create_app())
    r = c.post(
        "/mcp",
        headers={"MCP-Protocol-Version": V, "Mcp-Method": "tasks/get"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tasks/get", "params": {"taskId": "x"}},
    )
    assert r.status_code == 400
    assert "Mcp-Name" in r.json()["error"]["message"]


def test_mcp_name_must_equal_the_task_id():
    """SEP-2663 routing rule: intermediaries route on Mcp-Name."""
    c = TestClient(create_app())
    r = rpc(c, "tasks/get", {"taskId": "abc"}, name="not-abc")
    assert r.status_code == 400
    assert "must equal params.taskId" in r.json()["error"]["message"]


def test_an_unknown_task_is_reported_not_invented():
    c = TestClient(create_app())
    r = rpc(c, "tasks/get", {"taskId": "nope"}, name="nope")
    assert r.status_code == 404
    assert "Unknown task" in r.json()["error"]["message"]
    assert "result" not in r.json()


def test_tasks_get_requires_a_task_id():
    c = TestClient(create_app())
    r = rpc(c, "tasks/get", {}, name="anything")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == -32602


def test_subscriptions_listen_acknowledges_accepted_ids():
    c = TestClient(create_app())
    r = rpc(c, "subscriptions/listen", {"notifications": {"taskIds": ["unknown"]}})
    assert r.status_code == 200
    body = r.json()["result"]
    assert body["notifications"]["taskIds"] == []
    assert body["acknowledgement"] == "notifications/subscriptions/acknowledged"


def test_the_full_lifecycle_over_http():
    """Create out of band, then drive it entirely through the wire."""
    app = create_app()
    c = TestClient(app)
    store = app.state.maxey0_surface.tasks
    task = store.create(tool_name="maxey0-ss.scw.create")
    tid = task.task_id

    body = rpc(c, "tasks/get", {"taskId": tid}, name=tid).json()["result"]
    assert body["status"] == "working" and body["resultType"] == "task"

    store.require_input(tid, {"confirm": {"type": "boolean"}})
    body = rpc(c, "tasks/get", {"taskId": tid}, name=tid).json()["result"]
    assert body["status"] == "input_required" and "inputRequests" in body

    body = rpc(c, "tasks/update",
               {"taskId": tid, "inputResponses": {"confirm": {"action": "accept", "content": {"input": True}}}},
               name=tid).json()["result"]
    assert body["status"] == "working"

    store.complete(tid, {"scw": "SCW0"})
    body = rpc(c, "tasks/get", {"taskId": tid}, name=tid).json()["result"]
    assert body["resultType"] == "complete"
    assert body["result"] == {"scw": "SCW0"}


def test_cancel_over_http_is_terminal():
    app = create_app()
    c = TestClient(app)
    tid = app.state.maxey0_surface.tasks.create().task_id
    body = rpc(c, "tasks/cancel", {"taskId": tid}, name=tid).json()["result"]
    assert body["status"] == "canceled"
    assert body["resultType"] == "complete"


def test_tasks_status_tool_does_not_leak_payloads():
    app = create_app()
    c = TestClient(app)
    store = app.state.maxey0_surface.tasks
    tid = store.create().task_id
    store.complete(tid, {"secret": "do-not-leak"})
    r = rpc(c, "tools/call", {"name": "maxey0-ss.tasks.status", "arguments": {}}, name="maxey0-ss.tasks.status")
    blob = r.text
    assert "do-not-leak" not in blob
    assert r.json()["result"]["structuredContent"]["tasks"] == 1


# ---------------------------------------------------------------------------
# the extension had no producer
# ---------------------------------------------------------------------------


class TestTheExtensionHasAProducer:
    """`io.modelcontextprotocol/tasks` was advertised and unreachable.

    Every transport declared the capability, the edge Worker routed
    `tasks/get|update|cancel`, and `maxey0-ss.tasks.status` reported on the
    store — while `TaskStore.create()` had no caller outside a test. So
    `tasks/get` could only ever answer "unknown task", `status_summary` was
    structurally pinned at zero, and `purge_expired` enforced a TTL that every
    task carried and no code applied.

    That is a *protocol-level* claim another system acts on, which makes it the
    worst place in this build for the pattern.
    """

    def _surface(self):
        from maxey0_ss.mcp_surface import build_surface

        surface = build_surface()
        return surface, {t.name: t for t in surface.tools}

    def test_a_provider_call_raises_a_task(self):
        import os
        from unittest import mock

        surface, tools = self._surface()
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
            out = tools["maxey0-ss.provider.complete"].handler(
                {"provider": "anthropic", "prompt": "hi"})
        assert "task" in out
        assert out["task"]["taskId"]
        assert out["task"]["resultType"] == "complete"

    def test_the_task_is_retrievable_after_the_call(self):
        """The durable handle: a timed-out client is recoverable, not lost."""
        import os
        from unittest import mock

        surface, tools = self._surface()
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
            out = tools["maxey0-ss.provider.complete"].handler(
                {"provider": "anthropic", "prompt": "hi"})
        task = surface.tasks.get(out["task"]["taskId"])
        assert task.tool_name == "maxey0-ss.provider.complete"

    def test_a_refusal_fails_the_task_rather_than_leaving_it_working(self):
        """A task left `working` forever is a task nobody can act on."""
        import os
        from unittest import mock

        surface, tools = self._surface()
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
            out = tools["maxey0-ss.provider.complete"].handler(
                {"provider": "anthropic", "prompt": "hi"})
        assert out["ok"] is False
        assert out["task"]["status"] == "failed"
        assert out["task"]["error"]["message"]

    def test_status_summary_can_now_be_non_zero(self):
        """It was structurally incapable of it."""
        import os
        from unittest import mock

        surface, tools = self._surface()
        assert tools["maxey0-ss.tasks.status"].handler({})["tasks"] == 0
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
            tools["maxey0-ss.provider.complete"].handler(
                {"provider": "anthropic", "prompt": "hi"})
        status = tools["maxey0-ss.tasks.status"].handler({})
        assert status["tasks"] == 1
        assert sum(status["by_status"].values()) == 1

    def test_the_ttl_is_enforced_rather_than_reported(self):
        """`purge_expired` had no caller, so the store grew without bound."""
        from maxey0_ss.tasks import TaskStore

        clock = {"now": 1_000_000}
        store = TaskStore(clock=lambda: clock["now"])
        task = store.create(tool_name="t", ttl_ms=1_000)
        assert len(store) == 1
        clock["now"] += 2_000
        assert store.purge_expired() == 1
        assert len(store) == 0

    def test_reading_status_purges(self):
        import os
        from unittest import mock

        surface, tools = self._surface()
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
            tools["maxey0-ss.provider.complete"].handler(
                {"provider": "anthropic", "prompt": "hi"})
        status = tools["maxey0-ss.tasks.status"].handler({})
        assert "purged_on_read" in status

    def test_no_prompt_or_credential_reaches_the_task_payload(self):
        """A task carries the terminal result, and results are readable."""
        import json
        import os
        from unittest import mock

        surface, tools = self._surface()
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
            out = tools["maxey0-ss.provider.complete"].handler(
                {"provider": "anthropic", "prompt": "a-private-prompt-string"})
        assert "a-private-prompt-string" not in json.dumps(out["task"])


# ---------------------------------------------------------------------------
# a task belongs to the principal that raised it
# ---------------------------------------------------------------------------


class TestTasksAreOwned:
    """`tasks/*` demanded only `observe`, which every viewer holds, so any
    viewer holding a task id could read or cancel another caller's result."""

    def test_another_principal_gets_not_found(self, monkeypatch):
        import os
        from unittest import mock

        monkeypatch.setenv("MAXEY0_AUTH_MODE", "bearer")
        monkeypatch.setenv("MAXEY0_MCP_TOKENS", "tok-owner:admin,tok-other:admin")
        monkeypatch.delenv("MAXEY0_MCP_TOKEN_HASHES", raising=False)
        monkeypatch.delenv("MAXEY0_PUBLIC", raising=False)
        app = create_app()
        owner = TestClient(app, headers={"Authorization": "Bearer tok-owner"})
        other = TestClient(app, headers={"Authorization": "Bearer tok-other"})
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
            out = rpc(owner, "tools/call",
                      {"name": "maxey0-ss.provider.complete",
                       "arguments": {"provider": "anthropic", "prompt": "hi"}},
                      name="maxey0-ss.provider.complete")
        assert "result" in out.json(), out.text
        tid = out.json()["result"]["structuredContent"]["task"]["taskId"]
        for method in ("tasks/get", "tasks/cancel"):
            r = rpc(other, method, {"taskId": tid}, name=tid)
            assert r.status_code == 404, r.text
            assert r.json()["error"]["message"] == f"Unknown task: {tid}"
        mine = rpc(owner, "tasks/get", {"taskId": tid}, name=tid)
        assert mine.status_code == 200
        assert mine.json()["result"]["taskId"] == tid
        assert "owner" not in mine.text
