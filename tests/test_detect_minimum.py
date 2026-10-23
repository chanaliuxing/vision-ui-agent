# tests/test_detect_minimum.py
import pytest
import requests
import base64
import json
import os
from pathlib import Path

# Test configuration
API_BASE_URL = "http://localhost:8000"
TEST_IMAGE_PATH = os.path.join(os.path.dirname(__file__), "test_image.png")

def create_test_image():
    """Create a simple test image for testing"""
    import numpy as np
    from PIL import Image

    # Create a simple 200x200 image with some colored rectangles
    img_array = np.zeros((200, 200, 3), dtype=np.uint8)

    # Add a red rectangle (might be detected as button)
    img_array[50:100, 50:100] = [255, 0, 0]  # Red

    # Add a blue rectangle (might be detected as input)
    img_array[120:140, 50:150] = [0, 0, 255]  # Blue

    # Add a green rectangle (might be detected as text)
    img_array[160:180, 50:120] = [0, 255, 0]  # Green

    # Save as PNG
    img = Image.fromarray(img_array)
    img.save(TEST_IMAGE_PATH)
    return TEST_IMAGE_PATH

def image_to_base64(image_path):
    """Convert image file to base64 string"""
    with open(image_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
    return encoded_string

def test_detect_endpoint_basic():
    """Test basic /detect endpoint functionality"""
    # Create test image if it doesn't exist
    if not os.path.exists(TEST_IMAGE_PATH):
        create_test_image()

    # Convert image to base64
    image_b64 = image_to_base64(TEST_IMAGE_PATH)

    # Prepare request data
    data = {
        "image_b64": image_b64,
        "classes": json.dumps(["button", "input", "text"]),
        "top_k": 5,
        "min_conf": 0.1,  # Lower confidence for synthetic test image
        "return_image": False
    }

    # Make request to /detect endpoint
    response = requests.post(f"{API_BASE_URL}/detect", data=data)

    # Assertions
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    result = response.json()

    # Check unified response format
    assert "ok" in result, "Response missing 'ok' field"
    assert result["ok"] is True, f"Expected ok=True, got ok={result['ok']}"

    assert "data" in result, "Response missing 'data' field"
    assert result["data"] is not None, "Data field is None"

    # Check required data fields
    data_obj = result["data"]
    assert "candidates" in data_obj, "Data missing 'candidates' field"
    assert "selected" in data_obj, "Data missing 'selected' field"
    assert "time_ms" in data_obj, "Data missing 'time_ms' field"

    # Check candidates structure
    candidates = data_obj["candidates"]
    assert isinstance(candidates, list), "Candidates should be a list"

    # If we have candidates, check their structure
    if candidates:
        candidate = candidates[0]
        required_fields = ["label", "conf", "rect_abs", "rect_norm", "click_point"]
        for field in required_fields:
            assert field in candidate, f"Candidate missing required field: {field}"

        # Check click_point structure
        click_point = candidate["click_point"]
        assert "x" in click_point, "Click point missing 'x' coordinate"
        assert "y" in click_point, "Click point missing 'y' coordinate"
        assert isinstance(click_point["x"], int), "Click point x should be integer"
        assert isinstance(click_point["y"], int), "Click point y should be integer"

        # Check rect_abs format [x1, y1, x2, y2]
        rect_abs = candidate["rect_abs"]
        assert isinstance(rect_abs, list), "rect_abs should be a list"
        assert len(rect_abs) == 4, "rect_abs should have 4 elements"

        # Check rect_norm format [x1, y1, x2, y2] normalized 0-1
        rect_norm = candidate["rect_norm"]
        assert isinstance(rect_norm, list), "rect_norm should be a list"
        assert len(rect_norm) == 4, "rect_norm should have 4 elements"
        for coord in rect_norm:
            assert 0 <= coord <= 1, f"Normalized coordinate {coord} should be between 0 and 1"

    # Check selected structure (should be same as first candidate if any)
    selected = data_obj["selected"]
    if candidates:
        assert selected is not None, "Selected should not be None when candidates exist"
        # Selected should have same structure as candidates
        required_fields = ["label", "conf", "rect_abs", "rect_norm", "click_point"]
        for field in required_fields:
            assert field in selected, f"Selected missing required field: {field}"
    else:
        # If no candidates, selected can be None
        assert selected is None, "Selected should be None when no candidates exist"

    # Check time_ms is reasonable
    time_ms = data_obj["time_ms"]
    assert isinstance(time_ms, (int, float)), "time_ms should be numeric"
    assert time_ms >= 0, "time_ms should be non-negative"

def test_detect_endpoint_error_handling():
    """Test error handling for missing image"""
    data = {
        "classes": json.dumps(["button"]),
        "top_k": 5,
        "min_conf": 0.5
    }

    response = requests.post(f"{API_BASE_URL}/detect", data=data)

    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    result = response.json()
    assert "ok" in result, "Response missing 'ok' field"
    assert result["ok"] is False, "Expected ok=False for missing image"
    assert "error" in result, "Response missing 'error' field"
    assert result["error"] is not None, "Error field should not be None"

    error_obj = result["error"]
    assert "code" in error_obj, "Error missing 'code' field"
    assert "msg" in error_obj, "Error missing 'msg' field"
    assert error_obj["code"] == "MISSING_IMAGE", f"Expected MISSING_IMAGE, got {error_obj['code']}"

def test_version_endpoint():
    """Test /version endpoint for basic functionality"""
    response = requests.get(f"{API_BASE_URL}/version")

    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    result = response.json()
    assert "ok" in result, "Response missing 'ok' field"
    assert result["ok"] is True, f"Expected ok=True, got ok={result['ok']}"
    assert "data" in result, "Response missing 'data' field"

    data_obj = result["data"]
    required_fields = ["engine", "model", "build", "backend", "device"]
    for field in required_fields:
        assert field in data_obj, f"Version data missing required field: {field}"

    assert data_obj["engine"] == "yolo", f"Expected engine=yolo, got {data_obj['engine']}"

if __name__ == "__main__":
    # Run basic test manually if called directly
    print("Creating test image...")
    create_test_image()
    print(f"Test image created at: {TEST_IMAGE_PATH}")

    print("Testing /detect endpoint...")
    try:
        test_detect_endpoint_basic()
        print("✅ /detect endpoint test passed")
    except Exception as e:
        print(f"❌ /detect endpoint test failed: {e}")

    print("Testing error handling...")
    try:
        test_detect_endpoint_error_handling()
        print("✅ Error handling test passed")
    except Exception as e:
        print(f"❌ Error handling test failed: {e}")

    print("Testing /version endpoint...")
    try:
        test_version_endpoint()
        print("✅ /version endpoint test passed")
    except Exception as e:
        print(f"❌ /version endpoint test failed: {e}")

    print("All tests completed!")