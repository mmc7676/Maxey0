from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


@dataclass
class Event:
    seq: int
    type: str
    actor: str
    payload: dict[str, Any]
    prev_hash: str
    hash: str


class Ledger:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def emit(self, event_type: str, actor: str, payload: dict[str, Any]) -> Event:
        prev = self.events[-1].hash if self.events else "0" * 64
        body = {"seq": len(self.events) + 1, "type": event_type, "actor": actor, "payload": payload, "prev_hash": prev}
        digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        event = Event(body["seq"], event_type, actor, payload, prev, digest)
        self.events.append(event)
        return event

    def verify(self) -> bool:
        previous = "0" * 64
        for event in self.events:
            body = {"seq": event.seq, "type": event.type, "actor": event.actor, "payload": event.payload, "prev_hash": previous}
            expected = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            if expected != event.hash or event.prev_hash != previous:
                return False
            previous = event.hash
        return True
