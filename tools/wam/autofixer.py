"""
AutoFixer - 工作流自愈和自动晋升系统
"""
import json
import time
import hashlib
import copy
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)

class PatchKind(Enum):
    """补丁类型"""
    WAIT_QUIET_INSERT = "wait_quiet_insert"
    SCROLL_THEN_RETRY = "scroll_then_retry"
    SELECTOR_ROLE_TEXT = "selector_role_text"
    DOM_TO_COORDS_FALLBACK = "dom_to_coords_fallback"
    TIMEOUT_INCREASE_SMALL = "timeout_increase_small"
    ELEMENT_WAIT = "element_wait"
    RETRY_CLICK = "retry_click"
    SCROLL_INTO_VIEW = "scroll_into_view"

class AutofixMode(Enum):
    """自愈模式"""
    SUGGEST_ONLY = "suggest_only"
    HOT_PATCH_SESSION = "hot_patch_session"
    AUTO_PROMOTE_ON_SUCCESS = "auto_promote_on_success"

@dataclass
class AutofixConfig:
    """自愈配置"""
    mode: str = "suggest_only"
    promote: Dict[str, Any] = None
    limits: Dict[str, Any] = None
    allowed_patch_kinds: List[str] = None
    risk_gate: Dict[str, Any] = None

    def __post_init__(self):
        if self.promote is None:
            self.promote = {
                "enabled": False,
                "strategy": "auto_promote_on_success",
                "threshold": {
                    "successes": 20,
                    "window": 50,
                    "min_runs": 30,
                    "max_error_rate": 0.05,
                    "p95_latency_ms": 8000
                },
                "rollout": {
                    "staging_percent": 20,
                    "soak_minutes": 120
                },
                "cooldown_minutes": 30
            }

        if self.limits is None:
            self.limits = {
                "max_patches_per_run": 2,
                "max_total_patches_per_day": 10
            }

        if self.allowed_patch_kinds is None:
            self.allowed_patch_kinds = [
                "wait_quiet_insert",
                "scroll_then_retry",
                "selector_role_text",
                "dom_to_coords_fallback",
                "timeout_increase_small"
            ]

        if self.risk_gate is None:
            self.risk_gate = {
                "max_dom_change_ratio": 0.2,
                "disallow_host_widening": True,
                "disallow_upload_semantics_change": True
            }

@dataclass
class FailureContext:
    """失败上下文"""
    run_id: str
    workflow_id: str
    state: str
    action_index: int
    action: Dict[str, Any]
    error_type: str
    error_message: str
    page_state: Optional[Dict[str, Any]] = None
    screenshot_path: Optional[str] = None
    timestamp: Optional[datetime] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

@dataclass
class PatchProposal:
    """补丁提案"""
    patch_id: str
    workflow_id: str
    base_version: str
    kind: str
    reason: str
    json_patch: List[Dict[str, Any]]
    evidence: Dict[str, Any]
    risk_score: float
    created_at: datetime
    status: str = "proposed"  # proposed | applied | rejected

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["created_at"] = self.created_at.isoformat()
        return result

