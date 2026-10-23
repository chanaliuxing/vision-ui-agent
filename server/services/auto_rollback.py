"""
Sprint I: 自动回退服务
监控Planner性能并在异常时自动回退到稳定版本
"""

import asyncio
import logging
import time
import json
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class HealthStatus(Enum):
    """健康状态枚举"""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"

class RollbackReason(Enum):
    """回退原因枚举"""
    HIGH_FAILURE_RATE = "high_failure_rate"
    HIGH_COST = "high_cost"
    LOW_SUCCESS_RATE = "low_success_rate"
    TIMEOUT_SPIKE = "timeout_spike"
    ERROR_THRESHOLD = "error_threshold"
    MANUAL_TRIGGER = "manual_trigger"

@dataclass
class PerformanceMetrics:
    """性能指标"""
    success_rate: float
    failure_rate: float
    avg_cost_per_run: float
    avg_latency_ms: int
    total_runs: int
    error_count: int
    timeout_count: int
    timestamp: datetime

@dataclass
class RollbackThresholds:
    """回退阈值"""
    failure_rate_threshold: float = 0.15  # 15%失败率
    cost_multiplier_threshold: float = 1.5  # 成本超过1.5倍
    success_rate_threshold: float = 0.6   # 成功率低于60%
    latency_threshold_ms: int = 5000      # 延迟超过5秒
    min_sample_size: int = 20             # 最小样本数
    evaluation_window_minutes: int = 15   # 评估窗口15分钟

@dataclass
class RollbackAction:
    """回退动作"""
    timestamp: datetime
    version_id: int
    version_name: str
    reason: RollbackReason
    metrics_before: PerformanceMetrics
    target_version_id: Optional[int] = None
    rollback_completed: bool = False
    rollback_time: Optional[datetime] = None

class MetricsCollector:
    """指标收集器"""

    def __init__(self):
        self.metrics_cache = {}
        self.baseline_metrics = {}

    async def collect_current_metrics(self, version_id: int, host: str) -> PerformanceMetrics:
        """收集当前性能指标"""
        try:
            # 这里应该从实际的监控系统获取指标
            # 目前使用模拟数据
            return await self._simulate_metrics(version_id, host)

        except Exception as e:
            logger.error(f"Failed to collect metrics for version {version_id}: {e}")
            return self._get_default_metrics()

    async def _simulate_metrics(self, version_id: int, host: str) -> PerformanceMetrics:
        """模拟指标收集"""
        import random

        # 基础指标
        base_success_rate = 0.78
        base_cost = 0.02
        base_latency = 1200

        # 根据版本ID模拟不同性能
        version_factor = (version_id % 5) * 0.02

        # 模拟性能波动
        success_rate = base_success_rate + version_factor + random.uniform(-0.05, 0.05)
        success_rate = max(0.4, min(0.95, success_rate))

        failure_rate = random.uniform(0.05, 0.15)
        cost = base_cost * (1 + version_factor) + random.uniform(-0.002, 0.002)
        latency = int(base_latency + random.uniform(-200, 300))

        total_runs = random.randint(50, 200)
        error_count = int(total_runs * failure_rate)
        timeout_count = random.randint(1, 5)

        return PerformanceMetrics(
            success_rate=success_rate,
            failure_rate=failure_rate,
            avg_cost_per_run=cost,
            avg_latency_ms=latency,
            total_runs=total_runs,
            error_count=error_count,
            timeout_count=timeout_count,
            timestamp=datetime.now()
        )

    def _get_default_metrics(self) -> PerformanceMetrics:
        """获取默认指标（收集失败时使用）"""
        return PerformanceMetrics(
            success_rate=0.0,
            failure_rate=1.0,
            avg_cost_per_run=0.0,
            avg_latency_ms=0,
            total_runs=0,
            error_count=0,
            timeout_count=0,
            timestamp=datetime.now()
        )

    async def get_baseline_metrics(self, host: str) -> Optional[PerformanceMetrics]:
        """获取基线指标"""
        # 这里应该从历史数据计算基线
        # 目前返回模拟基线
        if host not in self.baseline_metrics:
            self.baseline_metrics[host] = PerformanceMetrics(
                success_rate=0.75,
                failure_rate=0.08,
                avg_cost_per_run=0.02,
                avg_latency_ms=1200,
                total_runs=1000,
                error_count=80,
                timeout_count=10,
                timestamp=datetime.now() - timedelta(days=7)
            )

        return self.baseline_metrics[host]

