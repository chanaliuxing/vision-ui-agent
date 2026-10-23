#!/usr/bin/env python3
"""
Debug script to test detector service directly
"""

import cv2
import numpy as np
from detector_service import DetectorService

def test_detector_service():
    """Test detector service directly with the Xiaohongshu screenshot"""

    # Load the image
    img_bgr = cv2.imread("1.png")
    print(f"Image shape: {img_bgr.shape}")
    print(f"Image dtype: {img_bgr.dtype}")
    print(f"Image min/max: {img_bgr.min()}/{img_bgr.max()}")

    # Initialize detector service
    print("Initializing detector service...")
    try:
        detector = DetectorService()
        print("✅ Detector service initialized")
    except Exception as e:
        print(f"❌ Failed to initialize detector service: {e}")
        return

    # Run YOLO detection
    print("Running YOLO detection...")
    try:
        candidates = detector.run_yolo(img_bgr, conf=0.35, iou=0.45)
        print(f"✅ YOLO detection completed: {len(candidates)} candidates found")

        # Print first few candidates
        for i, candidate in enumerate(candidates[:5]):
            print(f"  Candidate {i+1}: {candidate.cls} @ {candidate.xyxy} (conf: {candidate.score:.3f})")

    except Exception as e:
        print(f"❌ YOLO detection failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # Test filter_by_classes
    print("Testing filter_by_classes...")
    try:
        filtered = detector.filter_by_classes(candidates)
        print(f"✅ Filtering completed: {len(filtered)} candidates after filtering")
    except Exception as e:
        print(f"❌ Filtering failed: {e}")

    # Test limit_candidates
    print("Testing limit_candidates...")
    try:
        limited = detector.limit_candidates(filtered, max_candidates=32)
        print(f"✅ Limiting completed: {len(limited)} candidates after limiting")
    except Exception as e:
        print(f"❌ Limiting failed: {e}")

if __name__ == "__main__":
    test_detector_service()