#!/usr/bin/env python3
"""
HTML Report Generator for M3 Observability

Generates comprehensive HTML reports from report_events.jsonl with:
- Run-level KPIs (direct_run_rate, strategy_cache_hit_rate, tokens, timing)
- Per-step breakdown table (strategy, verification scores, LLM usage)
- Cost analysis and budget utilization
- Performance trends and degradation analysis

Usage:
  python tools/report_gen.py [--input out/logs/report_events.jsonl] [--output out/logs/run_report.html]
"""

import argparse
import json
import os
import statistics
import sys
from datetime import datetime
from typing import Dict, List, Any

def calculate_kpis(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate run-level KPIs from events"""
    
    # Group events by step
    steps = {}
    llm_events = []
    strategy_events = []
    verifier_events = []
    degradation_events = []
    error_events = []
    
    for event in events:
        if event.get("ev") == "step_begin":
            step_idx = event.get("i")
            if step_idx is not None:
                steps[step_idx] = {"begin": event, "end": None, "events": []}
        
        elif event.get("ev") == "step_end":
            step_idx = event.get("i")
            if step_idx is not None and step_idx in steps:
                steps[step_idx]["end"] = event
        
        elif event.get("ev") == "llm":
            llm_events.append(event)
            step_idx = event.get("i")
            if step_idx in steps:
                steps[step_idx]["events"].append(event)
        
        elif event.get("ev") == "strategy":
            strategy_events.append(event)
            step_idx = event.get("i")
            if step_idx in steps:
                steps[step_idx]["events"].append(event)
        
        elif event.get("ev") == "verify":
            verifier_events.append(event)
            step_idx = event.get("i")
            if step_idx in steps:
                steps[step_idx]["events"].append(event)
        
        elif event.get("ev") == "degradation":
            degradation_events.append(event)
        
        elif event.get("ev") == "error":
            error_events.append(event)
    
    # Calculate KPIs
    total_steps = len(steps)
    if total_steps == 0:
        return {"error": "No steps found in events"}
    
    # Direct run rate (steps without picker LLM calls)
    direct_runs = 0
    downgrade_runs = 0
    error_runs = 0
    
    for step_data in steps.values():
        step_events = step_data["events"]
        has_picker_llm = any(e.get("kind") == "picker" for e in step_events if e.get("ev") == "llm")
        has_strategy = any(e.get("ev") == "strategy" for e in step_events)
        has_error = step_data["end"] and step_data["end"].get("status") == "failure"
        
        if has_error:
            error_runs += 1
        elif has_picker_llm:
            downgrade_runs += 1
        elif has_strategy:
            direct_runs += 1
        else:
            direct_runs += 1  # Assume direct if no LLM calls
    
    # Strategy cache hit rate
    strategy_calls = len(strategy_events)
    strategy_cache_hits = sum(1 for e in strategy_events if e.get("cache_hit", False))
    strategy_cache_hit_rate = strategy_cache_hits / strategy_calls if strategy_calls > 0 else 0
    
    # Token usage
    total_tokens = sum(e.get("tokens", 0) for e in llm_events)
    avg_tokens_per_step = total_tokens / total_steps if total_steps > 0 else 0
    
    # Timing
    step_durations = []
    for step_data in steps.values():
        if step_data["begin"] and step_data["end"]:
            duration = step_data["end"].get("ms", 0)
            step_durations.append(duration)
    
    p95_step_time = 0
    if step_durations:
        step_durations.sort()
        p95_idx = int(len(step_durations) * 0.95)
        p95_step_time = step_durations[p95_idx] if p95_idx < len(step_durations) else step_durations[-1]
    
    # LLM call breakdown
    llm_by_kind = {}
    for event in llm_events:
        kind = event.get("kind", "unknown")
        llm_by_kind[kind] = llm_by_kind.get(kind, 0) + 1
    
    return {
        "total_steps": total_steps,
        "direct_run_rate": direct_runs / total_steps,
        "downgrade_rate": downgrade_runs / total_steps,
        "error_click_rate": error_runs / total_steps,
        "strategy_cache_hit_rate": strategy_cache_hit_rate,
        "strategy_calls": strategy_calls,
        "strategy_cache_hits": strategy_cache_hits,
        "total_tokens": total_tokens,
        "avg_tokens_per_step": avg_tokens_per_step,
        "p95_step_time_ms": p95_step_time,
        "llm_calls_by_kind": llm_by_kind,
        "degradation_count": len(degradation_events),
        "error_count": len(error_events),
        "step_durations": step_durations
    }

def generate_step_table(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Generate per-step breakdown table"""
    
    steps = {}
    
    # Group events by step
    for event in events:
        step_idx = event.get("i")
        if step_idx is not None:
            if step_idx not in steps:
                steps[step_idx] = []
            steps[step_idx].append(event)
    
    step_table = []
    
    for step_idx in sorted(steps.keys()):
        step_events = steps[step_idx]
        
        row = {
            "step": step_idx,
            "strategy_id": "",
            "strategy_params": "",
            "cache_hit": False,
            "fallback_used": False,
            "V1": 0.0,
            "V2": 0.0,
            "LLM": 0.0,
            "S": 0.0,
            "state_vote": {},
            "llm_tokens": 0,
            "llm_calls": 0,
            "picker_method": "",
            "duration_ms": 0,
            "status": "unknown",
            "degradations": [],
            "errors": []
        }
        
        for event in step_events:
            ev_type = event.get("ev")
            
            if ev_type == "step_end":
                row["duration_ms"] = event.get("ms", 0)
                row["status"] = event.get("status", "unknown")
            
            elif ev_type == "strategy":
                spec = event.get("spec", {})
                row["strategy_id"] = spec.get("strategy_id", "")
                row["strategy_params"] = json.dumps(spec.get("params", {}), separators=(',', ':'))
                row["cache_hit"] = event.get("cache_hit", False)
                row["fallback_used"] = event.get("fallback", False)
            
            elif ev_type == "verify":
                row["V1"] = event.get("V1", 0.0)
                row["V2"] = event.get("V2", 0.0)
                row["LLM"] = event.get("LLM", 0.0)
                row["S"] = event.get("S", 0.0)
                row["state_vote"] = event.get("state_vote", {})
            
            elif ev_type == "llm":
                row["llm_tokens"] += event.get("tokens", 0)
                row["llm_calls"] += 1
            
            elif ev_type == "picker":
                row["picker_method"] = event.get("method", "")
            
            elif ev_type == "degradation":
                row["degradations"].append({
                    "component": event.get("component"),
                    "degradation": event.get("degradation"),
                    "reason": event.get("reason")
                })
            
            elif ev_type == "error":
                row["errors"].append({
                    "component": event.get("component"),
                    "error_type": event.get("error_type"),
                    "message": event.get("message")
                })
        
        step_table.append(row)
    
    return step_table

def generate_html_report(kpis: Dict[str, Any], step_table: List[Dict[str, Any]], 
                        metadata: Dict[str, Any]) -> str:
    """Generate HTML report"""
    
    # Calculate additional metrics for display
    budget_status = "🟢 WITHIN BUDGET"
    if kpis.get("total_tokens", 0) > 35000:  # 90% of default budget
        budget_status = "🟡 APPROACHING LIMIT"
    if kpis.get("total_tokens", 0) > 40000:  # Over budget
        budget_status = "🔴 OVER BUDGET"
    
    performance_status = "🟢 GOOD"
    if kpis.get("p95_step_time_ms", 0) > 4000:  # 80% of target
        performance_status = "🟡 SLOW"
    if kpis.get("p95_step_time_ms", 0) > 5000:  # Over target
        performance_status = "🔴 TOO SLOW"
    
    cache_status = "🟢 EXCELLENT"
    cache_rate = kpis.get("strategy_cache_hit_rate", 0)
    if cache_rate < 0.9:
        cache_status = "🟡 NEEDS IMPROVEMENT"
    if cache_rate < 0.7:
        cache_status = "🔴 POOR"
    
    html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>M3 Workflow Report - {metadata.get('timestamp', 'Unknown')}</title>
    <meta charset="utf-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 20px; }}
        .header {{ background: #f8f9fa; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
        .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 30px; }}
        .kpi {{ background: white; border: 1px solid #dee2e6; border-radius: 8px; padding: 15px; text-align: center; }}
        .kpi h3 {{ margin: 0 0 10px 0; color: #495057; font-size: 14px; }}
        .kpi .value {{ font-size: 24px; font-weight: bold; color: #007bff; }}
        .kpi .label {{ font-size: 12px; color: #6c757d; margin-top: 5px; }}
        .status {{ display: inline-block; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }}
        .status.good {{ background: #d4edda; color: #155724; }}
        .status.warning {{ background: #fff3cd; color: #856404; }}
        .status.error {{ background: #f8d7da; color: #721c24; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; font-size: 13px; }}
        th, td {{ padding: 8px; text-align: left; border: 1px solid #dee2e6; }}
        th {{ background: #e9ecef; font-weight: 600; }}
        tr:nth-child(even) {{ background: #f8f9fa; }}
        .strategy-cell {{ max-width: 200px; overflow: hidden; text-overflow: ellipsis; }}
        .score {{ text-align: center; font-family: monospace; }}
        .degradation {{ color: #fd7e14; font-weight: bold; }}
        .error {{ color: #dc3545; font-weight: bold; }}
        .cache-hit {{ color: #28a745; font-weight: bold; }}
        .cache-miss {{ color: #ffc107; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🚀 M3 Workflow Execution Report</h1>
        <p><strong>Generated:</strong> {metadata.get('timestamp', 'Unknown')}</p>
        <p><strong>Workflow:</strong> {metadata.get('workflow_path', 'Unknown')}</p>
        <p><strong>Total Runtime:</strong> {metadata.get('total_runtime_ms', 0):.0f}ms</p>
    </div>
    
    <div class="kpis">
        <div class="kpi">
            <h3>Direct Run Rate</h3>
            <div class="value">{kpis.get('direct_run_rate', 0):.1%}</div>
            <div class="label">Target: ≥85%</div>
        </div>
        <div class="kpi">
            <h3>Strategy Cache Hit</h3>
            <div class="value">{kpis.get('strategy_cache_hit_rate', 0):.1%}</div>
            <div class="label">{cache_status}</div>
        </div>
        <div class="kpi">
            <h3>Total Tokens</h3>
            <div class="value">{kpis.get('total_tokens', 0):,}</div>
            <div class="label">{budget_status}</div>
        </div>
        <div class="kpi">
            <h3>Avg Tokens/Step</h3>
            <div class="value">{kpis.get('avg_tokens_per_step', 0):.0f}</div>
            <div class="label">Target: &lt;3000</div>
        </div>
        <div class="kpi">
            <h3>P95 Step Time</h3>
            <div class="value">{kpis.get('p95_step_time_ms', 0):.0f}ms</div>
            <div class="label">{performance_status}</div>
        </div>
        <div class="kpi">
            <h3>Error Rate</h3>
            <div class="value">{kpis.get('error_click_rate', 0):.1%}</div>
            <div class="label">Target: &lt;1%</div>
        </div>
        <div class="kpi">
            <h3>Downgrade Rate</h3>
            <div class="value">{kpis.get('downgrade_rate', 0):.1%}</div>
            <div class="label">Target: ≤15%</div>
        </div>
        <div class="kpi">
            <h3>Degradations</h3>
            <div class="value">{kpis.get('degradation_count', 0)}</div>
            <div class="label">Budget enforcement</div>
        </div>
    </div>
    
    <h2>📊 Per-Step Breakdown</h2>
    <table>
        <thead>
            <tr>
                <th>Step</th>
                <th>Strategy</th>
                <th>Cache</th>
                <th>V1</th>
                <th>V2</th>
                <th>LLM</th>
                <th>S</th>
                <th>Tokens</th>
                <th>Duration</th>
                <th>Status</th>
                <th>Issues</th>
            </tr>
        </thead>
        <tbody>
"""
    
    for row in step_table:
        strategy_display = row["strategy_id"]
        if row["strategy_params"]:
            strategy_display += f"<br><small>{row['strategy_params']}</small>"
        
        cache_indicator = ""
        if row["strategy_id"]:
            if row["cache_hit"]:
                cache_indicator = '<span class="cache-hit">HIT</span>'
            else:
                cache_indicator = '<span class="cache-miss">MISS</span>'
        
        issues = []
        if row["degradations"]:
            for deg in row["degradations"]:
                issues.append(f'<span class="degradation">{deg["degradation"].upper()}</span>')
        if row["errors"]:
            issues.append(f'<span class="error">{len(row["errors"])} ERR</span>')
        
        status_class = "good" if row["status"] == "success" else "error" if row["status"] == "failure" else "warning"
        
        html += f"""
            <tr>
                <td>{row['step']}</td>
                <td class="strategy-cell">{strategy_display}</td>
                <td>{cache_indicator}</td>
                <td class="score">{row['V1']:.2f}</td>
                <td class="score">{row['V2']:.2f}</td>
                <td class="score">{row['LLM']:.2f}</td>
                <td class="score">{row['S']:.2f}</td>
                <td class="score">{row['llm_tokens']}</td>
                <td class="score">{row['duration_ms']}ms</td>
                <td><span class="status {status_class}">{row['status'].upper()}</span></td>
                <td>{' '.join(issues)}</td>
            </tr>
        """
    
    html += """
        </tbody>
    </table>
    
    <h2>🔧 LLM Usage Breakdown</h2>
    <table style="width: auto;">
        <thead>
            <tr>
                <th>Component</th>
                <th>Calls</th>
                <th>Percentage</th>
            </tr>
        </thead>
        <tbody>
"""
    
    total_llm_calls = sum(kpis.get("llm_calls_by_kind", {}).values())
    for kind, count in kpis.get("llm_calls_by_kind", {}).items():
        percentage = (count / total_llm_calls * 100) if total_llm_calls > 0 else 0
        html += f"""
            <tr>
                <td>{kind.title()}</td>
                <td>{count}</td>
                <td>{percentage:.1f}%</td>
            </tr>
        """
    
    html += f"""
        </tbody>
    </table>
    
    <div style="margin-top: 40px; padding: 20px; background: #f8f9fa; border-radius: 8px; font-size: 12px; color: #6c757d;">
        <p><strong>M3 Production Hardening Report</strong> - This report tracks cost control, performance, and quality metrics for the strategy-enhanced workflow system.</p>
        <p>Key thresholds: Strategy cache hit ≥90%, Direct run rate ≥85%, P95 step time ≤5000ms, Total tokens ≤40k per run.</p>
    </div>
    
</body>
</html>
"""
    
    return html

def main():
    parser = argparse.ArgumentParser(description="Generate HTML report from workflow events")
    parser.add_argument("--input", default="out/logs/report_events.jsonl", 
                        help="Input events file")
    parser.add_argument("--output", default="out/logs/run_report.html",
                        help="Output HTML file")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input):
        print(f"Error: Input file {args.input} not found")
        sys.exit(1)
    
    # Read events
    events = []
    try:
        with open(args.input, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except Exception as e:
        print(f"Error reading events: {e}")
        sys.exit(1)
    
    if not events:
        print("No events found in input file")
        sys.exit(1)
    
    # Calculate metrics
    kpis = calculate_kpis(events)
    if "error" in kpis:
        print(f"Error calculating KPIs: {kpis['error']}")
        sys.exit(1)
    
    step_table = generate_step_table(events)
    
    # Metadata
    metadata = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "workflow_path": "Unknown",
        "total_runtime_ms": 0
    }
    
    # Extract metadata from events
    run_begin = next((e for e in events if e.get("ev") == "run_begin"), None)
    run_end = next((e for e in events if e.get("ev") == "run_end"), None)
    
    if run_begin:
        metadata["workflow_path"] = run_begin.get("workflow_path", "Unknown")
    
    if run_end:
        metadata["total_runtime_ms"] = run_end.get("total_ms", 0)
    elif events:
        # Estimate from first and last events
        first_time = events[0].get("t", 0)
        last_time = events[-1].get("t", 0)
        metadata["total_runtime_ms"] = int((last_time - first_time) * 1000)
    
    # Generate HTML
    html = generate_html_report(kpis, step_table, metadata)
    
    # Write output
    try:
        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(html)
        
        print(f"Report generated: {args.output}")
        print(f"Open in browser: file://{os.path.abspath(args.output)}")
        
        # Print summary to console
        print(f"\\n📊 Summary:")
        print(f"  Steps: {kpis['total_steps']}")
        print(f"  Direct run rate: {kpis['direct_run_rate']:.1%}")
        print(f"  Strategy cache hit: {kpis['strategy_cache_hit_rate']:.1%}")
        print(f"  Total tokens: {kpis['total_tokens']:,}")
        print(f"  P95 step time: {kpis['p95_step_time_ms']:.0f}ms")
        
    except Exception as e:
        print(f"Error writing output: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()