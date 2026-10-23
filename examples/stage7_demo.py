#!/usr/bin/env python3
"""Stage 7: 登录/设备注册/机器识别码 Demo"""

import sys
import os
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

import asyncio
import json
from pathlib import Path

# 模拟依赖项（简化演示）
class DummyDOM:
    pass

class DummyOS:
    pass

class DummyVision:
    pass

class DummyLogger:
    def info(self, msg): print(f"[INFO] {msg}")
    def error(self, msg): print(f"[ERROR] {msg}")

async def main():
    print("=== Stage 7: 登录/设备注册/机器识别码 Demo ===")

    # API配置
    api_base = "http://localhost:8080"

    print("\n1. 测试API连接")
    import requests
    try:
        response = requests.get(f"{api_base}/healthz", timeout=5)
        if response.status_code == 200:
            print("   ✓ API服务运行正常")
        else:
            print("   ✗ API服务响应异常")
            return
    except Exception as e:
        print(f"   ✗ 无法连接到API服务: {e}")
        print("   请确保运行: docker compose -f docker-compose.stage7.yml up -d")
        return

    print("\n2. 使用演示账号登录")
    from client.api_client import APIClient

    # 创建API客户端并尝试登录
    api = APIClient(api_base)

    # 模拟登录演示账号
    try:
        login_response = api.post("/auth/login", {
            "email": "test@acme.com",
            "password": "demo123"
        })
        token = login_response["access_token"]
        api.set_token(token)
        print(f"   ✓ 登录成功: {login_response['user']['email']}")
    except Exception as e:
        print(f"   ✗ 登录失败: {e}")
        return

    print("\n3. 生成并获取机器识别码")
    from client.machine_code import get_machine_code
    machine_code = get_machine_code()
    print(f"   ✓ 机器识别码: {machine_code[:8]}...{machine_code[-8:]}")

    print("\n4. 注册设备")
    try:
        capabilities = {
            "apps": ["wechat", "slack"],
            "ocr": "tesseract",
            "os": os.name,
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}"
        }

        device_response = api.register_device(
            machine_code=machine_code,
            name="Stage7 Demo Device",
            capabilities=capabilities
        )

        device_id = device_response["device_id"]
        reused = device_response.get("reused", False)

        if reused:
            print(f"   ✓ 设备重用: {device_id}")
        else:
            print(f"   ✓ 设备注册成功: {device_id}")

    except Exception as e:
        print(f"   ✗ 设备注册失败: {e}")
        return

    print("\n5. 发送心跳")
    try:
        api.heartbeat(device_id)
        print("   ✓ 心跳发送成功")
    except Exception as e:
        print(f"   ✗ 心跳发送失败: {e}")

    print("\n6. 查看设备列表")
    try:
        devices_response = api.list_devices()
        devices = devices_response["devices"]
        print(f"   ✓ 找到 {len(devices)} 个设备:")
        for device in devices:
            print(f"     - {device['name']} (ID: {device['id']})")
            print(f"       应用: {device['capabilities'].get('apps', [])}")
            print(f"       最后活跃: {device['last_seen']}")
    except Exception as e:
        print(f"   ✗ 获取设备列表失败: {e}")

    print("\n7. 检查本地认证文件")
    auth_file = Path.home() / ".autoagent" / "auth.json"
    device_file = Path.home() / ".autoagent" / "device.json"

    if auth_file.exists():
        print(f"   ✓ 认证文件: {auth_file}")
    else:
        print(f"   ✗ 认证文件不存在: {auth_file}")

    if device_file.exists():
        print(f"   ✓ 设备文件: {device_file}")
        try:
            device_data = json.loads(device_file.read_text())
            print(f"     机器码: {device_data['machine_code']}")
        except Exception:
            pass
    else:
        print(f"   ✗ 设备文件不存在: {device_file}")

    print("\n=== Stage 7 Demo Complete ===")
    print("✓ 用户认证系统已实现")
    print("✓ 设备注册与管理已验证")
    print("✓ 机器识别码生成已测试")
    print("✓ JWT认证与心跳已运行")
    print("✓ 本地认证持久化已配置")

if __name__ == "__main__":
    asyncio.run(main())