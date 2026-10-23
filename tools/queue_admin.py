#!/usr/bin/env python3
"""
队列管理工具 - CLI工具用于管理消息队列和调度器
按照upgrade.md Sprint E规范实现
"""
import argparse
import sys
import json
import time
from pathlib import Path

# 添加项目根目录到路径
sys.path.append(str(Path(__file__).parent.parent))

from core.queue.message_queue import queue_manager, Priority
from core.queue.priority_scheduler import priority_scheduler, TaskType, WorkerConfig


def cmd_queue_stats(args):
    """查看队列统计"""
    all_stats = queue_manager.get_all_stats()

    if not all_stats:
        print("No queues found")
        return

    print("Queue Statistics:")
    print("-" * 80)
    print(f"{'Queue':<25} {'Pending':<8} {'Processing':<10} {'Completed':<10} {'DLQ':<6} {'Oldest':<8}")
    print("-" * 80)

    for queue_name, stats in all_stats.items():
        oldest_age = f"{stats.oldest_pending_age_seconds:.0f}s" if stats.oldest_pending_age_seconds > 0 else "-"
        print(f"{queue_name:<25} "
              f"{stats.pending_count:<8} "
              f"{stats.processing_count:<10} "
              f"{stats.completed_count:<10} "
              f"{stats.dlq_count:<6} "
              f"{oldest_age:<8}")

    print()
    print("Legend: DLQ = Dead Letter Queue, Oldest = Age of oldest pending message")


def cmd_send_message(args):
    """发送消息"""
    try:
        content = json.loads(args.content)
    except json.JSONDecodeError:
        print("Error: Content must be valid JSON")
        return

    queue = queue_manager.get_queue(args.queue, fifo=args.fifo)

    priority = Priority[args.priority.upper()] if args.priority else Priority.NORMAL

    message_id = queue.send_message(
        content=content,
        priority=priority,
        deduplication_id=args.dedup_id,
        group_id=args.group_id,
        delay_seconds=args.delay or 0,
        max_retries=args.max_retries or 3
    )

    print(f"✓ Message sent: {message_id}")


def cmd_receive_message(args):
    """接收消息"""
    queue = queue_manager.get_queue(args.queue)

    print(f"Waiting for message from {args.queue}...")
    message = queue.receive_message(timeout_seconds=args.timeout or 30)

    if message:
        print(f"✓ Received message: {message.message_id}")
        print(f"Priority: {message.priority.name}")
        print(f"Content: {json.dumps(message.content, indent=2)}")
        print(f"Retry count: {message.retry_count}")

        if args.auto_delete:
            queue.delete_message(message.message_id)
            print("✓ Message auto-deleted")
    else:
        print("✗ No message received (timeout)")


def cmd_delete_message(args):
    """删除消息"""
    queue = queue_manager.get_queue(args.queue)

    if queue.delete_message(args.message_id):
        print(f"✓ Message deleted: {args.message_id}")
    else:
        print(f"✗ Message not found: {args.message_id}")


def cmd_fail_message(args):
    """标记消息失败"""
    queue = queue_manager.get_queue(args.queue)

    if queue.fail_message(args.message_id, args.error):
        print(f"✓ Message failed: {args.message_id}")
    else:
        print(f"✗ Message not found: {args.message_id}")


def cmd_purge_queue(args):
    """清空队列"""
    queue = queue_manager.get_queue(args.queue)

    if not args.force:
        confirm = input(f"Are you sure you want to purge queue '{args.queue}'? (y/N): ")
        if confirm.lower() != 'y':
            print("Cancelled")
            return

    count = queue.purge_queue()
    print(f"✓ Purged {count} messages from {args.queue}")


def cmd_requeue_dlq(args):
    """重新入队DLQ消息"""
    queue = queue_manager.get_queue(args.queue)

    if args.message_id:
        # 重新入队特定消息
        if queue.requeue_dlq_message(args.message_id):
            print(f"✓ Message requeued: {args.message_id}")
        else:
            print(f"✗ Message not found in DLQ: {args.message_id}")
    else:
        # 重新入队所有DLQ消息
        dlq_messages = list(queue.dlq_messages.keys())
        success_count = 0

        for message_id in dlq_messages:
            if queue.requeue_dlq_message(message_id):
                success_count += 1

        print(f"✓ Requeued {success_count}/{len(dlq_messages)} DLQ messages")


