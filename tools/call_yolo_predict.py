#!/usr/bin/env python3
"""
Small script to call YOLO /predict or LLM decision /v1/pick using s1.png (or a specified image).

Usage examples:
  # YOLO-only (multipart)
  python tools/call_yolo_predict.py --api http://127.0.0.1:8000 --image s1.png

  # YOLO+LLM decision (/v1/pick JSON)
  python tools/call_yolo_predict.py --llm --goal "点击搜索按钮" --image s1.png

Defaults:
  --api    http://127.0.0.1:8000
  --image  s1.png
"""

import argparse
import base64
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

from PIL import Image
import requests


def call_predict(api: str, image_path: str, conf: float, iou: float, imgsz: int) -> int:
    url = f"{api.rstrip('/')}/predict?return_image=true&conf={conf}&iou={iou}&imgsz={imgsz}"
    if not os.path.exists(image_path):
        print(f"Image not found: {image_path}")
        return 2
    with open(image_path, "rb") as f:
        files = {"image": (os.path.basename(image_path), f, "image/png")}
        print(f"POST {url}")
        resp = requests.post(url, files=files, timeout=60)
    if resp.status_code != 200:
        print(f"HTTP {resp.status_code}: {resp.text[:500]}")
        return 1
    data: Dict[str, Any] = resp.json()
    dets = data.get("detections", [])
    print(f"Detections: {len(dets)}")
    for i, d in enumerate(dets[:5]):
        print(f"  #{i+1}: label={d.get('label')} conf={d.get('conf')} bbox={d.get('bbox')}")
    overlay_b64 = data.get("image_base64")
    if overlay_b64:
        if overlay_b64.startswith("data:image"):
            overlay_b64 = overlay_b64.split(",", 1)[1]
        out_dir = "out"
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, "overlay_predict.png")
        with open(out_path, "wb") as f:
            f.write(base64.b64decode(overlay_b64))
        print(f"Saved overlay: {out_path}")
    return 0


def call_pick(api: str,
              image_path: str,
              goal: str,
              intent: Optional[str],
              site: Optional[str],
              hints_text: Optional[List[str]],
              mode: str,
              dpr: float,
              max_candidates: int,
              yolo_conf: float,
              yolo_iou: float,
              provider: Optional[str],
              idem: Optional[str]) -> int:
    # Prepare image base64 and capture size
    if not os.path.exists(image_path):
        print(f"Image not found: {image_path}")
        return 2
    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()
    with Image.open(image_path) as im:
        w, h = im.size
    payload: Dict[str, Any] = {
        "image": {"base64": img_b64, "format": "png"},
        "capture": {"mode": "full", "screen_size": [w, h], "dpr": dpr},
        "context": {"goal": goal},
        "options": {"mode": mode, "max_candidates": max_candidates, "yolo": {"conf": yolo_conf, "iou": yolo_iou}, "return_overlay": False},
        "idempotency_key": idem or f"pick-{int(time.time()*1000)}",
    }
    if intent:
        payload["context"]["intent"] = intent
    if site:
        payload["context"].setdefault("vars", {})["site"] = site
    if hints_text:
        payload["context"]["dom_hints"] = {"text": hints_text}
    if provider:
        payload["options"]["llm_provider"] = provider

    url = f"{api.rstrip('/')}/v1/pick"
    print(f"POST {url}\n{json.dumps(payload)[:300]}...")
    resp = requests.post(url, json=payload, timeout=90)
    if resp.status_code != 200:
        print(f"HTTP {resp.status_code}: {resp.text[:500]}")
        return 1
    body = resp.json()
    if not body.get("ok", False):
        print(f"ok=false: {json.dumps(body)[:500]}")
        return 1
    data = body.get("data", {})
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
    if mode == "explain_all":
        explain = data.get("explain", {}) or {}
        print("Explain:")
        print(f"  ok={explain.get('ok')} language={explain.get('language')} llm={explain.get('llm')}")
        elements = data.get("elements", []) or []
        print(f"Elements: {len(elements)}")
        for el in elements[:8]:
            print(f"  #{el.get('id')}: {el.get('label')} | {el.get('description')}")
    anchor = data.get("anchor_proposal")
    if anchor:
        out_dir = "out"
        os.makedirs(out_dir, exist_ok=True)
        anchor_path = os.path.join(out_dir, "anchor_from_pick.json")
        with open(anchor_path, "w", encoding="utf-8") as f:
            json.dump(anchor, f, ensure_ascii=False, indent=2)
        print(f"Saved anchor proposal -> {anchor_path}")
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Call YOLO /predict or LLM /v1/pick")
    p.add_argument("--api", default="http://127.0.0.1:8000", help="API base URL")
    p.add_argument("--image", default="s1.png", help="Image path")
    p.add_argument("--llm", action="store_true", help="Use /v1/pick (YOLO+LLM)")
    # /predict params
    p.add_argument("--conf", type=float, default=0.35, help="YOLO conf for /predict")
    p.add_argument("--iou", type=float, default=0.45, help="YOLO iou for /predict")
    p.add_argument("--imgsz", type=int, default=1280, help="YOLO imgsz for /predict")
    # /v1/pick params
    p.add_argument("--goal", default="点击搜索按钮", help="Task goal for /v1/pick")
    p.add_argument("--intent", default=None, help="Intent for /v1/pick (e.g., click/输入)")
    p.add_argument("--site", default=None, help="vars.site for /v1/pick")
    p.add_argument("--hints", default=None, help="Comma-separated text hints (e.g., 搜索,Search)")
    p.add_argument("--mode", default="pick", choices=["pick", "explain_all"], help="Mode for /v1/pick")
    p.add_argument("--dpr", type=float, default=1.0, help="DPR for capture")
    p.add_argument("--max-candidates", type=int, default=32, help="max candidates for /v1/pick")
    p.add_argument("--yolo-conf", type=float, default=0.35, help="YOLO conf for /v1/pick")
    p.add_argument("--yolo-iou", type=float, default=0.45, help="YOLO iou for /v1/pick")
    p.add_argument("--provider", default=None, help="LLM provider (gemini/openai/deepseek/nvidia)")
    p.add_argument("--idem", default=None, help="Custom idempotency key for /v1/pick")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if not args.llm:
        return call_predict(args.api, args.image, args.conf, args.iou, args.imgsz)
    hints_list: Optional[List[str]] = None
    if args.hints:
        hints_list = [s.strip() for s in args.hints.split(",") if s.strip()]
    return call_pick(
        api=args.api,
        image_path=args.image,
        goal=args.goal,
        intent=args.intent,
        site=args.site,
        hints_text=hints_list,
        mode=args.mode,
        dpr=args.dpr,
        max_candidates=args.max_candidates,
        yolo_conf=args.yolo_conf,
        yolo_iou=args.yolo_iou,
        provider=args.provider,
        idem=args.idem,
    )


if __name__ == "__main__":
    raise SystemExit(main())
