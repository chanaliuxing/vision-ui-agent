#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path

from .builder import WF


def _ensure_autofix(doc: dict) -> dict:
    d = json.loads(json.dumps(doc))  # deep copy
    d.setdefault("version", "1.1")
    d.setdefault("name", d.get("name") or "workflow")
    d.setdefault("autofix", {"mode": "auto_promote_on_success", "limits": {"max_patches_per_run": 2}})
    return d


def build_template_xhs(name: str = "xhs_search_reply_instr") -> dict:
    wf = (
        WF()
        .start("open_home")
        .state(
            "open_home",
            actions=[
                {"do": "instr.navigate", "url": "https://www.xiaohongshu.com/explore"},
                {"do": "instr.key", "key": "WaitQuiet"},
                {"do": "instr.click", "target": {"css": "input[placeholder*='搜索'], input[type=search]"}},
            ],
            on_success="search",
        )
        .state(
            "search",
            actions=[
                {"do": "instr.type_text", "target": {"css": "input[placeholder*='搜索'], input[type=search]"}, "text": "温哥华 卖车", "clear": True},
                {"do": "instr.key", "key": "Enter"},
                {"do": "instr.wait", "ms": 3000},
            ],
            on_success="results",
        )
        .state(
            "results",
            actions=[
                {"do": "instr.wait", "ms": 1500},
                {"do": "instr.scroll", "dir": "down", "amount": 400},
                {"do": "instr.click", "target": {"css": "section a, a[href*='/explore/']"}},
                {"do": "instr.key", "key": "WaitQuiet"},
            ],
            on_success="done",
        )
        .state("done", actions=[{"do": "instr.answer_user", "text": "xhs search/open completed"}])
    ).build()
    wf["name"] = name
    return _ensure_autofix(wf)


def build_template_wechat(name: str = "wechat_web_reply_instr", contact: str = "文件传输助手", text: str = "你好，这是一条自动化消息。") -> dict:
    wf = (
        WF()
        .start("open")
        .state(
            "open",
            actions=[
                {"do": "instr.navigate", "url": "https://wx.qq.com/"},
                {"do": "instr.key", "key": "WaitQuiet"},
            ],
            on_success="search_contact",
        )
        .state(
            "search_contact",
            actions=[
                {"do": "instr.click", "target": {"css": "input[placeholder*='搜索'], input[placeholder*='Search' i]"}},
                {"do": "instr.type_text", "target": {"css": "input[placeholder*='搜索'], input[placeholder*='Search' i]"}, "text": contact, "clear": True},
                {"do": "instr.key", "key": "Enter"},
                {"do": "instr.key", "key": "WaitQuiet"},
            ],
            on_success="send_message",
        )
        .state(
            "send_message",
            actions=[
                {"do": "instr.click", "target": {"css": "div[contenteditable='true'], textarea"}},
                {"do": "instr.type_text", "target": {"css": "div[contenteditable='true'], textarea"}, "text": text, "clear": False},
                {"do": "instr.key", "key": "Enter"},
                {"do": "instr.answer_user", "text": "WeChat Web message sent"},
            ],
        )
    ).build()
    wf["name"] = name
    return _ensure_autofix(wf)


def build_template_indeed(name: str = "indeed_apply_loop_instr", count: int = 10) -> dict:
    wf = (
        WF()
        .for_range(
            name="apply",
            counter="i",
            count_expr=str(int(count)),
            body_actions=[
                {"do": "instr.scroll", "target": {"css": "div.left-pane"}, "dir": "down", "amount": 600},
                {"do": "instr.click", "target": {"css": "div.left-pane .job-card:nth-child(@i+1)"}},
                {"do": "instr.wait", "ms": 500},
                {"do": "instr.click", "target": {"role": "button", "text": "Apply"}},
            ],
            next_state="done",
        )
    ).build()
    wf["name"] = name
    return _ensure_autofix(wf)


def generate_via_llm(task: str, provider: str | None, model: str | None, temperature: float = 0.2) -> dict:
    # Inline simplified LLM call to avoid subprocess; add a strong constraint to use instr.* and autofix
    from core.llm_client import generate_json
    sys_prompt = (
        "Generate a Workflow JSON that conforms to our schema and prefers instr.* actions.\n"
        "Rules:\n"
        "- Use instr.* (click/type_text/scroll/navigate/hover/key/select_option/upload/read/wait/history/task_complete/answer_user).\n"
        "- Include {\"version\":\"1.1\", \"name\":..., \"autofix\":{\"mode\":\"auto_promote_on_success\"}} at the top.\n"
        "- Keep states minimal with actions + on_success/transitions.\n"
        "- Output STRICT JSON only."
    )
    messages = [
        {"role": "user", "parts": [{"text": sys_prompt}, {"text": f"TASK:\n{task}"}]}
    ]
    data = generate_json(messages=messages, image_path=None, temperature=temperature, provider=(provider or os.getenv("LLM_PROVIDER")), model=(model or os.getenv("LLM_MODEL") or None))
    return data


def main():
    ap = argparse.ArgumentParser(description="Generate workflow via template or LLM (instr.* + autofix by default)")
    sub = ap.add_subparsers(dest="mode")

    t = sub.add_parser("template", help="Generate from built-in templates")
    t.add_argument("name", choices=["xhs_search", "wechat_reply", "indeed_loop"], help="Template name")
    t.add_argument("--out", required=True, help="Output file under flows/ (e.g., flows/my_flow.json)")
    t.add_argument("--flow-name", default=None, help="workflow name (defaults to output filename without ext)")
    t.add_argument("--count", type=int, default=10, help="indeed_loop count")
    t.add_argument("--contact", default="文件传输助手", help="wechat contact")
    t.add_argument("--text", default="你好，这是一条自动化消息。", help="wechat message text")

    l = sub.add_parser("llm", help="Generate with LLM meta-prompt (instr.* preferred)")
    l.add_argument("--task", required=True)
    l.add_argument("--out", required=True)
    l.add_argument("--provider", default=os.getenv("LLM_PROVIDER"))
    l.add_argument("--model", default=os.getenv("LLM_MODEL"))
    l.add_argument("--temperature", type=float, default=0.2)

    args = ap.parse_args()

    Path("flows").mkdir(parents=True, exist_ok=True)

    if args.mode == "template":
        out = Path(args.out)
        wname = args.flow_name or out.stem
        if args.name == "xhs_search":
            data = build_template_xhs(name=wname)
        elif args.name == "wechat_reply":
            data = build_template_wechat(name=wname, contact=args.contact, text=args.text)
        else:
            data = build_template_indeed(name=wname, count=args.count)
    elif args.mode == "llm":
        data = generate_via_llm(task=args.task, provider=args.provider, model=args.model, temperature=args.temperature)
        out = Path(args.out)
    else:
        ap.error("mode must be 'template' or 'llm'")
        return 2

    if not out.is_absolute():
        out = Path("flows") / out.name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

