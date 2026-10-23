import time, asyncio
import sys
import os
from typing import Dict, Any, List

# Ensure we can import from the parent directory
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from core.registry import get_action
from core.expr import eval_expr
from core.artifacts import step_dir, dump_json

class WorkflowRunner:
    def __init__(self, spec: Dict[str, Any], ctx):
        self.spec = spec
        self.ctx = ctx
        self.state = spec["start"]
        self.ctx.vars.update(spec.get("vars", {}))
        self.step_idx = 0
        self.priority = spec.get("meta", {}).get("priority", "LOW")  # 'HIGH' | 'LOW'

        # Stage 6: Checkpoint 控制标记
        self._pause_requested = False
        self._stop_requested = False
        self._paused = False

    def run(self):
        states = self.spec["states"]
        while self.state:
            st = states[self.state]
            self._run_state(st)
            self.state = self._next_state(st)

    def _run_state(self, st: Dict[str, Any]):
        actions: List[Dict[str, Any]] = st.get("actions", [])
        for step in actions:
            self.step_idx += 1
            self._run_action(step)

    def _run_action(self, step: Dict[str, Any]):
        fn = get_action(step["do"])
        t0 = time.time()
        res = fn(step, self.ctx)  # 同步执行
        if step.get("save"): self.ctx.vars[step["save"]] = res
        d = step_dir(self.ctx.artifacts_dir, self.ctx.run_id, self.state, self.step_idx)
        dump_json(d, "action.json", {"do": step["do"], "params": {k:v for k,v in step.items() if k!='do'}})
        dump_json(d, "result.json", res if isinstance(res, (dict, list)) else {"result": str(res)})
        self.ctx.services.logger.info(
            f"action={step['do']} dur_ms={int((time.time()-t0)*1000)} priority={self.priority}"
        )

    def _next_state(self, st: Dict[str, Any]):
        # transitions: [{if, go_to}] 或 [{go_to}]
        for tr in st.get("transitions", []):
            cond = tr.get("if")
            if cond is None or eval_expr(cond, self.ctx):
                return tr.get("go_to")
        return None

    async def step(self, should_preempt):
        """执行当前 state 的所有 actions（每个动作后检查抢占点），然后根据 transitions 迁移到下一个 state。
           如果 should_preempt() 为 True，则提前让出（下次再继续当前 state 的剩余动作）。"""
        if not self.state:
            return
        st = self.spec["states"][self.state]
        actions: List[Dict[str, Any]] = st.get("actions", [])
        i = 0
        while i < len(actions):
            step = actions[i]
            await self._run_action_async(step)
            i += 1
            # 抢占点：每个动作后检查
            if await should_preempt():
                return
        # 动作执行完，才进行 transitions
        self.state = self._next_state(st)

    async def _run_action_async(self, step: Dict[str, Any]):
        fn = get_action(step["do"])
        t0 = time.time()
        # 动作本身是同步函数：在这里直接调用（若后续需要IO，可改为await fn(...)）
        res = fn(step, self.ctx)
        if step.get("save"): self.ctx.vars[step["save"]] = res
        d = step_dir(self.ctx.artifacts_dir, self.ctx.run_id, self.state, self.step_idx)
        dump_json(d, "action.json", {"do": step["do"], "params": {k:v for k,v in step.items() if k!='do'}})
        dump_json(d, "result.json", res if isinstance(res, (dict, list)) else {"result": str(res)})
        self.step_idx += 1
        self.ctx.services.logger.info(
            f"action={step['do']} dur_ms={int((time.time()-t0)*1000)} priority={self.priority}"
        )
        # 给事件循环一个机会调度（避免长时间占用）
        await asyncio.sleep(0)