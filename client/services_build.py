# client/services_build.py
import os
import sys
import threading
import time
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from client.services_sqs import build_services_sqs
from client.api_client import APIClient
from client.machine_code import get_machine_code
from client.login_ui import login_and_save

def build_services(api_base, dom, osmod, vision, logger, device_name="My Device", apps=None):
    """统一构建Services，包含登录、设备注册、心跳等功能"""

    # 初始化API客户端
    api = APIClient(api_base)
    token = api._load_token()

    # 如果没有token，进行登录
    if not token:
        print("No authentication token found. Please login.")
        token = login_and_save(api_base)
        if not token:
            raise Exception("Authentication failed")
        api.set_token(token)
    else:
        api.set_token(token)

    # 获取机器码并注册设备
    machine_code = get_machine_code()
    capabilities = {
        "apps": apps or ["wechat"],
        "ocr": "tesseract",
        "os": os.name,
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}"
    }

    try:
        reg = api.register_device(machine_code, device_name, capabilities)
        device_id = reg["device_id"]

        if reg.get("reused"):
            print(f"Device reused: {device_id}")
        else:
            print(f"Device registered: {device_id}")

    except Exception as e:
        print(f"Device registration failed: {e}")
        raise

    # 构建SQS services，使用device_id
    services = build_services_sqs(dom, osmod, vision, logger, device_id=device_id)

    # 添加API客户端和设备信息到services
    services.api = api
    services.device_id = device_id
    services.machine_code = machine_code

    # 启动心跳后台线程
    def _heartbeat_loop():
        while True:
            try:
                api.heartbeat(device_id)
            except Exception:
                # 心跳失败不影响主流程
                pass
            time.sleep(30)  # 每30秒发送一次心跳

    heartbeat_thread = threading.Thread(target=_heartbeat_loop, daemon=True)
    heartbeat_thread.start()

    return services