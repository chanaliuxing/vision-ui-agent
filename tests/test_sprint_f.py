#!/usr/bin/env python3
"""
Sprint F测试 - 可观测/回放v2
"""
import pytest
import tempfile
import json
import time
from pathlib import Path
import sys
from datetime import datetime, timedelta

# 添加项目根目录到路径
sys.path.append(str(Path(__file__).parent.parent))

from core.observability.run_events import (
    RunEventRecorder, EventType, SensitivityLevel, DataSanitizer
)
from core.observability.sla_monitor import (
    SLAMonitor, MetricType, AlertLevel, SLATarget
)
from core.observability.alert_handlers import (
    AlertManager, ConsoleAlertHandler, Alert
)


class TestRunEventRecorder:
    """测试运行事件记录器"""

    def setup_method(self):
        # 使用临时目录
        self.temp_dir = tempfile.mkdtemp()
        self.recorder = RunEventRecorder(storage_path=self.temp_dir)

    def test_start_end_run(self):
        """测试开始和结束运行"""
        # 开始运行
        run_id = self.recorder.start_run(
            workflow_id="test_workflow",
            metadata={"test": True}
        )
        assert run_id is not None

        # 结束运行
        self.recorder.end_run(
            success=True,
            final_state={"result": "completed"},
            error=None
        )

        # 检查事件
        events = self.recorder.get_run_events(run_id)
        assert len(events) == 2
        assert events[0].event_type == EventType.WORKFLOW_START
        assert events[1].event_type == EventType.WORKFLOW_END

    def test_record_step_events(self):
        """测试记录步骤事件"""
        run_id = self.recorder.start_run("test_workflow")

        # 记录步骤开始
        self.recorder.record_step_start(
            step_id="step_1",
            step_data={"action": "click", "target": "button"}
        )

        # 记录步骤结束
        self.recorder.record_step_end(
            step_id="step_1",
            success=True,
            result={"clicked": True},
            duration_ms=1500
        )

        events = self.recorder.get_run_events(run_id)
        step_events = [e for e in events if e.step_id == "step_1"]
        assert len(step_events) == 2

    def test_record_llm_events(self):
        """测试记录LLM事件"""
        run_id = self.recorder.start_run("test_workflow")

        # 记录LLM请求
        self.recorder.record_llm_request(
            provider="openai",
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello"}],
            correlation_id="llm_001"
        )

        # 记录LLM响应
        self.recorder.record_llm_response(
            response="Hello! How can I help you?",
            usage={"prompt_tokens": 10, "completion_tokens": 15},
            correlation_id="llm_001",
            duration_ms=2000
        )

        events = self.recorder.get_run_events(run_id)
        llm_events = [e for e in events if e.correlation_id == "llm_001"]
        assert len(llm_events) == 2

    def test_record_error(self):
        """测试记录错误"""
        run_id = self.recorder.start_run("test_workflow")

        self.recorder.record_error(
            error_type="timeout",
            error_message="Action timed out after 30s",
            stack_trace="Stack trace here...",
            step_id="step_1"
        )

        events = self.recorder.get_run_events(run_id)
        error_events = [e for e in events if e.event_type == EventType.ERROR]
        assert len(error_events) == 1
        assert error_events[0].error_type == "timeout"

    def test_event_timeline(self):
        """测试事件时间线"""
        run_id = self.recorder.start_run("test_workflow")

        # 记录多个事件
        self.recorder.record_step_start("step_1", {"action": "click"})
        time.sleep(0.1)  # 确保时间戳不同
        self.recorder.record_action("action_1", "click", {"target": "button"}, "step_1")
        time.sleep(0.1)
        self.recorder.record_step_end("step_1", True, {"result": "success"})

        timeline = self.recorder.get_event_timeline(run_id)
        assert len(timeline) >= 4  # start + 3个步骤事件

        # 检查时间顺序
        timestamps = [datetime.fromisoformat(item['timestamp']) for item in timeline]
        assert timestamps == sorted(timestamps)

    def test_variable_tracking(self):
        """测试变量跟踪"""
        run_id = self.recorder.start_run("test_workflow")

        # 设置变量
        self.recorder.record_variable_set("user_name", "John Doe")
        self.recorder.record_variable_set("user_email", "john@example.com")
        self.recorder.record_variable_set("user_name", "Jane Doe")  # 更新

        events = self.recorder.get_run_events(run_id)
        var_events = [e for e in events if e.event_type == EventType.VARIABLE_SET]
        assert len(var_events) == 3

        # 检查最后的变量值
        user_name_events = [e for e in var_events if e.data.get('variable_name') == 'user_name']
        assert len(user_name_events) == 2


