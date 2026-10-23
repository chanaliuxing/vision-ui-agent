#!/usr/bin/env python3
"""
Smoke/Regression suite runner (skeleton).

Runs a workflow N times and aggregates core metrics from out/logs/steps_log.jsonl and
routes.jsonl to produce a quick summary: direct-run rate, downgrade rate, error-click
rate, go_back success.

Usage:
  python tools/smoke_suite.py --workflow flows/open_chrome_xhs.json --endpoint http://127.0.0.1:8000 --runs 3

Note: This is a skeleton; scenario toggles (theme/zoom/modal/network) need to be
driven externally or via your app under test; hook those into this script if needed.
"""

import argparse
import json
import os
import subprocess
from pathlib import Path


def run_once(workflow: str, endpoint: str, env_overrides: dict | None = None) -> None:
    env = os.environ.copy()
    if env_overrides:
        env.update({k: str(v) for k, v in env_overrides.items()})
    subprocess.run(["python", "run_workflow.py", "--workflow", workflow, "--endpoint", endpoint], check=False, env=env)


def parse_m3_metrics(logs_dir: Path) -> dict:
    """Parse M3 metrics from report_events.jsonl"""
    events_file = logs_dir / "report_events.jsonl"
    m3_metrics = {
        "total_tokens": 0,
        "avg_tokens_per_step": 0,
        "p95_step_time_ms": 0,
        "strategy_cache_hit_rate": 0.0,
        "degradation_count": 0,
        "llm_calls": 0
    }
    
    if not events_file.exists():
        return m3_metrics
    
    events = []
    try:
        with open(events_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except Exception:
        return m3_metrics
    
    # Calculate metrics
    step_durations = []
    total_tokens = 0
    strategy_calls = 0
    strategy_cache_hits = 0
    degradation_count = 0
    llm_calls = 0
    
    for event in events:
        ev_type = event.get("ev")
        
        if ev_type == "step_end":
            ms = event.get("ms", 0)
            if ms > 0:
                step_durations.append(ms)
        
        elif ev_type == "llm":
            llm_calls += 1
            total_tokens += event.get("tokens", 0)
        
        elif ev_type == "strategy":
            strategy_calls += 1
            if event.get("cache_hit", False):
                strategy_cache_hits += 1
        
        elif ev_type == "degradation":
            degradation_count += 1
    
    # Calculate derived metrics
    if step_durations:
        step_durations.sort()
        p95_idx = int(len(step_durations) * 0.95)
        m3_metrics["p95_step_time_ms"] = step_durations[p95_idx] if p95_idx < len(step_durations) else step_durations[-1]
        m3_metrics["avg_tokens_per_step"] = total_tokens / len(step_durations) if len(step_durations) > 0 else 0
    
    m3_metrics["total_tokens"] = total_tokens
    m3_metrics["strategy_cache_hit_rate"] = strategy_cache_hits / strategy_calls if strategy_calls > 0 else 0.0
    m3_metrics["degradation_count"] = degradation_count
    m3_metrics["llm_calls"] = llm_calls
    
    return m3_metrics

def parse_steps(logs_dir: Path, start_lines: int | None = None):
    steps_file = logs_dir / "steps_log.jsonl"
    direct = downgrade = error = goback = auto = 0
    # M2 Strategy metrics
    strategy_calls = strategy_success = strategy_memory_hits = 0
    if steps_file.exists():
        lines = steps_file.read_text(encoding="utf-8").splitlines()
        if start_lines is not None:
            lines = lines[start_lines:]
        for line in lines:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            name = rec.get("name") or ""
            msg = rec.get("message") or ""
            status = rec.get("status") or ""
            if isinstance(name, str) and name.startswith("autostep_"):
                auto += 1
                if "replay_compound ok" in msg or "replay_legacy ok" in msg:
                    direct += 1
                if "llm_picker" in msg:
                    downgrade += 1
                if status == "fail":
                    error += 1
            if "go_back" in msg.lower():
                goback += 1
    
    # Parse timeline.log for strategy metrics
    timeline_file = logs_dir / "timeline.log"
    if timeline_file.exists():
        try:
            lines = timeline_file.read_text(encoding="utf-8").splitlines()
            for line in lines:
                if "strategy/m2_selected" in line:
                    strategy_calls += 1
                    if "source=memory" in line:
                        strategy_memory_hits += 1
                elif "strategy/m2_executed" in line:
                    strategy_success += 1
        except Exception:
            pass
    return {
        "autosteps": auto,
        "direct": direct,
        "downgrade": downgrade,
        "error": error,
        "goback": goback,
        "strategy_calls": strategy_calls,
        "strategy_success": strategy_success,
        "strategy_memory_hits": strategy_memory_hits
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workflow", required=True)
    ap.add_argument("--endpoint", default="http://127.0.0.1:8000")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--scenarios", default="default")
    ap.add_argument("--dod-direct", type=float, default=0.85)
    ap.add_argument("--dod-downgrade", type=float, default=0.10)
    ap.add_argument("--dod-error", type=float, default=0.01)
    ap.add_argument("--dod-goback", type=float, default=0.80)
    # M3 DoD gates
    ap.add_argument("--dod-strategy-cache", type=float, default=0.90, help="Min strategy cache hit rate")
    ap.add_argument("--dod-tokens-per-run", type=int, default=40000, help="Max tokens per run")
    ap.add_argument("--dod-p95-step-ms", type=int, default=5000, help="Max P95 step time (ms)")
    ap.add_argument("--out", default="out")
    args = ap.parse_args()

    for i in range(args.runs):
        print(f"[run {i+1}/{args.runs}] running workflow...")
        run_once(args.workflow, args.endpoint)

    logs_dir = Path(args.out) / "logs"
    m = parse_steps(logs_dir)
    m3 = parse_m3_metrics(logs_dir)
    
    auto = max(1, m["autosteps"])  # avoid div by zero
    print("\n== Smoke Summary ==")
    print(f"autosteps: {m['autosteps']}")
    print(f"direct_run_rate: {m['direct']/auto:.2%}")
    print(f"downgrade_rate: {m['downgrade']/auto:.2%}")
    print(f"error_click_rate: {m['error']/auto:.2%}")
    print(f"go_back_events: {m['goback']}")
    
    # M2 Strategy metrics
    strategy_calls = m.get('strategy_calls', 0)
    if strategy_calls > 0:
        print(f"\n== M2 Strategy Metrics ==")
        print(f"strategy_calls: {strategy_calls}")
        print(f"strategy_success_rate: {m.get('strategy_success', 0)/strategy_calls:.2%}")
        print(f"strategy_memory_hit_rate: {m.get('strategy_memory_hits', 0)/strategy_calls:.2%}")
    else:
        print(f"\n== M2 Strategy Metrics ==")
        print("strategy_layer: DISABLED (set STRATEGY_LAYER=1 to enable)")
    
    # M3 Cost Control & Performance Metrics
    print(f"\n== M3 Cost Control & Performance ==")
    print(f"total_tokens: {m3['total_tokens']:,}")
    print(f"avg_tokens_per_step: {m3['avg_tokens_per_step']:.0f}")
    print(f"p95_step_time_ms: {m3['p95_step_time_ms']:.0f}ms")
    print(f"strategy_cache_hit_rate: {m3['strategy_cache_hit_rate']:.2%}")
    print(f"degradation_count: {m3['degradation_count']}")
    print(f"llm_calls: {m3['llm_calls']}")
    
    # DoD Gates Evaluation
    print(f"\n== DoD Gates Evaluation ==")
    failures = []
    
    # Basic metrics
    direct_rate = m['direct']/auto
    downgrade_rate = m['downgrade']/auto
    error_rate = m['error']/auto
    
    if direct_rate < args.dod_direct:
        failures.append(f"direct_run_rate: {direct_rate:.2%} < {args.dod_direct:.2%}")
    
    if downgrade_rate > args.dod_downgrade:
        failures.append(f"downgrade_rate: {downgrade_rate:.2%} > {args.dod_downgrade:.2%}")
    
    if error_rate > args.dod_error:
        failures.append(f"error_click_rate: {error_rate:.2%} > {args.dod_error:.2%}")
    
    # M3 specific gates
    if m3['strategy_cache_hit_rate'] < args.dod_strategy_cache:
        failures.append(f"strategy_cache_hit_rate: {m3['strategy_cache_hit_rate']:.2%} < {args.dod_strategy_cache:.2%}")
    
    if m3['total_tokens'] > args.dod_tokens_per_run:
        failures.append(f"total_tokens: {m3['total_tokens']:,} > {args.dod_tokens_per_run:,}")
    
    if m3['p95_step_time_ms'] > args.dod_p95_step_ms:
        failures.append(f"p95_step_time_ms: {m3['p95_step_time_ms']:.0f}ms > {args.dod_p95_step_ms}ms")
    
    if failures:
        print("❌ FAILED DoD Gates:")
        for failure in failures:
            print(f"  - {failure}")
        print(f"\nFailed {len(failures)} out of 6 gates")
        exit(1)
    else:
        print("✅ ALL DoD Gates PASSED")
        print("Ready for production deployment!")


if __name__ == "__main__":
    main()
