#!/usr/bin/env python3
"""
API Schemas for Unified YOLO+LLM Decision Service
Pydantic models for request/response validation
"""

from typing import Optional, List, Dict, Any, Union, Literal
from pydantic import BaseModel, Field
import time


# === Core Data Structures ===

class ImageSpec(BaseModel):
    """Image data specification"""
    base64: str = Field(..., description="Base64 encoded image data")
    format: str = Field(default="png", description="Image format (png, jpg, etc)")


class CaptureSpec(BaseModel):
    """Screen capture specification with coordinate system info"""
    mode: Literal["full", "active_window", "region"] = Field(..., description="Capture mode")
    screen_size: List[int] = Field(..., description="Screen logical size [width, height]")
    window_offset: Optional[List[int]] = Field(None, description="Window offset [x, y] for window/region mode")
    window_size: Optional[List[int]] = Field(None, description="Window size [width, height] for window/region mode")
    dpr: float = Field(default=1.0, description="Device pixel ratio")


class ContextSpec(BaseModel):
    """Workflow and task context"""
    workflow_id: Optional[str] = Field(None, description="Workflow identifier")
    step_id: Optional[str] = Field(None, description="Current step identifier")
    goal: str = Field(..., description="Task goal/intent")
    intent: Optional[str] = Field(None, description="Specific action intent")
    vars: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Workflow variables")
    history: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Action history")
    allow_rewrite: bool = Field(default=False, description="Allow AutoStep rewrite suggestions")
    dom_hints: Optional[Dict[str, List[str]]] = Field(None, description="DOM hints from extension/replay")


# === NEW: Looser context for /v1/verify ===
class VerifyContextSpec(BaseModel):
    """Lightweight context for verification step; all optional."""
    workflow_id: Optional[str] = Field(None, description="Workflow identifier")
    step_id: Optional[str] = Field(None, description="Current step identifier")
    goal: Optional[str] = Field(None, description="(Optional) original goal")
    intent: Optional[str] = Field(None, description="(Optional) original intent")
    vars: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Workflow variables")
    history: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Action history")
    # 不需要 allow_rewrite/dom_hints；verify 只做结果校验


class YoloOptionsSpec(BaseModel):
    """YOLO detection options"""
    conf: float = Field(default=0.35, description="Confidence threshold")
    iou: float = Field(default=0.45, description="IOU threshold")


class OptionsSpec(BaseModel):
    """Request options"""
    mode: Literal["pick", "explain_all"] = Field(default="pick", description="Mode switch: normal pick (default) or explain_all")
    timeout_ms: int = Field(default=3500, description="Request timeout in milliseconds")
    max_candidates: int = Field(default=32, description="Maximum number of candidates")
    yolo: YoloOptionsSpec = Field(default_factory=YoloOptionsSpec)
    llm_provider: str = Field(default="gemini", description="LLM provider")
    llm_method: str = Field(default="auto", description="LLM method: direct|auto|mq")
    llm_timeout_ms: int = Field(default=30000, description="LLM-specific timeout in milliseconds")
    llm_topk_crops: int = Field(default=0, description="Number of top candidate crops to send to LLM (0 = overlay only)")
    pick_min_conf: Optional[float] = Field(default=0.6, description="Minimum confidence gate for pick mode (default 0.6); candidates below this threshold return action=none")
    return_overlay: bool = Field(default=False, description="Return annotated overlay image")


# === Anchor System ===

class AnchorDescriptors(BaseModel):
    """Anchor descriptors for matching"""
    template_hash: Optional[str] = Field(None, description="Template hash")
    orb: Optional[Dict[str, Any]] = Field(None, description="ORB feature data")
    color_hist: Optional[str] = Field(None, description="Color histogram hash")


class NormalizationRef(BaseModel):
    """Normalization reference for anchor coordinates"""
    kind: Literal["screen", "window", "region"] = Field(..., description="Reference type")
    w: int = Field(..., description="Reference width")
    h: int = Field(..., description="Reference height")


class AnchorSpec(BaseModel):
    """Known anchor specification"""
    id: str = Field(..., description="Anchor identifier")
    fingerprint: str = Field(..., description="Anchor fingerprint")
    norm_ref: NormalizationRef = Field(..., description="Normalization reference")
    descriptors: Optional[AnchorDescriptors] = Field(None)
    norm_bbox: Optional[List[float]] = Field(None, description="Normalized bounding box [x1,y1,x2,y2]")
    version: int = Field(default=1, description="Anchor version")


