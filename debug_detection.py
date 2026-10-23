#!/usr/bin/env python3
"""
Debug what YOLO is actually detecting in 1.png
"""

import requests
import base64
import json
import cv2
import numpy as np
from detector_service import DetectorService

def debug_yolo_detection():
    """Debug YOLO detection to see what candidates exist"""
    print("🔍 DEBUGGING: What does YOLO actually detect in 1.png?")
    print("=" * 60)

    # Load image
    img = cv2.imread('1.png')
    if img is None:
        print("❌ Could not load 1.png")
        return

    print(f"✅ Image loaded: {img.shape[1]}x{img.shape[0]} pixels")

    # Run YOLO detection directly
    detector = DetectorService()
    candidates = detector.run_yolo(img, conf=0.35)

    print(f"🎯 YOLO found {len(candidates)} candidates:")
    print("-" * 60)

    # Show all candidates
    for i, candidate in enumerate(candidates):
        x1, y1, x2, y2 = candidate.xyxy
        center_x, center_y = candidate.center
        area = candidate.area

        print(f"{i+1:2d}. ID:{candidate.id} Class:'{candidate.cls}' Conf:{candidate.score:.3f}")
        print(f"    BBox: [{x1:.0f}, {y1:.0f}, {x2:.0f}, {y2:.0f}] Center:[{center_x:.0f}, {center_y:.0f}] Area:{area:.0f}")

        # Check if this is near the click point [1745, 707]
        if abs(center_x - 1745) < 100 and abs(center_y - 707) < 100:
            print(f"    ⭐ THIS IS NEAR THE CLICK POINT [1745, 707] ⭐")

    # Find what's at the click point specifically
    print(f"\n🎯 ANALYSIS: What's at click point [1745, 707]?")
    print("-" * 40)

    target_x, target_y = 1745, 707
    closest_candidate = None
    min_distance = float('inf')

    for candidate in candidates:
        center_x, center_y = candidate.center
        distance = ((center_x - target_x)**2 + (center_y - target_y)**2)**0.5

        if distance < min_distance:
            min_distance = distance
            closest_candidate = candidate

    if closest_candidate:
        print(f"Closest to [1745, 707]:")
        print(f"  - Class: '{closest_candidate.cls}'")
        print(f"  - Confidence: {closest_candidate.score:.3f}")
        print(f"  - Distance: {min_distance:.1f} pixels")
        print(f"  - Center: {closest_candidate.center}")

        # Check if it's actually inside the bounding box
        x1, y1, x2, y2 = closest_candidate.xyxy
        if x1 <= target_x <= x2 and y1 <= target_y <= y2:
            print(f"  ✅ Click point IS INSIDE this candidate's bounding box")
            return closest_candidate.cls
        else:
            print(f"  ❌ Click point is OUTSIDE the bounding box")
    else:
        print("❌ No candidates found")

    return None

def test_api_with_debug():
    """Test API and compare with direct YOLO results"""
    print(f"\n🔍 COMPARING: API vs Direct YOLO Detection")
    print("=" * 60)

    # Direct YOLO detection
    detected_class = debug_yolo_detection()

    # API call
    with open('1.png', 'rb') as f:
        img_b64 = base64.b64encode(f.read()).decode()

    data = {
        'image': {'base64': img_b64, 'format': 'png'},
        'capture': {'mode': 'full', 'screen_size': [2888, 1572], 'dpr': 1.0},
        'context': {'goal': '找到搜索输入框'},
        'options': {'return_overlay': True, 'max_candidates': 15},
        'idempotency_key': 'debug_test'
    }

    resp = requests.post('http://localhost:8000/v1/pick', json=data, timeout=30)

    if resp.status_code == 200:
        result = resp.json()
        if result.get('ok') and result.get('data', {}).get('decision'):
            decision = result['data']['decision']
            point = decision.get('point_in_capture', [])
            confidence = decision.get('confidence', 0)
            reason = decision.get('reason', '')

            print(f"\n📊 API RESULT:")
            print(f"  - Click point: {point}")
            print(f"  - Confidence: {confidence:.1%}")
            print(f"  - Reason: {reason[:100]}...")

            print(f"\n🔍 ANALYSIS:")
            if detected_class:
                print(f"  - YOLO detected: '{detected_class}' at that location")
                if detected_class.lower() in ['textbox', 'input', 'text']:
                    print(f"  ✅ This IS a text input element!")
                elif detected_class.lower() in ['button', 'icon']:
                    print(f"  ❌ This is NOT a text input - it's a {detected_class}")
                else:
                    print(f"  ⚠️  Unknown if '{detected_class}' is a search input")
            else:
                print(f"  ❌ No YOLO detection at that point")

if __name__ == "__main__":
    test_api_with_debug()