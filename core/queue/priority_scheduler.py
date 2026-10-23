"""
优先级调度器 - HP/LP任务智能调度
按照upgrade.md Sprint E规范实现
"""
import logging
import time
import threading
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from collections import deque
import queue

from .message_queue import QueueManager, Priority, MessageStatus

logger = logging.getLogger(__name__)


class TaskType(Enum):
    """任务类型"""
    HP = "high_priority"    # 高优先级：实时响应类（微信回复）
    LP = "low_priority"     # 低优先级：批处理类（数据采集）
    SYSTEM = "system"       # 系统级：监控、清理等


@dataclass
class WorkerConfig:
    """工作器配置"""
    worker_id: str
    task_types: List[TaskType]
    max_concurrent: int = 1
    idle_timeout: int = 30
    health_check_interval: int = 60


@dataclass
class WorkerStats:
    """工作器统计"""
    worker_id: str
    status: str  # "active", "idle", "stopped", "error"
    tasks_processed: int = 0
    total_processing_time: float = 0
    avg_processing_time: float = 0
    last_task_at: Optional[datetime] = None
    current_task_id: Optional[str] = None
    error_count: int = 0
    last_error: Optional[str] = None


class TaskWorker:
    """任务工作器"""

    def __init__(self, config: WorkerConfig, task_handler: Callable):
        self.config = config
        self.task_handler = task_handler
        self.stats = WorkerStats(worker_id=config.worker_id, status="idle")

        self.running = False
        self.thread = None
        self.current_tasks: Dict[str, Any] = {}  # task_id -> task_info
        self.task_lock = threading.RLock()

        # 获取队列管理器
        self.queue_manager = QueueManager()

    def start(self):
        """启动工作器"""
        if self.running:
            return

        self.running = True
        self.stats.status = "active"
        self.thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.thread.start()

        logger.info(f"Worker started: {self.config.worker_id}")

    def stop(self):
        """停止工作器"""
        self.running = False
        self.stats.status = "stopped"

        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)

        logger.info(f"Worker stopped: {self.config.worker_id}")

    def _worker_loop(self):
        """工作器主循环"""
        last_health_check = time.time()

        while self.running:
            try:
                # 健康检查
                if time.time() - last_health_check > self.config.health_check_interval:
                    self._health_check()
                    last_health_check = time.time()

                # 检查是否可以接收新任务
                if len(self.current_tasks) >= self.config.max_concurrent:
                    time.sleep(0.1)
                    continue

                # 按优先级接收任务
                message = self._receive_prioritized_message()
                if message:
                    self._process_message(message)
                else:
                    # 空闲状态
                    self.stats.status = "idle"
                    time.sleep(0.5)

            except Exception as e:
                self.stats.error_count += 1
                self.stats.last_error = str(e)
                self.stats.status = "error"
                logger.error(f"Worker error {self.config.worker_id}: {e}")
                time.sleep(1)

    def _receive_prioritized_message(self):
        """按优先级接收消息"""
        # 按任务类型优先级尝试接收
        for task_type in self.config.task_types:
            queue_name = f"{task_type.value}_queue"
            message_queue = self.queue_manager.get_queue(queue_name)

            message = message_queue.receive_message(timeout_seconds=1)
            if message:
                return message

        return None

    def _process_message(self, message):
        """处理消息"""
        task_id = message.message_id
        start_time = time.time()

        with self.task_lock:
            self.current_tasks[task_id] = {
                "message": message,
                "start_time": start_time
            }

        self.stats.current_task_id = task_id
        self.stats.status = "processing"

        try:
            # 调用任务处理器
            result = self.task_handler(message.content)

            # 成功完成
            processing_time = time.time() - start_time
            self._update_stats(processing_time, success=True)

            # 删除消息
            queue_name = f"{message.content.get('task_type', 'normal')}_queue"
            message_queue = self.queue_manager.get_queue(queue_name)
            message_queue.delete_message(task_id)

            logger.info(f"Task completed: {task_id} ({processing_time:.2f}s)")

        except Exception as e:
            processing_time = time.time() - start_time
            self._update_stats(processing_time, success=False)

            # 失败处理
            queue_name = f"{message.content.get('task_type', 'normal')}_queue"
            message_queue = self.queue_manager.get_queue(queue_name)
            message_queue.fail_message(task_id, str(e))

            logger.error(f"Task failed: {task_id} - {e}")

        finally:
            with self.task_lock:
                if task_id in self.current_tasks:
                    del self.current_tasks[task_id]

            self.stats.current_task_id = None

    def _update_stats(self, processing_time: float, success: bool):
        """更新统计信息"""
        self.stats.tasks_processed += 1
        self.stats.total_processing_time += processing_time
        self.stats.avg_processing_time = (
            self.stats.total_processing_time / self.stats.tasks_processed
        )
        self.stats.last_task_at = datetime.now()

        if not success:
            self.stats.error_count += 1

    def _health_check(self):
        """健康检查"""
        # 检查超时任务
        current_time = time.time()
        timeout_tasks = []

        with self.task_lock:
            for task_id, task_info in self.current_tasks.items():
                if current_time - task_info["start_time"] > 300:  # 5分钟超时
                    timeout_tasks.append(task_id)

        # 处理超时任务
        for task_id in timeout_tasks:
            logger.warning(f"Task timeout: {task_id}")
            # 这里可以添加超时处理逻辑

    def get_stats(self) -> WorkerStats:
        """获取工作器统计"""
        return self.stats