class AutoFixer:
    """自愈系统"""

    def __init__(self):
        self.patch_stats = {}  # patch_id -> stats
        self.promotion_history = {}  # workflow_id -> last_promotion_time

    def analyze_failure(self, failure_context) -> Dict[str, Any]:
        """分析失败并生成分析结果"""
        try:
            # 支持字典输入
            if isinstance(failure_context, dict):
                error_message = failure_context.get("error_message", "")
                error_type = failure_context.get("error_type", "unknown")
            else:
                error_message = failure_context.error_message
                error_type = failure_context.error_type

            # 分析错误类型
            if "timeout" in error_message.lower():
                category = "timeout_issue"
                confidence = 0.8
                details = ["Action timed out", "May need longer wait time"]
            elif "not found" in error_message.lower() or "not visible" in error_message.lower():
                category = "targeting_issue"
                confidence = 0.9
                details = ["Target element not found", "May need different selector"]
            elif "click failed" in error_message.lower():
                category = "interaction_issue"
                confidence = 0.7
                details = ["Click action failed", "Element may not be clickable"]
            elif "page not settled" in error_message.lower():
                category = "timing_issue"
                confidence = 0.8
                details = ["Page not ready for interaction", "Need to wait for page to settle"]
            else:
                category = "unknown_issue"
                confidence = 0.3
                details = ["Unknown error type", "Manual investigation needed"]

            return {
                "category": category,
                "confidence": confidence,
                "details": details,
                "error_type": error_type
            }

        except Exception as e:
            logger.error(f"Failed to analyze failure: {e}")
            return None

    def generate_patches(self, error_context: Dict[str, Any], analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """生成修复补丁列表"""
        patches = []

        try:
            category = analysis.get("category", "unknown")
            confidence = analysis.get("confidence", 0.5)

            if category == "timeout_issue":
                patches.append({
                    "type": "timeout_increase",
                    "description": "Increase timeout duration",
                    "confidence": confidence,
                    "changes": [
                        {"op": "add", "path": "/timeout", "value": 10000}
                    ]
                })

            elif category == "targeting_issue":
                patches.append({
                    "type": "selector_update",
                    "description": "Update element selector",
                    "confidence": confidence,
                    "changes": [
                        {"op": "replace", "path": "/target/css", "value": "updated-selector"}
                    ]
                })

            elif category == "interaction_issue":
                patches.append({
                    "type": "retry_mechanism",
                    "description": "Add retry mechanism",
                    "confidence": confidence,
                    "changes": [
                        {"op": "add", "path": "/retry", "value": {"max_attempts": 3, "delay": 1000}}
                    ]
                })

            elif category == "timing_issue":
                patches.append({
                    "type": "wait_insertion",
                    "description": "Add wait for page to settle",
                    "confidence": confidence,
                    "changes": [
                        {"op": "add", "path": "/wait_before", "value": {"do": "sleep_ms", "duration": 2000}}
                    ]
                })

            # 通用补丁
            if not patches:
                patches.append({
                    "type": "generic_fix",
                    "description": "Generic error handling",
                    "confidence": 0.3,
                    "changes": [
                        {"op": "add", "path": "/error_handling", "value": True}
                    ]
                })

        except Exception as e:
            logger.error(f"Failed to generate patches: {e}")

        return patches

    def apply_patch(self, workflow_path: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        """应用补丁到工作流文件"""
        try:
            with open(workflow_path, 'r', encoding='utf-8') as f:
                workflow = json.load(f)

            # 简化的补丁应用逻辑
            changes = patch.get("changes", [])
            for change in changes:
                op = change.get("op")
                path = change.get("path", "")
                value = change.get("value")

                # 简单的路径解析和应用
                if op == "add" and path.startswith("/"):
                    key = path[1:]  # 移除前导斜杠
                    workflow[key] = value
                elif op == "replace" and path.startswith("/"):
                    key = path[1:]
                    if key in workflow:
                        workflow[key] = value

            # 保存修改后的工作流
            with open(workflow_path, 'w', encoding='utf-8') as f:
                json.dump(workflow, f, indent=2, ensure_ascii=False)

            return {"success": True, "message": "Patch applied successfully"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def analyze_failure_legacy(self, failure: FailureContext) -> Optional[PatchProposal]:
        """分析失败并生成补丁提案（原版本）"""
        try:
            # 根据错误类型生成不同的补丁
            if "timeout" in failure.error_message.lower():
                return self._generate_timeout_patch(failure)
            elif "not found" in failure.error_message.lower() or "not visible" in failure.error_message.lower():
                return self._generate_element_not_found_patch(failure)
            elif "click failed" in failure.error_message.lower():
                return self._generate_click_failed_patch(failure)
            elif "page not settled" in failure.error_message.lower():
                return self._generate_page_not_settled_patch(failure)
            else:
                return self._generate_generic_patch(failure)

        except Exception as e:
            logger.error(f"Failed to analyze failure: {e}")
            return None

    def _generate_timeout_patch(self, failure: FailureContext) -> Optional[PatchProposal]:
        """生成超时相关补丁"""
        action = failure.action

        # 增加超时时间
        if "timeout_ms" in action:
            current_timeout = action["timeout_ms"]
            new_timeout = min(current_timeout + 2000, 15000)  # 最大15秒

            json_patch = [{
                "op": "replace",
                "path": f"/states/{failure.state}/actions/{failure.action_index}/timeout_ms",
                "value": new_timeout
            }]

            return PatchProposal(
                patch_id=self._generate_patch_id(failure, "timeout_increase"),
                workflow_id=failure.workflow_id,
                base_version="1.0.0",  # 应该从实际工作流获取
                kind=PatchKind.TIMEOUT_INCREASE_SMALL.value,
                reason=f"Increase timeout from {current_timeout}ms to {new_timeout}ms due to timeout error",
                json_patch=json_patch,
                evidence=self._build_evidence(failure),
                risk_score=0.1,
                created_at=datetime.now()
            )

        return None

    def _generate_element_not_found_patch(self, failure: FailureContext) -> Optional[PatchProposal]:
        """生成元素未找到补丁"""
        action = failure.action
        action_type = action.get("do")

        # 在动作前插入等待
        if action_type in ["instr.click", "ext.click_selector", "click"]:
            wait_action = {
                "do": "instr.wait",
                "ms": 1000
            }

            json_patch = [{
                "op": "add",
                "path": f"/states/{failure.state}/actions/{failure.action_index}",
                "value": wait_action
            }]

            return PatchProposal(
                patch_id=self._generate_patch_id(failure, "element_wait"),
                workflow_id=failure.workflow_id,
                base_version="1.0.0",
                kind=PatchKind.ELEMENT_WAIT.value,
                reason="Insert wait before click due to element not found",
                json_patch=json_patch,
                evidence=self._build_evidence(failure),
                risk_score=0.2,
                created_at=datetime.now()
            )

        return None

    def _generate_click_failed_patch(self, failure: FailureContext) -> Optional[PatchProposal]:
        """生成点击失败补丁"""
        action = failure.action

        # 先滚动再重试
        scroll_action = {
            "do": "instr.scroll",
            "dir": "down",
            "amount": 200,
            "target": action.get("target")
        }

        json_patch = [{
            "op": "add",
            "path": f"/states/{failure.state}/actions/{failure.action_index}",
            "value": scroll_action
        }]

        return PatchProposal(
            patch_id=self._generate_patch_id(failure, "scroll_retry"),
            workflow_id=failure.workflow_id,
            base_version="1.0.0",
            kind=PatchKind.SCROLL_THEN_RETRY.value,
            reason="Scroll before click to ensure element is visible",
            json_patch=json_patch,
            evidence=self._build_evidence(failure),
            risk_score=0.15,
            created_at=datetime.now()
        )

    def _generate_page_not_settled_patch(self, failure: FailureContext) -> Optional[PatchProposal]:
        """生成页面未稳定补丁"""
        wait_action = {
            "do": "instr.wait",
            "ms": 500
        }

        json_patch = [{
            "op": "add",
            "path": f"/states/{failure.state}/actions/{failure.action_index}",
            "value": wait_action
        }]

        return PatchProposal(
            patch_id=self._generate_patch_id(failure, "page_settle"),
            workflow_id=failure.workflow_id,
            base_version="1.0.0",
            kind=PatchKind.WAIT_QUIET_INSERT.value,
            reason="Insert wait for page to settle",
            json_patch=json_patch,
            evidence=self._build_evidence(failure),
            risk_score=0.1,
            created_at=datetime.now()
        )

    def _generate_generic_patch(self, failure: FailureContext) -> Optional[PatchProposal]:
        """生成通用补丁"""
        # 通用的等待补丁
        wait_action = {
            "do": "instr.wait",
            "ms": 300
        }

        json_patch = [{
            "op": "add",
            "path": f"/states/{failure.state}/actions/{failure.action_index}",
            "value": wait_action
        }]

        return PatchProposal(
            patch_id=self._generate_patch_id(failure, "generic_wait"),
            workflow_id=failure.workflow_id,
            base_version="1.0.0",
            kind=PatchKind.WAIT_QUIET_INSERT.value,
            reason=f"Generic wait patch for error: {failure.error_message}",
            json_patch=json_patch,
            evidence=self._build_evidence(failure),
            risk_score=0.3,
            created_at=datetime.now()
        )

    def _generate_patch_id(self, failure: FailureContext, patch_type: str) -> str:
        """生成补丁ID"""
        content = f"{failure.workflow_id}:{failure.state}:{failure.action_index}:{patch_type}:{failure.error_type}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _build_evidence(self, failure: FailureContext) -> Dict[str, Any]:
        """构建证据"""
        return {
            "run_id": failure.run_id,
            "state": failure.state,
            "action_index": failure.action_index,
            "error_type": failure.error_type,
            "error_message": failure.error_message,
            "timestamp": failure.timestamp.isoformat(),
            "screenshot": failure.screenshot_path,
            "page_state": failure.page_state
        }

    def apply_patch_to_workflow(self, workflow: Dict[str, Any], patch: PatchProposal) -> Dict[str, Any]:
        """将补丁应用到工作流"""
        import jsonpatch

        try:
            # 创建副本
            patched_workflow = copy.deepcopy(workflow)

            # 应用JSON patch
            patch_obj = jsonpatch.JsonPatch(patch.json_patch)
            patched_workflow = patch_obj.apply(patched_workflow)

            logger.info(f"Applied patch {patch.patch_id} to workflow {patch.workflow_id}")
            return patched_workflow

        except Exception as e:
            logger.error(f"Failed to apply patch {patch.patch_id}: {e}")
            raise

    def should_apply_patch(self, patch: PatchProposal, config: AutofixConfig) -> Tuple[bool, str]:
        """判断是否应该应用补丁"""
        # 检查补丁类型是否被允许
        if patch.kind not in config.allowed_patch_kinds:
            return False, f"Patch kind '{patch.kind}' not in allowed list"

        # 检查风险分数
        if patch.risk_score > 0.5:
            return False, f"Risk score too high: {patch.risk_score}"

        # 检查风险门
        if config.risk_gate.get("disallow_host_widening") and self._patch_widens_host(patch):
            return False, "Patch widens host scope"

        if config.risk_gate.get("disallow_upload_semantics_change") and self._patch_changes_upload(patch):
            return False, "Patch changes upload semantics"

        return True, ""

    def _patch_widens_host(self, patch: PatchProposal) -> bool:
        """检查补丁是否扩大了主机范围"""
        # 简化实现，实际需要分析JSON patch内容
        for operation in patch.json_patch:
            if "url" in str(operation.get("value", {})):
                return True
        return False

    def _patch_changes_upload(self, patch: PatchProposal) -> bool:
        """检查补丁是否改变了上传语义"""
        for operation in patch.json_patch:
            value = operation.get("value", {})
            if isinstance(value, dict) and value.get("do") == "instr.upload":
                return True
        return False

    def record_patch_execution(self, patch_id: str, success: bool, duration_ms: int):
        """记录补丁执行结果"""
        if patch_id not in self.patch_stats:
            self.patch_stats[patch_id] = {
                "total_runs": 0,
                "successes": 0,
                "failures": 0,
                "total_duration_ms": 0,
                "durations": []
            }

        stats = self.patch_stats[patch_id]
        stats["total_runs"] += 1
        stats["total_duration_ms"] += duration_ms
        stats["durations"].append(duration_ms)

        # 保持最近50次的记录
        if len(stats["durations"]) > 50:
            old_duration = stats["durations"].pop(0)
            stats["total_duration_ms"] -= old_duration

        if success:
            stats["successes"] += 1
        else:
            stats["failures"] += 1

    def should_promote_patch(self, patch_id: str, workflow_id: str, config: AutofixConfig) -> bool:
        """判断是否应该自动晋升补丁"""
        if not config.promote.get("enabled"):
            return False

        if config.mode != AutofixMode.AUTO_PROMOTE_ON_SUCCESS.value:
            return False

        # 检查冷却期
        last_promotion = self.promotion_history.get(workflow_id)
        if last_promotion:
            cooldown = timedelta(minutes=config.promote.get("cooldown_minutes", 30))
            if datetime.now() - last_promotion < cooldown:
                return False

        # 检查统计数据
        stats = self.patch_stats.get(patch_id, {})
        threshold = config.promote["threshold"]

        if stats.get("total_runs", 0) < threshold.get("min_runs", 30):
            return False

        if stats.get("successes", 0) < threshold.get("successes", 20):
            return False

        # 计算错误率
        total_runs = stats.get("total_runs", 0)
        failures = stats.get("failures", 0)
        error_rate = failures / total_runs if total_runs > 0 else 1.0

        if error_rate > threshold.get("max_error_rate", 0.05):
            return False

        # 计算P95延迟
        durations = stats.get("durations", [])
        if durations:
            durations_sorted = sorted(durations)
            p95_index = int(len(durations_sorted) * 0.95)
            p95_latency = durations_sorted[p95_index] if p95_index < len(durations_sorted) else durations_sorted[-1]

            if p95_latency > threshold.get("p95_latency_ms", 8000):
                return False

        return True

    def promote_patch(self, patch: PatchProposal, workflow: Dict[str, Any], config: AutofixConfig) -> Dict[str, Any]:
        """晋升补丁为新版本"""
        try:
            # 应用补丁创建新版本
            new_workflow = self.apply_patch_to_workflow(workflow, patch)

            # 更新版本号
            current_version = workflow.get("version", "1.0.0")
            new_version = self._bump_version(current_version, "minor")
            new_workflow["version"] = new_version

            # 记录晋升时间
            self.promotion_history[patch.workflow_id] = datetime.now()

            logger.info(f"Promoted patch {patch.patch_id} to version {new_version}")
            return new_workflow

        except Exception as e:
            logger.error(f"Failed to promote patch {patch.patch_id}: {e}")
            raise

    def _bump_version(self, version: str, bump_type: str = "minor") -> str:
        """版本号递增"""
        try:
            parts = version.split(".")
            major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0

            if bump_type == "major":
                major += 1
                minor = 0
                patch = 0
            elif bump_type == "minor":
                minor += 1
                patch = 0
            else:  # patch
                patch += 1

            return f"{major}.{minor}.{patch}"

        except Exception:
            return "1.0.1"  # 默认版本

class AutofixManager:
    """自愈管理器"""

    def __init__(self):
        self.autofixer = AutoFixer()
        self.pending_patches = {}  # workflow_id -> List[PatchProposal]

    def handle_workflow_failure(self, failure: FailureContext,
                               workflow: Dict[str, Any],
                               config: AutofixConfig) -> Optional[Dict[str, Any]]:
        """处理工作流失败"""
        try:
            # 分析失败生成补丁
            patch = self.autofixer.analyze_failure(failure)
            if not patch:
                logger.warning(f"No patch generated for failure in {failure.workflow_id}")
                return None

            # 检查是否应该应用补丁
            should_apply, reason = self.autofixer.should_apply_patch(patch, config)
            if not should_apply:
                logger.info(f"Patch {patch.patch_id} not applied: {reason}")
                self._store_patch_proposal(patch)
                return None

            # 根据模式决定如何处理
            if config.mode == AutofixMode.SUGGEST_ONLY.value:
                self._store_patch_proposal(patch)
                logger.info(f"Patch {patch.patch_id} stored as suggestion")
                return None

            elif config.mode in [AutofixMode.HOT_PATCH_SESSION.value, AutofixMode.AUTO_PROMOTE_ON_SUCCESS.value]:
                # 应用临时补丁
                patched_workflow = self.autofixer.apply_patch_to_workflow(workflow, patch)
                logger.info(f"Applied hot patch {patch.patch_id} for current session")
                return patched_workflow

            return None

        except Exception as e:
            logger.error(f"Failed to handle workflow failure: {e}")
            return None

    def _store_patch_proposal(self, patch: PatchProposal):
        """存储补丁提案"""
        if patch.workflow_id not in self.pending_patches:
            self.pending_patches[patch.workflow_id] = []

        self.pending_patches[patch.workflow_id].append(patch)
        logger.info(f"Stored patch proposal {patch.patch_id}")

    def get_pending_patches(self, workflow_id: str) -> List[PatchProposal]:
        """获取待处理补丁"""
        return self.pending_patches.get(workflow_id, [])

    def adopt_patch(self, patch_id: str, workflow: Dict[str, Any]) -> Dict[str, Any]:
        """采纳补丁"""
        # 查找补丁
        patch = None
        for patches in self.pending_patches.values():
            for p in patches:
                if p.patch_id == patch_id:
                    patch = p
                    break
            if patch:
                break

        if not patch:
            raise ValueError(f"Patch {patch_id} not found")

        # 应用补丁
        return self.autofixer.apply_patch_to_workflow(workflow, patch)

# 全局管理器实例
autofix_manager = AutofixManager()

def handle_failure(failure_context: FailureContext,
                  workflow: Dict[str, Any],
                  autofix_config: AutofixConfig) -> Optional[Dict[str, Any]]:
    """处理失败的便利函数"""
    return autofix_manager.handle_workflow_failure(failure_context, workflow, autofix_config)