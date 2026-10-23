#!/usr/bin/env python3
"""
Anchors Service - Template/Feature Matching Wrapper
Provides a stable interface for anchor-based element matching
"""

import hashlib
import time
import uuid
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
import logging

logger = logging.getLogger(__name__)


class AnchorsService:
    """Anchor-based element matching service"""

    def __init__(self):
        """Initialize anchors service"""
        self._initialize()

    def _initialize(self):
        """Initialize anchor functionality"""
        try:
            # Import anchor functionality from core
            from core.anchors import anchors_from, anchors_match, adjust_template_anchor
            self._anchors_from = anchors_from
            self._anchors_match = anchors_match
            self._adjust_template_anchor = adjust_template_anchor
            logger.info("AnchorsService initialized successfully")
        except ImportError as e:
            logger.error(f"Failed to import anchor functionality: {e}")
            raise RuntimeError("Anchor functionality not available")

    def quick_match(self, img_bgr: np.ndarray, anchors: List[Dict[str, Any]]) -> Optional[Tuple[List[int], float, str]]:
        """
        Quick anchor matching to find known elements

        Args:
            img_bgr: Image in BGR format
            anchors: List of known anchor specifications

        Returns:
            Tuple of (point, confidence, anchor_id) if match found, None otherwise
        """
        if not anchors:
            return None

        best_match = None
        best_confidence = 0.0
        best_anchor_id = None

        for anchor_spec in anchors:
            try:
                # Extract anchor data
                anchor_id = anchor_spec.get("id", "unknown")
                norm_ref = anchor_spec.get("norm_ref", {})
                norm_bbox = anchor_spec.get("norm_bbox")
                descriptors = anchor_spec.get("descriptors", {})

                if not norm_bbox:
                    continue

                # Convert normalized bbox to pixel coordinates
                img_h, img_w = img_bgr.shape[:2]
                ref_w = norm_ref.get("w", img_w)
                ref_h = norm_ref.get("h", img_h)

                # Scale normalized coordinates to current image
                scale_x = img_w / ref_w
                scale_y = img_h / ref_h
                x1 = int(norm_bbox[0] * img_w)
                y1 = int(norm_bbox[1] * img_h)
                x2 = int(norm_bbox[2] * img_w)
                y2 = int(norm_bbox[3] * img_h)

                # Create legacy anchor dict for matching
                # Accept either 'template_png' (preferred) or a transport-compatible 'template_hash'
                # Note: some schema variants may strip unknown fields; mirroring into template_hash allows transport.
                template_hex = descriptors.get("template_png") or descriptors.get("template_hash")
                legacy_anchor = {
                    "type": "template",
                    "roi": [x1, y1, x2, y2],
                    "template_png": template_hex or "",
                    "method": "TM_CCOEFF_NORMED",
                    "th": 0.80,
                }

                # Attempt template matching if template data exists
                if template_hex:
                    confidence = self._anchors_match(img_bgr, legacy_anchor)
                    if confidence > best_confidence and confidence > 0.75:
                        best_confidence = confidence
                        best_anchor_id = anchor_id
                        # Calculate center point
                        center_x = (x1 + x2) // 2
                        center_y = (y1 + y2) // 2
                        best_match = [center_x, center_y]

            except Exception as e:
                logger.warning(f"Failed to match anchor {anchor_spec.get('id', 'unknown')}: {e}")
                continue

        if best_match:
            logger.info(f"Anchor match found: {best_anchor_id} with confidence {best_confidence:.3f}")
            return best_match, best_confidence, best_anchor_id

        return None

    def propose_anchor(self, img_bgr: np.ndarray, bbox: List[float],
                      dom_hints: Optional[Dict[str, List[str]]] = None) -> Dict[str, Any]:
        """
        Generate anchor proposal for future matching

        Args:
            img_bgr: Image in BGR format
            bbox: Bounding box [x1, y1, x2, y2] in pixel coordinates
            dom_hints: Optional DOM hints for enhanced matching

        Returns:
            Anchor proposal dictionary
        """
        try:
            # Generate anchor descriptors
            anchor_data = self._anchors_from(img_bgr, bbox)

            # Create unique ID for this anchor
            anchor_id = self._generate_anchor_id(bbox, img_bgr.shape[:2])

            # Calculate normalized coordinates
            img_h, img_w = img_bgr.shape[:2]
            norm_bbox = [
                bbox[0] / img_w,  # x1
                bbox[1] / img_h,  # y1
                bbox[2] / img_w,  # x2
                bbox[3] / img_h   # y2
            ]

            # Create anchor proposal
            proposal = {
                "id": anchor_id,
                "type": "compound",
                "descriptors": {
                    # Store full template PNG hex for robust matching.
                    # Duplicate into 'template_hash' for schema transports that don't allow custom keys.
                    "template_png": anchor_data.get("template_png", ""),
                    "template_hash": anchor_data.get("template_png", ""),
                    "orb": {
                        "kpts": 64,  # Placeholder - would need actual ORB implementation
                        "desc_hash": self._hash_bbox_area(bbox)
                    },
                    "color_hist": self._hash_bbox_area(bbox)  # Placeholder
                },
                "norm_ref": {
                    "kind": "window",  # Default to window-relative
                    "w": img_w,
                    "h": img_h
                },
                "norm_bbox": norm_bbox,
                "dom_hints": dom_hints or {}
            }

            logger.info(f"Generated anchor proposal: {anchor_id}")
            return proposal

        except Exception as e:
            logger.error(f"Failed to generate anchor proposal: {e}")
            # Return minimal proposal
            return {
                "id": f"anchor_{int(time.time())}",
                "type": "simple",
                "descriptors": {},
                "norm_ref": {"kind": "window", "w": img_bgr.shape[1], "h": img_bgr.shape[0]},
                "norm_bbox": [0, 0, 1, 1],
                "dom_hints": {}
            }

    def verify_anchor(self, img_bgr: np.ndarray, anchor: Dict[str, Any]) -> float:
        """
        Verify anchor quality against current image

        Args:
            img_bgr: Current image in BGR format
            anchor: Anchor specification to verify

        Returns:
            Verification score (0.0 to 1.0)
        """
        try:
            # Use quick_match with single anchor
            result = self.quick_match(img_bgr, [anchor])
            if result:
                _, confidence, _ = result
                return confidence
            return 0.0
        except Exception as e:
            logger.warning(f"Anchor verification failed: {e}")
            return 0.0

    def lock_anchor(self, old_anchor: Dict[str, Any],
                   verification_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create locked anchor with updated descriptors

        Args:
            old_anchor: Original anchor proposal
            verification_result: Results from verification

        Returns:
            Updated anchor with new version
        """
        try:
            locked_anchor = {
                "id": old_anchor.get("id", f"locked_{int(time.time())}"),
                "norm_bbox": old_anchor.get("norm_bbox", [0, 0, 1, 1]),
                "descriptors_delta": {
                    # In a real implementation, this would contain actual descriptor updates
                    "template_hash": f"sha1:new_hash_{int(time.time())}",
                    "orb_patch": f"sha1:orb_patch_{int(time.time())}"
                },
                "version": old_anchor.get("version", 1) + 1
            }

            logger.info(f"Locked anchor: {locked_anchor['id']} v{locked_anchor['version']}")
            return locked_anchor

        except Exception as e:
            logger.error(f"Failed to lock anchor: {e}")
            return {}

    def _generate_anchor_id(self, bbox: List[float], img_shape: Tuple[int, int]) -> str:
        """Generate unique anchor ID based on bbox and image properties"""
        data = f"{bbox}_{img_shape}_{time.time()}"
        hash_obj = hashlib.sha1(data.encode())
        return f"anchor_{hash_obj.hexdigest()[:12]}"

    def _hash_bbox_area(self, bbox: List[float]) -> str:
        """Generate hash for bbox area (placeholder for actual feature extraction)"""
        data = f"{bbox[0]:.1f}_{bbox[1]:.1f}_{bbox[2]:.1f}_{bbox[3]:.1f}"
        return f"sha1:{hashlib.sha1(data.encode()).hexdigest()[:16]}"

    def get_anchor_stats(self, anchors: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Get statistics about anchor collection

        Args:
            anchors: List of anchor specifications

        Returns:
            Statistics dictionary
        """
        if not anchors:
            return {
                "total_count": 0,
                "types": {},
                "avg_version": 0.0
            }

        # Count by type
        type_counts = {}
        versions = []
        for anchor in anchors:
            anchor_type = anchor.get("type", "unknown")
            type_counts[anchor_type] = type_counts.get(anchor_type, 0) + 1
            versions.append(anchor.get("version", 1))

        avg_version = sum(versions) / len(versions) if versions else 0.0

        return {
            "total_count": len(anchors),
            "types": type_counts,
            "avg_version": avg_version
        }


# Singleton instance for dependency injection
_anchors_service_instance = None

def get_anchors_service() -> AnchorsService:
    """Get singleton anchors service instance"""
    global _anchors_service_instance
    if _anchors_service_instance is None:
        _anchors_service_instance = AnchorsService()
    return _anchors_service_instance
