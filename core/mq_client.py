"""
MQ Client abstraction for LLM request/response routing
Supports SQS FIFO, Redis Streams, or other message queues
"""
import json
import time
import uuid
import logging
from typing import Any, Dict, Optional
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class MQClient(ABC):
    """Abstract MQ client interface"""

    @abstractmethod
    def send_message(self, queue_name: str, payload: Dict[str, Any],
                    group_id: str = None, dedup_id: str = None) -> bool:
        """Send message to queue"""
        pass

    @abstractmethod
    def receive_message(self, queue_name: str, request_id: str = None,
                       timeout: int = 30) -> Optional[Dict[str, Any]]:
        """Receive message from queue, optionally filtered by request_id"""
        pass

class SQSMQClient(MQClient):
    """AWS SQS FIFO implementation"""

    def __init__(self, region: str = "us-east-1", endpoint_url: str = None):
        try:
            import boto3
            self.sqs = boto3.client('sqs', region_name=region, endpoint_url=endpoint_url)
            self.queue_urls = {}  # Cache queue URLs
        except ImportError:
            raise RuntimeError("boto3 required for SQS client")

    def _get_queue_url(self, queue_name: str) -> str:
        """Get and cache queue URL"""
        if queue_name not in self.queue_urls:
            try:
                response = self.sqs.get_queue_url(QueueName=queue_name)
                self.queue_urls[queue_name] = response['QueueUrl']
            except Exception as e:
                logger.error(f"Failed to get queue URL for {queue_name}: {e}")
                raise
        return self.queue_urls[queue_name]

    def send_message(self, queue_name: str, payload: Dict[str, Any],
                    group_id: str = None, dedup_id: str = None) -> bool:
        """Send message to SQS FIFO queue"""
        try:
            queue_url = self._get_queue_url(queue_name)

            message_body = json.dumps(payload)
            message_attrs = {
                'MessageBody': message_body,
                'QueueUrl': queue_url,
                'MessageGroupId': group_id or payload.get('request_id', str(uuid.uuid4())),
                'MessageDeduplicationId': dedup_id or payload.get('request_id', str(uuid.uuid4()))
            }

            response = self.sqs.send_message(**message_attrs)
            logger.debug(f"SQS sent message to {queue_name}: {response.get('MessageId')}")
            return True

        except Exception as e:
            logger.error(f"Failed to send SQS message to {queue_name}: {e}")
            return False

    def receive_message(self, queue_name: str, request_id: str = None,
                       timeout: int = 30) -> Optional[Dict[str, Any]]:
        """
        Receive message from SQS FIFO queue
        If request_id provided, poll until matching message found or timeout
        """
        try:
            queue_url = self._get_queue_url(queue_name)
            end_time = time.time() + timeout

            while time.time() < end_time:
                response = self.sqs.receive_message(
                    QueueUrl=queue_url,
                    MaxNumberOfMessages=1,
                    WaitTimeSeconds=min(10, int(end_time - time.time())),  # Long polling
                    VisibilityTimeout=timeout
                )

                messages = response.get('Messages', [])
                if not messages:
                    continue

                for message in messages:
                    try:
                        body = json.loads(message['Body'])

                        # If request_id specified, check for match
                        if request_id and body.get('request_id') != request_id:
                            # Put message back (change visibility timeout to 0)
                            self.sqs.change_message_visibility(
                                QueueUrl=queue_url,
                                ReceiptHandle=message['ReceiptHandle'],
                                VisibilityTimeout=0
                            )
                            continue

                        # Delete message from queue
                        self.sqs.delete_message(
                            QueueUrl=queue_url,
                            ReceiptHandle=message['ReceiptHandle']
                        )

                        logger.debug(f"SQS received message from {queue_name}: {body.get('request_id')}")
                        return body

                    except json.JSONDecodeError as e:
                        logger.warning(f"Invalid JSON in SQS message: {e}")
                        # Delete malformed message
                        self.sqs.delete_message(
                            QueueUrl=queue_url,
                            ReceiptHandle=message['ReceiptHandle']
                        )

                # Short delay between polls if no matching message
                time.sleep(0.1)

            logger.warning(f"SQS receive timeout after {timeout}s for queue {queue_name}")
            return None

        except Exception as e:
            logger.error(f"Failed to receive SQS message from {queue_name}: {e}")
            return None


class MockMQClient(MQClient):
    """Mock MQ client for testing"""

    def __init__(self):
        self.messages = {}  # queue_name -> list of messages

    def send_message(self, queue_name: str, payload: Dict[str, Any],
                    group_id: str = None, dedup_id: str = None) -> bool:
        if queue_name not in self.messages:
            self.messages[queue_name] = []
        self.messages[queue_name].append(payload)
        return True

    def receive_message(self, queue_name: str, request_id: str = None,
                       timeout: int = 30) -> Optional[Dict[str, Any]]:
        messages = self.messages.get(queue_name, [])
        for i, msg in enumerate(messages):
            if not request_id or msg.get('request_id') == request_id:
                return self.messages[queue_name].pop(i)
        return None


def create_mq_client(mq_type: str = "sqs", **kwargs) -> MQClient:
    """Factory function to create MQ client"""
    if mq_type == "sqs":
        return SQSMQClient(**kwargs)
    elif mq_type == "mock":
        return MockMQClient()
    else:
        raise ValueError(f"Unsupported MQ type: {mq_type}")