class AnchorProposal(BaseModel):
    """Proposed anchor for future use"""
    id: str = Field(..., description="Proposed anchor ID")
    type: str = Field(default="compound", description="Anchor type")
    descriptors: AnchorDescriptors = Field(..., description="Anchor descriptors")
    norm_ref: NormalizationRef = Field(..., description="Normalization reference")
    norm_bbox: List[float] = Field(..., description="Normalized bounding box")
    dom_hints: Optional[Dict[str, List[str]]] = Field(None, description="DOM hints")


class AnchorDelta(BaseModel):
    """Anchor update information"""
    id: str = Field(..., description="Anchor ID")
    norm_bbox: List[float] = Field(..., description="Updated normalized bbox")
    descriptors_delta: Optional[Dict[str, str]] = Field(None, description="Descriptor updates")
    version: int = Field(..., description="New version number")


# === Decision Making ===

class DecisionSpec(BaseModel):
    """LLM decision output"""
    action: str = Field(..., description="Action type (e.g., 'click')")
    bbox_in_capture: Optional[List[int]] = Field(None, description="Bounding box in capture coordinates")
    point_in_capture: List[int] = Field(..., description="Click point in capture coordinates")
    confidence: float = Field(..., description="Decision confidence score")
    reason: str = Field(..., description="Decision reasoning")


class MappingHint(BaseModel):
    """Coordinate mapping guidance for client"""
    apply_window_offset: bool = Field(..., description="Whether to apply window offset")
    expects_dpr: float = Field(..., description="Expected DPR for coordinate scaling")


class VerificationPlan(BaseModel):
    """Post-action verification plan"""
    expect_text_any: Optional[List[str]] = Field(None, description="Expected text to appear")
    expect_absent: Optional[List[str]] = Field(None, description="Text that should be absent")
    timeout_ms: int = Field(default=5000, description="Verification timeout")
    post_delay_ms: int = Field(default=300, description="Delay before verification")


class TelemetryInfo(BaseModel):
    """Request telemetry information"""
    req_id: str = Field(..., description="Request ID")
    cache_hit: bool = Field(default=False, description="Whether anchor cache was hit")
    stage_lat_ms: Dict[str, int] = Field(default_factory=dict, description="Latency per stage")


# === API Requests ===

class PickRequest(BaseModel):
    """Request for /v1/pick endpoint"""
    image: ImageSpec = Field(..., description="Input image")
    capture: Optional[CaptureSpec] = Field(None, description="Capture specification (optional - will be inferred from image if missing)")
    context: ContextSpec = Field(..., description="Task context")
    anchors_known: Optional[List[AnchorSpec]] = Field(default_factory=list, description="Known anchors for fast matching")
    options: OptionsSpec = Field(default_factory=OptionsSpec, description="Request options")
    idempotency_key: str = Field(..., description="Idempotency key for request deduplication")


class VerifyRequest(BaseModel):
    """Request for /v1/verify endpoint"""
    image: ImageSpec = Field(..., description="Post-action screenshot")
    capture: CaptureSpec = Field(..., description="Capture specification")
    context: Optional[VerifyContextSpec] = Field(None, description="Task context (optional)")
    expected: Dict[str, Any] = Field(..., description="Expected verification criteria")
    clicked: Dict[str, Any] = Field(..., description="Information about the click performed")


class AnchorResolveRequest(BaseModel):
    """Request for /v1/anchors/resolve endpoint"""
    image: ImageSpec = Field(..., description="Input image")
    anchors: List[AnchorSpec] = Field(..., description="Anchors to resolve")
    capture: CaptureSpec = Field(..., description="Capture specification")


class AutoStepPatchRequest(BaseModel):
    """Request for /v1/autostep/patch-proposal endpoint"""
    context: ContextSpec = Field(..., description="Task context")
    failure_info: Dict[str, Any] = Field(..., description="Failure information and trajectory")
    last_image: Optional[ImageSpec] = Field(None, description="Last failure screenshot")


