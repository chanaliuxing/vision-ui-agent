#!/usr/bin/env python3
"""
Hybrid Router - Smart sync/async path selection for YOLO processing
Routes requests to fast path (sync) or queue path (async) based on complexity
"""

import time
import uuid
import logging
from typing import Optional, Dict, Any
import httpx

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from schemas import PickRequest, PickResponse, ErrorResponse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Service endpoints
YOLO_API_URL = "http://localhost:8000"
QUEUE_API_URL = "http://localhost:8010"

# Route decision thresholds
FAST_PATH_THRESHOLDS = {
    "max_candidates": 20,      # Simple requests only
    "image_size_kb": 500,      # Small images only
    "timeout_ms": 5000,        # Quick responses only
    "complexity_score": 3.0    # Low complexity only
}

app = FastAPI(title="YOLO Hybrid Router", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RouteDecision(BaseModel):
    """Route decision result"""
    path: str  # "fast" or "queue"
    reason: str
    complexity_score: float
    estimated_time_ms: int


class HybridPickResponse(BaseModel):
    """Unified response for both sync and async paths"""
    # For sync responses
    decision: Optional[Dict[str, Any]] = None
    mapping_hint: Optional[Dict[str, Any]] = None
    telemetry: Optional[Dict[str, Any]] = None

    # For async responses
    job_id: Optional[str] = None
    status: str = "completed"  # completed|queued|processing|failed
    sse_url: Optional[str] = None
    estimated_wait_time_ms: Optional[int] = None

    # Common fields
    route_info: RouteDecision


def calculate_complexity_score(request: PickRequest) -> float:
    """Calculate request complexity score for routing decisions"""
    score = 0.0

    # Image size factor
    if hasattr(request.image, 'base64'):
        image_size_kb = len(request.image.base64) / 1024
        score += min(image_size_kb / 100, 3.0)  # 0-3 points for image size

    # Max candidates factor
    max_candidates = request.options.max_candidates if request.options else 32
    score += min(max_candidates / 10, 2.0)  # 0-2 points for candidates

    # Context complexity
    if request.context:
        if request.context.history:
            score += min(len(request.context.history) / 5, 1.0)  # 0-1 for history
        if request.context.dom_hints:
            score += 0.5  # +0.5 for DOM hints complexity

    # Anchor complexity
    if request.anchors_known:
        score += min(len(request.anchors_known) / 3, 1.0)  # 0-1 for anchors

    # LLM timeout factor
    if request.options and request.options.llm_timeout_ms > 15000:
        score += 1.0  # +1 for long timeout requests

    return score


def should_use_fast_path(request: PickRequest) -> RouteDecision:
    """Decide whether to use fast path (sync) or queue path (async)"""
    complexity_score = calculate_complexity_score(request)

    # Check thresholds
    reasons = []

    # Image size check
    if hasattr(request.image, 'base64'):
        image_size_kb = len(request.image.base64) / 1024
        if image_size_kb > FAST_PATH_THRESHOLDS["image_size_kb"]:
            reasons.append(f"image too large ({image_size_kb:.1f}KB > {FAST_PATH_THRESHOLDS['image_size_kb']}KB)")

    # Max candidates check
    max_candidates = request.options.max_candidates if request.options else 10  # Default to 10 for fast path
    if max_candidates > FAST_PATH_THRESHOLDS["max_candidates"]:
        reasons.append(f"too many candidates ({max_candidates} > {FAST_PATH_THRESHOLDS['max_candidates']})")

    # Timeout check
    timeout_ms = request.options.timeout_ms if request.options else 3500
    if timeout_ms > FAST_PATH_THRESHOLDS["timeout_ms"]:
        reasons.append(f"long timeout ({timeout_ms}ms > {FAST_PATH_THRESHOLDS['timeout_ms']}ms)")

    # Complexity check
    if complexity_score > FAST_PATH_THRESHOLDS["complexity_score"]:
        reasons.append(f"high complexity ({complexity_score:.1f} > {FAST_PATH_THRESHOLDS['complexity_score']})")

    # Decision
    if reasons:
        return RouteDecision(
            path="queue",
            reason="; ".join(reasons),
            complexity_score=complexity_score,
            estimated_time_ms=int(5000 + complexity_score * 3000)
        )
    else:
        return RouteDecision(
            path="fast",
            reason="simple request within fast path thresholds",
            complexity_score=complexity_score,
            estimated_time_ms=int(1000 + complexity_score * 500)
        )


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": time.time()}


@app.post("/v1/pick", response_model=HybridPickResponse)
async def hybrid_pick(request: PickRequest):
    """
    Hybrid pick endpoint - routes to fast path or queue based on complexity
    Maintains backward compatibility with existing clients
    """
    # Make routing decision
    route_decision = should_use_fast_path(request)

    logger.info(f"Route decision: {route_decision.path} - {route_decision.reason}")

    if route_decision.path == "fast":
        # Fast path: direct sync call to YOLO API
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{YOLO_API_URL}/v1/pick",
                    json=request.dict(),
                    headers={"Content-Type": "application/json"}
                )

                if response.status_code == 200:
                    yolo_result = response.json()
                    if yolo_result.get("ok"):
                        data = yolo_result["data"]
                        return HybridPickResponse(
                            decision=data.get("decision"),
                            mapping_hint=data.get("mapping_hint"),
                            telemetry=data.get("telemetry"),
                            status="completed",
                            route_info=route_decision
                        )
                    else:
                        raise HTTPException(
                            status_code=500,
                            detail=f"YOLO API error: {yolo_result.get('error', 'Unknown error')}"
                        )
                else:
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"YOLO API failed: {response.text}"
                    )

        except httpx.TimeoutException:
            logger.warning("Fast path timeout, falling back to queue")
            route_decision.path = "queue"
            route_decision.reason += " (fast path timeout)"
        except Exception as e:
            logger.error(f"Fast path error: {e}")
            raise HTTPException(status_code=500, detail=f"Fast path failed: {e}")

    if route_decision.path == "queue":
        # Queue path: submit to async processing
        try:
            job_id = str(uuid.uuid4())

            # Create queue request data
            queue_request_data = {
                "job_id": job_id,
                "request_data": request.dict(),
                "priority": min(int(route_decision.complexity_score), 10),
                "timeout_ms": route_decision.estimated_time_ms
            }

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{QUEUE_API_URL}/queue/submit",
                    json=queue_request_data,
                    headers={"Content-Type": "application/json"}
                )

                if response.status_code == 200:
                    queue_result = response.json()
                    return HybridPickResponse(
                        job_id=queue_result["job_id"],
                        status=queue_result["status"],
                        sse_url=queue_result.get("sse_url"),
                        estimated_wait_time_ms=queue_result.get("estimated_wait_time_ms"),
                        route_info=route_decision
                    )
                else:
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Queue API failed: {response.text}"
                    )

        except Exception as e:
            logger.error(f"Queue path error: {e}")
            raise HTTPException(status_code=500, detail=f"Queue path failed: {e}")


