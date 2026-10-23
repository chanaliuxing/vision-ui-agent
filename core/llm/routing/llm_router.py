"""
LLM路由和负载均衡
按照upgrade.md Sprint D规范实现
"""
import logging
import random
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class ProviderStatus(Enum):
    ACTIVE = "active"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass
class ProviderConfig:
    """LLM提供商配置"""
    provider: str
    model: str
    api_key: str
    base_url: Optional[str] = None
    priority: int = 1  # 1-10, 10最高
    max_tokens_per_minute: int = 100000
    max_requests_per_minute: int = 100
    cost_per_input_token: float = 0.000001
    cost_per_output_token: float = 0.000002
    timeout_seconds: int = 30
    retry_count: int = 3


@dataclass
class ProviderHealth:
    """提供商健康状态"""
    provider: str
    status: ProviderStatus
    success_rate: float
    avg_latency_ms: float
    last_error: Optional[str] = None
    last_success: Optional[datetime] = None
    consecutive_failures: int = 0
    tokens_used_current_minute: int = 0
    requests_used_current_minute: int = 0
    minute_window_start: datetime = None


class LLMRouter:
    """LLM路由器 - 智能选择最优提供商"""

    def __init__(self):
        self.providers: Dict[str, ProviderConfig] = {}
        self.health: Dict[str, ProviderHealth] = {}
        self.request_history: List[Dict] = []
        self.fallback_chain: List[str] = []

    def register_provider(self, config: ProviderConfig):
        """注册LLM提供商"""
        provider_key = f"{config.provider}:{config.model}"
        self.providers[provider_key] = config

        self.health[provider_key] = ProviderHealth(
            provider=provider_key,
            status=ProviderStatus.ACTIVE,
            success_rate=1.0,
            avg_latency_ms=1000.0,
            minute_window_start=datetime.now()
        )

        logger.info(f"Registered LLM provider: {provider_key}")

    def set_fallback_chain(self, chain: List[str]):
        """设置降级链"""
        self.fallback_chain = chain
        logger.info(f"Set fallback chain: {chain}")

    def select_provider(self,
                       user_id: str,
                       estimated_tokens: int = 1000,
                       job_type: str = "submit",
                       preferred_provider: str = None) -> Optional[ProviderConfig]:
        """智能选择最优提供商"""

        # 更新健康状态
        self._update_health_metrics()

        # 如果指定了首选提供商，先尝试
        if preferred_provider and preferred_provider in self.providers:
            if self._can_handle_request(preferred_provider, estimated_tokens):
                return self.providers[preferred_provider]

        # 按优先级和健康状态排序
        candidates = []
        for provider_key, config in self.providers.items():
            health = self.health[provider_key]

            # 检查是否可用
            if not self._can_handle_request(provider_key, estimated_tokens):
                continue

            # 计算综合评分
            score = self._calculate_provider_score(provider_key, job_type)
            candidates.append((score, provider_key, config))

        if not candidates:
            logger.warning("No available LLM providers for request")
            return None

        # 按评分排序，选择最优
        candidates.sort(key=lambda x: x[0], reverse=True)
        selected = candidates[0][2]

        logger.info(f"Selected LLM provider: {selected.provider}:{selected.model}")
        return selected

    def record_request(self,
                      provider_key: str,
                      success: bool,
                      latency_ms: float,
                      tokens_used: int,
                      error: str = None):
        """记录请求结果"""

        health = self.health.get(provider_key)
        if not health:
            return

        # 更新健康指标
        if success:
            health.consecutive_failures = 0
            health.last_success = datetime.now()
        else:
            health.consecutive_failures += 1
            health.last_error = error

        # 更新速率限制计数
        now = datetime.now()
        if health.minute_window_start is None or (now - health.minute_window_start).seconds >= 60:
            health.minute_window_start = now
            health.tokens_used_current_minute = 0
            health.requests_used_current_minute = 0

        health.tokens_used_current_minute += tokens_used
        health.requests_used_current_minute += 1

        # 记录历史
        self.request_history.append({
            "timestamp": now.isoformat(),
            "provider": provider_key,
            "success": success,
            "latency_ms": latency_ms,
            "tokens_used": tokens_used,
            "error": error
        })

        # 限制历史记录大小
        if len(self.request_history) > 1000:
            self.request_history = self.request_history[-500:]

        logger.info(f"Recorded request: {provider_key} - {'✓' if success else '✗'} {latency_ms:.0f}ms")

    def get_provider_status(self) -> Dict:
        """获取所有提供商状态"""
        self._update_health_metrics()

        status = {}
        for provider_key, health in self.health.items():
            config = self.providers[provider_key]

            status[provider_key] = {
                "status": health.status.value,
                "success_rate": health.success_rate,
                "avg_latency_ms": health.avg_latency_ms,
                "consecutive_failures": health.consecutive_failures,
                "last_success": health.last_success.isoformat() if health.last_success else None,
                "last_error": health.last_error,
                "priority": config.priority,
                "tokens_remaining_this_minute": config.max_tokens_per_minute - health.tokens_used_current_minute,
                "requests_remaining_this_minute": config.max_requests_per_minute - health.requests_used_current_minute
            }

        return status

    def _can_handle_request(self, provider_key: str, estimated_tokens: int) -> bool:
        """检查提供商是否能处理请求"""
        health = self.health.get(provider_key)
        config = self.providers.get(provider_key)

        if not health or not config:
            return False

        # 检查状态
        if health.status == ProviderStatus.UNAVAILABLE:
            return False

        # 检查连续失败次数
        if health.consecutive_failures >= 5:
            return False

        # 检查速率限制
        if health.tokens_used_current_minute + estimated_tokens > config.max_tokens_per_minute:
            return False

        if health.requests_used_current_minute >= config.max_requests_per_minute:
            return False

        return True

    def _calculate_provider_score(self, provider_key: str, job_type: str) -> float:
        """计算提供商评分"""
        health = self.health[provider_key]
        config = self.providers[provider_key]

        # 基础评分 = 优先级
        score = config.priority * 10

        # 成功率权重 (0-50分)
        score += health.success_rate * 50

        # 延迟权重 (0-20分，延迟越低越好)
        latency_score = max(0, 20 - (health.avg_latency_ms / 1000) * 10)
        score += latency_score

        # 可用容量权重 (0-20分)
        tokens_available_ratio = (config.max_tokens_per_minute - health.tokens_used_current_minute) / config.max_tokens_per_minute
        score += tokens_available_ratio * 20

        # 状态权重
        if health.status == ProviderStatus.DEGRADED:
            score *= 0.7
        elif health.status == ProviderStatus.UNAVAILABLE:
            score = 0

        return score

    def _update_health_metrics(self):
        """更新健康指标"""
        now = datetime.now()
        window_start = now - timedelta(minutes=5)  # 5分钟窗口

        for provider_key, health in self.health.items():
            # 获取最近5分钟的请求
            recent_requests = [
                r for r in self.request_history
                if r["provider"] == provider_key and
                datetime.fromisoformat(r["timestamp"]) > window_start
            ]

            if recent_requests:
                # 计算成功率
                successful = [r for r in recent_requests if r["success"]]
                health.success_rate = len(successful) / len(recent_requests)

                # 计算平均延迟
                if successful:
                    health.avg_latency_ms = sum(r["latency_ms"] for r in successful) / len(successful)

            # 更新状态
            if health.consecutive_failures >= 5:
                health.status = ProviderStatus.UNAVAILABLE
            elif health.success_rate < 0.8:
                health.status = ProviderStatus.DEGRADED
            else:
                health.status = ProviderStatus.ACTIVE


# 全局路由器实例
llm_router = LLMRouter()