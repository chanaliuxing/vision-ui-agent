#!/usr/bin/env python3
"""
Sprint I: Prompt优化工具
使用网格搜索/贝叶斯优化自动优化Planner Prompt模板
"""

import asyncio
import argparse
import json
import logging
import os
import random
import time
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime
import itertools
import hashlib

# 可选依赖
try:
    from skopt import gp_minimize
    from skopt.space import Real, Integer, Categorical
    from skopt.utils import use_named_args
    HAS_SKOPT = True
except ImportError:
    HAS_SKOPT = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class PromptOptimizationConfig:
    """Prompt优化配置"""
    # 搜索空间
    few_shot_count: List[int] = field(default_factory=lambda: [2, 3, 4, 5])
    instruction_weights: List[float] = field(default_factory=lambda: [0.3, 0.5, 0.7])
    constraint_emphasis: List[str] = field(default_factory=lambda: ["low", "medium", "high"])
    context_detail: List[str] = field(default_factory=lambda: ["minimal", "standard", "detailed"])

    # 评估配置
    eval_dataset_path: str = "data/prefs/test.jsonl"
    mock_eval: bool = True  # 是否使用模拟评估
    eval_batch_size: int = 10
    max_eval_samples: int = 50

    # 搜索配置
    search_method: str = "grid"  # "grid" | "bayesian" | "random"
    max_iterations: int = 20
    n_random_starts: int = 5

    # 输出配置
    output_dir: str = "trainer/prompt/results"
    save_all_variants: bool = True

class PromptTemplate:
    """Prompt模板类"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.few_shot_count = config.get("few_shot_count", 3)
        self.instruction_weight = config.get("instruction_weight", 0.5)
        self.constraint_emphasis = config.get("constraint_emphasis", "medium")
        self.context_detail = config.get("context_detail", "standard")

    def generate_system_prompt(self) -> str:
        """生成系统提示"""
        base_instruction = """You are an expert UI automation planner. Generate efficient and reliable action sequences for web automation tasks."""

        if self.constraint_emphasis == "high":
            constraint_text = """CRITICAL CONSTRAINTS:
- MUST stay within the target domain
- MUST use only coordinate-based actions
- MUST include proper wait conditions
- MUST validate each step"""
        elif self.constraint_emphasis == "medium":
            constraint_text = """Important constraints:
- Stay within target domain
- Use coordinate-based actions
- Include wait conditions when needed"""
        else:
            constraint_text = "Follow basic automation safety guidelines."

        weight_text = f"Prioritize reliability and efficiency (weight: {self.instruction_weight})."

        return f"{base_instruction}\n\n{constraint_text}\n\n{weight_text}"

    def generate_few_shot_examples(self) -> List[Dict[str, str]]:
        """生成few-shot示例"""
        all_examples = [
            {
                "context": "Host: ca.indeed.com, Goal: apply_job, Layout: left_list + right_detail",
                "plan": '''{"steps": [
                    {"do": "wheel_coordinates", "args": {"at_bbox": "@ps.panes.left.rect", "amount": -600}},
                    {"do": "click_coordinates", "args": {"bbox": "@ps.lists[0].itemRects[0]"}},
                    {"do": "wait_for", "args": {"until": {"type": "ext.wait_quiet", "timeout_ms": 3000}}},
                    {"do": "ext.extract", "args": {"mode": "find_button_bbox", "text_any_of": ["Apply", "Quick Apply"]}}
                ]}'''
            },
            {
                "context": "Host: www.xiaohongshu.com, Goal: expand_comments, Layout: single_column",
                "plan": '''{"steps": [
                    {"do": "scroll_coordinates", "args": {"at_bbox": "@ps.main.rect", "amount": 500}},
                    {"do": "click_coordinates", "args": {"bbox": "@ps.buttons.expand_comments"}},
                    {"do": "wait_for", "args": {"until": {"type": "content_loaded", "timeout_ms": 2000}}}
                ]}'''
            },
            {
                "context": "Host: linkedin.com, Goal: send_message, Layout: profile_page",
                "plan": '''{"steps": [
                    {"do": "click_coordinates", "args": {"bbox": "@ps.buttons.message"}},
                    {"do": "wait_for", "args": {"until": {"type": "modal_open", "timeout_ms": 1500}}},
                    {"do": "type_text", "args": {"text": "Hello! I'd like to connect.", "target": "@ps.inputs.message_box"}}
                ]}'''
            },
            {
                "context": "Host: github.com, Goal: create_issue, Layout: repository_page",
                "plan": '''{"steps": [
                    {"do": "click_coordinates", "args": {"bbox": "@ps.tabs.issues"}},
                    {"do": "wait_for", "args": {"until": {"type": "page_load", "timeout_ms": 2000}}},
                    {"do": "click_coordinates", "args": {"bbox": "@ps.buttons.new_issue"}}
                ]}'''
            },
            {
                "context": "Host: amazon.com, Goal: add_to_cart, Layout: product_page",
                "plan": '''{"steps": [
                    {"do": "click_coordinates", "args": {"bbox": "@ps.buttons.add_to_cart"}},
                    {"do": "wait_for", "args": {"until": {"type": "cart_updated", "timeout_ms": 1000}}}
                ]}'''
            }
        ]

        # 根据配置选择示例数量
        selected = all_examples[:self.few_shot_count]

        return selected

    def generate_context_template(self, context: Dict[str, Any]) -> str:
        """生成上下文模板"""
        host = context.get("host", "unknown")
        goal = context.get("goal_hash", "unknown")
        page_meta = context.get("page_state_meta", {})

        if self.context_detail == "detailed":
            template = f"""Context Analysis:
- Target Domain: {host}
- Primary Objective: {goal}
- Page Layout: left_ratio={page_meta.get('left_ratio', 0.5)}, right_ratio={page_meta.get('right_ratio', 0.5)}
- Device Pixel Ratio: {page_meta.get('dpr', 1.0)}
- Available Constraints: {context.get('constraints', {})}
- Reference Patterns: {len(context.get('references', []))} similar cases found"""

        elif self.context_detail == "standard":
            template = f"""Target: {host}
Goal: {goal}
Layout: {page_meta.get('left_ratio', 0.5):.1f}/{page_meta.get('right_ratio', 0.5):.1f} split
References: {len(context.get('references', []))} patterns"""

        else:  # minimal
            template = f"{host} | {goal}"

        return template

    def build_full_prompt(self, context: Dict[str, Any]) -> str:
        """构建完整的提示"""
        system_prompt = self.generate_system_prompt()
        few_shot_examples = self.generate_few_shot_examples()
        context_template = self.generate_context_template(context)

        prompt_parts = [system_prompt, ""]

        # 添加few-shot示例
        prompt_parts.append("Examples:")
        for i, example in enumerate(few_shot_examples, 1):
            prompt_parts.append(f"Example {i}:")
            prompt_parts.append(f"Context: {example['context']}")
            prompt_parts.append(f"Plan: {example['plan']}")
            prompt_parts.append("")

        # 添加当前任务
        prompt_parts.append("Current Task:")
        prompt_parts.append(context_template)
        prompt_parts.append("")
        prompt_parts.append("Generate a JSON plan with 'steps' array:")

        return "\n".join(prompt_parts)

    def get_config_signature(self) -> str:
        """获取配置签名"""
        config_str = json.dumps(self.config, sort_keys=True)
        return hashlib.sha256(config_str.encode()).hexdigest()[:8]

class PromptEvaluator:
    """Prompt评估器"""

    def __init__(self, config: PromptOptimizationConfig):
        self.config = config
        self.eval_cache = {}

    async def evaluate_prompt_template(self, template: PromptTemplate) -> Dict[str, float]:
        """评估Prompt模板"""
        # 检查缓存
        signature = template.get_config_signature()
        if signature in self.eval_cache:
            logger.info(f"Cache hit for template {signature}")
            return self.eval_cache[signature]

        if self.config.mock_eval:
            metrics = await self._mock_evaluate(template)
        else:
            metrics = await self._real_evaluate(template)

        # 缓存结果
        self.eval_cache[signature] = metrics

        return metrics

    async def _mock_evaluate(self, template: PromptTemplate) -> Dict[str, float]:
        """模拟评估"""
        await asyncio.sleep(0.1)  # 模拟评估时间

        # 基于配置生成模拟指标
        config = template.config

        # 基础分数
        base_success_rate = 0.75
        base_avg_steps = 4.5
        base_token_count = 120

        # 根据few-shot数量调整
        fs_factor = (config["few_shot_count"] - 3) * 0.02  # 3为最优点
        success_rate = base_success_rate + fs_factor + random.uniform(-0.05, 0.05)

        # 根据指令权重调整
        weight_factor = abs(config["instruction_weight"] - 0.5) * 0.1
        success_rate -= weight_factor

        # 根据约束强调调整
        if config["constraint_emphasis"] == "high":
            success_rate += 0.03
            avg_steps = base_avg_steps - 0.2
        elif config["constraint_emphasis"] == "low":
            success_rate -= 0.02
            avg_steps = base_avg_steps + 0.3
        else:
            avg_steps = base_avg_steps

        # 根据上下文详细程度调整
        if config["context_detail"] == "detailed":
            token_count = base_token_count + 30
            success_rate += 0.01
        elif config["context_detail"] == "minimal":
            token_count = base_token_count - 20
            success_rate -= 0.015
        else:
            token_count = base_token_count

        # 添加随机噪声
        success_rate = max(0.5, min(0.95, success_rate + random.uniform(-0.03, 0.03)))
        avg_steps = max(3.0, avg_steps + random.uniform(-0.3, 0.3))
        token_count = max(80, token_count + random.randint(-15, 15))

        return {
            "success_rate": success_rate,
            "avg_steps": avg_steps,
            "avg_tokens": token_count,
            "cost_per_success": token_count / max(success_rate, 0.1) * 0.0001,
            "efficiency_score": success_rate / (avg_steps * 0.2 + token_count * 0.0001)
        }

    async def _real_evaluate(self, template: PromptTemplate) -> Dict[str, float]:
        """真实评估（调用实际LLM）"""
        # 加载评估数据集
        test_cases = self.load_eval_dataset()

        success_count = 0
        total_steps = 0
        total_tokens = 0

        for i, test_case in enumerate(test_cases[:self.config.max_eval_samples]):
            try:
                # 生成提示
                prompt = template.build_full_prompt(test_case["context"])

                # 调用LLM（这里需要实际实现）
                plan_result = await self._call_llm_for_plan(prompt)

                # 评估结果
                is_success = self._evaluate_plan_quality(plan_result, test_case)
                if is_success:
                    success_count += 1

                total_steps += len(plan_result.get("steps", []))
                total_tokens += len(prompt.split())

            except Exception as e:
                logger.warning(f"Evaluation failed for test case {i}: {e}")

        if len(test_cases) == 0:
            return {"success_rate": 0, "avg_steps": 0, "avg_tokens": 0, "cost_per_success": 999, "efficiency_score": 0}

        success_rate = success_count / len(test_cases)
        avg_steps = total_steps / len(test_cases)
        avg_tokens = total_tokens / len(test_cases)

        return {
            "success_rate": success_rate,
            "avg_steps": avg_steps,
            "avg_tokens": avg_tokens,
            "cost_per_success": avg_tokens / max(success_rate, 0.01) * 0.0001,
            "efficiency_score": success_rate / (avg_steps * 0.2 + avg_tokens * 0.0001)
        }

    def load_eval_dataset(self) -> List[Dict]:
        """加载评估数据集"""
        if not os.path.exists(self.config.eval_dataset_path):
            logger.warning(f"Eval dataset not found: {self.config.eval_dataset_path}")
            return []

        test_cases = []
        try:
            with open(self.config.eval_dataset_path, 'r') as f:
                for line in f:
                    test_cases.append(json.loads(line.strip()))
        except Exception as e:
            logger.error(f"Failed to load eval dataset: {e}")

        return test_cases

    async def _call_llm_for_plan(self, prompt: str) -> Dict[str, Any]:
        """调用LLM生成计划"""
        # 这里应该调用实际的LLM API
        # 模拟返回
        await asyncio.sleep(0.2)

        return {
            "steps": [
                {"do": "click_coordinates", "args": {"bbox": "@ps.target"}},
                {"do": "wait_for", "args": {"timeout": 2000}}
            ]
        }

    def _evaluate_plan_quality(self, plan: Dict, test_case: Dict) -> bool:
        """评估计划质量"""
        # 简化的质量评估
        steps = plan.get("steps", [])

        if len(steps) == 0:
            return False

        # 检查是否包含基本的动作类型
        has_action = any("click" in step.get("do", "") or "scroll" in step.get("do", "") for step in steps)
        has_wait = any("wait" in step.get("do", "") for step in steps)

        return has_action and (has_wait or len(steps) <= 2)

class PromptOptimizer:
    """Prompt优化器"""

    def __init__(self, config: PromptOptimizationConfig):
        self.config = config
        self.evaluator = PromptEvaluator(config)
        self.optimization_history = []

    def generate_search_space(self) -> List[Dict[str, Any]]:
        """生成搜索空间"""
        if self.config.search_method == "grid":
            return self._generate_grid_search_space()
        elif self.config.search_method == "random":
            return self._generate_random_search_space()
        else:
            raise ValueError(f"Unsupported search method: {self.config.search_method}")

    def _generate_grid_search_space(self) -> List[Dict[str, Any]]:
        """生成网格搜索空间"""
        combinations = itertools.product(
            self.config.few_shot_count,
            self.config.instruction_weights,
            self.config.constraint_emphasis,
            self.config.context_detail
        )

        search_space = []
        for fs_count, inst_weight, const_emph, ctx_detail in combinations:
            search_space.append({
                "few_shot_count": fs_count,
                "instruction_weight": inst_weight,
                "constraint_emphasis": const_emph,
                "context_detail": ctx_detail
            })

        # 限制搜索空间大小
        if len(search_space) > self.config.max_iterations:
            random.shuffle(search_space)
            search_space = search_space[:self.config.max_iterations]

        return search_space

    def _generate_random_search_space(self) -> List[Dict[str, Any]]:
        """生成随机搜索空间"""
        search_space = []

        for _ in range(self.config.max_iterations):
            config = {
                "few_shot_count": random.choice(self.config.few_shot_count),
                "instruction_weight": random.choice(self.config.instruction_weights),
                "constraint_emphasis": random.choice(self.config.constraint_emphasis),
                "context_detail": random.choice(self.config.context_detail)
            }
            search_space.append(config)

        return search_space

    async def optimize(self) -> Tuple[Dict[str, Any], Dict[str, float]]:
        """执行优化"""
        logger.info(f"Starting prompt optimization with {self.config.search_method} search")

        if self.config.search_method == "bayesian" and HAS_SKOPT:
            return await self._bayesian_optimize()
        else:
            return await self._grid_or_random_optimize()

    async def _grid_or_random_optimize(self) -> Tuple[Dict[str, Any], Dict[str, float]]:
        """网格或随机搜索优化"""
        search_space = self.generate_search_space()
        logger.info(f"Evaluating {len(search_space)} configurations")

        best_config = None
        best_metrics = None
        best_score = -float('inf')

        for i, config in enumerate(search_space):
            logger.info(f"Evaluating configuration {i+1}/{len(search_space)}: {config}")

            template = PromptTemplate(config)
            metrics = await self.evaluator.evaluate_prompt_template(template)

            # 计算综合分数
            score = self._calculate_composite_score(metrics)

            # 记录历史
            self.optimization_history.append({
                "iteration": i + 1,
                "config": config,
                "metrics": metrics,
                "score": score
            })

            # 更新最佳配置
            if score > best_score:
                best_score = score
                best_config = config
                best_metrics = metrics

            logger.info(f"Score: {score:.4f}, Success Rate: {metrics['success_rate']:.3f}, "
                       f"Avg Steps: {metrics['avg_steps']:.1f}, Tokens: {metrics['avg_tokens']:.0f}")

        logger.info(f"Optimization completed. Best score: {best_score:.4f}")

        return best_config, best_metrics

    async def _bayesian_optimize(self) -> Tuple[Dict[str, Any], Dict[str, float]]:
        """贝叶斯优化（需要scikit-optimize）"""
        if not HAS_SKOPT:
            logger.warning("scikit-optimize not available, falling back to grid search")
            return await self._grid_or_random_optimize()

        # 定义搜索空间
        dimensions = [
            Categorical(self.config.few_shot_count, name='few_shot_count'),
            Real(min(self.config.instruction_weights), max(self.config.instruction_weights), name='instruction_weight'),
            Categorical(self.config.constraint_emphasis, name='constraint_emphasis'),
            Categorical(self.config.context_detail, name='context_detail')
        ]

        best_config = None
        best_metrics = None

        @use_named_args(dimensions)
        async def objective(**params):
            nonlocal best_config, best_metrics

            config = {
                "few_shot_count": params["few_shot_count"],
                "instruction_weight": params["instruction_weight"],
                "constraint_emphasis": params["constraint_emphasis"],
                "context_detail": params["context_detail"]
            }

            template = PromptTemplate(config)
            metrics = await self.evaluator.evaluate_prompt_template(template)
            score = self._calculate_composite_score(metrics)

            # 记录历史
            self.optimization_history.append({
                "iteration": len(self.optimization_history) + 1,
                "config": config,
                "metrics": metrics,
                "score": score
            })

            # 更新最佳配置
            if best_config is None or score > self._calculate_composite_score(best_metrics):
                best_config = config
                best_metrics = metrics

            logger.info(f"Bayesian iteration {len(self.optimization_history)}: score={score:.4f}")

            return -score  # 负号因为gp_minimize是最小化

        # 执行贝叶斯优化
        result = gp_minimize(
            objective,
            dimensions,
            n_calls=self.config.max_iterations,
            n_random_starts=self.config.n_random_starts
        )

        return best_config, best_metrics

    def _calculate_composite_score(self, metrics: Dict[str, float]) -> float:
        """计算综合分数"""
        # 加权组合多个指标
        success_weight = 0.4
        efficiency_weight = 0.3
        cost_weight = 0.3

        success_score = metrics.get("success_rate", 0)
        efficiency_score = min(1.0, metrics.get("efficiency_score", 0))
        cost_score = max(0, 1.0 - metrics.get("cost_per_success", 1.0) * 1000)  # 标准化成本

        composite = (success_weight * success_score +
                    efficiency_weight * efficiency_score +
                    cost_weight * cost_score)

        return composite

    def save_results(self, best_config: Dict[str, Any], best_metrics: Dict[str, float]):
        """保存优化结果"""
        os.makedirs(self.config.output_dir, exist_ok=True)

        # 保存最佳配置
        best_template = PromptTemplate(best_config)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 生成最佳模板
        sample_context = {
            "host": "ca.indeed.com",
            "goal_hash": "apply_job",
            "page_state_meta": {"left_ratio": 0.33, "right_ratio": 0.67, "dpr": 1.25},
            "constraints": {"max_steps": 5, "must_stay_in_host": True},
            "references": []
        }

        best_prompt = best_template.build_full_prompt(sample_context)

        # 保存最佳模板
        with open(f"{self.config.output_dir}/best_template_{timestamp}.md", 'w') as f:
            f.write(f"# Best Prompt Template\n\n")
            f.write(f"## Configuration\n```json\n{json.dumps(best_config, indent=2)}\n```\n\n")
            f.write(f"## Metrics\n```json\n{json.dumps(best_metrics, indent=2)}\n```\n\n")
            f.write(f"## Template\n```\n{best_prompt}\n```\n")

        # 保存优化历史
        with open(f"{self.config.output_dir}/optimization_history_{timestamp}.json", 'w') as f:
            json.dump(self.optimization_history, f, indent=2, default=str)

        # 保存所有变体（如果启用）
        if self.config.save_all_variants:
            variants_dir = f"{self.config.output_dir}/variants_{timestamp}"
            os.makedirs(variants_dir, exist_ok=True)

            for i, entry in enumerate(self.optimization_history):
                template = PromptTemplate(entry["config"])
                prompt = template.build_full_prompt(sample_context)

                with open(f"{variants_dir}/variant_{i+1:03d}.md", 'w') as f:
                    f.write(f"# Variant {i+1}\n\n")
                    f.write(f"Score: {entry['score']:.4f}\n\n")
                    f.write(f"## Configuration\n```json\n{json.dumps(entry['config'], indent=2)}\n```\n\n")
                    f.write(f"## Metrics\n```json\n{json.dumps(entry['metrics'], indent=2)}\n```\n\n")
                    f.write(f"## Template\n```\n{prompt}\n```\n")

        logger.info(f"Results saved to {self.config.output_dir}")

async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Prompt优化工具")
    parser.add_argument("--eval-data", help="评估数据集路径")
    parser.add_argument("--search-method", choices=["grid", "random", "bayesian"], default="grid", help="搜索方法")
    parser.add_argument("--max-iterations", type=int, default=20, help="最大迭代次数")
    parser.add_argument("--output-dir", default="trainer/prompt/results", help="输出目录")
    parser.add_argument("--mock-eval", action="store_true", help="使用模拟评估")

    args = parser.parse_args()

    # 创建配置
    config = PromptOptimizationConfig(
        eval_dataset_path=args.eval_data or "data/prefs/test.jsonl",
        search_method=args.search_method,
        max_iterations=args.max_iterations,
        output_dir=args.output_dir,
        mock_eval=args.mock_eval
    )

    # 创建优化器
    optimizer = PromptOptimizer(config)

    # 执行优化
    start_time = time.time()
    best_config, best_metrics = await optimizer.optimize()
    duration = time.time() - start_time

    # 保存结果
    optimizer.save_results(best_config, best_metrics)

    # 打印总结
    print("\n" + "="*60)
    print("PROMPT OPTIMIZATION COMPLETED")
    print("="*60)
    print(f"Duration: {duration:.1f} seconds")
    print(f"Iterations: {len(optimizer.optimization_history)}")
    print(f"Search Method: {config.search_method}")
    print()
    print("Best Configuration:")
    print(json.dumps(best_config, indent=2))
    print()
    print("Best Metrics:")
    print(json.dumps(best_metrics, indent=2))
    print(f"\nResults saved to: {config.output_dir}")

if __name__ == "__main__":
    asyncio.run(main())