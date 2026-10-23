import requests
import json
import uuid

BASE_URL = "http://localhost:8000"
TINY_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="

def test_default_config():
    print("Testing default configuration (should pick from .env)...")
    request_id = f"default_test_{uuid.uuid4().hex[:8]}"
    payload = {
        "phase": "planner_next",
        "goal": "Identify image",
        "image": {"base64": TINY_PNG_B64, "format": "png"},
        "request_id": request_id
        # Note: No provider/model specified
    }
    
    try:
        r = requests.post(f"{BASE_URL}/v1/autostep", json=payload, timeout=30)
        if r.status_code == 200:
            data = r.json()
            print(f"Server picked: {data.get('provider')} / {data.get('model')}")
            return True
        else:
            print(f"Error: {r.status_code} - {r.text}")
            return False
    except Exception as e:
        print(f"Request failed: {e}")
        return False

if __name__ == "__main__":
    test_default_config()
