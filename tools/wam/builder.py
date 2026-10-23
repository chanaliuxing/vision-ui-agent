from __future__ import annotations
from typing import Any, Dict, List, Optional


class WF:
    """Minimal workflow builder for authoring valid JSON workflows.

    Produces a dict that conforms to schema/workflow.schema.json.
    Supports helper patterns: for_range (counter loop) and poll (self-loop with sleep).
    """

    def __init__(self, version: str = "1.1") -> None:
        self.doc: Dict[str, Any] = {"version": version, "start": None, "vars": {}, "states": {}}

    def start(self, state: str) -> "WF":
        self.doc["start"] = state
        return self

    def set_var(self, k: str, v: Any) -> "WF":
        self.doc.setdefault("vars", {})[k] = v
        return self

    def state(
        self,
        name: str,
        actions: List[Dict[str, Any]],
        transitions: Optional[List[Dict[str, Any]]] = None,
        on_success: Optional[str] = None,
    ) -> "WF":
        s: Dict[str, Any] = {"actions": actions or []}
        if transitions:
            s["transitions"] = transitions
        if on_success is not None:
            s["on_success"] = on_success
        self.doc.setdefault("states", {})[name] = s
        if not self.doc.get("start"):
            self.doc["start"] = name
        return self

    def for_range(
        self,
        name: str,
        counter: str,
        count_expr: str,
        body_actions: List[Dict[str, Any]],
        next_state: str = "done",
    ) -> "WF":
        loop = f"{name}_loop"
        self.set_var(counter, 0)
        loop_actions = list(body_actions or []) + [{"do": "increment_variable", "name": counter}]
        transitions = [
            {"if": f"@{counter} < {count_expr}", "go_to": loop},
            {"else_go_to": next_state},
        ]
        self.state(loop, actions=loop_actions, transitions=transitions)
        if next_state not in self.doc.get("states", {}):
            self.state(next_state, actions=[{"do": "log", "message": f"loop {name} completed"}])
        return self

    def poll(self, name: str, period_ms: int, actions: List[Dict[str, Any]]) -> "WF":
        poll_actions = list(actions or []) + [{"do": "sleep_ms", "value": max(0, int(period_ms))}]
        self.state(name, actions=poll_actions, on_success=name)
        return self

    def build(self) -> Dict[str, Any]:
        return self.doc


def build_indeed_loop(count: int = 10) -> Dict[str, Any]:
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
    )
    return wf.build()


def build_wechat_poll_reply() -> Dict[str, Any]:
    wf = (
        WF()
        .poll(
            name="poll_new_msgs",
            period_ms=5000,
            actions=[
                {"do": "instr.key", "key": "WaitQuiet"},
                {"do": "instr.read", "target": {"css": "div.chat_list"}, "fields": ["texts"], "save": "msgs"},
                {"do": "log", "message": "polled messages"},
            ],
        )
    )
    return wf.build()

