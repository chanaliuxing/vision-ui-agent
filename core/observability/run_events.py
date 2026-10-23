"""
运行事件系统 - 详细的执行轨迹记录
按照upgrade.md Sprint F规范实现
"""
import logging
import json
import uuid
import hashlib
import base64
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
import re

logger = logging.getLogger(__name__)


class EventType(Enum):
    WORKFLOW_START = "workflow_start"
    WORKFLOW_END = "workflow_end"
    STEP_START = "step_start"
    STEP_END = "step_end"
    ACTION_EXECUTE = "action_execute"
    SCREENSHOT = "screenshot"
    YOLO_DETECT = "yolo_detect"
    LLM_REQUEST = "llm_request"
    LLM_RESPONSE = "llm_response"
    ERROR = "error"
    VARIABLE_SET = "variable_set"
    ANCHOR_MATCH = "anchor_match"
    USER_INPUT = "user_input"
    SYSTEM_ALERT = "system_alert"


class SensitivityLevel(Enum):
    PUBLIC = "public"        # 可公开
    INTERNAL = "internal"    # 内部使用
    SENSITIVE = "sensitive"  # 敏感信息
    SECRET = "secret"        # 机密信息


@dataclass
class RunEvent:
    """运行事件"""
    event_id: str
    timestamp: str
    event_type: EventType
    run_id: str
    workflow_id: str
    step_id: Optional[str] = None
    action_id: Optional[str] = None

    # 事件数据
    data: Dict = None
    metadata: Dict = None

    # 敏感度和脱敏
    sensitivity: SensitivityLevel = SensitivityLevel.INTERNAL
    is_sanitized: bool = False

    # 关联信息
    parent_event_id: Optional[str] = None
    correlation_id: Optional[str] = None

    # 性能指标
    duration_ms: Optional[float] = None
    memory_usage_mb: Optional[float] = None

    # 错误信息
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    stack_trace: Optional[str] = None


