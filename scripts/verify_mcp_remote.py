"""Verify a deployed Maxey0 MCP endpoint over the wire.

Checks the MCP 2026-07-28 contract against a live URL and reports what is
actually true, including whether tool execution is reachable. Exits non-zero if
the protocol contract is violated; a missing origin is reported, not failed,
because a metadata-only edge is a valid deployment state.

    python scripts/verify_mcp_remote.py https://maxey0-ss-mcp.maxey0.workers.dev
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

V = "2026-07-28"

#: Cloudflare bot management can challenge a bare `Python-urllib/x.y` agent and
#: answer with an HTML interstitial instead of the Worker's JSON. Identify the
#: client properly so the check measures the Worker, not the bot rules.
UA = "maxey0-ss-verify/1.0 (+https://github.com/mmc7676)"


def _decode(raw: bytes):
    """Return parsed JSON, or the raw text when the body is not JSON at all."""
    text = raw.decode("utf-8", "replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"_non_json_body": text[:400]}


def rpc(base: str, method: str, params: dict | None = None, name: str | None = None, timeout: int = 30):
    headers = {"Content-Type": "application/json", "User-Agent": UA,
               "MCP-Protocol-Version": V, "Mcp-Method": method}
    if name:
        headers["Mcp-Name"] = name
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}).encode()
    req = urllib.request.Request(f"{base}/mcp", data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, _decode(r.read())
    except urllib.error.HTTPError as e:
        return e.code, _decode(e.read())


def get(base: str, path: str, timeout: int = 30):
    req = urllib.request.Request(f"{base}{path}", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, _decode(r.read())
    except urllib.error.HTTPError as e:
        return e.code, _decode(e.read())


def _local_surface():
    """The surface this checkout would deploy, or None when not in one.

    Tolerant on purpose: this script is also run against a remote endpoint from
    a machine with no checkout, and a parity check that cannot run should say
    so rather than fail the verification it is part of.
    """
    try:
        import pathlib as _pl
        import sys as _sys

        root = _pl.Path(__file__).resolve().parents[1]
        if str(root) not in _sys.path:
            _sys.path.insert(0, str(root))
        from maxey0_ss import __version__
        from maxey0_ss.mcp_surface import build_surface, super_space_artifact

        surface = build_surface()
        return {
            "tools": [t.name for t in surface.tools],
            "version": __version__,
            "artifact_sha256": str(super_space_artifact()["sha256"]),
        }
    except Exception:
        return None


def main(base: str) -> int:
    base = base.rstrip("/")
    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}{(' — ' + detail) if detail else ''}")
        if not ok:
            failures.append(label)

    print(f"\nMaxey0-SuperSpace MCP verification — {base}\n")

    print("TRANSPORT")
    status, health = get(base, "/health")
    check("/health responds 200", status == 200, f"HTTP {status}")
    origin_configured = bool(health.get("origin_configured")) if status == 200 else False
    artifact = health.get("app_artifact", {}) if status == 200 else {}

    print("\nPROTOCOL 2026-07-28")
    status, body = rpc(base, "server/discover")
    result = body.get("result", {})
    check("server/discover returns 200", status == 200, f"HTTP {status}")
    check("protocolVersion is 2026-07-28", result.get("protocolVersion") == V, str(result.get("protocolVersion")))
    check("serverInfo present", bool(result.get("serverInfo", {}).get("name")), str(result.get("serverInfo")))
    server_version = str(result.get("serverInfo", {}).get("version", ""))
    caps = result.get("capabilities", {}).get("extensions", {})
    check("advertises the MCP Apps extension", "io.modelcontextprotocol/ui" in caps)

    status, body = rpc(base, "initialize")
    check(
        "initialize is rejected (2026-07-28 has no handshake)",
        body.get("error", {}).get("code") == -32601,
        f"HTTP {status} code {body.get('error', {}).get('code')}",
    )

    bad = urllib.request.Request(
        f"{base}/mcp",
        data=b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}',
        headers={"Content-Type": "application/json", "User-Agent": UA},
        method="POST",
    )
    try:
        urllib.request.urlopen(bad, timeout=30)
        check("request without protocol headers is refused", False, "accepted")
    except urllib.error.HTTPError as e:
        check("request without protocol headers is refused", e.code == 400, f"HTTP {e.code}")

    print("\nCATALOG")
    status, body = rpc(base, "tools/list")
    tools = body.get("result", {}).get("tools", [])
    check("tools/list returns tools", len(tools) > 0, f"{len(tools)} tools")

    # Parity against THIS checkout, not merely "some tools came back".
    #
    # `len(tools) > 0` passed against a deployment serving 22 tools at version
    # 1.0.0 while this tree had 29 at 0.3.0 -- a green check that measures
    # whether the endpoint is UP, printed under a heading a reader takes as
    # whether the endpoint is CURRENT. Every deploy verification this script
    # ran would have passed against that deployment.
    local = _local_surface()
    if local is None:
        print("  [skip] deployment parity -- run from a checkout to compare")
    else:
        deployed = sorted(t["name"] for t in tools)
        expected = sorted(local["tools"])
        check("deployed tool COUNT matches this checkout",
              len(deployed) == len(expected),
              f"deployed {len(deployed)}, checkout {len(expected)}")
        missing = [n for n in expected if n not in deployed]
        extra = [n for n in deployed if n not in expected]
        check("deployed tool NAMES match this checkout",
              not missing and not extra,
              f"missing {missing[:3]} extra {extra[:3]}")
        check("deployed version matches this checkout",
              server_version == local["version"],
              f"deployed {server_version!r}, checkout {local['version']!r}")
        if artifact:
            check("deployed App bundle matches this checkout",
                  artifact.get("sha256") == local["artifact_sha256"],
                  f"deployed {str(artifact.get('sha256'))[:16]}..., "
                  f"checkout {local['artifact_sha256'][:16]}...")
    check("catalog carries cache hints", body.get("result", {}).get("ttlMs", 0) > 0,
          f"ttlMs={body.get('result', {}).get('ttlMs')}")
    app_tool = next((t for t in tools if t["name"] == "maxey0-ss.super_space"), None)
    check("App tool is linked to the App resource",
          bool(app_tool and app_tool.get("_meta", {}).get("ui", {}).get("resourceUri")))

    status, body = rpc(base, "resources/list")
    resources = body.get("result", {}).get("resources", [])
    check("resources/list returns resources", len(resources) > 0, f"{len(resources)} resources")

    print("\nMCP APP")
    status, body = rpc(base, "resources/read", {"uri": "ui://maxey0-ss/super-space.html"})
    contents = body.get("result", {}).get("contents", [{}])[0]
    text = contents.get("text", "")
    check("App resource is served", status == 200 and bool(text), f"HTTP {status}")
    check("mime type is an MCP App", contents.get("mimeType", "").startswith("text/html;profile=mcp-app"),
          contents.get("mimeType", ""))
    check("App is the built bundle, not the stub", len(text) > 100_000, f"{len(text)} chars")
    if artifact:
        check("artifact identity is 'built'", artifact.get("kind") == "built", str(artifact.get("kind")))
        print(f"         sha256 {artifact.get('sha256', '')[:32]}")

    print("\nTOOL EXECUTION")
    status, body = rpc(base, "tools/call", {"name": "maxey0-ss.health", "arguments": {}}, name="maxey0-ss.health")
    if origin_configured:
        sc = body.get("result", {}).get("structuredContent", {})
        check("tools/call reaches the origin", status == 200, f"HTTP {status}")
        check("origin reports 2026-07-28", sc.get("mcp_protocol") == V, str(sc.get("mcp_protocol")))
    else:
        code = body.get("error", {}).get("code")
        check("no origin: refuses rather than fabricating", code == -32010 and "result" not in body,
              f"HTTP {status} code {code}")
        print("         NOTE: metadata-only deployment. Set MAXEY0_ORIGIN to enable tool execution.")

    print("\n" + ("-" * 60))
    if failures:
        print(f"RESULT: {len(failures)} FAILED — {', '.join(failures)}")
        return 1
    print("RESULT: all checks passed.")
    print(f"        tool execution: {'origin reachable' if origin_configured else 'NOT configured (metadata-only)'}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
