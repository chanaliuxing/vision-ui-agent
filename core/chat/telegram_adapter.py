"""
Telegram适配器 - 支持Telegram Desktop客户端
按照upgrade.md Sprint G规范实现
"""
import logging
import asyncio
import json
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

from .adapter_interface import (
    ChatAdapter, ChatMessage, ChatInfo, ContactInfo,
    MessageType, MessageDirection, ChatStatus
)

logger = logging.getLogger(__name__)


class TelegramAdapter(ChatAdapter):
    """Telegram桌面客户端适配器"""

    def __init__(self, adapter_id: str = "telegram", config: Dict = None):
        super().__init__(adapter_id, config or {})

        # Telegram配置
        self.api_id = config.get("api_id")
        self.api_hash = config.get("api_hash")
        self.phone_number = config.get("phone_number")
        self.session_file = config.get("session_file", "telegram_session")

        # 内部状态
        self.client = None
        self.me = None
        self.message_offset = 0

        # 消息缓存
        self.message_cache: Dict[str, List[ChatMessage]] = {}
        self.chat_cache: Dict[str, ChatInfo] = {}

    async def connect(self) -> bool:
        """连接到Telegram"""
        try:
            # 注意：这里使用模拟实现，实际需要telethon库
            # from telethon import TelegramClient
            # self.client = TelegramClient(self.session_file, self.api_id, self.api_hash)

            # 模拟连接过程
            await asyncio.sleep(0.1)  # 模拟连接延迟

            if not self._validate_config():
                logger.error("Invalid Telegram configuration")
                return False

            # 模拟获取自己的信息
            self.me = {
                "id": "self",
                "first_name": "Bot",
                "username": "automation_bot"
            }

            self.is_connected = True
            self._notify_status_handlers("connected", True)

            # 启动消息监听
            asyncio.create_task(self._message_listener())

            logger.info("Connected to Telegram")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to Telegram: {e}")
            return False

    async def disconnect(self) -> bool:
        """断开Telegram连接"""
        try:
            if self.client:
                # await self.client.disconnect()
                pass

            self.is_connected = False
            self.client = None
            self.me = None

            self._notify_status_handlers("disconnected", False)
            logger.info("Disconnected from Telegram")
            return True

        except Exception as e:
            logger.error(f"Failed to disconnect from Telegram: {e}")
            return False

    async def send_message(self, chat_id: str, content: str,
                          message_type: MessageType = MessageType.TEXT,
                          reply_to: str = None, **kwargs) -> str:
        """发送Telegram消息"""
        if not self.is_connected:
            raise Exception("Not connected to Telegram")

        try:
            # 实际实现会使用：
            # message = await self.client.send_message(chat_id, content, reply_to=reply_to)

            # 模拟发送
            message_id = f"tg_msg_{datetime.now().timestamp()}"

            # 创建消息对象
            message = ChatMessage(
                message_id=message_id,
                chat_id=chat_id,
                sender_id=self.me["id"],
                sender_name=self.me["first_name"],
                content=content,
                message_type=message_type,
                direction=MessageDirection.OUTGOING,
                timestamp=datetime.now(),
                reply_to=reply_to
            )

            # 添加到缓存
            if chat_id not in self.message_cache:
                self.message_cache[chat_id] = []
            self.message_cache[chat_id].append(message)

            logger.info(f"Sent Telegram message to {chat_id}: {content[:50]}")
            return message_id

        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            raise

    async def get_chats(self, limit: int = 50, offset: int = 0) -> List[ChatInfo]:
        """获取Telegram聊天列表"""
        if not self.is_connected:
            raise Exception("Not connected to Telegram")

        try:
            # 实际实现会使用：
            # dialogs = await self.client.get_dialogs(limit=limit, offset=offset)

            # 模拟聊天列表
            if not self.chat_cache:
                self.chat_cache = {
                    "chat_1": ChatInfo(
                        chat_id="chat_1",
                        chat_name="John Doe",
                        chat_type="private",
                        participant_count=2,
                        status=ChatStatus.ACTIVE,
                        unread_count=0
                    ),
                    "chat_2": ChatInfo(
                        chat_id="chat_2",
                        chat_name="Work Group",
                        chat_type="group",
                        participant_count=15,
                        status=ChatStatus.ACTIVE,
                        unread_count=2
                    ),
                    "chat_3": ChatInfo(
                        chat_id="chat_3",
                        chat_name="Tech News",
                        chat_type="channel",
                        participant_count=1200,
                        status=ChatStatus.ACTIVE,
                        unread_count=5
                    )
                }

            chats = list(self.chat_cache.values())[offset:offset + limit]
            return chats

        except Exception as e:
            logger.error(f"Failed to get Telegram chats: {e}")
            raise

    async def get_messages(self, chat_id: str, limit: int = 50,
                          before_message_id: str = None) -> List[ChatMessage]:
        """获取Telegram消息历史"""
        if not self.is_connected:
            raise Exception("Not connected to Telegram")

        try:
            # 实际实现会使用：
            # messages = await self.client.get_messages(chat_id, limit=limit)

            # 从缓存获取消息
            chat_messages = self.message_cache.get(chat_id, [])

            # 如果没有缓存，创建一些模拟消息
            if not chat_messages:
                chat_messages = self._create_sample_messages(chat_id)
                self.message_cache[chat_id] = chat_messages

            # 应用限制
            if before_message_id:
                # 找到指定消息的索引
                before_index = -1
                for i, msg in enumerate(chat_messages):
                    if msg.message_id == before_message_id:
                        before_index = i
                        break

                if before_index > 0:
                    chat_messages = chat_messages[:before_index]

            return chat_messages[-limit:] if chat_messages else []

        except Exception as e:
            logger.error(f"Failed to get Telegram messages: {e}")
            raise

    async def get_chat_info(self, chat_id: str) -> Optional[ChatInfo]:
        """获取Telegram聊天信息"""
        if not self.is_connected:
            raise Exception("Not connected to Telegram")

        try:
            # 从缓存获取
            if chat_id in self.chat_cache:
                return self.chat_cache[chat_id]

            # 实际实现会使用：
            # entity = await self.client.get_entity(chat_id)

            return None

        except Exception as e:
            logger.error(f"Failed to get Telegram chat info: {e}")
            return None

    async def get_contact_info(self, contact_id: str) -> Optional[ContactInfo]:
        """获取Telegram联系人信息"""
        if not self.is_connected:
            raise Exception("Not connected to Telegram")

        try:
            # 实际实现会使用：
            # user = await self.client.get_entity(contact_id)

            # 模拟联系人信息
            return ContactInfo(
                contact_id=contact_id,
                name=f"Telegram User {contact_id[-4:]}",
                username=f"user_{contact_id[-4:]}",
                status="online"
            )

        except Exception as e:
            logger.error(f"Failed to get Telegram contact info: {e}")
            return None

    async def mark_as_read(self, chat_id: str, message_id: str = None) -> bool:
        """标记Telegram消息为已读"""
        if not self.is_connected:
            raise Exception("Not connected to Telegram")

        try:
            # 实际实现会使用：
            # await self.client.send_read_acknowledge(chat_id, message_id)

            # 更新聊天信息
            if chat_id in self.chat_cache:
                self.chat_cache[chat_id].unread_count = 0

            return True

        except Exception as e:
            logger.error(f"Failed to mark Telegram message as read: {e}")
            return False

    async def search_messages(self, query: str, chat_id: str = None,
                            limit: int = 20) -> List[ChatMessage]:
        """搜索Telegram消息"""
        if not self.is_connected:
            raise Exception("Not connected to Telegram")

        try:
            results = []

            # 在指定聊天中搜索
            if chat_id:
                messages = self.message_cache.get(chat_id, [])
                for message in messages:
                    if query.lower() in message.content.lower():
                        results.append(message)
                        if len(results) >= limit:
                            break
            else:
                # 在所有聊天中搜索
                for chat_messages in self.message_cache.values():
                    for message in chat_messages:
                        if query.lower() in message.content.lower():
                            results.append(message)
                            if len(results) >= limit:
                                break
                    if len(results) >= limit:
                        break

            return results

        except Exception as e:
            logger.error(f"Failed to search Telegram messages: {e}")
            return []

    def get_capabilities(self) -> Dict[str, bool]:
        """获取Telegram适配器能力"""
        return {
            "send_text": True,
            "send_image": True,
            "send_file": True,
            "send_audio": True,
            "send_video": True,
            "send_sticker": True,
            "receive_messages": True,
            "message_search": True,
            "mark_as_read": True,
            "typing_indicator": True,
            "message_reactions": True,
            "message_editing": True,
            "message_deletion": True,
            "message_forwarding": True,
            "group_management": True,
            "contact_management": True,
            "channel_management": True,
            "bot_support": True
        }

    def _validate_config(self) -> bool:
        """验证配置"""
        required_fields = ["api_id", "api_hash", "phone_number"]
        for field in required_fields:
            if not self.config.get(field):
                logger.error(f"Missing required config field: {field}")
                return False
        return True

    def _create_sample_messages(self, chat_id: str) -> List[ChatMessage]:
        """创建示例消息"""
        base_time = datetime.now()
        messages = []

        sample_messages = [
            ("other", "Hello! How are you?"),
            ("self", "Hi! I'm doing well, thanks for asking."),
            ("other", "That's great to hear. Are you free for a meeting tomorrow?"),
            ("self", "Yes, I should be available. What time works for you?"),
            ("other", "How about 2 PM?"),
            ("self", "Perfect! I'll send you a calendar invite.")
        ]

        for i, (sender_type, content) in enumerate(sample_messages):
            is_self = sender_type == "self"
            messages.append(ChatMessage(
                message_id=f"sample_{chat_id}_{i}",
                chat_id=chat_id,
                sender_id=self.me["id"] if is_self else f"user_{chat_id}",
                sender_name=self.me["first_name"] if is_self else f"Contact {chat_id[-4:]}",
                content=content,
                message_type=MessageType.TEXT,
                direction=MessageDirection.OUTGOING if is_self else MessageDirection.INCOMING,
                timestamp=datetime.fromtimestamp(base_time.timestamp() - (len(sample_messages) - i) * 300)
            ))

        return messages

    async def _message_listener(self):
        """消息监听器"""
        while self.is_connected:
            try:
                # 实际实现会监听新消息
                # async for event in self.client.iter_messages():
                #     message = self._convert_telegram_message(event.message)
                #     self._notify_message_handlers(message)

                # 模拟消息监听
                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Message listener error: {e}")
                await asyncio.sleep(5)

    def _convert_telegram_message(self, tg_message) -> ChatMessage:
        """转换Telegram消息格式"""
        # 实际实现会转换telethon消息对象
        # 这里是示例结构
        return ChatMessage(
            message_id=str(tg_message.id),
            chat_id=str(tg_message.chat_id),
            sender_id=str(tg_message.sender_id),
            sender_name=getattr(tg_message.sender, 'first_name', 'Unknown'),
            content=tg_message.text or '',
            message_type=MessageType.TEXT,  # 需要根据消息类型判断
            direction=MessageDirection.INCOMING,
            timestamp=tg_message.date
        )

    async def send_typing(self, chat_id: str) -> bool:
        """发送正在输入状态"""
        if not self.is_connected:
            return False

        try:
            # 实际实现：
            # await self.client(SendTypingRequest(chat_id))
            logger.debug(f"Sent typing status to {chat_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to send typing status: {e}")
            return False

    async def send_file(self, chat_id: str, file_path: str, caption: str = "",
                       reply_to: str = None) -> str:
        """发送文件"""
        if not self.is_connected:
            raise Exception("Not connected to Telegram")

        try:
            # 实际实现：
            # message = await self.client.send_file(chat_id, file_path, caption=caption)

            file_path_obj = Path(file_path)
            if not file_path_obj.exists():
                raise FileNotFoundError(f"File not found: {file_path}")

            # 根据文件类型确定消息类型
            suffix = file_path_obj.suffix.lower()
            if suffix in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                message_type = MessageType.IMAGE
            elif suffix in ['.mp4', '.avi', '.mov', '.mkv']:
                message_type = MessageType.VIDEO
            elif suffix in ['.mp3', '.wav', '.ogg', '.m4a']:
                message_type = MessageType.AUDIO
            else:
                message_type = MessageType.FILE

            return await self.send_message(
                chat_id=chat_id,
                content=caption,
                message_type=message_type,
                reply_to=reply_to,
                file_path=file_path
            )

        except Exception as e:
            logger.error(f"Failed to send file: {e}")
            raise