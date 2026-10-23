from __future__ import annotations
from typing import Any, Dict, List, Optional


class PageState:
    """Very light virtual page state for dry-run simulation.

    dom_present: list of CSS selectors or role:text tokens representing available targets.
    scrollable: whether scroll can reveal more content.
    """

    def __init__(self, dom_present: Optional[List[str]] = None, scrollable: bool = True) -> None:
        self.dom_present = set(dom_present or [])
        self.scrollable = bool(scrollable)

    def has(self, target: Dict[str, Any]) -> bool:
        css = target.get("css")
        role = target.get("role")
        text = target.get("text")
        if css and css in self.dom_present:
            return True
        if role or text:
            key = f"{role or '*'}:{(text or '').strip()}".strip(':')
            return key in self.dom_present
        return False


def _iter_states(flow: Dict[str, Any]):
    states = flow.get("states") or {}
    start = flow.get("start")
    if not isinstance(states, dict):
        return []
    # simple order: start first if exists, then any others
    keys = [start] + [k for k in states.keys() if k != start] if start in states else list(states.keys())
    for k in keys:
        yield k, states[k]


def simulate(flow: Dict[str, Any], ps: Optional[PageState] = None) -> Dict[str, Any]:
    ps = ps or PageState()
    issues: List[Dict[str, Any]] = []
    suggestions: List[Dict[str, Any]] = []

    for sid, state in _iter_states(flow):
        actions = state.get("actions") or []
        for idx, act in enumerate(actions):
            op = act.get("do")
            if not op:
                continue
            if op == "instr.navigate":
                # after navigate, suggest a WaitQuiet if not followed by wait
                nxt = actions[idx + 1] if idx + 1 < len(actions) else None
                if not (nxt and nxt.get("do") in ("instr.wait", "wait_for")):
                    suggestions.append({
                        "kind": "wait_quiet_insert",
                        "state": sid,
                        "index": idx + 1,
                        "value": {"do": "instr.key", "key": "WaitQuiet"}
                    })
            elif op == "instr.click":
                tgt = act.get("target") or {}
                if not ps.has(tgt):
                    issues.append({"state": sid, "index": idx, "reason": "target_not_present"})
                    # propose a small scroll then retry click
                    suggestions.append({
                        "kind": "scroll_then_retry",
                        "state": sid,
                        "index": idx,
                        "value": {"do": "instr.scroll", "dir": "down", "amount": 300}
                    })
            elif op == "instr.type_text":
                tgt = act.get("target") or {}
                if tgt and not ps.has(tgt):
                    issues.append({"state": sid, "index": idx, "reason": "input_not_present"})
            elif op == "instr.read":
                tgt = act.get("target") or {}
                if tgt and not ps.has(tgt):
                    issues.append({"state": sid, "index": idx, "reason": "read_target_not_present"})
            # other ops: accept

    ok = len(issues) == 0
    return {"ok": ok, "issues": issues, "suggestions": suggestions}


__all__ = ["PageState", "simulate"]