class HealthEvaluator:
    """健康状态评估器"""

    def __init__(self, thresholds: RollbackThresholds):
        self.thresholds = thresholds

    def evaluate_health(self, current_metrics: PerformanceMetrics,
                       baseline_metrics: Optional[PerformanceMetrics] = None) -> Tuple[HealthStatus, List[RollbackReason]]:
        """评估健康状态"""
        issues = []

        # 检查样本数量
        if current_metrics.total_runs < self.thresholds.min_sample_size:
            return HealthStatus.UNKNOWN, []

        # 检查失败率
        if current_metrics.failure_rate > self.thresholds.failure_rate_threshold:
            issues.append(RollbackReason.HIGH_FAILURE_RATE)

        # 检查成功率
        if current_metrics.success_rate < self.thresholds.success_rate_threshold:
            issues.append(RollbackReason.LOW_SUCCESS_RATE)

        # 检查延迟
        if current_metrics.avg_latency_ms > self.thresholds.latency_threshold_ms:
            issues.append(RollbackReason.TIMEOUT_SPIKE)

        # 检查成本（与基线比较）
        if baseline_metrics:
            cost_ratio = current_metrics.avg_cost_per_run / max(baseline_metrics.avg_cost_per_run, 0.001)
            if cost_ratio > self.thresholds.cost_multiplier_threshold:
                issues.append(RollbackReason.HIGH_COST)

        # 确定整体健康状态
        if len(issues) >= 2:
            health_status = HealthStatus.CRITICAL
        elif len(issues) == 1:
            health_status = HealthStatus.WARNING
        else:
            health_status = HealthStatus.HEALTHY

        return health_status, issues

    def should_rollback(self, health_status: HealthStatus, issues: List[RollbackReason]) -> bool:
        """判断是否应该回退"""
        # 严重健康问题立即回退
        if health_status == HealthStatus.CRITICAL:
            return True

        # 特定严重问题立即回退
        critical_issues = {RollbackReason.HIGH_FAILURE_RATE, RollbackReason.LOW_SUCCESS_RATE}
        if any(issue in critical_issues for issue in issues):
            return True

        return False

