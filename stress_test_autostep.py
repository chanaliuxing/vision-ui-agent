import base64
import requests
import uuid
import time
import concurrent.futures

BASE_URL = "http://localhost:8000"
TINY_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="

def run_single_request(i):
    request_id = f"stress_{i}_{uuid.uuid4().hex[:8]}"
    payload = {
        "phase": "planner_next",
        "goal": "Stress test",
        "image": {"base64": TINY_PNG_B64},
        "request_id": request_id,
        "provider": "openai",
        "model": "gpt-4o-mini"
    }
    try:
        t0 = time.time()
        # Use a real vision model
        r = requests.post(f"{BASE_URL}/v1/autostep", json=payload, timeout=30)
        return r.status_code == 200, time.time() - t0
    except Exception as e:
        return False, str(e)

if __name__ == "__main__":
    print("Running stress test (50 requests)...")
    success_count = 0
    latencies = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(run_single_request, i) for i in range(50)]
        for i, future in enumerate(concurrent.futures.as_completed(futures)):
            ok, val = future.result()
            if ok:
                success_count += 1
                latencies.append(val)
            else:
                print(f"Request {i} failed: {val}")

    print("--- Results ---")
    print(f"Success: {success_count}/50")
    if latencies:
        print(f"Avg Latency: {sum(latencies)/len(latencies):.2f}s")
        print(f"Max Latency: {max(latencies):.2f}s")
        print(f"Min Latency: {min(latencies):.2f}s")
