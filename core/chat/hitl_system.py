"""
HITL (Human In The Loop) 审批流系统
按照upgrade.md Sprint G规范实现
"""
import logging
import json
import uuid
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
import asyncio

from .adapter_interface import ChatAdapter, ChatMessage

logger = logging.getLogger(__name__)


class ApprovalStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ApprovalType(Enum):
    WORKFLOW_START = "workflow_start"
    ACTION_EXECUTE = "action_execute"
    MESSAGE_SEND = "message_send"
    DATA_ACCESS = "data_access"
    SYSTEM_OPERATION = "system_operation"


@dataclass
class ApprovalRequest:
    """审批请求"""
    request_id: str
    request_type: ApprovalType
    risk_level: RiskLevel
    title: str
    description: str
    context: Dict  # 请求上下文信息
    requester_id: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    status: ApprovalStatus = ApprovalStatus.PENDING

    # 审批信息
    approver_id: Optional[str] = None
    approved_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None

    # 元数据
    workflow_id: Optional[str] = None
    step_id: Optional[str] = None
    chat_id: Optional[str] = None
    tags: Dict[str, str] = None


@dataclass
class RiskRule:
    """风险规则"""
    rule_id: str
    name: str
    description: str
    condition: str  # Python表达式
    risk_level: RiskLevel
    approval_required: bool = True
    auto_reject: bool = False
    tags: List[str] = None


@dataclass
class ApprovalTemplate:
    """审批模板"""
    template_id: str
    name: str
    risk_level: RiskLevel
    title_template: str
    description_template: str
    expiry_minutes: int = 60
    required_approvers: int = 1
    allowed_approvers: List[str] = None  # 允许的审批人列表


class RiskAssessment:
    """风险评估器"""

    def __init__(self, rules_config: str = "config/risk_rules.json"):
        self.rules_config = Path(rules_config)
        self.rules: List[RiskRule] = []
        self._load_rules()

    def _load_rules(self):
        """加载风险规则"""
        try:
            if self.rules_config.exists():
                with open(self.rules_config, 'r') as f:
                    rules_data = json.load(f)

                for rule_data in rules_data.get('rules', []):
                    rule = RiskRule(
                        rule_id=rule_data['rule_id'],
                        name=rule_data['name'],
                        description=rule_data['description'],
                        condition=rule_data['condition'],
                        risk_level=RiskLevel(rule_data['risk_level']),
                        approval_required=rule_data.get('approval_required', True),
                        auto_reject=rule_data.get('auto_reject', False),
                        tags=rule_data.get('tags', [])
                    )
                    self.rules.append(rule)

            else:
                self._create_default_rules()

            logger.info(f"Loaded {len(self.rules)} risk rules")

        except Exception as e:
            logger.error(f"Failed to load risk rules: {e}")
            self._create_default_rules()

    def _create_default_rules(self):
        """创建默认风险规则"""
        default_rules = [
            {
                "rule_id": "sensitive_data_access",
                "name": "敏感数据访问",
                "description": "检测访问敏感数据的操作",
                "condition": "'password' in str(context).lower() or 'token' in str(context).lower() or 'api_key' in str(context).lower()",
                "risk_level": "critical",
                "approval_required": True,
                "auto_reject": False,
                "tags": ["data", "security"]
            },
            {
                "rule_id": "high_volume_messages",
                "name": "大量消息发送",
                "description": "检测短时间内发送大量消息",
                "condition": "context.get('message_count', 0) > 10",
                "risk_level": "high",
                "approval_required": True,
                "auto_reject": False,
                "tags": ["messaging", "volume"]
            },
            {
                "rule_id": "external_url_access",
                "name": "外部URL访问",
                "description": "检测访问外部URL的操作",
                "condition": "'http' in str(context).lower() and 'external' in str(context).lower()",
                "risk_level": "medium",
                "approval_required": True,
                "auto_reject": False,
                "tags": ["network", "external"]
            },
            {
                "rule_id": "file_operation",
                "name": "文件操作",
                "description": "检测文件读写操作",
                "condition": "any(op in str(context).lower() for op in ['file_read', 'file_write', 'file_delete'])",
                "risk_level": "medium",
                "approval_required": True,
                "auto_reject": False,
                "tags": ["file", "system"]
            },
            {
                "rule_id": "system_command",
                "name": "系统命令执行",
                "description": "检测系统命令执行",
                "condition": "'command' in context and 'system' in str(context).lower()",
                "risk_level": "critical",
                "approval_required": True,
                "auto_reject": True,
                "tags": ["system", "command"]
            }
        ]

        for rule_data in default_rules:
            rule = RiskRule(**rule_data)
            self.rules.append(rule)

        self._save_rules()

    def _save_rules(self):
        """保存风险规则"""
        try:
            self.rules_config.parent.mkdir(parents=True, exist_ok=True)

            rules_data = {
                'rules': [asdict(rule) for rule in self.rules],
                'updated_at': datetime.now().isoformat()
            }

            with open(self.rules_config, 'w') as f:
                json.dump(rules_data, f, indent=2, default=str)

        except Exception as e:
            logger.error(f"Failed to save risk rules: {e}")

    def assess_risk(self, context: Dict) -> tuple[RiskLevel, List[str], bool]:
        """评估风险级别"""
        max_risk = RiskLevel.LOW
        triggered_rules = []
        auto_reject = False

        for rule in self.rules:
            try:
                # 安全地评估条件
                if self._evaluate_condition(rule.condition, context):
                    triggered_rules.append(rule.rule_id)

                    # 更新最高风险级别
                    if self._risk_level_value(rule.risk_level) > self._risk_level_value(max_risk):
                        max_risk = rule.risk_level

                    # 检查是否需要自动拒绝
                    if rule.auto_reject:
                        auto_reject = True

            except Exception as e:
                logger.warning(f"Failed to evaluate rule {rule.rule_id}: {e}")

        return max_risk, triggered_rules, auto_reject

    def _evaluate_condition(self, condition: str, context: Dict) -> bool:
        """安全地评估条件表达式"""
        try:
            # 创建安全的评估环境
            safe_globals = {
                '__builtins__': {},
                'str': str,
                'len': len,
                'any': any,
                'all': all,
                'context': context
            }

            return eval(condition, safe_globals)

        except Exception as e:
            logger.warning(f"Failed to evaluate condition '{condition}': {e}")
            return False

    def _risk_level_value(self, risk_level: RiskLevel) -> int:
        """获取风险级别的数值"""
        level_values = {
            RiskLevel.LOW: 1,
            RiskLevel.MEDIUM: 2,
            RiskLevel.HIGH: 3,
            RiskLevel.CRITICAL: 4
        }
        return level_values.get(risk_level, 1)


