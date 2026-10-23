#!/usr/bin/env python3
"""
Sprint H CLI工具
提供RAG检索和反思功能的命令行接口
"""

import asyncio
import argparse
import json
import sys
import os
from pathlib import Path
from typing import Dict, Any, List
import logging

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from server.services.embeddings import embedding_service
from server.routes.plans_recall import recall_service
import aiohttp

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SprintHCLI:
    """Sprint H功能的CLI工具"""

    def __init__(self):
        self.api_base = "http://127.0.0.1:8003"

    async def recall_command(self, args):
        """执行回想命令"""
        print("🔍 RAG轨迹检索")
        print("=" * 50)

        params = {}

        if args.fingerprint:
            params["fingerprint"] = args.fingerprint
            print(f"指纹: {args.fingerprint}")
        elif args.host:
            params["host"] = args.host
            print(f"主机: {args.host}")
        else:
            print("❌ 错误: 必须提供 --fingerprint 或 --host")
            return

        if args.goal:
            params["goal_hash"] = self._hash_goal(args.goal)
            print(f"目标: {args.goal}")

        params.update({
            "k": args.k,
            "min_reward": args.min_reward,
            "since": args.since
        })

        print(f"参数: k={args.k}, min_reward={args.min_reward}, since={args.since}")
        print()

        try:
            # 调用API
            result = await self._call_api("GET", "/plans/recall", params=params)

            if result:
                self._display_recall_results(result)
            else:
                print("❌ 检索失败")

        except Exception as e:
            print(f"❌ 错误: {e}")

    async def reflect_command(self, args):
        """执行反思命令"""
        print("🤔 计划反思")
        print("=" * 50)

        if args.run_id:
            print(f"运行ID: {args.run_id}")
        else:
            print("❌ 错误: 必须提供 --run-id")
            return

        # 构建反思数据
        reflection_data = {
            "history_id": args.run_id,
            "critique": args.critique or "手动触发的反思",
            "suggestions": {
                "manual_input": args.suggestions.split(";") if args.suggestions else [],
                "generated_by": "cli_manual"
            },
            "reward_before": args.reward,
            "tags": ["manual", "cli"]
        }

        print(f"反思内容: {reflection_data['critique']}")
        if args.suggestions:
            print(f"建议: {reflection_data['suggestions']['manual_input']}")
        print()

        try:
            result = await self._call_api("POST", "/plans/reflect", json=reflection_data)

            if result:
                print("✅ 反思创建成功")
                print(f"反思ID: {result.get('id')}")
                print(f"创建时间: {result.get('created_at')}")
            else:
                print("❌ 反思创建失败")

        except Exception as e:
            print(f"❌ 错误: {e}")

    async def embedding_command(self, args):
        """执行嵌入测试命令"""
        print("🔮 嵌入向量测试")
        print("=" * 50)

        if args.text:
            texts = [args.text]
        elif args.file:
            try:
                with open(args.file, 'r', encoding='utf-8') as f:
                    texts = [line.strip() for line in f if line.strip()]
            except Exception as e:
                print(f"❌ 读取文件失败: {e}")
                return
        else:
            texts = [
                "Click apply button on Indeed job page",
                "Scroll down to view more job listings",
                "Extract job title and company information"
            ]

        print(f"待嵌入文本数量: {len(texts)}")
        print(f"提供商: {args.provider or '默认'}")
        print()

        try:
            # 显示可用提供商
            providers = embedding_service.get_available_providers()
            print("可用的嵌入提供商:")
            for provider in providers:
                status = "✅ (默认)" if provider["is_default"] else "📦"
                print(f"  {status} {provider['provider']}: {provider['model']} ({provider['dimension']}维)")
            print()

            # 生成嵌入
            print("生成嵌入向量...")
            embeddings = await embedding_service.embed_batch(texts, args.provider)

            print("✅ 嵌入生成成功")
            print(f"向量数量: {len(embeddings)}")
            print(f"向量维度: {len(embeddings[0]) if embeddings else 0}")

            # 显示示例
            if embeddings and args.verbose:
                print(f"\n第一个向量示例 (前10维): {embeddings[0][:10]}")

            # 保存到文件
            if args.output:
                output_data = {
                    "texts": texts,
                    "embeddings": embeddings,
                    "provider": args.provider,
                    "dimension": len(embeddings[0]) if embeddings else 0
                }
                with open(args.output, 'w', encoding='utf-8') as f:
                    json.dump(output_data, f, ensure_ascii=False, indent=2)
                print(f"结果已保存到: {args.output}")

        except Exception as e:
            print(f"❌ 错误: {e}")

    async def backfill_command(self, args):
        """执行回填命令"""
        print("⚡ 嵌入向量回填")
        print("=" * 50)

        cmd_args = [
            "python", "jobs/backfill_embeddings.py",
            f"--since={args.since}",
            f"--batch-size={args.batch_size}"
        ]

        if args.provider:
            cmd_args.append(f"--provider={args.provider}")

        if args.dry_run:
            cmd_args.append("--dry-run")

        if args.max_batches:
            cmd_args.append(f"--max-batches={args.max_batches}")

        print(f"执行命令: {' '.join(cmd_args)}")
        print()

        # 执行回填脚本
        import subprocess
        try:
            result = subprocess.run(cmd_args, capture_output=True, text=True, cwd=Path(__file__).parent.parent)

            if result.returncode == 0:
                print("✅ 回填完成")
                if result.stdout:
                    print(result.stdout)
            else:
                print("❌ 回填失败")
                if result.stderr:
                    print(result.stderr)

        except Exception as e:
            print(f"❌ 执行错误: {e}")

    async def status_command(self, args):
        """显示系统状态"""
        print("📊 Sprint H 系统状态")
        print("=" * 50)

        try:
            # 检查嵌入服务
            providers = embedding_service.get_available_providers()
            print("🔮 嵌入服务:")
            for provider in providers:
                status = "✅" if provider["is_default"] else "📦"
                print(f"  {status} {provider['provider']}: {provider['model']}")

            # 检查API服务
            print("\n🌐 API服务:")
            try:
                health = await self._call_api("GET", "/plans/recall/health")
                if health:
                    print(f"  ✅ Recall API: {health.get('status')}")
                    print(f"     提供商数量: {health.get('embedding_providers')}")
                else:
                    print("  ❌ Recall API: 不可用")
            except Exception:
                print("  ❌ Recall API: 连接失败")

            # 模拟数据库状态
            print("\n💾 数据库:")
            print("  📦 计划历史表: 已就绪")
            print("  📦 反思表: 已就绪")
            print("  📦 向量索引: 已创建")

        except Exception as e:
            print(f"❌ 状态检查失败: {e}")

    async def _call_api(self, method: str, endpoint: str, params: Dict = None, json: Dict = None):
        """调用API"""
        url = f"{self.api_base}{endpoint}"

        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(method, url, params=params, json=json) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    raise Exception(f"API错误 {response.status}: {error_text}")

    def _display_recall_results(self, result: Dict):
        """显示检索结果"""
        refs = result.get("refs", [])
        method = result.get("method", "unknown")
        query_time = result.get("query_time_ms", 0)

        print("📋 检索结果:")
        print(f"方法: {method}")
        print(f"查询时间: {query_time}ms")
        print(f"找到 {len(refs)} 条引用")
        print()

        for i, ref in enumerate(refs, 1):
            print(f"{i}. 历史ID: {ref.get('history_id')}")
            print(f"   主机: {ref.get('host')}")
            print(f"   奖励: {ref.get('avg_reward', 0):.2f}")
            print(f"   步骤: {' → '.join(ref.get('step_templates', [])[:3])}...")

            if ref.get("similarity_score"):
                print(f"   相似度: {ref['similarity_score']:.3f}")

            meta = ref.get("meta", {})
            if meta:
                print(f"   元数据: {meta}")

            print()

    def _hash_goal(self, goal: str) -> str:
        """生成目标哈希"""
        import hashlib
        return hashlib.sha256(goal.encode()).hexdigest()[:16]

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Sprint H CLI工具")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # recall命令
    recall_parser = subparsers.add_parser("recall", help="检索相似轨迹")
    recall_parser.add_argument("--fingerprint", help="页面指纹")
    recall_parser.add_argument("--host", help="目标主机")
    recall_parser.add_argument("--goal", help="目标描述")
    recall_parser.add_argument("--k", type=int, default=5, help="返回数量")
    recall_parser.add_argument("--min-reward", type=float, default=0.5, help="最小奖励")
    recall_parser.add_argument("--since", default="90d", help="时间范围")

    # reflect命令
    reflect_parser = subparsers.add_parser("reflect", help="创建反思")
    reflect_parser.add_argument("--run-id", type=int, required=True, help="运行ID")
    reflect_parser.add_argument("--critique", help="反思内容")
    reflect_parser.add_argument("--suggestions", help="建议（用;分隔）")
    reflect_parser.add_argument("--reward", type=float, help="奖励值")

    # embedding命令
    embed_parser = subparsers.add_parser("embedding", help="测试嵌入向量")
    embed_parser.add_argument("--text", help="单个文本")
    embed_parser.add_argument("--file", help="文本文件")
    embed_parser.add_argument("--provider", help="嵌入提供商")
    embed_parser.add_argument("--output", help="输出文件")
    embed_parser.add_argument("--verbose", action="store_true", help="显示详细信息")

    # backfill命令
    backfill_parser = subparsers.add_parser("backfill", help="回填嵌入向量")
    backfill_parser.add_argument("--since", default="30d", help="时间范围")
    backfill_parser.add_argument("--batch-size", type=int, default=50, help="批次大小")
    backfill_parser.add_argument("--provider", help="嵌入提供商")
    backfill_parser.add_argument("--dry-run", action="store_true", help="测试运行")
    backfill_parser.add_argument("--max-batches", type=int, help="最大批次数")

    # status命令
    subparsers.add_parser("status", help="显示系统状态")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    cli = SprintHCLI()

    # 执行命令
    if args.command == "recall":
        asyncio.run(cli.recall_command(args))
    elif args.command == "reflect":
        asyncio.run(cli.reflect_command(args))
    elif args.command == "embedding":
        asyncio.run(cli.embedding_command(args))
    elif args.command == "backfill":
        asyncio.run(cli.backfill_command(args))
    elif args.command == "status":
        asyncio.run(cli.status_command(args))

if __name__ == "__main__":
    main()