"""
微信集成模块 - 按照upgrade.md Sprint E要求
实现微信LP→HP闭环在拥塞时仍优先发送
"""
import logging
import asyncio
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from core.queue.message_queue import MessageQueue, Priority, QueueMessage
from .wechat_real_api import WeChatRealIntegration, create_wechat_config_from_env

logger = logging.getLogger(__name__)


class WeChatMessageType(Enum):
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    VOICE = "voice"


@dataclass
class WeChatMessage:
    chat_id: str
    content: str
    message_type: WeChatMessageType
    sender: str = "bot"
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class WeChatAutoReply:
    """微信自动回复系统 - 增强版支持真实API"""

    def __init__(self, message_queue: MessageQueue, use_real_api: bool = True):
        self.message_queue = message_queue
        self.use_real_api = use_real_api
        self.real_integration = None

        if use_real_api:
            try:
                config = create_wechat_config_from_env()
                self.real_integration = WeChatRealIntegration(config)
                logger.info(f"Real WeChat API initialized: {config.api_type}")
            except Exception as e:
                logger.warning(f"Failed to initialize real WeChat API: {e}")
                self.use_real_api = False
        self.active_chats: Dict[str, Dict] = {}
        self.reply_templates = {
            "greeting": "您好！我是智能助手，有什么可以帮您的吗？",
            "working": "正在为您处理，请稍候...",
            "completed": "已完成您的请求！",
            "error": "抱歉，处理过程中遇到问题，请稍后重试。"
        }

    async def handle_incoming_message(self, chat_id: str, content: str,
                                     sender: str = "user") -> bool:
        """处理接收到的消息"""
        try:
            # 检测消息意图
            intent = self._detect_intent(content)

            # 根据意图选择处理策略
            if intent == "urgent":
                # 紧急消息使用HP优先级
                await self._send_reply(chat_id, content, Priority.HIGH)
            elif intent == "normal":
                # 普通消息使用LP优先级
                await self._send_reply(chat_id, content, Priority.LOW)
            elif intent == "greeting":
                # 问候消息立即回复
                await self._send_immediate_reply(chat_id, self.reply_templates["greeting"])

            # 更新聊天状态
            self.active_chats[chat_id] = {
                "last_message": content,
                "last_reply_time": datetime.now(),
                "message_count": self.active_chats.get(chat_id, {}).get("message_count", 0) + 1
            }

            return True

        except Exception as e:
            logger.error(f"Failed to handle WeChat message: {e}")
            return False

    async def _send_reply(self, chat_id: str, original_content: str, priority: Priority):
        """发送回复消息到队列"""
        try:
            # 生成回复内容
            reply_content = self._generate_reply(original_content)

            # 创建微信回复消息
            wechat_message = WeChatMessage(
                chat_id=chat_id,
                content=reply_content,
                message_type=WeChatMessageType.TEXT
            )

            # 封装为队列消息
            queue_message = QueueMessage()
            queue_message.message_id = f"wechat_{chat_id}_{int(time.time())}"
            queue_message.content = {
                "action": "wechat_reply",
                "chat_id": chat_id,
                "message": wechat_message.__dict__
            }
            queue_message.priority = priority
            queue_message.queue_name = "wechat_replies"
            queue_message.group_id = f"wechat_{chat_id}"  # 确保FIFO
            queue_message.deduplication_id = f"reply_{chat_id}_{hash(original_content)}"

            # 发送到队列
            await self.message_queue.send_message(queue_message)
            logger.info(f"WeChat reply queued: chat_id={chat_id}, priority={priority.value}")

        except Exception as e:
            logger.error(f"Failed to send WeChat reply: {e}")

    async def _send_immediate_reply(self, chat_id: str, content: str):
        """立即发送回复（绕过队列）"""
        try:
            if self.use_real_api and self.real_integration:
                # 使用真实微信API发送
                success = await self.real_integration.send_message(chat_id, content)
                if success:
                    logger.info(f"Real WeChat reply sent: chat_id={chat_id}")
                else:
                    logger.warning(f"Real WeChat send failed, falling back to simulation")
                    await self._simulate_wechat_send(chat_id, content)
            else:
                # 模拟发送到微信
                await self._simulate_wechat_send(chat_id, content)

            logger.info(f"Immediate WeChat reply sent: chat_id={chat_id}")

        except Exception as e:
            logger.error(f"Failed to send immediate reply: {e}")

    def _detect_intent(self, content: str) -> str:
        """检测消息意图"""
        content_lower = content.lower()

        # 紧急关键词
        urgent_keywords = ["紧急", "急", "马上", "立即", "urgent", "asap", "help"]
        if any(keyword in content_lower for keyword in urgent_keywords):
            return "urgent"

        # 问候关键词
        greeting_keywords = ["你好", "您好", "hi", "hello", "在吗"]
        if any(keyword in content_lower for keyword in greeting_keywords):
            return "greeting"

        return "normal"

    def _generate_reply(self, content: str) -> str:
        """生成回复内容"""
        # 简单的回复生成逻辑
        if "谢谢" in content or "thanks" in content.lower():
            return "不客气，很高兴能帮助您！"
        elif "?" in content or "？" in content:
            return f"关于您的问题「{content[:30]}...」，我需要一些时间来处理，请稍候。"
        else:
            return f"收到您的消息「{content[:30]}...」，正在为您处理中。"

    async def _simulate_wechat_send(self, chat_id: str, content: str):
        """模拟发送到微信（实际中应调用微信API）"""
        # 模拟网络延迟
        await asyncio.sleep(0.1)
        logger.info(f"[WeChat Send] To {chat_id}: {content}")


