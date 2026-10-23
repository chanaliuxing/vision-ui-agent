#!/usr/bin/env python3
"""
Sprint G测试 - 多客户端聊天适配 & HITL
"""
import pytest
import tempfile
import asyncio
import json
from pathlib import Path
import sys
from datetime import datetime

# 添加项目根目录到路径
sys.path.append(str(Path(__file__).parent.parent))

from core.chat.adapter_interface import (
    ChatAdapter, MockChatAdapter, ChatMessage, ChatInfo, ContactInfo,
    MessageType, MessageDirection, ChatStatus
)
from core.chat.telegram_adapter import TelegramAdapter
from core.chat.hitl_system import (
    HITLSystem, RiskAssessment, ApprovalRequest,
    ApprovalType, RiskLevel, ApprovalStatus
)
from core.chat.chat_manager import ChatManager


class TestChatAdapter:
    """测试聊天适配器接口"""

    def setup_method(self):
        self.adapter = MockChatAdapter("test_mock")

    @pytest.mark.asyncio
    async def test_adapter_connection(self):
        """测试适配器连接"""
        assert not self.adapter.is_connected

        # 连接
        success = await self.adapter.connect()
        assert success is True
        assert self.adapter.is_connected is True

        # 断开连接
        success = await self.adapter.disconnect()
        assert success is True
        assert self.adapter.is_connected is False

    @pytest.mark.asyncio
    async def test_send_receive_messages(self):
        """测试发送和接收消息"""
        await self.adapter.connect()

        # 发送消息
        message_id = await self.adapter.send_message(
            chat_id="test_chat",
            content="Hello, World!",
            message_type=MessageType.TEXT
        )
        assert message_id is not None

        # 获取消息历史
        messages = await self.adapter.get_messages("test_chat")
        assert len(messages) == 1
        assert messages[0].content == "Hello, World!"
        assert messages[0].message_type == MessageType.TEXT

    @pytest.mark.asyncio
    async def test_chat_management(self):
        """测试聊天管理"""
        await self.adapter.connect()

        # 获取聊天列表
        chats = await self.adapter.get_chats()
        assert len(chats) >= 2

        # 获取特定聊天信息
        chat_info = await self.adapter.get_chat_info("chat_1")
        assert chat_info is not None
        assert chat_info.chat_id == "chat_1"

    @pytest.mark.asyncio
    async def test_contact_management(self):
        """测试联系人管理"""
        await self.adapter.connect()

        # 获取联系人信息
        contact = await self.adapter.get_contact_info("user_123")
        assert contact is not None
        assert contact.contact_id == "user_123"

    @pytest.mark.asyncio
    async def test_message_search(self):
        """测试消息搜索"""
        await self.adapter.connect()

        # 发送测试消息
        await self.adapter.send_message("test_chat", "Hello world")
        await self.adapter.send_message("test_chat", "Python programming")
        await self.adapter.send_message("test_chat", "Machine learning")

        # 搜索消息
        results = await self.adapter.search_messages("Python", "test_chat")
        assert len(results) >= 1
        assert any("Python" in msg.content for msg in results)

    def test_capabilities(self):
        """测试适配器能力"""
        capabilities = self.adapter.get_capabilities()
        assert isinstance(capabilities, dict)
        assert "send_text" in capabilities
        assert capabilities["send_text"] is True

    def test_message_handlers(self):
        """测试消息处理器"""
        received_messages = []

        def message_handler(message: ChatMessage):
            received_messages.append(message)

        self.adapter.add_message_handler(message_handler)

        # 模拟接收消息
        self.adapter.simulate_incoming_message(
            chat_id="test_chat",
            sender_id="user_123",
            content="Incoming message"
        )

        assert len(received_messages) == 1
        assert received_messages[0].content == "Incoming message"


class TestTelegramAdapter:
    """测试Telegram适配器"""

    def setup_method(self):
        config = {
            "api_id": "123456",
            "api_hash": "test_hash",
            "phone_number": "+1234567890"
        }
        self.adapter = TelegramAdapter("telegram_test", config)

    @pytest.mark.asyncio
    async def test_telegram_connection(self):
        """测试Telegram连接（模拟）"""
        # 由于使用模拟实现，连接应该成功
        success = await self.adapter.connect()
        assert success is True

        # 检查连接状态
        assert self.adapter.is_connected is True

        # 断开连接
        success = await self.adapter.disconnect()
        assert success is True

    @pytest.mark.asyncio
    async def test_telegram_messaging(self):
        """测试Telegram消息功能"""
        await self.adapter.connect()

        # 发送消息
        message_id = await self.adapter.send_message(
            chat_id="telegram_chat",
            content="Test Telegram message"
        )
        assert message_id is not None

        # 获取消息
        messages = await self.adapter.get_messages("telegram_chat")
        assert len(messages) >= 1

    def test_telegram_capabilities(self):
        """测试Telegram能力"""
        capabilities = self.adapter.get_capabilities()
        assert capabilities["send_text"] is True
        assert capabilities["send_image"] is True
        assert capabilities["send_file"] is True
        assert capabilities["message_editing"] is True
        assert capabilities["bot_support"] is True


