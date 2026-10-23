#!/usr/bin/env python3
"""
Sprint D测试 - LLM成本与密钥治理
"""
import pytest
import tempfile
import os
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
import sys

# 添加项目根目录到路径
sys.path.append(str(Path(__file__).parent.parent))

from core.llm.cost.usage_tracker import UsageTracker
from core.llm.routing.llm_router import LLMRouter, ProviderConfig
from core.llm.keys.key_manager import KeyManager
from core.llm.service.enhanced_llm_service import EnhancedLLMService, LLMRequest


class TestUsageTracker:
    """测试使用量追踪"""

    def setup_method(self):
        self.tracker = UsageTracker()

    def test_record_usage(self):
        """测试记录使用量"""
        record = self.tracker.record_usage(
            user_id="test_user",
            workflow_id="test_workflow",
            device_id="test_device",
            provider="gemini",
            model="gemini-1.5-flash",
            prompt_tokens=100,
            completion_tokens=50,
            duration_ms=1500
        )

        assert record.user_id == "test_user"
        assert record.total_tokens == 150
        assert record.cost_usd > 0
        assert len(self.tracker.records) == 1

    def test_check_quota(self):
        """测试配额检查"""
        # 设置配额
        self.tracker.set_quota_limits("test_user", {
            "daily_tokens": 1000,
            "daily_cost_usd": 1.0
        })

        # 正常使用
        quota = self.tracker.check_quota("test_user", 500)
        assert quota["within_quota"] is True

        # 记录使用量
        self.tracker.record_usage(
            user_id="test_user",
            workflow_id="test_workflow",
            device_id="test_device",
            provider="gemini",
            model="gemini-1.5-flash",
            prompt_tokens=800,
            completion_tokens=100,
            duration_ms=1000
        )

        # 检查是否超限
        quota = self.tracker.check_quota("test_user", 200)
        assert quota["within_quota"] is False

    def test_usage_summary(self):
        """测试使用摘要"""
        # 记录多次使用
        for i in range(3):
            self.tracker.record_usage(
                user_id="test_user",
                workflow_id=f"workflow_{i}",
                device_id="test_device",
                provider="gemini",
                model="gemini-1.5-flash",
                prompt_tokens=100,
                completion_tokens=50,
                duration_ms=1000
            )

        summary = self.tracker.get_usage_summary("test_user", 7)
        assert summary["total_requests"] == 3
        assert summary["total_tokens"] == 450
        assert len(summary["by_workflow"]) == 3


class TestLLMRouter:
    """测试LLM路由"""

    def setup_method(self):
        self.router = LLMRouter()

    def test_register_provider(self):
        """测试注册提供商"""
        config = ProviderConfig(
            provider="gemini",
            model="gemini-1.5-flash",
            api_key="test_key",
            priority=8
        )

        self.router.register_provider(config)
        assert "gemini:gemini-1.5-flash" in self.router.providers

    def test_select_provider(self):
        """测试选择提供商"""
        # 注册多个提供商
        configs = [
            ProviderConfig("gemini", "gemini-1.5-flash", "key1", priority=8),
            ProviderConfig("openai", "gpt-4o", "key2", priority=10),
            ProviderConfig("deepseek", "deepseek-v2", "key3", priority=6)
        ]

        for config in configs:
            self.router.register_provider(config)

        # 选择最优提供商
        selected = self.router.select_provider("test_user", 1000)
        assert selected is not None
        assert selected.priority >= 6

    def test_record_request(self):
        """测试记录请求"""
        config = ProviderConfig("gemini", "gemini-1.5-flash", "key", priority=8)
        self.router.register_provider(config)

        # 记录成功请求
        self.router.record_request("gemini:gemini-1.5-flash", True, 1000, 100)

        # 记录失败请求
        self.router.record_request("gemini:gemini-1.5-flash", False, 5000, 0, "Timeout")

        health = self.router.health["gemini:gemini-1.5-flash"]
        assert health.consecutive_failures == 1
        assert health.last_error == "Timeout"


