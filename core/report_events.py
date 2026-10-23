# core/report_events.py - Normalized event schema for reporting
import json
import os
import time
from typing import Dict, Any, Optional

# Global event file path
_REPORT_PATH = os.environ.get("REPORT_JSONL", "out/logs/report_events.jsonl")

def _write_event(obj: Dict[str, Any]):
    """Write event to JSONL file"""
    try:
        os.makedirs(os.path.dirname(_REPORT_PATH), exist_ok=True)
        with open(_REPORT_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[report_events] Failed to write event: {e}")

def emit_run_begin(workflow_path: str, goal: str, run_id: str = None):
    """Emit run start event"""
    _write_event({
        "t": time.time(),
        "ev": "run_begin",
        "workflow_path": workflow_path,
        "goal": goal,
        "run_id": run_id or f"run_{int(time.time())}"
    })

def emit_run_end(status: str, total_ms: int, stats: Dict[str, Any] = None):
    """Emit run completion event"""
    _write_event({
        "t": time.time(),
        "ev": "run_end",
        "status": status,  # "success", "failure", "timeout"
        "total_ms": total_ms,
        "stats": stats or {}
    })

def emit_step_begin(step_idx: int, sig: str, goal: str, state_id: str = None):
    """Emit step start event"""
    _write_event({
        "t": time.time(),
        "ev": "step_begin",
        "i": step_idx,
        "sig": sig,
        "goal": goal,
        "state_id": state_id
    })

def emit_step_end(step_idx: int, status: str, ms: int, chosen_id: str = None):
    """Emit step completion event"""
    _write_event({
        "t": time.time(),
        "ev": "step_end",
        "i": step_idx,
        "status": status,  # "success", "failure", "timeout", "need_input"
        "ms": ms,
        "chosen_id": chosen_id
    })

def emit_strategy(step_idx: int, spec: Dict[str, Any], cache_hit: bool, 
                  fallback_used: bool, execution_success: bool = True):
    """Emit strategy selection and execution event"""
    _write_event({
        "t": time.time(),
        "ev": "strategy",
        "i": step_idx,
        "spec": spec,
        "cache_hit": cache_hit,
        "fallback": fallback_used,
        "success": execution_success
    })

def emit_verifier(step_idx: int, v1: float, v2: float, vllm: float, s: float, 
                  state_vote: Dict[str, Any], method: str = "combined"):
    """Emit verifier scores and state vote breakdown"""
    _write_event({
        "t": time.time(),
        "ev": "verify",
        "i": step_idx,
        "V1": v1,  # Template matching score
        "V2": v2,  # ORB/SIFT feature matching score
        "LLM": vllm,  # LLM verification score
        "S": s,  # Combined score
        "state_vote": state_vote,
        "method": method
    })

def emit_llm_call(kind: str, tokens: int, meta: Dict[str, Any]):
    """Emit LLM call event with token usage"""
    _write_event({
        "t": time.time(),
        "ev": "llm",
        "kind": kind,  # "strategy", "picker", "arbiter"
        "tokens": tokens,
        "meta": meta
    })

def emit_picker_decision(step_idx: int, chosen_id: str, confidence: float, 
                        why: str, alternatives: list = None, method: str = "llm"):
    """Emit picker decision event"""
    _write_event({
        "t": time.time(),
        "ev": "picker",
        "i": step_idx,
        "chosen_id": chosen_id,
        "confidence": confidence,
        "why": why,
        "alternatives": alternatives or [],
        "method": method  # "llm", "memory", "deterministic"
    })

def emit_memory_event(step_idx: int, action: str, sig_key: str, 
                     outcome: str, reason: str = "", click_id: str = None):
    """Emit memory storage/retrieval event"""
    _write_event({
        "t": time.time(),
        "ev": "memory",
        "i": step_idx,
        "action": action,  # "store", "retrieve", "hit", "miss"
        "sig_key": sig_key,
        "outcome": outcome,  # "success", "failure", "need_input"
        "reason": reason,
        "click_id": click_id
    })

def emit_anchor_event(step_idx: int, anchor_type: str, success: bool, 
                     confidence: float, method: str):
    """Emit anchor detection/matching event"""
    _write_event({
        "t": time.time(),
        "ev": "anchor",
        "i": step_idx,
        "type": anchor_type,  # "row", "action", "state"
        "success": success,
        "confidence": confidence,
        "method": method  # "template", "orb", "sift"
    })

def emit_degradation(step_idx: int, component: str, degradation: str, reason: str):
    """Emit budget-based degradation event"""
    _write_event({
        "t": time.time(),
        "ev": "degradation",
        "i": step_idx,
        "component": component,  # "picker", "arbiter", "strategy"
        "degradation": degradation,  # "skip", "downscale", "textonly"
        "reason": reason  # "over_step_budget", "over_run_budget", "call_limit"
    })

def emit_error(step_idx: int, component: str, error_type: str, message: str):
    """Emit error event"""
    _write_event({
        "t": time.time(),
        "ev": "error",
        "i": step_idx,
        "component": component,
        "error_type": error_type,
        "message": message
    })

def emit_custom(event_type: str, data: Dict[str, Any]):
    """Emit custom event"""
    _write_event({
        "t": time.time(),
        "ev": event_type,
        **data
    })

# Utility functions for reading events

def read_events(file_path: str = None) -> list:
    """Read all events from JSONL file"""
    path = file_path or _REPORT_PATH
    events = []
    
    if not os.path.exists(path):
        return events
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except Exception as e:
        print(f"[report_events] Failed to read events: {e}")
    
    return events

def filter_events_by_type(events: list, event_type: str) -> list:
    """Filter events by type"""
    return [e for e in events if e.get("ev") == event_type]

def filter_events_by_step(events: list, step_idx: int) -> list:
    """Filter events by step index"""
    return [e for e in events if e.get("i") == step_idx]

def get_step_summary(events: list, step_idx: int) -> Dict[str, Any]:
    """Get summary of events for a specific step"""
    step_events = filter_events_by_step(events, step_idx)
    
    summary = {
        "step_idx": step_idx,
        "events_count": len(step_events),
        "strategy_used": False,
        "strategy_cache_hit": False,
        "llm_calls": 0,
        "total_tokens": 0,
        "verifier_scores": {},
        "picker_method": "unknown",
        "degradations": [],
        "errors": []
    }
    
    for event in step_events:
        ev_type = event.get("ev")
        
        if ev_type == "strategy":
            summary["strategy_used"] = True
            summary["strategy_cache_hit"] = event.get("cache_hit", False)
        
        elif ev_type == "llm":
            summary["llm_calls"] += 1
            summary["total_tokens"] += event.get("tokens", 0)
        
        elif ev_type == "verify":
            summary["verifier_scores"] = {
                "V1": event.get("V1", 0),
                "V2": event.get("V2", 0),
                "LLM": event.get("LLM", 0),
                "S": event.get("S", 0)
            }
        
        elif ev_type == "picker":
            summary["picker_method"] = event.get("method", "unknown")
        
        elif ev_type == "degradation":
            summary["degradations"].append({
                "component": event.get("component"),
                "degradation": event.get("degradation"),
                "reason": event.get("reason")
            })
        
        elif ev_type == "error":
            summary["errors"].append({
                "component": event.get("component"),
                "error_type": event.get("error_type"),
                "message": event.get("message")
            })
    
    return summary

def clear_events(file_path: str = None):
    """Clear events file"""
    path = file_path or _REPORT_PATH
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception as e:
        print(f"[report_events] Failed to clear events: {e}")