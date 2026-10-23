import requests
import json
import uuid

BASE_URL = "http://localhost:8000"
TINY_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="

def test_forced_failure():
    print("Testing forced failure to check fallback logic...")
    request_id = f"fail_test_{uuid.uuid4().hex[:8]}"
    payload = {
        "phase": "planner_next",
        "goal": "Identify image",
        "image": {"base64": TINY_PNG_B64, "format": "png"},
        "request_id": request_id,
        "provider": "ollama",
        "model": "non_existent_model_12345" # This should fail
    }
    
    try:
        r = requests.post(f"{BASE_URL}/v1/autostep", json=payload, timeout=120)
        print(f"Status: {r.status_code}")
        data = r.json()
        print(f"Server reported provider: {data.get('provider')}")
        print(f"Server reported model: {data.get('model')}")
        return True
    except Exception as e:
        print(f"Request failed: {e}")
        return False

if __name__ == "__main__":
    test_forced_failure()
