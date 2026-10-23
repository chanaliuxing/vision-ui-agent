#!/usr/bin/env python3

import sys
import os
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

import asyncio
import subprocess
import time

async def main():
    print("=== Stage 4: LLM Async Cloud Loop Demo ===")

    env = os.environ.copy()
    env.update({
        'AWS_REGION': 'us-east-1',
        'AWS_ENDPOINT_URL': 'http://localhost:4566',
        'AWS_ACCESS_KEY_ID': 'test',
        'AWS_SECRET_ACCESS_KEY': 'test',
        'PYTHONPATH': parent_dir
    })

    print("\n1. 启动低优先级 LLM 轮询器")
    lp_cmd = [sys.executable, "core/runner.py", "examples/stage4_lp_poller.json"]
    process_lp = subprocess.Popen(lp_cmd, env=env, cwd=parent_dir)
    print(f"   LP Poller started: PID {process_lp.pid}")

    print("\n2. 启动高优先级响应器")
    hp_cmd = [sys.executable, "core/runner.py", "examples/stage4_hp_responder.json"]
    process_hp = subprocess.Popen(hp_cmd, env=env, cwd=parent_dir)
    print(f"   HP Responder started: PID {process_hp.pid}")

    print("\n3. 等待 15 秒观察 LLM 处理过程")
    await asyncio.sleep(15)

    print("\n4. 停止所有工作流")
    process_lp.terminate()
    process_hp.terminate()
    process_lp.wait()
    process_hp.wait()
    print("   All workflows stopped")

    print("\n=== Stage 4 Demo Complete ===")

if __name__ == "__main__":
    asyncio.run(main())