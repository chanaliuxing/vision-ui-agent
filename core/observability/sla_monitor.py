"""
SLA监控和告警系统
按照upgrade.md Sprint F规范实现
"""
import logging
import time
import threading
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict, deque
import statistics
import json
from pathlib import Path

logger = logging.getLogger(__name__)


class MetricType(Enum):
    SUCCESS_RATE = "success_rate"
    RESPONSE_TIME = "response_time"
    THROUGHPUT = "throughput"
    ERROR_RATE = "error_rate"
    AVAILABILITY = "availability"


class AlertLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class AlertStatus(Enum):
    ACTIVE = "active"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"


@dataclass
class SLATarget:
    """SLA目标"""
    name: str
    metric_type: MetricType
    target_value: float
    comparison: str  # ">=", "<=", "==", "!=", "<", ">"
    time_window_minutes: int = 5
    measurement_interval_seconds: int = 60
    breach_threshold_count: int = 3  # 连续违反次数触发告警


@dataclass
class MetricPoint:
    """指标数据点"""
    timestamp: datetime
    value: float
    labels: Dict[str, str] = None


@dataclass
class Alert:
    """告警"""
    alert_id: str
    timestamp: datetime
    level: AlertLevel
    status: AlertStatus
    title: str
    message: str
    metric_type: MetricType
    current_value: float
    target_value: float
    workflow_id: Optional[str] = None
    tags: Dict[str, str] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None


@dataclass
class SLAMetrics:
    """SLA指标摘要"""
    success_rate: float = 0.0
    avg_response_time_ms: float = 0.0
    p95_response_time_ms: float = 0.0
    p99_response_time_ms: float = 0.0
    throughput_per_minute: float = 0.0
    error_rate: float = 0.0
    availability: float = 0.0
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0


