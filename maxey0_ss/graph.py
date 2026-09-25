from __future__ import annotations

from collections import defaultdict, deque
from typing import Iterable


class DirectedGraph:
    """Small dependency-free directed graph used by the core.

    NetworkX can be used by an adapter, but the Maxey0 core deliberately does
    not require graph storage. This graph is deterministic and serializable.
    """

    def __init__(self) -> None:
        self.nodes: dict[str, dict] = {}
        self.edges: dict[str, set[str]] = defaultdict(set)

    def add_node(self, node_id: str, **attrs) -> None:
        self.nodes.setdefault(node_id, {}).update(attrs)

    def add_edge(self, source: str, target: str, **attrs) -> None:
        self.add_node(source)
        self.add_node(target)
        self.edges[source].add(target)
        if attrs:
            self.nodes[target].setdefault("incoming", {})[source] = attrs

    def neighbors(self, node_id: str) -> set[str]:
        return set(self.edges.get(node_id, set()))

    def reachable(self, start: str) -> set[str]:
        seen: set[str] = set()
        q = deque([start])
        while q:
            node = q.popleft()
            if node in seen:
                continue
            seen.add(node)
            q.extend(sorted(self.edges.get(node, set())))
        seen.discard(start)
        return seen

    def path(self, start: str, target: str) -> list[str] | None:
        q = deque([(start, [start])])
        seen = {start}
        while q:
            node, path = q.popleft()
            if node == target:
                return path
            for nxt in sorted(self.edges.get(node, set())):
                if nxt not in seen:
                    seen.add(nxt)
                    q.append((nxt, path + [nxt]))
        return None

    def to_dict(self) -> dict:
        return {
            "nodes": {k: v.copy() for k, v in sorted(self.nodes.items())},
            "edges": {k: sorted(v) for k, v in sorted(self.edges.items())},
        }
