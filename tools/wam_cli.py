#!/usr/bin/env python3
"""
WAM CLI - Workflow Authoring Module Command Line Interface
统一的工作流创作命令行工具
"""
import os
import sys
import json
import argparse
import logging
from pathlib import Path
from typing import Dict, Any, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.wam.workflow_builder import WorkflowBuilder, WorkflowTemplates
from tools.wam.workflow_validator import WorkflowValidator
from tools.wam.autofixer import AutoFixer

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class WAMCli:
    """WAM命令行接口"""

    def __init__(self):
        self.validator = WorkflowValidator()
        self.autofixer = AutoFixer()

    def create_workflow(self, args):
        """创建新工作流"""
        print(f"Creating workflow: {args.name}")

        if args.template:
            # 使用模板创建
            template_method = getattr(WorkflowTemplates, args.template, None)
            if not template_method:
                print(f"Template '{args.template}' not found")
                return 1

            builder = template_method()
            if args.name != args.template:
                builder.name(args.name)
        else:
            # 创建空工作流
            builder = WorkflowBuilder().name(args.name)

            if args.description:
                builder.description(args.description)

            # 添加基础状态
            builder.state("start", [
                {"do": "instr.answer_user", "text": f"工作流 {args.name} 已启动"}
            ])

        # 保存工作流
        output_path = args.output or f"flows/{args.name}.json"
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        try:
            builder.save_to_file(output_path)
            print(f"Workflow saved to: {output_path}")
            return 0
        except Exception as e:
            print(f"Error saving workflow: {e}")
            return 1

    def validate_workflow(self, args):
        """验证工作流"""
        print(f"Validating workflow: {args.file}")

        try:
            result = self.validator.validate_file(args.file)

            if result["valid"]:
                print("✅ Workflow validation PASSED")
            else:
                print("❌ Workflow validation FAILED")

            if result["errors"]:
                print("\nErrors:")
                for error in result["errors"]:
                    print(f"  - {error}")

            if result["warnings"]:
                print("\nWarnings:")
                for warning in result["warnings"]:
                    print(f"  - {warning}")

            return 0 if result["valid"] else 1

        except Exception as e:
            print(f"Error validating workflow: {e}")
            return 1

    def fix_workflow(self, args):
        """自动修复工作流"""
        print(f"Analyzing and fixing workflow: {args.file}")

        try:
            # 模拟错误上下文
            error_context = {
                "error_type": args.error_type or "validation_error",
                "error_message": args.error_message or "Workflow validation failed",
                "failed_state": args.failed_state,
                "screenshot_path": args.screenshot,
                "workflow_path": args.file
            }

            # 分析问题
            analysis = self.autofixer.analyze_failure(error_context)
            print(f"Problem analysis: {analysis['category']}")
            print(f"Confidence: {analysis['confidence']:.2f}")

            if analysis['details']:
                print("Details:")
                for detail in analysis['details']:
                    print(f"  - {detail}")

            # 生成修复补丁
            patches = self.autofixer.generate_patches(error_context, analysis)

            if not patches:
                print("No patches could be generated for this issue")
                return 1

            print(f"\nGenerated {len(patches)} potential fixes:")
            for i, patch in enumerate(patches, 1):
                print(f"{i}. {patch['description']} (confidence: {patch['confidence']:.2f})")

            # 应用最佳补丁
            if args.auto_apply:
                best_patch = max(patches, key=lambda p: p['confidence'])
                if best_patch['confidence'] >= 0.7:
                    print(f"\nAuto-applying patch: {best_patch['description']}")
                    result = self.autofixer.apply_patch(args.file, best_patch)

                    if result['success']:
                        print("✅ Patch applied successfully")
                        if args.backup:
                            backup_path = f"{args.file}.backup"
                            os.rename(args.file, backup_path)
                            print(f"Backup saved to: {backup_path}")
                    else:
                        print(f"❌ Failed to apply patch: {result['error']}")
                        return 1
                else:
                    print("Patch confidence too low for auto-apply")
            else:
                # 交互式选择
                choice = input("\nApply best patch? (y/n): ")
                if choice.lower() == 'y':
                    best_patch = patches[0]
                    result = self.autofixer.apply_patch(args.file, best_patch)

                    if result['success']:
                        print("✅ Patch applied successfully")
                    else:
                        print(f"❌ Failed to apply patch: {result['error']}")
                        return 1

            return 0

        except Exception as e:
            print(f"Error fixing workflow: {e}")
            return 1

    def list_templates(self, args):
        """列出可用模板"""
        print("Available workflow templates:")

        templates = [
            ("indeed_apply_loop", "Indeed循环申请模板"),
            ("wechat_poll_reply", "微信轮询回复模板"),
            ("web_login_sequence", "通用网页登录序列模板"),
            ("data_extraction_pipeline", "数据提取管道模板")
        ]

        for name, desc in templates:
            print(f"  {name:<25} - {desc}")

        return 0

    def build_from_task(self, args):
        """从任务描述构建工作流"""
        print(f"Building workflow from task: {args.task}")

        # 简单的任务解析和工作流生成
        task = args.task.lower()

        if "indeed" in task and "apply" in task:
            builder = WorkflowTemplates.indeed_apply_loop(args.count or 10)
        elif "wechat" in task or "微信" in task:
            builder = WorkflowTemplates.wechat_poll_reply(args.period or 5000)
        elif "login" in task or "登录" in task:
            site = args.site or "website"
            builder = WorkflowTemplates.web_login_sequence(site)
        else:
            # 创建通用工作流
            builder = (WorkflowBuilder()
                      .name(args.name or "generated_workflow")
                      .description(f"Generated from task: {args.task}")
                      .state("start", [
                          {"do": "instr.answer_user", "text": f"执行任务: {args.task}"}
                      ]))

        # 保存工作流
        output_path = args.output or f"flows/{args.name or 'generated'}.json"
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        try:
            builder.save_to_file(output_path)
            print(f"Workflow generated and saved to: {output_path}")

            # 自动验证
            result = self.validator.validate_file(output_path)
            if result["valid"]:
                print("✅ Generated workflow is valid")
            else:
                print("⚠️ Generated workflow has validation issues")
                for error in result["errors"]:
                    print(f"  - {error}")

            return 0

        except Exception as e:
            print(f"Error generating workflow: {e}")
            return 1

