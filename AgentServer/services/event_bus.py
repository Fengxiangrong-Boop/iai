import asyncio
from typing import Dict, List

class EventBus:
    def __init__(self):
        self._queues: Dict[str, List[asyncio.Queue]] = {}

    def publish(self, topic: str, message: str):
        if topic not in self._queues:
            return
        for q in self._queues[topic]:
            try:
                q.put_nowait(message)
            except Exception:
                pass

    def subscribe(self, topic: str) -> asyncio.Queue:
        if topic not in self._queues:
            self._queues[topic] = []
        q = asyncio.Queue()
        self._queues[topic].append(q)
        return q

    def unsubscribe(self, topic: str, q: asyncio.Queue):
        if topic in self._queues and q in self._queues[topic]:
            self._queues[topic].remove(q)

event_bus = EventBus()