class TestDataSanitizer:
    """测试数据脱敏器"""

    def setup_method(self):
        self.sanitizer = DataSanitizer()

    def test_sensitive_field_detection(self):
        """测试敏感字段检测"""
        assert self.sanitizer._is_sensitive_field("password")
        assert self.sanitizer._is_sensitive_field("api_key")
        assert self.sanitizer._is_sensitive_field("user_token")
        assert not self.sanitizer._is_sensitive_field("username")
        assert not self.sanitizer._is_sensitive_field("email")

    def test_deep_sanitization(self):
        """测试深度脱敏"""
        sensitive_data = {
            "username": "john_doe",
            "password": "secret123",
            "api_key": "sk-1234567890",
            "user_info": {
                "name": "John Doe",
                "token": "abc123"
            }
        }

        sanitized = self.sanitizer.sanitize_data(sensitive_data, SensitivityLevel.PUBLIC)

        assert sanitized["username"] == "john_doe"  # 非敏感字段保留
        assert sanitized["password"] == "[REDACTED]"  # 敏感字段脱敏
        assert sanitized["api_key"] == "[REDACTED]"
        assert sanitized["user_info"]["name"] == "John Doe"
        assert sanitized["user_info"]["token"] == "[REDACTED]"

    def test_pii_sanitization(self):
        """测试PII脱敏"""
        text = "My email is john@example.com and phone is 13812345678"
        sanitized = self.sanitizer._sanitize_string(text)

        assert "[EMAIL]" in sanitized
        assert "[PHONE]" in sanitized
        assert "john@example.com" not in sanitized
        assert "13812345678" not in sanitized

    def test_partial_sanitization(self):
        """测试部分脱敏"""
        data = {
            "username": "john_doe_very_long",
            "password": "secret123"
        }

        sanitized = self.sanitizer.sanitize_data(data, SensitivityLevel.INTERNAL)

        assert sanitized["username"] == "jo***********ng"  # 部分脱敏
        assert sanitized["password"] == "s*******3"


