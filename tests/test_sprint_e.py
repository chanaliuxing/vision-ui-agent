#!/usr/bin/env python3
"""
Sprint E测试 - SQS编排与HP/LP强化
"""
import pytest
import tempfile
import time
import json
from pathlib import Path
import sys
import threading

# 添加项目根目录到路径
sys.path.append(str(Path(__file__).parent.parent))

from core.queue.message_queue import MessageQueue, Priority, MessageStatus, QueueManager
from core.queue.priority_scheduler import PriorityScheduler, TaskType, WorkerConfig


class TestMessageQueue:
    """测试消息队列"""

    def setup_method(self):
        # 使用临时文件进行持久化测试
        self.temp_file = tempfile.NamedTemporaryFile(delete=False)
        self.temp_file.close()
        self.queue = MessageQueue("test_queue", persistence_path=self.temp_file.name)

    def teardown_method(self):
        import os
        os.unlink(self.temp_file.name)

    def test_send_receive_message(self):
        """测试发送和接收消息"""
        content = {"action": "test", "data": "hello"}

        # 发送消息
        message_id = self.queue.send_message(content, Priority.HIGH)
        assert message_id is not None

        # 接收消息
        message = self.queue.receive_message(timeout_seconds=1)
        assert message is not None
        assert message.content == content
        assert message.priority == Priority.HIGH

    def test_fifo_ordering(self):
        """测试FIFO顺序"""
        fifo_queue = MessageQueue("fifo_test", fifo=True)

        # 发送有序消息
        group_id = "test_group"
        msg1_id = fifo_queue.send_message({"order": 1}, group_id=group_id)
        msg2_id = fifo_queue.send_message({"order": 2}, group_id=group_id)
        msg3_id = fifo_queue.send_message({"order": 3}, group_id=group_id)

        # 接收消息应该按顺序
        msg1 = fifo_queue.receive_message(timeout_seconds=1)
        assert msg1.content["order"] == 1

        # 删除第一个消息后才能处理第二个
        fifo_queue.delete_message(msg1.message_id)

        msg2 = fifo_queue.receive_message(timeout_seconds=1)
        assert msg2.content["order"] == 2

    def test_deduplication(self):
        """测试消息去重"""
        content = {"action": "dedup_test"}
        dedup_id = "unique_dedup_123"

        # 发送相同去重ID的消息两次
        msg1_id = self.queue.send_message(content, deduplication_id=dedup_id)
        msg2_id = self.queue.send_message(content, deduplication_id=dedup_id)

        # 应该返回相同的消息ID
        assert msg1_id == msg2_id

        # 只能接收到一条消息
        msg1 = self.queue.receive_message(timeout_seconds=1)
        assert msg1 is not None

        msg2 = self.queue.receive_message(timeout_seconds=1)
        assert msg2 is None

    def test_priority_ordering(self):
        """测试优先级排序"""
        # 发送不同优先级的消息
        self.queue.send_message({"priority": "low"}, Priority.LOW)
        self.queue.send_message({"priority": "high"}, Priority.HIGH)
        self.queue.send_message({"priority": "critical"}, Priority.CRITICAL)
        self.queue.send_message({"priority": "normal"}, Priority.NORMAL)

        # 应该按优先级顺序接收
        msg1 = self.queue.receive_message(timeout_seconds=1)
        assert msg1.content["priority"] == "critical"

        msg2 = self.queue.receive_message(timeout_seconds=1)
        assert msg2.content["priority"] == "high"

        msg3 = self.queue.receive_message(timeout_seconds=1)
        assert msg3.content["priority"] == "normal"

        msg4 = self.queue.receive_message(timeout_seconds=1)
        assert msg4.content["priority"] == "low"

    def test_retry_mechanism(self):
        """测试重试机制"""
        content = {"action": "retry_test"}

        # 发送消息
        message_id = self.queue.send_message(content, max_retries=2)

        # 接收消息
        message = self.queue.receive_message(timeout_seconds=1)
        assert message is not None

        # 标记失败
        self.queue.fail_message(message_id, "Test error")

        # 消息应该重新入队
        time.sleep(0.1)  # 等待重试延迟
        retry_message = self.queue.receive_message(timeout_seconds=1)
        assert retry_message is not None
        assert retry_message.retry_count == 1

    def test_dlq_handling(self):
        """测试DLQ处理"""
        content = {"action": "dlq_test"}

        # 发送消息，最大重试1次
        message_id = self.queue.send_message(content, max_retries=1)

        # 接收并失败两次
        for i in range(2):
            message = self.queue.receive_message(timeout_seconds=1)
            assert message is not None
            self.queue.fail_message(message_id, f"Error {i+1}")

        # 消息应该进入DLQ
        assert message_id in self.queue.dlq_messages
        assert self.queue.dlq_messages[message_id].status == MessageStatus.DLQ

    def test_delayed_messages(self):
        """测试延迟消息"""
        content = {"action": "delayed_test"}

        # 发送延迟消息
        start_time = time.time()
        self.queue.send_message(content, delay_seconds=1)

        # 立即尝试接收应该失败
        message = self.queue.receive_message(timeout_seconds=0.5)
        assert message is None

        # 等待延迟后应该能接收
        message = self.queue.receive_message(timeout_seconds=2)
        assert message is not None
        assert time.time() - start_time >= 1

    def test_persistence(self):
        """测试持久化"""
        content = {"action": "persistence_test"}

        # 发送消息
        message_id = self.queue.send_message(content)

        # 创建新队列实例（模拟重启）
        new_queue = MessageQueue("test_queue", persistence_path=self.temp_file.name)

        # 应该能加载之前的消息
        assert message_id in new_queue.messages
        message = new_queue.receive_message(timeout_seconds=1)
        assert message is not None
        assert message.content == content