class DataSanitizer:
    """数据脱敏器"""

    def __init__(self):
        # 敏感字段模式
        self.sensitive_patterns = [
            r'password',
            r'passwd',
            r'token',
            r'secret',
            r'key',
            r'api_key',
            r'auth',
            r'credential',
            r'session',
            r'cookie',
            r'authorization'
        ]

        # 编译正则表达式
        self.sensitive_regex = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in self.sensitive_patterns
        ]

        # PII模式
        self.pii_patterns = [
            (r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b', '[CARD_NUMBER]'),  # 信用卡号
            (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]'),  # 邮箱
            (r'\b1[3-9]\d{9}\b', '[PHONE]'),  # 手机号
            (r'\b\d{15,18}\b', '[ID_NUMBER]'),  # 身份证号
        ]

        self.pii_regex = [
            (re.compile(pattern), replacement)
            for pattern, replacement in self.pii_patterns
        ]

    def sanitize_data(self, data: Any, sensitivity: SensitivityLevel) -> Any:
        """脱敏数据"""
        if sensitivity == SensitivityLevel.PUBLIC:
            return self._deep_sanitize(data)
        elif sensitivity == SensitivityLevel.INTERNAL:
            return self._partial_sanitize(data)
        elif sensitivity == SensitivityLevel.SENSITIVE:
            return self._mask_sensitive(data)
        else:  # SECRET
            return "[REDACTED]"

    def _deep_sanitize(self, data: Any) -> Any:
        """深度脱敏 - 移除所有敏感信息"""
        if isinstance(data, dict):
            result = {}
            for key, value in data.items():
                if self._is_sensitive_field(key):
                    result[key] = "[REDACTED]"
                else:
                    result[key] = self._deep_sanitize(value)
            return result
        elif isinstance(data, list):
            return [self._deep_sanitize(item) for item in data]
        elif isinstance(data, str):
            return self._sanitize_string(data)
        else:
            return data

    def _partial_sanitize(self, data: Any) -> Any:
        """部分脱敏 - 保留部分信息"""
        if isinstance(data, dict):
            result = {}
            for key, value in data.items():
                if self._is_sensitive_field(key):
                    result[key] = self._mask_value(value)
                else:
                    result[key] = self._partial_sanitize(value)
            return result
        elif isinstance(data, list):
            return [self._partial_sanitize(item) for item in data]
        elif isinstance(data, str):
            return self._partial_sanitize_string(data)
        else:
            return data

    def _mask_sensitive(self, data: Any) -> Any:
        """敏感信息掩码"""
        if isinstance(data, dict):
            return {k: "[MASKED]" if self._is_sensitive_field(k) else v for k, v in data.items()}
        elif isinstance(data, str):
            return self._mask_pii(data)
        else:
            return data

    def _is_sensitive_field(self, field_name: str) -> bool:
        """检查是否为敏感字段"""
        return any(regex.search(field_name) for regex in self.sensitive_regex)

    def _sanitize_string(self, text: str) -> str:
        """脱敏字符串"""
        result = text
        for pattern_regex, replacement in self.pii_regex:
            result = pattern_regex.sub(replacement, result)
        return result

    def _partial_sanitize_string(self, text: str) -> str:
        """部分脱敏字符串"""
        if len(text) <= 4:
            return "*" * len(text)
        return text[:2] + "*" * (len(text) - 4) + text[-2:]

    def _mask_value(self, value: Any) -> str:
        """掩码值"""
        if isinstance(value, str):
            if len(value) <= 4:
                return "*" * len(value)
            return value[:1] + "*" * (len(value) - 2) + value[-1:]
        else:
            return "[MASKED]"

    def _mask_pii(self, text: str) -> str:
        """掩码PII信息"""
        result = text
        for pattern_regex, replacement in self.pii_regex:
            result = pattern_regex.sub(replacement, result)
        return result


class RunEventRecorder:
    """运行事件记录器"""

    def __init__(self, storage_path: str = "data/run_events"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self.sanitizer = DataSanitizer()
        self.events: List[RunEvent] = []
        self.current_run_id: Optional[str] = None
        self.correlations: Dict[str, List[str]] = {}  # correlation_id -> event_ids

        # 性能缓存
        self.event_cache: Dict[str, RunEvent] = {}
        self.max_cache_size = 1000

    def start_run(self, workflow_id: str, metadata: Dict = None) -> str:
        """开始一次运行"""
        run_id = str(uuid.uuid4())
        self.current_run_id = run_id

        event = self._create_event(
            event_type=EventType.WORKFLOW_START,
            run_id=run_id,
            workflow_id=workflow_id,
            data={"metadata": metadata or {}},
            sensitivity=SensitivityLevel.INTERNAL
        )

        self._record_event(event)
        logger.info(f"Started run: {run_id}")
        return run_id

    def end_run(self, success: bool, final_state: Dict = None, error: str = None):
        """结束运行"""
        if not self.current_run_id:
            logger.warning("No active run to end")
            return

        event = self._create_event(
            event_type=EventType.WORKFLOW_END,
            run_id=self.current_run_id,
            workflow_id="",  # 从开始事件获取
            data={
                "success": success,
                "final_state": final_state or {},
                "error": error
            },
            sensitivity=SensitivityLevel.INTERNAL
        )

        self._record_event(event)

        # 持久化当前运行的事件
        self._persist_run_events(self.current_run_id)

        logger.info(f"Ended run: {self.current_run_id} (success={success})")
        self.current_run_id = None

    def record_step_start(self, step_id: str, step_data: Dict, correlation_id: str = None):
        """记录步骤开始"""
        event = self._create_event(
            event_type=EventType.STEP_START,
            run_id=self.current_run_id,
            workflow_id="",
            step_id=step_id,
            data=step_data,
            correlation_id=correlation_id,
            sensitivity=self._determine_sensitivity(step_data)
        )

        self._record_event(event)

    def record_step_end(self, step_id: str, success: bool, result: Dict = None,
                       duration_ms: float = None, error: str = None):
        """记录步骤结束"""
        event = self._create_event(
            event_type=EventType.STEP_END,
            run_id=self.current_run_id,
            workflow_id="",
            step_id=step_id,
            data={
                "success": success,
                "result": result or {},
                "error": error
            },
            duration_ms=duration_ms,
            sensitivity=SensitivityLevel.INTERNAL
        )

        if error:
            event.error_type = "step_error"
            event.error_message = error

        self._record_event(event)

    def record_action(self, action_id: str, action_type: str, action_data: Dict,
                     step_id: str = None, duration_ms: float = None):
        """记录动作执行"""
        event = self._create_event(
            event_type=EventType.ACTION_EXECUTE,
            run_id=self.current_run_id,
            workflow_id="",
            step_id=step_id,
            action_id=action_id,
            data={
                "action_type": action_type,
                "action_data": action_data
            },
            duration_ms=duration_ms,
            sensitivity=self._determine_sensitivity(action_data)
        )

        self._record_event(event)

    def record_screenshot(self, screenshot_path: str, step_id: str = None,
                         metadata: Dict = None):
        """记录截图"""
        # 计算截图哈希
        screenshot_hash = self._calculate_file_hash(screenshot_path)

        event = self._create_event(
            event_type=EventType.SCREENSHOT,
            run_id=self.current_run_id,
            workflow_id="",
            step_id=step_id,
            data={
                "screenshot_path": screenshot_path,
                "screenshot_hash": screenshot_hash,
                "metadata": metadata or {}
            },
            sensitivity=SensitivityLevel.SENSITIVE  # 截图可能包含敏感信息
        )

        self._record_event(event)

    def record_yolo_detection(self, detections: List[Dict], screenshot_path: str,
                            step_id: str = None):
        """记录YOLO检测"""
        # 脱敏检测结果中的敏感文本
        sanitized_detections = []
        for detection in detections:
            sanitized = detection.copy()
            if 'text' in sanitized:
                sanitized['text'] = self.sanitizer.sanitize_data(
                    sanitized['text'],
                    SensitivityLevel.PUBLIC
                )
            sanitized_detections.append(sanitized)

        event = self._create_event(
            event_type=EventType.YOLO_DETECT,
            run_id=self.current_run_id,
            workflow_id="",
            step_id=step_id,
            data={
                "detections": sanitized_detections,
                "detection_count": len(detections),
                "screenshot_path": screenshot_path
            },
            sensitivity=SensitivityLevel.INTERNAL
        )

        self._record_event(event)

    def record_llm_request(self, provider: str, model: str, messages: List[Dict],
                          correlation_id: str = None, step_id: str = None):
        """记录LLM请求"""
        # 脱敏LLM消息
        sanitized_messages = []
        for msg in messages:
            sanitized = msg.copy()
            if 'content' in sanitized:
                sanitized['content'] = self.sanitizer.sanitize_data(
                    sanitized['content'],
                    SensitivityLevel.INTERNAL
                )
            sanitized_messages.append(sanitized)

        event = self._create_event(
            event_type=EventType.LLM_REQUEST,
            run_id=self.current_run_id,
            workflow_id="",
            step_id=step_id,
            data={
                "provider": provider,
                "model": model,
                "messages": sanitized_messages,
                "message_count": len(messages)
            },
            correlation_id=correlation_id,
            sensitivity=SensitivityLevel.SENSITIVE
        )

        self._record_event(event)

    def record_llm_response(self, response: str, usage: Dict, correlation_id: str = None,
                           duration_ms: float = None, step_id: str = None):
        """记录LLM响应"""
        event = self._create_event(
            event_type=EventType.LLM_RESPONSE,
            run_id=self.current_run_id,
            workflow_id="",
            step_id=step_id,
            data={
                "response": self.sanitizer.sanitize_data(response, SensitivityLevel.INTERNAL),
                "usage": usage,
                "response_length": len(response)
            },
            correlation_id=correlation_id,
            duration_ms=duration_ms,
            sensitivity=SensitivityLevel.SENSITIVE
        )

        self._record_event(event)

    def record_variable_set(self, variable_name: str, value: Any, step_id: str = None):
        """记录变量设置"""
        event = self._create_event(
            event_type=EventType.VARIABLE_SET,
            run_id=self.current_run_id,
            workflow_id="",
            step_id=step_id,
            data={
                "variable_name": variable_name,
                "value": self.sanitizer.sanitize_data(value, SensitivityLevel.INTERNAL),
                "value_type": type(value).__name__
            },
            sensitivity=self._determine_sensitivity({variable_name: value})
        )

        self._record_event(event)

    def record_error(self, error_type: str, error_message: str, stack_trace: str = None,
                    step_id: str = None, action_id: str = None):
        """记录错误"""
        event = self._create_event(
            event_type=EventType.ERROR,
            run_id=self.current_run_id,
            workflow_id="",
            step_id=step_id,
            action_id=action_id,
            data={
                "error_type": error_type,
                "error_message": error_message,
                "stack_trace": stack_trace
            },
            error_type=error_type,
            error_message=error_message,
            stack_trace=stack_trace,
            sensitivity=SensitivityLevel.INTERNAL
        )

        self._record_event(event)

    def record_event(self, run_id: str, event_type: EventType, data: Dict, **kwargs):
        """通用事件记录方法 - 向后兼容API"""
        event = self._create_event(
            event_type=event_type,
            run_id=run_id,
            workflow_id=kwargs.get("workflow_id", ""),
            data=data,
            sensitivity=kwargs.get("sensitivity", SensitivityLevel.INTERNAL),
            **{k: v for k, v in kwargs.items() if k not in ["workflow_id", "sensitivity"]}
        )
        self._record_event(event)

    def get_run_events(self, run_id: str, sanitize: bool = True) -> List[RunEvent]:
        """获取运行事件"""
        events = [e for e in self.events if e.run_id == run_id]

        if sanitize:
            sanitized_events = []
            for event in events:
                sanitized_event = self._sanitize_event(event)
                sanitized_events.append(sanitized_event)
            return sanitized_events

        return events

    def get_event_timeline(self, run_id: str) -> List[Dict]:
        """获取事件时间线"""
        events = self.get_run_events(run_id, sanitize=True)
        events.sort(key=lambda e: e.timestamp)

        timeline = []
        for event in events:
            timeline_item = {
                "timestamp": event.timestamp,
                "event_type": event.event_type.value,
                "step_id": event.step_id,
                "action_id": event.action_id,
                "duration_ms": event.duration_ms,
                "summary": self._generate_event_summary(event),
                "data": event.data
            }
            timeline.append(timeline_item)

        return timeline

    def _create_event(self, event_type: EventType, run_id: str, workflow_id: str,
                     step_id: str = None, action_id: str = None, data: Dict = None,
                     correlation_id: str = None, duration_ms: float = None,
                     sensitivity: SensitivityLevel = SensitivityLevel.INTERNAL,
                     **kwargs) -> RunEvent:
        """创建事件"""
        event_id = str(uuid.uuid4())

        event = RunEvent(
            event_id=event_id,
            timestamp=datetime.now().isoformat(),
            event_type=event_type,
            run_id=run_id or self.current_run_id,
            workflow_id=workflow_id,
            step_id=step_id,
            action_id=action_id,
            data=data or {},
            correlation_id=correlation_id,
            duration_ms=duration_ms,
            sensitivity=sensitivity,
            **kwargs
        )

        return event

    def _record_event(self, event: RunEvent):
        """记录事件"""
        self.events.append(event)

        # 更新缓存
        self.event_cache[event.event_id] = event
        if len(self.event_cache) > self.max_cache_size:
            # 清理最老的事件
            oldest_events = sorted(self.event_cache.values(), key=lambda e: e.timestamp)[:100]
            for old_event in oldest_events:
                del self.event_cache[old_event.event_id]

        # 更新关联
        if event.correlation_id:
            if event.correlation_id not in self.correlations:
                self.correlations[event.correlation_id] = []
            self.correlations[event.correlation_id].append(event.event_id)

        logger.debug(f"Recorded event: {event.event_type.value} ({event.event_id})")

    def _sanitize_event(self, event: RunEvent) -> RunEvent:
        """脱敏事件"""
        if event.is_sanitized:
            return event

        sanitized_event = RunEvent(
            event_id=event.event_id,
            timestamp=event.timestamp,
            event_type=event.event_type,
            run_id=event.run_id,
            workflow_id=event.workflow_id,
            step_id=event.step_id,
            action_id=event.action_id,
            data=self.sanitizer.sanitize_data(event.data, event.sensitivity),
            metadata=event.metadata,
            sensitivity=event.sensitivity,
            is_sanitized=True,
            parent_event_id=event.parent_event_id,
            correlation_id=event.correlation_id,
            duration_ms=event.duration_ms,
            memory_usage_mb=event.memory_usage_mb,
            error_type=event.error_type,
            error_message=event.error_message,
            stack_trace=event.stack_trace
        )

        return sanitized_event

    def _determine_sensitivity(self, data: Dict) -> SensitivityLevel:
        """确定数据敏感度"""
        data_str = json.dumps(data, default=str).lower()

        # 检查是否包含机密信息
        secret_keywords = ['password', 'token', 'secret', 'key', 'credential']
        if any(keyword in data_str for keyword in secret_keywords):
            return SensitivityLevel.SECRET

        # 检查是否包含敏感信息
        sensitive_keywords = ['email', 'phone', 'address', 'id_number']
        if any(keyword in data_str for keyword in sensitive_keywords):
            return SensitivityLevel.SENSITIVE

        return SensitivityLevel.INTERNAL

    def _generate_event_summary(self, event: RunEvent) -> str:
        """生成事件摘要"""
        if event.event_type == EventType.WORKFLOW_START:
            return f"Started workflow"
        elif event.event_type == EventType.WORKFLOW_END:
            success = event.data.get('success', False)
            return f"Ended workflow ({'success' if success else 'failed'})"
        elif event.event_type == EventType.STEP_START:
            return f"Started step {event.step_id}"
        elif event.event_type == EventType.STEP_END:
            success = event.data.get('success', False)
            return f"Ended step {event.step_id} ({'success' if success else 'failed'})"
        elif event.event_type == EventType.ACTION_EXECUTE:
            action_type = event.data.get('action_type', 'unknown')
            return f"Executed action: {action_type}"
        elif event.event_type == EventType.SCREENSHOT:
            return "Captured screenshot"
        elif event.event_type == EventType.YOLO_DETECT:
            count = event.data.get('detection_count', 0)
            return f"YOLO detected {count} objects"
        elif event.event_type == EventType.LLM_REQUEST:
            provider = event.data.get('provider', 'unknown')
            model = event.data.get('model', 'unknown')
            return f"LLM request to {provider}:{model}"
        elif event.event_type == EventType.LLM_RESPONSE:
            length = event.data.get('response_length', 0)
            return f"LLM response ({length} chars)"
        elif event.event_type == EventType.ERROR:
            error_type = event.data.get('error_type', 'unknown')
            return f"Error: {error_type}"
        else:
            return f"{event.event_type.value}"

    def _calculate_file_hash(self, file_path: str) -> str:
        """计算文件哈希"""
        try:
            with open(file_path, 'rb') as f:
                file_hash = hashlib.md5(f.read()).hexdigest()
            return file_hash
        except Exception:
            return "unknown"

    def _persist_run_events(self, run_id: str):
        """持久化运行事件"""
        try:
            run_events = [e for e in self.events if e.run_id == run_id]

            # 转换为可序列化格式
            serializable_events = []
            for event in run_events:
                event_dict = asdict(event)
                event_dict['event_type'] = event.event_type.value
                event_dict['sensitivity'] = event.sensitivity.value
                serializable_events.append(event_dict)

            # 保存到文件
            file_path = self.storage_path / f"run_{run_id}.json"
            with open(file_path, 'w') as f:
                json.dump(serializable_events, f, indent=2)

            logger.info(f"Persisted {len(run_events)} events for run {run_id}")

        except Exception as e:
            logger.error(f"Failed to persist events for run {run_id}: {e}")


# 全局事件记录器
event_recorder = RunEventRecorder()