def main():
    parser = argparse.ArgumentParser(description="WAM - Workflow Authoring Module CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Create workflow command
    create_parser = subparsers.add_parser("create", help="Create new workflow")
    create_parser.add_argument("name", help="Workflow name")
    create_parser.add_argument("--template", help="Template to use")
    create_parser.add_argument("--description", help="Workflow description")
    create_parser.add_argument("--output", help="Output file path")

    # Validate workflow command
    validate_parser = subparsers.add_parser("validate", help="Validate workflow")
    validate_parser.add_argument("file", help="Workflow file to validate")

    # Fix workflow command
    fix_parser = subparsers.add_parser("fix", help="Auto-fix workflow issues")
    fix_parser.add_argument("file", help="Workflow file to fix")
    fix_parser.add_argument("--error-type", help="Type of error encountered")
    fix_parser.add_argument("--error-message", help="Error message")
    fix_parser.add_argument("--failed-state", help="State where error occurred")
    fix_parser.add_argument("--screenshot", help="Screenshot of error")
    fix_parser.add_argument("--auto-apply", action="store_true", help="Auto-apply best patch")
    fix_parser.add_argument("--backup", action="store_true", help="Create backup before applying patch")

    # List templates command
    list_parser = subparsers.add_parser("templates", help="List available templates")

    # Build from task command
    build_parser = subparsers.add_parser("build", help="Build workflow from task description")
    build_parser.add_argument("task", help="Task description")
    build_parser.add_argument("--name", help="Workflow name")
    build_parser.add_argument("--output", help="Output file path")
    build_parser.add_argument("--count", type=int, help="Count for loop-based workflows")
    build_parser.add_argument("--period", type=int, help="Period for polling workflows")
    build_parser.add_argument("--site", help="Site name for login workflows")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    cli = WAMCli()

    if args.command == "create":
        return cli.create_workflow(args)
    elif args.command == "validate":
        return cli.validate_workflow(args)
    elif args.command == "fix":
        return cli.fix_workflow(args)
    elif args.command == "templates":
        return cli.list_templates(args)
    elif args.command == "build":
        return cli.build_from_task(args)
    else:
        print(f"Unknown command: {args.command}")
        return 1

if __name__ == "__main__":
    sys.exit(main())