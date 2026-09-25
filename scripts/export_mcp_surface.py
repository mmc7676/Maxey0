"""Export the Maxey0 MCP surface for the Cloudflare edge adapter.

The Worker must never hand-maintain a copy of the tool catalog. It is generated
from `maxey0_ss.mcp_surface`, the same definition both Python transports use, so
the edge cannot advertise a tool the origin does not have.

`test_edge_surface_matches_python` fails if the generated files fall behind.

    python scripts/export_mcp_surface.py
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from maxey0_ss.mcp_surface import (  # noqa: E402
    SERVER_NAME,
    SERVER_VERSION,
    SUPER_SPACE_URI,
    build_surface,
    super_space_artifact,
    super_space_html,
)

OUT = ROOT / "workers" / "mcp-edge" / "src" / "generated"


def export() -> dict:
    surface = build_surface()

    catalog = {
        "serverName": SERVER_NAME,
        "serverVersion": SERVER_VERSION,
        "protocolVersion": "2026-07-28",
        "superSpaceUri": SUPER_SPACE_URI,
        "artifact": super_space_artifact(),
        "tools": [
            {
                "name": t.name,
                "description": t.description,
                "inputSchema": t.input_schema,
                **({"_meta": t.meta} if t.meta else {}),
            }
            for t in surface.tools
        ],
        "resources": [
            {
                "uri": r.uri,
                "name": r.name,
                "description": r.description,
                "mimeType": r.mime_type,
                **({"_meta": r.meta} if r.meta else {}),
            }
            for r in surface.resources
        ],
        # Resource bodies that are deterministic enough to serve from the edge.
        # The MCP App HTML is emitted separately because of its size.
        "staticResources": {
            r.uri: r.reader()
            for r in surface.resources
            if r.uri != SUPER_SPACE_URI
        },
    }
    return catalog


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    catalog = export()

    (OUT / "surface.json").write_text(
        json.dumps(catalog, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    # newline="" keeps LF endings. Without it Python rewrites every \n to \r\n
    # on Windows, the edge copy diverges from the origin copy by ~109 bytes, and
    # the artifact sha256 no longer matches across transports.
    (OUT / "super-space.html").write_text(
        super_space_html(), encoding="utf-8", newline=""
    )

    print(f"tools     : {len(catalog['tools'])}")
    print(f"resources : {len(catalog['resources'])}")
    print(f"artifact  : {catalog['artifact']['kind']} {catalog['artifact']['bytes']} bytes")
    print(f"sha256    : {catalog['artifact']['sha256']}")
    print(f"written   : {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