class TestRiskAssessment:
    """测试风险评估系统"""

    def setup_method(self):
        # 使用临时配置文件
        self.temp_file = tempfile.NamedTemporaryFile(delete=False)
        self.temp_file.close()
        self.assessor = RiskAssessment(rules_config=self.temp_file.name)

    def teardown_method(self):
        import os
        os.unlink(self.temp_file.name)

    def test_risk_rule_loading(self):
        """测试风险规则加载"""
        assert len(self.assessor.rules) > 0

        # 检查默认规则是否存在
        rule_names = [rule.name for rule in self.assessor.rules]
        assert "敏感数据访问" in rule_names
        assert "大量消息发送" in rule_names

    def test_sensitive_data_detection(self):
        """测试敏感数据检测"""
        # 包含密码的上下文
        context = {"action": "access", "data": "password=secret123"}
        risk_level, triggered_rules, auto_reject = self.assessor.assess_risk(context)

        assert risk_level == RiskLevel.CRITICAL
        assert len(triggered_rules) > 0
        assert "sensitive_data_access" in triggered_rules

    def test_high_volume_detection(self):
        """测试大量消息检测"""
        context = {"message_count": 15, "time_window": "5min"}
        risk_level, triggered_rules, auto_reject = self.assessor.assess_risk(context)

        assert risk_level == RiskLevel.HIGH
        assert "high_volume_messages" in triggered_rules

    def test_low_risk_context(self):
        """测试低风险上下文"""
        context = {"action": "send_message", "content": "Hello, how are you?"}
        risk_level, triggered_rules, auto_reject = self.assessor.assess_risk(context)

        assert risk_level == RiskLevel.LOW
        assert len(triggered_rules) == 0
        assert auto_reject is False


class TestHITLSystem:
    """测试HITL审批系统"""

    def setup_method(self):
        # 使用临时目录
        self.temp_dir = tempfile.mkdtemp()
        self.hitl = HITLSystem(storage_path=self.temp_dir)

    @pytest.mark.asyncio
    async def test_approval_request_creation(self):
        """测试审批请求创建"""
        request_id = await self.hitl.request_approval(
            request_type=ApprovalType.MESSAGE_SEND,
            title="Test Approval",
            description="This is a test approval request",
            context={"test": True},
            requester_id="test_user",
            timeout_minutes=60
        )

        assert request_id is not None
        assert request_id in self.hitl.pending_requests

        request = self.hitl.pending_requests[request_id]
        assert request.title == "Test Approval"
        assert request.status == ApprovalStatus.PENDING

    @pytest.mark.asyncio
    async def test_approval_process(self):
        """测试审批流程"""
        # 创建审批请求
        request_id = await self.hitl.request_approval(
            request_type=ApprovalType.ACTION_EXECUTE,
            title="High Risk Action",
            description="Requesting permission to execute high risk action",
            context={"risk_level": "high", "action": "system_command"},
            requester_id="test_user"
        )

        # 批准请求
        success = await self.hitl.approve_request(request_id, "admin")
        assert success is True

        # 检查请求状态
        assert request_id not in self.hitl.pending_requests
        assert request_id in self.hitl.request_history

        request = self.hitl.request_history[request_id]
        assert request.status == ApprovalStatus.APPROVED
        assert request.approver_id == "admin"

    @pytest.mark.asyncio
    async def test_approval_rejection(self):
        """测试审批拒绝"""
        # 创建审批请求
        request_id = await self.hitl.request_approval(
            request_type=ApprovalType.WORKFLOW_START,
            title="Workflow Start",
            description="Starting workflow",
            context={"workflow": "sensitive_workflow"},
            requester_id="test_user"
        )

        # 拒绝请求
        success = await self.hitl.reject_request(request_id, "admin", "Too risky")
        assert success is True

        request = self.hitl.request_history[request_id]
        assert request.status == ApprovalStatus.REJECTED
        assert request.rejection_reason == "Too risky"

    def test_approval_templates(self):
        """测试审批模板"""
        assert len(self.hitl.templates) > 0

        # 检查默认模板
        template_ids = list(self.hitl.templates.keys())
        assert "workflow_start" in template_ids
        assert "high_risk_action" in template_ids

    def test_approver_management(self):
        """测试审批人管理"""
        # 检查默认审批人
        assert "admin" in self.hitl.approvers
        assert "supervisor" in self.hitl.approvers

        # 检查审批权限
        assert self.hitl._can_approve("admin", RiskLevel.CRITICAL)
        assert self.hitl._can_approve("supervisor", RiskLevel.MEDIUM)
        assert not self.hitl._can_approve("supervisor", RiskLevel.CRITICAL)

    def test_approval_stats(self):
        """测试审批统计"""
        stats = self.hitl.get_approval_stats()

        assert "total_requests" in stats
        assert "pending_requests" in stats
        assert "status_breakdown" in stats
        assert "risk_level_breakdown" in stats
        assert "active_approvers" in stats

    @pytest.mark.asyncio
    async def test_cleanup_expired_requests(self):
        """测试清理过期请求"""
        # 创建一个立即过期的请求
        from datetime import timedelta
        request_id = await self.hitl.request_approval(
            request_type=ApprovalType.MESSAGE_SEND,
            title="Expired Request",
            description="This request will expire immediately",
            context={"test": "expired"},
            requester_id="test_user",
            timeout_minutes=0  # 立即过期
        )

        # 运行清理
        await self.hitl.cleanup_expired_requests()

        # 检查请求是否被移动到历史记录
        assert request_id not in self.hitl.pending_requests
        assert request_id in self.hitl.request_history

        request = self.hitl.request_history[request_id]
        assert request.status == ApprovalStatus.EXPIRED


