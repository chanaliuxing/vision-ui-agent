#!/usr/bin/env python3
"""
HTTP API test runner (Python) for YOLO+LLM service.

Scenarios (choose with --case):
  - pick_s1           : /v1/pick on s1.png (saves anchor to out/anchor_from_pick.json)
  - anchor_reuse_s1   : /v1/pick on s1.png with anchors_known (fast path)
  - idempotency_s1    : /v1/pick twice with same idempotency_key
  - pick_s2_hints     : /v1/pick on s2.png with hints and site vars
  - pick_s3_login     : /v1/pick on s3.png (login button)
  - pick_s3_input     : /v1/pick on s3.png (username input)
  - verify_s2         : /v1/verify using plan from pick(s2)

Usage examples:
  python tools/api_tests/run_api_tests.py --api http://192.168.1.113:8000 --case pick_s1
  python tools/api_tests/run_api_tests.py --api http://192.168.1.113:8000 --case anchor_reuse_s1
  python tools/api_tests/run_api_tests.py --api http://192.168.1.113:8000 --case idempotency_s1
  python tools/api_tests/run_api_tests.py --api http://192.168.1.113:8000 --case pick_s2_hints
  python tools/api_tests/run_api_tests.py --api http://192.168.1.113:8000 --case verify_s2
"""

import argparse
import base64
import json
import os
import sys
import time
from typing import Any, Dict, Optional, Tuple
import hashlib

import requests
from PIL import Image


