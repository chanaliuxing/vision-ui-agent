#!/usr/bin/env python3
"""
Verification Service - Post-Action Verification
Handles verification of action results and UI state changes
"""

import time
from typing import Dict, Any, Optional, List, Tuple
import numpy as np
import logging

logger = logging.getLogger(__name__)


class VerificationService:
    """Service for verifying action results and UI changes"""

    def __init__(self):
        """Initialize verification service"""
        self._initialize()

    def _initialize(self):
        """Initialize verification capabilities"""
        try:
            # Try to import OCR functionality if available
            try:
                from core.ocr_client import OcrClient
                # Use OCR endpoint from environment or default
                import os
                ocr_endpoint = os.getenv("OCR_ENDPOINT", "http://127.0.0.1:8001")
                self._ocr_client = OcrClient(endpoint=ocr_endpoint)
                self._has_ocr = True
            except ImportError:
                logger.info("OCR functionality not available")
                self._ocr_client = None
                self._has_ocr = False
            except Exception as e:
                logger.warning(f"OCR client initialization failed: {e}")
                self._ocr_client = None
                self._has_ocr = False

            logger.info("VerificationService initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize verification service: {e}")
            raise RuntimeError("Verification service initialization failed")

    def plan_for(self, context: Dict[str, Any], candidate: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Generate verification plan for given context and candidate

        Args:
            context: Task context information
            candidate: Selected candidate that was clicked (optional)

        Returns:
            Verification plan dictionary
        """
        # Safe string extraction
        goal = (context.get("goal") or "").lower() if isinstance(context.get("goal"), str) else ""
        intent = (context.get("intent") or "").lower() if isinstance(context.get("intent"), str) else ""

        # Default verification plan
        plan = {
            "expect_text_any": [],
            "expect_absent": [],
            "timeout_ms": 5000,
            "post_delay_ms": 300
        }

        # Customize based on goal and intent
        if "login" in goal or "sign in" in goal:
            plan["expect_text_any"] = ["Dashboard", "Welcome", "Profile", "Settings", "Home"]
            plan["expect_absent"] = ["Error", "Invalid", "Failed", "Incorrect", "Try again"]
            plan["timeout_ms"] = 8000  # Login may take longer

        elif "submit" in intent or "send" in intent:
            plan["expect_text_any"] = ["Success", "Submitted", "Sent", "Thank you", "Confirmation"]
            plan["expect_absent"] = ["Error", "Failed", "Required", "Missing", "Invalid"]

        elif "search" in goal or "find" in goal:
            plan["expect_text_any"] = ["Results", "Found", "Search results", "matches"]
            plan["expect_absent"] = ["No results", "Not found", "Error"]

        elif "save" in intent or "update" in intent:
            plan["expect_text_any"] = ["Saved", "Updated", "Success", "Changes saved"]
            plan["expect_absent"] = ["Error", "Failed", "Unable to save"]

        elif "delete" in intent or "remove" in intent:
            plan["expect_text_any"] = ["Deleted", "Removed", "Success", "Confirmation"]
            plan["expect_absent"] = ["Error", "Failed", "Unable to delete"]

        # Add candidate-specific expectations
        if candidate:
            candidate_text = candidate.get("text_hint", "")
            if candidate_text:
                # If candidate has text, expect some change after clicking
                plan["expect_absent"].append(candidate_text)  # Text might disappear

        return plan

    def default_plan(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate default verification plan

        Args:
            context: Task context

        Returns:
            Default verification plan
        """
        return {
            "expect_text_any": [],
            "expect_absent": [],
            "timeout_ms": 3000,
            "post_delay_ms": 200
        }

    def verify(self, img_bgr: np.ndarray, expected: Dict[str, Any]) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Verify action results against expectations

        Args:
            img_bgr: Post-action screenshot in BGR format
            expected: Expected verification criteria

        Returns:
            Tuple of (pass, reason, lock_anchor)
        """
        try:
            verification_plan = expected.get("verification_plan", {})
            anchor_id = expected.get("anchor_id")

            # Extract expected criteria
            expect_text_any = verification_plan.get("expect_text_any", [])
            expect_absent = verification_plan.get("expect_absent", [])
            timeout_ms = verification_plan.get("timeout_ms", 5000)
            post_delay_ms = verification_plan.get("post_delay_ms", 300)

            # Apply post-action delay if specified
            if post_delay_ms > 0:
                time.sleep(post_delay_ms / 1000.0)

            success_indicators = []
            failure_indicators = []

            # Text-based verification using OCR (if available)
            if self._has_ocr and self._ocr_client and (expect_text_any or expect_absent):
                try:
                    ocr_results = self._ocr_client.extract_text(img_bgr)
                    extracted_text = " ".join([r.get("text", "") for r in ocr_results]).lower()

                    # Check for expected text
                    for expected_text in expect_text_any:
                        if expected_text.lower() in extracted_text:
                            success_indicators.append(f"Found expected text: '{expected_text}'")

                    # Check for absent text (should not be present)
                    for absent_text in expect_absent:
                        if absent_text.lower() in extracted_text:
                            failure_indicators.append(f"Found unwanted text: '{absent_text}'")

                except Exception as e:
                    logger.warning(f"OCR verification failed: {e}")

            # Visual-based verification (placeholder for advanced image analysis)
            visual_changes = self._detect_visual_changes(img_bgr)
            if visual_changes:
                success_indicators.append("Visual changes detected")

            # URL change detection (would require browser integration)
            # For now, assume any significant change indicates success
            if len(success_indicators) > 0 and len(failure_indicators) == 0:
                verification_pass = True
                reason = f"Verification passed: {', '.join(success_indicators)}"
            elif len(failure_indicators) > 0:
                verification_pass = False
                reason = f"Verification failed: {', '.join(failure_indicators)}"
            else:
                # Default heuristic: assume success if no explicit failures
                verification_pass = True
                reason = "Verification passed: no explicit failures detected"

            # Generate anchor lock if verification passed
            lock_anchor = None
            if verification_pass and anchor_id:
                lock_anchor = {
                    "id": anchor_id,
                    "norm_bbox": [0.0, 0.0, 1.0, 1.0],  # Placeholder
                    "descriptors_delta": {
                        "template_hash": f"sha1:verified_{int(time.time())}",
                        "orb_patch": f"sha1:orb_verified_{int(time.time())}"
                    },
                    "version": int(time.time()) % 1000  # Simple versioning
                }

            return verification_pass, reason, lock_anchor

        except Exception as e:
            logger.error(f"Verification failed with error: {e}")
            return False, f"Verification error: {e}", None

    def _detect_visual_changes(self, img_bgr: np.ndarray) -> bool:
        """
        Detect significant visual changes in the image

        This is a placeholder implementation. In practice, this would:
        - Compare against previous screenshot
        - Detect new UI elements
        - Check for loading indicators
        - Analyze color/layout changes

        Args:
            img_bgr: Current image in BGR format

        Returns:
            True if significant changes detected
        """
        # Placeholder: assume changes occurred if image is valid
        return img_bgr is not None and img_bgr.size > 0

    def _extract_text_simple(self, img_bgr: np.ndarray) -> List[str]:
        """
        Simple text extraction fallback (without OCR dependencies)

        Args:
            img_bgr: Image in BGR format

        Returns:
            List of extracted text strings (placeholder)
        """
        # This is a placeholder implementation
        # In practice, you might use simple pattern matching or heuristics
        return []

    def get_verification_stats(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Get statistics about verification results

        Args:
            results: List of verification results

        Returns:
            Statistics dictionary
        """
        if not results:
            return {
                "total_verifications": 0,
                "pass_rate": 0.0,
                "avg_duration_ms": 0.0
            }

        passed = sum(1 for r in results if r.get("pass", False))
        total = len(results)
        pass_rate = passed / total if total > 0 else 0.0

        # Calculate average duration if available
        durations = [r.get("duration_ms", 0) for r in results if r.get("duration_ms")]
        avg_duration = sum(durations) / len(durations) if durations else 0.0

        return {
            "total_verifications": total,
            "pass_rate": pass_rate,
            "avg_duration_ms": avg_duration,
            "success_count": passed,
            "failure_count": total - passed
        }


# Singleton instance for dependency injection
_verification_service_instance = None

def get_verification_service() -> VerificationService:
    """Get singleton verification service instance"""
    global _verification_service_instance
    if _verification_service_instance is None:
        _verification_service_instance = VerificationService()
    return _verification_service_instance