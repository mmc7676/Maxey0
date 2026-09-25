"""Drive the Maxey0 stdio MCP server as a real client: spawn, handshake, exercise."""
import asyncio, os, pathlib, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO = str(pathlib.Path(__file__).resolve().parents[1])
PY = str(pathlib.Path(REPO) / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python"))


async def main() -> int:
    env = dict(os.environ)
    env["PYTHONPATH"] = REPO
    params = StdioServerParameters(
        command=PY, args=["-m", "maxey0_ss.mcp_stdio_server"], cwd=REPO, env=env
    )
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            init = await s.initialize()
            print("HANDSHAKE   : OK")
            print("serverInfo  :", init.serverInfo.name, init.serverInfo.version)
            print("protocol    :", init.protocolVersion)
            caps = init.capabilities
            print("capabilities: tools=%s resources=%s" % (bool(caps.tools), bool(caps.resources)))

            tools = (await s.list_tools()).tools
            print("tools       :", len(tools))
            for t in tools:
                flag = " [ui]" if (t.meta or {}).get("ui") else ""
                print("   -", t.name + flag)

            res = (await s.list_resources()).resources
            print("resources   :", len(res))
            for x in res:
                print("   -", str(x.uri), "|", x.mimeType)

            h = await s.call_tool("maxey0-ss.health", {})
            art = (h.structuredContent or {}).get("app_artifact", {})
            print("health      :", (h.structuredContent or {}).get("mcp_protocol"))
            print("app artifact:", art.get("kind"), art.get("bytes"), "sha256", str(art.get("sha256"))[:16])

            c = await s.call_tool("maxey0-ss.scw.create", {"scw_id": "SCW9", "task": "handshake verification"})
            print("scw.create  :", (c.structuredContent or {}).get("id"), "parent:", (c.structuredContent or {}).get("parent_id"))

            d = await s.call_tool("maxey0-ss.scw.describe", {})
            print("scw.describe:", sorted((d.structuredContent or {}).get("specifications", {}).keys()))

            rr = await s.read_resource("ui://maxey0-ss/super-space.html")
            body = rr.contents[0]
            print("ui resource :", body.mimeType, len(body.text), "chars")

            # Admission rule must still bite on stdio.
            bad = await s.call_tool("maxey0-ss.scw.observe_host_window", {"scw_address": "not-an-address", "segments": []})
            if not bad.isError:
                print("GATE        : FAIL (bad address accepted)")
                return 1
            print("GATE        : enforced ->", bad.content[0].text[:70])

            good = await s.call_tool("maxey0-ss.scw.observe_host_window",
                {"scw_address": "scw://maxey0/context/observation/host-window/SCW0", "segments": []})
            print("GATE        : valid address ->", "accepted" if not good.isError else "REJECTED")
            if good.isError:
                return 1
    print("\nRESULT: stdio server handshakes and serves the full Maxey0 surface.")
    return 0


sys.exit(asyncio.run(main()))