class TestChatManager:
    """测试聊天管理器"""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.hitl_system = HITLSystem(storage_path=self.temp_dir)
        self.chat_manager = ChatManager(hitl_system=self.hitl_system)

    @pytest.mark.asyncio
    async def test_adapter_registration(self):
        """测试适配器注册"""
        # 创建测试适配器
        mock_adapter = MockChatAdapter("test_adapter")

        # 注册适配器
        success = self.chat_manager.register_adapter(mock_adapter, set_as_default=True)
        assert success is True

        # 检查注册状态
        assert "test_adapter" in self.chat_manager.adapters
        assert self.chat_manager.default_adapter_id == "test_adapter"

        adapter_info = self.chat_manager.get_adapter_info("test_adapter")
        assert adapter_info is not None
        assert adapter_info.adapter_id == "test_adapter"

    @pytest.mark.asyncio
    async def test_adapter_connection_management(self):
        """测试适配器连接管理"""
        mock_adapter = MockChatAdapter("test_adapter")
        self.chat_manager.register_adapter(mock_adapter)

        # 连接适配器
        success = await self.chat_manager.connect_adapter("test_adapter")
        assert success is True

        info = self.chat_manager.get_adapter_info("test_adapter")
        assert info.status.value == "connected"

        # 断开连接
        success = await self.chat_manager.disconnect_adapter("test_adapter")
        assert success is True

        info = self.chat_manager.get_adapter_info("test_adapter")
        assert info.status.value == "disconnected"

    @pytest.mark.asyncio
    async def test_message_sending(self):
        """测试消息发送"""
        mock_adapter = MockChatAdapter("test_adapter")
        self.chat_manager.register_adapter(mock_adapter, set_as_default=True)
        await self.chat_manager.connect_adapter("test_adapter")

        # 发送消息（无需审批）
        message_id = await self.chat_manager.send_text(
            chat_id="test_chat",
            text="Hello from chat manager",
            require_approval=False
        )

        assert message_id is not None

        # 检查统计
        stats = self.chat_manager.get_manager_stats()
        assert stats["message_stats"]["total_sent"] >= 1

    @pytest.mark.asyncio
    async def test_message_routing(self):
        """测试消息路由"""
        # 注册多个适配器
        mock_adapter1 = MockChatAdapter("adapter1")
        mock_adapter2 = MockChatAdapter("adapter2")

        self.chat_manager.register_adapter(mock_adapter1, set_as_default=True)
        self.chat_manager.register_adapter(mock_adapter2)

        await self.chat_manager.connect_adapter("adapter1")
        await self.chat_manager.connect_adapter("adapter2")

        # 设置路由
        self.chat_manager.set_chat_router("chat_1", "adapter1")
        self.chat_manager.set_chat_router("chat_2", "adapter2")

        # 发送消息到不同聊天
        await self.chat_manager.send_text("chat_1", "Message to chat 1", require_approval=False)
        await self.chat_manager.send_text("chat_2", "Message to chat 2", require_approval=False)

        # 检查消息是否发送到正确的适配器
        messages_1 = await mock_adapter1.get_messages("chat_1")
        messages_2 = await mock_adapter2.get_messages("chat_2")

        assert len(messages_1) >= 1
        assert len(messages_2) >= 1

    @pytest.mark.asyncio
    async def test_adapter_switching(self):
        """测试适配器切换"""
        mock_adapter1 = MockChatAdapter("adapter1")
        mock_adapter2 = MockChatAdapter("adapter2")

        self.chat_manager.register_adapter(mock_adapter1, set_as_default=True)
        self.chat_manager.register_adapter(mock_adapter2)

        await self.chat_manager.connect_adapter("adapter1")

        # 切换到adapter2
        success = await self.chat_manager.switch_adapter("adapter1", "adapter2")
        assert success is True

        # 检查新的默认适配器
        assert self.chat_manager.default_adapter_id == "adapter2"

        info1 = self.chat_manager.get_adapter_info("adapter1")
        info2 = self.chat_manager.get_adapter_info("adapter2")

        assert info1.status.value == "disconnected"
        assert info2.status.value == "connected"

    def test_message_handlers(self):
        """测试全局消息处理器"""
        received_messages = []

        def global_handler(adapter_id: str, message: ChatMessage):
            received_messages.append((adapter_id, message))

        self.chat_manager.add_message_handler(global_handler)

        # 注册适配器并模拟收到消息
        mock_adapter = MockChatAdapter("test_adapter")
        self.chat_manager.register_adapter(mock_adapter)

        # 模拟接收消息
        mock_adapter.simulate_incoming_message("test_chat", "user_123", "Test message")

        # 检查是否触发了全局处理器
        assert len(received_messages) >= 1
        assert received_messages[0][0] == "test_adapter"
        assert received_messages[0][1].content == "Test message"

    def test_manager_stats(self):
        """测试管理器统计"""
        stats = self.chat_manager.get_manager_stats()

        assert "adapters" in stats
        assert "message_stats" in stats
        assert "default_adapter" in stats
        assert "hitl_enabled" in stats

        assert stats["hitl_enabled"] is True


