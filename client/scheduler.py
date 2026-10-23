import asyncio
from typing import Dict
from core.runner import WorkflowRunner

class Scheduler:
    def __init__(self, hp_runner: WorkflowRunner, lp_runners: Dict[str, WorkflowRunner], services):
        self.hp_runner = hp_runner
        self.lp_runners = lp_runners
        self.services = services

    async def start(self):
        await asyncio.gather(self._loop_hp(), self._loop_lp())

    async def _loop_hp(self):
        # HP 工作流：不停单步推进（每步很快），动作内部非阻塞地尝试 mq.consume
        while True:
            async def no_preempt(): return False
            await self.hp_runner.step(no_preempt)  # HP 不被抢占
            await asyncio.sleep(0)  # 把时间片让出去

    async def _loop_lp(self):
        while True:
            # round-robin 所有 LP 工作流，每个只执行一小步
            for wid, runner in self.lp_runners.items():
                async def should_preempt():
                    # ★ 抢占条件：HP 主题上有未处理消息，则立即让渡
                    return self.services.mq.qsize("hp") > 0
                await runner.step(should_preempt)
                # 如果出现 HP 消息，让出时间片给 HP
                if self.services.mq.qsize("hp") > 0:
                    await asyncio.sleep(0)
            # 避免忙等
            await asyncio.sleep(0.01)