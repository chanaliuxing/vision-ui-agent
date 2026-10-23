#!/usr/bin/env python3
"""
Minimal MVP runner: detects and (optionally) clicks `post_plus_button` using the local YOLO API.

Usage:
  python run_post.py --dry-run
  python run_post.py --run
  python run_post.py --endpoint http://127.0.0.1:8000
  python run_post.py --dry-run --from-file codex.png
"""

import argparse
import json
import os
import time
from typing import List

import cv2
import numpy as np
from PIL import Image

import os
from core.capture import ScreenCapture
from core.executor import Executor
from core.locator import bbox_center, select_best
from core.reporter import Reporter, StepLog
from core.yolo_client import YoloClient
from core.mapping import CaptureMeta, PreprocMeta, map_id_to_screen_point


def ensure_dirs():
    for d in ["out", "out/screens", "out/reports", "out/logs"]:
        os.makedirs(d, exist_ok=True)


def load_classes_conf(path: str) -> dict:
    if not os.path.exists(path):
        return {
            "click_padding_px": -6,
            "conf_min": 0.5,
            "retry": 2,
            "poll_interval_s": 0.6,
            "wait_timeout_s": 8,
        }
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser(description="MVP: detect and click post_plus_button")
    default_endpoint = os.getenv("YOLO_ENDPOINT", "http://127.0.0.1:8000")
    default_source = os.getenv("SOURCE_PATH")
    ap.add_argument("--endpoint", default=default_endpoint, help="YOLO API endpoint root (or set YOLO_ENDPOINT)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Only detect and visualize; no clicks")
    mode.add_argument("--run", action="store_true", help="Execute clicks and minimal waits")
    ap.add_argument("--class", dest="target_cls", default="post_plus_button", help="Target class to click")
    ap.add_argument("--conf", type=float, default=0.5, help="min confidence threshold")
    ap.add_argument("--config", default="config/classes.json", help="config path")
    ap.add_argument("--from-file", dest="from_file", default=default_source, help="Use an image file instead of screenshot (or set SOURCE_PATH)")
    args = ap.parse_args()

    ensure_dirs()
    cfg = load_classes_conf(args.config)
    conf_min = float(args.conf or cfg.get("conf_min", 0.5))
    pad_px = int(cfg.get("click_padding_px", -6))

    reporter = Reporter(out_dir="out")
    cap = ScreenCapture()
    yolo = YoloClient(endpoint=args.endpoint)
    exe = Executor()

    # Step: screenshot + detect
    if args.from_file:
        from PIL import Image as _Image
        if not os.path.exists(args.from_file):
            raise SystemExit(f"--from-file not found: {args.from_file}")
        img0 = _Image.open(args.from_file).convert("RGB")
    else:
        # This requires screen recording permissions
        g0 = cap.screenshot()
        img0 = g0.image

    bgr0 = cv2.cvtColor(np.array(img0.convert("RGB")), cv2.COLOR_RGB2BGR)
    resp = yolo.infer(img0, return_image=False)
    dets = yolo.to_detections(resp)

    # Locate best candidate
    sel = select_best(dets, [args.target_cls], bgr0.shape[1], bgr0.shape[0], conf_min=conf_min)

    boxes = [d.bbox_xyxy for d in sel.candidates]
    labels = [f"{d.class_name} {d.conf:.2f}" for d in sel.candidates]
    chosen_idx = sel.candidates.index(sel.chosen) if sel.chosen in sel.candidates else None

    overlay0 = reporter.draw_detections(bgr0, boxes, labels, chosen_idx)
    before_path = reporter.save_image(bgr0, "step_01_before.png")
    overlay_path = reporter.save_image(overlay0, "step_01_overlay.png")

    clicked = None
    after_path = None
    if sel.chosen is None:
        reporter.log_step(
            StepLog(
                name="home_detect_plus",
                status="fail",
                message=f"no candidate found for {args.target_cls}",
                conf=None,
                before_img=before_path,
                overlay_img=overlay_path,
            )
        )
    else:
        # Robust mapping to screen coords
        cap_w, cap_h = bgr0.shape[1], bgr0.shape[0]
        cap_meta = CaptureMeta(cap_w=cap_w, cap_h=cap_h, dpr=float(getattr(g0, "dpr", 1.0)))
        pre = PreprocMeta(frame_w=cap_w, frame_h=cap_h, imgsz=cap_w, letterbox=False, normalized=False)
        sx, sy = map_id_to_screen_point(sel.chosen.bbox_xyxy, sel.chosen.class_name, pre, cap_meta)
        clicked = [int(sx), int(sy)]
        if args.run and not args.from_file:
            exe.click(sx, sy, dpr=cap_meta.dpr)
            time.sleep(0.8)
        if args.from_file:
            bgr1 = bgr0.copy()
        else:
            g1 = cap.screenshot()
            bgr1 = cv2.cvtColor(np.array(g1.image.convert("RGB")), cv2.COLOR_RGB2BGR)
        after_path = reporter.save_image(bgr1, "step_01_after.png")
        reporter.log_step(
            StepLog(
                name="home_detect_plus",
                status="success",
                message="detected and {}clicked".format("" if (args.run and not args.from_file) else "(dry) "),
                conf=sel.chosen.conf,
                chosen_cls=sel.chosen.class_name,
                before_img=before_path,
                overlay_img=overlay_path,
                after_img=after_path,
                click_xy=clicked,
            )
        )

    reporter.flush_jsonl()
    html_path = reporter.write_html()
    print(f"Report written: {html_path}")


if __name__ == "__main__":
    main()
