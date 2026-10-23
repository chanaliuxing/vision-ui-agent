"""
Web回放UI应用 - 集成Sprint F的Web回放功能
"""
import asyncio
import logging
from pathlib import Path
from core.observability.run_events import RunEventRecorder
from core.observability.web_replay_ui import create_replay_ui

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """启动Web回放UI服务器"""
    # 创建事件记录器
    event_recorder = RunEventRecorder()

    # 创建回放UI服务器
    replay_server = create_replay_ui(event_recorder, port=8890)

    print("🎬 Starting Web Replay UI Server...")
    print("   URL: http://localhost:8890")
    print("   按Ctrl+C停止服务器")

    try:
        # 同步启动服务器
        replay_server.start_sync()
    except KeyboardInterrupt:
        print("\n👋 服务器已停止")


async def main_async():
    """异步启动Web回放UI服务器"""
    # 创建事件记录器
    event_recorder = RunEventRecorder()

    # 创建回放UI服务器
    replay_server = create_replay_ui(event_recorder, port=8890)

    print("🎬 Starting Web Replay UI Server (async)...")
    print("   URL: http://localhost:8890")
    print("   按Ctrl+C停止服务器")

    try:
        await replay_server.start()
    except KeyboardInterrupt:
        print("\n👋 服务器已停止")


if __name__ == "__main__":
    import sys

    if "--async" in sys.argv:
        asyncio.run(main_async())
    else:
        main()