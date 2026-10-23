#!/usr/bin/env python3
"""
Compare overlay outputs between the legacy YOLO API (app_nice_version.py)
and the new /v1/pick overlay used by the orchestrator.

Usage:
  python tools/compare_overlays.py --old http://127.0.0.1:8010 \
                                   --new http://127.0.0.1:8000 \
                                   --image s2.png

Requirements:
  - Legacy API running: uvicorn app_nice_version:app --port 8010
  - New API running:    uvicorn app:app --port 8000
  - Set FULL_CAPTURE=true for the new API so it writes overlay to CAPTURE_DIR
    (default ./yolo_captures)
"""
import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

import requests
from PIL import Image


def b64_of(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def size_of(path: str):
    with Image.open(path) as im:
        return im.size


def call_legacy(old_base: str, image_path: str, out_path: str) -> None:
    url = old_base.rstrip("/") + "/predict?return_image=true&text_mode=short&id_order=tl"
    with open(image_path, "rb") as f:
        files = {"image": (Path(image_path).name, f, "image/png")}
        resp = requests.post(url, files=files, timeout=60)
    resp.raise_for_status()
    body = resp.json()
    img_b64 = body.get("image_base64") or ""
    if img_b64.startswith("data:image"):
        img_b64 = img_b64.split(",", 1)[1]
    raw = base64.b64decode(img_b64) if img_b64 else b""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(raw)
    print(f"Legacy overlay saved -> {out_path}")


def call_new(new_base: str, image_path: str, out_path: str) -> None:
    # Build /v1/pick payload (overlay-only vision; direct LLM; short timeout)
    w, h = size_of(image_path)
    idem = f"cmp-{int(time.time()*1000)}"
    payload = {
        "image": {"base64": b64_of(image_path), "format": "png"},
        "capture": {"mode": "full", "screen_size": [w, h], "dpr": 1.0},
        "context": {"goal": "Compare overlay only"},
        "options": {"llm_method": "direct", "llm_topk_crops": 0, "llm_timeout_ms": 8000},
        "idempotency_key": idem,
    }
    url = new_base.rstrip("/") + "/v1/pick"
    resp = requests.post(url, json=payload, timeout=60)
    resp.raise_for_status()
    body = resp.json()
    if not body.get("ok", False):
        print(json.dumps(body, indent=2), file=sys.stderr)
        raise SystemExit(2)
    # Locate overlay file from CAPTURE_DIR (FULL_CAPTURE must be true for the server)
    cap_dir = Path(os.getenv("CAPTURE_DIR", "./yolo_captures"))
    # overlay is at runs/<date>/no-wf/<req_id>/vision/overlay.png
    candidates = list(cap_dir.glob(f"runs/*/no-wf/{idem}/vision/overlay.png"))
    if not candidates:
        # try using the response telemetry req_id if present
        req_id = (body.get("data", {}) or {}).get("telemetry", {}).get("req_id") or idem
        candidates = list(cap_dir.glob(f"runs/*/no-wf/{req_id}/vision/overlay.png"))
    if not candidates:
        raise FileNotFoundError("Could not find overlay.png in capture dir. Ensure FULL_CAPTURE=true on server.")
    src = candidates[-1]
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    data = src.read_bytes()
    with open(out_path, "wb") as f:
        f.write(data)
    print(f"New overlay saved -> {out_path}")


def main():
    ap = argparse.ArgumentParser(description="Compare overlays between legacy and new YOLO APIs")
    ap.add_argument("--old", default="http://127.0.0.1:8010", help="Legacy API base (app_nice_version)")
    ap.add_argument("--new", default="http://127.0.0.1:8000", help="New API base (app)")
    ap.add_argument("--image", default="s2.png", help="Path to input image")
    ap.add_argument("--out", default="out/compare", help="Output directory for overlays")
    args = ap.parse_args()

    old_out = os.path.join(args.out, "old_overlay.png")
    new_out = os.path.join(args.out, "new_overlay.png")

    call_legacy(args.old, args.image, old_out)
    call_new(args.new, args.image, new_out)
    print("Done. Compare:")
    print(f"  {old_out}")
    print(f"  {new_out}")


if __name__ == "__main__":
    main()

