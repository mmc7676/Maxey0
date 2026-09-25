from __future__ import annotations

from .ledger import Ledger


class Observatory:
    def __init__(self) -> None:
        self.ledger = Ledger()

    def record(self, event_type: str, actor: str, **payload) -> None:
        self.ledger.emit(event_type, actor, payload)

    def trace(self) -> list[dict]:
        return [e.__dict__.copy() for e in self.ledger.events]

    def verify(self) -> bool:
        return self.ledger.verify()