class AutoStepRequest(BaseModel):
    """Request for /v1/autostep endpoint (planner_next/planner_report)."""
    phase: Literal["planner_next", "planner_report"] = Field(..., description="Planner phase")
    goal: Optional[str] = Field(None, description="Task goal")
    platform_id: Optional[str] = Field(None, description="Platform identifier")
    sig_key: Optional[str] = Field(None, description="UI signature key")
    observation: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Current observation")
    blacklist: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Rejected candidates")

    # planner_next image input (preferred)
    image: Optional[ImageSpec] = Field(None, description="Image payload")

    # Compatibility input for OpenAI-style multimodal content
    content: Optional[List[Dict[str, Any]]] = Field(default=None, description="OpenAI-style content list")
    messages: Optional[List[Dict[str, Any]]] = Field(default=None, description="Optional OpenAI-style messages")

    # planner_report fields
    tool_call: Optional[Dict[str, Any]] = Field(default=None, description="Executed tool call")
    result: Optional[Dict[str, Any]] = Field(default=None, description="Execution result")
    observation_after: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Post-action observation")

    # tracing and idempotency
    trace: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Tracing metadata")
    request_id: Optional[str] = Field(default=None, description="Trace request id")
    operation_id: Optional[str] = Field(default=None, description="Operation id")

    # optional provider/model hints
    provider: Optional[str] = Field(default=None, description="Requested provider")
    model: Optional[str] = Field(default=None, description="Requested model")

    class Config:
        extra = "allow"


# === API Responses ===

class PickResponse(BaseModel):
    """Response from /v1/pick endpoint"""
    decision: DecisionSpec = Field(..., description="Decision made by the system")
    mapping_hint: MappingHint = Field(..., description="Coordinate mapping guidance")
    anchor_proposal: Optional[AnchorProposal] = Field(None, description="Proposed anchor for learning")
    verification_plan: VerificationPlan = Field(..., description="Post-action verification plan")
    telemetry: TelemetryInfo = Field(..., description="Request telemetry")


class VerifyResponse(BaseModel):
    """Response from /v1/verify endpoint"""
    pass_: bool = Field(..., alias="pass", description="Whether verification passed")
    reason: str = Field(..., description="Verification result reason")
    lock_anchor: Optional[AnchorDelta] = Field(None, description="Anchor to lock/update")
    telemetry: Dict[str, Any] = Field(default_factory=dict, description="Verification telemetry")


class AnchorResolveResponse(BaseModel):
    """Response from /v1/anchors/resolve endpoint"""
    hit: bool = Field(..., description="Whether anchor was resolved")
    point_in_capture: Optional[List[int]] = Field(None, description="Resolved point coordinates")
    confidence: Optional[float] = Field(None, description="Resolution confidence")
    anchor_id: Optional[str] = Field(None, description="ID of resolved anchor")


class AutoStepPatchResponse(BaseModel):
    """Response from /v1/autostep/patch-proposal endpoint"""
    patches: List[Dict[str, Any]] = Field(default_factory=list, description="Proposed patches")
    risk: Literal["low", "medium", "high"] = Field(..., description="Risk level of patches")
    reason: str = Field(..., description="Patch reasoning")


# === Error Handling ===

class ErrorInfo(BaseModel):
    """Error information structure"""
    code: str = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    hint: Optional[str] = Field(None, description="Recovery hint")
    req_id: Optional[str] = Field(None, description="Request ID")


class ErrorResponse(BaseModel):
    """Standard error response"""
    error: ErrorInfo = Field(..., description="Error details")


# === Health and Metrics ===

class HealthStatus(BaseModel):
    """Service health status"""
    ok: bool = Field(..., description="Overall health status")
    deps: Dict[str, Any] = Field(default_factory=dict, description="Dependency status")
    timestamp: float = Field(default_factory=time.time, description="Status timestamp")


class MetricsInfo(BaseModel):
    """Service metrics information"""
    qps: Dict[str, float] = Field(default_factory=dict, description="Queries per second by endpoint")
    latency_ms: Dict[str, Dict[str, float]] = Field(default_factory=dict, description="Latency percentiles")
    hit_ratios: Dict[str, float] = Field(default_factory=dict, description="Cache hit ratios")
    error_rates: Dict[str, float] = Field(default_factory=dict, description="Error rates by type")
