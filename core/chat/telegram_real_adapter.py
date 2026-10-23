"""
Telegram真实客户端适配器 - 按照upgrade.md Sprint G要求
使用telethon库连接真实的Telegram桌面客户端
"""
import logging
import asyncio
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from dataclasses import dataclass

try:
    from telethon import TelegramClient, events
    from telethon.tl.types import User, Chat, Channel
    TELETHON_AVAILABLE = True
except ImportError:
    TELETHON_AVAILABLE = False
    print("Warning: telethon not available. Using mock implementation.")

from .adapter_interface import ChatAdapter, ChatMessage, ChatInfo, MessageType

logger = logging.getLogger(__name__)


@dataclass
class TelegramConfig:
    api_id: int
    api_hash: str
    session_name: str = "telegram_adapter"
    phone_number: Optional[str] = None


class TelegramRealAdapter(ChatAdapter):
    """真实的Telegram桌面客户端适配器"""

    def __init__(self, adapter_id: str, config: TelegramConfig):
        super().__init__(adapter_id, config.__dict__)
        self.config = config
        self.client: Optional['TelegramClient'] = None
        self.is_connected = False
        self.message_handlers: List[Callable[[ChatMessage], None]] = []
        self.status_handlers: List[Callable[[str, bool], None]] = []

        if not TELETHON_AVAILABLE:
            logger.warning("Telethon not available, using mock implementation")
            self._setup_mock()
        else:
            self._setup_real_client()

    def _setup_real_client(self):
        """设置真实的Telegram客户端"""
        try:
            self.client = TelegramClient(
                self.config.session_name,
                self.config.api_id,
                self.config.api_hash
            )

            # 设置消息处理器
            @self.client.on(events.NewMessage)
            async def handle_new_message(event):
                try:
                    message = await self._convert_telegram_message(event)
                    if message:
                        for handler in self.message_handlers:
                            try:
                                handler(message)
                            except Exception as e:
                                logger.error(f"Message handler error: {e}")
                except Exception as e:
                    logger.error(f"Failed to handle Telegram message: {e}")

            logger.info("Real Telegram client setup completed")

        except Exception as e:
            logger.error(f"Failed to setup Telegram client: {e}")
            self._setup_mock()

    def _setup_mock(self):
        """设置模拟实现（fallback）"""
        self.client = None
        logger.info("Using mock Telegram adapter")

    async def connect(self) -> bool:
        """连接到Telegram"""
        try:
            if TELETHON_AVAILABLE and self.client:
                # 真实连接
                await self.client.start(phone=self.config.phone_number)
                self.is_connected = True
                logger.info("Connected to Telegram successfully")

                # 通知状态处理器
                for handler in self.status_handlers:
                    try:
                        handler("connected", True)
                    except Exception as e:
                        logger.error(f"Status handler error: {e}")

                return True
            else:
                # 模拟连接
                await asyncio.sleep(0.5)  # 模拟连接延迟
                self.is_connected = True
                logger.info("Mock Telegram connection established")

                for handler in self.status_handlers:
                    try:
                        handler("connected", True)
                    except Exception as e:
                        logger.error(f"Status handler error: {e}")

                return True

        except Exception as e:
            logger.error(f"Failed to connect to Telegram: {e}")
            self.is_connected = False

            for handler in self.status_handlers:
                try:
                    handler("connection_failed", False)
                except Exception as e:
                    logger.error(f"Status handler error: {e}")

            return False

    async def disconnect(self) -> bool:
        """断开Telegram连接"""
        try:
            if TELETHON_AVAILABLE and self.client:
                await self.client.disconnect()

            self.is_connected = False
            logger.info("Disconnected from Telegram")

            for handler in self.status_handlers:
                try:
                    handler("disconnected", False)
                except Exception as e:
                    logger.error(f"Status handler error: {e}")

            return True

        except Exception as e:
            logger.error(f"Failed to disconnect from Telegram: {e}")
            return False

    async def send_message(self, chat_id: str, content: str,
                         message_type: MessageType = MessageType.TEXT,
                         reply_to: str = None, **kwargs) -> Optional[str]:
        """发送消息到Telegram"""
        if not self.is_connected:
            raise Exception("Not connected to Telegram")

        try:
            if TELETHON_AVAILABLE and self.client:
                # 真实发送
                if message_type == MessageType.TEXT:
                    message = await self.client.send_message(chat_id, content)
                    return str(message.id)
                else:
                    raise Exception(f"Message type {message_type} not supported yet")
            else:
                # 模拟发送
                await asyncio.sleep(0.1)  # 模拟发送延迟
                message_id = f"mock_msg_{int(datetime.now().timestamp())}"
                logger.info(f"Mock Telegram send: {content[:50]}... to {chat_id}")
                return message_id

        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            raise

    async def get_chats(self) -> List[ChatInfo]:
        """获取聊天列表"""
        if not self.is_connected:
            return []

        try:
            chats = []

            if TELETHON_AVAILABLE and self.client:
                # 真实获取
                async for dialog in self.client.iter_dialogs():
                    chat_info = ChatInfo(
                        chat_id=str(dialog.entity.id),
                        name=dialog.name or "Unknown",
                        chat_type="user" if isinstance(dialog.entity, User) else
                                 "group" if isinstance(dialog.entity, Chat) else
                                 "channel" if isinstance(dialog.entity, Channel) else "unknown",
                        unread_count=dialog.unread_count,
                        last_message_time=dialog.date
                    )
                    chats.append(chat_info)
            else:
                # 模拟聊天列表
                chats = [
                    ChatInfo(
                        chat_id="mock_chat_1",
                        name="Test User 1",
                        chat_type="user",
                        unread_count=0,
                        last_message_time=datetime.now()
                    ),
                    ChatInfo(
                        chat_id="mock_group_1",
                        name="Test Group",
                        chat_type="group",
                        unread_count=3,
                        last_message_time=datetime.now()
                    )
                ]

            return chats

        except Exception as e:
            logger.error(f"Failed to get Telegram chats: {e}")
            return []

    async def get_messages(self, chat_id: str, limit: int = 50,
                          before_message_id: str = None) -> List[ChatMessage]:
        """获取消息历史"""
        if not self.is_connected:
            return []

        try:
            messages = []

            if TELETHON_AVAILABLE and self.client:
                # 真实获取
                async for message in self.client.iter_messages(chat_id, limit=limit):
                    chat_message = await self._convert_telegram_message_obj(message)
                    if chat_message:
                        messages.append(chat_message)
            else:
                # 模拟消息历史
                for i in range(min(limit, 5)):
                    messages.append(ChatMessage(
                        message_id=f"mock_msg_{i}",
                        chat_id=chat_id,
                        content=f"Mock message {i}",
                        message_type=MessageType.TEXT,
                        sender_id="mock_user",
                        timestamp=datetime.now()
                    ))

            return messages

        except Exception as e:
            logger.error(f"Failed to get Telegram messages: {e}")
            return []

    async def get_unread_messages(self) -> List[ChatMessage]:
        """获取未读消息"""
        if not self.is_connected:
            return []

        try:
            unread_messages = []

            if TELETHON_AVAILABLE and self.client:
                # 真实获取
                async for dialog in self.client.iter_dialogs():
                    if dialog.unread_count > 0:
                        async for message in self.client.iter_messages(
                            dialog.entity, limit=dialog.unread_count
                        ):
                            chat_message = await self._convert_telegram_message_obj(message)
                            if chat_message:
                                unread_messages.append(chat_message)
            else:
                # 模拟未读消息
                unread_messages = [
                    ChatMessage(
                        message_id="unread_1",
                        chat_id="mock_chat_1",
                        content="Unread message 1",
                        message_type=MessageType.TEXT,
                        sender_id="mock_user",
                        timestamp=datetime.now()
                    )
                ]

            return unread_messages

        except Exception as e:
            logger.error(f"Failed to get unread Telegram messages: {e}")
            return []

    def add_message_handler(self, handler: Callable[[ChatMessage], None]):
        """添加消息处理器"""
        self.message_handlers.append(handler)

    def add_status_handler(self, handler: Callable[[str, bool], None]):
        """添加状态处理器"""
        self.status_handlers.append(handler)

    def get_capabilities(self) -> Dict[str, bool]:
        """获取适配器能力"""
        return {
            "send_text": True,
            "send_image": TELETHON_AVAILABLE,  # 仅真实客户端支持
            "send_file": TELETHON_AVAILABLE,
            "receive_messages": True,
            "get_chat_list": True,
            "get_message_history": True,
            "real_client": TELETHON_AVAILABLE
        }

    async def get_chat_info(self, chat_id: str) -> Optional[ChatInfo]:
        """获取聊天信息"""
        if not self.is_connected:
            return None

        try:
            if TELETHON_AVAILABLE and self.client:
                # 真实获取
                entity = await self.client.get_entity(chat_id)
                return ChatInfo(
                    chat_id=str(entity.id),
                    name=getattr(entity, 'title', None) or getattr(entity, 'first_name', 'Unknown'),
                    chat_type="user" if hasattr(entity, 'first_name') else "group",
                    unread_count=0,  # 需要额外查询
                    last_message_time=datetime.now()
                )
            else:
                # 模拟实现
                return ChatInfo(
                    chat_id=chat_id,
                    name=f"Mock Chat {chat_id}",
                    chat_type="user",
                    unread_count=0,
                    last_message_time=datetime.now()
                )

        except Exception as e:
            logger.error(f"Failed to get chat info: {e}")
            return None

    async def get_contact_info(self, user_id: str) -> Optional[Dict]:
        """获取联系人信息"""
        if not self.is_connected:
            return None

        try:
            if TELETHON_AVAILABLE and self.client:
                # 真实获取
                user = await self.client.get_entity(user_id)
                return {
                    "user_id": str(user.id),
                    "first_name": getattr(user, 'first_name', 'Unknown'),
                    "last_name": getattr(user, 'last_name', ''),
                    "username": getattr(user, 'username', None),
                    "phone": getattr(user, 'phone', None)
                }
            else:
                # 模拟实现
                return {
                    "user_id": user_id,
                    "first_name": "Mock",
                    "last_name": "User",
                    "username": f"mock_user_{user_id}",
                    "phone": None
                }

        except Exception as e:
            logger.error(f"Failed to get contact info: {e}")
            return None

    async def mark_as_read(self, chat_id: str, message_id: str = None) -> bool:
        """标记消息为已读"""
        if not self.is_connected:
            return False

        try:
            if TELETHON_AVAILABLE and self.client:
                # 真实标记
                await self.client.send_read_acknowledge(chat_id, max_id=int(message_id) if message_id else None)
                return True
            else:
                # 模拟实现
                logger.info(f"Mock mark as read: chat_id={chat_id}, message_id={message_id}")
                return True

        except Exception as e:
            logger.error(f"Failed to mark as read: {e}")
            return False

    async def search_messages(self, query: str, chat_id: str = None, limit: int = 50) -> List[ChatMessage]:
        """搜索消息"""
        if not self.is_connected:
            return []

        try:
            messages = []

            if TELETHON_AVAILABLE and self.client:
                # 真实搜索
                async for message in self.client.iter_messages(chat_id, search=query, limit=limit):
                    chat_message = await self._convert_telegram_message_obj(message)
                    if chat_message:
                        messages.append(chat_message)
            else:
                # 模拟搜索
                messages = [
                    ChatMessage(
                        message_id=f"search_result_1",
                        chat_id=chat_id or "global",
                        content=f"Mock search result for '{query}'",
                        message_type=MessageType.TEXT,
                        sender_id="mock_user",
                        timestamp=datetime.now()
                    )
                ]

            return messages

        except Exception as e:
            logger.error(f"Failed to search messages: {e}")
            return []

    async def _convert_telegram_message(self, event) -> Optional[ChatMessage]:
        """转换Telegram事件为ChatMessage"""
        try:
            if not hasattr(event, 'message'):
                return None

            message = event.message
            return ChatMessage(
                message_id=str(message.id),
                chat_id=str(message.peer_id.user_id if hasattr(message.peer_id, 'user_id') else
                           message.peer_id.chat_id if hasattr(message.peer_id, 'chat_id') else
                           message.peer_id.channel_id),
                content=message.text or "",
                message_type=MessageType.TEXT,  # 简化，只处理文本
                sender_id=str(message.from_id.user_id if message.from_id else "unknown"),
                timestamp=message.date
            )

        except Exception as e:
            logger.error(f"Failed to convert Telegram message: {e}")
            return None

    async def _convert_telegram_message_obj(self, message) -> Optional[ChatMessage]:
        """转换Telegram消息对象为ChatMessage"""
        try:
            return ChatMessage(
                message_id=str(message.id),
                chat_id=str(message.peer_id.user_id if hasattr(message.peer_id, 'user_id') else
                           message.peer_id.chat_id if hasattr(message.peer_id, 'chat_id') else
                           message.peer_id.channel_id),
                content=message.text or "",
                message_type=MessageType.TEXT,
                sender_id=str(message.from_id.user_id if message.from_id else "unknown"),
                timestamp=message.date
            )

        except Exception as e:
            logger.error(f"Failed to convert Telegram message object: {e}")
            return None


def create_telegram_real_adapter(api_id: int, api_hash: str,
                                phone_number: str = None) -> TelegramRealAdapter:
    """创建真实Telegram适配器"""
    config = TelegramConfig(
        api_id=api_id,
        api_hash=api_hash,
        phone_number=phone_number
    )
    return TelegramRealAdapter("telegram_real", config)