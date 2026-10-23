#!/usr/bin/env python3
"""
Sprint I: DPO训练流水线
使用TRL库训练Direct Preference Optimization模型
"""

import os
import json
import argparse
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
import torch
from datetime import datetime

# 检查依赖
try:
    from transformers import (
        AutoTokenizer, AutoModelForCausalLM, TrainingArguments,
        BitsAndBytesConfig, TrainerCallback
    )
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from trl import DPOTrainer
    from datasets import Dataset
    import wandb
    HAS_TRAINING_DEPS = True
except ImportError as e:
    HAS_TRAINING_DEPS = False
    print(f"Training dependencies not available: {e}")
    print("Run: pip install transformers trl peft accelerate bitsandbytes datasets wandb")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class DPOConfig:
    """DPO训练配置"""
    # 模型配置
    model_name: str = "microsoft/DialoGPT-small"  # 小模型用于演示
    tokenizer_name: Optional[str] = None
    use_4bit: bool = True
    use_lora: bool = True

    # LoRA配置
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.1
    lora_target_modules: List[str] = field(default_factory=lambda: ["q_proj", "v_proj"])

    # DPO配置
    beta: float = 0.1
    max_length: int = 512
    max_prompt_length: int = 256

    # 训练配置
    num_train_epochs: int = 1
    per_device_train_batch_size: int = 2
    per_device_eval_batch_size: int = 2
    gradient_accumulation_steps: int = 4
    learning_rate: float = 5e-5
    lr_scheduler_type: str = "cosine"
    warmup_ratio: float = 0.1

    # 保存配置
    output_dir: str = "models/dpo_planner"
    save_steps: int = 500
    eval_steps: int = 250

    # 监控配置
    logging_steps: int = 10
    report_to: str = "none"  # "wandb" | "tensorboard" | "none"

