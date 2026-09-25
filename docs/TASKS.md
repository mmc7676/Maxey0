# MCP Tasks extension (SEP-2663)

## Why this exists

`io.modelcontextprotocol/tasks` was advertised in `server/discover` by every
transport and implemented by none. A client that read the capability and called
`tasks/get` received `-32601 Method not found`. Advertising a capability you do
not implement is worse than omitting it, because clients branch on the
declaration.

## The contract

Taken from SEP-2663, not from memory.

| Method | Params | Notes |
|---|---|---|
| `tasks/get` | `{taskId}` | Poll. Replaces the old blocking `tasks/result`. |
| `tasks/update` | `{taskId, inputResponses}` | Client answers an outstanding input request. |
| `tasks/cancel` | `{taskId}` | Terminal; a no-op on an already-finished task. |
| `subscriptions/listen` | `{notifications: {taskIds}}` | Per-task opt-in. |

Statuses: `working`, `input_required`, `completed`, `failed`, `canceled`.

`resultType` is `"task"` while live and `"complete"` once terminal, so a poller
knows when the payload is final.

Task handles are returned **unsolicited** — SEP-2663 removed per-request opt-in,
so a caller does not ask for a task, it receives one.

### The routing rule

> When `tasks/get`, `tasks/update`, or `tasks/cancel` is sent over the
> Streamable HTTP transport, the client **MUST** set the `Mcp-Name` header to
> the value of `params.taskId`.

This lets intermediaries route a task to the instance holding its state. Both
the Python adapter and the edge Worker enforce it and refuse a mismatch with
`-32600`.

## Where it lives

`maxey0_ss/tasks.py` — transport-neutral, like `mcp_surface`. A task is
*application state above the transport*, exactly like an SCW: the protocol
carries a handle, the state lives here. A task raised by a governed call carries
its `scw_address`, so task state and application state stay addressable together.

## Per transport

| Transport | Tasks |
|---|---|
| HTTP (2026-07-28) | Implemented. All four methods. |
| Edge Worker | **Proxied to origin.** Tasks are durable state; answering them at the edge would mean two stores that disagree. |
| stdio | Not advertised. stdio speaks the pre-extension session protocol, and its capabilities are derived from registered handlers, so it makes no claim. |

## Not implemented

- **No push delivery.** `subscriptions/listen` acknowledges inline and records
  the opt-in; the stateless HTTP transport holds no stream. Clients poll
  `tasks/get`, which SEP-2663 permits.
- **No shared task store.** In-memory and per-process, so a multi-instance
  deployment needs the `Mcp-Name` routing to land on the right instance — which
  is exactly why the rule exists.
- **No task-creating public tool yet.** The store is driven programmatically;
  none of the 22 public tools is long-running enough to warrant a handle.