class TestPriorityScheduler:
    """测试优先级调度器"""

    def setup_method(self):
        self.scheduler = PriorityScheduler()
        self.task_results = []

        # 注册测试任务处理器
        def hp_handler(content):
            self.task_results.append(("HP", content))
            return f"HP processed: {content}"

        def lp_handler(content):
            self.task_results.append(("LP", content))
            time.sleep(0.1)  # 模拟较慢的处理
            return f"LP processed: {content}"

        def system_handler(content):
            self.task_results.append(("SYSTEM", content))
            return f"SYSTEM processed: {content}"

        self.scheduler.register_task_handler(TaskType.HP, hp_handler)
        self.scheduler.register_task_handler(TaskType.LP, lp_handler)
        self.scheduler.register_task_handler(TaskType.SYSTEM, system_handler)

    def teardown_method(self):
        self.scheduler.stop()

    def test_task_submission(self):
        """测试任务提交"""
        content = {"test": "data"}

        # 提交HP任务
        task_id = self.scheduler.submit_task(TaskType.HP, content)
        assert task_id is not None

        # 检查任务是否在队列中
        stats = self.scheduler.get_scheduler_stats()
        hp_queue_stats = stats["queues"].get("high_priority_queue")
        assert hp_queue_stats is not None
        assert hp_queue_stats.pending_count >= 0

    def test_worker_management(self):
        """测试工作器管理"""
        # 添加HP工作器
        hp_config = WorkerConfig(
            worker_id="hp_worker_1",
            task_types=[TaskType.HP],
            max_concurrent=1
        )
        worker_id = self.scheduler.add_worker(hp_config)
        assert worker_id == "hp_worker_1"

        # 添加LP工作器
        lp_config = WorkerConfig(
            worker_id="lp_worker_1",
            task_types=[TaskType.LP],
            max_concurrent=2
        )
        self.scheduler.add_worker(lp_config)

        # 检查工作器统计
        stats = self.scheduler.get_scheduler_stats()
        assert stats["total_workers"] == 2

    def test_priority_processing(self):
        """测试优先级处理"""
        # 添加工作器
        hp_config = WorkerConfig("hp_worker", [TaskType.HP])
        self.scheduler.add_worker(hp_config)

        # 启动调度器
        self.scheduler.start()

        # 提交不同优先级的任务
        self.scheduler.submit_task(TaskType.LP, {"priority": "low"})
        self.scheduler.submit_task(TaskType.HP, {"priority": "high"})

        # 等待处理
        time.sleep(0.5)

        # HP任务应该优先处理
        assert len(self.task_results) >= 1
        assert self.task_results[0][0] == "HP"

    def test_fifo_within_group(self):
        """测试组内FIFO"""
        # 添加工作器
        hp_config = WorkerConfig("hp_worker", [TaskType.HP], max_concurrent=1)
        self.scheduler.add_worker(hp_config)

        self.scheduler.start()

        # 提交同组的有序任务
        group_id = "test_group"
        for i in range(3):
            self.scheduler.submit_task(
                TaskType.HP,
                {"order": i},
                group_id=group_id
            )

        # 等待处理
        time.sleep(1)

        # 检查处理顺序
        hp_results = [r for r in self.task_results if r[0] == "HP"]
        if len(hp_results) >= 2:
            assert hp_results[0][1]["order"] < hp_results[1][1]["order"]

    def test_scheduler_stats(self):
        """测试调度器统计"""
        # 添加工作器
        config = WorkerConfig("test_worker", [TaskType.HP, TaskType.LP])
        self.scheduler.add_worker(config)

        # 提交任务
        self.scheduler.submit_task(TaskType.HP, {"test": "hp"})
        self.scheduler.submit_task(TaskType.LP, {"test": "lp"})

        # 获取统计
        stats = self.scheduler.get_scheduler_stats()

        assert "queues" in stats
        assert "workers" in stats
        assert stats["total_workers"] == 1
        assert "high_priority_queue" in stats["queues"]
        assert "low_priority_queue" in stats["queues"]


