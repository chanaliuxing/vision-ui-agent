import requests
import json
import uuid

BASE_URL = "http://localhost:8000"
TINY_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="

def test_actual_execution():
    print("Testing actual LLM execution path...")
    request_id = f"actual_test_{uuid.uuid4().hex[:8]}"
    payload = {
        "phase": "planner_next",
        "goal": "Identify image",
        "image": {"base64": TINY_PNG_B64, "format": "png"},
        "request_id": request_id
    }
    
    try:
        r = requests.post(f"{BASE_URL}/v1/autostep", json=payload, timeout=120)
        if r.status_code == 200:
            data = r.json()
            # The server's response top-level 'provider' field comes from generate_json
            print(f"Server reported provider: {data.get('provider')}")
            print(f"Server reported model: {data.get('model')}")
            
            # Check if reason suggests fallback
            reason = data.get('reason', '')
            print(f"Reason: {reason}")
            
            return True
        else:
            print(f"Error: {r.status_code} - {r.text}")
            return False
    except Exception as e:
        print(f"Request failed: {e}")
        return False

if __name__ == "__main__":
    test_actual_execution()
