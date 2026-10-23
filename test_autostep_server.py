import base64
import requests
import json
import uuid
import time

BASE_URL = "http://localhost:8000"

# 1x1 white PNG
TINY_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="

def test_health():
    print("Testing /health...")
    try:
        r = requests.get(f"{BASE_URL}/health")
        print(f"Status: {r.status_code}, Body: {r.json()}")
        return r.status_code == 200
    except Exception as e:
        print(f"Failed to connect to server: {e}")
        return False

def test_invalid_phase():
    print("Testing invalid phase...")
    payload = {
        "phase": "invalid_phase",
        "goal": "test"
    }
    r = requests.post(f"{BASE_URL}/v1/autostep", json=payload)
    print(f"Status: {r.status_code}, Body: {r.text}")
    return r.status_code == 422

def test_planner_next_missing_image():
    print("Testing planner_next missing image...")
    payload = {
        "phase": "planner_next",
        "goal": "test goal"
    }
    r = requests.post(f"{BASE_URL}/v1/autostep", json=payload)
    print(f"Status: {r.status_code}, Body: {r.json()}")
    return r.status_code == 400 and r.json()["code"] == "BAD_REQUEST"

def test_planner_next_success():
    print("Testing planner_next success (with multimodal check)...")
    request_id = f"req_{uuid.uuid4().hex}"
    operation_id = f"op_{uuid.uuid4().hex}"
    payload = {
        "phase": "planner_next",
        "goal": "Click the login button",
        "image": {"base64": TINY_PNG_B64, "format": "png"},
        "request_id": request_id,
        "operation_id": operation_id,
        "provider": "openai",
        "model": "gpt-4o-mini"
    }
    r = requests.post(f"{BASE_URL}/v1/autostep", json=payload)
    print(f"Status: {r.status_code}, Body: {r.json()}")
    data = r.json()
    return data["ok"] == True and data["phase"] == "planner_next" and ("tool_call" in data or "done" in data)

def test_planner_report_and_idempotency():
    print("Testing planner_report and idempotency...")
    request_id = f"req_{uuid.uuid4().hex}"
    operation_id = f"op_{uuid.uuid4().hex}"
    payload = {
        "phase": "planner_report",
        "goal": "Click the login button",
        "request_id": request_id,
        "operation_id": operation_id,
        "tool_call": {"action": "click", "params": {"x": 10, "y": 20}},
        "result": {"ok": True}
    }
    
    print("First report...")
    r1 = requests.post(f"{BASE_URL}/v1/autostep", json=payload)
    print(f"Status: {r1.status_code}, Body: {r1.json()}")
    
    print("Second report (idempotency check)...")
    r2 = requests.post(f"{BASE_URL}/v1/autostep", json=payload)
    print(f"Status: {r2.status_code}, Body: {r2.json()}")
    
    d1 = r1.json()
    d2 = r2.json()
    
    success = (d1["ok"] == True and d1["phase"] == "planner_report" and 
               d2["ok"] == True and d2.get("idempotent") == True)
    return success

def test_text_only_fallback():
    print("Testing text-only provider fallback for planner_next...")
    request_id = f"req_{uuid.uuid4().hex}"
    payload = {
        "phase": "planner_next",
        "goal": "Test fallback",
        "image": {"base64": TINY_PNG_B64},
        "request_id": request_id,
        "provider": "deepseek",
        "model": "deepseek-chat"
    }
    r = requests.post(f"{BASE_URL}/v1/autostep", json=payload)
    print(f"Status: {r.status_code}, Body: {r.json()}")
    data = r.json()
    actual_provider = data.get("provider")
    actual_model = data.get("model")
    print(f"Requested: deepseek, Actual: {actual_provider}/{actual_model}")
    return data["ok"] == True and actual_provider != "deepseek"

def test_openai_style_content():
    print("Testing OpenAI-style content compatibility...")
    request_id = f"req_{uuid.uuid4().hex}"
    payload = {
        "phase": "planner_next",
        "goal": "Test OpenAI style",
        "content": [
            {"type": "text", "text": "What is in this image?"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{TINY_PNG_B64}"}}
        ],
        "request_id": request_id
    }
    r = requests.post(f"{BASE_URL}/v1/autostep", json=payload)
    print(f"Status: {r.status_code}, Body: {r.json()}")
    return r.json()["ok"] == True

if __name__ == "__main__":
    results = []
    if test_health():
        results.append(("Invalid Phase", test_invalid_phase()))
        results.append(("Missing Image", test_planner_next_missing_image()))
        results.append(("Planner Next Success", test_planner_next_success()))
        results.append(("Idempotency", test_planner_report_and_idempotency()))
        results.append(("Text-only Fallback", test_text_only_fallback()))
        results.append(("OpenAI Style Content", test_openai_style_content()))
    else:
        print("Server is not running or unreachable.")
    
    print("\n--- Summary ---")
    for name, success in results:
        print(f"{'[PASS]' if success else '[FAIL]'} {name}")
