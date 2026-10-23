#!/usr/bin/env python3
"""
Send the server-annotated overlay image and YOLO JSON to Gemini with a structured prompt.

Example:
  python run_gemini.py \
    --image out/screens/open_home_server_overlay.png \
    --yolo out/logs/yolo_open_home.json \
    --goal publish_post --page home
"""

import argparse
import json
import os
from typing import Any, Dict

from PIL import Image

from core.llm_client import call_llm, extract_text_generic
from core.gemini_client import parse_first_json
from core.prompt_builder import (
    PromptSpec,
    SYSTEM_TEMPLATE_UI_OUTLINE,
    build_messages,
    build_user_payload,
    build_id_only_messages,
)


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser(description="Send overlay + YOLO JSON to Gemini")
    ap.add_argument("--image", required=True, help="Path to server overlay PNG")
    ap.add_argument("--yolo", required=True, help="Path to YOLO API JSON response")
    ap.add_argument("--goal", default="publish_post")
    ap.add_argument("--page", default="home")
    ap.add_argument("--preferred-classes", default="", help="comma-separated preferred class names")
    ap.add_argument("--negative-classes", default="", help="comma-separated negative class names")
    ap.add_argument("--hints", default="", help="comma-separated short hints")
    ap.add_argument("--outline", default="", help="Path to ui_outline JSON file")
    ap.add_argument("--outline-narrative", default="", help="Optional narrative outline string")
    ap.add_argument("--allow-dangerous", action="store_true")
    ap.add_argument("--requires-danger", action="store_true")
    ap.add_argument("--k", type=int, default=6)
    ap.add_argument("--conf", type=float, default=0.3)
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--provider", default=os.getenv("LLM_PROVIDER", "gemini"))
    ap.add_argument("--model", default=os.getenv("LLM_MODEL", ""))
    ap.add_argument("--save", default="out/logs/gemini_result.json")
    ap.add_argument("--id-only", action="store_true", help="Use ID-only template (image-driven)")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.save), exist_ok=True)

    yj = load_json(args.yolo)
    W, H = Image.open(args.image).size
    outline = {}
    if args.outline and os.path.exists(args.outline):
        try:
            outline = load_json(args.outline)
        except Exception:
            outline = {}
    preferred = [s for s in (args.preferred_classes.split(",") if args.preferred_classes else []) if s]
    negative = [s for s in (args.negative_classes.split(",") if args.negative_classes else []) if s]
    hints = [s for s in (args.hints.split(",") if args.hints else []) if s]

    if args.id_only:
        messages = build_id_only_messages(goal=args.goal, hints=hints)
    else:
        spec = PromptSpec(
            goal=args.goal,
            page=args.page,
            preferred_classes=preferred,
            negative_classes=negative,
            hints=hints,
            ui_outline=outline or None,
            ui_outline_narrative=args.outline_narrative or None,
            k_max=args.k,
            conf_min=args.conf,
            allow_dangerous=args.allow_dangerous,
            requires_danger=args.requires_danger,
        )
        payload = build_user_payload(yj, (W, H), spec)
        messages = build_messages(SYSTEM_TEMPLATE_UI_OUTLINE, payload)

    # Call Gemini (requires GEMINI_API_KEY in environment or .env)
    resp = call_llm(provider=args.provider, model=(args.model or None), messages=messages, image_path=args.image, temperature=args.temperature)
    text = extract_text_generic(resp)
    parsed = parse_first_json(text) or {}

    out = {"request": {}, "raw_text": text, "parsed": parsed}
    if not args.id_only:
        out["request"]["payload"] = payload
    with open(args.save, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"Saved Gemini result to {args.save}")
    if parsed:
        print(json.dumps(parsed, ensure_ascii=False, indent=2))
    else:
        print("Warning: could not parse JSON from model response. See raw_text in the output file.")


if __name__ == "__main__":
    main()
