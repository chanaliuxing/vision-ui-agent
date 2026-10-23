# core/llm_router.py - Unified LLM gateway with budget enforcement
import json
import time
from typing import Dict, Any, Optional, Union
import cv2
import numpy as np

from .costs import CostGuard, ImageDegradationPolicy
from .report_events import emit_llm_call

class LLMRouter:
    """Unified router for all LLM calls with budget enforcement and degradation"""
    
    def __init__(self, guard: CostGuard):
        self.guard = guard
        self.policy = ImageDegradationPolicy()
        self.call_history = []
    
    def _extract_token_usage(self, resp: Any) -> int:
        """Extract token usage from LLM response"""
        if isinstance(resp, dict):
            usage = resp.get("usage", {})
            if isinstance(usage, dict):
                return int(usage.get("total_tokens", 0))
        return 0
    
    def _apply_image_degradation(self, image_path: str, kind: str, degradation: str) -> Optional[str]:
        """Apply image degradation policies and return processed image path"""
        if degradation == "skip":
            return None
            
        if kind == "picker":
            policy = self.policy.get_picker_policy(degradation)
        elif kind == "arbiter":
            policy = self.policy.get_arbiter_policy(degradation)
        else:
            return image_path  # Strategy never uses images
        
        if not policy.get("allow", True):
            return None
        
        try:
            # Load original image
            img = cv2.imread(image_path)
            if img is None:
                return image_path
            
            # Apply degradation
            if degradation == "downscale" and kind == "picker":
                img = self._apply_picker_degradation(img, policy)
            elif degradation == "textonly" and kind == "arbiter":
                # For arbiter text-only, we don't process image but return None
                return None
            
            # Save processed image
            import os
            base_name = os.path.basename(image_path)
            name, ext = os.path.splitext(base_name)
            processed_path = image_path.replace(name + ext, f"{name}_{degradation}{ext}")
            
            cv2.imwrite(processed_path, img)
            return processed_path
            
        except Exception as e:
            print(f"[llm_router] Image degradation failed: {e}")
            return image_path
    
    def _apply_picker_degradation(self, img: np.ndarray, policy: dict) -> np.ndarray:
        """Apply picker-specific image degradation"""
        h, w = img.shape[:2]
        
        # Downscale if needed
        max_px = policy.get("max_px", 1024)
        if max(h, w) > max_px:
            scale = max_px / max(h, w)
            new_w, new_h = int(w * scale), int(h * scale)
            img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
        
        # ROI cropping could be implemented here if detection data is available
        # For now, just return downscaled image
        return img
    
    def _estimate_tokens_for_call(self, kind: str, degradation: str, has_image: bool, 
                                  messages: list = None) -> int:
        """Estimate token usage for a call"""
        base_estimate = self.policy.estimate_tokens(kind, degradation, has_image)
        
        # Add message length estimate
        if messages:
            text_length = 0
            for msg in messages:
                if isinstance(msg, dict):
                    parts = msg.get("parts", [])
                    for part in parts:
                        if isinstance(part, dict) and "text" in part:
                            text_length += len(part["text"])
                        elif isinstance(part, str):
                            text_length += len(part)
            
            # Rough estimate: 4 chars per token
            text_tokens = text_length // 4
            base_estimate += text_tokens
        
        return base_estimate
    
    def maybe_call(self, kind: str, messages: list, image_path: Optional[str] = None,
                   provider: str = "gemini", model: str = "gemini-1.5-flash",
                   fallback_result: Optional[dict] = None) -> Optional[dict]:
        """
        Central LLM call with budget enforcement and degradation
        
        Args:
            kind: "strategy", "picker", "arbiter"
            messages: LLM messages in standard format
            image_path: Optional path to image for vision models
            provider: LLM provider
            model: Model name
            fallback_result: Result to return if call is skipped
            
        Returns:
            LLM response dict or fallback_result if skipped
        """
        start_time = time.time()
        
        # Check if we can make this call
        if not self.guard.can_call(kind):
            print(f"[llm_router] {kind} call limit exceeded")
            return fallback_result
        
        # Determine degradation policy
        degradation = self.guard.should_degrade(kind)
        
        # Skip if budget exceeded
        if degradation == "skip":
            print(f"[llm_router] Skipping {kind} call due to budget")
            self.guard.apply_degradation("skip")
            return fallback_result
        
        # Process image if needed
        processed_image_path = image_path
        if image_path and degradation != "none":
            processed_image_path = self._apply_image_degradation(image_path, kind, degradation)
            self.guard.apply_degradation(degradation)
        
        # Estimate tokens
        has_image = processed_image_path is not None
        estimated_tokens = self._estimate_tokens_for_call(kind, degradation, has_image, messages)
        
        try:
            # Make the actual LLM call
            from .llm_client import call_llm, extract_text_generic
            
            resp = call_llm(
                provider=provider,
                model=model, 
                messages=messages,
                image_path=processed_image_path
            )
            
            # Extract response text
            response_text = extract_text_generic(resp)
            
            # Record usage
            actual_tokens = self._extract_token_usage(resp) or estimated_tokens
            self.guard.add_tokens(actual_tokens)
            self.guard.inc(kind)
            
            # Parse response
            try:
                from .gemini_client import parse_first_json
                parsed = parse_first_json(response_text) or {}
            except:
                parsed = {"raw": response_text}
            
            # Emit event
            call_duration_ms = int((time.time() - start_time) * 1000)
            emit_llm_call(
                kind=kind,
                tokens=actual_tokens,
                meta={
                    "provider": provider,
                    "model": model,
                    "degradation": degradation,
                    "has_image": has_image,
                    "duration_ms": call_duration_ms,
                    "estimated_tokens": estimated_tokens
                }
            )
            
            # Record call
            self.call_history.append({
                "kind": kind,
                "tokens": actual_tokens,
                "degradation": degradation,
                "duration_ms": call_duration_ms,
                "success": True
            })
            
            return parsed
            
        except Exception as e:
            # Handle error
            print(f"[llm_router] {kind} call failed: {e}")
            
            # Still record the call attempt
            self.guard.inc(kind)
            
            call_duration_ms = int((time.time() - start_time) * 1000)
            emit_llm_call(
                kind=kind,
                tokens=0,
                meta={
                    "provider": provider,
                    "model": model,
                    "degradation": degradation,
                    "has_image": has_image,
                    "duration_ms": call_duration_ms,
                    "error": str(e)
                }
            )
            
            self.call_history.append({
                "kind": kind,
                "tokens": 0,
                "degradation": degradation,
                "duration_ms": call_duration_ms,
                "success": False,
                "error": str(e)
            })
            
            return fallback_result
    
    def get_call_stats(self) -> dict:
        """Get statistics about calls made through this router"""
        total_calls = len(self.call_history)
        if total_calls == 0:
            return {"total_calls": 0}
        
        successful_calls = sum(1 for call in self.call_history if call["success"])
        total_tokens = sum(call["tokens"] for call in self.call_history)
        total_duration = sum(call["duration_ms"] for call in self.call_history)
        
        degradation_counts = {}
        kind_counts = {}
        
        for call in self.call_history:
            deg = call.get("degradation", "none")
            degradation_counts[deg] = degradation_counts.get(deg, 0) + 1
            
            kind = call.get("kind", "unknown")
            kind_counts[kind] = kind_counts.get(kind, 0) + 1
        
        return {
            "total_calls": total_calls,
            "successful_calls": successful_calls,
            "success_rate": successful_calls / total_calls if total_calls > 0 else 0,
            "total_tokens": total_tokens,
            "avg_tokens_per_call": total_tokens / successful_calls if successful_calls > 0 else 0,
            "total_duration_ms": total_duration,
            "avg_duration_ms": total_duration / total_calls if total_calls > 0 else 0,
            "degradation_counts": degradation_counts,
            "kind_counts": kind_counts
        }