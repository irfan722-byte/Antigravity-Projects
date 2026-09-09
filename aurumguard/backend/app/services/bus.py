"""In-process event bus for Server-Sent Events. One queue per subscriber."""
from __future__ import annotations

import asyncio
import json
from collections import defaultdict


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[asyncio.Queue]] = defaultdict(list)

    def subscribe(self, user_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subs[user_id].append(q)
        return q

    def unsubscribe(self, user_id: str, q: asyncio.Queue) -> None:
        try:
            self._subs[user_id].remove(q)
        except ValueError:
            pass

    def publish(self, user_id: str, event: str, data: dict) -> None:
        payload = json.dumps({"event": event, "data": data}, default=str)
        for q in list(self._subs.get(user_id, [])) + list(self._subs.get("*", [])):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass


bus = EventBus()