class MetricCollector:
    """指标收集器"""

    def __init__(self):
        self.metrics: Dict[str, List[MetricPoint]] = defaultdict(list)
        self.lock = threading.RLock()
        self.max_points_per_metric = 10000

    def record_metric(self, metric_name: str, value: float, labels: Dict[str, str] = None):
        """记录指标"""
        with self.lock:
            point = MetricPoint(
                timestamp=datetime.now(),
                value=value,
                labels=labels or {}
            )

            self.metrics[metric_name].append(point)

            # 限制数据点数量
            if len(self.metrics[metric_name]) > self.max_points_per_metric:
                self.metrics[metric_name] = self.metrics[metric_name][-self.max_points_per_metric//2:]

    def get_metric_values(self, metric_name: str, time_window_minutes: int = 5) -> List[float]:
        """获取指标值"""
        with self.lock:
            cutoff_time = datetime.now() - timedelta(minutes=time_window_minutes)
            points = [
                p.value for p in self.metrics.get(metric_name, [])
                if p.timestamp >= cutoff_time
            ]
            return points

    def get_latest_value(self, metric_name: str) -> Optional[float]:
        """获取最新值"""
        with self.lock:
            points = self.metrics.get(metric_name, [])
            return points[-1].value if points else None

    def calculate_percentile(self, values: List[float], percentile: int) -> float:
        """计算百分位数"""
        if not values:
            return 0.0
        return statistics.quantiles(sorted(values), n=100)[percentile - 1] if len(values) > 1 else values[0]


class SLAMonitor:
    """SLA监控器"""

    def __init__(self, config_path: str = "config/sla_targets.json"):
        self.config_path = Path(config_path)
        self.collector = MetricCollector()
        self.sla_targets: Dict[str, SLATarget] = {}
        self.alerts: List[Alert] = []
        self.alert_handlers: List[Callable[[Alert], None]] = []

        # 监控状态
        self.running = False
        self.monitor_thread = None

        # 时间窗口数据
        self.request_times: deque = deque(maxlen=1000)
        self.request_results: deque = deque(maxlen=1000)  # True for success, False for failure

        # 加载SLA配置
        self._load_sla_config()

    def _load_sla_config(self):
        """加载SLA配置"""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r') as f:
                    config = json.load(f)

                for target_config in config.get('sla_targets', []):
                    target = SLATarget(
                        name=target_config['name'],
                        metric_type=MetricType(target_config['metric_type']),
                        target_value=target_config['target_value'],
                        comparison=target_config['comparison'],
                        time_window_minutes=target_config.get('time_window_minutes', 5),
                        measurement_interval_seconds=target_config.get('measurement_interval_seconds', 60),
                        breach_threshold_count=target_config.get('breach_threshold_count', 3)
                    )
                    self.sla_targets[target.name] = target

                logger.info(f"Loaded {len(self.sla_targets)} SLA targets")
            else:
                self._create_default_sla_targets()

        except Exception as e:
            logger.error(f"Failed to load SLA config: {e}")
            self._create_default_sla_targets()

    def _create_default_sla_targets(self):
        """创建默认SLA目标"""
        default_targets = [
            SLATarget(
                name="workflow_success_rate",
                metric_type=MetricType.SUCCESS_RATE,
                target_value=0.95,  # 95%
                comparison=">=",
                time_window_minutes=10
            ),
            SLATarget(
                name="workflow_response_time_p95",
                metric_type=MetricType.RESPONSE_TIME,
                target_value=5000,  # 5秒
                comparison="<=",
                time_window_minutes=5
            ),
            SLATarget(
                name="hp_task_response_time",
                metric_type=MetricType.RESPONSE_TIME,
                target_value=3000,  # 3秒 (HP任务)
                comparison="<=",
                time_window_minutes=5
            ),
            SLATarget(
                name="error_rate",
                metric_type=MetricType.ERROR_RATE,
                target_value=0.05,  # 5%
                comparison="<=",
                time_window_minutes=10
            ),
            SLATarget(
                name="system_availability",
                metric_type=MetricType.AVAILABILITY,
                target_value=0.99,  # 99%
                comparison=">=",
                time_window_minutes=60
            )
        ]

        for target in default_targets:
            self.sla_targets[target.name] = target

        # 保存默认配置
        self._save_sla_config()

    def _save_sla_config(self):
        """保存SLA配置"""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)

            config = {
                'sla_targets': [
                    {
                        'name': target.name,
                        'metric_type': target.metric_type.value,
                        'target_value': target.target_value,
                        'comparison': target.comparison,
                        'time_window_minutes': target.time_window_minutes,
                        'measurement_interval_seconds': target.measurement_interval_seconds,
                        'breach_threshold_count': target.breach_threshold_count
                    }
                    for target in self.sla_targets.values()
                ]
            }

            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=2)

        except Exception as e:
            logger.error(f"Failed to save SLA config: {e}")

    def start_monitoring(self):
        """开始监控"""
        if self.running:
            return

        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()

        logger.info("SLA monitoring started")

    def stop_monitoring(self):
        """停止监控"""
        self.running = False
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5)

        logger.info("SLA monitoring stopped")

    def record_workflow_execution(self, workflow_id: str, success: bool, duration_ms: float,
                                 task_type: str = "normal"):
        """记录工作流执行"""
        timestamp = datetime.now()

        # 记录基础指标
        self.collector.record_metric("workflow_execution_success", 1.0 if success else 0.0,
                                    {"workflow_id": workflow_id, "task_type": task_type})
        self.collector.record_metric("workflow_execution_duration_ms", duration_ms,
                                    {"workflow_id": workflow_id, "task_type": task_type})

        # 添加到时间窗口数据
        self.request_times.append((timestamp, duration_ms, task_type))
        self.request_results.append((timestamp, success, task_type))

        # 记录特定任务类型的指标
        if task_type == "hp":
            self.collector.record_metric("hp_task_duration_ms", duration_ms, {"workflow_id": workflow_id})

        logger.debug(f"Recorded workflow execution: {workflow_id} ({duration_ms:.0f}ms, success={success})")

    def record_error(self, error_type: str, workflow_id: str = None):
        """记录错误"""
        self.collector.record_metric("error_count", 1.0,
                                    {"error_type": error_type, "workflow_id": workflow_id or "unknown"})

    def record_system_health(self, is_healthy: bool):
        """记录系统健康状态"""
        self.collector.record_metric("system_health", 1.0 if is_healthy else 0.0)

    def get_current_sla_metrics(self, time_window_minutes: int = 10) -> SLAMetrics:
        """获取当前SLA指标"""
        cutoff_time = datetime.now() - timedelta(minutes=time_window_minutes)

        # 过滤时间窗口内的数据
        recent_times = [(t, d, tt) for t, d, tt in self.request_times if t >= cutoff_time]
        recent_results = [(t, s, tt) for t, s, tt in self.request_results if t >= cutoff_time]

        # 计算指标
        total_requests = len(recent_results)
        successful_requests = sum(1 for _, success, _ in recent_results if success)
        failed_requests = total_requests - successful_requests

        success_rate = successful_requests / total_requests if total_requests > 0 else 0.0
        error_rate = failed_requests / total_requests if total_requests > 0 else 0.0

        # 响应时间指标
        durations = [d for _, d, _ in recent_times]
        avg_response_time = statistics.mean(durations) if durations else 0.0
        p95_response_time = self.collector.calculate_percentile(durations, 95) if durations else 0.0
        p99_response_time = self.collector.calculate_percentile(durations, 99) if durations else 0.0

        # 吞吐量
        throughput = total_requests / time_window_minutes if time_window_minutes > 0 else 0.0

        # 可用性
        health_values = self.collector.get_metric_values("system_health", time_window_minutes)
        availability = statistics.mean(health_values) if health_values else 1.0

        return SLAMetrics(
            success_rate=success_rate,
            avg_response_time_ms=avg_response_time,
            p95_response_time_ms=p95_response_time,
            p99_response_time_ms=p99_response_time,
            throughput_per_minute=throughput,
            error_rate=error_rate,
            availability=availability,
            total_requests=total_requests,
            successful_requests=successful_requests,
            failed_requests=failed_requests
        )

    def add_alert_handler(self, handler: Callable[[Alert], None]):
        """添加告警处理器"""
        self.alert_handlers.append(handler)

    def _monitor_loop(self):
        """监控循环"""
        breach_counts = defaultdict(int)
        last_check_times = {}

        while self.running:
            try:
                current_time = datetime.now()

                for target_name, target in self.sla_targets.items():
                    # 检查测量间隔
                    last_check = last_check_times.get(target_name, datetime.min)
                    if (current_time - last_check).total_seconds() < target.measurement_interval_seconds:
                        continue

                    last_check_times[target_name] = current_time

                    # 计算当前指标值
                    current_value = self._calculate_metric_value(target)
                    if current_value is None:
                        continue

                    # 检查是否违反SLA
                    is_breached = self._is_sla_breached(current_value, target)

                    if is_breached:
                        breach_counts[target_name] += 1
                        if breach_counts[target_name] >= target.breach_threshold_count:
                            self._trigger_alert(target, current_value)
                            breach_counts[target_name] = 0  # 重置计数
                    else:
                        breach_counts[target_name] = 0
                        self._resolve_alerts(target)

                time.sleep(10)  # 每10秒检查一次

            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
                time.sleep(5)

    def _calculate_metric_value(self, target: SLATarget) -> Optional[float]:
        """计算指标值"""
        if target.metric_type == MetricType.SUCCESS_RATE:
            cutoff_time = datetime.now() - timedelta(minutes=target.time_window_minutes)
            recent_results = [(t, s, tt) for t, s, tt in self.request_results if t >= cutoff_time]
            if not recent_results:
                return None
            successful = sum(1 for _, success, _ in recent_results if success)
            return successful / len(recent_results)

        elif target.metric_type == MetricType.RESPONSE_TIME:
            if target.name == "hp_task_response_time":
                # HP任务特殊处理
                cutoff_time = datetime.now() - timedelta(minutes=target.time_window_minutes)
                hp_times = [d for t, d, tt in self.request_times
                           if t >= cutoff_time and tt == "hp"]
                return self.collector.calculate_percentile(hp_times, 95) if hp_times else None
            else:
                # 一般响应时间
                cutoff_time = datetime.now() - timedelta(minutes=target.time_window_minutes)
                recent_times = [d for t, d, tt in self.request_times if t >= cutoff_time]
                return self.collector.calculate_percentile(recent_times, 95) if recent_times else None

        elif target.metric_type == MetricType.ERROR_RATE:
            cutoff_time = datetime.now() - timedelta(minutes=target.time_window_minutes)
            recent_results = [(t, s, tt) for t, s, tt in self.request_results if t >= cutoff_time]
            if not recent_results:
                return None
            failed = sum(1 for _, success, _ in recent_results if not success)
            return failed / len(recent_results)

        elif target.metric_type == MetricType.AVAILABILITY:
            health_values = self.collector.get_metric_values("system_health", target.time_window_minutes)
            return statistics.mean(health_values) if health_values else None

        elif target.metric_type == MetricType.THROUGHPUT:
            cutoff_time = datetime.now() - timedelta(minutes=target.time_window_minutes)
            recent_count = len([(t, s, tt) for t, s, tt in self.request_results if t >= cutoff_time])
            return recent_count / target.time_window_minutes

        return None

    def _is_sla_breached(self, current_value: float, target: SLATarget) -> bool:
        """检查SLA是否违反"""
        if target.comparison == ">=":
            return current_value < target.target_value
        elif target.comparison == "<=":
            return current_value > target.target_value
        elif target.comparison == "==":
            return current_value != target.target_value
        elif target.comparison == "!=":
            return current_value == target.target_value
        elif target.comparison == "<":
            return current_value >= target.target_value
        elif target.comparison == ">":
            return current_value <= target.target_value
        return False

    def _trigger_alert(self, target: SLATarget, current_value: float):
        """触发告警"""
        # 检查是否已有活跃告警
        existing_alerts = [a for a in self.alerts
                          if a.metric_type == target.metric_type and a.status == AlertStatus.ACTIVE]
        if existing_alerts:
            return

        # 确定告警级别
        deviation = abs(current_value - target.target_value) / target.target_value
        if deviation > 0.5:
            level = AlertLevel.CRITICAL
        elif deviation > 0.2:
            level = AlertLevel.WARNING
        else:
            level = AlertLevel.INFO

        # 创建告警
        alert = Alert(
            alert_id=f"sla_{target.name}_{int(time.time())}",
            timestamp=datetime.now(),
            level=level,
            status=AlertStatus.ACTIVE,
            title=f"SLA Breach: {target.name}",
            message=f"SLA target '{target.name}' breached. Current: {current_value:.4f}, Target: {target.comparison} {target.target_value}",
            metric_type=target.metric_type,
            current_value=current_value,
            target_value=target.target_value,
            tags={"sla_target": target.name}
        )

        self.alerts.append(alert)

        # 触发告警处理器
        for handler in self.alert_handlers:
            try:
                handler(alert)
            except Exception as e:
                logger.error(f"Alert handler error: {e}")

        logger.warning(f"SLA alert triggered: {alert.title}")

    def _resolve_alerts(self, target: SLATarget):
        """解决告警"""
        for alert in self.alerts:
            if (alert.metric_type == target.metric_type and
                alert.status == AlertStatus.ACTIVE and
                alert.tags.get("sla_target") == target.name):

                alert.status = AlertStatus.RESOLVED
                alert.resolved_at = datetime.now()

                logger.info(f"SLA alert resolved: {alert.title}")

    def get_active_alerts(self) -> List[Alert]:
        """获取活跃告警"""
        return [a for a in self.alerts if a.status == AlertStatus.ACTIVE]

    def get_sla_dashboard_data(self) -> Dict:
        """获取SLA仪表盘数据"""
        current_metrics = self.get_current_sla_metrics()
        active_alerts = self.get_active_alerts()

        return {
            "timestamp": datetime.now().isoformat(),
            "metrics": asdict(current_metrics),
            "sla_targets": {
                name: {
                    "target_value": target.target_value,
                    "comparison": target.comparison,
                    "current_value": self._calculate_metric_value(target),
                    "is_meeting_sla": not self._is_sla_breached(
                        self._calculate_metric_value(target) or 0, target
                    ) if self._calculate_metric_value(target) is not None else None
                }
                for name, target in self.sla_targets.items()
            },
            "alerts": [
                {
                    "alert_id": alert.alert_id,
                    "level": alert.level.value,
                    "title": alert.title,
                    "message": alert.message,
                    "timestamp": alert.timestamp.isoformat(),
                    "current_value": alert.current_value,
                    "target_value": alert.target_value
                }
                for alert in active_alerts
            ]
        }


# 全局SLA监控器
sla_monitor = SLAMonitor()