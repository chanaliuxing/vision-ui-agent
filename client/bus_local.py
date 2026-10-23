import asyncio
from typing import Dict

class LocalBus:
    def __init__(self):
        self._topics: Dict[str, asyncio.Queue] = {}

    def topic(self, name: str) -> asyncio.Queue:
        if name not in self._topics:
            self._topics[name] = asyncio.Queue()
        return self._topics[name]

    async def publish(self, topic: str, message):
        await self.topic(topic).put(message)

    async def consume(self, topic: str, timeout_ms: int | None = None):
        q = self.topic(topic)
        if timeout_ms is None:
            return await q.get()
        try:
            return await asyncio.wait_for(q.get(), timeout=timeout_ms/1000)
        except asyncio.TimeoutError:
            return None

    def qsize(self, topic: str) -> int:
        return self.topic(topic).qsize()