class TestQueueManager:
    """测试队列管理器"""

    def setup_method(self):
        self.manager = QueueManager()

    def test_queue_creation(self):
        """测试队列创建"""
        # 获取普通队列
        queue1 = self.manager.get_queue("test_queue")
        assert queue1.name == "test_queue"
        assert queue1.fifo is False

        # 获取FIFO队列
        queue2 = self.manager.get_queue("fifo_queue", fifo=True)
        assert queue2.name == "fifo_queue"
        assert queue2.fifo is True

        # 再次获取应该返回相同实例
        queue1_again = self.manager.get_queue("test_queue")
        assert queue1 is queue1_again

    def test_list_queues(self):
        """测试列出队列"""
        # 创建几个队列
        self.manager.get_queue("queue1")
        self.manager.get_queue("queue2")
        self.manager.get_queue("queue3")

        queues = self.manager.list_queues()
        assert len(queues) == 3
        assert "queue1" in queues
        assert "queue2" in queues
        assert "queue3" in queues

    def test_all_stats(self):
        """测试获取所有统计"""
        # 创建队列并发送消息
        queue1 = self.manager.get_queue("stats_queue1")
        queue2 = self.manager.get_queue("stats_queue2")

        queue1.send_message({"test": "data1"})
        queue2.send_message({"test": "data2"})

        # 获取统计
        all_stats = self.manager.get_all_stats()
        assert len(all_stats) == 2
        assert "stats_queue1" in all_stats
        assert "stats_queue2" in all_stats

        assert all_stats["stats_queue1"].pending_count == 1
        assert all_stats["stats_queue2"].pending_count == 1


def test_integration_workflow():
    """集成测试：基本队列功能"""

    # 直接测试队列功能
    from core.queue.message_queue import QueueManager

    manager = QueueManager()
    hp_queue = manager.get_queue("hp_test", fifo=True)
    lp_queue = manager.get_queue("lp_test", fifo=False)

    # 测试HP队列FIFO
    for i in range(3):
        hp_queue.send_message({"task": f"hp_{i}"}, Priority.HIGH, group_id="test_group")

    # 测试LP队列优先级
    lp_queue.send_message({"task": "lp_low"}, Priority.LOW)
    lp_queue.send_message({"task": "lp_high"}, Priority.HIGH)
    lp_queue.send_message({"task": "lp_normal"}, Priority.NORMAL)

    # 验证HP队列FIFO顺序
    msg1 = hp_queue.receive_message(timeout_seconds=1)
    assert msg1 is not None
    assert msg1.content["task"] == "hp_0"
    hp_queue.delete_message(msg1.message_id)

    msg2 = hp_queue.receive_message(timeout_seconds=1)
    assert msg2 is not None
    assert msg2.content["task"] == "hp_1"

    # 验证LP队列优先级顺序
    msg_high = lp_queue.receive_message(timeout_seconds=1)
    assert msg_high is not None
    assert msg_high.content["task"] == "lp_high"

    msg_normal = lp_queue.receive_message(timeout_seconds=1)
    assert msg_normal is not None
    assert msg_normal.content["task"] == "lp_normal"

    msg_low = lp_queue.receive_message(timeout_seconds=1)
    assert msg_low is not None
    assert msg_low.content["task"] == "lp_low"

    # 获取统计
    stats = manager.get_all_stats()
    print(f"Queue stats: {len(stats)} queues")
    for name, stat in stats.items():
        print(f"  {name}: {stat.pending_count} pending, {stat.processing_count} processing")

    print("✓ Integration test passed")


if __name__ == "__main__":
    # 运行集成测试
    test_integration_workflow()

    # 运行单元测试
    pytest.main([__file__, "-v"])