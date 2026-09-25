from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Role:
    name: str
    capabilities: frozenset[str]


ROLES = {
    "viewer": Role("viewer", frozenset({"observe"})),
    "operator": Role("operator", frozenset({"observe", "route", "scw.read", "mcp.discover", "mcp.call.read"})),
    "builder": Role("builder", frozenset({"observe", "route", "scw.read", "scw.create", "scw.admit", "mcp.discover", "mcp.call.read", "app.read"})),
    "admin": Role("admin", frozenset({"*"})),
}

#: Most privileged first. Used where one caller presents several roles at once
#: -- an OIDC `groups` claim listing two of them -- so the answer depends on
#: which roles were presented and never on the order an identity provider
#: happened to list them in. A role added to `ROLES` must be placed here too;
#: `test_oidc.py` fails until it is.
PRECEDENCE: tuple[str, ...] = ("admin", "builder", "operator", "viewer")


def allowed(role: str, capability: str) -> bool:
    r = ROLES.get(role)
    return bool(r and ("*" in r.capabilities or capability in r.capabilities))
