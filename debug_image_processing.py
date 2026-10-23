#!/usr/bin/env python3
"""
Debug script to compare image processing between direct call and API call
"""

import cv2
import numpy as np
import base64
from app import decode_image_to_bgr
from schemas import ImageSpec

def test_image_processing():
    """Compare image processing between direct load and base64 decode"""

    # Method 1: Direct load (what works)
    img_direct = cv2.imread("1.png")
    print(f"Direct load - Shape: {img_direct.shape}, dtype: {img_direct.dtype}")
    print(f"Direct load - Min/Max: {img_direct.min()}/{img_direct.max()}")

    # Method 2: Via base64 (what the API uses)
    with open("1_b64.txt", "r") as f:
        img_b64 = f.read().strip()

    # Create ImageSpec
    image_spec = ImageSpec(base64=img_b64, format="png")

    # Decode using API method
    img_api = decode_image_to_bgr(image_spec)
    print(f"API decode - Shape: {img_api.shape}, dtype: {img_api.dtype}")
    print(f"API decode - Min/Max: {img_api.min()}/{img_api.max()}")

    # Compare arrays
    if np.array_equal(img_direct, img_api):
        print("✅ Images are identical!")
    else:
        print("❌ Images are different!")

        # Check differences
        diff = np.abs(img_direct.astype(np.float32) - img_api.astype(np.float32))
        max_diff = diff.max()
        mean_diff = diff.mean()
        print(f"Max difference: {max_diff}")
        print(f"Mean difference: {mean_diff}")

        # Check if shapes are different
        if img_direct.shape != img_api.shape:
            print(f"Shape mismatch: {img_direct.shape} vs {img_api.shape}")

    # Test with detector service on both
    from detector_service import DetectorService
    detector = DetectorService()

    print("\nTesting detector with direct image...")
    candidates_direct = detector.run_yolo(img_direct, conf=0.35)
    print(f"Direct: {len(candidates_direct)} candidates")

    print("\nTesting detector with API-decoded image...")
    candidates_api = detector.run_yolo(img_api, conf=0.35)
    print(f"API: {len(candidates_api)} candidates")

if __name__ == "__main__":
    test_image_processing()