class AutoRollbackService:
    """自动回退服务"""

    def __init__(self, thresholds: Optional[RollbackThresholds] = None):
        self.thresholds = thresholds or RollbackThresholds()
        self.metrics_collector = MetricsCollector()
        self.health_evaluator = HealthEvaluator(self.thresholds)
        self.rollback_history = []
        self.monitored_deployments = {}
        self.is_running = False

    async def start_monitoring(self):
        """启动监控"""
        if self.is_running:
            logger.warning("Auto rollback monitoring is already running")
            return

        self.is_running = True
        logger.info("Starting auto rollback monitoring")

        try:
            while self.is_running:
                await self._monitoring_cycle()
                await asyncio.sleep(60)  # 每分钟检查一次

        except Exception as e:
            logger.error(f"Auto rollback monitoring failed: {e}")
        finally:
            self.is_running = False

    async def stop_monitoring(self):
        """停止监控"""
        self.is_running = False
        logger.info("Stopping auto rollback monitoring")

    async def _monitoring_cycle(self):
        """监控周期"""
        try:
            # 获取所有活跃部署
            active_deployments = await self._get_active_deployments()

            for deployment in active_deployments:
                await self._check_deployment_health(deployment)

        except Exception as e:
            logger.error(f"Monitoring cycle failed: {e}")

    async def _get_active_deployments(self) -> List[Dict[str, Any]]:
        """获取活跃部署"""
        try:
            # 这里应该调用部署API获取活跃部署
            # 目前返回模拟数据
            return [
                {
                    "version_id": 1,
                    "version_name": "baseline_agentq",
                    "host": "ca.indeed.com",
                    "traffic_pct": 80,
                    "assignment_id": 1
                },
                {
                    "version_id": 3,
                    "version_name": "dpo_optimized_v1",
                    "host": "ca.indeed.com",
                    "traffic_pct": 20,
                    "assignment_id": 2
                }
            ]

        except Exception as e:
            logger.error(f"Failed to get active deployments: {e}")
            return []

    async def _check_deployment_health(self, deployment: Dict[str, Any]):
        """检查部署健康状态"""
        version_id = deployment["version_id"]
        host = deployment["host"]
        deployment_key = f"{version_id}:{host}"

        try:
            # 收集当前指标
            current_metrics = await self.metrics_collector.collect_current_metrics(version_id, host)

            # 获取基线指标
            baseline_metrics = await self.metrics_collector.get_baseline_metrics(host)

            # 评估健康状态
            health_status, issues = self.health_evaluator.evaluate_health(current_metrics, baseline_metrics)

            # 记录健康状态
            self.monitored_deployments[deployment_key] = {
                "deployment": deployment,
                "health_status": health_status,
                "issues": issues,
                "current_metrics": current_metrics,
                "last_check": datetime.now()
            }

            logger.debug(f"Health check for {deployment['version_name']}: {health_status.value}, issues: {[i.value for i in issues]}")

            # 判断是否需要回退
            if self.health_evaluator.should_rollback(health_status, issues):
                await self._execute_rollback(deployment, current_metrics, issues)

        except Exception as e:
            logger.error(f"Health check failed for deployment {deployment_key}: {e}")

    async def _execute_rollback(self, deployment: Dict[str, Any],
                              metrics: PerformanceMetrics, issues: List[RollbackReason]):
        """执行回退"""
        version_id = deployment["version_id"]
        version_name = deployment["version_name"]

        logger.warning(f"Triggering auto rollback for {version_name} (ID: {version_id})")

        # 创建回退记录
        rollback_action = RollbackAction(
            timestamp=datetime.now(),
            version_id=version_id,
            version_name=version_name,
            reason=issues[0] if issues else RollbackReason.ERROR_THRESHOLD,
            metrics_before=metrics
        )

        try:
            # 查找稳定的回退目标
            target_version = await self._find_rollback_target(deployment["host"])

            if target_version:
                rollback_action.target_version_id = target_version["id"]

                # 执行回退操作
                await self._perform_rollback(deployment, target_version)

                rollback_action.rollback_completed = True
                rollback_action.rollback_time = datetime.now()

                logger.info(f"Auto rollback completed: {version_name} -> {target_version['name']}")

            else:
                logger.error(f"No suitable rollback target found for {version_name}")

        except Exception as e:
            logger.error(f"Rollback execution failed for {version_name}: {e}")

        finally:
            # 记录回退历史
            self.rollback_history.append(rollback_action)

            # 限制历史记录数量
            if len(self.rollback_history) > 100:
                self.rollback_history = self.rollback_history[-100:]

    async def _find_rollback_target(self, host: str) -> Optional[Dict[str, Any]]:
        """查找回退目标版本"""
        try:
            # 查找同host下状态为prod的稳定版本
            # 这里应该调用版本管理API
            # 目前返回模拟数据
            stable_versions = [
                {
                    "id": 1,
                    "name": "baseline_agentq",
                    "status": "prod",
                    "eval_metrics": {"success_rate": 0.75, "avg_cost": 0.02}
                }
            ]

            if stable_versions:
                # 选择指标最好的稳定版本
                best_version = max(stable_versions, key=lambda v: v["eval_metrics"]["success_rate"])
                return best_version

        except Exception as e:
            logger.error(f"Failed to find rollback target: {e}")

        return None

    async def _perform_rollback(self, deployment: Dict[str, Any], target_version: Dict[str, Any]):
        """执行回退操作"""
        assignment_id = deployment["assignment_id"]

        # 1. 禁用当前A/B分配
        await self._disable_assignment(assignment_id)

        # 2. 更新版本状态为rollback
        await self._update_version_status(deployment["version_id"], "rollback")

        # 3. 创建新的分配到稳定版本（如果需要）
        if target_version["id"] != deployment["version_id"]:
            await self._create_fallback_assignment(deployment, target_version)

    async def _disable_assignment(self, assignment_id: int):
        """禁用A/B分配"""
        # 这里应该调用部署API禁用分配
        logger.info(f"Disabling assignment {assignment_id}")

    async def _update_version_status(self, version_id: int, status: str):
        """更新版本状态"""
        # 这里应该调用版本管理API更新状态
        logger.info(f"Updating version {version_id} status to {status}")

    async def _create_fallback_assignment(self, original_deployment: Dict[str, Any], target_version: Dict[str, Any]):
        """创建回退分配"""
        # 这里应该调用部署API创建新分配
        logger.info(f"Creating fallback assignment: {target_version['name']} for {original_deployment['host']}")

    def get_monitoring_status(self) -> Dict[str, Any]:
        """获取监控状态"""
        return {
            "is_running": self.is_running,
            "monitored_deployments": len(self.monitored_deployments),
            "rollback_count_24h": len([
                r for r in self.rollback_history
                if r.timestamp > datetime.now() - timedelta(days=1)
            ]),
            "thresholds": {
                "failure_rate_threshold": self.thresholds.failure_rate_threshold,
                "cost_multiplier_threshold": self.thresholds.cost_multiplier_threshold,
                "success_rate_threshold": self.thresholds.success_rate_threshold,
                "evaluation_window_minutes": self.thresholds.evaluation_window_minutes
            }
        }

    def get_deployment_health(self) -> Dict[str, Any]:
        """获取部署健康状态"""
        health_summary = {}

        for key, data in self.monitored_deployments.items():
            deployment = data["deployment"]
            health_summary[key] = {
                "version_name": deployment["version_name"],
                "host": deployment["host"],
                "health_status": data["health_status"].value,
                "issues": [issue.value for issue in data["issues"]],
                "success_rate": data["current_metrics"].success_rate,
                "failure_rate": data["current_metrics"].failure_rate,
                "avg_latency_ms": data["current_metrics"].avg_latency_ms,
                "last_check": data["last_check"].isoformat()
            }

        return health_summary

    def get_rollback_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取回退历史"""
        recent_rollbacks = self.rollback_history[-limit:]

        return [
            {
                "timestamp": r.timestamp.isoformat(),
                "version_id": r.version_id,
                "version_name": r.version_name,
                "reason": r.reason.value,
                "rollback_completed": r.rollback_completed,
                "rollback_time": r.rollback_time.isoformat() if r.rollback_time else None,
                "metrics_before": {
                    "success_rate": r.metrics_before.success_rate,
                    "failure_rate": r.metrics_before.failure_rate,
                    "avg_cost_per_run": r.metrics_before.avg_cost_per_run,
                    "avg_latency_ms": r.metrics_before.avg_latency_ms
                }
            }
            for r in reversed(recent_rollbacks)
        ]

    async def manual_rollback(self, version_id: int, reason: str = "manual_trigger") -> bool:
        """手动触发回退"""
        try:
            # 查找部署
            deployment = None
            for data in self.monitored_deployments.values():
                if data["deployment"]["version_id"] == version_id:
                    deployment = data["deployment"]
                    break

            if not deployment:
                logger.error(f"No active deployment found for version {version_id}")
                return False

            # 获取当前指标
            current_metrics = await self.metrics_collector.collect_current_metrics(
                version_id, deployment["host"]
            )

            # 执行回退
            await self._execute_rollback(
                deployment,
                current_metrics,
                [RollbackReason.MANUAL_TRIGGER]
            )

            return True

        except Exception as e:
            logger.error(f"Manual rollback failed: {e}")
            return False

# 全局自动回退服务实例
auto_rollback_service = AutoRollbackService()

# 启动和停止函数
async def start_auto_rollback_monitoring():
    """启动自动回退监控"""
    await auto_rollback_service.start_monitoring()

async def stop_auto_rollback_monitoring():
    """停止自动回退监控"""
    await auto_rollback_service.stop_monitoring()

if __name__ == "__main__":
    # 测试代码
    async def test_auto_rollback():
        """测试自动回退服务"""
        service = AutoRollbackService()

        print("Testing auto rollback service...")

        # 模拟监控周期
        await service._monitoring_cycle()

        # 获取状态
        status = service.get_monitoring_status()
        health = service.get_deployment_health()

        print("Monitoring Status:", status)
        print("Deployment Health:", health)

        # 测试手动回退
        result = await service.manual_rollback(2, "testing")
        print("Manual Rollback Result:", result)

        # 获取回退历史
        history = service.get_rollback_history(10)
        print("Rollback History:", history)

    asyncio.run(test_auto_rollback())