class PriorityScheduler:
    """优先级调度器"""

    def __init__(self):
        self.queue_manager = QueueManager()
        self.workers: Dict[str, TaskWorker] = {}
        self.task_handlers: Dict[TaskType, Callable] = {}

        # 创建不同优先级的队列
        self._setup_queues()

        self.running = False
        self.monitor_thread = None

    def _setup_queues(self):
        """设置队列"""
        # HP队列 - FIFO保证顺序
        self.hp_queue = self.queue_manager.get_queue("high_priority_queue", fifo=True)

        # LP队列 - 普通队列
        self.lp_queue = self.queue_manager.get_queue("low_priority_queue", fifo=False)

        # 系统队列 - 普通队列
        self.system_queue = self.queue_manager.get_queue("system_queue", fifo=False)

        logger.info("Priority queues initialized")

    def register_task_handler(self, task_type: TaskType, handler: Callable):
        """注册任务处理器"""
        self.task_handlers[task_type] = handler
        logger.info(f"Registered handler for {task_type.value}")

    def add_worker(self, config: WorkerConfig) -> str:
        """添加工作器"""
        # 为工作器分配任务处理器
        def worker_handler(task_content):
            task_type_name = task_content.get("task_type")
            if not task_type_name:
                raise ValueError("Task type not specified")

            task_type = TaskType(task_type_name)
            handler = self.task_handlers.get(task_type)
            if not handler:
                raise ValueError(f"No handler for task type: {task_type}")

            return handler(task_content)

        worker = TaskWorker(config, worker_handler)
        self.workers[config.worker_id] = worker

        if self.running:
            worker.start()

        logger.info(f"Added worker: {config.worker_id}")
        return config.worker_id

    def submit_task(self,
                   task_type: TaskType,
                   content: Dict,
                   priority: Priority = None,
                   group_id: str = None,
                   delay_seconds: int = 0) -> str:
        """提交任务"""

        # 自动设置优先级
        if priority is None:
            if task_type == TaskType.HP:
                priority = Priority.HIGH
            elif task_type == TaskType.SYSTEM:
                priority = Priority.CRITICAL
            else:
                priority = Priority.NORMAL

        # 添加任务类型到内容
        content = content.copy()
        content["task_type"] = task_type.value

        # 选择队列
        if task_type == TaskType.HP:
            queue = self.hp_queue
        elif task_type == TaskType.SYSTEM:
            queue = self.system_queue
        else:
            queue = self.lp_queue

        # 发送消息
        message_id = queue.send_message(
            content=content,
            priority=priority,
            group_id=group_id,
            delay_seconds=delay_seconds
        )

        logger.info(f"Task submitted: {message_id} (type={task_type.value}, priority={priority.name})")
        return message_id

    def start(self):
        """启动调度器"""
        if self.running:
            return

        self.running = True

        # 启动所有工作器
        for worker in self.workers.values():
            worker.start()

        # 启动监控线程
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()

        logger.info("Priority scheduler started")

    def stop(self):
        """停止调度器"""
        self.running = False

        # 停止所有工作器
        for worker in self.workers.values():
            worker.stop()

        # 停止监控线程
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5)

        logger.info("Priority scheduler stopped")

    def _monitor_loop(self):
        """监控循环"""
        while self.running:
            try:
                self._check_queue_health()
                self._auto_scale_workers()
                time.sleep(10)  # 每10秒检查一次
            except Exception as e:
                logger.error(f"Monitor error: {e}")
                time.sleep(5)

    def _check_queue_health(self):
        """检查队列健康状态"""
        all_stats = self.queue_manager.get_all_stats()

        for queue_name, stats in all_stats.items():
            # 检查积压
            if stats.pending_count > 100:
                logger.warning(f"Queue backlog: {queue_name} has {stats.pending_count} pending messages")

            # 检查DLQ
            if stats.dlq_count > 10:
                logger.warning(f"DLQ alert: {queue_name} has {stats.dlq_count} failed messages")

            # 检查老消息
            if stats.oldest_pending_age_seconds > 300:  # 5分钟
                logger.warning(f"Old messages: {queue_name} has messages pending for {stats.oldest_pending_age_seconds:.0f}s")

    def _auto_scale_workers(self):
        """自动伸缩工作器"""
        all_stats = self.queue_manager.get_all_stats()

        # HP队列需要快速响应
        hp_stats = all_stats.get("high_priority_queue")
        if hp_stats and hp_stats.pending_count > 5:
            # 考虑启动更多HP工作器
            hp_workers = [w for w in self.workers.values() if TaskType.HP in w.config.task_types]
            if len(hp_workers) < 3:  # 最多3个HP工作器
                logger.info("Consider scaling up HP workers")

    def get_scheduler_stats(self) -> Dict:
        """获取调度器统计"""
        queue_stats = self.queue_manager.get_all_stats()
        worker_stats = {wid: worker.get_stats() for wid, worker in self.workers.items()}

        return {
            "queues": queue_stats,
            "workers": worker_stats,
            "running": self.running,
            "total_workers": len(self.workers),
            "active_workers": sum(1 for w in worker_stats.values() if w.status == "active")
        }

    def get_queue_info(self, queue_name: str) -> Dict:
        """获取队列信息"""
        if queue_name in self.queue_manager.queues:
            queue = self.queue_manager.queues[queue_name]
            return {
                "name": queue.name,
                "fifo": queue.fifo,
                "stats": queue.get_queue_stats(),
                "pending_priorities": {
                    p.name: len(q) for p, q in queue.pending_messages.items()
                }
            }
        return {}


# 全局优先级调度器
priority_scheduler = PriorityScheduler()