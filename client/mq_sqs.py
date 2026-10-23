import os, json, time, hashlib
import boto3
from botocore.config import Config

class SQSAdapter:
    def __init__(self, device_id: str, region: str | None = None, endpoint_url: str | None = None):
        region = region or os.getenv("AWS_REGION", "us-east-1")
        endpoint_url = endpoint_url or os.getenv("AWS_ENDPOINT_URL") or None
        self.client = boto3.client("sqs", region_name=region, endpoint_url=endpoint_url,
                                   config=Config(retries={"max_attempts": 3, "mode": "standard"}))
        self.device_id = device_id
        self.cache = {}  # queue_name -> url
        self._qsize_cache = {}  # queue_name -> (ts, value)

    def _queue_name(self, topic: str) -> str:
        # 约定：topic 直接就是队列名（含 .fifo）
        return topic

    def _url(self, queue_name: str) -> str:
        if queue_name in self.cache:
            return self.cache[queue_name]
        url = self.client.get_queue_url(QueueName=queue_name)["QueueUrl"]
        self.cache[queue_name] = url
        return url

    async def publish(self, topic: str, message: dict):
        qname = self._queue_name(topic)
        url = self._url(qname)
        body = json.dumps(message, ensure_ascii=False)
        # FIFO 需要 MessageGroupId；我们用 device_id 或 topic 自身
        group_id = self.device_id or topic
        # 开启 ContentBasedDeduplication 后可以不传 DeduplicationId；但带上更稳
        dedup = hashlib.md5(body.encode("utf-8")).hexdigest()
        self.client.send_message(
            QueueUrl=url,
            MessageBody=body,
            MessageGroupId=group_id,
            MessageDeduplicationId=dedup
        )

    async def consume(self, topic: str, timeout_ms: int | None = None):
        qname = self._queue_name(topic)
        url = self._url(qname)
        # 非阻塞短轮询：WaitTimeSeconds=0；MaxNumberOfMessages=1
        resp = self.client.receive_message(
            QueueUrl=url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=0,
            VisibilityTimeout=20  # 20s 内未 ack 会再次投递
        )
        msgs = resp.get("Messages", [])
        if not msgs:
            return None
        m = msgs[0]
        body = json.loads(m["Body"])
        # 把 receipt_handle 附在消息上，用于 ack / requeue
        body["_sqs_receipt"] = m["ReceiptHandle"]
        return body

    async def ack(self, topic: str, receipt: str):
        url = self._url(self._queue_name(topic))
        self.client.delete_message(QueueUrl=url, ReceiptHandle=receipt)

    async def requeue_now(self, topic: str, receipt: str):
        url = self._url(self._queue_name(topic))
        # 把可见性置 0，立刻重新可见
        self.client.change_message_visibility(QueueUrl=url, ReceiptHandle=receipt, VisibilityTimeout=0)

    def qsize(self, topic: str) -> int:
        # 近似值；简单做 200ms 缓存，避免过度调用
        qname = self._queue_name(topic)
        url = self._url(qname)
        now = time.time()
        ts_val = self._qsize_cache.get(qname)
        if ts_val and now - ts_val[0] < 0.2:
            return ts_val[1]
        attrs = self.client.get_queue_attributes(
            QueueUrl=url,
            AttributeNames=["ApproximateNumberOfMessages"]
        )
        val = int(attrs["Attributes"].get("ApproximateNumberOfMessages", "0"))
        self._qsize_cache[qname] = (now, val)
        return val