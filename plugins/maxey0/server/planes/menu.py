"""`loops_menu` — the control surface, rendered from the registry.

Until 0.7.0 the menu was a 296-line prompt telling the model to render the
surface from a tool call, with the fallback — when the call failed — being the
prose in the file itself. That is the failure mode it was written to prevent,
and it is exactly what happened: with the connectors down, `/maxey0:menu`
transcribed its own instructions and appended a caveat.

A menu that must not drift cannot be prose. This one is a function over
`catalog.py`, so what it prints is what the product registers. If a tool is
added and this list does not change, the tool is not in the catalog and
`scripts/check_lexicon.py` fails the build.

It also reports **which connectors are reachable from here**, because the
honest answer to "what can I do" depends on what is installed, and a menu that
lists the full surface on a machine with one connector is lying politely.

Planes and connectors are reported separately, on purpose. A plane is what the
system is; a connector is what installs. The mapping is many-to-one, and one
plane — Execution — has no connector at all, because Maxey0 does not own it.
"""

from __future__ import annotations

import importlib.util
from typing import Any

from . import catalog

#: What each connector must be able to import to be usable in this process.
_PROBE = {
    "context": "scw_runtime.server",
    "loops": "maxey0_studio.state",
    "observe": "gate.journal",
}


def _reachable(connector: str) -> dict[str, Any]:
    """Whether this connector's implementation imports in this process.

    Import-checked rather than assumed. A connector declared in a manifest but
    unable to start is the single most common failure this product has, so the
    menu reports what it can verify and says plainly when it cannot.
    """
    module = _PROBE[connector]
    try:
        found = importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        found = False
    return {"importable": found, "probe": module}


def _planes() -> list[dict]:
    """The three architectural planes, including the one Maxey0 does not own."""
    return [{"plane": pid, **meta} for pid, meta in catalog.PLANES.items()]


def _connector_block(connector: str) -> dict:
    meta = catalog.CONNECTORS[connector]
    groups: dict[str, list[dict]] = {}
    for tool in catalog.BY_CONNECTOR[connector]:
        groups.setdefault(tool.group, []).append(
            {"tool": tool.name, "does": tool.summary, "mutates": tool.mutates}
        )
    return {
        "connector": meta["connector"],
        "serves_plane": meta["plane"],
        "title": meta["title"],
        "tagline": meta["tagline"],
        "owns": meta["owns"],
        "useful_alone": meta["alone"],
        "tools": len(catalog.BY_CONNECTOR[connector]),
        "groups": groups,
        **_reachable(connector),
    }


def render(section: str = "menu") -> dict:
    """The Maxey0 control surface.

    Sections: `menu` (everything), `planes`, `connectors`, `context`, `loops`,
    `observe`, `commands`, `views`.

    Every row comes from the catalog, so this cannot describe a tool the
    product does not register, and cannot omit one it does.
    """
    section = (section or "menu").strip().lower()

    if section in catalog.BY_CONNECTOR:
        return {"ok": True, "section": section,
                "connector": _connector_block(section)}

    if section == "commands":
        return {"ok": True, "section": "commands",
                "commands": [
                    {"command": f"/maxey0:{name}",
                     "connector": f"maxey0-{owner}",
                     "serves_plane": catalog.CONNECTORS[owner]["plane"],
                     "does": does}
                    for name, owner, does in catalog.COMMANDS
                ]}

    if section == "views":
        return {"ok": True, "section": "views",
                "studio": "http://127.0.0.1:7676",
                "views": [{"view": n, "shows": s} for n, s in catalog.VIEWS]}

    if section == "planes":
        return {"ok": True, "section": "planes",
                "planes": _planes(),
                "note": "A plane is what the system is. A connector is what "
                        "installs. Maxey0 owns two of the three; the Execution "
                        "plane belongs to the host, and the Gate stands at its "
                        "boundary rather than inside it."}

    if section == "connectors":
        return {"ok": True, "section": "connectors",
                "connectors": [_connector_block(c)
                               for c in ("context", "loops", "observe")]}

    return {
        "ok": True,
        "section": "menu",
        "product": "Maxey0 — the context plane as an engineered surface.",
        "differentiator": (
            "Most agent infrastructure primarily adds capability to the "
            "execution plane. Maxey0 makes the contextual environment "
            "surrounding agentic execution an independently structured, "
            "routable, partitionable, and observable plane, while providing "
            "an engineering plane that can observe and tune both."
        ),
        "counts": catalog.counts(),
        "planes": _planes(),
        "connectors": [_connector_block(c)
                       for c in ("context", "loops", "observe")],
        "commands": [
            {"command": f"/maxey0:{name}", "connector": f"maxey0-{owner}",
             "does": does}
            for name, owner, does in catalog.COMMANDS
        ],
        "studio": {
            "url": "http://127.0.0.1:7676",
            "command": "/maxey0:studio",
            "views": [{"view": n, "shows": s} for n, s in catalog.VIEWS],
        },
        "how_to_read_this": (
            "Every row is a tool this product registers, not a description of "
            "one. Ask for a section by name — menu planes, menu connectors, "
            "menu context, menu loops, menu observe, menu commands, menu "
            "views — for the detail."
        ),
        "rules": [
            "Call, do not recall. Never render a list from memory; the counts "
            "and contents come from the registry so what you see is what is "
            "loaded.",
            "A refusal is output. Report it with the runtime's own message and "
            "hint rather than routing around it.",
            "Never claim isolation held without checking. "
            "context_scope_closure and context_window_disjointness check the "
            "regions; observe_gate_activity checks the agents.",
            "context_window_reset is destructive. Confirm before calling it.",
            "Say what you did not check.",
        ],
    }


def loops_menu(section: str = "menu") -> dict:
    """The Maxey0 control surface — every plane, connector, tool and view.

    Rendered from the catalog rather than written down, so it cannot drift from
    what the product installs. Sections: `menu`, `planes`, `connectors`,
    `context`, `loops`, `observe`, `commands`, `views`.
    """
    return render(section)