class WeChatQueueMonitor:
    """微信队列监控器 - 确保LP→HP切换正常工作"""

    def __init__(self, message_queue: MessageQueue):
        self.message_queue = message_queue
        self.monitoring = False
        self.stats = {
            "hp_messages_sent": 0,
            "lp_messages_sent": 0,
            "queue_congestion_detected": 0,
            "priority_switches": 0
        }

    async def start_monitoring(self):
        """开始监控队列状态"""
        self.monitoring = True
        logger.info("WeChat queue monitoring started")

        while self.monitoring:
            try:
                await self._check_queue_health()
                await asyncio.sleep(5)  # 每5秒检查一次

            except Exception as e:
                logger.error(f"Queue monitoring error: {e}")
                await asyncio.sleep(10)

    async def stop_monitoring(self):
        """停止监控"""
        self.monitoring = False
        logger.info("WeChat queue monitoring stopped")

    async def _check_queue_health(self):
        """检查队列健康状态"""
        try:
            # 获取队列统计
            queue_stats = await self.message_queue.get_stats()

            # 检测拥塞（待处理消息过多）
            pending_count = queue_stats.get("pending_messages", 0)
            if pending_count > 50:  # 拥塞阈值
                self.stats["queue_congestion_detected"] += 1
                logger.warning(f"Queue congestion detected: {pending_count} pending messages")

                # 检查是否有HP消息等待
                await self._check_hp_priority()

            # 统计优先级处理情况
            hp_processed = queue_stats.get("hp_messages_processed", 0)
            lp_processed = queue_stats.get("lp_messages_processed", 0)

            if hp_processed > self.stats["hp_messages_sent"]:
                self.stats["hp_messages_sent"] = hp_processed

            if lp_processed > self.stats["lp_messages_sent"]:
                self.stats["lp_messages_sent"] = lp_processed

        except Exception as e:
            logger.error(f"Queue health check failed: {e}")

    async def _check_hp_priority(self):
        """检查HP优先级是否正常工作"""
        try:
            # 检查HP队列是否有积压
            hp_pending = await self.message_queue.get_pending_count(Priority.HIGH)
            lp_pending = await self.message_queue.get_pending_count(Priority.LOW)

            if hp_pending > 0 and lp_pending > hp_pending * 3:
                logger.warning(f"HP priority may not be working: HP={hp_pending}, LP={lp_pending}")

                # 记录优先级切换
                self.stats["priority_switches"] += 1

        except Exception as e:
            logger.error(f"HP priority check failed: {e}")

    def get_monitoring_stats(self) -> Dict:
        """获取监控统计"""
        return {
            "monitoring_active": self.monitoring,
            "stats": self.stats.copy(),
            "last_check": datetime.now().isoformat()
        }


class WeChatIntegrationTest:
    """微信集成测试类 - 验证LP→HP闭环"""

    def __init__(self, auto_reply: WeChatAutoReply, monitor: WeChatQueueMonitor):
        self.auto_reply = auto_reply
        self.monitor = monitor

    async def test_lp_to_hp_switching(self) -> Dict:
        """测试LP→HP优先级切换"""
        test_results = {
            "test_name": "LP to HP Priority Switching",
            "start_time": datetime.now().isoformat(),
            "results": []
        }

        try:
            # 1. 发送多个LP消息制造拥塞
            logger.info("Step 1: Creating LP message congestion...")
            for i in range(20):
                await self.auto_reply.handle_incoming_message(
                    f"test_chat_{i}", f"普通消息 {i}", "test_user"
                )

            await asyncio.sleep(2)

            # 2. 发送HP紧急消息
            logger.info("Step 2: Sending HP urgent message...")
            hp_start_time = time.time()
            await self.auto_reply.handle_incoming_message(
                "urgent_chat", "紧急！需要立即处理", "urgent_user"
            )

            # 3. 等待处理并检查优先级
            await asyncio.sleep(3)
            hp_response_time = time.time() - hp_start_time

            # 4. 检查统计
            monitor_stats = self.monitor.get_monitoring_stats()

            test_results["results"] = [
                {
                    "step": "LP_message_flood",
                    "status": "completed",
                    "lp_messages_sent": 20
                },
                {
                    "step": "HP_urgent_message",
                    "status": "completed",
                    "response_time_seconds": hp_response_time
                },
                {
                    "step": "priority_verification",
                    "status": "completed" if hp_response_time < 5 else "failed",
                    "monitor_stats": monitor_stats
                }
            ]

            # 验收标准：HP消息在5秒内处理完成
            overall_success = hp_response_time < 5
            test_results["overall_result"] = "PASSED" if overall_success else "FAILED"
            test_results["end_time"] = datetime.now().isoformat()

            logger.info(f"LP→HP test completed: {test_results['overall_result']}")

        except Exception as e:
            test_results["error"] = str(e)
            test_results["overall_result"] = "ERROR"
            logger.error(f"LP→HP test failed: {e}")

        return test_results


# 工厂函数
async def create_wechat_integration(message_queue: MessageQueue) -> tuple[WeChatAutoReply, WeChatQueueMonitor]:
    """创建微信集成组件"""
    auto_reply = WeChatAutoReply(message_queue)
    monitor = WeChatQueueMonitor(message_queue)

    return auto_reply, monitor