class TestSLAMonitor:
    """测试SLA监控器"""

    def setup_method(self):
        # 使用临时配置文件
        self.temp_file = tempfile.NamedTemporaryFile(delete=False)
        self.temp_file.close()
        self.monitor = SLAMonitor(config_path=self.temp_file.name)

    def teardown_method(self):
        import os
        self.monitor.stop_monitoring()
        os.unlink(self.temp_file.name)

    def test_sla_target_creation(self):
        """测试SLA目标创建"""
        assert len(self.monitor.sla_targets) > 0

        # 检查默认目标
        success_rate_target = self.monitor.sla_targets.get("workflow_success_rate")
        assert success_rate_target is not None
        assert success_rate_target.metric_type == MetricType.SUCCESS_RATE
        assert success_rate_target.target_value == 0.95

    def test_workflow_execution_recording(self):
        """测试工作流执行记录"""
        # 记录成功的工作流执行
        self.monitor.record_workflow_execution(
            workflow_id="test_workflow_1",
            success=True,
            duration_ms=2000,
            task_type="normal"
        )

        # 记录失败的工作流执行
        self.monitor.record_workflow_execution(
            workflow_id="test_workflow_2",
            success=False,
            duration_ms=5000,
            task_type="normal"
        )

        # 获取SLA指标
        metrics = self.monitor.get_current_sla_metrics(time_window_minutes=1)

        assert metrics.total_requests == 2
        assert metrics.successful_requests == 1
        assert metrics.failed_requests == 1
        assert metrics.success_rate == 0.5
        assert metrics.error_rate == 0.5

    def test_hp_task_monitoring(self):
        """测试HP任务监控"""
        # 记录HP任务
        self.monitor.record_workflow_execution(
            workflow_id="hp_task_1",
            success=True,
            duration_ms=1500,
            task_type="hp"
        )

        self.monitor.record_workflow_execution(
            workflow_id="hp_task_2",
            success=True,
            duration_ms=4000,
            task_type="hp"
        )

        # 检查HP任务指标
        hp_times = self.monitor.collector.get_metric_values("hp_task_duration_ms", 1)
        assert len(hp_times) == 2
        assert 1500 in hp_times
        assert 4000 in hp_times

    def test_system_health_recording(self):
        """测试系统健康状态记录"""
        # 记录健康状态
        self.monitor.record_system_health(True)
        self.monitor.record_system_health(True)
        self.monitor.record_system_health(False)

        metrics = self.monitor.get_current_sla_metrics(time_window_minutes=1)
        assert 0.6 <= metrics.availability <= 0.7  # 2/3

    def test_alert_conditions(self):
        """测试告警条件"""
        # 先启动监控
        self.monitor.start_monitoring()
        time.sleep(0.1)  # 让监控线程启动

        # 记录多个失败的执行来触发告警条件
        for i in range(10):
            self.monitor.record_workflow_execution(
                workflow_id=f"failing_workflow_{i}",
                success=False,
                duration_ms=10000,  # 10秒，超过目标
                task_type="normal"
            )

        # 等待监控处理
        time.sleep(1)

        # 检查指标
        metrics = self.monitor.get_current_sla_metrics(time_window_minutes=1)
        assert metrics.success_rate < 0.95  # 低于目标

    def test_sla_dashboard_data(self):
        """测试SLA仪表盘数据"""
        # 记录一些数据
        self.monitor.record_workflow_execution("wf_1", True, 1000)
        self.monitor.record_workflow_execution("wf_2", False, 6000)

        dashboard_data = self.monitor.get_sla_dashboard_data()

        assert "timestamp" in dashboard_data
        assert "metrics" in dashboard_data
        assert "sla_targets" in dashboard_data
        assert "alerts" in dashboard_data

        # 检查指标
        metrics = dashboard_data["metrics"]
        assert metrics["total_requests"] == 2
        assert metrics["success_rate"] == 0.5


