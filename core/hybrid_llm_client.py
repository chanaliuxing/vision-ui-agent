"""
Hybrid LLM Client: MQ-first with direct fallback
Maintains compatibility with existing LLMClient interface while adding MQ routing
"""
import time
import json
import uuid
import logging
import base64
from typing import Any, Dict, List, Optional, Union

from .llm_client import LLMClient
from yolo.logging_setup import get_logger, Timer, redact
try:
    from yolo.capture.blob_store import init_store, make_prefix
except Exception:  # capture optional
    init_store = None  # type: ignore
    make_prefix = None  # type: ignore
try:
    from .image_optimizer import LLMImageOptimizer
except Exception:  # optimization optional
    LLMImageOptimizer = None  # type: ignore
_jsonlog = get_logger()

logger = logging.getLogger(__name__)

class HybridLLMClient(LLMClient):
    """
    Enhanced LLM client with MQ-first routing and direct fallback

    Strategy:
    1. Try MQ (async, scalable) with timeout
    2. Fall back to direct HTTP if MQ fails/timeout
    3. Log all requests/responses with full tracing
    4. Handle vision data via object storage to avoid MQ size limits
    """

    def __init__(self, provider: str = "openai", model: str = "gpt-4o-mini",
                 mq_timeout_s: int = 30, direct_timeout_s: int = 120,
                 storage=None, mq=None):
        super().__init__(provider, model)
        self.mq_timeout_s = mq_timeout_s
        self.direct_timeout_s = direct_timeout_s
        self.storage = storage  # S3/MinIO client for vision data
        self.mq = mq           # MQ client (SQS/Redis/etc)

        # Circuit breaker state
        self.circuit_failures = 0
        self.circuit_last_failure = 0
        self.circuit_threshold = 3
        self.circuit_timeout = 300  # 5 minutes

    def generate_response(self, messages: List[Dict[str, Any]],
                         image_path: Optional[str] = None,
                         vision: Optional[List[Dict]] = None,
                         timeout: Optional[int] = None,
                         method: str = "auto",
                         request_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate LLM response with MQ-first + direct fallback strategy

        Args:
            messages: OpenAI-compatible message format
            image_path: Legacy single image path (for compatibility)
            vision: List of vision objects [{"bytes": b"...", "role": "crop", "meta": {...}}]
            timeout: Override timeout in seconds
            method: "auto"|"mq"|"direct" - force specific method
            request_id: Optional request ID for tracing

        Returns:
            {
                "content": "LLM response content",
                "provider": "mq"|"direct",
                "latency_ms": 1234,
                "request_id": "req_abc123",
                "method_used": "mq_success"|"direct_fallback"|"direct_only"
            }
        """
        req_id = request_id or f"llm-{uuid.uuid4().hex[:8]}"
        t_start = time.time()

        # 1. Prepare vision data first (it's needed for logging)
        vision_prepared = self._prepare_vision_for_mq(vision, image_path, req_id) if (vision or image_path) else None

        logger.info(f"🚀 HYBRID-LLM: Starting request {req_id} method={method}")

        # 2. Full capture outbound LLM request
        try:
            import os
            if init_store and make_prefix and os.getenv("FULL_CAPTURE", "false").lower() == "true":
                store = init_store()
                prefix = make_prefix(None, req_id)
                
                # Safely extract vision meta
                v_meta = []
                try:
                    if vision_prepared:
                        v_meta = [
                            {"role": it.get("role"), "size": (it.get("meta") or {}).get("size")}
                            for it in vision_prepared
                        ]
                except Exception:
                    v_meta = ["error extracting meta"]

                store.save_json(f"{prefix}/llm/{self.provider}/request.json", {
                    "provider": self.provider,
                    "model": self.model,
                    "method": method,
                    "messages": messages,
                    "vision_meta": v_meta,
                })
        except Exception as e:
            logger.warning(f"⚠️ Failed to capture LLM request log: {e}")

        # Try MQ first (unless method=direct)
        if method in ("auto", "mq") and self._should_try_mq():
            try:
                with Timer() as _t:
                    mq_raw = self._try_mq_request(messages, vision_prepared, timeout, req_id)
                if mq_raw:
                    # Normalize into unified envelope
                    content_text = self._extract_text(mq_raw)
                    parsed = self._safe_parse(content_text)
                    duration_ms = int((time.time() - t_start) * 1000)
                    logger.info(f"📥 MQ-LLM: Success {req_id} in {duration_ms}ms")
                    try:
                        _jsonlog.info("llm.call", svc="yoloapi", req_id=req_id,
                                       envelope={
                                           "ok": True, "method": "mq", "provider": self.provider, "model": self.model,
                                           "latency_ms": duration_ms,
                                           "content": redact(content_text),
                                           "parsed": parsed,
                                       })
                        # Save full raw response if capture enabled
                        import os
                        if init_store and make_prefix and os.getenv("FULL_CAPTURE", "false").lower() == "true":
                            store = init_store()
                            prefix = make_prefix(None, req_id)
                            store.save_json(f"{prefix}/llm/{self.provider}/response.json", mq_raw)
                    except Exception:
                        pass
                    return {
                        "ok": True,
                        "method": "mq",
                        "provider": self.provider,
                        "model": self.model,
                        "latency_ms": duration_ms,
                        "request_id": req_id,
                        "raw": mq_raw,
                        "content": content_text,
                        "parsed": parsed,
                        "method_used": "mq_success",
                    }
            except Exception as e:
                logger.warning(f"⚠️ MQ-LLM: Failed {req_id}: {e}, falling back to direct")
                self._record_mq_failure()

        # Direct fallback or direct-only
        logger.info(f"🔄 DIRECT-LLM: Calling {self.provider} directly for {req_id}")
        try:
            # Prepare for direct call - need to handle vision data
            direct_image_path = image_path
            direct_messages = messages

            # If we have vision data but no image_path, we need to create one
            # The parent class expects a single image file, so we'll use the overlay if available
            if vision and not direct_image_path:
                # Find the overlay/overview image or use the first image
                overlay_item = None
                for item in vision:
                    if item.get("role") in ("overlay", "overview") and "bytes" in item:
                        overlay_item = item
                        break
                
                if overlay_item:
                    # Create temporary file for the overlay
                    import tempfile
                    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                        tmp.write(overlay_item["bytes"])
                        direct_image_path = tmp.name
                        logger.debug(f"🖼️ Created temp image for direct LLM: {direct_image_path}")

            # Optimize image for token reduction if optimizer available
            optimized_image_path = direct_image_path
            if direct_image_path and LLMImageOptimizer:
                try:
                    optimizer = LLMImageOptimizer()
                    optimized_path, stats = optimizer.optimize_for_llm(direct_image_path)
                    if stats.get('optimized', False):
                        optimized_image_path = optimized_path
                        logger.info(f"🚀 Image optimized: {stats['reduction_percent']}% token reduction "
                                  f"({stats['original_tokens']} → {stats['final_tokens']} tokens)")
                    else:
                        logger.debug(f"📷 Image already optimal or optimization skipped")
                except Exception as e:
                    logger.warning(f"⚠️ Image optimization failed, using original: {e}")
                    optimized_image_path = direct_image_path

            # Use parent class direct implementation with optimized image
            direct_raw = super().generate_response(direct_messages, optimized_image_path)

            # Clean up temporary files if we created them
            if vision and direct_image_path != image_path and direct_image_path:
                try:
                    import os
                    os.unlink(direct_image_path)
                except:
                    pass
            # Clean up optimized image if it's different from original
            if optimized_image_path != direct_image_path and optimized_image_path != image_path:
                try:
                    import os
                    os.unlink(optimized_image_path)
                except:
                    pass

            content_text = self._extract_text(direct_raw)
            if content_text is not None:
                duration_ms = int((time.time() - t_start) * 1000)
                logger.info(f"📥 DIRECT-LLM: Success {req_id} in {duration_ms}ms")
                try:
                    _jsonlog.info("llm.call", svc="yoloapi", req_id=req_id,
                                   envelope={
                                       "ok": True, "method": "direct", "provider": self.provider, "model": self.model,
                                       "latency_ms": duration_ms,
                                       "content": redact(content_text),
                                       "parsed": self._safe_parse(content_text),
                                   })
                    # Save full raw response if capture enabled
                    import os
                    if init_store and make_prefix and os.getenv("FULL_CAPTURE", "false").lower() == "true":
                        store = init_store()
                        prefix = make_prefix(None, req_id)
                        store.save_json(f"{prefix}/llm/{self.provider}/response.json", direct_raw if isinstance(direct_raw, dict) else {"raw": str(direct_raw)[:2000]})
                except Exception:
                    pass

                fallback_used = method in ("auto", "mq")
                return {
                    "ok": True,
                    "method": "direct",
                    "provider": self.provider,
                    "model": self.model,
                    "latency_ms": duration_ms,
                    "request_id": req_id,
                    "raw": direct_raw,
                    "content": content_text,
                    "parsed": self._safe_parse(content_text),
                    "method_used": "direct_fallback" if fallback_used else "direct_only",
                }

        except Exception as e:
            # Redact API keys from error messages
            msg = str(e)
            try:
                if "key=" in msg:
                    import re
                    msg = re.sub(r"key=[^&\s]+", "key=REDACTED", msg)
            except Exception:
                pass
            logger.error(f"❌ DIRECT-LLM: Failed {req_id}: {msg}")

        # Complete failure
        try:
            _jsonlog.info("llm.call", svc="yoloapi", req_id=req_id,
                           envelope={"ok": False, "method": method, "provider": self.provider,
                                     "model": self.model, "latency_ms": int((time.time() - t_start) * 1000),
                                     "error": "llm_failed"})
            import os
            if init_store and make_prefix and os.getenv("FULL_CAPTURE", "false").lower() == "true":
                store = init_store()
                prefix = make_prefix(None, req_id)
                store.save_json(f"{prefix}/llm/{self.provider}/response.json", {"error": "llm_failed"})
        except Exception:
            pass
        return {
            "ok": False,
            "content": "",
            "provider": self.provider,
            "model": self.model,
            "error": "llm_failed",
            "request_id": req_id,
            "method_used": "failed",
            "latency_ms": int((time.time() - t_start) * 1000)
        }

    def _should_try_mq(self) -> bool:
        """Circuit breaker: avoid MQ if recent failures exceed threshold"""
        if not self.mq:
            return False

        # Reset circuit if enough time passed
        if time.time() - self.circuit_last_failure > self.circuit_timeout:
            self.circuit_failures = 0

        return self.circuit_failures < self.circuit_threshold

    def _record_mq_failure(self):
        """Record MQ failure for circuit breaker"""
        self.circuit_failures += 1
        self.circuit_last_failure = time.time()
        logger.warning(f"🔥 MQ Circuit: {self.circuit_failures}/{self.circuit_threshold} failures")

    # ---------- compression helpers ----------
    def _encode_path_to_webp_bytes(self, path: str) -> bytes:
        try:
            import app  # uses app._encode_image_file_for_llm
            b64 = app._encode_image_file_for_llm(path)
            data = base64.b64decode(b64)
            try:
                import os
                o = os.path.getsize(path); c = len(data)
                logger.info(f"MQ compress(path): {o} → {c} bytes ({(1-c/max(1,o))*100:.1f}%)")
            except Exception:
                pass
            return data
        except Exception as e:
            logger.warning(f"MQ compress(path) failed, using original: {e}")
            with open(path, "rb") as f:
                return f.read()

    def _encode_bytes_to_webp_bytes(self, data: bytes) -> bytes:
        # Skip if caller already marked as compressed
        try:
            # quick signature check for RIFF WEBP
            if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
                return data
        except Exception:
            pass
        tmp = None
        try:
            import tempfile, os
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp.write(data); tmp.flush(); tmp.close()
            return self._encode_path_to_webp_bytes(tmp.name)
        except Exception as e:
            logger.warning(f"MQ compress(bytes) failed, using original: {e}")
            return data
        finally:
            try:
                if tmp and os.path.exists(tmp.name):
                    os.unlink(tmp.name)
            except Exception:
                pass

    def _prepare_vision_for_mq(self, vision: Optional[List[Dict]],
                              image_path: Optional[str],
                              req_id: str) -> Optional[List[Dict]]:
        """
        Prepare vision data for MQ by uploading to object storage
        Avoids MQ message size limits by passing URLs instead of base64 data
        """
        if not vision and not image_path:
            return None

        if not self.storage:
            logger.warning(f"⚠️ Vision data provided but no storage configured for {req_id}")
            return None

        prepared = []

        # Handle legacy image_path
        if image_path:
            try:
                with open(image_path, 'rb') as f:
                    orig = f.read()
                webp = self._encode_path_to_webp_bytes(image_path)
                key = self._upload_vision_data(webp, req_id, "main_image", content_type="image/webp", ext="webp")
                if key:
                    prepared.append({
                        "uri": self.storage.get_signed_url(key),
                        "role": "main_image",
                        "meta": {"source": "image_path", "size": len(webp), "orig_size": len(orig), "compressed": True, "mime": "image/webp"}
                    })
            except Exception as e:
                logger.warning(f"⚠️ Failed to upload image_path for {req_id}: {e}")

        # Handle vision list
        if vision:
            for i, item in enumerate(vision):
                try:
                    if "bytes" in item:
                        orig = item["bytes"]
                        # don't recompress if caller already marked as compressed
                        webp = orig if (item.get("meta") or {}).get("compressed") else self._encode_bytes_to_webp_bytes(orig)
                        key = self._upload_vision_data(webp, req_id, f"crop_{i}", content_type="image/webp", ext="webp")
                        if key:
                            prepared.append({
                                "uri": self.storage.get_signed_url(key),
                                "role": item.get("role", "crop"),
                                "meta": {
                                    **item.get("meta", {}),
                                    "index": i,
                                    "size": len(webp),
                                    "orig_size": len(orig),
                                    "compressed": True,
                                    "mime": "image/webp"
                                }
                            })
                    elif "uri" in item:
                        # Already has URI, pass through
                        prepared.append(item)
                except Exception as e:
                    logger.warning(f"⚠️ Failed to upload vision item {i} for {req_id}: {e}")

        logger.info(f"📤 Vision: Prepared {len(prepared)} items for {req_id}")
        return prepared if prepared else None

    def _upload_vision_data(self, data: bytes, req_id: str, suffix: str, *, content_type: str = "image/png", ext: str = "png") -> Optional[str]:
        """Upload vision data to storage and return key (content_type/ext aware)"""
        try:
            key = f"llm-vision/{req_id}/{suffix}.{ext}"
            self.storage.put_object(key, data, content_type=content_type)
            return key
        except Exception as e:
            logger.error(f"❌ Storage upload failed for {req_id}/{suffix}: {e}")
            return None

    # ---- helpers ----
    def _extract_text(self, resp: Any) -> Optional[str]:
        """Extract human text from provider/MQ responses as best-effort."""
        try:
            if resp is None:
                return None
            # Direct text
            if isinstance(resp, str):
                return resp
            # Common OpenAI-like
            if isinstance(resp, dict) and "choices" in resp:
                ch = resp.get("choices") or []
                if ch:
                    msg = ch[0].get("message", {})
                    return msg.get("content") or ""
            # Gemini JSON
            if isinstance(resp, dict) and ("candidates" in resp or "contents" in resp):
                from .gemini_client import extract_text as _ex
                return _ex(resp)
            # MQ normalized
            if isinstance(resp, dict) and "content" in resp:
                return resp.get("content")
            # Fallback
            return json.dumps(resp)[:1000]
        except Exception:
            return None

    def _safe_parse(self, text: Optional[str]) -> Dict[str, Any]:
        from .llm_utils import safe_parse_decision
        return safe_parse_decision(text or "")

    def _try_mq_request(self, messages: List[Dict], vision: Optional[List[Dict]],
                       timeout: Optional[int], req_id: str) -> Optional[Dict]:
        """
        Send request via MQ and wait for response
        Returns response dict or None if failed/timeout
        """
        if not self.mq:
            raise RuntimeError("MQ client not configured")

        # Prepare MQ payload
        payload = {
            "request_id": req_id,
            "provider": self.provider,
            "model": self.model,
            "messages": messages,
            "vision": vision,
            "timeout": timeout or self.mq_timeout_s,
            "created_at": time.time()
        }

        # Send to request queue
        logger.info(f"📨 MQ-LLM: Sending {req_id} to llm-vision-request.fifo")
        self.mq.send_message("llm-vision-request.fifo", payload, group_id=req_id)

        # Wait for response
        timeout_s = timeout or self.mq_timeout_s
        logger.info(f"⏳ MQ-LLM: Waiting for response {req_id} (timeout={timeout_s}s)")

        response = self.mq.receive_message("llm-vision-response.fifo",
                                         request_id=req_id,
                                         timeout=timeout_s)

        if response and "content" in response:
            logger.info(f"📥 MQ-LLM: Received response for {req_id}")
            return response
        else:
            logger.warning(f"⏰ MQ-LLM: Timeout/empty response for {req_id}")
            return None