def b64_of(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def size_of(path: str) -> Tuple[int, int]:
    with Image.open(path) as im:
        return im.size


def api_post_json(api: str, path: str, payload: Dict[str, Any], timeout: int = 60) -> Dict[str, Any]:
    url = f"{api.rstrip('/')}{path}"
    resp = requests.post(url, json=payload, timeout=timeout)
    try:
        body = resp.json()
    except Exception:
        body = {"ok": False, "error": {"code": "INVALID_JSON", "raw": resp.text[:500]}}
    return {"status": resp.status_code, "body": body}


def print_pick_summary(data: Dict[str, Any]) -> None:
    decision = data.get("decision", {})
    mapping = data.get("mapping_hint", {})
    telemetry = data.get("telemetry", {})
    print("Decision:")
    print(f"  action={decision.get('action')} point={decision.get('point_in_capture')} bbox={decision.get('bbox_in_capture')}")
    print(f"  conf={decision.get('confidence')} reason={(decision.get('reason') or '')[:160]}")
    print("Mapping:")
    print(f"  apply_window_offset={mapping.get('apply_window_offset')} expects_dpr={mapping.get('expects_dpr')}")
    print("Telemetry:")
    print(f"  req_id={telemetry.get('req_id')} stages={telemetry.get('stage_lat_ms')} cache_hit={telemetry.get('cache_hit')}")


def save_anchor_if_any(data: Dict[str, Any], path: str = "out/anchor_from_pick.json") -> None:
    anchor = data.get("anchor_proposal")
    if not anchor:
        return
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(anchor, f, ensure_ascii=False, indent=2)
    print(f"Saved anchor -> {path}")


def case_pick_s1(api: str, image: str = "s1.png") -> int:
    if not os.path.exists(image):
        print(f"Image not found: {image}")
        return 2
    w, h = size_of(image)
    payload = {
        "image": {"base64": b64_of(image), "format": "png"},
        "capture": {"mode": "full", "screen_size": [w, h], "dpr": 1.0},
        "context": {"goal": "点击搜索按钮"},
        "options": {"max_candidates": 32, "yolo": {"conf": 0.35, "iou": 0.45}},
        "idempotency_key": f"pick-{int(time.time()*1000)}",
    }
    res = api_post_json(api, "/v1/pick", payload)
    print(f"HTTP {res['status']}")
    if res["status"] != 200 or not res["body"].get("ok", False):
        print(json.dumps(res["body"], ensure_ascii=False, indent=2)[:800])
        return 1
    data = res["body"]["data"]
    print_pick_summary(data)
    save_anchor_if_any(data)
    return 0


def case_anchor_reuse_s1(api: str, image: str = "s1.png", anchor_path: str = "out/anchor_from_pick.json") -> int:
    if not os.path.exists(image):
        print(f"Image not found: {image}")
        return 2
    if not os.path.exists(anchor_path):
        print(f"Anchor file not found: {anchor_path}")
        return 2
    with open(anchor_path, "r", encoding="utf-8") as f:
        anchor = json.load(f)

    # Ensure required fields for AnchorSpec
    if not anchor.get("fingerprint"):
        tpl_hex = (
            (anchor.get("descriptors") or {}).get("template_png")
            or ""
        )
        fp_src = bytes.fromhex(tpl_hex) if tpl_hex else anchor.get("id", "anchor") .encode("utf-8")
        fp = hashlib.sha1(fp_src).hexdigest()[:16]
        anchor["fingerprint"] = f"sha1:{fp}"
    w = int(anchor.get("norm_ref", {}).get("w", size_of(image)[0]))
    h = int(anchor.get("norm_ref", {}).get("h", size_of(image)[1]))
    payload = {
        "image": {"base64": b64_of(image), "format": "png"},
        "capture": {"mode": "full", "screen_size": [w, h], "dpr": 1.0},
        "context": {"goal": "点击搜索按钮"},
        "anchors_known": [anchor],
        "options": {"max_candidates": 24},
        "idempotency_key": f"t5-anchor-{int(time.time()*1000)}",
    }
    res = api_post_json(api, "/v1/pick", payload)
    print(f"HTTP {res['status']}")
    if res["status"] != 200 or not res["body"].get("ok", False):
        print(json.dumps(res["body"], ensure_ascii=False, indent=2)[:800])
        return 1
    data = res["body"]["data"]
    print(json.dumps({"decision": data.get("decision"), "telemetry": data.get("telemetry")}, ensure_ascii=False, indent=2))
    return 0


def case_idempotency_s1(api: str, image: str = "s1.png") -> int:
    if not os.path.exists(image):
        print(f"Image not found: {image}")
        return 2
    w, h = size_of(image)
    idem = f"idem-{int(time.time()*1000)}"
    payload = {
        "image": {"base64": b64_of(image), "format": "png"},
        "capture": {"mode": "full", "screen_size": [w, h], "dpr": 1.0},
        "context": {"goal": "点击搜索按钮"},
        "options": {"max_candidates": 32, "yolo": {"conf": 0.35, "iou": 0.45}},
        "idempotency_key": idem,
    }
    r1 = api_post_json(api, "/v1/pick", payload)
    r2 = api_post_json(api, "/v1/pick", payload)
    print(f"First:  HTTP {r1['status']}")
    print(f"Second: HTTP {r2['status']}")
    if r2["status"] == 200 and r2["body"].get("ok", False):
        cache_hit = r2["body"]["data"].get("telemetry", {}).get("cache_hit")
        print(f"Second response cache_hit={cache_hit}")
        return 0
    print(json.dumps(r2["body"], ensure_ascii=False, indent=2)[:800])
    return 1


def case_pick_s2_hints(api: str, image: str = "s2.png") -> int:
    if not os.path.exists(image):
        print(f"Image not found: {image}")
        return 2
    w, h = size_of(image)
    payload = {
        "image": {"base64": b64_of(image), "format": "png"},
        "capture": {"mode": "full", "screen_size": [w, h], "dpr": 1.0},
        "context": {
            "goal": "点击页面上的搜索",
            "intent": "click",
            "vars": {"site": "xiaohongshu"},
            "dom_hints": {"text": ["搜索", "Search", "submit", "magnifier"]},
        },
        "options": {"max_candidates": 48},
        "idempotency_key": f"t2-{int(time.time()*1000)}",
    }
    res = api_post_json(api, "/v1/pick", payload)
    print(f"HTTP {res['status']}")
    if res["status"] != 200 or not res["body"].get("ok", False):
        print(json.dumps(res["body"], ensure_ascii=False, indent=2)[:800])
        return 1
    data = res["body"]["data"]
    print_pick_summary(data)
    return 0


def case_pick_s3_login(api: str, image: str = "s3.png") -> int:
    if not os.path.exists(image):
        print(f"Image not found: {image}")
        return 2
    w, h = size_of(image)
    payload = {
        "image": {"base64": b64_of(image), "format": "png"},
        "capture": {"mode": "full", "screen_size": [w, h], "dpr": 1.0},
        "context": {"goal": "点击登录按钮", "intent": "click", "vars": {"site": "login_page"}},
        "options": {"max_candidates": 32},
        "idempotency_key": f"t3-{int(time.time()*1000)}",
    }
    res = api_post_json(api, "/v1/pick", payload)
    print(f"HTTP {res['status']}")
    if res["status"] != 200 or not res["body"].get("ok", False):
        print(json.dumps(res["body"], ensure_ascii=False, indent=2)[:800])
        return 1
    data = res["body"]["data"]
    print_pick_summary(data)
    return 0


def case_pick_s3_input(api: str, image: str = "s3.png") -> int:
    if not os.path.exists(image):
        print(f"Image not found: {image}")
        return 2
    w, h = size_of(image)
    payload = {
        "image": {"base64": b64_of(image), "format": "png"},
        "capture": {"mode": "full", "screen_size": [w, h], "dpr": 1.0},
        "context": {"goal": "点击用户名输入框", "intent": "输入", "vars": {"site": "login_page"}},
        "options": {"max_candidates": 32},
        "idempotency_key": f"t4-{int(time.time()*1000)}",
    }
    res = api_post_json(api, "/v1/pick", payload)
    print(f"HTTP {res['status']}")
    if res["status"] != 200 or not res["body"].get("ok", False):
        print(json.dumps(res["body"], ensure_ascii=False, indent=2)[:800])
        return 1
    data = res["body"]["data"]
    print_pick_summary(data)
    return 0


def case_verify_s2(api: str, image: str = "s2.png") -> int:
    if not os.path.exists(image):
        print(f"Image not found: {image}")
        return 2
    # First pick to get plan
    w, h = size_of(image)
    pick_payload = {
        "image": {"base64": b64_of(image), "format": "png"},
        "capture": {"mode": "full", "screen_size": [w, h], "dpr": 1.0},
        "context": {"goal": "点击页面上的搜索", "vars": {"site": "xiaohongshu"}},
        "options": {"max_candidates": 48},
        "idempotency_key": "t7-pick",
    }
    pr = api_post_json(api, "/v1/pick", pick_payload)
    if pr["status"] != 200 or not pr["body"].get("ok", False):
        print("Pick failed before verify:")
        print(json.dumps(pr["body"], ensure_ascii=False, indent=2)[:800])
        return 1
    plan = pr["body"]["data"].get("verification_plan")
    if not plan:
        print("No verification_plan from pick; aborting")
        return 1
    # Now verify using same image (simulated post-click)
    verify_payload = {
        "image": {"base64": b64_of(image), "format": "png"},
        "capture": {"mode": "full", "screen_size": [w, h], "dpr": 1.0},
        "context": {"goal": "点击页面上的搜索", "vars": {"site": "xiaohongshu"}},
        "expected": plan,
        "clicked": {"point_in_capture": [100, 100], "bbox_in_capture": [90, 90, 110, 110], "candidate_id": "cand-xx"},
    }
    vr = api_post_json(api, "/v1/verify", verify_payload, timeout=30)
    print(f"HTTP {vr['status']}")
    print(json.dumps(vr["body"], ensure_ascii=False, indent=2)[:800])
    return 0 if vr["status"] == 200 else 1


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="YOLO+LLM API tests (HTTP)")
    p.add_argument("--api", default="http://192.168.1.113:8000", help="API base URL")
    p.add_argument("--case", default="pick_s1", choices=[
        "pick_s1", "anchor_reuse_s1", "idempotency_s1",
        "pick_s2_hints", "pick_s3_login", "pick_s3_input", "verify_s2",
    ], help="Test scenario to run")
    p.add_argument("--image", default=None, help="Image path override (optional)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    api = args.api
    img = args.image
    case = args.case

    if case == "pick_s1":
        return case_pick_s1(api, img or "s1.png")
    if case == "anchor_reuse_s1":
        return case_anchor_reuse_s1(api, img or "s1.png")
    if case == "idempotency_s1":
        return case_idempotency_s1(api, img or "s1.png")
    if case == "pick_s2_hints":
        return case_pick_s2_hints(api, img or "s2.png")
    if case == "pick_s3_login":
        return case_pick_s3_login(api, img or "s3.png")
    if case == "pick_s3_input":
        return case_pick_s3_input(api, img or "s3.png")
    if case == "verify_s2":
        return case_verify_s2(api, img or "s2.png")
    print(f"Unknown case: {case}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
