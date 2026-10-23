#!/usr/bin/env python3
"""
Orchestrator - Main Coordination Layer
Coordinates YOLO detection, LLM decision making, and anchor learning
"""

import time
import uuid
import os
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import logging
from yolo.logging_setup import get_logger

# === Safe lowercase helper ===
def _lower_safe(x: Any) -> str:
    return x.lower() if isinstance(x, str) else ""

def _sanitize_hints(dom_hints: Any) -> Optional[str]:
    """安全处理 DOM hints，确保不会因为 None 或非字符串导致异常"""
    if not dom_hints:
        return None
    if isinstance(dom_hints, dict):
        text_hint = dom_hints.get("text")
        return text_hint if isinstance(text_hint, str) else None
    return str(dom_hints) if dom_hints else None

from schemas import (
    PickRequest, PickResponse, VerifyRequest, VerifyResponse,
    AnchorResolveRequest, AnchorResolveResponse,
    DecisionSpec, MappingHint, TelemetryInfo
)
from coordinate_utils import get_coordinate_transformer, transform_response_coordinates, validate_capture_spec
from telemetry import get_telemetry_system, StageTracker

logger = logging.getLogger(__name__)
jsonlog = get_logger()


class Orchestrator:
    """Main orchestration service for unified YOLO+LLM decisions"""

    def __init__(self, anchors_service, detector_service, verification_service, llm_client):
        """
        Initialize orchestrator with service dependencies

        Args:
            anchors_service: AnchorsService instance
            detector_service: DetectorService instance
            verification_service: VerificationService instance
            llm_client: LLM client for decision making
        """
        self.anchors = anchors_service
        self.detector = detector_service
        self.verifier = verification_service
        self.llm = llm_client

        # Cache for idempotency
        self._request_cache = {}

        # Telemetry system
        self.telemetry = get_telemetry_system()

        logger.info("Orchestrator initialized successfully")

    def pick(self, img_bgr: np.ndarray, request: PickRequest) -> Dict[str, Any]:
        """
        Main pick endpoint - coordinates YOLO+LLM decision making

        Args:
            img_bgr: Input image in BGR format
            request: Pick request with context and options

        Returns:
            Pick response dictionary
        """
        t_start = time.time()
        req_id = request.idempotency_key
        mode = (getattr(getattr(request, "options", None), "mode", None) or "pick")
        cache_key = f"{mode}:{req_id}"

        # Start telemetry tracking
        capture_mode = "unknown" if request.capture is None else request.capture.mode
        self.telemetry.start_request_tracking(req_id, "pick", {
            "goal": request.context.goal,
            "intent": request.context.intent,
            "capture_mode": capture_mode,
            "mode": mode,
        })

        try:
            # Validate and handle capture specification
            if request.capture is None:
                # Server-side hardening: infer missing capture metadata from image
                logger.warning(f"Request {req_id} missing capture metadata, attempting to infer from image")
                try:
                    # Get image dimensions from the uploaded image
                    import base64
                    import cv2
                    from PIL import Image
                    import io

                    # Decode image to get dimensions
                    image_data = request.image.base64
                    if image_data.startswith('data:image'):
                        image_data = image_data.split(',', 1)[1]

                    image_bytes = base64.b64decode(image_data)
                    pil_image = Image.open(io.BytesIO(image_bytes))
                    width, height = pil_image.size

                    # Create fallback capture specification as a proper CaptureSpec object
                    from schemas import CaptureSpec
                    inferred_capture = CaptureSpec(
                        mode="full",
                        screen_size=[width, height],
                        dpr=1.0
                    )

                    # Replace the None capture with our inferred object
                    request.capture = inferred_capture
                    capture_spec = inferred_capture.dict()

                    logger.info(f"Inferred capture metadata for {req_id}: {capture_spec}")
                except Exception as infer_error:
                    error_msg = f"Missing capture metadata and inference failed: {infer_error}"
                    logger.error(error_msg)
                    self.telemetry.record_error("MISSING_CAPTURE_SPEC", error_msg, req_id=req_id)
                    return self._create_error_response(error_msg, request, t_start)
            else:
                capture_spec = request.capture.dict()

            if not validate_capture_spec(capture_spec):
                error_msg = "Invalid capture specification"
                self.telemetry.record_error("INVALID_CAPTURE_SPEC", error_msg, req_id=req_id)
                return self._create_error_response(error_msg, request, t_start)

            # Check idempotency cache (mode-scoped)
            if cache_key in self._request_cache:
                cached_result = self._request_cache[cache_key]
                logger.info(f"Returning cached result for request {req_id}")
                self.telemetry.record_cache_operation(hit=True)
                # Mark cache hit in telemetry of the cached payload
                try:
                    if isinstance(cached_result, dict):
                        cached_result.setdefault("telemetry", {})
                        cached_result["telemetry"]["cache_hit"] = True
                except Exception:
                    pass
                self.telemetry.finish_request_tracking(req_id, success=True)
                # Transform coordinates for cached result
                return transform_response_coordinates(cached_result, capture_spec)

            # Record cache miss
            self.telemetry.record_cache_operation(hit=False)

            # Phase 1: Quick anchor matching (skip for explain_all)
            if mode != "explain_all" and request.anchors_known:
                with StageTracker(req_id, "anchor_matching"):
                    anchor_result = self.anchors.quick_match(img_bgr, [spec.dict() for spec in request.anchors_known])
                    if anchor_result:
                        point, confidence, anchor_id = anchor_result
                        result = self._create_anchor_hit_response(
                            point, confidence, anchor_id, request, t_start
                        )
                        self._cache_result(cache_key, result)
                        self.telemetry.finish_request_tracking(req_id, success=True)
                        return transform_response_coordinates(result, capture_spec)

            # Phase 2: YOLO detection
            t_yolo_start = time.time()
            with StageTracker(req_id, "yolo_detection"):
                candidates = self.detector.run_yolo(
                    img_bgr,
                    conf=request.options.yolo.conf,
                    iou=request.options.yolo.iou,
                    imgsz=1280,  # Could be made configurable
                    max_det=300
                )
            t_yolo_end = time.time()

            # Filter and limit candidates
            candidates = self.detector.filter_by_classes(
                candidates,
                preferred_classes=self._extract_preferred_classes(request.context),
                negative_classes=self._extract_negative_classes(request.context)
            )

            explain_candidates: Optional[List] = None
            if mode == "explain_all":
                # For explain_all we draw/return as many elements as possible.
                # Number detections in reading order (top->bottom, left->right) for stable IDs.
                def _tl_key(c):
                    x1, y1, x2, y2 = [int(v) for v in c.xyxy]
                    return (y1, x1)

                explain_candidates = sorted(list(candidates), key=_tl_key)

            # Remove candidate limiting - show all detected elements to avoid missing important UI
            # candidates = self.detector.limit_candidates(candidates, request.options.max_candidates)

            # Save overlay and YOLO JSON early (regardless of LLM path)
            try:
                if candidates:
                    # Select list to save (explain mode or raw candidates)
                    raw_list = explain_candidates if explain_candidates is not None else candidates
                    
                    # Sort by reading order (Top-Left -> Bottom-Right) for stable IDs
                    # This matches the logic used in _make_llm_decision and ensures logical numbering
                    def _tl_key_save(c):
                        x1, y1, x2, y2 = [int(v) for v in c.xyxy]
                        return (y1, x1)
                    
                    overlay_candidates = sorted(list(raw_list), key=_tl_key_save)
                    
                    overlay_img = self._create_overlay_image(img_bgr, overlay_candidates)
                    import cv2, os, json as _json
                    key = request.idempotency_key
                    out_dir = os.path.join("out", "overlays")
                    os.makedirs(out_dir, exist_ok=True)
                    cv2.imwrite(os.path.join(out_dir, f"{key}_overlay.png"), overlay_img)
                    # Save YOLO candidate JSON for inspection
                    dets = []
                    for i, c in enumerate(overlay_candidates, start=1):
                        dets.append({
                            "id": i,
                            "xyxy": [int(v) for v in c.xyxy],
                            "cls": getattr(c, 'cls', None),
                            "score": float(getattr(c, 'score', 0.0)),
                        })
                    with open(os.path.join(out_dir, f"{key}_yolo.json"), "w", encoding="utf-8") as f:
                        _json.dump({"candidates": dets}, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

            if not candidates:
                # No candidates found
                self.telemetry.record_error("NO_CANDIDATES", "YOLO detection found no candidates", req_id=req_id)
                result = self._create_no_candidates_response(request, t_start)
                self._cache_result(cache_key, result)
                self.telemetry.finish_request_tracking(req_id, success=False)
                return result

            # Phase 3: LLM
            if mode == "explain_all":
                t_llm_start = time.time()
                with StageTracker(req_id, "llm_explain_all"):
                    explain_result = self._make_llm_explain_all(
                        img_bgr,
                        explain_candidates if explain_candidates is not None else candidates,
                        request,
                    )
                t_llm_end = time.time()

                result = self._create_explain_all_response(
                    explain_candidates if explain_candidates is not None else candidates,
                    explain_result,
                    request,
                    t_start,
                    yolo_ms=(t_yolo_end - t_yolo_start),
                    llm_ms=(t_llm_end - t_llm_start),
                )

                self._cache_result(cache_key, result)
                self.telemetry.finish_request_tracking(req_id, success=True)
                return transform_response_coordinates(result, capture_spec)

            t_llm_start = time.time()
            with StageTracker(req_id, "llm_decision"):
                decision_result = self._make_llm_decision(img_bgr, candidates, request)
            t_llm_end = time.time()

            if not decision_result:
                # LLM decision failed
                self.telemetry.record_error("LLM_DECISION_FAILED", "LLM failed to make decision", req_id=req_id)
                result = self._create_llm_failure_response(candidates, request, t_start)
                self._cache_result(cache_key, result)
                self.telemetry.finish_request_tracking(req_id, success=False)
                return result

            selected_candidate, llm_reasoning = decision_result

            # Confidence gate enabled by default (0.6) to prevent low-confidence clicks.
            try:
                raw_min_pick_conf = getattr(request.options, "pick_min_conf", None)
                min_pick_conf = float(raw_min_pick_conf) if raw_min_pick_conf is not None else 0.6
            except Exception:
                min_pick_conf = 0.6
            cand_conf = float(getattr(selected_candidate, "score", 0.0))
            if cand_conf < min_pick_conf:
                result = self._create_low_confidence_response(
                    request=request,
                    t_start=t_start,
                    candidate_conf=cand_conf,
                    min_conf=min_pick_conf,
                )
                self._cache_result(cache_key, result)
                self.telemetry.finish_request_tracking(req_id, success=False)
                return result

            # Phase 4: Generate anchor proposal
            with StageTracker(req_id, "anchor_proposal"):
                anchor_proposal = self.anchors.propose_anchor(
                    img_bgr,
                    selected_candidate.xyxy,
                    request.context.dom_hints
                )

            # Phase 5: Create verification plan
            with StageTracker(req_id, "verification_plan"):
                verification_plan = self.verifier.plan_for(
                    request.context.dict(),
                    selected_candidate.to_dict()
                )

            # Phase 6: Assemble response
            result = self._create_success_response(
                selected_candidate, anchor_proposal, verification_plan,
                llm_reasoning, request, t_start, t_yolo_end - t_yolo_start, t_llm_end - t_llm_start
            )

            self._cache_result(cache_key, result)
            self.telemetry.finish_request_tracking(req_id, success=True)

            # Transform coordinates before returning
            return transform_response_coordinates(result, capture_spec)

        except Exception as e:
            logger.error(f"Pick operation failed: {e}")
            self.telemetry.record_error("PICK_OPERATION_FAILED", str(e), req_id=req_id)
            self.telemetry.finish_request_tracking(req_id, success=False)
            result = self._create_error_response(str(e), request, t_start)
            return result

    def verify(self, img_bgr: np.ndarray, request: VerifyRequest) -> Dict[str, Any]:
        """
        Verify action results and lock anchors

        Args:
            img_bgr: Post-action screenshot in BGR format
            request: Verify request with expectations

        Returns:
            Verify response dictionary
        """
        try:
            t_start = time.time()

            # Perform verification
            pass_result, reason, lock_anchor = self.verifier.verify(
                img_bgr, request.expected
            )

            # Create response
            result = {
                "pass": pass_result,
                "reason": reason,
                "lock_anchor": lock_anchor,
                "telemetry": {
                    "latency_ms": int((time.time() - t_start) * 1000),
                    "timestamp": time.time()
                }
            }

            logger.info(f"Verification {'passed' if pass_result else 'failed'}: {reason}")
            try:
                jsonlog.info(
                    "verify.result",
                    svc="yoloapi",
                    event="verify.result",
                    req_id=(getattr(request, 'idempotency_key', None) or f"verify-{int(time.time()*1000)}"),
                    pass_bool=bool(pass_result),
                    latency_ms=result["telemetry"]["latency_ms"],
                    lock_anchor=bool(lock_anchor),
                )
            except Exception:
                pass
            return result

        except Exception as e:
            logger.error(f"Verification failed: {e}")
            return {
                "pass": False,
                "reason": f"Verification error: {e}",
                "lock_anchor": None,
                "telemetry": {"latency_ms": -1, "error": str(e)}
            }

    def resolve_anchors(self, img_bgr: np.ndarray, request: AnchorResolveRequest) -> Dict[str, Any]:
        """
        Fast anchor-only resolution

        Args:
            img_bgr: Input image in BGR format
            request: Anchor resolve request

        Returns:
            Anchor resolve response dictionary
        """
        try:
            # Convert request anchors to dict format
            anchor_specs = [anchor.dict() for anchor in request.anchors]

            # Attempt anchor matching
            result = self.anchors.quick_match(img_bgr, anchor_specs)

            if result:
                point, confidence, anchor_id = result
                return {
                    "hit": True,
                    "point_in_capture": point,
                    "confidence": confidence,
                    "anchor_id": anchor_id
                }
            else:
                return {
                    "hit": False,
                    "point_in_capture": None,
                    "confidence": None,
                    "anchor_id": None
                }

        except Exception as e:
            logger.error(f"Anchor resolution failed: {e}")
            return {
                "hit": False,
                "point_in_capture": None,
                "confidence": 0.0,
                "anchor_id": None,
                "error": str(e)
            }

    def _make_llm_decision(self, img_bgr: np.ndarray, candidates: List, request: PickRequest) -> Optional[Tuple[Any, str]]:
        """
        Make LLM decision from candidates using visual analysis with hybrid MQ+direct routing
        Args:
            img_bgr: Image in BGR format
            candidates: List of detection candidates
            request: Pick request with context
        Returns:
            Tuple of (selected_candidate, reasoning) or None if failed
        """
        try:
            print(f"🎯 ORCHESTRATOR: _make_llm_decision called with {len(candidates)} candidates")

            import cv2
            import base64

            # Get LLM options from request
            options = request.options
            llm_method = options.llm_method  # auto|mq|direct
            llm_timeout_s = options.llm_timeout_ms / 1000.0
            topk_crops = min(options.llm_topk_crops, len(candidates))

            print(f"🎯 ORCHESTRATOR: LLM method={llm_method}, timeout={llm_timeout_s}s, topk={topk_crops}")

            # Create visual prompt for LLM
            goal = request.context.goal or "interact with the correct UI element"
            intent = getattr(request.context, 'intent', '') or ''

            # Select candidates for overlay/numbering
            # When topk_crops <= 0, we disable crops but still want all candidates in the overlay
            if topk_crops <= 0:
                top_candidates = list(candidates)
            else:
                top_candidates = sorted(candidates, key=lambda c: c.score, reverse=True)[:topk_crops]

            # Reorder for overlay and LLM numbering to match legacy (top->bottom then left->right)
            def _tl_key(c):
                x1, y1, x2, y2 = [int(v) for v in c.xyxy]
                return (y1, x1)
            ordered = sorted(list(top_candidates), key=_tl_key)

            visual_prompt = f"""Analyze screenshot. Goal: {goal}

Select the numbered element that best matches the goal. Keep reason under 5 words.

JSON format:
{{"decision": {{"click_id": "[number]", "reason": "max 5 words"}}}}

Example: {{"decision": {{"click_id": "3", "reason": "search input field"}}}}"""

            # Generate vision data: create overlay + candidate crops (based on ordered list)
            vision_data = self._create_vision_data_for_llm(img_bgr, ordered, req_id=request.idempotency_key)

            # Prepare messages for LLM (using Gemini-style parts format)
            messages = [
                {
                    "role": "user",
                    "parts": [
                        {"text": visual_prompt}
                        # Vision content will be added by HybridLLMClient
                    ]
                }
            ]

            print(f"🚀 ORCHESTRATOR: Calling hybrid LLM with method={llm_method}")
            print(f"🚀 ORCHESTRATOR: Goal = '{goal}', vision_items={len(vision_data) if vision_data else 0}")
            overlay_meta = {}
            try:
                if isinstance(vision_data, list) and vision_data:
                    m0 = (vision_data[0] or {}).get("meta") or {}
                    if isinstance(m0, dict):
                        overlay_meta = m0
            except Exception:
                overlay_meta = {}

            # Call hybrid LLM client with enhanced parameters
            response = self.llm.generate_response(
                messages=messages,
                vision=vision_data,
                timeout=int(llm_timeout_s),
                method=llm_method,
                request_id=f"{request.idempotency_key[:16]}-{int(time.time() * 1000) % 10000}"  # Unique ID per LLM call
            )

            print(f"🚀 ORCHESTRATOR: LLM response method={response.get('method_used')}, latency={response.get('latency_ms')}ms")

            # Unify parse path using envelope
            if response:
                content_text = response.get("content") or ""
                parsed = response.get("parsed") or {}
                method_used = response.get("method") or response.get("method_used") or "unknown"
                if content_text:
                    print(f"📥 ORCHESTRATOR: LLM content preview: {content_text[:100]}...")

                # fallback: if no parsed, attempt soft parse on content
                if not parsed or parsed.get("candidate_id") is None:
                    try:
                        from core.llm_utils import safe_parse_decision
                        parsed = safe_parse_decision(content_text)
                    except Exception:
                        parsed = {}

                cid = parsed.get("candidate_id")
                reasoning = parsed.get("reason") or "LLM visual selection"
                if isinstance(cid, int) and 1 <= cid <= len(ordered):
                    idx = cid - 1
                    # IMPORTANT: pick directly from `ordered` because overlay numbering shown to LLM
                    # is built from this exact list. This avoids index remap drift.
                    selected_candidate = ordered[idx]
                    try:
                        setattr(selected_candidate, "llm_selected_id", int(cid))
                        setattr(selected_candidate, "llm_method_used", str(method_used))
                        setattr(selected_candidate, "llm_overlay_path", str(overlay_meta.get("overlay_path") or ""))
                        setattr(selected_candidate, "llm_overlay_sha1", str(overlay_meta.get("overlay_sha1") or ""))
                    except Exception:
                        pass
                    if hasattr(self, 'telemetry'):
                        self.telemetry.add_kv(request.idempotency_key, {
                            "llm_method_used": method_used,
                            "llm_provider": response.get("provider", "unknown"),
                            "llm_latency_ms": response.get("latency_ms", -1),
                            "llm_selected_rank": cid,
                            "llm_selected_confidence": selected_candidate.score
                        })
                    print(f"✅ ORCHESTRATOR: LLM selected candidate {cid}/{len(ordered)} - {reasoning}")
                    return selected_candidate, f"Visual analysis ({method_used}): {reasoning}"

            # Do not click on detector-confidence fallback by default.
            # This prevents large off-target clicks when LLM parse/selection fails.
            allow_fallback_click = os.getenv("AUTOSTEP_ALLOW_FALLBACK_CLICK", "0").strip().lower() in {"1", "true", "yes", "on"}
            print(f"⚠️ ORCHESTRATOR: LLM decision unresolved (allow_fallback_click={allow_fallback_click})")
            if allow_fallback_click and candidates:
                best_candidate = max(candidates, key=lambda c: c.score)
                try:
                    setattr(best_candidate, "llm_overlay_path", str(overlay_meta.get("overlay_path") or ""))
                    setattr(best_candidate, "llm_overlay_sha1", str(overlay_meta.get("overlay_sha1") or ""))
                except Exception:
                    pass
                if hasattr(self, 'telemetry'):
                    self.telemetry.add_kv(request.idempotency_key, {
                        "llm_method_used": response.get("method_used", "unknown") if response else "failed",
                        "llm_fallback_used": True,
                        "fallback_confidence": best_candidate.score
                    })
                return best_candidate, "Fallback: highest confidence candidate"
            return None

        except Exception as e:
            print(f"❌ ORCHESTRATOR: LLM decision making failed: {e}")
            logger.error(f"LLM decision making failed: {e}")

            # By default, do not click on error fallback.
            allow_fallback_click = os.getenv("AUTOSTEP_ALLOW_FALLBACK_CLICK", "0").strip().lower() in {"1", "true", "yes", "on"}
            if allow_fallback_click and candidates:
                best_candidate = candidates[0]
                if hasattr(self, 'telemetry'):
                    self.telemetry.add_kv(request.idempotency_key, {
                        "llm_error": str(e),
                        "llm_fallback_used": True,
                        "error_fallback_confidence": best_candidate.score
                    })
                return best_candidate, f"Error fallback: {e}"
            return None

    def _make_llm_explain_all(self, img_bgr: np.ndarray, candidates: List, request: PickRequest) -> Dict[str, Any]:
        """
        Ask the LLM to explain what each numbered element is.

        The overlay numbering matches the order of `candidates` as passed in.
        Returns a dict containing the normalized LLM output (best-effort).
        """
        try:
            print(f"🧭 ORCHESTRATOR: _make_llm_explain_all called with {len(candidates)} candidates")

            options = request.options
            llm_method = options.llm_method  # auto|mq|direct
            llm_timeout_s = options.llm_timeout_ms / 1000.0

            n = len(candidates)
            if n <= 0:
                return {"ok": False, "error": "no candidates", "elements": []}

            # In explain_all mode we want the overlay to include ALL detections, but LLM output
            # can hit length limits. We chunk ids into multiple calls for reliability.
            try:
                chunk_size = int(getattr(options, "max_candidates", 32) or 32)
            except Exception:
                chunk_size = 32
            if chunk_size < 1:
                chunk_size = 32
            chunk_size = min(chunk_size, 64)

            goal = (request.context.goal or "").strip()
            goal_line = f"User goal/context: {goal}\n\n" if goal else ""

            # Build overlay ONCE for all candidates; reuse for chunked calls.
            vision_data = self._create_vision_data_for_llm(img_bgr, candidates, req_id=request.idempotency_key)
            if not vision_data:
                return {"ok": False, "error": "failed to build vision data", "elements": []}

            rid_prefix = (request.idempotency_key or "req")[:16]

            def _hint_line(eid: int) -> str:
                c = candidates[eid - 1]
                return f"[{eid}] {getattr(c, 'cls', None)} (conf: {float(getattr(c, 'score', 0.0)):.2f})"

            elements_by_id: Dict[int, Dict[str, Any]] = {}
            language: Optional[str] = None
            llm_provider: Optional[str] = None
            llm_model: Optional[str] = None
            llm_method_used: Optional[str] = None
            latency_sum_ms = 0
            latency_max_ms = 0
            raw_samples: List[str] = []

            num_chunks = 0
            for start_id in range(1, n + 1, chunk_size):
                end_id = min(start_id + chunk_size - 1, n)
                num_chunks += 1

                candidate_list = [_hint_line(eid) for eid in range(start_id, end_id + 1)]

                visual_prompt = f"""{goal_line}You are given a screenshot with numbered boxes drawn on top of UI elements.
Each number corresponds to ONE detected UI element.

Task:
- Explain ONLY ids from {start_id} to {end_id} (inclusive). Ignore all other ids.

Output rules:
- Return STRICT JSON only (no markdown, no code fences, no extra text).
- Include every id in this range exactly once.
- Keep label/description short (label <= 6 words; description <= 1 sentence).
- Use English by default. If the UI text is primarily Chinese, you may use Chinese.
- If unsure, use \"unknown\" and confidence 0.

JSON schema:
{{
  \"mode\": \"explain_all\",
  \"language\": \"en\" | \"zh\",
  \"elements\": [
    {{
      \"id\": {start_id},
      \"label\": \"short name\",
      \"description\": \"what it is / what it does\",
      \"type\": \"button|input|link|icon|menu|tab|text|image|checkbox|radio|dropdown|unknown\",
      \"confidence\": 0.0
    }}
  ]
}}

CANDIDATES (extra hints; numbering must match the overlay):
{chr(10).join(candidate_list)}
"""

                messages = [{"role": "user", "parts": [{"text": visual_prompt}]}]

                print(
                    f"🧭 ORCHESTRATOR: explain_all chunk {start_id}-{end_id}/{n} "
                    f"(method={llm_method}, timeout={llm_timeout_s}s)"
                )

                try:
                    response = self.llm.generate_response(
                        messages=messages,
                        vision=vision_data,
                        timeout=int(llm_timeout_s),
                        method=llm_method,
                        request_id=f"{rid_prefix}-exp-{start_id}-{end_id}-{int(time.time() * 1000) % 10000}",
                    )
                except Exception as chunk_err:
                    logger.warning(f"explain_all chunk {start_id}-{end_id} failed: {chunk_err}")
                    continue

                content_text = (response or {}).get("content") or ""
                parsed = self._parse_explain_all_json(content_text)
                chunk_elements = self._normalize_explain_all_elements(
                    parsed.get("elements") if isinstance(parsed, dict) else None
                )

                if isinstance(parsed, dict) and not language and parsed.get("language"):
                    language = str(parsed.get("language"))

                # Capture provider/model/method once (stable) + track latencies
                if response and not llm_provider:
                    llm_provider = response.get("provider")
                if response and not llm_model:
                    llm_model = response.get("model")
                if response and not llm_method_used:
                    llm_method_used = response.get("method") or response.get("method_used")

                lat_ms = (response or {}).get("latency_ms")
                if isinstance(lat_ms, int):
                    latency_sum_ms += lat_ms
                    latency_max_ms = max(latency_max_ms, lat_ms)

                if content_text:
                    raw_samples.append(content_text[:800])

                for el in chunk_elements:
                    eid = el.get("id")
                    if not isinstance(eid, int):
                        continue
                    if start_id <= eid <= end_id:
                        elements_by_id[eid] = el

            elements_out = [elements_by_id[k] for k in sorted(elements_by_id.keys())]
            return {
                "ok": bool(elements_out),
                "language": language,
                "elements": elements_out,
                "llm": {
                    "method": llm_method_used or "unknown",
                    "provider": llm_provider,
                    "model": llm_model,
                    "chunks": num_chunks,
                    "chunk_size": chunk_size,
                    "latency_ms_sum": latency_sum_ms or None,
                    "latency_ms_max": latency_max_ms or None,
                },
                "raw": ("\n\n".join(raw_samples))[:4000],
            }

        except Exception as e:
            logger.error(f"LLM explain_all failed: {e}")
            return {"ok": False, "error": str(e), "elements": []}

    def _parse_explain_all_json(self, content: str) -> Optional[Dict[str, Any]]:
        """Parse strict JSON response for explain_all."""
        if not content:
            return None
        try:
            import json
            from core.gemini_client import parse_first_json

            try:
                js = json.loads(content)
            except Exception:
                js = parse_first_json(content)

            # Allow a raw list as shorthand
            if isinstance(js, list):
                return {"elements": js}
            if isinstance(js, dict):
                return js
            return None
        except Exception:
            return None

    def _normalize_explain_all_elements(self, elements: Any) -> List[Dict[str, Any]]:
        """Normalize LLM elements list into stable, typed dicts."""
        out: List[Dict[str, Any]] = []
        if not isinstance(elements, list):
            return out

        def _to_int(v: Any) -> Optional[int]:
            try:
                if isinstance(v, bool):
                    return None
                if isinstance(v, int):
                    return v
                if isinstance(v, float) and float(v).is_integer():
                    return int(v)
                if isinstance(v, str):
                    import re
                    m = re.search(r"\d+", v)
                    if m:
                        return int(m.group(0))
            except Exception:
                return None
            return None

        def _to_float(v: Any) -> Optional[float]:
            try:
                if isinstance(v, (int, float)):
                    return float(v)
                if isinstance(v, str):
                    return float(v.strip())
            except Exception:
                return None
            return None

        for item in elements:
            if not isinstance(item, dict):
                continue
            id_raw = item.get("id", item.get("index", item.get("candidate_id")))
            eid = _to_int(id_raw)
            if eid is None:
                continue

            label = item.get("label") or item.get("name") or item.get("title") or item.get("meaning")
            desc = item.get("description") or item.get("desc") or item.get("what") or item.get("purpose")
            typ = item.get("type") or item.get("kind") or "unknown"
            conf = _to_float(item.get("confidence"))

            out.append({
                "id": eid,
                "label": str(label)[:120] if isinstance(label, str) else ("unknown" if label is None else str(label)[:120]),
                "description": str(desc)[:400] if isinstance(desc, str) else ("unknown" if desc is None else str(desc)[:400]),
                "type": str(typ)[:40] if isinstance(typ, str) else ("unknown" if typ is None else str(typ)[:40]),
                "confidence": conf,
            })
        return out

    def _create_vision_data_for_llm(self, img_bgr: np.ndarray, candidates: List, req_id: Optional[str] = None) -> Optional[List[Dict]]:
        """
        Create vision data for LLM: overlay image + candidate crops
        Returns list of vision items for HybridLLMClient
        """
        try:
            import cv2
            import numpy as np
            import os

            vision_data = []

            # 1. Create overlay image with all candidates numbered
            overlay_img = self._create_overlay_image(img_bgr, candidates)

            # Resize overlay to reduce transfer costs when explicitly configured.
            # Default is no resize to preserve visual detail for dense overlays.
            try:
                max_width = int(os.getenv("LLM_VISION_MAX_WIDTH", "0"))
            except ValueError:
                max_width = 0

            if max_width > 0:
                height, width = overlay_img.shape[:2]
                if width > max_width:
                    scale = max_width / width
                    new_width = max_width
                    new_height = int(height * scale)
                    overlay_img = cv2.resize(overlay_img, (new_width, new_height), interpolation=cv2.INTER_AREA)

            # Convert overlay to bytes and persist the exact image sent to LLM.
            _, overlay_buffer = cv2.imencode('.png', overlay_img, [cv2.IMWRITE_PNG_COMPRESSION, 6])
            overlay_bytes = overlay_buffer.tobytes()
            overlay_sha1 = ""
            overlay_path = ""
            try:
                import hashlib
                overlay_sha1 = hashlib.sha1(overlay_bytes).hexdigest()
                safe_req = str(req_id or f"req_{int(time.time() * 1000)}")
                safe_req = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in safe_req)
                out_dir = os.path.join("out", "overlays")
                os.makedirs(out_dir, exist_ok=True)
                overlay_path = os.path.join(out_dir, f"{safe_req}_llm_overlay_{overlay_sha1[:12]}.png")
                with open(overlay_path, "wb") as f:
                    f.write(overlay_bytes)
            except Exception:
                overlay_path = ""

            vision_data.append({
                "bytes": overlay_bytes,
                "role": "overview",
                "meta": {
                    "type": "numbered_overlay",
                    "candidate_count": len(candidates),
                    "size": len(overlay_bytes),
                    "overlay_sha1": overlay_sha1,
                    "overlay_path": overlay_path,
                    "overlay_w": int(overlay_img.shape[1]) if overlay_img is not None else None,
                    "overlay_h": int(overlay_img.shape[0]) if overlay_img is not None else None,
                }
            })

            # Persist overlay here removed; saved early in pick()

            # 2. Candidate crops disabled (overlay-only vision)

            print(f"📸 ORCHESTRATOR: Generated {len(vision_data)} vision items ({sum(item['meta']['size'] for item in vision_data)} bytes total)")
            if overlay_path or overlay_sha1:
                print(f"📸 ORCHESTRATOR: LLM overlay path={overlay_path} sha1={overlay_sha1[:16]}")
            return vision_data

        except Exception as e:
            logger.error(f"Failed to create vision data for LLM: {e}")
            return None

    def _parse_llm_response(self, content: str) -> Optional[Dict[str, Any]]:
        """Parse LLM response content"""
        try:
            # Try to parse as JSON
            import json
            from core.gemini_client import parse_first_json

            return parse_first_json(content)
        except Exception as e:
            logger.warning(f"Failed to parse LLM response: {e}")
            return None

    def _extract_preferred_classes(self, context) -> Optional[List[str]]:
        """Extract preferred classes from context with safe string handling"""
        intent = _lower_safe(getattr(context, 'intent', None))
        goal = _lower_safe(getattr(context, 'goal', None))

        # Map intents/goals to preferred classes (支持中英文关键词)
        if any(keyword in intent for keyword in ["click", "button", "点击", "按钮"]) or \
           any(keyword in goal for keyword in ["click", "button", "点击", "按钮", "搜索"]):
            return ["button", "link", "icon"]
        elif any(keyword in intent for keyword in ["input", "type", "输入", "填写"]) or \
             any(keyword in goal for keyword in ["input", "type", "输入", "填写"]):
            return ["textbox", "input"]
        elif any(keyword in intent for keyword in ["select", "dropdown", "选择", "下拉"]) or \
             any(keyword in goal for keyword in ["select", "dropdown", "选择", "下拉"]):
            return ["combobox", "dropdown", "select"]

        return None

    def _extract_negative_classes(self, context) -> Optional[List[str]]:
        """Extract classes to avoid from context"""
        # Generally avoid decorative elements but keep "icon" since YOLO detects UI elements as "icon"
        return ["decoration", "background"]  # Removed "icon" to allow UI element detection

    def _create_anchor_hit_response(self, point: List[int], confidence: float,
                                  anchor_id: str, request: PickRequest, t_start: float) -> Dict[str, Any]:
        """Create response for anchor cache hit"""
        return {
            "decision": {
                "action": "click",
                "bbox_in_capture": None,
                "point_in_capture": point,
                "confidence": confidence,
                "reason": f"Anchor hit: {anchor_id}"
            },
            "mapping_hint": {
                "apply_window_offset": request.capture.mode != "full",
                "expects_dpr": request.capture.dpr
            },
            "anchor_proposal": None,
            "verification_plan": self.verifier.default_plan(request.context.dict()),
            "telemetry": {
                "req_id": request.idempotency_key,
                "cache_hit": True,
                "stage_lat_ms": {"total": int((time.time() - t_start) * 1000)}
            }
        }

    def _create_success_response(self, candidate, anchor_proposal: Dict, verification_plan: Dict,
                               reasoning: str, request: PickRequest, t_start: float,
                               yolo_ms: float, llm_ms: float) -> Dict[str, Any]:
        """Create successful pick response"""
        # Calculate center point
        x1, y1, x2, y2 = candidate.xyxy
        center_x = int((x1 + x2) / 2)
        center_y = int((y1 + y2) / 2)

        selected_rank = None
        overlay_path = ""
        overlay_sha1 = ""
        try:
            rid = getattr(candidate, "llm_selected_id", None)
            if isinstance(rid, int) and rid > 0:
                selected_rank = rid
            overlay_path = str(getattr(candidate, "llm_overlay_path", "") or "")
            overlay_sha1 = str(getattr(candidate, "llm_overlay_sha1", "") or "")
        except Exception:
            selected_rank = None

        out = {
            "decision": {
                "action": "click",
                "bbox_in_capture": [int(x) for x in candidate.xyxy],
                "point_in_capture": [center_x, center_y],
                "confidence": candidate.score,
                "reason": reasoning
            },
            "mapping_hint": {
                "apply_window_offset": request.capture.mode != "full",
                "expects_dpr": request.capture.dpr
            },
            "anchor_proposal": anchor_proposal,
            "verification_plan": verification_plan,
            "telemetry": {
                "req_id": request.idempotency_key,
                "cache_hit": False,
                "stage_lat_ms": {
                    "yolo": int(yolo_ms * 1000),
                    "llm": int(llm_ms * 1000),
                    "total": int((time.time() - t_start) * 1000)
                }
            }
        }
        if selected_rank is not None:
            out["decision"]["selected_rank"] = selected_rank
        if overlay_path or overlay_sha1:
            out["decision"]["llm_debug"] = {
                "overlay_path": overlay_path,
                "overlay_sha1": overlay_sha1,
            }
        return out

    def _create_explain_all_response(
        self,
        candidates: List,
        explain_result: Dict[str, Any],
        request: PickRequest,
        t_start: float,
        yolo_ms: float,
        llm_ms: float,
    ) -> Dict[str, Any]:
        """Create response for explain_all mode (elements + coordinates)."""
        elements_in = explain_result.get("elements") if isinstance(explain_result, dict) else None
        explain_map: Dict[int, Dict[str, Any]] = {}
        if isinstance(elements_in, list):
            for item in elements_in:
                if not isinstance(item, dict):
                    continue
                eid = item.get("id")
                if isinstance(eid, int):
                    explain_map[eid] = item

        merged: List[Dict[str, Any]] = []
        for i, c in enumerate(candidates, start=1):
            try:
                x1, y1, x2, y2 = [int(v) for v in c.xyxy]
            except Exception:
                continue
            cx = int((x1 + x2) / 2)
            cy = int((y1 + y2) / 2)

            base = {
                "id": i,
                "bbox_in_capture": [x1, y1, x2, y2],
                "point_in_capture": [cx, cy],
                "cls": getattr(c, "cls", None),
                "score": float(getattr(c, "score", 0.0)),
            }

            expl = explain_map.get(i)
            if isinstance(expl, dict):
                base.update({
                    "label": expl.get("label", "unknown"),
                    "description": expl.get("description", "unknown"),
                    "type": expl.get("type", "unknown"),
                    "confidence": expl.get("confidence"),
                })
            else:
                base.update({
                    "label": "unknown",
                    "description": "unknown",
                    "type": "unknown",
                    "confidence": None,
                })
            merged.append(base)

        return {
            "decision": {
                "action": "explain_all",
                "bbox_in_capture": None,
                "point_in_capture": [0, 0],
                "confidence": 0.0,
                "reason": "explain_all mode",
            },
            "mapping_hint": {
                "apply_window_offset": request.capture.mode != "full",
                "expects_dpr": request.capture.dpr,
            },
            "anchor_proposal": None,
            "verification_plan": self.verifier.default_plan(request.context.dict()),
            "elements": merged,
            "explain": {
                "ok": bool(explain_result.get("ok")) if isinstance(explain_result, dict) else False,
                "language": explain_result.get("language") if isinstance(explain_result, dict) else None,
                "llm": explain_result.get("llm") if isinstance(explain_result, dict) else None,
            },
            "telemetry": {
                "req_id": request.idempotency_key,
                "cache_hit": False,
                "stage_lat_ms": {
                    "yolo": int(yolo_ms * 1000),
                    "llm": int(llm_ms * 1000),
                    "total": int((time.time() - t_start) * 1000),
                },
            },
        }

    def _create_no_candidates_response(self, request: PickRequest, t_start: float) -> Dict[str, Any]:
        """Create response when no candidates found"""
        return {
            "decision": {
                "action": "none",
                "bbox_in_capture": None,
                "point_in_capture": [0, 0],
                "confidence": 0.0,
                "reason": "No candidates detected by YOLO"
            },
            "mapping_hint": {
                "apply_window_offset": False,
                "expects_dpr": request.capture.dpr
            },
            "anchor_proposal": None,
            "verification_plan": self.verifier.default_plan(request.context.dict()),
            "telemetry": {
                "req_id": request.idempotency_key,
                "cache_hit": False,
                "stage_lat_ms": {"total": int((time.time() - t_start) * 1000)}
            }
        }

    def _create_low_confidence_response(
        self,
        request: PickRequest,
        t_start: float,
        candidate_conf: float,
        min_conf: float,
    ) -> Dict[str, Any]:
        """Create response when selected candidate confidence is below threshold."""
        return {
            "decision": {
                "action": "none",
                "bbox_in_capture": None,
                "point_in_capture": [0, 0],
                "confidence": candidate_conf,
                "reason": f"Low confidence: {candidate_conf:.3f} < {min_conf:.3f}",
            },
            "mapping_hint": {
                "apply_window_offset": False,
                "expects_dpr": request.capture.dpr,
            },
            "anchor_proposal": None,
            "verification_plan": self.verifier.default_plan(request.context.dict()),
            "telemetry": {
                "req_id": request.idempotency_key,
                "cache_hit": False,
                "stage_lat_ms": {"total": int((time.time() - t_start) * 1000)},
                "low_confidence": True,
                "pick_min_conf": min_conf,
            },
        }

    def _create_llm_failure_response(self, candidates: List, request: PickRequest, t_start: float) -> Dict[str, Any]:
        """Create response when LLM decision fails"""
        # Safe default: return no-op and let caller retry with better context/constraints.
        return {
            "decision": {
                "action": "none",
                "bbox_in_capture": None,
                "point_in_capture": [0, 0],
                "confidence": 0.0,
                "reason": "LLM decision unresolved; no fallback click"
            },
            "mapping_hint": {
                "apply_window_offset": False,
                "expects_dpr": request.capture.dpr
            },
            "anchor_proposal": None,
            "verification_plan": self.verifier.default_plan(request.context.dict()),
            "telemetry": {
                "req_id": request.idempotency_key,
                "cache_hit": False,
                "stage_lat_ms": {"total": int((time.time() - t_start) * 1000)},
                "llm_failed": True,
                "fallback_click_blocked": True
            }
        }

    def _create_error_response(self, error_msg: str, request: PickRequest, t_start: float) -> Dict[str, Any]:
        """Create error response"""
        return {
            "error": {
                "code": "INTERNAL_ERROR",
                "message": error_msg,
                "req_id": request.idempotency_key
            },
            "telemetry": {
                "req_id": request.idempotency_key,
                "stage_lat_ms": {"total": int((time.time() - t_start) * 1000)},
                "error": True
            }
        }

    def _cache_result(self, req_id: str, result: Dict[str, Any]):
        """Cache result for idempotency"""
        # Simple in-memory cache with size limit
        if len(self._request_cache) > 1000:
            # Remove oldest entries
            oldest_keys = list(self._request_cache.keys())[:100]
            for key in oldest_keys:
                del self._request_cache[key]

        self._request_cache[req_id] = result

    def _create_overlay_image(self, img_bgr: np.ndarray, candidates: List) -> np.ndarray:
        """
        Create overlay image with YOLO detection boxes for LLM visual analysis.
        Match legacy style: draw IDs inside the box (corner preferred, then top-band),
        no class/conf in the label.
        """
        import cv2

        def _font_scale_from_px(desired_px: int, thickness: int = 1) -> float:
            font = cv2.FONT_HERSHEY_SIMPLEX
            lo, hi = 0.05, 5.0
            for _ in range(20):
                mid = (lo + hi) / 2.0
                (_, h), _ = cv2.getTextSize("Ag", font, mid, thickness)
                if h > desired_px:
                    hi = mid
                else:
                    lo = mid
            return lo

        def _clip_int(v: int, lo: int, hi: int) -> int:
            return max(lo, min(hi, v))

        def _draw_inside_label(img, box, text, base_font_px, line_width, img_h, min_band_px, min_band_px_ratio,
                               color_box=(255, 0, 0), color_text=(255, 255, 255), alpha_bg=0.45):
            x1, y1, x2, y2 = [int(v) for v in box]
            w, h = x2 - x1, y2 - y1
            out = img
            pad = 4
            thickness_text = max(1, line_width - 1)
            font_px = max(7, base_font_px)

            def draw_filled(rect):
                rx1, ry1, rx2, ry2 = rect
                overlay = out.copy()
                cv2.rectangle(overlay, (rx1, ry1), (rx2, ry2), color_box, -1)
                cv2.addWeighted(overlay, alpha_bg, out, 1 - alpha_bg, 0, out)

            font = cv2.FONT_HERSHEY_SIMPLEX
            # Corner priority
            while font_px >= 7:
                scale = _font_scale_from_px(font_px, thickness=thickness_text)
                (tw, th), _ = cv2.getTextSize(text, font, scale, thickness_text)
                bw, bh = tw + 2 * pad, th + 2 * pad
                candidates_pos = [
                    (x1 + line_width, y1 + line_width),
                    (x2 - line_width - bw, y1 + line_width),
                    (x1 + line_width, y2 - line_width - bh),
                    (x2 - line_width - bw, y2 - line_width - bh),
                ]
                for (lx, ly) in candidates_pos:
                    if lx >= x1 and ly >= y1 and (lx + bw) <= x2 and (ly + bh) <= y2:
                        rect = (int(lx), int(ly), int(lx + bw), int(ly + bh))
                        draw_filled(rect)
                        cv2.putText(out, text, (rect[0] + pad, rect[3] - pad - 1), font, scale, color_text, thickness_text, cv2.LINE_AA)
                        return out, rect, 0
                font_px = int(font_px * 0.9)

            # Top band fallback inside box
            min_band = max(min_band_px, int(min_band_px_ratio * img_h))
            band_h_px = max(min_band, int(h * 0.20))
            rx1, ry1, rx2, ry2 = x1 + line_width, y1 + line_width, x2 - line_width, y1 + band_h_px
            rx1, ry1 = _clip_int(rx1, 0, img.shape[1] - 1), _clip_int(ry1, 0, img.shape[0] - 1)
            rx2, ry2 = _clip_int(rx2, 0, img.shape[1] - 1), _clip_int(ry2, 0, img.shape[0] - 1)
            rect = (rx1, ry1, rx2, ry2)

            scale = _font_scale_from_px(max(9, band_h_px - 6), thickness=thickness_text)
            (tw, th), _ = cv2.getTextSize(text, font, scale, thickness_text)
            tries = 0
            while tw + 8 > (rx2 - rx1) and tries < 8:
                scale *= 0.9
                (tw, th), _ = cv2.getTextSize(text, font, scale, thickness_text)
                tries += 1

            overlay = out.copy()
            cv2.rectangle(overlay, (rx1, ry1), (rx2, ry2), color_box, -1)
            cv2.addWeighted(overlay, 0.45, out, 0.55, 0, out)
            cx = int((rx1 + rx2 - tw) / 2)
            cy = int((ry1 + ry2 + th) / 2) - 2
            cv2.putText(out, text, (cx, cy), font, scale, color_text, thickness_text, cv2.LINE_AA)
            return out, rect, 1

        # Build overlay using inside-label strategy
        H, W = img_bgr.shape[:2]
        out = img_bgr.copy()
        color_box = (255, 0, 0)
        thickness_box = 2
        text_mode = "short"  # IDs only
        # Draw rectangles first
        xyxy = [[int(v) for v in c.xyxy] for c in candidates]
        for (x1, y1, x2, y2) in xyxy:
            cv2.rectangle(out, (int(x1), int(y1)), (int(x2), int(y2)), color_box, thickness_box)

        label_rects = []
        N = max(1, len(xyxy))
        for idx, (x1, y1, x2, y2) in enumerate(xyxy, start=1):
            h = int(y2 - y1)
            # compute base font px roughly proportional to box height and image height
            img_based = max(12, int(0.016 * H))
            box_based = max(9, int(0.28 * h))
            base_px = min(max(img_based, box_based), 36)
            # adjust by density
            if N > 70:
                base_px = int(base_px * 0.88)
            elif N < 15:
                base_px = int(base_px * 1.12)
            base_px = max(7, base_px)
            # text is just the numeric ID
            text = f"{idx}"
            out, rect, _ = _draw_inside_label(
                out, (x1, y1, x2, y2), text=text,
                base_font_px=base_px, line_width=thickness_box, img_h=H,
                min_band_px=14, min_band_px_ratio=0.012,
                color_box=color_box, color_text=(255, 255, 255), alpha_bg=0.45,
            )
            label_rects.append(rect)

        return out

    def get_stats(self) -> Dict[str, Any]:
        """Get orchestrator statistics"""
        return {
            "cache_size": len(self._request_cache),
            "detector_stats": self.detector.get_detection_stats([]),
            "anchors_stats": self.anchors.get_anchor_stats([]),
            "verification_stats": self.verifier.get_verification_stats([])
        }
