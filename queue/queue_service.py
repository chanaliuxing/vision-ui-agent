#!/usr/bin/env python3
"""
Queue Service - Message routing and job management for YOLO processing
Handles SQS queue operations and job lifecycle management
"""

import asyncio
import json
import time
import uuid
from typing import Dict, Any, Optional, List
import logging
import os

import boto3
import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from schemas import PickRequest, PickResponse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# AWS/LocalStack configuration
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
AWS_ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Queue configuration
QUEUE_NAME = "yolo-processing-queue"
RESULT_TTL = 3600  # Results expire after 1 hour
VISIBILITY_TIMEOUT = 300  # 5 minutes for job processing

app = FastAPI(title="YOLO Queue Service", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global connections
sqs_client = None
redis_client = None


class QueueJobRequest(BaseModel):
    """Request to queue a YOLO processing job"""
    job_id: str = Field(..., description="Unique job identifier")
    request_data: PickRequest = Field(..., description="YOLO pick request")
    priority: int = Field(default=5, description="Job priority (1-10, lower = higher priority)")
    timeout_ms: int = Field(default=30000, description="Job timeout in milliseconds")


class QueueJobResponse(BaseModel):
    """Response from queuing a job"""
    job_id: str = Field(..., description="Job identifier")
    status: str = Field(..., description="Job status: queued|processing|completed|failed")
    estimated_wait_time_ms: Optional[int] = Field(None, description="Estimated processing time")
    sse_url: Optional[str] = Field(None, description="SSE endpoint for progress updates")


class JobStatusResponse(BaseModel):
    """Job status query response"""
    job_id: str = Field(..., description="Job identifier")
    status: str = Field(..., description="Current job status")
    progress: float = Field(default=0.0, description="Progress percentage (0-100)")
    result: Optional[PickResponse] = Field(None, description="Result if completed")
    error: Optional[str] = Field(None, description="Error message if failed")
    created_at: float = Field(..., description="Job creation timestamp")
    updated_at: float = Field(..., description="Last update timestamp")


async def get_connections():
    """Initialize AWS SQS and Redis connections"""
    global sqs_client, redis_client

    if sqs_client is None:
        sqs_client = boto3.client(
            'sqs',
            region_name=AWS_REGION,
            endpoint_url=AWS_ENDPOINT_URL,
            aws_access_key_id='test',
            aws_secret_access_key='test'
        )

        # Ensure queue exists
        try:
            sqs_client.create_queue(
                QueueName=QUEUE_NAME,
                Attributes={
                    'VisibilityTimeout': str(VISIBILITY_TIMEOUT),
                    'MessageRetentionPeriod': '1209600',  # 14 days
                    'ReceiveMessageWaitTimeSeconds': '20'  # Long polling
                }
            )
            logger.info(f"SQS queue '{QUEUE_NAME}' ready")
        except Exception as e:
            logger.warning(f"Queue creation failed (may already exist): {e}")

    if redis_client is None:
        redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
        await redis_client.ping()
        logger.info("Redis connection established")


@app.on_event("startup")
async def startup_event():
    """Initialize connections on startup"""
    await get_connections()


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up connections on shutdown"""
    global redis_client
    if redis_client:
        await redis_client.close()


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        await get_connections()

        # Test SQS
        queue_url = sqs_client.get_queue_url(QueueName=QUEUE_NAME)['QueueUrl']

        # Test Redis
        await redis_client.ping()

        return {
            "status": "healthy",
            "sqs_queue": QUEUE_NAME,
            "redis": "connected",
            "timestamp": time.time()
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Service unhealthy: {e}")


@app.post("/queue/submit", response_model=QueueJobResponse)
async def submit_job(job_request: QueueJobRequest):
    """Submit a YOLO processing job to the queue"""
    try:
        await get_connections()

        # Get queue URL
        queue_url = sqs_client.get_queue_url(QueueName=QUEUE_NAME)['QueueUrl']

        # Create job metadata
        job_data = {
            "job_id": job_request.job_id,
            "request_data": job_request.request_data.dict(),
            "priority": job_request.priority,
            "timeout_ms": job_request.timeout_ms,
            "created_at": time.time()
        }

        # Send to SQS (standard queue, no FIFO parameters)
        response = sqs_client.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(job_data),
            MessageAttributes={
                'priority': {
                    'StringValue': str(job_request.priority),
                    'DataType': 'Number'
                }
            }
        )

        # Store job status in Redis
        job_status = {
            "job_id": job_request.job_id,
            "status": "queued",
            "progress": 0.0,
            "created_at": time.time(),
            "updated_at": time.time()
        }

        await redis_client.setex(
            f"job:{job_request.job_id}",
            RESULT_TTL,
            json.dumps(job_status)
        )

        # Estimate wait time based on queue depth
        queue_attrs = sqs_client.get_queue_attributes(
            QueueUrl=queue_url,
            AttributeNames=['ApproximateNumberOfMessages']
        )

        queue_depth = int(queue_attrs['Attributes']['ApproximateNumberOfMessages'])
        estimated_wait_ms = queue_depth * 5000  # Assume 5s per job

        logger.info(f"Job {job_request.job_id} queued successfully")

        return QueueJobResponse(
            job_id=job_request.job_id,
            status="queued",
            estimated_wait_time_ms=estimated_wait_ms,
            sse_url=f"/progress/stream/{job_request.job_id}"
        )

    except Exception as e:
        logger.error(f"Failed to submit job {job_request.job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to queue job: {e}")


@app.get("/queue/status/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """Get status of a queued job"""
    try:
        await get_connections()

        job_data = await redis_client.get(f"job:{job_id}")
        if not job_data:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

        job_status = json.loads(job_data)

        # If completed, try to get result
        result = None
        if job_status["status"] == "completed":
            result_data = await redis_client.get(f"result:{job_id}")
            if result_data:
                result = PickResponse.parse_raw(result_data)

        return JobStatusResponse(
            job_id=job_id,
            status=job_status["status"],
            progress=job_status.get("progress", 0.0),
            result=result,
            error=job_status.get("error"),
            created_at=job_status["created_at"],
            updated_at=job_status["updated_at"]
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get job status {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get job status: {e}")


@app.get("/queue/metrics")
async def get_queue_metrics():
    """Get queue metrics for monitoring"""
    try:
        await get_connections()

        queue_url = sqs_client.get_queue_url(QueueName=QUEUE_NAME)['QueueUrl']

        # Get queue attributes
        attrs = sqs_client.get_queue_attributes(
            QueueUrl=queue_url,
            AttributeNames=[
                'ApproximateNumberOfMessages',
                'ApproximateNumberOfMessagesNotVisible',
                'ApproximateAgeOfOldestMessage'
            ]
        )

        # Get active jobs from Redis
        active_jobs = []
        cursor = 0
        while True:
            cursor, keys = await redis_client.scan(cursor, match="job:*", count=100)
            for key in keys:
                job_data = await redis_client.get(key)
                if job_data:
                    job = json.loads(job_data)
                    if job["status"] in ["queued", "processing"]:
                        active_jobs.append(job)
            if cursor == 0:
                break

        return {
            "queue_depth": int(attrs['Attributes']['ApproximateNumberOfMessages']),
            "processing_jobs": int(attrs['Attributes']['ApproximateNumberOfMessagesNotVisible']),
            "oldest_message_age": attrs['Attributes'].get('ApproximateAgeOfOldestMessage'),
            "active_jobs": len(active_jobs),
            "timestamp": time.time()
        }

    except Exception as e:
        logger.error(f"Failed to get queue metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get metrics: {e}")


@app.delete("/queue/cancel/{job_id}")
async def cancel_job(job_id: str):
    """Cancel a queued job (if not yet processing)"""
    try:
        await get_connections()

        # Update job status to cancelled
        job_data = await redis_client.get(f"job:{job_id}")
        if not job_data:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

        job_status = json.loads(job_data)
        if job_status["status"] == "processing":
            raise HTTPException(status_code=400, detail="Cannot cancel job that is already processing")

        job_status.update({
            "status": "cancelled",
            "updated_at": time.time()
        })

        await redis_client.setex(
            f"job:{job_id}",
            RESULT_TTL,
            json.dumps(job_status)
        )

        logger.info(f"Job {job_id} cancelled")
        return {"message": f"Job {job_id} cancelled successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cancel job: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8010)