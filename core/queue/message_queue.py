"""
消息队列系统 - SQS风格的FIFO/DLQ/重试/幂等
按照upgrade.md Sprint E规范实现
"""
import logging
import json
import time
import uuid
import hashlib
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict, deque
import threading
from pathlib import Path

logger = logging.getLogger(__name__)


class MessageStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DLQ = "dlq"


class Priority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class QueueMessage:
    """队列消息"""
    message_id: str
    content: Dict
    priority: Priority
    queue_name: str
    deduplication_id: str = None
    group_id: str = None
    created_at: str = None
    scheduled_at: str = None
    retry_count: int = 0
    max_retries: int = 3
    timeout_seconds: int = 300
    status: MessageStatus = MessageStatus.PENDING
    last_error: str = None
    processing_started_at: str = None


@dataclass
class QueueStats:
    """队列统计"""
    queue_name: str
    pending_count: int = 0
    processing_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    dlq_count: int = 0
    oldest_pending_age_seconds: float = 0
    avg_processing_time_seconds: float = 0


class MessageQueue:
    """高性能消息队列 - 支持FIFO, DLQ, 优先级"""

    def __init__(self, name: str, fifo: bool = False, persistence_path: str = None):
        self.name = name
        self.fifo = fifo
        self.persistence_path = Path(persistence_path) if persistence_path else None

        # 消息存储
        self.messages: Dict[str, QueueMessage] = {}
        self.pending_messages: Dict[Priority, deque] = defaultdict(deque)
        self.processing_messages: Dict[str, QueueMessage] = {}
        self.dlq_messages: Dict[str, QueueMessage] = {}

        # FIFO组管理
        self.group_queues: Dict[str, deque] = defaultdict(deque)  # group_id -> message_ids
        self.group_processing: Dict[str, str] = {}  # group_id -> processing_message_id

        # 去重管理
        self.dedup_cache: Dict[str, str] = {}  # dedup_id -> message_id
        self.dedup_ttl: Dict[str, datetime] = {}  # dedup_id -> expiry

        # 统计信息
        self.stats = QueueStats(name)
        self.processing_times: List[float] = []

        # 线程安全
        self.lock = threading.RLock()

        # 加载持久化数据
        if self.persistence_path:
            self._load_from_disk()

    def send_message(self,
                    content: Dict,
                    priority: Priority = Priority.NORMAL,
                    deduplication_id: str = None,
                    group_id: str = None,
                    delay_seconds: int = 0,
                    max_retries: int = 3) -> str:
        """发送消息"""

        with self.lock:
            # 生成消息ID
            message_id = str(uuid.uuid4())

            # 检查去重
            if deduplication_id:
                self._cleanup_expired_dedup()
                if deduplication_id in self.dedup_cache:
                    existing_id = self.dedup_cache[deduplication_id]
                    logger.info(f"Duplicate message detected: {deduplication_id} -> {existing_id}")
                    return existing_id

                # 记录去重信息
                self.dedup_cache[deduplication_id] = message_id
                self.dedup_ttl[deduplication_id] = datetime.now() + timedelta(hours=1)

            # 计算调度时间
            scheduled_at = None
            if delay_seconds > 0:
                scheduled_at = (datetime.now() + timedelta(seconds=delay_seconds)).isoformat()

            # 创建消息
            message = QueueMessage(
                message_id=message_id,
                content=content,
                priority=priority,
                queue_name=self.name,
                deduplication_id=deduplication_id,
                group_id=group_id,
                created_at=datetime.now().isoformat(),
                scheduled_at=scheduled_at,
                max_retries=max_retries
            )

            self.messages[message_id] = message

            # 添加到待处理队列
            if delay_seconds == 0:
                self._enqueue_message(message)

            # 持久化
            self._persist_to_disk()

            logger.info(f"Message sent: {message_id} (priority={priority.name}, group={group_id})")
            return message_id

    def receive_message(self, timeout_seconds: int = 30) -> Optional[QueueMessage]:
        """接收消息"""

        start_time = time.time()

        while time.time() - start_time < timeout_seconds:
            with self.lock:
                # 处理延迟消息
                self._process_delayed_messages()

                # 按优先级获取消息
                message = self._dequeue_message()
                if message:
                    # 标记为处理中
                    message.status = MessageStatus.PROCESSING
                    message.processing_started_at = datetime.now().isoformat()
                    self.processing_messages[message.message_id] = message

                    # FIFO组处理
                    if self.fifo and message.group_id:
                        self.group_processing[message.group_id] = message.message_id

                    self._update_stats()
                    self._persist_to_disk()

                    logger.info(f"Message received: {message.message_id}")
                    return message

            # 等待一段时间再重试
            time.sleep(0.1)

        return None

    def delete_message(self, message_id: str) -> bool:
        """删除消息（标记为完成）"""

        with self.lock:
            message = self.processing_messages.get(message_id)
            if not message:
                logger.warning(f"Message not found in processing: {message_id}")
                return False

            # 计算处理时间
            start_time = datetime.fromisoformat(message.processing_started_at)
            processing_time = (datetime.now() - start_time).total_seconds()
            self.processing_times.append(processing_time)
            if len(self.processing_times) > 100:
                self.processing_times = self.processing_times[-50:]

            # 更新状态
            message.status = MessageStatus.COMPLETED
            del self.processing_messages[message_id]

            # 释放FIFO组
            if self.fifo and message.group_id:
                if self.group_processing.get(message.group_id) == message_id:
                    del self.group_processing[message.group_id]
                    # 处理组中的下一个消息
                    self._process_group_queue(message.group_id)

            self._update_stats()
            self._persist_to_disk()

            logger.info(f"Message completed: {message_id} ({processing_time:.1f}s)")
            return True

    def fail_message(self, message_id: str, error: str = None) -> bool:
        """失败处理消息"""

        with self.lock:
            message = self.processing_messages.get(message_id)
            if not message:
                logger.warning(f"Message not found in processing: {message_id}")
                return False

            message.last_error = error
            message.retry_count += 1

            # 从处理中移除
            del self.processing_messages[message_id]

            # 释放FIFO组
            if self.fifo and message.group_id:
                if self.group_processing.get(message.group_id) == message_id:
                    del self.group_processing[message.group_id]
                    self._process_group_queue(message.group_id)

            # 检查是否超过重试次数
            if message.retry_count >= message.max_retries:
                message.status = MessageStatus.DLQ
                self.dlq_messages[message_id] = message
                logger.warning(f"Message moved to DLQ: {message_id} (retries={message.retry_count})")
            else:
                # 重新入队（延迟重试）
                delay = min(2 ** message.retry_count, 300)  # 指数退避，最大5分钟
                if delay > 1:  # 只有延迟超过1秒才使用scheduled_at
                    message.scheduled_at = (datetime.now() + timedelta(seconds=delay)).isoformat()
                else:
                    message.scheduled_at = None
                    # 立即重新入队
                    self._enqueue_message(message)
                message.status = MessageStatus.PENDING
                logger.info(f"Message retry scheduled: {message_id} (retry={message.retry_count}, delay={delay}s)")

            self._update_stats()
            self._persist_to_disk()
            return True

    def get_queue_stats(self) -> QueueStats:
        """获取队列统计"""
        with self.lock:
            self._update_stats()
            return self.stats

    def purge_queue(self) -> int:
        """清空队列"""
        with self.lock:
            count = len(self.messages)
            self.messages.clear()
            self.pending_messages.clear()
            self.processing_messages.clear()
            self.dlq_messages.clear()
            self.group_queues.clear()
            self.group_processing.clear()
            self.dedup_cache.clear()
            self.dedup_ttl.clear()

            self._update_stats()
            self._persist_to_disk()

            logger.info(f"Queue purged: {count} messages removed")
            return count

    def requeue_dlq_message(self, message_id: str) -> bool:
        """重新入队DLQ消息"""
        with self.lock:
            message = self.dlq_messages.get(message_id)
            if not message:
                return False

            # 重置状态
            message.status = MessageStatus.PENDING
            message.retry_count = 0
            message.last_error = None
            message.scheduled_at = None

            # 移出DLQ
            del self.dlq_messages[message_id]

            # 重新入队
            self._enqueue_message(message)
            self._update_stats()
            self._persist_to_disk()

            logger.info(f"Message requeued from DLQ: {message_id}")
            return True

    def _enqueue_message(self, message: QueueMessage):
        """将消息加入待处理队列"""
        if self.fifo and message.group_id:
            # FIFO模式：按组排队
            self.group_queues[message.group_id].append(message.message_id)
            # 如果组没有在处理中，启动处理
            if message.group_id not in self.group_processing:
                self._process_group_queue(message.group_id)
        else:
            # 非FIFO模式：按优先级排队
            self.pending_messages[message.priority].append(message.message_id)

    def _dequeue_message(self) -> Optional[QueueMessage]:
        """从待处理队列获取消息"""
        # 按优先级顺序处理
        for priority in [Priority.CRITICAL, Priority.HIGH, Priority.NORMAL, Priority.LOW]:
            queue = self.pending_messages[priority]
            if queue:
                message_id = queue.popleft()
                return self.messages.get(message_id)

        return None

    def _process_group_queue(self, group_id: str):
        """处理FIFO组队列"""
        group_queue = self.group_queues[group_id]
        if group_queue and group_id not in self.group_processing:
            message_id = group_queue.popleft()
            message = self.messages.get(message_id)
            if message and message.status == MessageStatus.PENDING:
                # 添加到优先级队列
                self.pending_messages[message.priority].appendleft(message_id)  # 优先处理FIFO消息

    def _process_delayed_messages(self):
        """处理延迟消息"""
        now = datetime.now()
        delayed_messages = []

        for message in self.messages.values():
            if (message.status == MessageStatus.PENDING and
                message.scheduled_at and
                datetime.fromisoformat(message.scheduled_at) <= now):
                delayed_messages.append(message)

        for message in delayed_messages:
            message.scheduled_at = None
            self._enqueue_message(message)

    def _cleanup_expired_dedup(self):
        """清理过期的去重记录"""
        now = datetime.now()
        expired_keys = [
            dedup_id for dedup_id, expiry in self.dedup_ttl.items()
            if expiry < now
        ]

        for dedup_id in expired_keys:
            del self.dedup_cache[dedup_id]
            del self.dedup_ttl[dedup_id]

    def _update_stats(self):
        """更新统计信息"""
        # 计算各状态消息数量
        self.stats.pending_count = sum(len(q) for q in self.pending_messages.values())
        self.stats.processing_count = len(self.processing_messages)
        self.stats.dlq_count = len(self.dlq_messages)

        completed_count = sum(1 for m in self.messages.values() if m.status == MessageStatus.COMPLETED)
        failed_count = sum(1 for m in self.messages.values() if m.status == MessageStatus.FAILED)
        self.stats.completed_count = completed_count
        self.stats.failed_count = failed_count

        # 计算最老待处理消息年龄
        oldest_pending = None
        for message in self.messages.values():
            if message.status == MessageStatus.PENDING:
                created = datetime.fromisoformat(message.created_at)
                if oldest_pending is None or created < oldest_pending:
                    oldest_pending = created

        if oldest_pending:
            self.stats.oldest_pending_age_seconds = (datetime.now() - oldest_pending).total_seconds()
        else:
            self.stats.oldest_pending_age_seconds = 0

        # 计算平均处理时间
        if self.processing_times:
            self.stats.avg_processing_time_seconds = sum(self.processing_times) / len(self.processing_times)
        else:
            self.stats.avg_processing_time_seconds = 0

    def _persist_to_disk(self):
        """持久化到磁盘"""
        if not self.persistence_path:
            return

        try:
            self.persistence_path.parent.mkdir(parents=True, exist_ok=True)

            # 转换消息为可序列化格式
            serializable_messages = {}
            for mid, msg in self.messages.items():
                msg_dict = asdict(msg)
                msg_dict['priority'] = msg.priority.value
                msg_dict['status'] = msg.status.value
                serializable_messages[mid] = msg_dict

            data = {
                "messages": serializable_messages,
                "pending_queues": {
                    p.name: list(q) for p, q in self.pending_messages.items()
                },
                "group_queues": {gid: list(q) for gid, q in self.group_queues.items()},
                "group_processing": self.group_processing,
                "dedup_cache": self.dedup_cache,
                "dedup_ttl": {k: v.isoformat() for k, v in self.dedup_ttl.items()},
                "saved_at": datetime.now().isoformat()
            }

            with open(self.persistence_path, 'w') as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            logger.error(f"Failed to persist queue to disk: {e}")

    def _load_from_disk(self):
        """从磁盘加载"""
        if not self.persistence_path.exists():
            return

        try:
            with open(self.persistence_path, 'r') as f:
                data = json.load(f)

            # 加载消息
            for mid, msg_data in data.get("messages", {}).items():
                # 转换枚举类型
                msg_data['priority'] = Priority(msg_data['priority'])
                msg_data['status'] = MessageStatus(msg_data['status'])
                message = QueueMessage(**msg_data)
                self.messages[mid] = message

            # 加载待处理队列
            for priority_name, queue_list in data.get("pending_queues", {}).items():
                priority = Priority[priority_name]
                self.pending_messages[priority] = deque(queue_list)

            # 加载FIFO组队列
            for gid, queue_list in data.get("group_queues", {}).items():
                self.group_queues[gid] = deque(queue_list)

            # 加载组处理状态
            self.group_processing = data.get("group_processing", {})

            # 加载去重缓存
            self.dedup_cache = data.get("dedup_cache", {})
            dedup_ttl_data = data.get("dedup_ttl", {})
            self.dedup_ttl = {
                k: datetime.fromisoformat(v) for k, v in dedup_ttl_data.items()
            }

            # 重建处理中消息索引
            for message in self.messages.values():
                if message.status == MessageStatus.PROCESSING:
                    self.processing_messages[message.message_id] = message
                elif message.status == MessageStatus.DLQ:
                    self.dlq_messages[message.message_id] = message

            logger.info(f"Loaded {len(self.messages)} messages from disk")

        except Exception as e:
            logger.error(f"Failed to load queue from disk: {e}")


class QueueManager:
    """队列管理器"""

    def __init__(self, persistence_dir: str = "data/queues"):
        self.persistence_dir = Path(persistence_dir)
        self.queues: Dict[str, MessageQueue] = {}
        self.lock = threading.RLock()

    def get_queue(self, name: str, fifo: bool = False) -> MessageQueue:
        """获取或创建队列"""
        with self.lock:
            if name not in self.queues:
                persistence_path = self.persistence_dir / f"{name}.json"
                self.queues[name] = MessageQueue(
                    name=name,
                    fifo=fifo,
                    persistence_path=str(persistence_path)
                )
                logger.info(f"Created queue: {name} (FIFO={fifo})")

            return self.queues[name]

    def list_queues(self) -> List[str]:
        """列出所有队列"""
        with self.lock:
            return list(self.queues.keys())

    def get_all_stats(self) -> Dict[str, QueueStats]:
        """获取所有队列统计"""
        with self.lock:
            return {name: queue.get_queue_stats() for name, queue in self.queues.items()}


# 全局队列管理器
queue_manager = QueueManager()