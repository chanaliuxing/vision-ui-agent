"""
聊天管理器 - 统一管理多个聊天适配器
按照upgrade.md Sprint G规范实现
"""
import logging
import asyncio
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .adapter_interface import ChatAdapter, ChatMessage, ChatInfo, MessageType
from .telegram_adapter import TelegramAdapter
from .hitl_system import HITLSystem, ApprovalType, RiskLevel

logger = logging.getLogger(__name__)


class AdapterStatus(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class AdapterInfo:
    """适配器信息"""
    adapter_id: str
    adapter_type: str
    status: AdapterStatus
    last_connected: Optional[datetime] = None
    error_count: int = 0
    last_error: Optional[str] = None
    message_count: int = 0
    capabilities: Dict[str, bool] = None


class ChatManager:
    """聊天管理器"""

    def __init__(self, hitl_system: HITLSystem = None):
        self.adapters: Dict[str, ChatAdapter] = {}
        self.adapter_info: Dict[str, AdapterInfo] = {}
        self.default_adapter_id: Optional[str] = None

        # HITL系统集成
        self.hitl_system = hitl_system

        # 消息处理器
        self.global_message_handlers: List[Callable[[str, ChatMessage], None]] = []
        self.message_routers: Dict[str, str] = {}  # chat_id -> adapter_id

        # 统计信息
        self.message_stats = {
            "total_sent": 0,
            "total_received": 0,
            "errors": 0
        }

    def register_adapter(self, adapter: ChatAdapter, set_as_default: bool = False) -> bool:
        """注册聊天适配器"""
        try:
            adapter_id = adapter.adapter_id

            # 添加消息处理器
            adapter.add_message_handler(
                lambda msg: self._handle_incoming_message(adapter_id, msg)
            )

            # 添加状态处理器
            adapter.add_status_handler(
                lambda status, connected: self._handle_status_change(adapter_id, status, connected)
            )

            # 注册适配器
            self.adapters[adapter_id] = adapter
            self.adapter_info[adapter_id] = AdapterInfo(
                adapter_id=adapter_id,
                adapter_type=type(adapter).__name__,
                status=AdapterStatus.DISCONNECTED,
                capabilities=adapter.get_capabilities()
            )

            if set_as_default or self.default_adapter_id is None:
                self.default_adapter_id = adapter_id

            logger.info(f"Registered chat adapter: {adapter_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to register adapter {adapter.adapter_id}: {e}")
            return False

    def unregister_adapter(self, adapter_id: str) -> bool:
        """注销聊天适配器"""
        try:
            if adapter_id in self.adapters:
                adapter = self.adapters[adapter_id]

                # 断开连接
                if adapter.is_connected:
                    asyncio.create_task(adapter.disconnect())

                del self.adapters[adapter_id]
                del self.adapter_info[adapter_id]

                # 如果是默认适配器，选择新的默认适配器
                if self.default_adapter_id == adapter_id:
                    self.default_adapter_id = next(iter(self.adapters.keys()), None)

                logger.info(f"Unregistered chat adapter: {adapter_id}")
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to unregister adapter {adapter_id}: {e}")
            return False

    async def connect_adapter(self, adapter_id: str) -> bool:
        """连接适配器"""
        adapter = self.adapters.get(adapter_id)
        if not adapter:
            logger.error(f"Adapter not found: {adapter_id}")
            return False

        try:
            self.adapter_info[adapter_id].status = AdapterStatus.CONNECTING

            success = await adapter.connect()
            if success:
                self.adapter_info[adapter_id].status = AdapterStatus.CONNECTED
                self.adapter_info[adapter_id].last_connected = datetime.now()
                self.adapter_info[adapter_id].error_count = 0
                logger.info(f"Connected adapter: {adapter_id}")
            else:
                self.adapter_info[adapter_id].status = AdapterStatus.ERROR
                self.adapter_info[adapter_id].error_count += 1

            return success

        except Exception as e:
            self.adapter_info[adapter_id].status = AdapterStatus.ERROR
            self.adapter_info[adapter_id].error_count += 1
            self.adapter_info[adapter_id].last_error = str(e)
            logger.error(f"Failed to connect adapter {adapter_id}: {e}")
            return False

    async def disconnect_adapter(self, adapter_id: str) -> bool:
        """断开适配器连接"""
        adapter = self.adapters.get(adapter_id)
        if not adapter:
            return False

        try:
            success = await adapter.disconnect()
            if success:
                self.adapter_info[adapter_id].status = AdapterStatus.DISCONNECTED

            return success

        except Exception as e:
            logger.error(f"Failed to disconnect adapter {adapter_id}: {e}")
            return False

    async def connect_all(self) -> Dict[str, bool]:
        """连接所有适配器"""
        results = {}
        for adapter_id in self.adapters:
            results[adapter_id] = await self.connect_adapter(adapter_id)
        return results

    async def disconnect_all(self) -> Dict[str, bool]:
        """断开所有适配器连接"""
        results = {}
        for adapter_id in self.adapters:
            results[adapter_id] = await self.disconnect_adapter(adapter_id)
        return results

    async def send_message(self, chat_id: str, content: str,
                          message_type: MessageType = MessageType.TEXT,
                          adapter_id: str = None,
                          reply_to: str = None,
                          require_approval: bool = None,
                          **kwargs) -> Optional[str]:
        """发送消息"""

        # 选择适配器
        if not adapter_id:
            adapter_id = self.message_routers.get(chat_id, self.default_adapter_id)

        if not adapter_id:
            raise Exception("No adapter available")

        adapter = self.adapters.get(adapter_id)
        if not adapter or not adapter.is_connected:
            raise Exception(f"Adapter {adapter_id} not available")

        # HITL审批检查
        if require_approval is None:
            # 自动判断是否需要审批
            require_approval = await self._should_require_approval(chat_id, content, message_type, adapter_id)

        if require_approval and self.hitl_system:
            # 请求审批
            approval_request_id = await self.hitl_system.request_approval(
                request_type=ApprovalType.MESSAGE_SEND,
                title=f"发送消息审批",
                description=f"请求向 {chat_id} 发送消息: {content[:100]}...",
                context={
                    "chat_id": chat_id,
                    "content": content,
                    "message_type": message_type.value,
                    "adapter_id": adapter_id
                },
                requester_id="chat_manager",
                chat_id=chat_id,
                timeout_minutes=30
            )

            # 等待审批结果
            approval_result = await self._wait_for_approval(approval_request_id)
            if not approval_result or approval_result.status.value != "approved":
                raise Exception("Message sending was not approved")

        try:
            # 发送消息
            message_id = await adapter.send_message(
                chat_id=chat_id,
                content=content,
                message_type=message_type,
                reply_to=reply_to,
                **kwargs
            )

            self.message_stats["total_sent"] += 1
            self.adapter_info[adapter_id].message_count += 1

            logger.info(f"Sent message via {adapter_id} to {chat_id}")
            return message_id

        except Exception as e:
            self.message_stats["errors"] += 1
            logger.error(f"Failed to send message via {adapter_id}: {e}")
            raise

    async def send_text(self, chat_id: str, text: str, adapter_id: str = None,
                       reply_to: str = None, require_approval: bool = None) -> Optional[str]:
        """发送文本消息"""
        return await self.send_message(
            chat_id=chat_id,
            content=text,
            message_type=MessageType.TEXT,
            adapter_id=adapter_id,
            reply_to=reply_to,
            require_approval=require_approval
        )

    async def get_chats(self, adapter_id: str = None) -> List[ChatInfo]:
        """获取聊天列表"""
        if not adapter_id:
            adapter_id = self.default_adapter_id

        adapter = self.adapters.get(adapter_id)
        if not adapter or not adapter.is_connected:
            return []

        try:
            return await adapter.get_chats()
        except Exception as e:
            logger.error(f"Failed to get chats from {adapter_id}: {e}")
            return []

    async def get_messages(self, chat_id: str, limit: int = 50,
                          adapter_id: str = None,
                          before_message_id: str = None) -> List[ChatMessage]:
        """获取消息历史"""
        if not adapter_id:
            adapter_id = self.message_routers.get(chat_id, self.default_adapter_id)

        adapter = self.adapters.get(adapter_id)
        if not adapter or not adapter.is_connected:
            return []

        try:
            return await adapter.get_messages(chat_id, limit, before_message_id)
        except Exception as e:
            logger.error(f"Failed to get messages from {adapter_id}: {e}")
            return []

    async def get_unread_messages(self, adapter_id: str = None) -> List[tuple[str, ChatMessage]]:
        """获取所有未读消息"""
        unread_messages = []

        adapters_to_check = [adapter_id] if adapter_id else list(self.adapters.keys())

        for aid in adapters_to_check:
            adapter = self.adapters.get(aid)
            if adapter and adapter.is_connected:
                try:
                    messages = await adapter.get_unread_messages()
                    for message in messages:
                        unread_messages.append((aid, message))
                except Exception as e:
                    logger.error(f"Failed to get unread messages from {aid}: {e}")

        return unread_messages

    def add_message_handler(self, handler: Callable[[str, ChatMessage], None]):
        """添加全局消息处理器"""
        self.global_message_handlers.append(handler)

    def set_chat_router(self, chat_id: str, adapter_id: str):
        """设置聊天路由"""
        if adapter_id in self.adapters:
            self.message_routers[chat_id] = adapter_id
            logger.info(f"Routed chat {chat_id} to adapter {adapter_id}")
        else:
            logger.warning(f"Cannot route to non-existent adapter: {adapter_id}")

    def get_adapter_info(self, adapter_id: str = None) -> Any:
        """获取适配器信息"""
        if adapter_id:
            return self.adapter_info.get(adapter_id)
        else:
            return dict(self.adapter_info)

    def get_manager_stats(self) -> Dict:
        """获取管理器统计"""
        return {
            "adapters": {
                aid: {
                    "type": info.adapter_type,
                    "status": info.status.value,
                    "connected": info.status == AdapterStatus.CONNECTED,
                    "message_count": info.message_count,
                    "error_count": info.error_count,
                    "last_connected": info.last_connected.isoformat() if info.last_connected else None
                }
                for aid, info in self.adapter_info.items()
            },
            "message_stats": self.message_stats,
            "default_adapter": self.default_adapter_id,
            "total_chats_routed": len(self.message_routers),
            "hitl_enabled": self.hitl_system is not None
        }

    def _handle_incoming_message(self, adapter_id: str, message: ChatMessage):
        """处理接收到的消息"""
        try:
            self.message_stats["total_received"] += 1

            # 调用全局消息处理器
            for handler in self.global_message_handlers:
                try:
                    handler(adapter_id, message)
                except Exception as e:
                    logger.error(f"Message handler error: {e}")

            logger.debug(f"Handled incoming message from {adapter_id}: {message.message_id}")

        except Exception as e:
            logger.error(f"Failed to handle incoming message: {e}")

    def _handle_status_change(self, adapter_id: str, status: str, is_connected: bool):
        """处理适配器状态变化"""
        try:
            info = self.adapter_info.get(adapter_id)
            if info:
                if is_connected:
                    info.status = AdapterStatus.CONNECTED
                    info.last_connected = datetime.now()
                    info.error_count = 0
                else:
                    info.status = AdapterStatus.DISCONNECTED

            logger.info(f"Adapter {adapter_id} status changed: {status} (connected={is_connected})")

        except Exception as e:
            logger.error(f"Failed to handle status change: {e}")

    async def _should_require_approval(self, chat_id: str, content: str,
                                     message_type: MessageType, adapter_id: str) -> bool:
        """判断是否需要审批"""
        if not self.hitl_system:
            return False

        # 创建上下文用于风险评估
        context = {
            "chat_id": chat_id,
            "content": content,
            "message_type": message_type.value,
            "adapter_id": adapter_id,
            "message_length": len(content)
        }

        # 进行风险评估
        risk_level, triggered_rules, auto_reject = self.hitl_system.risk_assessor.assess_risk(context)

        # 中等风险及以上需要审批
        return risk_level.value in ["medium", "high", "critical"]

    async def _wait_for_approval(self, approval_request_id: str, timeout_seconds: int = 1800):
        """等待审批结果"""
        start_time = datetime.now()

        while (datetime.now() - start_time).total_seconds() < timeout_seconds:
            # 检查请求状态
            request = self.hitl_system.request_history.get(approval_request_id)
            if request:
                return request

            # 等待一段时间再检查
            await asyncio.sleep(1)

        # 超时
        logger.warning(f"Approval request {approval_request_id} timed out")
        return None

    async def switch_adapter(self, from_adapter_id: str, to_adapter_id: str) -> bool:
        """切换适配器"""
        if to_adapter_id not in self.adapters:
            logger.error(f"Target adapter not found: {to_adapter_id}")
            return False

        try:
            # 断开原适配器
            if from_adapter_id in self.adapters:
                await self.disconnect_adapter(from_adapter_id)

            # 连接新适配器
            success = await self.connect_adapter(to_adapter_id)
            if success:
                # 更新路由
                chats_to_update = [
                    chat_id for chat_id, adapter_id in self.message_routers.items()
                    if adapter_id == from_adapter_id
                ]

                for chat_id in chats_to_update:
                    self.message_routers[chat_id] = to_adapter_id

                # 更新默认适配器
                if self.default_adapter_id == from_adapter_id:
                    self.default_adapter_id = to_adapter_id

                logger.info(f"Switched from {from_adapter_id} to {to_adapter_id}")
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to switch adapter: {e}")
            return False


# 便捷函数用于创建常用适配器
def create_telegram_adapter(config: Dict) -> TelegramAdapter:
    """创建Telegram适配器"""
    return TelegramAdapter("telegram", config)


def create_mock_adapter(adapter_id: str = "mock") -> Any:
    """创建模拟适配器"""
    from .adapter_interface import MockChatAdapter
    return MockChatAdapter(adapter_id)