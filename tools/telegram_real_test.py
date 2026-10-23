#!/usr/bin/env python3
"""
Telegram真实客户端集成测试工具
按照upgrade.md Sprint G要求实现
"""
import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.chat.telegram_real_adapter import TelegramRealAdapter, TelegramConfig, create_telegram_real_adapter
from core.chat.adapter_interface import MessageType

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TelegramRealTest:
    """Telegram真实集成测试类"""

    def __init__(self):
        self.adapter: Optional[TelegramRealAdapter] = None
        self.test_results = []

    def create_adapter_from_env(self) -> TelegramRealAdapter:
        """从环境变量创建Telegram适配器"""
        api_id = os.getenv("TELEGRAM_API_ID")
        api_hash = os.getenv("TELEGRAM_API_HASH")
        phone_number = os.getenv("TELEGRAM_PHONE_NUMBER")

        if not api_id or not api_hash:
            raise ValueError(
                "Missing Telegram credentials. Please set:\n"
                "TELEGRAM_API_ID=your_api_id\n"
                "TELEGRAM_API_HASH=your_api_hash\n"
                "TELEGRAM_PHONE_NUMBER=your_phone_number (optional)"
            )

        try:
            api_id = int(api_id)
        except ValueError:
            raise ValueError("TELEGRAM_API_ID must be an integer")

        return create_telegram_real_adapter(api_id, api_hash, phone_number)

    async def test_connection(self) -> bool:
        """测试连接"""
        logger.info("🔗 Testing Telegram connection...")

        try:
            self.adapter = self.create_adapter_from_env()
            connected = await self.adapter.connect()

            if connected:
                logger.info("✅ Connection test PASSED")
                self.test_results.append({
                    "test": "connection",
                    "status": "PASSED",
                    "timestamp": datetime.now().isoformat()
                })
                return True
            else:
                logger.error("❌ Connection test FAILED")
                self.test_results.append({
                    "test": "connection",
                    "status": "FAILED",
                    "timestamp": datetime.now().isoformat(),
                    "error": "Failed to connect"
                })
                return False

        except Exception as e:
            logger.error(f"❌ Connection test ERROR: {e}")
            self.test_results.append({
                "test": "connection",
                "status": "ERROR",
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            })
            return False

    async def test_get_chats(self) -> bool:
        """测试获取聊天列表"""
        logger.info("💬 Testing get chats...")

        try:
            chats = await self.adapter.get_chats()

            if chats:
                logger.info(f"✅ Get chats test PASSED ({len(chats)} chats found)")
                for i, chat in enumerate(chats[:3]):  # 显示前3个
                    logger.info(f"  {i+1}. {chat.name} ({chat.chat_type})")

                self.test_results.append({
                    "test": "get_chats",
                    "status": "PASSED",
                    "timestamp": datetime.now().isoformat(),
                    "chat_count": len(chats)
                })
                return True
            else:
                logger.warning("⚠️ Get chats test returned empty list")
                self.test_results.append({
                    "test": "get_chats",
                    "status": "WARNING",
                    "timestamp": datetime.now().isoformat(),
                    "chat_count": 0
                })
                return True  # 空列表也算正常

        except Exception as e:
            logger.error(f"❌ Get chats test ERROR: {e}")
            self.test_results.append({
                "test": "get_chats",
                "status": "ERROR",
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            })
            return False

    async def test_get_unread_messages(self) -> bool:
        """测试获取未读消息"""
        logger.info("📨 Testing get unread messages...")

        try:
            unread_messages = await self.adapter.get_unread_messages()

            logger.info(f"✅ Get unread messages test PASSED ({len(unread_messages)} unread)")

            if unread_messages:
                for i, msg in enumerate(unread_messages[:3]):  # 显示前3条
                    logger.info(f"  {i+1}. From {msg.sender_id}: {msg.content[:50]}...")

            self.test_results.append({
                "test": "get_unread_messages",
                "status": "PASSED",
                "timestamp": datetime.now().isoformat(),
                "unread_count": len(unread_messages)
            })
            return True

        except Exception as e:
            logger.error(f"❌ Get unread messages test ERROR: {e}")
            self.test_results.append({
                "test": "get_unread_messages",
                "status": "ERROR",
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            })
            return False

    async def test_send_message(self, test_chat_id: str = None) -> bool:
        """测试发送消息"""
        if not test_chat_id:
            logger.info("📤 Skipping send message test (no test_chat_id provided)")
            return True

        logger.info(f"📤 Testing send message to {test_chat_id}...")

        try:
            test_content = f"Test message from M3 Vision-First Engine at {datetime.now().strftime('%H:%M:%S')}"

            message_id = await self.adapter.send_message(
                test_chat_id,
                test_content,
                MessageType.TEXT
            )

            if message_id:
                logger.info(f"✅ Send message test PASSED (message_id: {message_id})")
                self.test_results.append({
                    "test": "send_message",
                    "status": "PASSED",
                    "timestamp": datetime.now().isoformat(),
                    "message_id": message_id,
                    "chat_id": test_chat_id
                })
                return True
            else:
                logger.error("❌ Send message test FAILED (no message_id returned)")
                self.test_results.append({
                    "test": "send_message",
                    "status": "FAILED",
                    "timestamp": datetime.now().isoformat(),
                    "error": "No message_id returned"
                })
                return False

        except Exception as e:
            logger.error(f"❌ Send message test ERROR: {e}")
            self.test_results.append({
                "test": "send_message",
                "status": "ERROR",
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            })
            return False

    async def test_capabilities(self) -> bool:
        """测试能力查询"""
        logger.info("🛠️ Testing capabilities...")

        try:
            capabilities = self.adapter.get_capabilities()

            logger.info("✅ Capabilities test PASSED")
            for capability, available in capabilities.items():
                status = "✅" if available else "❌"
                logger.info(f"  {status} {capability}")

            self.test_results.append({
                "test": "capabilities",
                "status": "PASSED",
                "timestamp": datetime.now().isoformat(),
                "capabilities": capabilities
            })
            return True

        except Exception as e:
            logger.error(f"❌ Capabilities test ERROR: {e}")
            self.test_results.append({
                "test": "capabilities",
                "status": "ERROR",
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            })
            return False

    async def test_message_search(self, query: str = "test") -> bool:
        """测试消息搜索"""
        logger.info(f"🔍 Testing message search with query: '{query}'...")

        try:
            messages = await self.adapter.search_messages(query, limit=10)

            logger.info(f"✅ Message search test PASSED ({len(messages)} results)")

            if messages:
                for i, msg in enumerate(messages[:3]):  # 显示前3条
                    logger.info(f"  {i+1}. {msg.content[:50]}...")

            self.test_results.append({
                "test": "message_search",
                "status": "PASSED",
                "timestamp": datetime.now().isoformat(),
                "query": query,
                "result_count": len(messages)
            })
            return True

        except Exception as e:
            logger.error(f"❌ Message search test ERROR: {e}")
            self.test_results.append({
                "test": "message_search",
                "status": "ERROR",
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            })
            return False

    async def run_all_tests(self, test_chat_id: str = None) -> dict:
        """运行所有测试"""
        logger.info("🚀 Starting Telegram Real Integration Tests")
        logger.info("=" * 60)

        start_time = datetime.now()
        all_passed = True

        # 运行测试
        tests = [
            self.test_connection(),
            self.test_capabilities(),
            self.test_get_chats(),
            self.test_get_unread_messages(),
            self.test_message_search(),
            self.test_send_message(test_chat_id)
        ]

        for test in tests:
            if not await test:
                all_passed = False

        # 断开连接
        if self.adapter:
            await self.adapter.disconnect()

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        # 汇总结果
        passed_count = len([r for r in self.test_results if r["status"] == "PASSED"])
        failed_count = len([r for r in self.test_results if r["status"] == "FAILED"])
        error_count = len([r for r in self.test_results if r["status"] == "ERROR"])

        summary = {
            "overall_result": "PASSED" if all_passed else "FAILED",
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_seconds": duration,
            "test_count": len(self.test_results),
            "passed": passed_count,
            "failed": failed_count,
            "errors": error_count,
            "test_results": self.test_results
        }

        logger.info("=" * 60)
        logger.info(f"🏁 Test Summary: {summary['overall_result']}")
        logger.info(f"   Duration: {duration:.2f}s")
        logger.info(f"   Tests: {len(self.test_results)} total")
        logger.info(f"   ✅ Passed: {passed_count}")
        logger.info(f"   ❌ Failed: {failed_count}")
        logger.info(f"   💥 Errors: {error_count}")

        return summary

    def print_env_setup_help(self):
        """打印环境设置帮助"""
        print("""
🔧 Telegram Real Integration Setup:

1. Get Telegram API credentials:
   - Go to https://my.telegram.org/auth
   - Login with your phone number
   - Go to 'API development tools'
   - Create a new application
   - Note down 'App api_id' and 'App api_hash'

2. Set environment variables:
   export TELEGRAM_API_ID=your_api_id
   export TELEGRAM_API_HASH=your_api_hash
   export TELEGRAM_PHONE_NUMBER=your_phone_number  # optional

3. Install dependencies:
   pip install telethon

4. Run tests:
   python tools/telegram_real_test.py
   python tools/telegram_real_test.py --send-test chat_id_or_username
        """)


async def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="Telegram Real Integration Test Tool")
    parser.add_argument("--send-test", help="Test chat ID for send message test")
    parser.add_argument("--setup-help", action="store_true", help="Show setup instructions")
    args = parser.parse_args()

    if args.setup_help:
        TelegramRealTest().print_env_setup_help()
        return

    test_tool = TelegramRealTest()

    try:
        summary = await test_tool.run_all_tests(args.send_test)

        # 保存结果到文件
        import json
        output_file = Path("out/telegram_test_results.json")
        output_file.parent.mkdir(exist_ok=True)
        with open(output_file, "w") as f:
            json.dump(summary, f, indent=2)

        logger.info(f"📄 Test results saved to: {output_file}")

        # 退出码
        sys.exit(0 if summary["overall_result"] == "PASSED" else 1)

    except Exception as e:
        logger.error(f"💥 Test execution failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())