class DPOTrainingPipeline:
    """DPO训练流水线"""

    def __init__(self, config: DPOConfig):
        self.config = config
        self.model = None
        self.tokenizer = None
        self.trainer = None

    def load_model_and_tokenizer(self):
        """加载模型和分词器"""
        if not HAS_TRAINING_DEPS:
            raise RuntimeError("Training dependencies not installed")

        logger.info(f"Loading model: {self.config.model_name}")

        # 配置量化
        if self.config.use_4bit:
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_use_double_quant=True,
            )
        else:
            bnb_config = None

        # 加载模型
        self.model = AutoModelForCausalLM.from_pretrained(
            self.config.model_name,
            quantization_config=bnb_config,
            torch_dtype=torch.float16 if self.config.use_4bit else torch.float32,
            device_map="auto",
            trust_remote_code=True
        )

        # 加载分词器
        tokenizer_name = self.config.tokenizer_name or self.config.model_name
        self.tokenizer = AutoTokenizer.from_pretrained(
            tokenizer_name,
            trust_remote_code=True,
            padding_side="left"
        )

        # 设置pad token
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        # 配置LoRA
        if self.config.use_lora:
            if self.config.use_4bit:
                self.model = prepare_model_for_kbit_training(self.model)

            lora_config = LoraConfig(
                r=self.config.lora_r,
                lora_alpha=self.config.lora_alpha,
                target_modules=self.config.lora_target_modules,
                lora_dropout=self.config.lora_dropout,
                bias="none",
                task_type="CAUSAL_LM",
            )

            self.model = get_peft_model(self.model, lora_config)
            self.model.print_trainable_parameters()

        logger.info("Model and tokenizer loaded successfully")

    def load_preference_data(self, train_path: str, eval_path: str = None) -> Dict[str, Dataset]:
        """加载偏好对数据"""
        logger.info(f"Loading preference data from {train_path}")

        # 加载训练数据
        train_data = self.load_jsonl(train_path)
        train_dataset = self.convert_to_dpo_format(train_data)

        datasets = {"train": train_dataset}

        # 加载验证数据
        if eval_path and os.path.exists(eval_path):
            eval_data = self.load_jsonl(eval_path)
            eval_dataset = self.convert_to_dpo_format(eval_data)
            datasets["eval"] = eval_dataset

        logger.info(f"Loaded {len(train_dataset)} training samples")
        if "eval" in datasets:
            logger.info(f"Loaded {len(datasets['eval'])} evaluation samples")

        return datasets

    def load_jsonl(self, path: str) -> List[Dict]:
        """加载JSONL文件"""
        data = []
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                data.append(json.loads(line.strip()))
        return data

    def convert_to_dpo_format(self, preference_pairs: List[Dict]) -> Dataset:
        """将偏好对转换为DPO格式"""
        dpo_data = []

        for pair in preference_pairs:
            # 构建prompt
            prompt = self.build_prompt_from_context(pair["context"])

            # 转换计划为文本
            chosen = self.plan_to_text(pair["preferred_plan"])
            rejected = self.plan_to_text(pair["rejected_plan"])

            dpo_data.append({
                "prompt": prompt,
                "chosen": chosen,
                "rejected": rejected,
                "margin": pair.get("reward_margin", 0)
            })

        return Dataset.from_list(dpo_data)

    def build_prompt_from_context(self, context: Dict) -> str:
        """从上下文构建提示"""
        host = context.get("host", "")
        goal = context.get("goal_hash", "")
        page_meta = context.get("page_state_meta", {})
        constraints = context.get("constraints", {})

        prompt = f"""Plan a UI automation sequence for the following context:

Host: {host}
Goal: {goal}
Page Layout: left_ratio={page_meta.get('left_ratio', 0.5)}, right_ratio={page_meta.get('right_ratio', 0.5)}
Constraints: max_steps={constraints.get('max_steps', 5)}, must_stay_in_host={constraints.get('must_stay_in_host', True)}

Generate a sequence of actions as a JSON plan:"""

        return prompt

    def plan_to_text(self, plan: Dict) -> str:
        """将计划转换为文本"""
        steps = plan.get("steps", [])

        # 简化的计划表示
        plan_json = {
            "steps": [
                {
                    "do": step.get("do"),
                    "target": self.simplify_args(step.get("args", {}))
                }
                for step in steps
            ]
        }

        return json.dumps(plan_json, ensure_ascii=False)

    def simplify_args(self, args: Dict) -> str:
        """简化参数表示"""
        if "bbox" in args:
            return "target_element"
        elif "at_bbox" in args and "amount" in args:
            return f"scroll_{args['amount']}"
        elif "text_any_of" in args:
            return "button_search"
        else:
            return "element"

    def setup_trainer(self, datasets: Dict[str, Dataset]):
        """设置DPO训练器"""
        logger.info("Setting up DPO trainer")

        # 训练参数
        training_args = TrainingArguments(
            output_dir=self.config.output_dir,
            num_train_epochs=self.config.num_train_epochs,
            per_device_train_batch_size=self.config.per_device_train_batch_size,
            per_device_eval_batch_size=self.config.per_device_eval_batch_size,
            gradient_accumulation_steps=self.config.gradient_accumulation_steps,
            learning_rate=self.config.learning_rate,
            lr_scheduler_type=self.config.lr_scheduler_type,
            warmup_ratio=self.config.warmup_ratio,
            logging_steps=self.config.logging_steps,
            save_steps=self.config.save_steps,
            eval_steps=self.config.eval_steps,
            evaluation_strategy="steps" if "eval" in datasets else "no",
            save_strategy="steps",
            load_best_model_at_end=True if "eval" in datasets else False,
            metric_for_best_model="eval_loss" if "eval" in datasets else None,
            greater_is_better=False,
            report_to=self.config.report_to,
            remove_unused_columns=False,
            bf16=True,
            dataloader_pin_memory=False,  # 减少内存使用
        )

        # DPO训练器
        self.trainer = DPOTrainer(
            model=self.model,
            args=training_args,
            beta=self.config.beta,
            train_dataset=datasets["train"],
            eval_dataset=datasets.get("eval"),
            tokenizer=self.tokenizer,
            max_length=self.config.max_length,
            max_prompt_length=self.config.max_prompt_length,
        )

        # 添加回调
        self.trainer.add_callback(TrainingCallback())

    def train(self, datasets: Dict[str, Dataset]):
        """执行训练"""
        logger.info("Starting DPO training")

        # 设置wandb（如果启用）
        if self.config.report_to == "wandb":
            wandb.init(
                project="sprint-i-dpo",
                name=f"dpo_planner_{datetime.now().strftime('%Y%m%d_%H%M')}",
                config=self.config.__dict__
            )

        # 开始训练
        train_result = self.trainer.train()

        # 保存模型
        self.trainer.save_model()
        self.trainer.save_state()

        # 保存训练指标
        metrics = train_result.metrics
        self.save_training_metrics(metrics)

        logger.info("Training completed successfully")
        return metrics

    def save_training_metrics(self, metrics: Dict):
        """保存训练指标"""
        metrics_path = os.path.join(self.config.output_dir, "training_metrics.json")

        with open(metrics_path, 'w') as f:
            json.dump(metrics, f, indent=2, default=str)

        logger.info(f"Training metrics saved to {metrics_path}")

    def evaluate(self, eval_dataset: Dataset = None) -> Dict:
        """评估模型"""
        if eval_dataset is None and hasattr(self.trainer, 'eval_dataset'):
            eval_dataset = self.trainer.eval_dataset

        if eval_dataset is None:
            logger.warning("No evaluation dataset available")
            return {}

        logger.info("Running evaluation")
        eval_result = self.trainer.evaluate(eval_dataset=eval_dataset)

        return eval_result

