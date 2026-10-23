"""
Telegram服务 - 集成真实Telegram客户端到聊天系统
按照upgrade.md Sprint G要求实现
"""
import asyncio
import logging
from typing import Dict, List, Optional, Callable
from datetime import datetime
from dataclasses import dataclass

from .telegram_real_adapter import TelegramRealAdapter, create_telegram_real_adapter
from .adapter_interface import ChatMessage, MessageType
from .chat_manager import ChatManager

logger = logging.getLogger(__name__)


@dataclass
class TelegramServiceConfig:
    """Telegram服务配置"""
    api_id: int
    api_hash: str
    phone_number: Optional[str] = None
    auto_reply_enabled: bool = True
    message_processing_enabled: bool = True
    unread_check_interval: int = 30  # 秒


class TelegramMessageProcessor:
    """Telegram消息处理器"""

    def __init__(self, service: 'TelegramService'):
        self.service = service
        self.processing_rules = []
        self.auto_responses = {
            "greeting": ["hi", "hello", "你好", "您好"],
            "help": ["help", "帮助", "?", "？"],
            "status": ["status", "状态", "info"]
        }

    def add_processing_rule(self, rule: Callable[[ChatMessage], bool],
                          action: Callable[[ChatMessage], None]):
        """添加消息处理规则"""
        self.processing_rules.append((rule, action))

    async def process_message(self, message: ChatMessage):
        """处理接收到的消息"""
        try:
            logger.info(f"Processing message from {message.sender_id}: {message.content[:50]}...")

            # 应用处理规则
            for rule, action in self.processing_rules:
                try:
                    if rule(message):
                        await action(message)
                except Exception as e:
                    logger.error(f"Processing rule error: {e}")

            # 自动回复
            if self.service.config.auto_reply_enabled:
                await self._handle_auto_reply(message)

        except Exception as e:
            logger.error(f"Message processing error: {e}")

    async def _handle_auto_reply(self, message: ChatMessage):
        """处理自动回复"""
        content_lower = message.content.lower()

        # 检查是否需要自动回复
        reply_text = None

        for response_type, keywords in self.auto_responses.items():
            if any(keyword in content_lower for keyword in keywords):
                if response_type == "greeting":
                    reply_text = "Hello! I'm M3 Vision-First Engine bot. How can I help you?"
                elif response_type == "help":
                    reply_text = "Available commands:\n- status: Show system status\n- help: Show this help"
                elif response_type == "status":
                    reply_text = f"System status: Online\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                break

        if reply_text:
            try:
                await self.service.send_message(message.chat_id, reply_text)
                logger.info(f"Auto-replied to {message.sender_id}")
            except Exception as e:
                logger.error(f"Auto-reply error: {e}")


