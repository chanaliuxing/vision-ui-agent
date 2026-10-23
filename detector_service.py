#!/usr/bin/env python3
"""
Detector Service - YOLO Detection Wrapper
Provides a stable interface for YOLO object detection
"""

import time
from typing import List, Dict, Any, Optional
import numpy as np
import logging

logger = logging.getLogger(__name__)


class Candidate:
    """Detection candidate with standardized interface"""

    def __init__(self, id: str, xyxy: List[float], cls: str, score: float, text_hint: Optional[str] = None):
        self.id = id
        self.xyxy = xyxy  # [x1, y1, x2, y2]
        self.cls = cls
        self.score = score
        self.text_hint = text_hint

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format"""
        return {
            "id": self.id,
            "xyxy": self.xyxy,
            "cls": self.cls,
            "score": self.score,
            "text_hint": self.text_hint
        }

    @property
    def center(self) -> List[float]:
        """Get center point of bounding box"""
        x1, y1, x2, y2 = self.xyxy
        return [(x1 + x2) / 2, (y1 + y2) / 2]

    @property
    def area(self) -> float:
        """Get bounding box area"""
        x1, y1, x2, y2 = self.xyxy
        return max(0, x2 - x1) * max(0, y2 - y1)


class DetectorService:
    """YOLO detection service with stable interface"""

    def __init__(self):
        """Initialize detector service"""
        self._yolo_mode = None
        self._initialize()

    def _initialize(self):
        """Initialize YOLO detection capabilities"""
        try:
            # Import YOLO functionality from app.py
            from app import run_yolo, _sort_indices_tl
            self._run_yolo = run_yolo
            self._sort_indices = _sort_indices_tl
            logger.info("DetectorService initialized successfully")
        except ImportError as e:
            logger.error(f"Failed to import YOLO functionality: {e}")
            raise RuntimeError("YOLO detection not available")

    def run_yolo(self, img_bgr: np.ndarray, conf: float = 0.35, iou: float = 0.45,
                 imgsz: int = 1280, max_det: int = 300) -> List[Candidate]:
        """
        Run YOLO detection on image and return sorted candidates

        Args:
            img_bgr: Image in BGR format (numpy array)
            conf: Confidence threshold
            iou: IOU threshold for NMS
            imgsz: Input image size for YOLO
            max_det: Maximum number of detections

        Returns:
            List[Candidate]: Sorted list of detection candidates
        """
        try:
            t_start = time.time()

            # Run YOLO detection using existing app.py functionality
            logger.info(f"Calling _run_yolo with conf={conf}, iou={iou}, imgsz={imgsz}")
            detections = self._run_yolo(img_bgr, conf=conf, iou=iou, imgsz=imgsz, max_det=max_det)
            logger.info(f"_run_yolo returned {len(detections)} detections")

            # Convert to Candidate objects
            candidates = []
            for i, det in enumerate(detections):
                # Convert bbox from [x,y,w,h] to [x1,y1,x2,y2]
                x, y, w, h = det.bbox
                xyxy = [x, y, x + w, y + h]

                candidate = Candidate(
                    id=f"cand_{i+1}",
                    xyxy=xyxy,
                    cls=det.label,
                    score=det.conf,
                    text_hint=None
                )
                candidates.append(candidate)

            logger.info(f"Converted to {len(candidates)} candidates")

            # Sort candidates by reading order (top-left to bottom-right)
            if candidates:
                xyxy_list = [c.xyxy for c in candidates]
                sorted_indices = self._sort_indices(xyxy_list)
                candidates = [candidates[i] for i in sorted_indices]

                # Update IDs to reflect sorted order
                for i, candidate in enumerate(candidates):
                    candidate.id = f"cand_{i+1}"

            t_elapsed = time.time() - t_start
            logger.info(f"YOLO detection completed: {len(candidates)} candidates in {t_elapsed*1000:.1f}ms")

            return candidates

        except Exception as e:
            logger.error(f"YOLO detection failed: {e}")
            raise RuntimeError(f"Detection failed: {e}")

    def get_candidates_json(self, candidates: List[Candidate], include_crops: bool = False) -> List[Dict[str, Any]]:
        """
        Convert candidates to JSON format for LLM consumption

        Args:
            candidates: List of detection candidates
            include_crops: Whether to include cropped images as base64

        Returns:
            List of candidate dictionaries
        """
        result = []
        for candidate in candidates:
            candidate_dict = candidate.to_dict()

            # Add computed properties
            candidate_dict.update({
                "center": candidate.center,
                "area": candidate.area,
                "visible": True,  # Assume all YOLO detections are visible
                "enabled": True   # Assume all YOLO detections are enabled
            })

            # Optionally add cropped image (not implemented for now)
            if include_crops:
                candidate_dict["crop_b64"] = None  # Would require image cropping implementation

            result.append(candidate_dict)

        return result

    def filter_by_classes(self, candidates: List[Candidate],
                         preferred_classes: Optional[List[str]] = None,
                         negative_classes: Optional[List[str]] = None) -> List[Candidate]:
        """
        Filter candidates by class preferences

        Args:
            candidates: Input candidates
            preferred_classes: Classes to prefer (higher priority)
            negative_classes: Classes to exclude

        Returns:
            Filtered list of candidates
        """
        if not candidates:
            return candidates

        filtered = candidates.copy()

        # Remove negative classes
        if negative_classes:
            filtered = [c for c in filtered if c.cls not in negative_classes]

        # Prioritize preferred classes (move to front)
        if preferred_classes:
            preferred = [c for c in filtered if c.cls in preferred_classes]
            others = [c for c in filtered if c.cls not in preferred_classes]
            filtered = preferred + others

        return filtered

    def limit_candidates(self, candidates: List[Candidate], max_candidates: int = 32) -> List[Candidate]:
        """
        Limit number of candidates to prevent LLM overload

        Args:
            candidates: Input candidates
            max_candidates: Maximum number to keep

        Returns:
            Limited list of candidates
        """
        if len(candidates) <= max_candidates:
            return candidates

        # Keep highest confidence candidates
        sorted_by_conf = sorted(candidates, key=lambda c: c.score, reverse=True)
        return sorted_by_conf[:max_candidates]

    def get_detection_stats(self, candidates: List[Candidate]) -> Dict[str, Any]:
        """
        Get statistics about detected candidates

        Args:
            candidates: List of candidates

        Returns:
            Statistics dictionary
        """
        if not candidates:
            return {
                "total_count": 0,
                "class_counts": {},
                "avg_confidence": 0.0,
                "confidence_range": [0.0, 0.0]
            }

        # Count by class
        class_counts = {}
        for candidate in candidates:
            class_counts[candidate.cls] = class_counts.get(candidate.cls, 0) + 1

        # Confidence statistics
        confidences = [c.score for c in candidates]
        avg_conf = sum(confidences) / len(confidences)
        min_conf = min(confidences)
        max_conf = max(confidences)

        return {
            "total_count": len(candidates),
            "class_counts": class_counts,
            "avg_confidence": avg_conf,
            "confidence_range": [min_conf, max_conf]
        }


# Singleton instance for dependency injection
_detector_service_instance = None

def get_detector_service() -> DetectorService:
    """Get singleton detector service instance"""
    global _detector_service_instance
    if _detector_service_instance is None:
        _detector_service_instance = DetectorService()
    return _detector_service_instance