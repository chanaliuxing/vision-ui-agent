#!/usr/bin/env python3
"""
Background Worker - Processes YOLO jobs from SQS queue
Handles job execution, progress tracking, and result storage
"""

import asyncio
import json
import time
import os
import signal
import logging
from typing import Dict, Any, Optional
import traceback

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import boto3
import redis.asyncio as aioredis
import httpx
from schemas import PickRequest, PickResponse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
AWS_ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
WORKER_ID = os.getenv("WORKER_ID", f"worker-{os.getpid()}")

QUEUE_NAME = "yolo-processing-queue"
YOLO_API_URL = "http://localhost:8000"
POLL_INTERVAL = 5  # seconds
MAX_RECEIVE_COUNT = 3
VISIBILITY_TIMEOUT = 300  # 5 minutes

# Global state
running = True
sqs_client = None
redis_client = None


class YoloWorker:
    """Background worker for processing YOLO jobs"""

    def __init__(self):
        self.worker_id = WORKER_ID
        self.processed_count = 0
        self.error_count = 0
        self.start_time = time.time()

    async def initialize(self):
        """Initialize AWS and Redis connections"""
        global sqs_client, redis_client

        # Initialize SQS client
        sqs_client = boto3.client(
            'sqs',
            region_name=AWS_REGION,
            endpoint_url=AWS_ENDPOINT_URL,
            aws_access_key_id='test',
            aws_secret_access_key='test'
        )

        # Initialize Redis client
        redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
        await redis_client.ping()

        logger.info(f"Worker {self.worker_id} initialized")

    async def update_job_status(self, job_id: str, status: str, progress: float = None,
                               error: str = None, result: PickResponse = None):
        """Update job status in Redis"""
        try:
            # Get current job data
            job_data = await redis_client.get(f"job:{job_id}")
            if not job_data:
                logger.warning(f"Job {job_id} not found in Redis")
                return

            job_status = json.loads(job_data)
            job_status.update({
                "status": status,
                "updated_at": time.time(),
                "worker_id": self.worker_id
            })

            if progress is not None:
                job_status["progress"] = progress

            if error is not None:
                job_status["error"] = error

            # Update job status
            await redis_client.setex(f"job:{job_id}", 3600, json.dumps(job_status))

            # Store result if completed
            if result and status == "completed":
                await redis_client.setex(f"result:{job_id}", 3600, result.json())

            # Publish progress update for SSE
            progress_update = {
                "job_id": job_id,
                "status": status,
                "progress": progress or job_status.get("progress", 0),
                "timestamp": time.time(),
                "worker_id": self.worker_id
            }

            await redis_client.publish(f"progress:{job_id}", json.dumps(progress_update))

            logger.debug(f"Updated job {job_id} status to {status}")

        except Exception as e:
            logger.error(f"Failed to update job status for {job_id}: {e}")

    async def process_yolo_request(self, job_id: str, request_data: Dict[str, Any]) -> PickResponse:
        """Process a YOLO request and return the result"""
        try:
            # Parse request
            pick_request = PickRequest.parse_obj(request_data)

            # Update progress: starting processing
            await self.update_job_status(job_id, "processing", 10.0)

            # Call YOLO API
            async with httpx.AsyncClient(timeout=60.0) as client:
                await self.update_job_status(job_id, "processing", 30.0)

                response = await client.post(
                    f"{YOLO_API_URL}/v1/pick",
                    json=pick_request.dict(),
                    headers={"Content-Type": "application/json"}
                )

                await self.update_job_status(job_id, "processing", 80.0)

                if response.status_code == 200:
                    yolo_result = response.json()
                    if yolo_result.get("ok"):
                        # Convert to PickResponse
                        data = yolo_result["data"]
                        result = PickResponse.parse_obj(data)

                        await self.update_job_status(job_id, "processing", 100.0)
                        return result
                    else:
                        error_msg = yolo_result.get("error", "Unknown YOLO API error")
                        raise Exception(f"YOLO API error: {error_msg}")
                else:
                    raise Exception(f"YOLO API HTTP {response.status_code}: {response.text}")

        except httpx.TimeoutException:
            raise Exception("YOLO API timeout")
        except Exception as e:
            logger.error(f"YOLO processing failed for job {job_id}: {e}")
            raise

    async def process_message(self, message: Dict[str, Any]) -> bool:
        """Process a single SQS message"""
        receipt_handle = message['ReceiptHandle']
        message_id = message['MessageId']

        try:
            # Parse message body
            body = json.loads(message['Body'])
            job_id = body['job_id']
            request_data = body['request_data']
            timeout_ms = body.get('timeout_ms', 30000)

            logger.info(f"Processing job {job_id} (message {message_id})")

            # Set processing timeout
            processing_timeout = min(timeout_ms / 1000, 300)  # Max 5 minutes

            # Process with timeout
            result = await asyncio.wait_for(
                self.process_yolo_request(job_id, request_data),
                timeout=processing_timeout
            )

            # Mark as completed
            await self.update_job_status(job_id, "completed", 100.0, result=result)

            # Delete message from queue
            queue_url = sqs_client.get_queue_url(QueueName=QUEUE_NAME)['QueueUrl']
            sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)

            self.processed_count += 1
            logger.info(f"Successfully processed job {job_id}")
            return True

        except asyncio.TimeoutError:
            error_msg = f"Job processing timeout ({timeout_ms}ms)"
            logger.error(f"Job {body.get('job_id', 'unknown')} timed out")
            await self.update_job_status(body.get('job_id', 'unknown'), "failed", error=error_msg)
            return False

        except Exception as e:
            error_msg = f"Processing error: {str(e)}"
            logger.error(f"Failed to process message {message_id}: {e}")
            logger.error(traceback.format_exc())

            try:
                job_id = json.loads(message['Body'])['job_id']
                await self.update_job_status(job_id, "failed", error=error_msg)
            except:
                pass

            self.error_count += 1
            return False

    async def poll_and_process(self):
        """Main polling loop"""
        logger.info(f"Worker {self.worker_id} starting polling loop")

        queue_url = sqs_client.get_queue_url(QueueName=QUEUE_NAME)['QueueUrl']

        while running:
            try:
                # Long polling for messages
                response = sqs_client.receive_message(
                    QueueUrl=queue_url,
                    MaxNumberOfMessages=1,
                    WaitTimeSeconds=20,  # Long polling
                    VisibilityTimeout=VISIBILITY_TIMEOUT,
                    AttributeNames=['ApproximateReceiveCount']
                )

                messages = response.get('Messages', [])

                if not messages:
                    logger.debug("No messages received, continuing polling")
                    continue

                for message in messages:
                    if not running:
                        break

                    # Check receive count for poison messages
                    receive_count = int(message.get('Attributes', {}).get('ApproximateReceiveCount', 0))
                    if receive_count > MAX_RECEIVE_COUNT:
                        logger.warning(f"Message {message['MessageId']} exceeded max receive count, deleting")
                        sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=message['ReceiptHandle'])
                        continue

                    # Process message
                    success = await self.process_message(message)

                    if not success:
                        # Message will become visible again after visibility timeout
                        logger.warning(f"Message {message['MessageId']} processing failed, will retry")

            except Exception as e:
                logger.error(f"Polling error: {e}")
                await asyncio.sleep(POLL_INTERVAL)

        logger.info(f"Worker {self.worker_id} stopped polling")

    async def run(self):
        """Main worker run method"""
        await self.initialize()

        # Register worker in Redis
        worker_info = {
            "worker_id": self.worker_id,
            "start_time": self.start_time,
            "status": "running",
            "processed_count": 0,
            "error_count": 0
        }
        await redis_client.setex(f"worker:{self.worker_id}", 60, json.dumps(worker_info))

        # Start heartbeat task
        heartbeat_task = asyncio.create_task(self.heartbeat_loop())

        try:
            # Start main polling loop
            await self.poll_and_process()
        finally:
            # Cleanup
            heartbeat_task.cancel()
            await redis_client.delete(f"worker:{self.worker_id}")
            await redis_client.close()

            logger.info(f"Worker {self.worker_id} shutdown complete. "
                       f"Processed: {self.processed_count}, Errors: {self.error_count}")

    async def heartbeat_loop(self):
        """Send periodic heartbeat to Redis"""
        while running:
            try:
                worker_info = {
                    "worker_id": self.worker_id,
                    "start_time": self.start_time,
                    "status": "running",
                    "processed_count": self.processed_count,
                    "error_count": self.error_count,
                    "last_heartbeat": time.time()
                }
                await redis_client.setex(f"worker:{self.worker_id}", 60, json.dumps(worker_info))
                await asyncio.sleep(30)  # Heartbeat every 30 seconds
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
                await asyncio.sleep(30)


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    global running
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    running = False


async def main():
    """Main entry point"""
    # Setup signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Create and run worker
    worker = YoloWorker()

    try:
        await worker.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Worker error: {e}")
        logger.error(traceback.format_exc())


if __name__ == "__main__":
    asyncio.run(main())