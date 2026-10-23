#!/usr/bin/env python3
"""
End-to-end tests for YOLO+LLM v1 API using s1.png, s2.png, s3.png.
Implements T1–T10 from the provided test matrix.

Usage:
  python tools/run_e2e_v1_tests.py [API_BASE]

Defaults to http://127.0.0.1:8000 if not specified.
"""

import base64
import json
import sys
import time
from typing import Any, Dict, Optional

import requests


API_BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"


def b64_of(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def post_json(path: str, payload: Dict[str, Any], timeout: int = 45) -> Dict[str, Any]:
    url = f"{API_BASE}{path}"
    resp = requests.post(url, json=payload, timeout=timeout)
    return {"status": resp.status_code, "body": safe_json(resp)}


def safe_json(resp) -> Dict[str, Any]:
    try:
        return resp.json()
    except Exception:
        return {"ok": False, "error": {"code": "INVALID_JSON", "raw": resp.text[:500]}}


def assert_ok(res: Dict[str, Any], label: str) -> Optional[Dict[str, Any]]:
    status = res.get("status")
    body = res.get("body", {})
    if status != 200:
        print(f"❌ {label}: HTTP {status} -> {body}")
        return None
    if not body.get("ok", False):
        print(f"❌ {label}: ok=false -> {body}")
        return None
    return body.get("data")


def run():
    print("🚀 Running E2E v1 API tests (T1–T10)")
    print(f"API_BASE = {API_BASE}")

    # Pre-flight health/stats
    health = requests.get(f"{API_BASE}/v1/health", timeout=10)
    print(f"/v1/health -> {health.status_code}")
    stats = requests.get(f"{API_BASE}/v1/stats", timeout=10)
    print(f"/v1/stats   -> {stats.status_code}")

    s1 = b64_of("s1.png")
    s2 = b64_of("s2.png")
    s3 = b64_of("s3.png")

    passed = 0
    total = 10
    anchor_from_t1: Optional[Dict[str, Any]] = None

    # T1: 微信主界面：点击搜索（无 intent，无 hints）
    print("\nT1: /v1/pick on S1 (wechat, minimal context)")
    t1_req = {
        "image": {"base64": s1, "format": "png"},
        "capture": {"mode": "full", "screen_size": [2888, 1572], "dpr": 1.0},
        "context": {"goal": "点击搜索按钮"},
        "options": {"max_candidates": 24, "yolo": {"conf": 0.3, "iou": 0.45}, "return_overlay": True},
        "idempotency_key": "t1-wechat-click-search",
    }
    t1_res = post_json("/v1/pick", t1_req)
    t1_data = assert_ok(t1_res, "T1 pick")
    if t1_data:
        dec = t1_data.get("decision", {})
        if dec.get("action") in ("click", "none"):
            # Accept click as pass; action none is edge if no candidates, still record
            print(f"  action={dec.get('action')} conf={dec.get('confidence')} reason={dec.get('reason','')[:80]}")
            anchor_from_t1 = t1_data.get("anchor_proposal")
            passed += 1
        else:
            print("❌ T1: invalid decision")

    # T2: 浏览器页：点击搜索（提供 hints）
    print("\nT2: /v1/pick on S2 (browser, hints)")
    t2_req = {
        "image": {"base64": s2, "format": "png"},
        "capture": {"mode": "full", "screen_size": [2560, 1440], "dpr": 1.0},
        "context": {
            "goal": "点击页面上的搜索",
            "intent": "click",
            "vars": {"site": "xiaohongshu"},
            "dom_hints": {"text": ["搜索", "Search", "submit", "magnifier"]},
        },
        "options": {"max_candidates": 48, "return_overlay": True},
        "idempotency_key": "t2-xhs-click-search",
    }
    t2_res = post_json("/v1/pick", t2_req)
    t2_data = assert_ok(t2_res, "T2 pick")
    t2_plan = None
    if t2_data:
        dec = t2_data.get("decision", {})
        tele = t2_data.get("telemetry", {}).get("stage_lat_ms", {})
        print(f"  action={dec.get('action')} bbox={dec.get('bbox_in_capture')} stages={list(tele.keys())}")
        t2_plan = t2_data.get("verification_plan")
        passed += 1

    # T3: 登录页：点“登录/Sign in”按钮（intent=click，中文 goal）
    print("\nT3: /v1/pick on S3 (login, button)")
    t3_req = {
        "image": {"base64": s3, "format": "png"},
        "capture": {"mode": "full", "screen_size": [1920, 1080], "dpr": 1.25},
        "context": {
            "goal": "点击登录按钮",
            "intent": "click",
            "vars": {"site": "login_page"},
            "dom_hints": {"text": ["登录", "Sign in", "submit"]},
        },
        "options": {"max_candidates": 32},
        "idempotency_key": "t3-login-click-button",
    }
    t3_res = post_json("/v1/pick", t3_req)
    t3_data = assert_ok(t3_res, "T3 pick")
    if t3_data:
        mh = t3_data.get("mapping_hint", {})
        print(f"  expects_dpr={mh.get('expects_dpr')} action={t3_data.get('decision',{}).get('action')}")
        passed += 1

    # T4: 同一页面：点“用户名输入框”（intent=输入）
    print("\nT4: /v1/pick on S3 (login, input field)")
    t4_req = {
        "image": {"base64": s3, "format": "png"},
        "capture": {"mode": "full", "screen_size": [1920, 1080], "dpr": 1.25},
        "context": {"goal": "点击用户名输入框", "intent": "输入", "vars": {"site": "login_page"}},
        "options": {"max_candidates": 32},
        "idempotency_key": "t4-login-click-username",
    }
    t4_res = post_json("/v1/pick", t4_req)
    t4_data = assert_ok(t4_res, "T4 pick")
    if t4_data:
        print(f"  action={t4_data.get('decision',{}).get('action')} reason={t4_data.get('decision',{}).get('reason','')[:80]}")
        passed += 1

    # T5: 锚点复用（以 T1 的 anchor_proposal 为例）
    print("\nT5: /v1/pick anchor reuse on S1")
    anchors_known = []
    if anchor_from_t1:
        # Minimal anchor fields for resolve path
        anchors_known = [{
            "id": anchor_from_t1.get("id", "wx_search_btn_v1"),
            "fingerprint": "sha1:dummy",
            "norm_ref": anchor_from_t1.get("norm_ref", {"kind": "screen", "w": 2888, "h": 1572}),
            "norm_bbox": anchor_from_t1.get("norm_bbox", [0.5, 0.5, 0.6, 0.6]),
            "version": 1,
            "descriptors": anchor_from_t1.get("descriptors", {}),
        }]
    t5_req = {
        "image": {"base64": s1, "format": "png"},
        "capture": {"mode": "full", "screen_size": [2888, 1572], "dpr": 1.0},
        "context": {"goal": "点击搜索按钮"},
        "anchors_known": anchors_known,
        "options": {"max_candidates": 24},
        "idempotency_key": "t5-anchor-reuse",
    }
    t5_res = post_json("/v1/pick", t5_req)
    t5_data = assert_ok(t5_res, "T5 pick (anchor)")
    if t5_data:
        print(f"  cache_hit={t5_data.get('telemetry',{}).get('cache_hit')} reason={t5_data.get('decision',{}).get('reason')}")
        passed += 1

    # T6: 窗口/区域截图 + DPR 校正（模拟 window capture on S1）
    print("\nT6: /v1/pick active_window on S1")
    t6_req = {
        "image": {"base64": s1, "format": "png"},
        "capture": {
            "mode": "active_window",
            "screen_size": [3840, 2160],
            "window_offset": [240, 120],
            "window_size": [1600, 900],
            "dpr": 2.0,
        },
        "context": {"goal": "点击搜索按钮"},
        "options": {"max_candidates": 32},
        "idempotency_key": "t6-window-capture",
    }
    t6_res = post_json("/v1/pick", t6_req)
    t6_data = assert_ok(t6_res, "T6 pick")
    if t6_data:
        mh = t6_data.get("mapping_hint", {})
        print(f"  apply_window_offset={mh.get('apply_window_offset')} expects_dpr={mh.get('expects_dpr')}")
        passed += 1

    # T7: /v1/verify（使用 S2 作为点击后截图，计划来自 T2）
    print("\nT7: /v1/verify using S2 and T2 verification_plan")
    verification_plan = t2_plan or {"expect_text_any": ["搜索", "Search"]}
    t7_req = {
        "image": {"base64": s2, "format": "png"},
        "capture": {"mode": "full", "screen_size": [2560, 1440], "dpr": 1.0},
        "context": {"goal": "点击页面上的搜索", "vars": {"site": "xiaohongshu"}},
        "expected": verification_plan,
        "clicked": {"point_in_capture": [100, 100], "bbox_in_capture": [90, 90, 110, 110], "candidate_id": "cand-xx"},
    }
    t7_res = post_json("/v1/verify", t7_req)
    t7_data = assert_ok(t7_res, "T7 verify")
    if t7_data:
        print(f"  pass={t7_data.get('pass')} reason={t7_data.get('reason','')[:80]}")
        passed += 1

    # T8: 候选噪声压力（max_candidates up）
    print("\nT8: /v1/pick noisy candidates on S2")
    t8_req = {
        "image": {"base64": s2, "format": "png"},
        "capture": {"mode": "full", "screen_size": [2560, 1440], "dpr": 1.0},
        "context": {"goal": "点击搜索", "intent": "click"},
        "options": {"max_candidates": 96, "yolo": {"conf": 0.25, "iou": 0.50}},
        "idempotency_key": "t8-noisy-candidates",
    }
    t8_res = post_json("/v1/pick", t8_req)
    t8_data = assert_ok(t8_res, "T8 pick")
    if t8_data:
        print(f"  action={t8_data.get('decision',{}).get('action')} reason={t8_data.get('decision',{}).get('reason','')[:80]}")
        passed += 1

    # T9: 无候选（黑屏）
    print("\nT9: /v1/pick on blank image (no candidates)")
    # Generate minimal black image base64 (1x1 PNG)
    from PIL import Image
    import io
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (0, 0, 0)).save(buf, format="PNG")
    blank_b64 = base64.b64encode(buf.getvalue()).decode()
    t9_req = {
        "image": {"base64": blank_b64, "format": "png"},
        "capture": {"mode": "full", "screen_size": [2560, 1440], "dpr": 1.0},
        "context": {"goal": "点击搜索按钮"},
        "options": {"max_candidates": 16},
        "idempotency_key": "t9-no-candidates",
    }
    t9_res = post_json("/v1/pick", t9_req)
    t9_data = assert_ok(t9_res, "T9 pick")
    if t9_data:
        print(f"  action={t9_data.get('decision',{}).get('action')} reason={t9_data.get('decision',{}).get('reason')}")
        passed += 1

    # T10: 幂等缓存（重放 T2）
    print("\nT10: /v1/pick idempotency replay (T2 body)")
    t10_res = post_json("/v1/pick", t2_req)
    t10_data = assert_ok(t10_res, "T10 pick")
    if t10_data:
        print(f"  cache_hit={t10_data.get('telemetry',{}).get('cache_hit')} req_id={t10_data.get('telemetry',{}).get('req_id')}")
        passed += 1

    print("\n======== Summary ========")
    print(f"Passed: {passed}/{total}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(run())

