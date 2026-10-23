#!/usr/bin/env python3
"""
Stage 2 Demo: Local Preemptive Scheduler

This script demonstrates HP/LP scheduling with local message queue
"""

import asyncio, uuid
import json, pathlib
import sys
import os

# Add parent directory to path to import core modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.logging_setup import setup_logger
from core.context import Ctx
from core.runner import WorkflowRunner
from client.bus_local import LocalBus
from client.services_local import build_services
from client.scheduler import Scheduler

# Import all actions to register them
import actions.vars
import actions.flow
import actions.wait_scroll
import actions.exec
import actions.ext
import actions.mq_local
import actions.demo

# Dummy adapters for testing
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
    logger = setup_logger()
    bus = LocalBus()
    services = build_services(DummyDOM(), DummyOS(), DummyVision(), DummyLogger(), bus)

    # LP runner
    lp_spec = load_spec("examples/stage2_lp_poller.json")
    lp_ctx = Ctx(services=services, run_id=str(uuid.uuid4()))
    lp_runner = WorkflowRunner(lp_spec, lp_ctx)

    # HP runner
    hp_spec = load_spec("examples/stage2_hp_responder.json")
    hp_ctx = Ctx(services=services, run_id=str(uuid.uuid4()))
    hp_runner = WorkflowRunner(hp_spec, hp_ctx)

    print("Starting Stage 2 Demo: Local Preemptive Scheduler")
    print("Watch for HP messages preempting LP execution...")

    sched = Scheduler(hp_runner=hp_runner, lp_runners={"poller": lp_runner}, services=services)
    await sched.start()

if __name__ == "__main__":
    asyncio.run(main())