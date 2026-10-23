#!/usr/bin/env python3
"""
Worker Scaling Utility - Manual and programmatic worker scaling
Provides utilities for scaling YOLO workers up/down and monitoring queue health
"""

import argparse
import json
import time
import logging
from typing import Dict, Any, List, Optional
import subprocess
import os
import signal

import boto3
import redis

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
AWS_ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
QUEUE_NAME = "yolo-processing-queue"

# Docker compose configuration
COMPOSE_FILE = "scaling/docker-compose.scaling.yml"
SERVICE_NAME = "yolo-worker"


class WorkerScaler:
    """Utility for scaling YOLO workers"""

    def __init__(self):
        self.sqs_client = None
        self.redis_client = None
        self.initialize_clients()

    def initialize_clients(self):
        """Initialize AWS and Redis clients"""
        try:
            # Initialize SQS client
            self.sqs_client = boto3.client(
                'sqs',
                region_name=AWS_REGION,
                endpoint_url=AWS_ENDPOINT_URL,
                aws_access_key_id='test',
                aws_secret_access_key='test'
            )

            # Initialize Redis client
            self.redis_client = redis.from_url(REDIS_URL, decode_responses=True)
            self.redis_client.ping()

            logger.info("AWS and Redis clients initialized")

        except Exception as e:
            logger.error(f"Failed to initialize clients: {e}")
            raise

    def get_queue_metrics(self) -> Dict[str, Any]:
        """Get current queue metrics"""
        try:
            queue_url = self.sqs_client.get_queue_url(QueueName=QUEUE_NAME)['QueueUrl']

            # Get queue attributes
            attrs = self.sqs_client.get_queue_attributes(
                QueueUrl=queue_url,
                AttributeNames=[
                    'ApproximateNumberOfMessages',
                    'ApproximateNumberOfMessagesNotVisible',
                    'ApproximateAgeOfOldestMessage'
                ]
            )

            queue_depth = int(attrs['Attributes']['ApproximateNumberOfMessages'])
            processing_jobs = int(attrs['Attributes']['ApproximateNumberOfMessagesNotVisible'])
            oldest_message_age = attrs['Attributes'].get('ApproximateAgeOfOldestMessage')

            return {
                "queue_depth": queue_depth,
                "processing_jobs": processing_jobs,
                "oldest_message_age": int(oldest_message_age) if oldest_message_age else None,
                "timestamp": time.time()
            }

        except Exception as e:
            logger.error(f"Failed to get queue metrics: {e}")
            return {}

    def get_worker_count(self) -> int:
        """Get current number of active workers"""
        try:
            # Get worker count from Redis
            cursor = 0
            worker_count = 0

            while True:
                cursor, keys = self.redis_client.scan(cursor, match="worker:*", count=100)
                worker_count += len(keys)

                if cursor == 0:
                    break

            return worker_count

        except Exception as e:
            logger.error(f"Failed to get worker count: {e}")
            return 0

    def get_worker_status(self) -> List[Dict[str, Any]]:
        """Get detailed status of all workers"""
        try:
            workers = []
            cursor = 0

            while True:
                cursor, keys = self.redis_client.scan(cursor, match="worker:*", count=100)

                for key in keys:
                    worker_data = self.redis_client.get(key)
                    if worker_data:
                        worker_info = json.loads(worker_data)
                        workers.append(worker_info)

                if cursor == 0:
                    break

            return workers

        except Exception as e:
            logger.error(f"Failed to get worker status: {e}")
            return []

    def scale_workers(self, target_count: int) -> bool:
        """Scale workers to target count using docker-compose"""
        try:
            current_count = self.get_worker_count()
            logger.info(f"Scaling workers: {current_count} → {target_count}")

            if target_count < 0:
                target_count = 0

            # Use docker-compose to scale
            cmd = [
                "docker-compose",
                "-f", COMPOSE_FILE,
                "up", "-d",
                "--scale", f"{SERVICE_NAME}={target_count}"
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if result.returncode == 0:
                logger.info(f"Successfully scaled workers to {target_count}")
                return True
            else:
                logger.error(f"Failed to scale workers: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            logger.error("Scaling command timed out")
            return False
        except Exception as e:
            logger.error(f"Failed to scale workers: {e}")
            return False

    def auto_scale(self, max_workers: int = 10, min_workers: int = 1) -> Dict[str, Any]:
        """
        Automatically scale workers based on queue depth

        Args:
            max_workers: Maximum number of workers
            min_workers: Minimum number of workers

        Returns:
            Scaling decision information
        """
        try:
            metrics = self.get_queue_metrics()
            current_workers = self.get_worker_count()

            queue_depth = metrics.get("queue_depth", 0)
            processing_jobs = metrics.get("processing_jobs", 0)

            # Scaling logic
            # - Scale up if queue depth > 3 messages per worker
            # - Scale down if queue is empty and workers idle
            target_workers = current_workers

            if queue_depth > 0:
                # Scale up: 1 worker per 3 queued messages, but respect max
                desired_workers = min((queue_depth + 2) // 3, max_workers)
                target_workers = max(desired_workers, min_workers)
            else:
                # Scale down: reduce to minimum if no queue
                target_workers = min_workers

            # Apply scaling
            scaling_applied = False
            if target_workers != current_workers:
                scaling_applied = self.scale_workers(target_workers)

            return {
                "current_workers": current_workers,
                "target_workers": target_workers,
                "queue_depth": queue_depth,
                "processing_jobs": processing_jobs,
                "scaling_applied": scaling_applied,
                "timestamp": time.time()
            }

        except Exception as e:
            logger.error(f"Auto-scaling failed: {e}")
            return {
                "error": str(e),
                "timestamp": time.time()
            }

    def monitor_loop(self, interval: int = 30, max_workers: int = 10, min_workers: int = 1):
        """
        Continuous monitoring and auto-scaling loop

        Args:
            interval: Monitoring interval in seconds
            max_workers: Maximum workers for auto-scaling
            min_workers: Minimum workers for auto-scaling
        """
        logger.info(f"Starting monitoring loop (interval={interval}s, workers={min_workers}-{max_workers})")

        try:
            while True:
                # Get metrics and auto-scale
                result = self.auto_scale(max_workers, min_workers)

                logger.info(
                    f"Queue: {result.get('queue_depth', 'N/A')} messages, "
                    f"Workers: {result.get('current_workers', 'N/A')} → {result.get('target_workers', 'N/A')}, "
                    f"Scaled: {result.get('scaling_applied', False)}"
                )

                time.sleep(interval)

        except KeyboardInterrupt:
            logger.info("Monitoring stopped by user")
        except Exception as e:
            logger.error(f"Monitoring loop error: {e}")

    def status(self) -> Dict[str, Any]:
        """Get comprehensive system status"""
        try:
            queue_metrics = self.get_queue_metrics()
            workers = self.get_worker_status()
            worker_count = len(workers)

            # Calculate worker statistics
            running_workers = sum(1 for w in workers if w.get("status") == "running")
            total_processed = sum(w.get("processed_count", 0) for w in workers)
            total_errors = sum(w.get("error_count", 0) for w in workers)

            return {
                "queue": queue_metrics,
                "workers": {
                    "count": worker_count,
                    "running": running_workers,
                    "total_processed": total_processed,
                    "total_errors": total_errors,
                    "details": workers
                },
                "system": {
                    "timestamp": time.time(),
                    "healthy": queue_metrics.get("queue_depth", 0) < 100  # Arbitrary health threshold
                }
            }

        except Exception as e:
            logger.error(f"Failed to get status: {e}")
            return {"error": str(e), "timestamp": time.time()}

    def purge_queue(self) -> bool:
        """Purge all messages from the queue (dangerous!)"""
        try:
            queue_url = self.sqs_client.get_queue_url(QueueName=QUEUE_NAME)['QueueUrl']

            logger.warning("Purging queue - this will delete all pending jobs!")
            self.sqs_client.purge_queue(QueueUrl=queue_url)

            logger.info("Queue purged successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to purge queue: {e}")
            return False


def main():
    """Main CLI interface"""
    parser = argparse.ArgumentParser(description="YOLO Worker Scaling Utility")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Status command
    status_parser = subparsers.add_parser("status", help="Show system status")

    # Scale command
    scale_parser = subparsers.add_parser("scale", help="Manual worker scaling")
    scale_parser.add_argument("count", type=int, help="Target worker count")

    # Auto-scale command
    auto_parser = subparsers.add_parser("auto", help="One-time auto-scaling")
    auto_parser.add_argument("--max", type=int, default=10, help="Maximum workers")
    auto_parser.add_argument("--min", type=int, default=1, help="Minimum workers")

    # Monitor command
    monitor_parser = subparsers.add_parser("monitor", help="Continuous monitoring")
    monitor_parser.add_argument("--interval", type=int, default=30, help="Check interval (seconds)")
    monitor_parser.add_argument("--max", type=int, default=10, help="Maximum workers")
    monitor_parser.add_argument("--min", type=int, default=1, help="Minimum workers")

    # Purge command
    purge_parser = subparsers.add_parser("purge", help="Purge queue (dangerous!)")
    purge_parser.add_argument("--confirm", action="store_true", help="Confirm purge operation")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    try:
        scaler = WorkerScaler()

        if args.command == "status":
            status = scaler.status()
            print(json.dumps(status, indent=2))

        elif args.command == "scale":
            success = scaler.scale_workers(args.count)
            if success:
                print(f"✅ Successfully scaled to {args.count} workers")
            else:
                print(f"❌ Failed to scale workers")

        elif args.command == "auto":
            result = scaler.auto_scale(args.max, args.min)
            print(json.dumps(result, indent=2))

        elif args.command == "monitor":
            scaler.monitor_loop(args.interval, args.max, args.min)

        elif args.command == "purge":
            if not args.confirm:
                print("⚠️  This will delete ALL pending jobs. Use --confirm to proceed.")
                return

            success = scaler.purge_queue()
            if success:
                print("✅ Queue purged successfully")
            else:
                print("❌ Failed to purge queue")

    except KeyboardInterrupt:
        print("\n🛑 Operation cancelled by user")
    except Exception as e:
        print(f"❌ Error: {e}")
        logger.error(f"CLI error: {e}")


if __name__ == "__main__":
    main()