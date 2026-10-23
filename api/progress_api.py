#!/usr/bin/env python3
"""
Progress API - Server-Sent Events (SSE) for real-time job progress tracking
Provides real-time updates for queued YOLO processing jobs
"""

import asyncio
import json
import time
import logging
from typing import AsyncGenerator, Dict, Any
import os

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
SSE_HEARTBEAT_INTERVAL = 30  # seconds
SSE_TIMEOUT = 300  # 5 minutes max connection time

app = FastAPI(title="YOLO Progress API", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Redis connection
redis_client = None


async def get_redis_client():
    """Get Redis client instance"""
    global redis_client
    if redis_client is None:
        redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
        await redis_client.ping()
        logger.info("Redis connection established")
    return redis_client


@app.on_event("startup")
async def startup_event():
    """Initialize Redis connection on startup"""
    await get_redis_client()


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up Redis connection on shutdown"""
    global redis_client
    if redis_client:
        await redis_client.close()


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        redis = await get_redis_client()
        await redis.ping()
        return {"status": "healthy", "timestamp": time.time()}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Service unhealthy: {e}")


async def job_progress_stream(job_id: str) -> AsyncGenerator[str, None]:
    """
    Generate SSE stream for job progress updates

    Args:
        job_id: Job identifier to track

    Yields:
        SSE formatted messages with job progress updates
    """
    redis = await get_redis_client()
    pubsub = redis.pubsub()

    try:
        # Subscribe to job progress channel
        progress_channel = f"progress:{job_id}"
        await pubsub.subscribe(progress_channel)

        logger.info(f"SSE stream started for job {job_id}")

        # Send initial job status
        job_data = await redis.get(f"job:{job_id}")
        if job_data:
            job_status = json.loads(job_data)
            initial_event = {
                "event": "job_status",
                "job_id": job_id,
                "status": job_status["status"],
                "progress": job_status.get("progress", 0.0),
                "created_at": job_status["created_at"],
                "updated_at": job_status["updated_at"]
            }
            yield f"data: {json.dumps(initial_event)}\n\n"
        else:
            error_event = {
                "event": "error",
                "job_id": job_id,
                "message": "Job not found",
                "timestamp": time.time()
            }
            yield f"data: {json.dumps(error_event)}\n\n"
            return

        start_time = time.time()
        last_heartbeat = time.time()

        # Listen for progress updates
        while True:
            # Check timeout
            if time.time() - start_time > SSE_TIMEOUT:
                timeout_event = {
                    "event": "timeout",
                    "job_id": job_id,
                    "message": "SSE connection timeout",
                    "timestamp": time.time()
                }
                yield f"data: {json.dumps(timeout_event)}\n\n"
                break

            # Send heartbeat
            if time.time() - last_heartbeat > SSE_HEARTBEAT_INTERVAL:
                heartbeat_event = {
                    "event": "heartbeat",
                    "timestamp": time.time()
                }
                yield f"data: {json.dumps(heartbeat_event)}\n\n"
                last_heartbeat = time.time()

            # Check for messages with timeout
            try:
                message = await asyncio.wait_for(pubsub.get_message(), timeout=5.0)

                if message and message['type'] == 'message':
                    # Parse progress update
                    try:
                        progress_data = json.loads(message['data'])

                        # Forward progress event
                        progress_event = {
                            "event": "progress",
                            **progress_data
                        }
                        yield f"data: {json.dumps(progress_event)}\n\n"

                        # Check if job is completed or failed
                        if progress_data.get("status") in ["completed", "failed", "cancelled"]:
                            # Send final status and close
                            final_event = {
                                "event": "job_complete",
                                "job_id": job_id,
                                "final_status": progress_data["status"],
                                "timestamp": time.time()
                            }
                            yield f"data: {json.dumps(final_event)}\n\n"
                            break

                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse progress message: {e}")

            except asyncio.TimeoutError:
                # No message received, continue loop
                continue

            except Exception as e:
                logger.error(f"Error in progress stream for job {job_id}: {e}")
                error_event = {
                    "event": "error",
                    "job_id": job_id,
                    "message": str(e),
                    "timestamp": time.time()
                }
                yield f"data: {json.dumps(error_event)}\n\n"
                break

    except Exception as e:
        logger.error(f"SSE stream error for job {job_id}: {e}")
        error_event = {
            "event": "stream_error",
            "job_id": job_id,
            "message": str(e),
            "timestamp": time.time()
        }
        yield f"data: {json.dumps(error_event)}\n\n"

    finally:
        # Clean up subscription
        await pubsub.unsubscribe(progress_channel)
        await pubsub.close()
        logger.info(f"SSE stream ended for job {job_id}")


@app.get("/progress/stream/{job_id}")
async def stream_job_progress(job_id: str):
    """
    Server-Sent Events endpoint for job progress tracking

    Args:
        job_id: Job identifier to track

    Returns:
        SSE stream with real-time progress updates
    """
    return StreamingResponse(
        job_progress_stream(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control"
        }
    )


@app.get("/progress/status/{job_id}")
async def get_job_progress(job_id: str):
    """
    Get current job progress status (non-streaming)

    Args:
        job_id: Job identifier

    Returns:
        Current job status and progress
    """
    try:
        redis = await get_redis_client()

        # Get job data
        job_data = await redis.get(f"job:{job_id}")
        if not job_data:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

        job_status = json.loads(job_data)

        # Get result if completed
        result = None
        if job_status["status"] == "completed":
            result_data = await redis.get(f"result:{job_id}")
            if result_data:
                result = json.loads(result_data)

        return {
            "job_id": job_id,
            "status": job_status["status"],
            "progress": job_status.get("progress", 0.0),
            "created_at": job_status["created_at"],
            "updated_at": job_status["updated_at"],
            "worker_id": job_status.get("worker_id"),
            "error": job_status.get("error"),
            "result": result,
            "timestamp": time.time()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get job progress for {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get job progress: {e}")


@app.get("/progress/active")
async def get_active_jobs():
    """
    Get list of all active jobs (queued or processing)

    Returns:
        List of active job statuses
    """
    try:
        redis = await get_redis_client()

        active_jobs = []
        cursor = 0

        # Scan for all job keys
        while True:
            cursor, keys = await redis.scan(cursor, match="job:*", count=100)

            for key in keys:
                job_data = await redis.get(key)
                if job_data:
                    job_status = json.loads(job_data)
                    if job_status["status"] in ["queued", "processing"]:
                        job_id = key.split(":", 1)[1]
                        active_jobs.append({
                            "job_id": job_id,
                            "status": job_status["status"],
                            "progress": job_status.get("progress", 0.0),
                            "created_at": job_status["created_at"],
                            "updated_at": job_status["updated_at"],
                            "worker_id": job_status.get("worker_id")
                        })

            if cursor == 0:
                break

        # Sort by creation time
        active_jobs.sort(key=lambda x: x["created_at"])

        return {
            "active_jobs": active_jobs,
            "count": len(active_jobs),
            "timestamp": time.time()
        }

    except Exception as e:
        logger.error(f"Failed to get active jobs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get active jobs: {e}")


@app.get("/progress/workers")
async def get_worker_status():
    """
    Get status of all active workers

    Returns:
        List of worker statuses
    """
    try:
        redis = await get_redis_client()

        workers = []
        cursor = 0

        # Scan for worker keys
        while True:
            cursor, keys = await redis.scan(cursor, match="worker:*", count=100)

            for key in keys:
                worker_data = await redis.get(key)
                if worker_data:
                    worker_info = json.loads(worker_data)
                    workers.append(worker_info)

            if cursor == 0:
                break

        return {
            "workers": workers,
            "count": len(workers),
            "timestamp": time.time()
        }

    except Exception as e:
        logger.error(f"Failed to get worker status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get worker status: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8011)