class TelegramService:
    """Telegram服务主类"""

    def __init__(self, config: TelegramServiceConfig, chat_manager: ChatManager):
        self.config = config
        self.chat_manager = chat_manager
        self.adapter: Optional[TelegramRealAdapter] = None
        self.processor = TelegramMessageProcessor(self)
        self.is_running = False
        self.background_tasks = []

        # 统计
        self.stats = {
            "messages_received": 0,
            "messages_sent": 0,
            "auto_replies_sent": 0,
            "connection_errors": 0,
            "last_activity": None
        }

    async def start(self) -> bool:
        """启动Telegram服务"""
        try:
            logger.info("Starting Telegram service...")

            # 创建适配器
            self.adapter = create_telegram_real_adapter(
                self.config.api_id,
                self.config.api_hash,
                self.config.phone_number
            )

            # 设置消息处理器
            self.adapter.add_message_handler(self._on_message_received)
            self.adapter.add_status_handler(self._on_status_change)

            # 连接
            if not await self.adapter.connect():
                raise Exception("Failed to connect to Telegram")

            # 注册到聊天管理器
            self.chat_manager.register_adapter(self.adapter)

            # 启动后台任务
            self.is_running = True
            self._start_background_tasks()

            logger.info("Telegram service started successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to start Telegram service: {e}")
            return False

    async def stop(self):
        """停止Telegram服务"""
        try:
            logger.info("Stopping Telegram service...")

            self.is_running = False

            # 停止后台任务
            for task in self.background_tasks:
                task.cancel()

            await asyncio.gather(*self.background_tasks, return_exceptions=True)
            self.background_tasks.clear()

            # 断开连接
            if self.adapter:
                await self.adapter.disconnect()
                self.chat_manager.unregister_adapter(self.adapter.adapter_id)

            logger.info("Telegram service stopped")

        except Exception as e:
            logger.error(f"Error stopping Telegram service: {e}")

    def _start_background_tasks(self):
        """启动后台任务"""
        # 未读消息检查任务
        if self.config.unread_check_interval > 0:
            task = asyncio.create_task(self._unread_check_loop())
            self.background_tasks.append(task)

        # 状态监控任务
        task = asyncio.create_task(self._status_monitor_loop())
        self.background_tasks.append(task)

    async def _unread_check_loop(self):
        """未读消息检查循环"""
        while self.is_running:
            try:
                if self.adapter:
                    unread_messages = await self.adapter.get_unread_messages()

                    for message in unread_messages:
                        await self.processor.process_message(message)
                        # 标记为已读
                        await self.adapter.mark_as_read(message.chat_id, message.message_id)

                await asyncio.sleep(self.config.unread_check_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Unread check error: {e}")
                await asyncio.sleep(10)  # 错误时等待更长时间

    async def _status_monitor_loop(self):
        """状态监控循环"""
        while self.is_running:
            try:
                # 更新统计信息
                self.stats["last_activity"] = datetime.now().isoformat()

                # 检查连接状态
                if self.adapter and not self.adapter.is_connected:
                    logger.warning("Telegram connection lost, attempting to reconnect...")
                    if await self.adapter.connect():
                        logger.info("Telegram reconnection successful")
                    else:
                        self.stats["connection_errors"] += 1

                await asyncio.sleep(60)  # 每分钟检查一次

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Status monitor error: {e}")
                await asyncio.sleep(30)

    def _on_message_received(self, message: ChatMessage):
        """消息接收回调"""
        try:
            self.stats["messages_received"] += 1

            # 异步处理消息
            if self.config.message_processing_enabled:
                asyncio.create_task(self.processor.process_message(message))

        except Exception as e:
            logger.error(f"Message receive callback error: {e}")

    def _on_status_change(self, status: str, connected: bool):
        """状态变化回调"""
        logger.info(f"Telegram status changed: {status} (connected: {connected})")

        if not connected:
            self.stats["connection_errors"] += 1

    async def send_message(self, chat_id: str, content: str,
                          message_type: MessageType = MessageType.TEXT) -> Optional[str]:
        """发送消息"""
        try:
            if not self.adapter or not self.adapter.is_connected:
                raise Exception("Telegram adapter not connected")

            message_id = await self.adapter.send_message(chat_id, content, message_type)

            if message_id:
                self.stats["messages_sent"] += 1

            return message_id

        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            raise

    async def send_auto_reply(self, chat_id: str, content: str) -> Optional[str]:
        """发送自动回复"""
        try:
            message_id = await self.send_message(chat_id, content)

            if message_id:
                self.stats["auto_replies_sent"] += 1

            return message_id

        except Exception as e:
            logger.error(f"Failed to send auto reply: {e}")
            return None

    async def get_chats(self):
        """获取聊天列表"""
        if not self.adapter:
            return []

        return await self.adapter.get_chats()

    async def search_messages(self, query: str, chat_id: str = None, limit: int = 50):
        """搜索消息"""
        if not self.adapter:
            return []

        return await self.adapter.search_messages(query, chat_id, limit)

    def get_stats(self) -> Dict:
        """获取服务统计"""
        return {
            "service": "telegram",
            "status": "running" if self.is_running else "stopped",
            "connected": self.adapter.is_connected if self.adapter else False,
            "config": {
                "auto_reply_enabled": self.config.auto_reply_enabled,
                "message_processing_enabled": self.config.message_processing_enabled,
                "unread_check_interval": self.config.unread_check_interval
            },
            "stats": self.stats.copy(),
            "capabilities": self.adapter.get_capabilities() if self.adapter else {}
        }

    def add_message_rule(self, rule: Callable[[ChatMessage], bool],
                        action: Callable[[ChatMessage], None]):
        """添加消息处理规则"""
        self.processor.add_processing_rule(rule, action)


def create_telegram_service_from_env(chat_manager: ChatManager) -> TelegramService:
    """从环境变量创建Telegram服务"""
    import os

    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    phone_number = os.getenv("TELEGRAM_PHONE_NUMBER")

    if not api_id or not api_hash:
        raise ValueError("Missing TELEGRAM_API_ID or TELEGRAM_API_HASH environment variables")

    try:
        api_id = int(api_id)
    except ValueError:
        raise ValueError("TELEGRAM_API_ID must be an integer")

    config = TelegramServiceConfig(
        api_id=api_id,
        api_hash=api_hash,
        phone_number=phone_number,
        auto_reply_enabled=os.getenv("TELEGRAM_AUTO_REPLY", "true").lower() == "true",
        message_processing_enabled=os.getenv("TELEGRAM_MESSAGE_PROCESSING", "true").lower() == "true",
        unread_check_interval=int(os.getenv("TELEGRAM_UNREAD_CHECK_INTERVAL", "30"))
    )

    return TelegramService(config, chat_manager)


async def test_telegram_service():
    """测试Telegram服务"""
    from .chat_manager import ChatManager

    # 创建聊天管理器
    chat_manager = ChatManager()

    try:
        # 创建Telegram服务
        service = create_telegram_service_from_env(chat_manager)

        # 启动服务
        if await service.start():
            logger.info("Telegram service test: START - PASSED")

            # 测试获取聊天列表
            chats = await service.get_chats()
            logger.info(f"Chats retrieved: {len(chats)}")

            # 测试搜索
            messages = await service.search_messages("test", limit=5)
            logger.info(f"Search results: {len(messages)}")

            # 获取统计
            stats = service.get_stats()
            logger.info(f"Service stats: {stats}")

            # 停止服务
            await service.stop()
            logger.info("Telegram service test: STOP - PASSED")

            return True

        else:
            logger.error("Telegram service test: START - FAILED")
            return False

    except Exception as e:
        logger.error(f"Telegram service test ERROR: {e}")
        return False


if __name__ == "__main__":
    # 运行测试
    asyncio.run(test_telegram_service())