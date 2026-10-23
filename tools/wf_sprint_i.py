#!/usr/bin/env python3
"""
Sprint I CLI工具
提供DPO训练、版本管理、A/B测试和自动回退的命令行接口
"""

import asyncio
import argparse
import json
import sys
import os
import subprocess
from pathlib import Path
from typing import Dict, Any, List
import logging
import aiohttp
from datetime import datetime, timedelta

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from server.services.auto_rollback import auto_rollback_service

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SprintICLI:
    """Sprint I功能的CLI工具"""

    def __init__(self):
        self.api_endpoints = {
            "teacher": "http://127.0.0.1:8004",
            "deploy": "http://127.0.0.1:8005",
            "recall": "http://127.0.0.1:8003"
        }

    async def prepare_pairs_command(self, args):
        """执行偏好对生成命令"""
        print("🔄 生成DPO训练偏好对")
        print("=" * 50)

        cmd_args = [
            "python", "jobs/dpo/prepare_pairs.py",
            f"--output-dir={args.output_dir}",
            f"--min-margin={args.min_margin}",
            f"--max-pairs={args.max_pairs}"
        ]

        if args.host:
            cmd_args.append(f"--host={args.host}")
        if args.goal:
            cmd_args.append(f"--goal={args.goal}")
        if args.start_date:
            cmd_args.append(f"--start-date={args.start_date}")
        if args.end_date:
            cmd_args.append(f"--end-date={args.end_date}")

        print(f"执行命令: {' '.join(cmd_args)}")
        print()

        try:
            result = subprocess.run(cmd_args, capture_output=True, text=True, cwd=Path(__file__).parent.parent)

            if result.returncode == 0:
                print("✅ 偏好对生成完成")
                if result.stdout:
                    print(result.stdout)

                # 检查输出文件
                output_files = [
                    f"{args.output_dir}/train.jsonl",
                    f"{args.output_dir}/val.jsonl",
                    f"{args.output_dir}/test.jsonl"
                ]

                for file_path in output_files:
                    if os.path.exists(file_path):
                        with open(file_path, 'r') as f:
                            line_count = sum(1 for _ in f)
                        print(f"  📄 {file_path}: {line_count} 条记录")

            else:
                print("❌ 偏好对生成失败")
                if result.stderr:
                    print(result.stderr)

        except Exception as e:
            print(f"❌ 执行错误: {e}")

    async def train_dpo_command(self, args):
        """执行DPO训练命令"""
        print("🧠 启动DPO训练")
        print("=" * 50)

        cmd_args = [
            "python", "trainer/dpo/train.py",
            f"--train-data={args.train_data}",
            f"--output-dir={args.output_dir}",
            f"--epochs={args.epochs}",
            f"--batch-size={args.batch_size}",
            f"--learning-rate={args.learning_rate}",
            f"--beta={args.beta}"
        ]

        if args.eval_data:
            cmd_args.append(f"--eval-data={args.eval_data}")
        if args.model_name:
            cmd_args.append(f"--model-name={args.model_name}")
        if args.use_lora:
            cmd_args.append("--use-lora")
        if args.use_4bit:
            cmd_args.append("--use-4bit")
        if args.report_to != "none":
            cmd_args.append(f"--report-to={args.report_to}")

        print(f"执行命令: {' '.join(cmd_args)}")
        print()

        try:
            # 异步执行训练（可能需要很长时间）
            print("🚀 开始训练（这可能需要较长时间）...")
            result = subprocess.run(cmd_args, cwd=Path(__file__).parent.parent)

            if result.returncode == 0:
                print("✅ DPO训练完成")

                # 检查输出文件
                model_path = f"{args.output_dir}/pytorch_model.bin"
                metrics_path = f"{args.output_dir}/training_metrics.json"

                if os.path.exists(metrics_path):
                    with open(metrics_path, 'r') as f:
                        metrics = json.load(f)
                    print("📊 训练指标:")
                    for key, value in metrics.items():
                        if isinstance(value, float):
                            print(f"  {key}: {value:.4f}")
                        else:
                            print(f"  {key}: {value}")
            else:
                print("❌ DPO训练失败")

        except Exception as e:
            print(f"❌ 训练错误: {e}")

    async def optimize_prompt_command(self, args):
        """执行Prompt优化命令"""
        print("⚡ 启动Prompt优化")
        print("=" * 50)

        cmd_args = [
            "python", "trainer/prompt/tune.py",
            f"--search-method={args.search_method}",
            f"--max-iterations={args.max_iterations}",
            f"--output-dir={args.output_dir}"
        ]

        if args.eval_data:
            cmd_args.append(f"--eval-data={args.eval_data}")
        if args.mock_eval:
            cmd_args.append("--mock-eval")

        print(f"执行命令: {' '.join(cmd_args)}")
        print()

        try:
            result = subprocess.run(cmd_args, capture_output=True, text=True, cwd=Path(__file__).parent.parent)

            if result.returncode == 0:
                print("✅ Prompt优化完成")
                if result.stdout:
                    print(result.stdout)

                # 查找最新的结果文件
                output_dir = Path(args.output_dir)
                if output_dir.exists():
                    best_files = list(output_dir.glob("best_template_*.md"))
                    if best_files:
                        latest_file = max(best_files, key=os.path.getctime)
                        print(f"📄 最佳模板保存在: {latest_file}")
            else:
                print("❌ Prompt优化失败")
                if result.stderr:
                    print(result.stderr)

        except Exception as e:
            print(f"❌ 优化错误: {e}")

    async def teacher_score_command(self, args):
        """执行Teacher评分命令"""
        print("🎓 Teacher评分测试")
        print("=" * 50)

        # 构建测试请求
        test_context = {
            "host": args.host or "ca.indeed.com",
            "goal_hash": "apply_job",
            "page_state_meta": {"left_ratio": 0.33, "right_ratio": 0.67, "dpr": 1.25}
        }

        test_candidates = []
        if args.candidates_file:
            try:
                with open(args.candidates_file, 'r') as f:
                    test_candidates = json.load(f)
            except Exception as e:
                print(f"❌ 读取候选文件失败: {e}")
                return
        else:
            # 使用默认测试候选
            test_candidates = [
                {
                    "plan_id": "plan_1",
                    "steps": [
                        {"do": "wheel_coordinates", "args": {"at_bbox": "@ps.panes.left.rect", "amount": -600}},
                        {"do": "click_coordinates", "args": {"bbox": "@ps.lists[0].itemRects[0]"}},
                        {"do": "wait_for", "args": {"until": {"type": "ext.wait_quiet"}}},
                        {"do": "ext.extract", "args": {"mode": "find_button_bbox", "text_any_of": ["Apply"]}}
                    ]
                },
                {
                    "plan_id": "plan_2",
                    "steps": [
                        {"do": "click_coordinates", "args": {"bbox": "@ps.lists[0].itemRects[1]"}},
                        {"do": "wait_for", "args": {"timeout": 3000}}
                    ]
                }
            ]

        request_data = {
            "context": test_context,
            "candidates": test_candidates
        }

        print(f"评分 {len(test_candidates)} 个候选计划...")
        print()

        try:
            result = await self._call_api("POST", "teacher", "/teacher/score", json=request_data)

            if result:
                print("✅ Teacher评分完成")
                print(f"置信度: {result['confidence_score']:.3f}")
                print()

                scores = result["scores"]
                rationales = result["rationales"]
                ranking = result["preference_ranking"]

                print("📊 评分结果:")
                for i, (score, rationale) in enumerate(zip(scores, rationales)):
                    rank = ranking.index(i) + 1
                    print(f"  候选 {i+1} (排名 #{rank}): {score:.3f}")
                    print(f"    理由: {rationale}")
                    print()

                print(f"🥇 最佳候选: 候选 {ranking[0] + 1}")
                print(f"Teacher信息: {result['teacher_info']['provider']} / {result['teacher_info']['model']}")

            else:
                print("❌ Teacher评分失败")

        except Exception as e:
            print(f"❌ 评分错误: {e}")

    async def deploy_version_command(self, args):
        """执行版本部署命令"""
        print("🚀 部署Planner版本")
        print("=" * 50)

        version_data = {
            "name": args.name,
            "version": args.version,
            "type": args.type,
            "base_provider": args.base_provider,
            "base_model": args.base_model,
            "notes": args.notes
        }

        if args.model_path:
            version_data["model_path"] = args.model_path
        if args.prompt_template:
            version_data["prompt_template"] = args.prompt_template

        print(f"部署配置: {json.dumps(version_data, indent=2)}")
        print()

        try:
            result = await self._call_api("POST", "deploy", "/deploy/planner", json=version_data)

            if result:
                print("✅ 版本部署成功")
                print(f"版本ID: {result['id']}")
                print(f"版本名称: {result['name']}")
                print(f"状态: {result['status']}")
                print(f"创建时间: {result['created_at']}")
            else:
                print("❌ 版本部署失败")

        except Exception as e:
            print(f"❌ 部署错误: {e}")

    async def create_ab_test_command(self, args):
        """创建A/B测试"""
        print("🧪 创建A/B测试")
        print("=" * 50)

        assignment_data = {
            "host": args.host,
            "strategy": args.strategy,
            "planner_version_id": args.version_id,
            "traffic_pct": args.traffic_pct,
            "failure_threshold": args.failure_threshold,
            "cost_threshold": args.cost_threshold
        }

        print(f"A/B测试配置: {json.dumps(assignment_data, indent=2)}")
        print()

        try:
            result = await self._call_api("POST", "deploy", "/deploy/ab", json=assignment_data)

            if result:
                print("✅ A/B测试创建成功")
                print(f"分配ID: {result['id']}")
                print(f"主机: {result['host']}")
                print(f"策略: {result['strategy']}")
                print(f"流量分配: {result['traffic_pct']}%")
                print(f"版本ID: {result['planner_version_id']}")
            else:
                print("❌ A/B测试创建失败")

        except Exception as e:
            print(f"❌ 创建错误: {e}")

    async def status_command(self, args):
        """显示系统状态"""
        print("📊 Sprint I 系统状态")
        print("=" * 50)

        try:
            # 检查各个服务
            print("🌐 服务状态:")

            # Teacher服务
            try:
                teacher_stats = await self._call_api("GET", "teacher", "/teacher/stats")
                if teacher_stats:
                    print(f"  ✅ Teacher服务: 运行中")
                    print(f"     缓存大小: {teacher_stats.get('cache_size', 0)}")
                    print(f"     支持的提供商: {teacher_stats.get('supported_providers', [])}")
                else:
                    print("  ❌ Teacher服务: 不可用")
            except Exception:
                print("  ❌ Teacher服务: 连接失败")

            # 部署服务
            try:
                versions = await self._call_api("GET", "deploy", "/deploy/versions")
                if versions:
                    print(f"  ✅ 部署服务: 运行中")
                    print(f"     版本数量: {len(versions)}")

                    prod_versions = [v for v in versions if v.get("status") == "prod"]
                    print(f"     生产版本: {len(prod_versions)}")
                else:
                    print("  ❌ 部署服务: 不可用")
            except Exception:
                print("  ❌ 部署服务: 连接失败")

            # A/B测试状态
            try:
                assignments = await self._call_api("GET", "deploy", "/deploy/ab/active")
                if assignments is not None:
                    print(f"  ✅ A/B测试: {len(assignments)} 个活跃分配")
                    for assignment in assignments[:3]:  # 显示前3个
                        print(f"     {assignment['host']}: {assignment['traffic_pct']}% -> 版本{assignment['planner_version_id']}")
                else:
                    print("  ❌ A/B测试: 查询失败")
            except Exception:
                print("  ❌ A/B测试: 连接失败")

            # 自动回退状态
            print("\n🔄 自动回退监控:")
            rollback_status = auto_rollback_service.get_monitoring_status()
            if rollback_status["is_running"]:
                print("  ✅ 监控状态: 运行中")
                print(f"     监控部署数: {rollback_status['monitored_deployments']}")
                print(f"     24小时回退次数: {rollback_status['rollback_count_24h']}")
            else:
                print("  ⏸️ 监控状态: 未运行")

            # 部署健康状态
            health_data = auto_rollback_service.get_deployment_health()
            if health_data:
                print("\n💚 部署健康状态:")
                for key, health in health_data.items():
                    status_icon = "✅" if health["health_status"] == "healthy" else "⚠️" if health["health_status"] == "warning" else "❌"
                    print(f"  {status_icon} {health['version_name']}: {health['health_status']}")
                    print(f"     成功率: {health['success_rate']:.1%}, 延迟: {health['avg_latency_ms']}ms")

        except Exception as e:
            print(f"❌ 状态检查失败: {e}")

    async def rollback_command(self, args):
        """执行回退命令"""
        print("⏪ 执行版本回退")
        print("=" * 50)

        if args.version_id:
            print(f"手动回退版本 {args.version_id}...")

            try:
                success = await auto_rollback_service.manual_rollback(args.version_id, "manual_cli")

                if success:
                    print("✅ 手动回退成功")
                else:
                    print("❌ 手动回退失败")

            except Exception as e:
                print(f"❌ 回退错误: {e}")

        # 显示回退历史
        print("\n📜 回退历史:")
        history = auto_rollback_service.get_rollback_history(args.limit)

        if history:
            for entry in history:
                timestamp = entry["timestamp"][:19]  # 移除微秒
                print(f"  {timestamp}: {entry['version_name']} -> {entry['reason']}")
                print(f"    成功率: {entry['metrics_before']['success_rate']:.1%}, " +
                      f"完成: {'✅' if entry['rollback_completed'] else '❌'}")
        else:
            print("  无回退记录")

    async def _call_api(self, method: str, service: str, endpoint: str, **kwargs):
        """调用API"""
        if service not in self.api_endpoints:
            raise ValueError(f"Unknown service: {service}")

        url = f"{self.api_endpoints[service]}{endpoint}"

        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(method, url, **kwargs) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    logger.error(f"API错误 {response.status}: {error_text}")
                    return None

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Sprint I CLI工具")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # prepare-pairs命令
    pairs_parser = subparsers.add_parser("prepare-pairs", help="生成DPO训练偏好对")
    pairs_parser.add_argument("--host", help="目标域名过滤")
    pairs_parser.add_argument("--goal", help="目标任务过滤")
    pairs_parser.add_argument("--start-date", help="开始日期")
    pairs_parser.add_argument("--end-date", help="结束日期")
    pairs_parser.add_argument("--output-dir", default="data/prefs", help="输出目录")
    pairs_parser.add_argument("--min-margin", type=float, default=0.8, help="最小奖励差值")
    pairs_parser.add_argument("--max-pairs", type=int, default=10, help="每指纹最大偏好对数")

    # train-dpo命令
    train_parser = subparsers.add_parser("train-dpo", help="执行DPO训练")
    train_parser.add_argument("--train-data", required=True, help="训练数据路径")
    train_parser.add_argument("--eval-data", help="验证数据路径")
    train_parser.add_argument("--model-name", default="microsoft/DialoGPT-small", help="基础模型")
    train_parser.add_argument("--output-dir", default="models/dpo_planner", help="输出目录")
    train_parser.add_argument("--epochs", type=int, default=1, help="训练轮数")
    train_parser.add_argument("--batch-size", type=int, default=2, help="批大小")
    train_parser.add_argument("--learning-rate", type=float, default=5e-5, help="学习率")
    train_parser.add_argument("--beta", type=float, default=0.1, help="DPO beta参数")
    train_parser.add_argument("--use-lora", action="store_true", help="使用LoRA")
    train_parser.add_argument("--use-4bit", action="store_true", help="使用4bit量化")
    train_parser.add_argument("--report-to", default="none", choices=["wandb", "tensorboard", "none"], help="实验跟踪")

    # optimize-prompt命令
    prompt_parser = subparsers.add_parser("optimize-prompt", help="优化Prompt模板")
    prompt_parser.add_argument("--eval-data", help="评估数据路径")
    prompt_parser.add_argument("--search-method", choices=["grid", "random", "bayesian"], default="grid", help="搜索方法")
    prompt_parser.add_argument("--max-iterations", type=int, default=20, help="最大迭代次数")
    prompt_parser.add_argument("--output-dir", default="trainer/prompt/results", help="输出目录")
    prompt_parser.add_argument("--mock-eval", action="store_true", help="使用模拟评估")

    # teacher-score命令
    teacher_parser = subparsers.add_parser("teacher-score", help="Teacher评分测试")
    teacher_parser.add_argument("--host", help="目标域名")
    teacher_parser.add_argument("--candidates-file", help="候选计划JSON文件")

    # deploy-version命令
    deploy_parser = subparsers.add_parser("deploy-version", help="部署Planner版本")
    deploy_parser.add_argument("--name", required=True, help="版本名称")
    deploy_parser.add_argument("--version", required=True, help="版本号")
    deploy_parser.add_argument("--type", required=True, choices=["prompt", "lora", "fine_tuned"], help="版本类型")
    deploy_parser.add_argument("--base-provider", required=True, help="基础提供商")
    deploy_parser.add_argument("--base-model", required=True, help="基础模型")
    deploy_parser.add_argument("--model-path", help="模型路径")
    deploy_parser.add_argument("--prompt-template", help="Prompt模板")
    deploy_parser.add_argument("--notes", help="说明")

    # create-ab命令
    ab_parser = subparsers.add_parser("create-ab", help="创建A/B测试")
    ab_parser.add_argument("--host", required=True, help="目标域名")
    ab_parser.add_argument("--strategy", required=True, help="策略名称")
    ab_parser.add_argument("--version-id", type=int, required=True, help="Planner版本ID")
    ab_parser.add_argument("--traffic-pct", type=int, default=20, help="流量百分比")
    ab_parser.add_argument("--failure-threshold", type=float, default=0.1, help="失败率阈值")
    ab_parser.add_argument("--cost-threshold", type=float, default=1.3, help="成本阈值倍数")

    # rollback命令
    rollback_parser = subparsers.add_parser("rollback", help="版本回退")
    rollback_parser.add_argument("--version-id", type=int, help="要回退的版本ID")
    rollback_parser.add_argument("--limit", type=int, default=10, help="显示历史记录数量")

    # status命令
    subparsers.add_parser("status", help="显示系统状态")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    cli = SprintICLI()

    # 执行命令
    if args.command == "prepare-pairs":
        asyncio.run(cli.prepare_pairs_command(args))
    elif args.command == "train-dpo":
        asyncio.run(cli.train_dpo_command(args))
    elif args.command == "optimize-prompt":
        asyncio.run(cli.optimize_prompt_command(args))
    elif args.command == "teacher-score":
        asyncio.run(cli.teacher_score_command(args))
    elif args.command == "deploy-version":
        asyncio.run(cli.deploy_version_command(args))
    elif args.command == "create-ab":
        asyncio.run(cli.create_ab_test_command(args))
    elif args.command == "rollback":
        asyncio.run(cli.rollback_command(args))
    elif args.command == "status":
        asyncio.run(cli.status_command(args))

if __name__ == "__main__":
    main()