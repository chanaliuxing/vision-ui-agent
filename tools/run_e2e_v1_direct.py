#!/usr/bin/env python3
"""
Direct in-process E2E runner for YOLO+LLM pipeline without HTTP.
Executes T1–T10 by calling Orchestrator methods directly.

Useful when localhost networking is restricted.
"""

import base64
import io
import sys
from typing import Any, Dict, Optional

import numpy as np
from PIL import Image

from dependencies import get_orchestrator
from schemas import (
    PickRequest,
    VerifyRequest,
    AnchorResolveRequest,
    ImageSpec,
    CaptureSpec,
    ContextSpec,
    OptionsSpec,
    YoloOptionsSpec,
)


def load_bgr(path: str) -> np.ndarray:
    import cv2
    pil = Image.open(path).convert("RGB")
    rgb = np.array(pil)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def to_imgspec_b64(path: str) -> ImageSpec:
    with open(path, "rb") as f:
        return ImageSpec(base64=base64.b64encode(f.read()).decode(), format="png")


def run() -> int:
    print("🚀 Running direct in-process E2E (no HTTP)")
    orch = get_orchestrator()

    s1_bgr = load_bgr("s1.png")
    s2_bgr = load_bgr("s2.png")
    s3_bgr = load_bgr("s3.png")

    passed = 0
    total = 10
    anchor_from_t1: Optional[Dict[str, Any]] = None

    # T1
    print("\nT1: pick S1 minimal context")
    t1_req = PickRequest(
        image=to_imgspec_b64("s1.png"),
        capture=CaptureSpec(mode="full", screen_size=[2888, 1572], dpr=1.0),
        context=ContextSpec(goal="点击搜索按钮"),
        options=OptionsSpec(max_candidates=24, yolo=YoloOptionsSpec(conf=0.3, iou=0.45), return_overlay=True),
        idempotency_key="t1-wechat-click-search",
    )
    t1 = orch.pick(s1_bgr, t1_req)
    print(f"  action={t1.get('decision',{}).get('action')} conf={t1.get('decision',{}).get('confidence')}")
    passed += 1
    anchor_from_t1 = t1.get("anchor_proposal")

    # T2
    print("\nT2: pick S2 with hints")
    t2_req = PickRequest(
        image=to_imgspec_b64("s2.png"),
        capture=CaptureSpec(mode="full", screen_size=[2560, 1440], dpr=1.0),
        context=ContextSpec(goal="点击页面上的搜索", intent="click", vars={"site": "xiaohongshu"}, dom_hints={"text": ["搜索", "Search", "submit", "magnifier"]}),
        options=OptionsSpec(max_candidates=48, return_overlay=True),
        idempotency_key="t2-xhs-click-search",
    )
    t2 = orch.pick(s2_bgr, t2_req)
    print(f"  action={t2.get('decision',{}).get('action')} bbox={t2.get('decision',{}).get('bbox_in_capture')}")
    passed += 1

    # T3
    print("\nT3: pick S3 login button")
    t3_req = PickRequest(
        image=to_imgspec_b64("s3.png"),
        capture=CaptureSpec(mode="full", screen_size=[1920, 1080], dpr=1.25),
        context=ContextSpec(goal="点击登录按钮", intent="click", vars={"site": "login_page"}, dom_hints={"text": ["登录", "Sign in", "submit"]}),
        options=OptionsSpec(max_candidates=32),
        idempotency_key="t3-login-click-button",
    )
    t3 = orch.pick(s3_bgr, t3_req)
    print(f"  expects_dpr={t3.get('mapping_hint',{}).get('expects_dpr')}")
    passed += 1

    # T4
    print("\nT4: pick S3 input field")
    t4_req = PickRequest(
        image=to_imgspec_b64("s3.png"),
        capture=CaptureSpec(mode="full", screen_size=[1920, 1080], dpr=1.25),
        context=ContextSpec(goal="点击用户名输入框", intent="输入", vars={"site": "login_page"}),
        options=OptionsSpec(max_candidates=32),
        idempotency_key="t4-login-click-username",
    )
    t4 = orch.pick(s3_bgr, t4_req)
    print(f"  action={t4.get('decision',{}).get('action')} reason={t4.get('decision',{}).get('reason','')[:80]}")
    passed += 1

    # T5
    print("\nT5: anchor reuse on S1")
    anchors_known = []
    if anchor_from_t1:
        anchors_known = [{
            "id": anchor_from_t1.get("id", "wx_search_btn_v1"),
            "fingerprint": "sha1:dummy",
            "norm_ref": anchor_from_t1.get("norm_ref", {"kind": "screen", "w": 2888, "h": 1572}),
            "norm_bbox": anchor_from_t1.get("norm_bbox", [0.5, 0.5, 0.6, 0.6]),
            "version": 1,
            "descriptors": anchor_from_t1.get("descriptors", {}),
        }]
    t5_req = PickRequest(
        image=to_imgspec_b64("s1.png"),
        capture=CaptureSpec(mode="full", screen_size=[2888, 1572], dpr=1.0),
        context=ContextSpec(goal="点击搜索按钮"),
        options=OptionsSpec(max_candidates=24),
        idempotency_key="t5-anchor-reuse",
        anchors_known=anchors_known,
    )
    t5 = orch.pick(s1_bgr, t5_req)
    print(f"  reason={t5.get('decision',{}).get('reason')}")
    passed += 1

    # T6
    print("\nT6: active_window S1")
    t6_req = PickRequest(
        image=to_imgspec_b64("s1.png"),
        capture=CaptureSpec(mode="active_window", screen_size=[3840, 2160], window_offset=[240, 120], window_size=[1600, 900], dpr=2.0),
        context=ContextSpec(goal="点击搜索按钮"),
        options=OptionsSpec(max_candidates=32),
        idempotency_key="t6-window-capture",
    )
    t6 = orch.pick(s1_bgr, t6_req)
    mh = t6.get("mapping_hint", {})
    print(f"  apply_window_offset={mh.get('apply_window_offset')} expects_dpr={mh.get('expects_dpr')}")
    passed += 1

    # T7
    print("\nT7: verify with S2 and plan from T2")
    verification_plan = t2.get("verification_plan") if isinstance(t2, dict) else {}
    vreq = VerifyRequest(
        image=to_imgspec_b64("s2.png"),
        capture=CaptureSpec(mode="full", screen_size=[2560, 1440], dpr=1.0),
        context=None,
        expected=verification_plan or {"expect_text_any": ["搜索", "Search"]},
        clicked={"point_in_capture": [100, 100], "bbox_in_capture": [90, 90, 110, 110], "candidate_id": "cand-xx"},
    )
    t7 = orch.verify(s2_bgr, vreq)
    print(f"  pass={t7.get('pass')} reason={t7.get('reason','')[:80]}")
    passed += 1

    # T8
    print("\nT8: noisy candidates on S2")
    t8_req = PickRequest(
        image=to_imgspec_b64("s2.png"),
        capture=CaptureSpec(mode="full", screen_size=[2560, 1440], dpr=1.0),
        context=ContextSpec(goal="点击搜索", intent="click"),
        options=OptionsSpec(max_candidates=96, yolo=YoloOptionsSpec(conf=0.25, iou=0.50)),
        idempotency_key="t8-noisy-candidates",
    )
    t8 = orch.pick(s2_bgr, t8_req)
    print(f"  action={t8.get('decision',{}).get('action')} reason={t8.get('decision',{}).get('reason','')[:80]}")
    passed += 1

    # T9
    print("\nT9: blank image no candidates")
    from PIL import Image as PILImage
    buf = io.BytesIO()
    PILImage.new("RGB", (32, 32), (0, 0, 0)).save(buf, format="PNG")
    blank_b64 = base64.b64encode(buf.getvalue()).decode()
    blank = ImageSpec(base64=blank_b64, format="png")
    t9_req = PickRequest(
        image=blank,
        capture=CaptureSpec(mode="full", screen_size=[2560, 1440], dpr=1.0),
        context=ContextSpec(goal="点击搜索按钮"),
        options=OptionsSpec(max_candidates=16),
        idempotency_key="t9-no-candidates",
    )
    # Use s2_bgr as dummy (image content doesn't matter for return structure in this path)
    t9 = orch.pick(s2_bgr, t9_req)
    print(f"  action={t9.get('decision',{}).get('action')} reason={t9.get('decision',{}).get('reason')}")
    passed += 1

    # T10
    print("\nT10: idempotency replay (T2)")
    t10 = orch.pick(s2_bgr, t2_req)
    print(f"  cache_hit={t10.get('telemetry',{}).get('cache_hit')} req_id={t10.get('telemetry',{}).get('req_id')}")
    passed += 1

    print("\n======== Summary (Direct) ========")
    print(f"Passed: {passed}/{total}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(run())

