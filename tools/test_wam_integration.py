#!/usr/bin/env python3
"""
WAM集成测试 - 测试工作流创作模块的所有组件
"""
import os
import sys
import json
import tempfile
import unittest
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.wam.workflow_builder import WorkflowBuilder, WorkflowTemplates
from tools.wam.workflow_validator import WorkflowValidator
from tools.wam.autofixer import AutoFixer

class TestWAMIntegration(unittest.TestCase):
    """WAM集成测试套件"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.builder = WorkflowBuilder()
        self.validator = WorkflowValidator()
        self.autofixer = AutoFixer()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_basic_workflow_creation(self):
        """测试基础工作流创建"""
        workflow = (self.builder
                   .name("test_workflow")
                   .description("测试工作流")
                   .set_var("test_var", "test_value")
                   .state("start", [
                       {"do": "instr.answer_user", "text": "Hello World"}
                   ])
                   .build())

        self.assertEqual(workflow["name"], "test_workflow")
        self.assertEqual(workflow["start"], "start")
        self.assertIn("start", workflow["states"])
        self.assertEqual(workflow["vars"]["test_var"], "test_value")

    def test_for_loop_workflow(self):
        """测试for循环工作流"""
        workflow = (WorkflowBuilder()
                   .name("loop_test")
                   .for_range("test_loop", "i", 5, [
                       {"do": "instr.answer_user", "text": "Iteration @i"}
                   ])
                   .build())

        self.assertIn("test_loop_loop", workflow["states"])
        self.assertEqual(workflow["vars"]["i"], 0)

        # 验证循环结构
        loop_state = workflow["states"]["test_loop_loop"]
        self.assertIn("transitions", loop_state)
        self.assertEqual(len(loop_state["actions"]), 2)  # body + increment

    def test_workflow_validation(self):
        """测试工作流验证"""
        # 创建有效工作流
        valid_workflow = {
            "version": "1.3",
            "start": "begin",
            "states": {
                "begin": {
                    "actions": [
                        {"do": "instr.answer_user", "text": "Valid workflow"}
                    ]
                }
            }
        }

        result = self.validator.validate(valid_workflow)
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["errors"]), 0)

    def test_workflow_validation_errors(self):
        """测试工作流验证错误检测"""
        # 创建无效工作流（缺少start状态）
        invalid_workflow = {
            "version": "1.3",
            "start": "nonexistent",
            "states": {
                "begin": {
                    "actions": [
                        {"do": "instr.answer_user", "text": "Invalid workflow"}
                    ]
                }
            }
        }

        result = self.validator.validate(invalid_workflow)
        self.assertFalse(result["valid"])
        self.assertGreater(len(result["errors"]), 0)

    def test_variable_reference_validation(self):
        """测试变量引用验证"""
        workflow = {
            "version": "1.3",
            "start": "test",
            "vars": {"defined_var": "value"},
            "states": {
                "test": {
                    "actions": [
                        {"do": "instr.answer_user", "text": "@defined_var is valid"},
                        {"do": "instr.answer_user", "text": "@undefined_var is invalid"}
                    ]
                }
            }
        }

        result = self.validator.validate(workflow)
        self.assertFalse(result["valid"])

        # 应该检测到未定义变量引用
        error_found = any("undefined_var" in error for error in result["errors"])
        self.assertTrue(error_found)

    def test_autofixer_analysis(self):
        """测试自动修复分析"""
        error_context = {
            "error_type": "target_not_found",
            "error_message": "Target element not found",
            "failed_state": "click_button",
            "workflow_path": "test_workflow.json"
        }

        analysis = self.autofixer.analyze_failure(error_context)

        self.assertIn("category", analysis)
        self.assertIn("confidence", analysis)
        self.assertIsInstance(analysis["confidence"], float)
        self.assertGreaterEqual(analysis["confidence"], 0.0)
        self.assertLessEqual(analysis["confidence"], 1.0)

    def test_autofixer_patch_generation(self):
        """测试补丁生成"""
        error_context = {
            "error_type": "action_failed",
            "error_message": "Click action failed",
            "failed_state": "main_action",
            "workflow_path": "test.json"
        }

        analysis = {
            "category": "targeting_issue",
            "confidence": 0.8,
            "details": ["Target selector may be outdated"]
        }

        patches = self.autofixer.generate_patches(error_context, analysis)

        self.assertIsInstance(patches, list)
        if patches:
            patch = patches[0]
            self.assertIn("type", patch)
            self.assertIn("description", patch)
            self.assertIn("confidence", patch)
            self.assertIn("changes", patch)

    def test_template_workflows(self):
        """测试预设模板"""
        # 测试Indeed申请模板
        indeed_wf = WorkflowTemplates.indeed_apply_loop(3)
        workflow = indeed_wf.build()

        self.assertEqual(workflow["name"], "indeed_apply_loop")
        self.assertIn("apply_loop", workflow["states"])

        # 验证模板生成的工作流
        result = self.validator.validate(workflow)
        self.assertTrue(result["valid"], f"Template validation failed: {result['errors']}")

    def test_workflow_file_operations(self):
        """测试工作流文件操作"""
        workflow_path = os.path.join(self.temp_dir, "test_workflow.json")

        # 创建并保存工作流
        workflow = (WorkflowBuilder()
                   .name("file_test")
                   .state("start", [
                       {"do": "instr.answer_user", "text": "File test"}
                   ])
                   .build())

        with open(workflow_path, 'w', encoding='utf-8') as f:
            json.dump(workflow, f, indent=2)

        # 验证文件中的工作流
        result = self.validator.validate_file(workflow_path)
        self.assertTrue(result["valid"])

    def test_complex_workflow_patterns(self):
        """测试复杂工作流模式"""
        # 创建包含条件、循环、错误处理的复杂工作流
        builder = WorkflowBuilder().name("complex_test")

        # 添加条件分支
        builder.conditional("check_condition", "@test_var == 'test'", [
            {"do": "instr.answer_user", "text": "Condition met"}
        ], [
            {"do": "instr.answer_user", "text": "Condition not met"}
        ], "next_step")

        # 添加错误恢复
        builder.error_recovery("recovery", [
            {"do": "sleep_ms", "duration": 1000}
        ], "check_condition", max_retries=2)

        # 添加结束状态
        builder.state("next_step", [
            {"do": "instr.answer_user", "text": "Workflow complete"}
        ])

        workflow = builder.build()

        # 验证复杂工作流
        result = self.validator.validate(workflow)
        self.assertTrue(result["valid"], f"Complex workflow validation failed: {result['errors']}")

    def test_action_parameter_validation(self):
        """测试动作参数验证"""
        workflow = {
            "version": "1.3",
            "start": "test",
            "states": {
                "test": {
                    "actions": [
                        # 缺少必需参数的动作
                        {"do": "instr.click"},  # 缺少target
                        {"do": "instr.type_text", "target": {"css": "#input"}},  # 缺少text
                        {"do": "sleep_ms"}  # 缺少duration
                    ]
                }
            }
        }

        result = self.validator.validate(workflow)
        self.assertFalse(result["valid"])

        # 应该检测到多个参数错误
        self.assertGreaterEqual(len(result["errors"]), 3)

    def test_loop_termination_validation(self):
        """测试循环终止性验证"""
        # 创建可能的无限循环
        workflow = {
            "version": "1.3",
            "start": "infinite_loop",
            "states": {
                "infinite_loop": {
                    "actions": [
                        {"do": "sleep_ms", "duration": 100}
                    ],
                    "on_success": "infinite_loop"  # 自循环
                }
            }
        }

        result = self.validator.validate(workflow)

        # 应该检测到循环问题
        loop_warning_found = any("loop" in error.lower() for error in result["errors"])
        self.assertTrue(loop_warning_found or len(result["warnings"]) > 0)

def run_integration_tests():
    """运行所有集成测试"""
    unittest.main(verbosity=2)

if __name__ == "__main__":
    print("Running WAM Integration Tests...")
    run_integration_tests()