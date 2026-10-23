"""
聊天适配器接口 - 统一的多客户端聊天抽象
按照upgrade.md Sprint G规范实现
"""
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class MessageType(Enum):
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    AUDIO = "audio"
    VIDEO = "video"
    STICKER = "sticker"
    LOCATION = "location"
    CONTACT = "contact"
    SYSTEM = "system"


class MessageDirection(Enum):
    INCOMING = "incoming"
    OUTGOING = "outgoing"


class ChatStatus(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"
    BLOCKED = "blocked"


@dataclass
class ChatMessage:
    """聊天消息"""
    message_id: str
    chat_id: str
    sender_id: str
    sender_name: str
    content: str
    message_type: MessageType
    direction: MessageDirection
    timestamp: datetime
    reply_to: Optional[str] = None
    attachments: List[Dict] = None
    metadata: Dict = None


@dataclass
class ChatInfo:
    """聊天信息"""
    chat_id: str
    chat_name: str
    chat_type: str  # "private", "group", "channel"
    participant_count: int
    status: ChatStatus
    last_message: Optional[ChatMessage] = None
    unread_count: int = 0
    metadata: Dict = None


@dataclass
class ContactInfo:
    """联系人信息"""
    contact_id: str
    name: str
    username: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    avatar_url: Optional[str] = None
    status: str = "unknown"  # "online", "offline", "away", "busy"
    metadata: Dict = None


class ChatAdapter(ABC):
    """聊天适配器基类"""

    def __init__(self, adapter_id: str, config: Dict):
        self.adapter_id = adapter_id
        self.config = config
        self.is_connected = False
        self.message_handlers: List[Callable[[ChatMessage], None]] = []
        self.status_handlers: List[Callable[[str, bool], None]] = []

    @abstractmethod
    async def connect(self) -> bool:
        """连接到聊天服务"""
        pass

    @abstractmethod
    async def disconnect(self) -> bool:
        """断开连接"""
        pass

    @abstractmethod
    async def send_message(self, chat_id: str, content: str,
                          message_type: MessageType = MessageType.TEXT,
                          reply_to: str = None, **kwargs) -> str:
        """发送消息"""
        pass

    @abstractmethod
    async def get_chats(self, limit: int = 50, offset: int = 0) -> List[ChatInfo]:
        """获取聊天列表"""
        pass

    @abstractmethod
    async def get_messages(self, chat_id: str, limit: int = 50,
                          before_message_id: str = None) -> List[ChatMessage]:
        """获取消息历史"""
        pass

    @abstractmethod
    async def get_chat_info(self, chat_id: str) -> Optional[ChatInfo]:
        """获取聊天信息"""
        pass

    @abstractmethod
    async def get_contact_info(self, contact_id: str) -> Optional[ContactInfo]:
        """获取联系人信息"""
        pass

    @abstractmethod
    async def mark_as_read(self, chat_id: str, message_id: str = None) -> bool:
        """标记为已读"""
        pass

    @abstractmethod
    async def search_messages(self, query: str, chat_id: str = None,
                            limit: int = 20) -> List[ChatMessage]:
        """搜索消息"""
        pass

    @abstractmethod
    def get_capabilities(self) -> Dict[str, bool]:
        """获取适配器能力"""
        pass

    # 通用方法
    def add_message_handler(self, handler: Callable[[ChatMessage], None]):
        """添加消息处理器"""
        self.message_handlers.append(handler)

    def add_status_handler(self, handler: Callable[[str, bool], None]):
        """添加状态处理器"""
        self.status_handlers.append(handler)

    def _notify_message_handlers(self, message: ChatMessage):
        """通知消息处理器"""
        for handler in self.message_handlers:
            try:
                handler(message)
            except Exception as e:
                logger.error(f"Message handler error: {e}")

    def _notify_status_handlers(self, status: str, is_connected: bool):
        """通知状态处理器"""
        for handler in self.status_handlers:
            try:
                handler(status, is_connected)
            except Exception as e:
                logger.error(f"Status handler error: {e}")

    async def send_text(self, chat_id: str, text: str, reply_to: str = None) -> str:
        """发送文本消息的便捷方法"""
        return await self.send_message(chat_id, text, MessageType.TEXT, reply_to)

    async def send_image(self, chat_id: str, image_path: str, caption: str = "",
                        reply_to: str = None) -> str:
        """发送图片消息的便捷方法"""
        return await self.send_message(chat_id, caption, MessageType.IMAGE,
                                     reply_to, image_path=image_path)

    async def get_unread_messages(self, chat_id: str = None) -> List[ChatMessage]:
        """获取未读消息"""
        if chat_id:
            # 获取特定聊天的未读消息
            chat_info = await self.get_chat_info(chat_id)
            if chat_info and chat_info.unread_count > 0:
                messages = await self.get_messages(chat_id, limit=chat_info.unread_count)
                return [msg for msg in messages if msg.direction == MessageDirection.INCOMING]
        else:
            # 获取所有未读消息
            unread_messages = []
            chats = await self.get_chats()
            for chat in chats:
                if chat.unread_count > 0:
                    messages = await self.get_messages(chat.chat_id, limit=chat.unread_count)
                    unread_messages.extend([
                        msg for msg in messages
                        if msg.direction == MessageDirection.INCOMING
                    ])
            return unread_messages

        return []

    def is_capability_supported(self, capability: str) -> bool:
        """检查是否支持特定能力"""
        capabilities = self.get_capabilities()
        return capabilities.get(capability, False)

    def get_adapter_info(self) -> Dict:
        """获取适配器信息"""
        return {
            "adapter_id": self.adapter_id,
            "is_connected": self.is_connected,
            "capabilities": self.get_capabilities(),
            "config": {k: v for k, v in self.config.items() if k not in ['password', 'token', 'api_key']}
        }


class MockChatAdapter(ChatAdapter):
    """模拟聊天适配器 - 用于测试"""

    def __init__(self, adapter_id: str = "mock", config: Dict = None):
        super().__init__(adapter_id, config or {})
        self.mock_messages: List[ChatMessage] = []
        self.mock_chats: List[ChatInfo] = []

    async def connect(self) -> bool:
        """模拟连接"""
        self.is_connected = True
        self._notify_status_handlers("connected", True)
        return True

    async def disconnect(self) -> bool:
        """模拟断开连接"""
        self.is_connected = False
        self._notify_status_handlers("disconnected", False)
        return True

    async def send_message(self, chat_id: str, content: str,
                          message_type: MessageType = MessageType.TEXT,
                          reply_to: str = None, **kwargs) -> str:
        """模拟发送消息"""
        if not self.is_connected:
            raise Exception("Not connected")

        message_id = f"mock_msg_{len(self.mock_messages)}"
        message = ChatMessage(
            message_id=message_id,
            chat_id=chat_id,
            sender_id="self",
            sender_name="Self",
            content=content,
            message_type=message_type,
            direction=MessageDirection.OUTGOING,
            timestamp=datetime.now(),
            reply_to=reply_to
        )

        self.mock_messages.append(message)
        return message_id

    async def get_chats(self, limit: int = 50, offset: int = 0) -> List[ChatInfo]:
        """模拟获取聊天列表"""
        if not self.mock_chats:
            # 创建模拟聊天
            self.mock_chats = [
                ChatInfo(
                    chat_id="chat_1",
                    chat_name="Mock Chat 1",
                    chat_type="private",
                    participant_count=2,
                    status=ChatStatus.ACTIVE
                ),
                ChatInfo(
                    chat_id="chat_2",
                    chat_name="Mock Group Chat",
                    chat_type="group",
                    participant_count=5,
                    status=ChatStatus.ACTIVE
                )
            ]

        return self.mock_chats[offset:offset + limit]

    async def get_messages(self, chat_id: str, limit: int = 50,
                          before_message_id: str = None) -> List[ChatMessage]:
        """模拟获取消息历史"""
        chat_messages = [msg for msg in self.mock_messages if msg.chat_id == chat_id]
        return chat_messages[-limit:] if chat_messages else []

    async def get_chat_info(self, chat_id: str) -> Optional[ChatInfo]:
        """模拟获取聊天信息"""
        for chat in self.mock_chats:
            if chat.chat_id == chat_id:
                return chat
        return None

    async def get_contact_info(self, contact_id: str) -> Optional[ContactInfo]:
        """模拟获取联系人信息"""
        return ContactInfo(
            contact_id=contact_id,
            name=f"Mock Contact {contact_id}",
            username=f"user_{contact_id}",
            status="online"
        )

    async def mark_as_read(self, chat_id: str, message_id: str = None) -> bool:
        """模拟标记已读"""
        return True

    async def search_messages(self, query: str, chat_id: str = None,
                            limit: int = 20) -> List[ChatMessage]:
        """模拟搜索消息"""
        results = []
        for message in self.mock_messages:
            if chat_id and message.chat_id != chat_id:
                continue
            if query.lower() in message.content.lower():
                results.append(message)
                if len(results) >= limit:
                    break
        return results

    def get_capabilities(self) -> Dict[str, bool]:
        """模拟适配器能力"""
        return {
            "send_text": True,
            "send_image": True,
            "send_file": False,
            "receive_messages": True,
            "message_search": True,
            "mark_as_read": True,
            "typing_indicator": False,
            "message_reactions": False,
            "message_editing": False,
            "message_deletion": False,
            "group_management": False,
            "contact_management": True
        }

    def simulate_incoming_message(self, chat_id: str, sender_id: str,
                                 content: str, sender_name: str = None):
        """模拟接收消息"""
        message_id = f"incoming_{len(self.mock_messages)}"
        message = ChatMessage(
            message_id=message_id,
            chat_id=chat_id,
            sender_id=sender_id,
            sender_name=sender_name or f"User {sender_id}",
            content=content,
            message_type=MessageType.TEXT,
            direction=MessageDirection.INCOMING,
            timestamp=datetime.now()
        )

        self.mock_messages.append(message)
        self._notify_message_handlers(message)
        return message_id