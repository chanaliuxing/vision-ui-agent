"""
LLM计划服务 - 提供llm.plan API
按照upgrade.md Sprint C规范实现
"""
import logging
import json
from typing import Dict, List, Optional
from core.planner.micro_planner import micro_planner

logger = logging.getLogger(__name__)


class LLMPlanService:
    def __init__(self):
        self.supported_providers = ["gemini", "openai", "deepseek", "nvidia"]
        self.default_provider = "gemini"

    def generate_plan(self, job: str, inputs: Dict, provider_hint: str = None) -> Dict:
        """
        生成LLM计划

        Args:
            job: 任务类型
            inputs: 输入参数
            provider_hint: 提供商提示

        Returns:
            Dict: 计划结果
        """
        try:
            # 提取参数
            goal = inputs.get("goal", "")
            context = inputs.get("context", {})
            page_state = inputs.get("page_state", {})

            if not goal:
                return {
                    "ok": False,
                    "error": "Missing required parameter: goal"
                }

            # 选择计划器
            if job == "micro_plan" or job == "micro_plan_v1":
                return self._generate_micro_plan(goal, context, page_state)
            else:
                return {
                    "ok": False,
                    "error": f"Unsupported job type: {job}"
                }

        except Exception as e:
            logger.error(f"Plan generation failed: {str(e)}")
            return {
                "ok": False,
                "error": str(e)
            }

    def _generate_micro_plan(self, goal: str, context: Dict, page_state: Dict) -> Dict:
        """生成微计划"""
        try:
            # 在实际实现中，这里会调用LLM API
            # 当前使用简化的规则引擎

            # 先用微计划器生成基础计划
            base_plan = micro_planner.generate_plan(goal, context, page_state)

            if not base_plan.get("ok"):
                return base_plan

            # 模拟LLM增强（实际应该调用真实LLM API）
            enhanced_plan = self._enhance_plan_with_llm(base_plan, goal, context)

            return enhanced_plan

        except Exception as e:
            logger.error(f"Micro plan generation failed: {str(e)}")
            return {
                "ok": False,
                "error": str(e)
            }

    def _enhance_plan_with_llm(self, base_plan: Dict, goal: str, context: Dict) -> Dict:
        """使用LLM增强计划（模拟实现）"""
        steps = base_plan.get("steps", [])

        # 模拟LLM增强：添加更详细的描述和参数
        for step in steps:
            action = step.get("action")

            # 根据动作类型优化参数
            if action == "click_coordinates":
                # 添加人类化配置
                if "params" not in step:
                    step["params"] = {}
                step["params"]["humanize"] = True
                step["description"] = f"智能点击目标元素 - {goal}"

            elif action == "ext.extract":
                # 优化提取参数
                if "params" not in step:
                    step["params"] = {}
                args = step["params"].get("args", {})
                args["intelligent_selection"] = True
                step["params"]["args"] = args
                step["description"] = f"智能提取页面元素用于 {goal}"

            elif action == "wait_for":
                # 优化等待时间
                if "params" not in step:
                    step["params"] = {}
                until = step["params"].get("until", {})
                if "timeout_ms" not in until:
                    until["timeout_ms"] = 8000  # 更合理的默认超时
                step["params"]["until"] = until

        # 更新元数据
        enhanced_metadata = base_plan.get("metadata", {})
        enhanced_metadata["enhanced_by_llm"] = True
        enhanced_metadata["llm_provider"] = "mock_gemini"  # 模拟
        enhanced_metadata["enhancement_version"] = "v1.0"

        return {
            "ok": True,
            "steps": steps,
            "metadata": enhanced_metadata,
            "plan_type": "micro_plan_v1",
            "enhanced": True
        }


class MockLLMClient:
    """模拟LLM客户端（用于测试）"""

    def __init__(self, provider: str = "gemini"):
        self.provider = provider

    def generate_plan_prompt(self, goal: str, page_state: Dict) -> str:
        """生成计划提示词"""
        prompt = f"""
请为以下目标生成一个简短的执行计划（最多5步）：

目标：{goal}

可用动作：
- click_coordinates: 点击指定坐标
- wheel_coordinates: 在容器中滚动
- ext.extract: 提取页面元素
- ext.type_text: 输入文本
- wait_for: 等待条件

页面状态：{json.dumps(page_state, ensure_ascii=False, indent=2)}

请返回JSON格式的计划，包含steps数组。
"""
        return prompt

    def call_llm(self, prompt: str) -> Dict:
        """调用LLM（模拟）"""
        # 模拟LLM响应
        mock_response = {
            "steps": [
                {
                    "step": 1,
                    "action": "ext.extract",
                    "description": "分析当前页面",
                    "params": {
                        "args": {"mode": "intelligent"}
                    }
                },
                {
                    "step": 2,
                    "action": "click_coordinates",
                    "description": "点击目标元素",
                    "params": {
                        "bbox": "@elements[0]['bbox']"
                    }
                }
            ]
        }

        return {
            "ok": True,
            "response": mock_response
        }


# 全局服务实例
llm_plan_service = LLMPlanService()