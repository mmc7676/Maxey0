"""End-to-end smoke test of a deployed Maxey0 MCP endpoint.

Runs one SCW through its whole life over the public MCP transport:

    health -> tools/list -> create -> start -> drift (anchor) -> drift (measure)
    -> describe -> close

against a live URL, so every hop is exercised: client, Cloudflare, the edge,
the origin, the Maxey0 runtime. It is not a unit test and never runs in the
suite; it talks to whatever URL it is given.

    MAXEY0_SMOKE_TOKEN=<bearer token> python scripts/smoke_production.py https://mcp.maxey0.com

The token needs the builder or admin role: `scw.start` and `scw.close` require
`scw.admit`. It is read from MAXEY0_SMOKE_TOKEN or `--token-file`, never from
an argument (argv is visible to other users of the machine) and never printed.

Each failing step is classified by layer, so a red run says where to look:

    network       DNS, TLS, connection refused, timeout
    routing       Cloudflare answered but could not reach the origin (52x/530)
    auth          the token was refused (-32001 / 401)
    authz         the token is valid but its role lacks the capability (-32002 / 403)
    protocol      the response is not a well-formed MCP/JSON-RPC answer
    application   the tool ran and reported an error
    version       the deployed version differs from --expect-version

Exit status is 0 only when every step passed. The SCW it creates has a random
9-digit identifier and is closed at the end, so repeated runs do not collide.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import urllib.error
import urllib.request

PROTOCOL = "2026-07-28"
UA = "maxey0-smoke/1.0 (+https://github.com/mmc7676/Maxey0)"
ROUTING_STATUSES = {502, 503, 504, 520, 521, 522, 523, 524, 525, 526, 530}


class StepFailed(Exception):
    def __init__(self, layer: str, detail: str) -> None:
        super().__init__(detail)
        self.layer = layer
        self.detail = detail


def classify(status: int | None, body: object) -> tuple[str, str] | None:
    """Return (layer, detail) for a failed exchange, or None if it succeeded.

    `status` is the HTTP status, or None when no HTTP response arrived.
    """
    if status is None:
        return "network", str(body)
    if status in ROUTING_STATUSES:
        return "routing", f"HTTP {status} from the edge: the origin is unreachable"
    if not isinstance(body, dict):
        return "protocol", f"HTTP {status} with a non-JSON body"
    error = body.get("error")
    if isinstance(error, dict):
        code = error.get("code")
        message = str(error.get("message", ""))
        if code == -32001 or status == 401:
            return "auth", f"{code}: {message}"
        if code == -32002 or status == 403:
            return "authz", f"{code}: {message}"
        if code in (-32011, -32012):
            return "routing", f"{code}: {message}"
        return "protocol", f"{code}: {message}"
    if status >= 400:
        return "protocol", f"HTTP {status} without a JSON-RPC error"
    if "result" not in body:
        return "protocol", "JSON-RPC response has neither result nor error"
    result = body["result"]
    if isinstance(result, dict) and result.get("isError"):
        content = result.get("content") or [{}]
        return "application", str(content[0].get("text", "tool reported isError"))[:300]
    return None


def _request(url: str, *, data: bytes | None, headers: dict[str, str],
             timeout: float) -> tuple[int | None, object]:
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **headers},
                                 method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as exc:
        status, raw = exc.code, exc.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, getattr(exc, "reason", exc)
    try:
        return status, json.loads(raw.decode("utf-8", "replace"))
    except json.JSONDecodeError:
        return status, raw[:200].decode("utf-8", "replace")


class Client:
    def __init__(self, base: str, token: str, timeout: float) -> None:
        self.base = base.rstrip("/")
        self._token = token
        self.timeout = timeout

    def rpc(self, method: str, params: dict | None = None, name: str | None = None) -> dict:
        headers = {"Content-Type": "application/json", "MCP-Protocol-Version": PROTOCOL,
                   "Mcp-Method": method, "Authorization": f"Bearer {self._token}"}
        if name:
            headers["Mcp-Name"] = name
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                           "params": params or {}}).encode()
        status, parsed = _request(f"{self.base}/mcp", data=body, headers=headers,
                                  timeout=self.timeout)
        failure = classify(status, parsed)
        if failure:
            raise StepFailed(*failure)
        return parsed["result"]

    def tool(self, name: str, arguments: dict) -> dict:
        result = self.rpc("tools/call", {"name": name, "arguments": arguments}, name=name)
        structured = result.get("structuredContent")
        if isinstance(structured, dict):
            return structured
        try:
            return json.loads(result["content"][0]["text"])
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise StepFailed("protocol", f"{name} returned no parseable content") from exc

    def health(self) -> dict:
        status, parsed = _request(f"{self.base}/health", data=None, headers={},
                                  timeout=self.timeout)
        failure = classify(status, {"result": parsed} if isinstance(parsed, dict) else parsed)
        if failure:
            raise StepFailed(*failure)
        return parsed


def run(client: Client, expect_version: str | None) -> list[tuple[str, str, str]]:
    """Run every step; return (step, outcome, detail) rows. Stops at the first failure."""
    # SCW identifiers are "SCW" plus digits; a random 9-digit suffix keeps
    # repeated runs from colliding with each other or with real windows.
    scw_id = f"SCW{100_000_000 + secrets.randbelow(900_000_000)}"
    rows: list[tuple[str, str, str]] = []
    instance: str | None = None

    def step(label, fn, check=None):
        try:
            value = fn()
            if check:
                check(value)
        except StepFailed as exc:
            rows.append((label, f"FAIL [{exc.layer}]", exc.detail))
            raise
        rows.append((label, "ok", ""))
        return value

    def expect(condition: bool, layer: str, detail: str) -> None:
        if not condition:
            raise StepFailed(layer, detail)

    try:
        health = step("health", client.health)
        if expect_version:
            step("version", lambda: health.get("version"),
                 lambda v: expect(v == expect_version, "version",
                                  f"deployed {v!r}, expected {expect_version!r}"))
        step("tools/list", lambda: client.rpc("tools/list"),
             lambda r: expect(any(t.get("name") == "maxey0-ss.scw.start" for t in r.get("tools", [])),
                              "version", "maxey0-ss.scw.start is not listed; the deployment predates 0.3.1"))
        step("create", lambda: client.tool("maxey0-ss.scw.create",
                                           {"scw_id": scw_id, "task": "production smoke test"}),
             lambda r: expect(r.get("id") == scw_id, "application", f"create returned {r!r}"[:300]))
        started = step("start", lambda: client.tool("maxey0-ss.scw.start", {"scw_id": scw_id}),
                       lambda r: expect(r.get("scw_id") == scw_id and r.get("started"),
                                        "application", f"start returned {r!r}"[:300]))
        instance = started["started"]
        step("drift anchor", lambda: client.tool("maxey0-ss.scw.drift",
                                                 {"scw_id": scw_id, "vector": [0.12, 0.40, 0.33], "anchor": True}),
             lambda r: expect(r.get("anchored") is True, "application", f"anchor returned {r!r}"[:300]))
        step("drift measure", lambda: client.tool("maxey0-ss.scw.drift",
                                                  {"scw_id": scw_id, "vector": [0.10, 0.42, 0.35]}),
             lambda r: expect(isinstance(r.get("distance"), (int, float)), "application",
                              f"measure returned {r!r}"[:300]))
        step("describe", lambda: client.tool("maxey0-ss.scw.describe", {}),
             lambda r: expect(scw_id in r.get("specifications", {})
                              and r.get(instance, {}).get("open") is True,
                              "application", f"{instance} not open in describe"))
    except StepFailed:
        pass
    if instance:
        # Closed even when a later step failed, so a red run leaves nothing open.
        try:
            step("close", lambda: client.tool("maxey0-ss.scw.close", {"scw_id": instance}),
                 lambda r: expect(r.get("closed") == instance, "application",
                                  f"close returned {r!r}"[:300]))
        except StepFailed:
            pass
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("base", help="endpoint base URL, e.g. https://mcp.maxey0.com")
    parser.add_argument("--token-file", help="file holding the bearer token")
    parser.add_argument("--expect-version", help="fail if /health reports another version")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args(argv)

    token = os.environ.get("MAXEY0_SMOKE_TOKEN", "")
    if args.token_file:
        with open(args.token_file, encoding="utf-8") as handle:
            token = handle.read().strip()
    if not token:
        print("no token: set MAXEY0_SMOKE_TOKEN or pass --token-file", file=sys.stderr)
        return 2

    rows = run(Client(args.base, token, args.timeout), args.expect_version)
    width = max(len(r[0]) for r in rows)
    for label, outcome, detail in rows:
        print(f"{label:<{width}}  {outcome}{('  ' + detail) if detail else ''}")
    return 0 if rows and all(r[1] == "ok" for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