class MockDPOTrainer:
    """模拟DPO训练器（当依赖不可用时）"""

    def __init__(self, config: DPOConfig):
        self.config = config

    def run_mock_training(self, train_path: str, eval_path: str = None):
        """运行模拟训练"""
        logger.info("Running mock DPO training (dependencies not available)")

        # 模拟加载数据
        train_data = self.load_jsonl(train_path) if os.path.exists(train_path) else []
        eval_data = self.load_jsonl(eval_path) if eval_path and os.path.exists(eval_path) else []

        logger.info(f"Mock training with {len(train_data)} train samples, {len(eval_data)} eval samples")

        # 模拟训练过程
        import time
        import random

        epochs = self.config.num_train_epochs
        for epoch in range(epochs):
            logger.info(f"Mock epoch {epoch + 1}/{epochs}")

            # 模拟训练步骤
            for step in range(0, len(train_data), self.config.per_device_train_batch_size):
                if step % (self.config.logging_steps * self.config.per_device_train_batch_size) == 0:
                    loss = random.uniform(1.0, 2.0) - (step / len(train_data)) * 0.5
                    logger.info(f"Step {step}: loss = {loss:.4f}")

                time.sleep(0.01)  # 模拟计算时间

        # 模拟保存模型
        os.makedirs(self.config.output_dir, exist_ok=True)

        mock_metrics = {
            "train_loss": random.uniform(0.8, 1.2),
            "eval_loss": random.uniform(0.9, 1.3),
            "train_runtime": random.uniform(100, 300),
            "train_samples_per_second": random.uniform(1, 5)
        }

        with open(os.path.join(self.config.output_dir, "training_metrics.json"), 'w') as f:
            json.dump(mock_metrics, f, indent=2)

        logger.info("Mock training completed")
        return mock_metrics

    def load_jsonl(self, path: str) -> List[Dict]:
        """加载JSONL文件"""
        data = []
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    data.append(json.loads(line.strip()))
        except Exception as e:
            logger.warning(f"Failed to load {path}: {e}")
        return data

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="DPO训练流水线")
    parser.add_argument("--train-data", required=True, help="训练数据路径 (JSONL)")
    parser.add_argument("--eval-data", help="验证数据路径 (JSONL)")
    parser.add_argument("--model-name", default="microsoft/DialoGPT-small", help="基础模型名称")
    parser.add_argument("--output-dir", default="models/dpo_planner", help="输出目录")
    parser.add_argument("--epochs", type=int, default=1, help="训练轮数")
    parser.add_argument("--batch-size", type=int, default=2, help="批大小")
    parser.add_argument("--learning-rate", type=float, default=5e-5, help="学习率")
    parser.add_argument("--beta", type=float, default=0.1, help="DPO beta参数")
    parser.add_argument("--use-lora", action="store_true", help="使用LoRA")
    parser.add_argument("--use-4bit", action="store_true", help="使用4bit量化")
    parser.add_argument("--report-to", default="none", choices=["wandb", "tensorboard", "none"], help="实验跟踪")

    args = parser.parse_args()

    # 创建配置
    config = DPOConfig(
        model_name=args.model_name,
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        beta=args.beta,
        use_lora=args.use_lora,
        use_4bit=args.use_4bit,
        report_to=args.report_to
    )

    try:
        if HAS_TRAINING_DEPS:
            # 真实训练
            pipeline = DPOTrainingPipeline(config)
            pipeline.load_model_and_tokenizer()

            datasets = pipeline.load_preference_data(args.train_data, args.eval_data)
            pipeline.setup_trainer(datasets)

            metrics = pipeline.train(datasets)
            logger.info(f"Training metrics: {metrics}")

        else:
            # 模拟训练
            pipeline = MockDPOTrainer(config)
            metrics = pipeline.run_mock_training(args.train_data, args.eval_data)
            logger.info(f"Mock training metrics: {metrics}")

    except Exception as e:
        logger.error(f"Training failed: {e}")
        raise

if __name__ == "__main__":
    main()