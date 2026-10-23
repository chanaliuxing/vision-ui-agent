#!/usr/bin/env python3
"""
LLM管理工具 - CLI工具用于管理API密钥、配额和路由
按照upgrade.md Sprint D规范实现
"""
import argparse
import sys
import json
import asyncio
from pathlib import Path

# 添加项目根目录到路径
sys.path.append(str(Path(__file__).parent.parent))

from core.llm.service.enhanced_llm_service import enhanced_llm_service
from core.llm.keys.key_manager import key_manager
from core.llm.routing.llm_router import llm_router
from core.llm.cost.usage_tracker import usage_tracker


def cmd_add_key(args):
    """添加API密钥"""
    key_id = enhanced_llm_service.add_api_key(
        provider=args.provider,
        model=args.model,
        api_key=args.key,
        daily_limit=args.daily_limit,
        monthly_limit=args.monthly_limit
    )
    print(f"✓ Added API key: {key_id}")


def cmd_list_keys(args):
    """列出API密钥"""
    keys = key_manager.list_keys(provider=args.provider, active_only=not args.all)

    if not keys:
        print("No API keys found")
        return

    print(f"{'KEY_ID':<30} {'PROVIDER':<15} {'MODEL':<20} {'REQUESTS':<10} {'ACTIVE':<8}")
    print("-" * 90)

    for key_info in keys:
        print(f"{key_info['key_id']:<30} "
              f"{key_info['provider']:<15} "
              f"{key_info['model']:<20} "
              f"{key_info.get('total_requests', 0):<10} "
              f"{'✓' if key_info['is_active'] else '✗':<8}")


def cmd_deactivate_key(args):
    """停用API密钥"""
    if key_manager.deactivate_key(args.key_id):
        print(f"✓ Deactivated key: {args.key_id}")
    else:
        print(f"✗ Key not found: {args.key_id}")


def cmd_rotate_key(args):
    """轮换API密钥"""
    if key_manager.rotate_key(args.key_id, args.new_key):
        print(f"✓ Rotated key: {args.key_id}")
    else:
        print(f"✗ Failed to rotate key: {args.key_id}")


def cmd_provider_status(args):
    """查看提供商状态"""
    status = enhanced_llm_service.get_service_status()

    print("LLM Provider Status:")
    print("-" * 80)

    for provider, info in status["providers"].items():
        status_icon = "🟢" if info["status"] == "active" else "🟡" if info["status"] == "degraded" else "🔴"
        print(f"{status_icon} {provider}")
        print(f"   Success Rate: {info['success_rate']:.1%}")
        print(f"   Avg Latency: {info['avg_latency_ms']:.0f}ms")
        print(f"   Priority: {info['priority']}")
        print(f"   Tokens Remaining: {info['tokens_remaining_this_minute']}")
        if info['last_error']:
            print(f"   Last Error: {info['last_error']}")
        print()


def cmd_user_usage(args):
    """查看用户使用统计"""
    usage = enhanced_llm_service.get_user_usage(args.user_id, args.days)
    quota = usage_tracker.check_quota(args.user_id)

    print(f"Usage Summary for {args.user_id} (last {args.days} days):")
    print("-" * 60)
    print(f"Total Tokens: {usage['total_tokens']:,}")
    print(f"Total Cost: ${usage['total_cost']:.4f}")
    print(f"Total Requests: {usage['total_requests']}")
    print()

    print("Daily Quota Status:")
    daily = quota["daily"]
    print(f"  Tokens: {daily['tokens_used']:,} / {daily['tokens_limit']:,} "
          f"({daily['tokens_used']/daily['tokens_limit']:.1%})")
    print(f"  Cost: ${daily['cost_used']:.4f} / ${daily['cost_limit']:.2f} "
          f"({daily['cost_used']/daily['cost_limit']:.1%})")
    print()

    print("Monthly Quota Status:")
    monthly = quota["monthly"]
    print(f"  Tokens: {monthly['tokens_used']:,} / {monthly['tokens_limit']:,} "
          f"({monthly['tokens_used']/monthly['tokens_limit']:.1%})")
    print(f"  Cost: ${monthly['cost_used']:.4f} / ${monthly['cost_limit']:.2f} "
          f"({monthly['cost_used']/monthly['cost_limit']:.1%})")
    print()

    if usage['by_provider']:
        print("By Provider:")
        for provider, stats in usage['by_provider'].items():
            print(f"  {provider}: {stats['tokens']:,} tokens, ${stats['cost']:.4f}, {stats['requests']} requests")


def cmd_cost_analysis(args):
    """成本分析"""
    analysis = enhanced_llm_service.get_cost_analysis(args.days)

    print(f"Cost Analysis (last {args.days} days):")
    print("-" * 50)
    print(f"Total Cost: ${analysis['total_cost']:.4f}")
    print(f"Avg Daily Cost: ${analysis['avg_daily_cost']:.4f}")
    print(f"Most Expensive Model: {analysis['most_expensive_model']}")
    print()

    print("By Model:")
    for model, stats in analysis['by_model'].items():
        print(f"  {model}: ${stats['cost']:.4f} ({stats['tokens']:,} tokens, {stats['requests']} requests)")


