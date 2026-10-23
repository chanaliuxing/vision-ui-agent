"""
微计划器 - MicroPlanV1实现
按照upgrade.md Sprint C规范：≤5步短计划、白名单动作、来源校验
"""
import logging
import json
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class MicroPlanner:
    def __init__(self):
        self.max_steps = 5  # MicroPlanV1限制：≤5步
        self.allowed_actions = {
            # 基础动作白名单
            'click_coordinates',
            'wheel_coordinates',
            'ext.extract',
            'ext.click_selector',
            'ext.type_text',
            'wait_for',
            'set_variable',
            'get_list_item',
            'branch'
        }

    def generate_plan(self, goal: str, context: Dict, page_state: Dict = None) -> Dict:
        """
        生成微计划

        Args:
            goal: 目标描述
            context: 当前上下文（变量等）
            page_state: 页面状态

        Returns:
            Dict: 计划结果 {steps: [...], metadata: {...}}
        """
        try:
            plan_start = datetime.now()

            # 分析目标和上下文
            analysis = self._analyze_goal_and_context(goal, context, page_state)

            # 生成计划步骤
            steps = self._generate_plan_steps(analysis)

            # 验证计划
            if not self._validate_plan(steps):
                return {
                    "ok": False,
                    "error": "Plan validation failed",
                    "steps": []
                }

            plan_duration = (datetime.now() - plan_start).total_seconds()

            return {
                "ok": True,
                "steps": steps,
                "metadata": {
                    "goal": goal,
                    "step_count": len(steps),
                    "plan_duration_ms": int(plan_duration * 1000),
                    "planner_version": "MicroPlanV1",
                    "generated_at": plan_start.isoformat()
                }
            }

        except Exception as e:
            logger.error(f"Plan generation failed: {str(e)}")
            return {
                "ok": False,
                "error": str(e),
                "steps": []
            }

    def _analyze_goal_and_context(self, goal: str, context: Dict, page_state: Dict) -> Dict:
        """分析目标和上下文"""
        analysis = {
            "goal_type": "unknown",
            "required_actions": [],
            "context_vars": list(context.get('variables', {}).keys()),
            "page_elements": []
        }

        # 简化的目标分析（实际应该使用LLM）
        if "点击" in goal or "click" in goal.lower():
            analysis["goal_type"] = "click_action"
            analysis["required_actions"] = ["click_coordinates"]

        elif "滚动" in goal or "scroll" in goal.lower():
            analysis["goal_type"] = "scroll_action"
            analysis["required_actions"] = ["wheel_coordinates"]

        elif "输入" in goal or "type" in goal.lower():
            analysis["goal_type"] = "input_action"
            analysis["required_actions"] = ["ext.type_text"]

        elif "等待" in goal or "wait" in goal.lower():
            analysis["goal_type"] = "wait_action"
            analysis["required_actions"] = ["wait_for"]

        else:
            # 复合目标
            analysis["goal_type"] = "compound"
            analysis["required_actions"] = ["ext.extract", "click_coordinates", "wait_for"]

        # 提取页面元素信息（如果有）
        if page_state:
            analysis["page_elements"] = page_state.get("elements", [])
            analysis["containers"] = page_state.get("containers", [])

        return analysis

    def _generate_plan_steps(self, analysis: Dict) -> List[Dict]:
        """生成计划步骤"""
        steps = []
        goal_type = analysis["goal_type"]

        if goal_type == "click_action":
            steps = self._generate_click_plan(analysis)
        elif goal_type == "scroll_action":
            steps = self._generate_scroll_plan(analysis)
        elif goal_type == "input_action":
            steps = self._generate_input_plan(analysis)
        elif goal_type == "wait_action":
            steps = self._generate_wait_plan(analysis)
        else:
            # 复合目标的通用计划
            steps = self._generate_compound_plan(analysis)

        # 确保不超过最大步数
        if len(steps) > self.max_steps:
            logger.warning(f"Plan truncated from {len(steps)} to {self.max_steps} steps")
            steps = steps[:self.max_steps]

        return steps

    def _generate_click_plan(self, analysis: Dict) -> List[Dict]:
        """生成点击计划"""
        return [
            {
                "step": 1,
                "action": "ext.extract",
                "description": "提取页面元素信息",
                "params": {
                    "args": {
                        "mode": "find_clickable",
                        "return_metrics": True
                    }
                },
                "save": "clickable_elements"
            },
            {
                "step": 2,
                "action": "click_coordinates",
                "description": "点击目标元素",
                "params": {
                    "bbox": "@clickable_elements[0]['bbox']"
                },
                "guard": {
                    "source_vars_only": True
                }
            },
            {
                "step": 3,
                "action": "wait_for",
                "description": "等待页面响应",
                "params": {
                    "until": {
                        "type": "ext.wait_quiet",
                        "timeout_ms": 5000
                    }
                }
            }
        ]

    def _generate_scroll_plan(self, analysis: Dict) -> List[Dict]:
        """生成滚动计划"""
        return [
            {
                "step": 1,
                "action": "ext.extract",
                "description": "获取容器信息",
                "params": {
                    "args": {
                        "mode": "find_containers",
                        "return_container_bbox": True
                    }
                },
                "save": "container_info"
            },
            {
                "step": 2,
                "action": "wheel_coordinates",
                "description": "执行滚动",
                "params": {
                    "at_bbox": "@container_info['container_bbox']",
                    "amount": -300
                },
                "guard": {
                    "source_vars_only": True
                }
            }
        ]

    def _generate_input_plan(self, analysis: Dict) -> List[Dict]:
        """生成输入计划"""
        return [
            {
                "step": 1,
                "action": "ext.type_text",
                "description": "输入文本",
                "params": {
                    "sel": "input, textarea",
                    "text": "待确定",
                    "replace": True
                }
            }
        ]

    def _generate_wait_plan(self, analysis: Dict) -> List[Dict]:
        """生成等待计划"""
        return [
            {
                "step": 1,
                "action": "wait_for",
                "description": "等待条件满足",
                "params": {
                    "until": {
                        "type": "ext.wait_quiet",
                        "timeout_ms": 10000
                    }
                }
            }
        ]

    def _generate_compound_plan(self, analysis: Dict) -> List[Dict]:
        """生成复合计划"""
        # 通用的复合计划模板
        return [
            {
                "step": 1,
                "action": "ext.extract",
                "description": "分析页面状态",
                "params": {
                    "args": {
                        "mode": "comprehensive",
                        "return_metrics": True
                    }
                },
                "save": "page_analysis"
            },
            {
                "step": 2,
                "action": "branch",
                "description": "基于页面状态决定行动",
                "params": {
                    "if": "@page_analysis != null",
                    "then": "continue_plan",
                    "else": "fallback_plan"
                }
            }
        ]

    def _validate_plan(self, steps: List[Dict]) -> bool:
        """验证计划"""
        if not steps:
            logger.error("Empty plan")
            return False

        if len(steps) > self.max_steps:
            logger.error(f"Plan exceeds maximum steps: {len(steps)} > {self.max_steps}")
            return False

        # 验证每个步骤
        for i, step in enumerate(steps):
            if not self._validate_step(step, i + 1):
                return False

        return True

    def _validate_step(self, step: Dict, step_num: int) -> bool:
        """验证单个步骤"""
        # 检查必需字段
        if "action" not in step:
            logger.error(f"Step {step_num}: missing 'action' field")
            return False

        action = step["action"]

        # 检查动作是否在白名单中
        if action not in self.allowed_actions:
            logger.error(f"Step {step_num}: action '{action}' not allowed")
            return False

        # 检查参数来源（简化实现）
        params = step.get("params", {})
        guard = step.get("guard", {})

        if guard.get("source_vars_only", False):
            # 应该验证参数只来源于变量或上一步结果
            # 这里简化处理
            pass

        return True


# 全局微计划器实例
micro_planner = MicroPlanner()