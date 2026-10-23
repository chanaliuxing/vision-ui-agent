#!/usr/bin/env python3
"""
Quick metrics over routes.jsonl to estimate replay vs LLM usage and anchor tuning.

Usage:
  python tools/replay_run.py --logs out/logs
"""

import argparse
import json
import os
from collections import Counter


def iter_routes(path: str):
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                yield json.loads(line)
            except Exception:
                continue


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--logs", default="out/logs")
    args = ap.parse_args()
    routes_path = os.path.join(args.logs, "routes.jsonl")
    succ = 0
    fail = 0
    by_goal = Counter()
    tightened = 0
    relaxed = 0
    total = 0
    for r in iter_routes(routes_path):
        total += 1
        if r.get("success_count", 0) > 1:
            succ += 1
        if r.get("fail_count", 0) >= 1:
            fail += 1
        g = r.get("goal", "")
        if g:
            by_goal[g] += 1
        a = r.get("action_anchor") or {}
        if isinstance(a, dict) and a.get("type") == "template":
            th = float(a.get("th", 0.82))
            # Heuristic: >0.84 considered tightened; <0.80 considered relaxed
            if th > 0.84:
                tightened += 1
            if th < 0.80:
                relaxed += 1
    print("routes total:", total)
    print("replay successes (records with success_count>1):", succ)
    print("replay failures (records with fail_count>=1):", fail)
    print("template anchors tightened:", tightened)
    print("template anchors relaxed:", relaxed)
    print("top goals:")
    for k, v in by_goal.most_common(8):
        print("  ", k, v)


if __name__ == "__main__":
    main()