def cmd_scheduler_stats(args):
    """查看调度器统计"""
    stats = priority_scheduler.get_scheduler_stats()

    print("Priority Scheduler Statistics:")
    print("-" * 60)
    print(f"Status: {'Running' if stats['running'] else 'Stopped'}")
    print(f"Total Workers: {stats['total_workers']}")
    print(f"Active Workers: {stats['active_workers']}")
    print()

    # 队列统计
    print("Queues:")
    for queue_name, queue_stats in stats['queues'].items():
        print(f"  {queue_name}:")
        print(f"    Pending: {queue_stats.pending_count}")
        print(f"    Processing: {queue_stats.processing_count}")
        print(f"    DLQ: {queue_stats.dlq_count}")

    print()

    # 工作器统计
    print("Workers:")
    for worker_id, worker_stats in stats['workers'].items():
        status_icon = {"active": "🟢", "idle": "🟡", "stopped": "🔴", "error": "❌"}.get(worker_stats.status, "⚪")
        print(f"  {status_icon} {worker_id} ({worker_stats.status})")
        print(f"    Tasks Processed: {worker_stats.tasks_processed}")
        print(f"    Avg Processing Time: {worker_stats.avg_processing_time:.2f}s")
        if worker_stats.current_task_id:
            print(f"    Current Task: {worker_stats.current_task_id}")
        if worker_stats.error_count > 0:
            print(f"    Errors: {worker_stats.error_count}")


def cmd_submit_task(args):
    """提交任务"""
    try:
        content = json.loads(args.content)
    except json.JSONDecodeError:
        print("Error: Content must be valid JSON")
        return

    task_type = TaskType(args.task_type)
    priority = Priority[args.priority.upper()] if args.priority else None

    task_id = priority_scheduler.submit_task(
        task_type=task_type,
        content=content,
        priority=priority,
        group_id=args.group_id,
        delay_seconds=args.delay or 0
    )

    print(f"✓ Task submitted: {task_id}")


def cmd_add_worker(args):
    """添加工作器"""
    task_types = [TaskType(t) for t in args.task_types]

    config = WorkerConfig(
        worker_id=args.worker_id,
        task_types=task_types,
        max_concurrent=args.max_concurrent or 1,
        idle_timeout=args.idle_timeout or 30
    )

    worker_id = priority_scheduler.add_worker(config)
    print(f"✓ Worker added: {worker_id}")


def cmd_start_scheduler(args):
    """启动调度器"""
    priority_scheduler.start()
    print("✓ Priority scheduler started")


def cmd_stop_scheduler(args):
    """停止调度器"""
    priority_scheduler.stop()
    print("✓ Priority scheduler stopped")


