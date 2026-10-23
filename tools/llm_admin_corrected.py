#!/usr/bin/env python3
"""
LLM管理CLI工具 - 按照upgrade.md Sprint D要求
支持配额管理、密钥可视化、审计查看
"""
import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
sys.path.append(str(Path(__file__).parent.parent))

from runtime.actions.llm import (
    get_quota_status, get_key_audit_log, admin_view_keys, set_api_key,
    quota_manager, routing_strategy, LLMProvider
)


def cmd_quota(args):
    """查看配额状态"""
    status = get_quota_status(args.user_id)

    print(f"📊 LLM Quota Status for user: {args.user_id}")
    print("=" * 50)

    daily_limits = status['daily_limits']
    daily_usage = status['daily_usage']

    print(f"📅 Daily Limits:")
    print(f"   Requests: {daily_usage['requests']:,} / {daily_limits['requests']:,}")
    print(f"   Tokens:   {daily_usage['tokens']:,} / {daily_limits['tokens']:,}")
    print(f"   Cost:     ${daily_usage['cost_usd']:.2f} / ${daily_limits['cost_usd']:.2f}")

    print(f"\n⏱️  Per-Minute:")
    print(f"   Requests: {status['per_minute_usage']} / {status['per_minute_limit']}")

    # 计算剩余百分比
    req_pct = (daily_usage['requests'] / daily_limits['requests']) * 100
    token_pct = (daily_usage['tokens'] / daily_limits['tokens']) * 100
    cost_pct = (daily_usage['cost_usd'] / daily_limits['cost_usd']) * 100

    print(f"\n📈 Usage Percentage:")
    print(f"   Requests: {req_pct:.1f}%")
    print(f"   Tokens:   {token_pct:.1f}%")
    print(f"   Cost:     {cost_pct:.1f}%")


def cmd_keys(args):
    """管理API密钥"""
    if args.action == "list":
        if args.admin_user:
            # 管理员查看PLAINTEXT密钥
            keys = admin_view_keys(args.admin_user)
            print(f"🔑 API Keys (PLAINTEXT view by {args.admin_user}):")
            print("=" * 50)
            for provider, key in keys.items():
                if key:
                    print(f"   {provider:10}: {key}")
                else:
                    print(f"   {provider:10}: (not configured)")
        else:
            # 普通用户查看脱敏密钥
            from runtime.actions.llm import key_manager
            print("🔑 API Keys (masked view):")
            print("=" * 50)
            for provider in LLMProvider:
                if provider != LLMProvider.AUTO:
                    key = key_manager.get_key(provider)
                    print(f"   {provider.value:10}: {key or '(not configured)'}")

    elif args.action == "set":
        if not args.admin_user:
            print("❌ Error: --admin-user required for setting keys")
            return

        set_api_key(args.provider, args.key, args.admin_user)
        print(f"✅ API key set for {args.provider} by {args.admin_user}")

    elif args.action == "audit":
        audit_log = get_key_audit_log()
        print("📋 API Key Audit Log:")
        print("=" * 80)
        for entry in audit_log[-10:]:  # 显示最近10条
            print(f"{entry['timestamp']} | {entry['action']:15} | "
                  f"{entry['provider']:10} | {entry.get('admin_user', 'N/A')}")


def cmd_routing(args):
    """查看AUTO路由策略"""
    print("🎯 AUTO Routing Strategy Table:")
    print("=" * 60)

    for task_type, strategies in routing_strategy.routing_table.items():
        print(f"\n📋 Task: {task_type}")
        for quality, providers in strategies.items():
            provider_names = [p.value for p in providers]
            print(f"   {quality:15}: {' → '.join(provider_names)}")

    print(f"\n💰 Provider Metrics:")
    print("   Provider    | Cost | Quality | Speed")
    print("   " + "-" * 40)
    for provider, metrics in routing_strategy.provider_metrics.items():
        print(f"   {provider.value:10}  | {metrics['cost']:.2f} | "
              f"{metrics['quality']:.2f}    | {metrics['speed']:.2f}")


def cmd_test(args):
    """测试LLM调用"""
    import asyncio
    from runtime.actions.llm import llm_submit, llm_plan

    async def run_test():
        try:
            if args.type == "submit":
                result = await llm_submit(
                    content=args.content,
                    user_id=args.user_id,
                    provider=args.provider,
                    quality=args.quality
                )
                print("✅ LLM Submit Test:")
                print(f"   Response: {result['response'][:100]}...")
                print(f"   Provider: {result['provider']}")
                print(f"   Cost: ${result['usage']['cost_usd']:.4f}")

            elif args.type == "plan":
                result = await llm_plan(
                    goal=args.content,
                    page_state={"url": "test.com", "elements": []},
                    user_id=args.user_id,
                    provider=args.provider,
                    quality=args.quality
                )
                print("✅ LLM Plan Test:")
                print(f"   Steps: {len(result['plan']['steps'])}")
                print(f"   Provider: {result['provider']}")
                print(f"   Cost: ${result['usage']['cost_usd']:.4f}")
                print(f"   Confidence: {result['plan']['confidence']}")

        except Exception as e:
            print(f"❌ Test failed: {e}")

    asyncio.run(run_test())


def main():
    parser = argparse.ArgumentParser(description="LLM管理CLI工具")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # quota命令
    quota_parser = subparsers.add_parser("quota", help="查看配额状态")
    quota_parser.add_argument("--user-id", default="default", help="用户ID")

    # keys命令
    keys_parser = subparsers.add_parser("keys", help="管理API密钥")
    keys_parser.add_argument("action", choices=["list", "set", "audit"], help="操作类型")
    keys_parser.add_argument("--admin-user", help="管理员用户（查看PLAINTEXT密钥）")
    keys_parser.add_argument("--provider", help="提供商")
    keys_parser.add_argument("--key", help="API密钥")

    # routing命令
    routing_parser = subparsers.add_parser("routing", help="查看AUTO路由策略")

    # test命令
    test_parser = subparsers.add_parser("test", help="测试LLM调用")
    test_parser.add_argument("type", choices=["submit", "plan"], help="测试类型")
    test_parser.add_argument("content", help="测试内容")
    test_parser.add_argument("--user-id", default="default", help="用户ID")
    test_parser.add_argument("--provider", default="auto", help="提供商")
    test_parser.add_argument("--quality", default="balanced", help="质量要求")

    args = parser.parse_args()

    if args.command == "quota":
        cmd_quota(args)
    elif args.command == "keys":
        cmd_keys(args)
    elif args.command == "routing":
        cmd_routing(args)
    elif args.command == "test":
        cmd_test(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()