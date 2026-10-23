#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path

from core.prompt_builder import build_workflow_prompt
from core.llm_client import generate_json


def _load_json_arg(value: str) -> dict:
    if not value:
        return {}
    try:
        # Allow inline JSON or path to JSON file
        if (value.endswith('.json') or value.endswith('.JSON')) and Path(value).exists():
            return json.loads(Path(value).read_text(encoding='utf-8'))
        return json.loads(value)
    except Exception:
        return {}


def main():
    ap = argparse.ArgumentParser(description="Generate a workflow JSON via LLM meta-prompt")
    ap.add_argument("--task", required=True, help="Task description (natural language)")
    ap.add_argument("--env", default="{}", help="Inline JSON or path to JSON file")
    ap.add_argument("--inputs", default="{}", help="Inline JSON or path to JSON file")
    ap.add_argument("--out", default=None, help="Output path under flows/ (e.g., flows/my_flow.json)")
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--provider", default=os.getenv("LLM_PROVIDER", "gemini"))
    ap.add_argument("--model", default=os.getenv("LLM_MODEL", ""))
    args = ap.parse_args()

    env = _load_json_arg(args.env)
    user_inputs = _load_json_arg(args.inputs)
    messages = build_workflow_prompt(task=args.task, env=env, user_inputs=user_inputs, include_examples=True)
    data = generate_json(messages=messages, image_path=None, temperature=args.temperature, provider=args.provider, model=(args.model or None))

    if args.out:
        out_path = Path(args.out)
        if not out_path.is_absolute():
            out_path = Path("flows") / out_path.name
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved to {out_path}")
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