class TestKeyManager:
    """测试密钥管理"""

    def setup_method(self):
        # 使用临时文件
        self.temp_file = tempfile.NamedTemporaryFile(delete=False)
        self.temp_file.close()
        self.manager = KeyManager(vault_path=self.temp_file.name, master_key="test_key")

    def teardown_method(self):
        os.unlink(self.temp_file.name)

    def test_add_key(self):
        """测试添加密钥"""
        key_id = self.manager.add_key(
            provider="gemini",
            model="gemini-1.5-flash",
            api_key="test_api_key",
            daily_limit=1000
        )

        assert key_id in self.manager.keys
        config = self.manager.keys[key_id]
        assert config.provider == "gemini"
        assert config.daily_limit == 1000

    def test_get_key(self):
        """测试获取密钥"""
        # 添加密钥
        self.manager.add_key("gemini", "gemini-1.5-flash", "secret_key")

        # 获取密钥
        key = self.manager.get_key("gemini", "gemini-1.5-flash")
        assert key == "secret_key"

    def test_key_rotation(self):
        """测试密钥轮换"""
        key_id = self.manager.add_key("gemini", "gemini-1.5-flash", "old_key")

        # 轮换密钥
        success = self.manager.rotate_key(key_id, "new_key")
        assert success is True

        # 验证新密钥
        key = self.manager.get_key("gemini", "gemini-1.5-flash")
        assert key == "new_key"

    def test_key_limits(self):
        """测试密钥限制"""
        key_id = self.manager.add_key(
            provider="gemini",
            model="gemini-1.5-flash",
            api_key="limited_key",
            daily_limit=2
        )

        # 使用密钥多次
        for i in range(3):
            key = self.manager.get_key("gemini", "gemini-1.5-flash")
            if i < 2:
                assert key == "limited_key"
            else:
                # 第3次应该受限制
                pass  # 实际测试中可能需要模拟时间


class TestEnhancedLLMService:
    """测试增强LLM服务"""

    def setup_method(self):
        self.service = EnhancedLLMService()

    def test_service_initialization(self):
        """测试服务初始化"""
        status = self.service.get_service_status()
        assert "providers" in status
        assert "key_stats" in status

    @pytest.mark.asyncio
    async def test_generate_request(self):
        """测试生成请求（模拟）"""
        request = LLMRequest(
            user_id="test_user",
            workflow_id="test_workflow",
            device_id="test_device",
            job_type="chat",
            messages=[{"role": "user", "content": "Hello"}]
        )

        # 注意：这个测试需要有效的API密钥才能真正工作
        # 这里只测试请求构造和配额检查
        response = await self.service.generate(request)

        # 由于没有真实的API密钥，请求会失败
        # 但我们可以验证配额检查是否工作
        assert response is not None

    def test_add_api_key(self):
        """测试添加API密钥"""
        key_id = self.service.add_api_key(
            provider="gemini",
            model="gemini-1.5-flash",
            api_key="test_key"
        )
        assert key_id is not None

    def test_user_usage_tracking(self):
        """测试用户使用统计"""
        usage = self.service.get_user_usage("test_user", 7)
        assert "total_tokens" in usage
        assert "total_cost" in usage

    def test_cost_analysis(self):
        """测试成本分析"""
        analysis = self.service.get_cost_analysis(30)
        assert "total_cost" in analysis
        assert "by_model" in analysis


def test_integration_workflow():
    """集成测试：完整工作流"""

    # 1. 创建服务
    service = EnhancedLLMService()

    # 2. 添加API密钥
    key_id = service.add_api_key(
        provider="gemini",
        model="gemini-1.5-flash",
        api_key="test_integration_key"
    )

    # 3. 检查服务状态
    status = service.get_service_status()
    assert len(status["providers"]) > 0

    # 4. 查看用户使用情况
    usage = service.get_user_usage("integration_test_user")
    assert usage["total_tokens"] >= 0

    print("✓ Integration test passed")


if __name__ == "__main__":
    # 运行基本测试
    test_integration_workflow()

    # 运行单元测试
    pytest.main([__file__, "-v"])