"""
WAM工作流验证器
包含JSON Schema验证和语义规则验证
"""
import json
import re
import os
import logging
from typing import Dict, List, Any, Set, Tuple, Optional
from pathlib import Path

try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

logger = logging.getLogger(__name__)

class ValidationError(Exception):
    """验证错误"""
    pass

class WorkflowValidator:
    """工作流验证器"""

    def __init__(self, schema_path: Optional[str] = None):
        """初始化验证器"""
        self.schema = None
        if schema_path:
            self.load_schema(schema_path)
        elif HAS_JSONSCHEMA:
            # 尝试加载默认schema
            default_schema = Path(__file__).parent.parent.parent / "schema" / "workflow.schema.json"
            if default_schema.exists():
                self.load_schema(str(default_schema))

    def load_schema(self, schema_path: str) -> None:
        """加载JSON Schema"""
        try:
            with open(schema_path, 'r', encoding='utf-8') as f:
                self.schema = json.load(f)
            logger.info(f"Loaded workflow schema from {schema_path}")
        except Exception as e:
            logger.warning(f"Failed to load schema: {e}")
            self.schema = None

    def validate(self, workflow: Dict[str, Any]) -> Dict[str, Any]:
        """完整验证工作流"""
        errors = []
        warnings = []

        # JSON Schema验证
        if self.schema and HAS_JSONSCHEMA:
            schema_result = self._validate_schema(workflow)
            if not schema_result["valid"]:
                errors.extend(schema_result["errors"])
        elif not HAS_JSONSCHEMA:
            warnings.append("jsonschema library not available, skipping schema validation")

        # 语义验证
        semantic_result = self._validate_semantics(workflow)
        if not semantic_result["valid"]:
            errors.extend(semantic_result["errors"])
        warnings.extend(semantic_result.get("warnings", []))

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }

    def _validate_schema(self, workflow: Dict[str, Any]) -> Dict[str, Any]:
        """JSON Schema验证"""
        try:
            jsonschema.validate(workflow, self.schema)
            return {"valid": True, "errors": []}
        except jsonschema.ValidationError as e:
            return {
                "valid": False,
                "errors": [f"Schema validation failed: {e.message}"]
            }
        except Exception as e:
            return {
                "valid": False,
                "errors": [f"Schema validation error: {str(e)}"]
            }

    def _validate_semantics(self, workflow: Dict[str, Any]) -> Dict[str, Any]:
        """语义验证"""
        errors = []
        warnings = []

        try:
            # 基础结构验证
            structure_errors = self._validate_structure(workflow)
            errors.extend(structure_errors)

            # 变量引用验证
            variable_errors = self._validate_variables(workflow)
            errors.extend(variable_errors)

            # 状态可达性验证
            reachability_errors = self._validate_reachability(workflow)
            errors.extend(reachability_errors)

            # 循环终止性验证
            loop_errors, loop_warnings = self._validate_loops(workflow)
            errors.extend(loop_errors)
            warnings.extend(loop_warnings)

            # 动作语义验证
            action_errors = self._validate_actions(workflow)
            errors.extend(action_errors)

        except Exception as e:
            errors.append(f"Semantic validation error: {str(e)}")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }

    def _validate_structure(self, workflow: Dict[str, Any]) -> List[str]:
        """验证基础结构"""
        errors = []

        # 检查必需字段
        required_fields = ["start", "states"]
        for field in required_fields:
            if field not in workflow:
                errors.append(f"Missing required field: {field}")

        if "start" in workflow and "states" in workflow:
            start_state = workflow["start"]
            states = workflow["states"]

            # 检查start状态是否存在
            if start_state not in states:
                errors.append(f"Start state '{start_state}' not found in states")

            # 检查每个状态是否有actions
            for state_name, state_def in states.items():
                if not isinstance(state_def, dict):
                    errors.append(f"State '{state_name}' must be an object")
                    continue

                if "actions" not in state_def:
                    errors.append(f"State '{state_name}' missing required field 'actions'")
                elif not isinstance(state_def["actions"], list):
                    errors.append(f"State '{state_name}' actions must be a list")
                elif len(state_def["actions"]) == 0:
                    errors.append(f"State '{state_name}' actions cannot be empty")

        return errors

    def _validate_variables(self, workflow: Dict[str, Any]) -> List[str]:
        """验证变量引用"""
        errors = []

        # 收集所有定义的变量
        defined_vars = set()
        if "vars" in workflow:
            defined_vars.update(workflow["vars"].keys())

        # 收集动作中保存的变量
        saved_vars = set()
        for state_name, state_def in workflow.get("states", {}).items():
            for action in state_def.get("actions", []):
                if isinstance(action, dict) and "save" in action:
                    saved_vars.add(action["save"])

        all_defined_vars = defined_vars | saved_vars

        # 检查变量引用
        referenced_vars = self._find_variable_references(workflow)
        for var_name in referenced_vars:
            if var_name not in all_defined_vars:
                errors.append(f"Undefined variable reference: @{var_name}")

        return errors

    def _find_variable_references(self, obj: Any, refs: Optional[Set[str]] = None) -> Set[str]:
        """递归查找变量引用"""
        if refs is None:
            refs = set()

        if isinstance(obj, str):
            # 查找@variable格式的引用
            matches = re.findall(r'@([a-zA-Z_][a-zA-Z0-9_]*(?:\[[^\]]*\])?)', obj)
            for match in matches:
                # 移除数组索引部分
                var_name = match.split('[')[0]
                refs.add(var_name)

        elif isinstance(obj, list):
            for item in obj:
                self._find_variable_references(item, refs)

        elif isinstance(obj, dict):
            for value in obj.values():
                self._find_variable_references(value, refs)

        return refs

    def _validate_reachability(self, workflow: Dict[str, Any]) -> List[str]:
        """验证状态可达性"""
        errors = []

        states = workflow.get("states", {})
        if not states:
            return errors

        start_state = workflow.get("start")
        if not start_state:
            return errors

        # 构建状态转换图
        transitions = {}
        for state_name, state_def in states.items():
            transitions[state_name] = set()

            # on_success转换
            if "on_success" in state_def and state_def["on_success"]:
                transitions[state_name].add(state_def["on_success"])

            # on_error转换
            if "on_error" in state_def and state_def["on_error"]:
                transitions[state_name].add(state_def["on_error"])

            # transitions转换
            for transition in state_def.get("transitions", []):
                if "go_to" in transition:
                    transitions[state_name].add(transition["go_to"])
                if "else_go_to" in transition:
                    transitions[state_name].add(transition["else_go_to"])

        # 检查可达性
        reachable = set()
        to_visit = [start_state]

        while to_visit:
            current = to_visit.pop()
            if current in reachable:
                continue
            reachable.add(current)

            for next_state in transitions.get(current, []):
                if next_state and next_state not in reachable:
                    to_visit.append(next_state)

        # 找出不可达的状态
        unreachable = set(states.keys()) - reachable
        for state in unreachable:
            errors.append(f"Unreachable state: {state}")

        # 检查引用的状态是否存在
        all_referenced_states = set()
        for target_states in transitions.values():
            all_referenced_states.update(target_states)

        for state in all_referenced_states:
            if state and state not in states:
                errors.append(f"Referenced state '{state}' does not exist")

        return errors

    def _validate_loops(self, workflow: Dict[str, Any]) -> Tuple[List[str], List[str]]:
        """验证循环终止性"""
        errors = []
        warnings = []

        states = workflow.get("states", {})

        # 检测自循环
        self_loops = []
        for state_name, state_def in states.items():
            targets = set()

            if state_def.get("on_success") == state_name:
                targets.add("on_success")
            if state_def.get("on_error") == state_name:
                targets.add("on_error")

            for transition in state_def.get("transitions", []):
                if transition.get("go_to") == state_name:
                    targets.add("transition")
                if transition.get("else_go_to") == state_name:
                    targets.add("transition")

            if targets:
                self_loops.append((state_name, targets))

        # 分析自循环是否有终止条件
        for state_name, loop_types in self_loops:
            state_def = states[state_name]

            has_termination = False

            # 检查是否有transitions（条件分支）
            if state_def.get("transitions"):
                for transition in state_def["transitions"]:
                    if transition.get("go_to") != state_name or transition.get("else_go_to") != state_name:
                        has_termination = True
                        break

            # 检查是否有计数器递增
            has_counter = False
            for action in state_def.get("actions", []):
                if isinstance(action, dict) and action.get("do") == "increment_variable":
                    has_counter = True
                    break

            # 检查是否有等待（轮询模式）
            has_wait = False
            for action in state_def.get("actions", []):
                if isinstance(action, dict) and action.get("do") in ["sleep_ms", "wait_for", "instr.wait"]:
                    has_wait = True
                    break

            if not has_termination:
                if has_counter:
                    warnings.append(f"State '{state_name}' has infinite loop with counter - ensure termination condition exists")
                elif has_wait:
                    warnings.append(f"State '{state_name}' appears to be polling loop - consider adding termination condition")
                else:
                    errors.append(f"State '{state_name}' has infinite loop without termination condition")

        return errors, warnings

    def _validate_actions(self, workflow: Dict[str, Any]) -> List[str]:
        """验证动作语义"""
        errors = []

        # 定义已知的动作类型
        known_actions = {
            # 基础动作
            "sleep_ms", "open_url", "screenshot", "wait_for", "goto_state",
            # 检测动作
            "detect", "locate", "yolo_detect",
            # 浏览器动作
            "click", "type_text", "scroll", "go_back", "refresh",
            # 扩展动作
            "ext.navigate", "ext.click_selector", "ext.type_text", "ext.key",
            "ext.scroll", "ext.extract", "ext.get_pagestate", "ext.wait_quiet",
            # 指令动作
            "instr.click", "instr.type_text", "instr.select_option", "instr.scroll",
            "instr.navigate", "instr.history", "instr.hover", "instr.key",
            "instr.upload", "instr.read", "instr.wait", "instr.task_complete",
            "instr.answer_user", "instr.annotate",
            # 变量动作
            "set_variable", "increment_variable", "get_list_length", "get_list_item", "query_data",
            # 坐标动作
            "click_coordinates", "wheel_coordinates",
            # 消息队列动作
            "mq.consume", "mq.ack", "mq.publish",
            # OCR动作
            "ocr.run", "ocr_extract",
            # 聊天动作
            "chat.send", "chat.receive",
            # 系统动作
            "authenticate", "secure_operation", "platform_detect",
            # 任务动作
            "task.run", "task.validate", "task.list", "task.sync", "task.install",
            # 记忆动作
            "mem.recall", "plan.reflect",
            # LLM动作
            "llm_decide", "llm.submit", "llm.plan"
        }

        for state_name, state_def in workflow.get("states", {}).items():
            for i, action in enumerate(state_def.get("actions", [])):
                if not isinstance(action, dict):
                    errors.append(f"State '{state_name}' action {i} must be an object")
                    continue

                if "do" not in action:
                    errors.append(f"State '{state_name}' action {i} missing 'do' field")
                    continue

                action_type = action["do"]
                if action_type not in known_actions:
                    errors.append(f"State '{state_name}' action {i}: unknown action type '{action_type}'")

                # 验证特定动作的必需参数
                errors.extend(self._validate_action_params(state_name, i, action))

        return errors

    def _validate_action_params(self, state_name: str, action_index: int, action: Dict[str, Any]) -> List[str]:
        """验证动作参数"""
        errors = []
        action_type = action.get("do")

        # 定义动作的必需参数
        required_params = {
            "instr.click": ["target"],
            "instr.type_text": ["target", "text"],
            "instr.select_option": ["target", "value"],
            "instr.scroll": ["dir"],
            "instr.navigate": ["url"],
            "instr.history": ["op"],
            "instr.hover": ["target"],
            "instr.key": ["key"],
            "instr.upload": ["target", "file"],
            "instr.answer_user": ["text"],
            "instr.annotate": ["text"],
            "task.run": ["name"],
            "task.validate": ["name"],
            "task.install": ["name"],
            "mem.recall": ["goal"],
            "sleep_ms": ["duration"],
            "open_url": ["url"],
            "goto_state": ["state"],
            "set_variable": ["name", "value"],
            "increment_variable": ["name"],
            "click_coordinates": ["bbox"],
            "type_text": ["text"],
            "ext.click_selector": ["sel"],
            "ext.type_text": ["sel", "text"],
            "ext.navigate": ["url"]
        }

        if action_type in required_params:
            for param in required_params[action_type]:
                if param not in action:
                    errors.append(
                        f"State '{state_name}' action {action_index}: "
                        f"missing required parameter '{param}' for action '{action_type}'"
                    )

        return errors

    def validate_file(self, workflow_path: str) -> Dict[str, Any]:
        """验证工作流文件"""
        try:
            with open(workflow_path, 'r', encoding='utf-8') as f:
                workflow = json.load(f)
            return self.validate(workflow)
        except Exception as e:
            return {
                "valid": False,
                "errors": [f"Failed to load workflow file: {str(e)}"],
                "warnings": []
            }

# 便利函数
def validate_workflow(workflow: Dict[str, Any], schema_path: Optional[str] = None) -> Dict[str, Any]:
    """验证工作流"""
    validator = WorkflowValidator(schema_path)
    return validator.validate(workflow)

def validate_workflow_file(workflow_path: str, schema_path: Optional[str] = None) -> Dict[str, Any]:
    """验证工作流文件"""
    validator = WorkflowValidator(schema_path)
    return validator.validate_file(workflow_path)

# CLI入口
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python workflow_validator.py <workflow_file> [schema_file]")
        sys.exit(1)

    workflow_file = sys.argv[1]
    schema_file = sys.argv[2] if len(sys.argv) > 2 else None

    result = validate_workflow_file(workflow_file, schema_file)

    print(f"Validation result: {'PASS' if result['valid'] else 'FAIL'}")

    if result["errors"]:
        print("\nErrors:")
        for error in result["errors"]:
            print(f"  - {error}")

    if result["warnings"]:
        print("\nWarnings:")
        for warning in result["warnings"]:
            print(f"  - {warning}")

    sys.exit(0 if result["valid"] else 1)