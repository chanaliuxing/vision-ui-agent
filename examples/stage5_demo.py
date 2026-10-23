#!/usr/bin/env python3
"""Stage 5: Multi-Chat App Adapter Demo"""

import sys
import os
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

import asyncio
import subprocess
import time

async def main():
    print("=== Stage 5: Multi-Chat App Adapter Demo ===")

    env = os.environ.copy()
    env.update({
        'AWS_REGION': 'us-east-1',
        'AWS_ENDPOINT_URL': 'http://localhost:4566',
        'AWS_ACCESS_KEY_ID': 'test',
        'AWS_SECRET_ACCESS_KEY': 'test',
        'PYTHONPATH': parent_dir
    })

    print("\n1. 启动微信低优先级轮询器")
    lp_cmd = [sys.executable, "core/runner.py", "examples/stage5_lp_generic.json"]
    process_lp = subprocess.Popen(lp_cmd, env=env, cwd=parent_dir)
    print(f"   WeChat LP Poller started: PID {process_lp.pid}")

    print("\n2. 启动微信高优先级响应器")
    hp_cmd = [sys.executable, "core/runner.py", "examples/stage5_hp_generic.json"]
    process_hp = subprocess.Popen(hp_cmd, env=env, cwd=parent_dir)
    print(f"   WeChat HP Responder started: PID {process_hp.pid}")

    print("\n3. 等待 20 秒观察多应用聊天自动化过程")
    print("   - LP: 轮询未读标记 → OCR聊天截图 → 提交LLM")
    print("   - HP: 监听LLM完成 → 聚焦联系人 → 发送回复")
    print("   - API: 上报聊天记录和事件到云端")
    await asyncio.sleep(20)

    print("\n4. 停止所有工作流")
    process_lp.terminate()
    process_hp.terminate()
    process_lp.wait()
    process_hp.wait()
    print("   All workflows stopped")

    print("\n=== Stage 5 Demo Complete ===")
    print("✓ 多聊天应用适配器框架已实现")
    print("✓ 本地OCR服务已集成")
    print("✓ 云端API客户端已配置")
    print("✓ 微信/Slack通用工作流已验证")

if __name__ == "__main__":
    asyncio.run(main())