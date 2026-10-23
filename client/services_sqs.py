import os
from core.context import Services
from .mq_sqs import SQSAdapter

def build_services_sqs(dom, osmod, vision, logger, device_id: str) -> Services:
    adapter = SQSAdapter(
        device_id=device_id,
        region=os.getenv("AWS_REGION", "us-east-1"),
        endpoint_url=os.getenv("AWS_ENDPOINT_URL") or None
    )
    # 给 actions 用的统一接口：同名方法
    class MQCompat:
        def __init__(self, sqs: SQSAdapter): self.sqs = sqs
        async def publish(self, topic: str, message): return await self.sqs.publish(topic, message)
        async def consume(self, topic: str, timeout_ms=None): return await self.sqs.consume(topic, timeout_ms)
        async def ack(self, topic: str, receipt: str): return await self.sqs.ack(topic, receipt)
        async def requeue_now(self, topic: str, receipt: str): return await self.sqs.requeue_now(topic, receipt)
        def qsize(self, topic: str) -> int: return self.sqs.qsize(topic)

    return Services(dom=dom, os=osmod, vision=vision, mq=MQCompat(adapter), logger=logger)