def test_integration_chat_system():
    """集成测试：完整的聊天系统"""

    # 创建临时目录
    temp_dir = tempfile.mkdtemp()

    async def run_integration():
        # 初始化系统组件
        hitl_system = HITLSystem(storage_path=temp_dir)
        chat_manager = ChatManager(hitl_system=hitl_system)

        # 注册多个适配器
        mock_adapter = MockChatAdapter("mock")
        telegram_adapter = TelegramAdapter("telegram", {
            "api_id": "123456",
            "api_hash": "test_hash",
            "phone_number": "+1234567890"
        })

        chat_manager.register_adapter(mock_adapter, set_as_default=True)
        chat_manager.register_adapter(telegram_adapter)

        # 连接适配器
        await chat_manager.connect_adapter("mock")
        await chat_manager.connect_adapter("telegram")

        # 设置消息路由
        chat_manager.set_chat_router("general_chat", "mock")
        chat_manager.set_chat_router("telegram_chat", "telegram")

        # 发送普通消息（无需审批）
        message_id_1 = await chat_manager.send_text(
            chat_id="general_chat",
            text="Hello, this is a normal message",
            require_approval=False
        )

        # 发送高风险消息（需要审批）
        try:
            message_id_2 = await chat_manager.send_text(
                chat_id="telegram_chat",
                text="Password: secret123, accessing sensitive data",
                require_approval=True
            )
            # 这个应该会失败，因为没有审批
            assert False, "High-risk message should require approval"
        except Exception as e:
            assert "not approved" in str(e)

        # 获取管理器统计
        stats = chat_manager.get_manager_stats()
        assert stats["adapters"]["mock"]["status"] == "connected"
        assert stats["adapters"]["telegram"]["status"] == "connected"
        assert stats["message_stats"]["total_sent"] >= 1

        # 获取HITL统计
        hitl_stats = hitl_system.get_approval_stats()
        assert hitl_stats["total_requests"] >= 1

        print("✓ Chat system integration test passed")

    # 运行异步测试
    asyncio.run(run_integration())


if __name__ == "__main__":
    # 运行集成测试
    test_integration_chat_system()

    # 运行单元测试
    pytest.main([__file__, "-v"])