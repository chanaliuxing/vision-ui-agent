#!/usr/bin/env python3
"""
Stage 3 Demo: SQS-based Preemptive Scheduler

This script demonstrates HP/LP scheduling with SQS FIFO queues
"""

import asyncio, uuid, os, json, pathlib
import sys

# Add parent directory to path to import core modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.logging_setup import setup_logger
from core.context import Ctx
from core.runner import WorkflowRunner
from client.services_sqs import build_services_sqs
from client.scheduler import Scheduler

# Import all actions to register them
import actions.vars
import actions.flow
import actions.wait_scroll
import actions.exec
import actions.ext
import actions.mq
import actions.demo

class DummyDOM:
    def open(self, url): return {"ok": True}
    def exists(self, selector): return True
    def extract(self, query): return {"posts": []}
    def go_back(self): return {"ok": True}

class DummyOS:
    def move_to(self, x, y): pass
    def click(self): pass
    def scroll(self, px): pass

class DummyVision:
    pass

class DummyLogger:
    def info(self, message, extra=None):
        print(f"LOG: {message}")
    def error(self, message, extra=None):
        print(f"ERROR: {message}")

def load_spec(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))

async def main():
    # Set environment variables for LocalStack
    os.environ.setdefault("AWS_REGION", "us-east-1")
    os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost:4566")
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")

    logger = setup_logger()
    services = build_services_sqs(DummyDOM(), DummyOS(), DummyVision(), DummyLogger(), device_id="demo")

    lp_spec = load_spec("examples/stage3_lp_poller.json")
    lp_runner = WorkflowRunner(lp_spec, Ctx(services=services, run_id=str(uuid.uuid4())))

    hp_spec = load_spec("examples/stage3_hp_responder.json")
    hp_runner = WorkflowRunner(hp_spec, Ctx(services=services, run_id=str(uuid.uuid4())))

    print("Starting Stage 3 Demo: SQS-based Preemptive Scheduler")
    print("Make sure LocalStack is running: docker compose -f docker-compose.sqs.yml up -d")
    print("Watch for HP messages preempting LP execution via SQS...")

    # 复用阶段2的调度器，但需要适配 SQS 队列名
    # 更新调度器以使用正确的主题名
    class SQSScheduler:
        def __init__(self, hp_runner: WorkflowRunner, lp_runners: dict, services):
            self.hp_runner = hp_runner
            self.lp_runners = lp_runners
            self.services = services

        async def start(self):
            await asyncio.gather(self._loop_hp(), self._loop_lp())

        async def _loop_hp(self):
            while True:
                async def no_preempt(): return False
                await self.hp_runner.step(no_preempt)
                await asyncio.sleep(0)

        async def _loop_lp(self):
            while True:
                for wid, runner in self.lp_runners.items():
                    async def should_preempt():
                        # ★ 抢占条件：device-demo-hp.fifo 队列上有未处理消息
                        return self.services.mq.qsize("device-demo-hp.fifo") > 0
                    await runner.step(should_preempt)
                    if self.services.mq.qsize("device-demo-hp.fifo") > 0:
                        await asyncio.sleep(0)
                await asyncio.sleep(0.01)

    sched = SQSScheduler(hp_runner=hp_runner, lp_runners={"poller": lp_runner}, services=services)
    await sched.start()

if __name__ == "__main__":
    asyncio.run(main())