class HITLSystem:
    """HITL审批流系统"""

    def __init__(self, storage_path: str = "data/hitl", chat_adapter: ChatAdapter = None):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self.chat_adapter = chat_adapter
        self.risk_assessor = RiskAssessment()

        # 审批请求存储
        self.pending_requests: Dict[str, ApprovalRequest] = {}
        self.request_history: Dict[str, ApprovalRequest] = {}

        # 审批模板
        self.templates: Dict[str, ApprovalTemplate] = {}
        self._load_templates()

        # 审批人配置
        self.approvers: Dict[str, Dict] = {}
        self._load_approvers()

        # 回调处理器
        self.approval_handlers: Dict[str, Callable[[ApprovalRequest], None]] = {}

        # 加载持久化数据
        self._load_requests()

    def _load_templates(self):
        """加载审批模板"""
        try:
            template_file = self.storage_path / "approval_templates.json"
            if template_file.exists():
                with open(template_file, 'r') as f:
                    templates_data = json.load(f)

                for template_data in templates_data.get('templates', []):
                    template = ApprovalTemplate(**template_data)
                    self.templates[template.template_id] = template

            else:
                self._create_default_templates()

        except Exception as e:
            logger.error(f"Failed to load approval templates: {e}")
            self._create_default_templates()

    def _create_default_templates(self):
        """创建默认审批模板"""
        default_templates = [
            ApprovalTemplate(
                template_id="workflow_start",
                name="工作流启动审批",
                risk_level=RiskLevel.MEDIUM,
                title_template="工作流启动审批: {workflow_id}",
                description_template="请求启动工作流 {workflow_id}，风险级别: {risk_level}",
                expiry_minutes=30,
                required_approvers=1
            ),
            ApprovalTemplate(
                template_id="high_risk_action",
                name="高风险动作审批",
                risk_level=RiskLevel.HIGH,
                title_template="高风险动作审批: {action_type}",
                description_template="请求执行高风险动作: {action_description}",
                expiry_minutes=15,
                required_approvers=1
            ),
            ApprovalTemplate(
                template_id="critical_operation",
                name="关键操作审批",
                risk_level=RiskLevel.CRITICAL,
                title_template="关键操作审批: {operation}",
                description_template="请求执行关键操作，需要立即审批: {operation_description}",
                expiry_minutes=10,
                required_approvers=2
            )
        ]

        for template in default_templates:
            self.templates[template.template_id] = template

        self._save_templates()

    def _save_templates(self):
        """保存审批模板"""
        try:
            template_file = self.storage_path / "approval_templates.json"
            templates_data = {
                'templates': [asdict(template) for template in self.templates.values()],
                'updated_at': datetime.now().isoformat()
            }

            with open(template_file, 'w') as f:
                json.dump(templates_data, f, indent=2, default=str)

        except Exception as e:
            logger.error(f"Failed to save approval templates: {e}")

    def _load_approvers(self):
        """加载审批人配置"""
        try:
            approvers_file = self.storage_path / "approvers.json"
            if approvers_file.exists():
                with open(approvers_file, 'r') as f:
                    self.approvers = json.load(f)
            else:
                # 创建默认审批人配置
                self.approvers = {
                    "admin": {
                        "name": "系统管理员",
                        "chat_id": "admin_chat",
                        "risk_levels": ["low", "medium", "high", "critical"],
                        "active": True
                    },
                    "supervisor": {
                        "name": "主管",
                        "chat_id": "supervisor_chat",
                        "risk_levels": ["medium", "high"],
                        "active": True
                    }
                }
                self._save_approvers()

        except Exception as e:
            logger.error(f"Failed to load approvers: {e}")

    def _save_approvers(self):
        """保存审批人配置"""
        try:
            approvers_file = self.storage_path / "approvers.json"
            with open(approvers_file, 'w') as f:
                json.dump(self.approvers, f, indent=2)

        except Exception as e:
            logger.error(f"Failed to save approvers: {e}")

    async def request_approval(self,
                              request_type: ApprovalType,
                              title: str,
                              description: str,
                              context: Dict,
                              requester_id: str = "system",
                              workflow_id: str = None,
                              step_id: str = None,
                              chat_id: str = None,
                              timeout_minutes: int = None) -> str:
        """请求审批"""

        # 风险评估
        risk_level, triggered_rules, auto_reject = self.risk_assessor.assess_risk(context)

        if auto_reject:
            logger.warning(f"Request auto-rejected due to high risk: {triggered_rules}")
            raise Exception(f"Request automatically rejected: {triggered_rules}")

        # 创建审批请求
        request_id = str(uuid.uuid4())
        expires_at = None

        if timeout_minutes:
            expires_at = datetime.now() + timedelta(minutes=timeout_minutes)

        request = ApprovalRequest(
            request_id=request_id,
            request_type=request_type,
            risk_level=risk_level,
            title=title,
            description=description,
            context=context,
            requester_id=requester_id,
            created_at=datetime.now(),
            expires_at=expires_at,
            workflow_id=workflow_id,
            step_id=step_id,
            chat_id=chat_id,
            tags={"triggered_rules": triggered_rules}
        )

        # 存储请求
        self.pending_requests[request_id] = request

        # 发送审批通知
        await self._send_approval_notification(request)

        # 持久化
        self._save_requests()

        logger.info(f"Created approval request {request_id} with risk level {risk_level.value}")
        return request_id

    async def approve_request(self, request_id: str, approver_id: str) -> bool:
        """审批通过"""
        request = self.pending_requests.get(request_id)
        if not request:
            logger.warning(f"Approval request not found: {request_id}")
            return False

        if request.status != ApprovalStatus.PENDING:
            logger.warning(f"Request {request_id} is not pending")
            return False

        # 检查审批人权限
        if not self._can_approve(approver_id, request.risk_level):
            logger.warning(f"Approver {approver_id} cannot approve risk level {request.risk_level}")
            return False

        # 更新请求状态
        request.status = ApprovalStatus.APPROVED
        request.approver_id = approver_id
        request.approved_at = datetime.now()

        # 移动到历史记录
        self.request_history[request_id] = request
        del self.pending_requests[request_id]

        # 通知审批结果
        await self._notify_approval_result(request, approved=True)

        # 触发回调
        handler = self.approval_handlers.get(request_id)
        if handler:
            try:
                handler(request)
                del self.approval_handlers[request_id]
            except Exception as e:
                logger.error(f"Approval handler error: {e}")

        self._save_requests()
        logger.info(f"Request {request_id} approved by {approver_id}")
        return True

    async def reject_request(self, request_id: str, approver_id: str, reason: str = "") -> bool:
        """审批拒绝"""
        request = self.pending_requests.get(request_id)
        if not request:
            return False

        if request.status != ApprovalStatus.PENDING:
            return False

        # 检查审批人权限
        if not self._can_approve(approver_id, request.risk_level):
            return False

        # 更新请求状态
        request.status = ApprovalStatus.REJECTED
        request.approver_id = approver_id
        request.approved_at = datetime.now()
        request.rejection_reason = reason

        # 移动到历史记录
        self.request_history[request_id] = request
        del self.pending_requests[request_id]

        # 通知审批结果
        await self._notify_approval_result(request, approved=False)

        # 触发回调
        handler = self.approval_handlers.get(request_id)
        if handler:
            try:
                handler(request)
                del self.approval_handlers[request_id]
            except Exception as e:
                logger.error(f"Approval handler error: {e}")

        self._save_requests()
        logger.info(f"Request {request_id} rejected by {approver_id}: {reason}")
        return True

    def wait_for_approval(self, request_id: str,
                         callback: Callable[[ApprovalRequest], None] = None) -> ApprovalRequest:
        """等待审批结果"""
        if callback:
            self.approval_handlers[request_id] = callback

        request = self.pending_requests.get(request_id)
        return request

    def get_pending_requests(self, approver_id: str = None) -> List[ApprovalRequest]:
        """获取待审批请求"""
        requests = list(self.pending_requests.values())

        if approver_id:
            # 过滤该审批人可以处理的请求
            filtered_requests = []
            for request in requests:
                if self._can_approve(approver_id, request.risk_level):
                    filtered_requests.append(request)
            requests = filtered_requests

        # 按创建时间排序
        requests.sort(key=lambda r: r.created_at)
        return requests

    def _can_approve(self, approver_id: str, risk_level: RiskLevel) -> bool:
        """检查审批人是否能审批指定风险级别"""
        approver = self.approvers.get(approver_id)
        if not approver or not approver.get('active', True):
            return False

        allowed_levels = approver.get('risk_levels', [])
        return risk_level.value in allowed_levels

    async def _send_approval_notification(self, request: ApprovalRequest):
        """发送审批通知"""
        if not self.chat_adapter:
            logger.warning("No chat adapter configured for approval notifications")
            return

        # 查找合适的审批人
        eligible_approvers = []
        for approver_id, approver in self.approvers.items():
            if self._can_approve(approver_id, request.risk_level):
                eligible_approvers.append(approver)

        # 发送通知消息
        for approver in eligible_approvers:
            try:
                chat_id = approver.get('chat_id')
                if not chat_id:
                    continue

                message = self._format_approval_message(request)
                await self.chat_adapter.send_text(chat_id, message)

                logger.info(f"Sent approval notification to {approver['name']}")

            except Exception as e:
                logger.error(f"Failed to send approval notification: {e}")

    def _format_approval_message(self, request: ApprovalRequest) -> str:
        """格式化审批消息"""
        risk_emoji = {
            RiskLevel.LOW: "🟢",
            RiskLevel.MEDIUM: "🟡",
            RiskLevel.HIGH: "🟠",
            RiskLevel.CRITICAL: "🔴"
        }

        emoji = risk_emoji.get(request.risk_level, "⚪")

        message = f"""
🔍 **审批请求**

{emoji} **风险级别**: {request.risk_level.value.upper()}
📋 **标题**: {request.title}
📝 **描述**: {request.description}
👤 **申请人**: {request.requester_id}
🕐 **申请时间**: {request.created_at.strftime('%Y-%m-%d %H:%M:%S')}
🆔 **请求ID**: {request.request_id}

请回复以下命令之一:
• `/approve {request.request_id}` - 批准
• `/reject {request.request_id} [原因]` - 拒绝
        """.strip()

        return message

    async def _notify_approval_result(self, request: ApprovalRequest, approved: bool):
        """通知审批结果"""
        if not self.chat_adapter:
            return

        try:
            # 通知申请人
            if request.chat_id:
                status = "✅ 已批准" if approved else "❌ 已拒绝"
                reason = f"\n拒绝原因: {request.rejection_reason}" if not approved and request.rejection_reason else ""

                message = f"""
📬 **审批结果通知**

🆔 **请求ID**: {request.request_id}
📋 **标题**: {request.title}
📊 **结果**: {status}
👤 **审批人**: {request.approver_id}
🕐 **处理时间**: {request.approved_at.strftime('%Y-%m-%d %H:%M:%S')}{reason}
                """.strip()

                await self.chat_adapter.send_text(request.chat_id, message)

        except Exception as e:
            logger.error(f"Failed to notify approval result: {e}")

    def _load_requests(self):
        """加载持久化的审批请求"""
        try:
            requests_file = self.storage_path / "approval_requests.json"
            if requests_file.exists():
                with open(requests_file, 'r') as f:
                    data = json.load(f)

                # 加载待审批请求
                for request_data in data.get('pending', []):
                    request_data['created_at'] = datetime.fromisoformat(request_data['created_at'])
                    if request_data.get('expires_at'):
                        request_data['expires_at'] = datetime.fromisoformat(request_data['expires_at'])
                    if request_data.get('approved_at'):
                        request_data['approved_at'] = datetime.fromisoformat(request_data['approved_at'])

                    request_data['request_type'] = ApprovalType(request_data['request_type'])
                    request_data['risk_level'] = RiskLevel(request_data['risk_level'])
                    request_data['status'] = ApprovalStatus(request_data['status'])

                    request = ApprovalRequest(**request_data)
                    self.pending_requests[request.request_id] = request

                # 加载历史记录
                for request_data in data.get('history', []):
                    # 同样的转换逻辑
                    request_data['created_at'] = datetime.fromisoformat(request_data['created_at'])
                    if request_data.get('expires_at'):
                        request_data['expires_at'] = datetime.fromisoformat(request_data['expires_at'])
                    if request_data.get('approved_at'):
                        request_data['approved_at'] = datetime.fromisoformat(request_data['approved_at'])

                    request_data['request_type'] = ApprovalType(request_data['request_type'])
                    request_data['risk_level'] = RiskLevel(request_data['risk_level'])
                    request_data['status'] = ApprovalStatus(request_data['status'])

                    request = ApprovalRequest(**request_data)
                    self.request_history[request.request_id] = request

        except Exception as e:
            logger.error(f"Failed to load approval requests: {e}")

    def _save_requests(self):
        """保存审批请求"""
        try:
            requests_file = self.storage_path / "approval_requests.json"

            data = {
                'pending': [asdict(request) for request in self.pending_requests.values()],
                'history': [asdict(request) for request in self.request_history.values()],
                'updated_at': datetime.now().isoformat()
            }

            with open(requests_file, 'w') as f:
                json.dump(data, f, indent=2, default=str)

        except Exception as e:
            logger.error(f"Failed to save approval requests: {e}")

    async def cleanup_expired_requests(self):
        """清理过期的审批请求"""
        now = datetime.now()
        expired_requests = []

        for request_id, request in self.pending_requests.items():
            if request.expires_at and now > request.expires_at:
                expired_requests.append(request_id)

        for request_id in expired_requests:
            request = self.pending_requests[request_id]
            request.status = ApprovalStatus.EXPIRED

            # 移动到历史记录
            self.request_history[request_id] = request
            del self.pending_requests[request_id]

            logger.info(f"Request {request_id} expired")

        if expired_requests:
            self._save_requests()

    def get_approval_stats(self) -> Dict:
        """获取审批统计"""
        total_requests = len(self.pending_requests) + len(self.request_history)
        pending_count = len(self.pending_requests)

        history_by_status = {}
        for request in self.request_history.values():
            status = request.status.value
            history_by_status[status] = history_by_status.get(status, 0) + 1

        risk_level_counts = {}
        all_requests = list(self.pending_requests.values()) + list(self.request_history.values())
        for request in all_requests:
            level = request.risk_level.value
            risk_level_counts[level] = risk_level_counts.get(level, 0) + 1

        return {
            "total_requests": total_requests,
            "pending_requests": pending_count,
            "status_breakdown": history_by_status,
            "risk_level_breakdown": risk_level_counts,
            "active_approvers": len([a for a in self.approvers.values() if a.get('active', True)])
        }


# 全局HITL系统实例
hitl_system = HITLSystem()