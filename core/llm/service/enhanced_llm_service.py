"""
增强的LLM服务 - 集成成本控制、路由和密钥管理
按照upgrade.md Sprint D规范实现
"""
import logging
import time
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from datetime import datetime

from ..cost.usage_tracker import usage_tracker, UsageRecord
from ..routing.llm_router import llm_router, ProviderConfig
from ..keys.key_manager import key_manager
from ...llm_client import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class LLMRequest:
    """LLM请求"""
    user_id: str
    workflow_id: str
    device_id: str
    job_type: str  # "plan", "submit", "chat"
    messages: List[Dict]
    temperature: float = 0.7
    max_tokens: int = 1000
    preferred_provider: str = None
    estimated_input_tokens: int = None


@dataclass
class LLMResponse:
    """LLM响应"""
    success: bool
    content: str = None
    usage_record: UsageRecord = None
    provider_used: str = None
    model_used: str = None
    latency_ms: float = None
    error: str = None
    quota_status: Dict = None


class EnhancedLLMService:
    """增强的LLM服务"""

    def __init__(self):
        self.llm_client = LLMClient()

        # 初始化默认提供商配置
        self._setup_default_providers()

    def _setup_default_providers(self):
        """设置默认提供商配置"""

        # Gemini配置
        gemini_config = ProviderConfig(
            provider="gemini",
            model="gemini-1.5-flash",
            api_key="",  # 从key_manager获取
            priority=8,
            max_tokens_per_minute=100000,
            max_requests_per_minute=60,
            cost_per_input_token=0.000000075,
            cost_per_output_token=0.0000003,
            timeout_seconds=30
        )
        llm_router.register_provider(gemini_config)

        # GPT-4o配置
        gpt4_config = ProviderConfig(
            provider="openai",
            model="gpt-4o",
            api_key="",
            priority=9,
            max_tokens_per_minute=80000,
            max_requests_per_minute=50,
            cost_per_input_token=0.000005,
            cost_per_output_token=0.000015,
            timeout_seconds=30
        )
        llm_router.register_provider(gpt4_config)

        # Claude配置
        claude_config = ProviderConfig(
            provider="anthropic",
            model="claude-3.5-sonnet",
            api_key="",
            priority=10,
            max_tokens_per_minute=60000,
            max_requests_per_minute=40,
            cost_per_input_token=0.000003,
            cost_per_output_token=0.000015,
            timeout_seconds=45
        )
        llm_router.register_provider(claude_config)

        # DeepSeek配置
        deepseek_config = ProviderConfig(
            provider="deepseek",
            model="deepseek-v2",
            api_key="",
            priority=6,
            max_tokens_per_minute=150000,
            max_requests_per_minute=100,
            cost_per_input_token=0.0000001,
            cost_per_output_token=0.0000002,
            timeout_seconds=20
        )
        llm_router.register_provider(deepseek_config)

        # 设置降级链
        llm_router.set_fallback_chain([
            "anthropic:claude-3.5-sonnet",
            "openai:gpt-4o",
            "gemini:gemini-1.5-flash",
            "deepseek:deepseek-v2"
        ])

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """生成LLM响应"""
        start_time = time.time()

        try:
            # 1. 检查用户配额
            estimated_tokens = request.estimated_input_tokens or self._estimate_tokens(request.messages)
            quota_status = usage_tracker.check_quota(request.user_id, estimated_tokens)

            if not quota_status["within_quota"]:
                return LLMResponse(
                    success=False,
                    error=f"Quota exceeded: {quota_status.get('reason', 'Unknown')}",
                    quota_status=quota_status
                )

            # 2. 选择最优提供商
            provider_config = llm_router.select_provider(
                user_id=request.user_id,
                estimated_tokens=estimated_tokens,
                job_type=request.job_type,
                preferred_provider=request.preferred_provider
            )

            if not provider_config:
                return LLMResponse(
                    success=False,
                    error="No available LLM providers",
                    quota_status=quota_status
                )

            # 3. 获取API密钥
            api_key = key_manager.get_key(
                provider=provider_config.provider,
                model=provider_config.model,
                user_id=request.user_id
            )

            if not api_key:
                return LLMResponse(
                    success=False,
                    error=f"No available API key for {provider_config.provider}:{provider_config.model}",
                    quota_status=quota_status
                )

            # 4. 执行LLM调用
            response_content, token_usage = await self._call_llm(
                provider_config=provider_config,
                api_key=api_key,
                request=request
            )

            latency_ms = (time.time() - start_time) * 1000
            provider_key = f"{provider_config.provider}:{provider_config.model}"

            # 5. 记录使用量
            usage_record = usage_tracker.record_usage(
                user_id=request.user_id,
                workflow_id=request.workflow_id,
                device_id=request.device_id,
                provider=provider_config.provider,
                model=provider_config.model,
                prompt_tokens=token_usage.get("prompt_tokens", estimated_tokens),
                completion_tokens=token_usage.get("completion_tokens", 0),
                duration_ms=int(latency_ms),
                job_type=request.job_type,
                success=True
            )

            # 6. 记录路由统计
            llm_router.record_request(
                provider_key=provider_key,
                success=True,
                latency_ms=latency_ms,
                tokens_used=usage_record.total_tokens
            )

            return LLMResponse(
                success=True,
                content=response_content,
                usage_record=usage_record,
                provider_used=provider_config.provider,
                model_used=provider_config.model,
                latency_ms=latency_ms,
                quota_status=quota_status
            )

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            error_msg = str(e)

            # 记录失败
            if 'provider_config' in locals():
                provider_key = f"{provider_config.provider}:{provider_config.model}"
                llm_router.record_request(
                    provider_key=provider_key,
                    success=False,
                    latency_ms=latency_ms,
                    tokens_used=0,
                    error=error_msg
                )

            logger.error(f"LLM generation failed: {error_msg}")
            return LLMResponse(
                success=False,
                error=error_msg,
                latency_ms=latency_ms,
                quota_status=quota_status if 'quota_status' in locals() else None
            )

    async def _call_llm(self,
                        provider_config: ProviderConfig,
                        api_key: str,
                        request: LLMRequest) -> tuple[str, Dict]:
        """调用LLM API"""

        # 设置临时API密钥
        original_key = None
        if provider_config.provider == "gemini":
            import os
            original_key = os.environ.get("GOOGLE_API_KEY")
            os.environ["GOOGLE_API_KEY"] = api_key
        elif provider_config.provider == "openai":
            import os
            original_key = os.environ.get("OPENAI_API_KEY")
            os.environ["OPENAI_API_KEY"] = api_key
        elif provider_config.provider == "anthropic":
            import os
            original_key = os.environ.get("ANTHROPIC_API_KEY")
            os.environ["ANTHROPIC_API_KEY"] = api_key
        elif provider_config.provider == "deepseek":
            import os
            original_key = os.environ.get("DEEPSEEK_API_KEY")
            os.environ["DEEPSEEK_API_KEY"] = api_key

        try:
            # 调用LLM
            response = await self.llm_client.generate_async(
                provider=provider_config.provider,
                model=provider_config.model,
                messages=request.messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens
            )

            # 提取token使用量
            token_usage = {
                "prompt_tokens": getattr(response, 'prompt_tokens', request.estimated_input_tokens or 0),
                "completion_tokens": getattr(response, 'completion_tokens', 0)
            }

            content = response.content if hasattr(response, 'content') else str(response)

            return content, token_usage

        finally:
            # 恢复原始API密钥
            if provider_config.provider == "gemini" and original_key is not None:
                import os
                os.environ["GOOGLE_API_KEY"] = original_key
            elif provider_config.provider == "openai" and original_key is not None:
                import os
                os.environ["OPENAI_API_KEY"] = original_key
            elif provider_config.provider == "anthropic" and original_key is not None:
                import os
                os.environ["ANTHROPIC_API_KEY"] = original_key
            elif provider_config.provider == "deepseek" and original_key is not None:
                import os
                os.environ["DEEPSEEK_API_KEY"] = original_key

    def _estimate_tokens(self, messages: List[Dict]) -> int:
        """估算token数量"""
        total_chars = 0
        for message in messages:
            if isinstance(message.get("content"), str):
                total_chars += len(message["content"])
            elif isinstance(message.get("content"), list):
                for content_item in message["content"]:
                    if content_item.get("type") == "text":
                        total_chars += len(content_item.get("text", ""))

        # 粗略估算：4个字符≈1个token
        return max(100, total_chars // 4)

    def get_service_status(self) -> Dict:
        """获取服务状态"""
        return {
            "timestamp": datetime.now().isoformat(),
            "providers": llm_router.get_provider_status(),
            "key_stats": key_manager.get_usage_stats()
        }

    def add_api_key(self,
                   provider: str,
                   model: str,
                   api_key: str,
                   daily_limit: int = None,
                   monthly_limit: int = None) -> str:
        """添加API密钥"""
        return key_manager.add_key(
            provider=provider,
            model=model,
            api_key=api_key,
            daily_limit=daily_limit,
            monthly_limit=monthly_limit
        )

    def get_user_usage(self, user_id: str, period_days: int = 7) -> Dict:
        """获取用户使用统计"""
        return usage_tracker.get_usage_summary(user_id, period_days)

    def get_cost_analysis(self, period_days: int = 30) -> Dict:
        """获取成本分析"""
        return usage_tracker.get_cost_analysis(period_days)


# 全局增强LLM服务实例
enhanced_llm_service = EnhancedLLMService()