class TestAlertHandlers:
    """测试告警处理器"""

    def setup_method(self):
        self.temp_file = tempfile.NamedTemporaryFile(delete=False)
        self.temp_file.close()
        self.alert_manager = AlertManager(config_path=self.temp_file.name)

    def teardown_method(self):
        import os
        os.unlink(self.temp_file.name)

    def test_console_alert_handler(self):
        """测试控制台告警处理器"""
        handler = ConsoleAlertHandler()

        alert = Alert(
            alert_id="test_alert_1",
            timestamp=datetime.now(),
            level=AlertLevel.WARNING,
            status=None,  # 不重要
            title="Test Alert",
            message="This is a test alert",
            metric_type=MetricType.SUCCESS_RATE,
            current_value=0.85,
            target_value=0.95
        )

        # 应该成功处理
        result = handler.send_alert(alert)
        assert result is True

    def test_alert_manager_cooldown(self):
        """测试告警管理器冷却机制"""
        # 创建相同的告警
        alert1 = Alert(
            alert_id="test_alert_1",
            timestamp=datetime.now(),
            level=AlertLevel.WARNING,
            status=None,
            title="Test Alert",
            message="This is a test alert",
            metric_type=MetricType.SUCCESS_RATE,
            current_value=0.85,
            target_value=0.95,
            tags={"sla_target": "test_target"}
        )

        alert2 = Alert(
            alert_id="test_alert_2",
            timestamp=datetime.now(),
            level=AlertLevel.WARNING,
            status=None,
            title="Test Alert 2",
            message="This is another test alert",
            metric_type=MetricType.SUCCESS_RATE,
            current_value=0.80,
            target_value=0.95,
            tags={"sla_target": "test_target"}  # 相同的目标
        )

        # 第一个告警应该成功
        result1 = self.alert_manager.handle_alert(alert1)
        assert result1 is True

        # 第二个告警应该被冷却阻止
        result2 = self.alert_manager.handle_alert(alert2)
        assert result2 is False

    def test_alert_level_filtering(self):
        """测试告警级别过滤"""
        # 设置最小告警级别为WARNING
        self.alert_manager.config.min_alert_level = AlertLevel.WARNING

        info_alert = Alert(
            alert_id="info_alert",
            timestamp=datetime.now(),
            level=AlertLevel.INFO,  # 低于最小级别
            status=None,
            title="Info Alert",
            message="This is an info alert",
            metric_type=MetricType.SUCCESS_RATE,
            current_value=0.90,
            target_value=0.95
        )

        warning_alert = Alert(
            alert_id="warning_alert",
            timestamp=datetime.now(),
            level=AlertLevel.WARNING,  # 符合最小级别
            status=None,
            title="Warning Alert",
            message="This is a warning alert",
            metric_type=MetricType.SUCCESS_RATE,
            current_value=0.85,
            target_value=0.95
        )

        # INFO级别应该被过滤
        result1 = self.alert_manager.handle_alert(info_alert)
        assert result1 is False

        # WARNING级别应该通过
        result2 = self.alert_manager.handle_alert(warning_alert)
        assert result2 is True

    def test_default_config_creation(self):
        """测试默认配置创建"""
        self.alert_manager.create_default_config()

        # 检查配置文件是否创建
        assert Path(self.temp_file.name).exists()

        # 检查配置内容
        with open(self.temp_file.name, 'r') as f:
            config = json.load(f)

        assert "enabled" in config
        assert "email" in config
        assert "slack" in config
        assert "webhook" in config


def test_integration_observability():
    """集成测试：完整的可观测性工作流"""

    # 创建临时目录
    temp_dir = tempfile.mkdtemp()

    # 初始化组件
    event_recorder = RunEventRecorder(storage_path=temp_dir)
    sla_monitor = SLAMonitor()

    # 开始一个运行
    run_id = event_recorder.start_run("integration_test_workflow")

    # 记录步骤和动作
    event_recorder.record_step_start("step_1", {"action": "navigate", "url": "https://example.com"})
    time.sleep(0.1)

    event_recorder.record_action("action_1", "navigate",
                                {"url": "https://example.com"},
                                step_id="step_1", duration_ms=1000)

    event_recorder.record_step_end("step_1", True, {"navigated": True}, duration_ms=1200)

    # 记录LLM交互
    event_recorder.record_llm_request("openai", "gpt-4",
                                    [{"role": "user", "content": "Analyze this page"}],
                                    correlation_id="llm_001")

    event_recorder.record_llm_response("The page contains...",
                                     {"prompt_tokens": 100, "completion_tokens": 50},
                                     correlation_id="llm_001", duration_ms=2000)

    # 记录到SLA监控
    sla_monitor.record_workflow_execution(
        workflow_id="integration_test_workflow",
        success=True,
        duration_ms=3200,
        task_type="normal"
    )

    # 结束运行
    event_recorder.end_run(success=True, final_state={"completed": True})

    # 验证事件记录
    events = event_recorder.get_run_events(run_id)
    assert len(events) >= 6  # start, step_start, action, step_end, llm_request, llm_response, end

    # 验证时间线
    timeline = event_recorder.get_event_timeline(run_id)
    assert len(timeline) >= 6

    # 验证SLA指标
    metrics = sla_monitor.get_current_sla_metrics(time_window_minutes=1)
    assert metrics.total_requests >= 1
    assert metrics.success_rate >= 1.0

    print("✓ Integration test passed")


if __name__ == "__main__":
    # 运行集成测试
    test_integration_observability()

    # 运行单元测试
    pytest.main([__file__, "-v"])