@app.get("/v1/job/{job_id}")
async def get_job_result(job_id: str):
    """Get result of an async job"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{QUEUE_API_URL}/queue/status/{job_id}")

            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Job status query failed: {response.text}"
                )

    except Exception as e:
        logger.error(f"Job status error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get job status: {e}")


@app.get("/route/config")
async def get_route_config():
    """Get current routing configuration"""
    return {
        "fast_path_thresholds": FAST_PATH_THRESHOLDS,
        "yolo_api_url": YOLO_API_URL,
        "queue_api_url": QUEUE_API_URL,
        "timestamp": time.time()
    }


@app.post("/route/config")
async def update_route_config(config: Dict[str, Any]):
    """Update routing thresholds (admin endpoint)"""
    global FAST_PATH_THRESHOLDS

    updated = {}
    for key, value in config.items():
        if key in FAST_PATH_THRESHOLDS:
            FAST_PATH_THRESHOLDS[key] = value
            updated[key] = value

    logger.info(f"Updated routing config: {updated}")
    return {"updated": updated, "current": FAST_PATH_THRESHOLDS}


@app.get("/route/test")
async def test_route_decision(
    max_candidates: int = 10,
    image_size_kb: float = 100.0,
    timeout_ms: int = 3000,
    complexity_bonus: float = 0.0
):
    """Test routing decision with simulated parameters"""
    # Create a mock request for testing
    from schemas import ImageSpec, ContextSpec, OptionsSpec

    mock_image = ImageSpec(
        base64="x" * int(image_size_kb * 1024),  # Simulate image size
        format="png"
    )

    mock_request = PickRequest(
        image=mock_image,
        context=ContextSpec(goal="test routing"),
        options=OptionsSpec(
            max_candidates=max_candidates,
            timeout_ms=timeout_ms
        ),
        idempotency_key="test-route"
    )

    decision = should_use_fast_path(mock_request)
    decision.complexity_score += complexity_bonus

    return {
        "parameters": {
            "max_candidates": max_candidates,
            "image_size_kb": image_size_kb,
            "timeout_ms": timeout_ms,
            "complexity_bonus": complexity_bonus
        },
        "decision": decision,
        "thresholds": FAST_PATH_THRESHOLDS
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8020)