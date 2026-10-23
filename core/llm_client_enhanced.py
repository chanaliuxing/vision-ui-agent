"""
增强的LLM客户端 - 集成Sprint D的配额和密钥管理功能
将现有的core/llm_client.py与runtime/actions/llm.py集成
"""
import os
import json
from typing import Any, Dict, List, Optional
from .llm_client import LLMClient as BaseLLMClient, call_llm, extract_text_generic
from runtime.actions.llm import (
    quota_manager, key_manager, routing_strategy,
    LLMProvider, LLMUsage, LLMQuotaManager
)
import time
from datetime import datetime


class EnhancedLLMClient(BaseLLMClient):
    """增强的LLM客户端，支持配额管理和密钥管理"""

    def __init__(self, provider: str = "gemini", model: str = "gemini-1.5-flash",
                 user_id: str = "default"):
        super().__init__(provider, model)
        self.user_id = user_id

    def generate_response(self, messages: List[Dict[str, Any]],
                         image_path: Optional[str] = None,
                         quality: str = "balanced") -> Dict[str, Any]:
        """带配额检查的响应生成"""
        start_time = time.time()

        # 1. 配额检查
        can_proceed, quota_msg = quota_manager.check_quota(self.user_id)
        if not can_proceed:
            raise RuntimeError(f"Quota exceeded: {quota_msg}")

        # 2. 提供商选择（如果是auto）
        provider = self.provider
        if provider == "auto":
            selected_provider = routing_strategy.select_provider("submit", quality)
            provider = selected_provider.value

        # 3. 调用原始LLM方法
        response = call_llm(
            provider=provider,
            model=self.model,
            messages=messages,
            image_path=image_path
        )

        # 4. 记录使用量
        duration_ms = int((time.time() - start_time) * 1000)

        # 估算token使用量
        input_text = ""
        for msg in messages:
            parts = msg.get("parts", [])
            for part in parts:
                if "text" in part:
                    input_text += part["text"]

        output_text = extract_text_generic(response)

        usage = LLMUsage(
            provider=provider,
            model=self.model,
            input_tokens=len(input_text) // 4,
            output_tokens=len(output_text) // 4,
            cost_usd=len(input_text) * 0.00001,  # 简化成本计算
            duration_ms=duration_ms,
            timestamp=datetime.now()
        )

        quota_manager.record_usage(self.user_id, usage)

        # 5. 返回增强响应
        return {
            "response": response,
            "usage": {
                "provider": provider,
                "model": self.model,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "cost_usd": usage.cost_usd,
                "duration_ms": duration_ms
            },
            "quota_remaining": {
                "requests": quota_manager.get_quota(self.user_id).daily_requests - quota_manager.get_quota(self.user_id).used_requests_today,
                "tokens": quota_manager.get_quota(self.user_id).daily_tokens - quota_manager.get_quota(self.user_id).used_tokens_today
            }
        }

    def generate_json(self, prompt: str, image_path: Optional[str] = None,
                     quality: str = "balanced") -> Dict[str, Any]:
        """带配额检查的JSON生成"""
        messages = [{"role": "user", "parts": [{"text": prompt}]}]
        enhanced_response = self.generate_response(messages, image_path, quality)

        # 从原始响应中提取JSON
        original_response = enhanced_response["response"]
        text = extract_text_generic(original_response)

        try:
            json_data = json.loads(text)
        except json.JSONDecodeError:
            from .gemini_client import parse_first_json
            json_data = parse_first_json(text)
            if json_data is None:
                raise RuntimeError("Failed to parse JSON from LLM response")

        return {
            "data": json_data,
            "usage": enhanced_response["usage"],
            "quota_remaining": enhanced_response["quota_remaining"]
        }

    def get_quota_status(self) -> Dict[str, Any]:
        """获取当前用户的配额状态"""
        from runtime.actions.llm import get_quota_status
        return get_quota_status(self.user_id)


# 便利函数：创建增强客户端
def create_enhanced_client(provider: str = None, model: str = None,
                          user_id: str = "default") -> EnhancedLLMClient:
    """创建增强LLM客户端"""
    provider = provider or os.getenv("LLM_PROVIDER", "gemini")
    model = model or os.getenv("LLM_MODEL", "gemini-1.5-flash")
    return EnhancedLLMClient(provider, model, user_id)


# 兼容性包装器：使现有代码无缝迁移
def call_llm_with_quota(provider: Optional[str], model: Optional[str],
                       messages: List[Dict[str, Any]],
                       image_path: Optional[str] = None,
                       user_id: str = "default",
                       quality: str = "balanced") -> Dict[str, Any]:
    """
    兼容性包装器：为现有的call_llm添加配额管理
    返回格式：{response: 原始响应, usage: 使用统计, quota_remaining: 剩余配额}
    """
    client = create_enhanced_client(provider, model, user_id)
    return client.generate_response(messages, image_path, quality)


def generate_json_with_quota(provider: Optional[str], model: Optional[str],
                           prompt: str, image_path: Optional[str] = None,
                           user_id: str = "default",
                           quality: str = "balanced") -> Dict[str, Any]:
    """
    兼容性包装器：为现有的generate_json添加配额管理
    返回格式：{data: JSON数据, usage: 使用统计, quota_remaining: 剩余配额}
    """
    client = create_enhanced_client(provider, model, user_id)
    return client.generate_json(prompt, image_path, quality)


# 配额管理API
def set_user_quota(user_id: str, daily_requests: int = 1000,
                  daily_tokens: int = 100000, daily_cost_usd: float = 50.0):
    """设置用户配额"""
    quota = quota_manager.get_quota(user_id)
    quota.daily_requests = daily_requests
    quota.daily_tokens = daily_tokens
    quota.daily_cost_usd = daily_cost_usd


def get_all_quota_status() -> Dict[str, Dict]:
    """获取所有用户的配额状态"""
    from runtime.actions.llm import get_quota_status
    result = {}
    for user_id in quota_manager.quotas.keys():
        result[user_id] = get_quota_status(user_id)
    return result


# 密钥管理API
def admin_set_api_key(provider: str, key: str, admin_user: str):
    """管理员设置API密钥"""
    from runtime.actions.llm import set_api_key
    set_api_key(provider, key, admin_user)


def admin_view_all_keys(admin_user: str) -> Dict[str, str]:
    """管理员查看所有PLAINTEXT密钥"""
    from runtime.actions.llm import admin_view_keys
    return admin_view_keys(admin_user)


def get_key_audit_log() -> List[Dict]:
    """获取密钥审计日志"""
    from runtime.actions.llm import get_key_audit_log
    return get_key_audit_log()