# client/run_manager.py
import asyncio
from typing import Dict, Any
import sys
import os

# 确保能导入core模块
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from core import ENGINE_VERSION
from client.checkpoint import Checkpointer

class RunManager:
    def __init__(self, scheduler, services, locks):
        self.scheduler = scheduler
        self.services = services
        self.locks = locks
        self.checkpointer = Checkpointer(api=getattr(services, 'api', None),
                                         logger=getattr(services, 'logger', None))
        self._runs: Dict[str, Any] = {}  # run_id -> runner

    def register(self, run_id: str, runner):
        """注册运行中的工作流"""
        self._runs[run_id] = runner

    async def pause(self, run_id: str):
        """暂停指定的运行"""
        r = self._runs.get(run_id)
        if not r:
            return
        # 等待到当前动作完成：由 Scheduler 在一步结束后调用 safepoint 回调
        r._pause_requested = True

    async def stop(self, run_id: str):
        """停止指定的运行"""
        r = self._runs.get(run_id)
        if not r:
            return
        r._stop_requested = True

    async def resume(self, run_id: str, snapshot: Dict[str, Any] | None = None):
        """恢复指定的运行"""
        r = self._runs.get(run_id)
        if not r:
            return
        if not snapshot:
            snapshot = self.checkpointer.load_local(run_id)  # 若云端不可达，用本地
        if not snapshot:
            return

        # 恢复上下文
        r.state = snapshot["state"]
        r.ctx.vars.update(snapshot["vars"])
        r.step_idx = snapshot.get("step_idx", 0)
        r._paused = False

        if self.services.logger:
            self.services.logger.info(f"resumed run={run_id} state={r.state}")

    async def at_safepoint(self, runner):
        """
        由 Scheduler/Runner 在每个动作后调用：检查是否需要暂停/停止；
        如需要则保存快照并释放资源锁。
        """
        if getattr(runner, "_stop_requested", False):
            await self._save_and_cleanup(runner, status="STOPPED")
            runner.state = None
            return True

        if getattr(runner, "_pause_requested", False):
            await self._save_and_cleanup(runner, status="PAUSED")
            runner._paused = True
            return True

        return False

    async def _save_and_cleanup(self, runner, status: str):
        """保存快照并清理资源"""
        inflight = {}

        # 如果当前有未 ack 的 SQS 消息且需要立即可见，调用 requeue_now
        receipt = runner.ctx.vars.get("_sqs_receipt")
        topic = runner.ctx.vars.get("_sqs_topic")
        if receipt and topic and hasattr(self.services, 'mq'):
            try:
                # 这里应该调用 requeue_now，暂时先记录在inflight中
                inflight["sqs"] = {"topic": topic, "receipt": receipt}
            except Exception:
                pass

        inflight["ocr_job"] = runner.ctx.vars.get("ocr_job")

        # 获取资源锁信息
        resource_lock = runner.spec.get("meta", {}).get("resource_lock")
        resource_locks = [resource_lock] if resource_lock else []

        # 保存快照
        self.checkpointer.save(
            run_id=getattr(runner.ctx, 'run_id', 'unknown'),
            workflow_name=runner.spec.get("name", ""),
            engine_version=ENGINE_VERSION,
            state=runner.state,
            vars=runner.ctx.vars,
            step_idx=getattr(runner, 'step_idx', 0),
            resource_locks=resource_locks,
            inflight=inflight
        )

        # 上报运行状态（API）
        if hasattr(self.services, 'api') and self.services.api:
            self.services.api.post_async("/api/runs/status", {
                "run_id": getattr(runner.ctx, 'run_id', 'unknown'),
                "status": status,
                "state": runner.state
            })