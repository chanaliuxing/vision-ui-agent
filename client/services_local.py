from core.context import Services
from .bus_local import LocalBus

class LocalMQAdapter:
    def __init__(self, bus: LocalBus):
        self.bus = bus
    async def publish(self, topic: str, message):
        await self.bus.publish(topic, message)
    async def consume(self, topic: str, timeout_ms: int | None = None):
        return await self.bus.consume(topic, timeout_ms)
    def qsize(self, topic: str) -> int:
        return self.bus.qsize(topic)

def build_services(dom, os, vision, logger, bus: LocalBus) -> Services:
    return Services(dom=dom, os=os, vision=vision, mq=LocalMQAdapter(bus), logger=logger)