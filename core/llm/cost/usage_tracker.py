"""
LLM使用量追踪和成本控制
按照upgrade.md Sprint D规范实现
"""
import logging
import json
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class UsageRecord:
    """使用量记录"""
    timestamp: str
    user_id: str
    workflow_id: str
    device_id: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    duration_ms: int
    job_type: str  # "plan", "submit", "chat"
    success: bool


class UsageTracker:
    def __init__(self):
        self.records: List[UsageRecord] = []
        self.cost_per_token = {
            # 模拟价格（实际应从配置获取）
            "gemini-1.5-flash": {"input": 0.000001, "output": 0.000002},
            "gpt-4o": {"input": 0.000005, "output": 0.000015},
            "claude-3.5-sonnet": {"input": 0.000003, "output": 0.000015},
            "deepseek-v2": {"input": 0.0000001, "output": 0.0000002}
        }
        self.quota_limits = {}  # user_id -> quota config

    def record_usage(self,
                    user_id: str,
                    workflow_id: str,
                    device_id: str,
                    provider: str,
                    model: str,
                    prompt_tokens: int,
                    completion_tokens: int,
                    duration_ms: int,
                    job_type: str = "submit",
                    success: bool = True) -> UsageRecord:
        """记录使用量"""

        # 计算成本
        model_pricing = self.cost_per_token.get(model, {"input": 0.000001, "output": 0.000002})
        cost_usd = (prompt_tokens * model_pricing["input"] +
                   completion_tokens * model_pricing["output"])

        record = UsageRecord(
            timestamp=datetime.now().isoformat(),
            user_id=user_id,
            workflow_id=workflow_id,
            device_id=device_id,
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            cost_usd=cost_usd,
            duration_ms=duration_ms,
            job_type=job_type,
            success=success
        )

        self.records.append(record)
        logger.info(f"Recorded usage: {model} - {prompt_tokens}/{completion_tokens} tokens, ${cost_usd:.6f}")

        return record

    def check_quota(self, user_id: str, estimated_tokens: int = 0) -> Dict:
        """检查配额"""
        now = datetime.now()

        # 获取用户配额配置
        default_config = {
            "daily_tokens": 100000,
            "daily_cost_usd": 10.0,
            "monthly_tokens": 2000000,
            "monthly_cost_usd": 200.0
        }
        quota_config = self.quota_limits.get(user_id, {})
        for key, value in default_config.items():
            if key not in quota_config:
                quota_config[key] = value

        # 计算今日使用量
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_usage = self._get_usage_in_period(user_id, today_start, now)

        # 计算本月使用量
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_usage = self._get_usage_in_period(user_id, month_start, now)

        # 检查限额
        quota_status = {
            "user_id": user_id,
            "within_quota": True,
            "daily": {
                "tokens_used": today_usage["total_tokens"],
                "tokens_limit": quota_config["daily_tokens"],
                "cost_used": today_usage["total_cost"],
                "cost_limit": quota_config["daily_cost_usd"],
                "remaining_tokens": quota_config["daily_tokens"] - today_usage["total_tokens"],
                "remaining_cost": quota_config["daily_cost_usd"] - today_usage["total_cost"]
            },
            "monthly": {
                "tokens_used": month_usage["total_tokens"],
                "tokens_limit": quota_config["monthly_tokens"],
                "cost_used": month_usage["total_cost"],
                "cost_limit": quota_config["monthly_cost_usd"],
                "remaining_tokens": quota_config["monthly_tokens"] - month_usage["total_tokens"],
                "remaining_cost": quota_config["monthly_cost_usd"] - month_usage["total_cost"]
            }
        }

        # 检查是否超限
        if (today_usage["total_tokens"] + estimated_tokens > quota_config["daily_tokens"] or
            month_usage["total_tokens"] + estimated_tokens > quota_config["monthly_tokens"]):
            quota_status["within_quota"] = False
            quota_status["reason"] = "Token limit exceeded"

        if (today_usage["total_cost"] > quota_config["daily_cost_usd"] or
            month_usage["total_cost"] > quota_config["monthly_cost_usd"]):
            quota_status["within_quota"] = False
            quota_status["reason"] = "Cost limit exceeded"

        return quota_status

    def get_usage_summary(self, user_id: str, period_days: int = 7) -> Dict:
        """获取使用量摘要"""
        end_time = datetime.now()
        start_time = end_time - timedelta(days=period_days)

        usage = self._get_usage_in_period(user_id, start_time, end_time)

        # 按provider分组统计
        provider_stats = {}
        workflow_stats = {}

        user_records = [r for r in self.records if r.user_id == user_id]

        for record in user_records:
            record_time = datetime.fromisoformat(record.timestamp)
            if start_time <= record_time <= end_time:
                # Provider统计
                if record.provider not in provider_stats:
                    provider_stats[record.provider] = {
                        "tokens": 0, "cost": 0.0, "requests": 0
                    }
                provider_stats[record.provider]["tokens"] += record.total_tokens
                provider_stats[record.provider]["cost"] += record.cost_usd
                provider_stats[record.provider]["requests"] += 1

                # Workflow统计
                if record.workflow_id not in workflow_stats:
                    workflow_stats[record.workflow_id] = {
                        "tokens": 0, "cost": 0.0, "requests": 0
                    }
                workflow_stats[record.workflow_id]["tokens"] += record.total_tokens
                workflow_stats[record.workflow_id]["cost"] += record.cost_usd
                workflow_stats[record.workflow_id]["requests"] += 1

        return {
            "user_id": user_id,
            "period_days": period_days,
            "total_tokens": usage["total_tokens"],
            "total_cost": usage["total_cost"],
            "total_requests": usage["total_requests"],
            "by_provider": provider_stats,
            "by_workflow": workflow_stats
        }

    def _get_usage_in_period(self, user_id: str, start_time: datetime, end_time: datetime) -> Dict:
        """获取时间段内的使用量"""
        total_tokens = 0
        total_cost = 0.0
        total_requests = 0

        user_records = [r for r in self.records if r.user_id == user_id]

        for record in user_records:
            record_time = datetime.fromisoformat(record.timestamp)
            if start_time <= record_time <= end_time:
                total_tokens += record.total_tokens
                total_cost += record.cost_usd
                total_requests += 1

        return {
            "total_tokens": total_tokens,
            "total_cost": total_cost,
            "total_requests": total_requests
        }

    def set_quota_limits(self, user_id: str, quota_config: Dict):
        """设置用户配额"""
        self.quota_limits[user_id] = quota_config
        logger.info(f"Updated quota for user {user_id}: {quota_config}")

    def get_cost_analysis(self, period_days: int = 30) -> Dict:
        """获取成本分析"""
        end_time = datetime.now()
        start_time = end_time - timedelta(days=period_days)

        # 按模型统计成本
        model_costs = {}
        daily_costs = {}

        for record in self.records:
            record_time = datetime.fromisoformat(record.timestamp)
            if start_time <= record_time <= end_time:
                # 按模型统计
                model = record.model
                if model not in model_costs:
                    model_costs[model] = {
                        "cost": 0.0, "tokens": 0, "requests": 0
                    }
                model_costs[model]["cost"] += record.cost_usd
                model_costs[model]["tokens"] += record.total_tokens
                model_costs[model]["requests"] += 1

                # 按日期统计
                date_key = record_time.date().isoformat()
                if date_key not in daily_costs:
                    daily_costs[date_key] = 0.0
                daily_costs[date_key] += record.cost_usd

        # 计算趋势
        total_cost = sum(model_costs[m]["cost"] for m in model_costs)
        avg_daily_cost = total_cost / period_days if period_days > 0 else 0

        return {
            "period_days": period_days,
            "total_cost": total_cost,
            "avg_daily_cost": avg_daily_cost,
            "by_model": model_costs,
            "daily_breakdown": daily_costs,
            "most_expensive_model": max(model_costs.keys(), key=lambda m: model_costs[m]["cost"]) if model_costs else None
        }


# 全局使用量追踪器
usage_tracker = UsageTracker()