def cmd_monitor(args):
    """监控模式"""
    print("Queue Monitor (Ctrl+C to exit)")
    print("=" * 50)

    try:
        while True:
            # 清屏（简单版本）
            print("\033[2J\033[H")

            # 显示时间戳
            print(f"Last Updated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
            print()

            # 显示队列统计
            cmd_queue_stats(args)
            print()

            # 显示调度器统计
            if args.scheduler:
                cmd_scheduler_stats(args)

            time.sleep(args.interval or 5)

    except KeyboardInterrupt:
        print("\nMonitoring stopped")


def main():
    parser = argparse.ArgumentParser(description="队列管理工具")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # 队列统计
    stats_parser = subparsers.add_parser("stats", help="查看队列统计")
    stats_parser.set_defaults(func=cmd_queue_stats)

    # 发送消息
    send_parser = subparsers.add_parser("send", help="发送消息")
    send_parser.add_argument("queue", help="队列名称")
    send_parser.add_argument("content", help="消息内容 (JSON)")
    send_parser.add_argument("--priority", choices=["low", "normal", "high", "critical"], help="优先级")
    send_parser.add_argument("--fifo", action="store_true", help="使用FIFO队列")
    send_parser.add_argument("--dedup-id", help="去重ID")
    send_parser.add_argument("--group-id", help="组ID (FIFO)")
    send_parser.add_argument("--delay", type=int, help="延迟秒数")
    send_parser.add_argument("--max-retries", type=int, help="最大重试次数")
    send_parser.set_defaults(func=cmd_send_message)

    # 接收消息
    receive_parser = subparsers.add_parser("receive", help="接收消息")
    receive_parser.add_argument("queue", help="队列名称")
    receive_parser.add_argument("--timeout", type=int, help="超时秒数")
    receive_parser.add_argument("--auto-delete", action="store_true", help="自动删除消息")
    receive_parser.set_defaults(func=cmd_receive_message)

    # 删除消息
    delete_parser = subparsers.add_parser("delete", help="删除消息")
    delete_parser.add_argument("queue", help="队列名称")
    delete_parser.add_argument("message_id", help="消息ID")
    delete_parser.set_defaults(func=cmd_delete_message)

    # 失败消息
    fail_parser = subparsers.add_parser("fail", help="标记消息失败")
    fail_parser.add_argument("queue", help="队列名称")
    fail_parser.add_argument("message_id", help="消息ID")
    fail_parser.add_argument("--error", help="错误信息")
    fail_parser.set_defaults(func=cmd_fail_message)

    # 清空队列
    purge_parser = subparsers.add_parser("purge", help="清空队列")
    purge_parser.add_argument("queue", help="队列名称")
    purge_parser.add_argument("--force", action="store_true", help="强制清空")
    purge_parser.set_defaults(func=cmd_purge_queue)

    # 重新入队DLQ
    requeue_parser = subparsers.add_parser("requeue-dlq", help="重新入队DLQ消息")
    requeue_parser.add_argument("queue", help="队列名称")
    requeue_parser.add_argument("--message-id", help="消息ID (可选，默认重新入队所有)")
    requeue_parser.set_defaults(func=cmd_requeue_dlq)

    # 调度器统计
    sched_stats_parser = subparsers.add_parser("scheduler-stats", help="查看调度器统计")
    sched_stats_parser.set_defaults(func=cmd_scheduler_stats)

    # 提交任务
    task_parser = subparsers.add_parser("submit-task", help="提交任务")
    task_parser.add_argument("task_type", choices=["high_priority", "low_priority", "system"], help="任务类型")
    task_parser.add_argument("content", help="任务内容 (JSON)")
    task_parser.add_argument("--priority", choices=["low", "normal", "high", "critical"], help="优先级")
    task_parser.add_argument("--group-id", help="组ID")
    task_parser.add_argument("--delay", type=int, help="延迟秒数")
    task_parser.set_defaults(func=cmd_submit_task)

    # 添加工作器
    worker_parser = subparsers.add_parser("add-worker", help="添加工作器")
    worker_parser.add_argument("worker_id", help="工作器ID")
    worker_parser.add_argument("task_types", nargs="+", choices=["high_priority", "low_priority", "system"], help="任务类型")
    worker_parser.add_argument("--max-concurrent", type=int, help="最大并发数")
    worker_parser.add_argument("--idle-timeout", type=int, help="空闲超时秒数")
    worker_parser.set_defaults(func=cmd_add_worker)

    # 启动调度器
    start_parser = subparsers.add_parser("start-scheduler", help="启动调度器")
    start_parser.set_defaults(func=cmd_start_scheduler)

    # 停止调度器
    stop_parser = subparsers.add_parser("stop-scheduler", help="停止调度器")
    stop_parser.set_defaults(func=cmd_stop_scheduler)

    # 监控模式
    monitor_parser = subparsers.add_parser("monitor", help="监控模式")
    monitor_parser.add_argument("--interval", type=int, default=5, help="刷新间隔")
    monitor_parser.add_argument("--scheduler", action="store_true", help="包含调度器统计")
    monitor_parser.set_defaults(func=cmd_monitor)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    try:
        args.func(args)
    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()