def cmd_set_quota(args):
    """设置用户配额"""
    quota_config = {}

    if args.daily_tokens:
        quota_config["daily_tokens"] = args.daily_tokens
    if args.daily_cost:
        quota_config["daily_cost_usd"] = args.daily_cost
    if args.monthly_tokens:
        quota_config["monthly_tokens"] = args.monthly_tokens
    if args.monthly_cost:
        quota_config["monthly_cost_usd"] = args.monthly_cost

    usage_tracker.set_quota_limits(args.user_id, quota_config)
    print(f"✓ Updated quota for {args.user_id}")


async def cmd_test_llm(args):
    """测试LLM调用"""
    from core.llm.service.enhanced_llm_service import LLMRequest

    request = LLMRequest(
        user_id=args.user_id or "test_user",
        workflow_id="test_workflow",
        device_id="test_device",
        job_type="chat",
        messages=[{"role": "user", "content": args.message}],
        preferred_provider=args.provider
    )

    response = await enhanced_llm_service.generate(request)

    if response.success:
        print("✓ LLM Response:")
        print(f"Provider: {response.provider_used}:{response.model_used}")
        print(f"Latency: {response.latency_ms:.0f}ms")
        print(f"Tokens: {response.usage_record.total_tokens}")
        print(f"Cost: ${response.usage_record.cost_usd:.6f}")
        print(f"Content: {response.content}")
    else:
        print(f"✗ LLM Error: {response.error}")


def main():
    parser = argparse.ArgumentParser(description="LLM管理工具")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # 添加密钥
    add_parser = subparsers.add_parser("add-key", help="添加API密钥")
    add_parser.add_argument("provider", help="提供商 (gemini/openai/anthropic/deepseek)")
    add_parser.add_argument("model", help="模型名称")
    add_parser.add_argument("key", help="API密钥")
    add_parser.add_argument("--daily-limit", type=int, help="日请求限制")
    add_parser.add_argument("--monthly-limit", type=int, help="月请求限制")
    add_parser.set_defaults(func=cmd_add_key)

    # 列出密钥
    list_parser = subparsers.add_parser("list-keys", help="列出API密钥")
    list_parser.add_argument("--provider", help="过滤提供商")
    list_parser.add_argument("--all", action="store_true", help="包括停用的密钥")
    list_parser.set_defaults(func=cmd_list_keys)

    # 停用密钥
    deactivate_parser = subparsers.add_parser("deactivate-key", help="停用API密钥")
    deactivate_parser.add_argument("key_id", help="密钥ID")
    deactivate_parser.set_defaults(func=cmd_deactivate_key)

    # 轮换密钥
    rotate_parser = subparsers.add_parser("rotate-key", help="轮换API密钥")
    rotate_parser.add_argument("key_id", help="密钥ID")
    rotate_parser.add_argument("new_key", help="新的API密钥")
    rotate_parser.set_defaults(func=cmd_rotate_key)

    # 提供商状态
    status_parser = subparsers.add_parser("provider-status", help="查看提供商状态")
    status_parser.set_defaults(func=cmd_provider_status)

    # 用户使用统计
    usage_parser = subparsers.add_parser("user-usage", help="查看用户使用统计")
    usage_parser.add_argument("user_id", help="用户ID")
    usage_parser.add_argument("--days", type=int, default=7, help="统计天数")
    usage_parser.set_defaults(func=cmd_user_usage)

    # 成本分析
    cost_parser = subparsers.add_parser("cost-analysis", help="成本分析")
    cost_parser.add_argument("--days", type=int, default=30, help="分析天数")
    cost_parser.set_defaults(func=cmd_cost_analysis)

    # 设置配额
    quota_parser = subparsers.add_parser("set-quota", help="设置用户配额")
    quota_parser.add_argument("user_id", help="用户ID")
    quota_parser.add_argument("--daily-tokens", type=int, help="日token限制")
    quota_parser.add_argument("--daily-cost", type=float, help="日成本限制($)")
    quota_parser.add_argument("--monthly-tokens", type=int, help="月token限制")
    quota_parser.add_argument("--monthly-cost", type=float, help="月成本限制($)")
    quota_parser.set_defaults(func=cmd_set_quota)

    # 测试LLM
    test_parser = subparsers.add_parser("test-llm", help="测试LLM调用")
    test_parser.add_argument("message", help="测试消息")
    test_parser.add_argument("--user-id", help="用户ID")
    test_parser.add_argument("--provider", help="指定提供商")
    test_parser.set_defaults(func=cmd_test_llm)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    try:
        if args.command == "test-llm":
            asyncio.run(args.func(args))
        else:
            args.func(args)
    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()