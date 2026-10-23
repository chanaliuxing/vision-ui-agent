#!/usr/bin/env python3
"""
Sprint I: 偏好对数据生成器
从 plans_history 和 plan_candidates 生成DPO训练的偏好对数据
"""

import asyncio
import argparse
import json
import sys
import os
import logging
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timedelta
from pathlib import Path
import hashlib
from collections import defaultdict, Counter

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from server.services.embeddings import build_fingerprint_text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PreferencePairGenerator:
    """偏好对生成器"""

    def __init__(self, min_reward_margin: float = 0.8, max_pairs_per_fingerprint: int = 10):
        self.min_reward_margin = min_reward_margin
        self.max_pairs_per_fingerprint = max_pairs_per_fingerprint
        self.stats = {
            "total_histories": 0,
            "valid_fingerprints": 0,
            "generated_pairs": 0,
            "filtered_pairs": 0,
            "duplicate_pairs": 0
        }

    def hash_fingerprint(self, fingerprint_data: Dict) -> str:
        """生成指纹哈希"""
        fp_str = json.dumps(fingerprint_data, sort_keys=True)
        return hashlib.sha256(fp_str.encode()).hexdigest()[:16]

    def extract_context(self, history_row: Dict) -> Dict[str, Any]:
        """提取上下文信息"""
        return {
            "host": history_row.get("host", ""),
            "goal_hash": history_row.get("goal_hash", ""),
            "page_state_meta": history_row.get("page_state_meta", {}),
            "constraints": {
                "must_stay_in_host": history_row.get("host", "").split(".")[0] if history_row.get("host") else "",
                "max_steps": 5,
                "no_dom_click": True
            },
            "references": [],  # 将在实际使用时填充RAG引用
            "timestamp": history_row.get("created_at", "").isoformat() if history_row.get("created_at") else ""
        }

    def build_microplan_from_history(self, history_row: Dict) -> Dict[str, Any]:
        """从历史记录构建MicroPlan"""
        action_sigs = history_row.get("candidate_action_sigs") or history_row.get("action_sigs") or []

        # 将动作签名转换为MicroPlan格式
        steps = []
        for sig in action_sigs[:5]:  # 限制步数
            if "@" in sig:
                action, target = sig.split("@", 1)
                step = {"do": f"{action}_coordinates"}

                # 根据动作类型设置参数
                if action == "click":
                    step["args"] = {"bbox": f"@ps.{target}"}
                elif action == "wheel":
                    if "(" in target and ")" in target:
                        amount = target[target.find("(")+1:target.find(")")]
                        step["args"] = {"at_bbox": "@ps.panes.left.rect", "amount": int(amount)}
                elif action == "wait":
                    step = {"do": "wait_for", "args": {"until": {"type": "ext.wait_quiet", "timeout_ms": 3000}}}
                elif action.startswith("ext."):
                    step = {"do": action, "args": {"mode": "find_button_bbox", "text_any_of": ["Apply", "Submit"]}}

                steps.append(step)

        return {
            "version": "1.0",
            "steps": steps,
            "metadata": {
                "source": "history_reconstruction",
                "original_sigs": action_sigs
            }
        }

    async def get_historical_data(self, host: str, goal: str, start_date: str, end_date: str) -> List[Dict]:
        """获取历史数据 - 模拟实现"""
        # 在实际项目中，这里应该是真实的数据库查询
        mock_data = [
            {
                "id": 1,
                "host": "ca.indeed.com",
                "goal_hash": self.hash_goal(goal),
                "fingerprint": "fp_indeed_001",
                "page_state_meta": {"left_ratio": 0.33, "right_ratio": 0.67, "dpr": 1.25},
                "candidate_action_sigs": ["wheel@leftPane(-600)", "click@list[0]", "wait@quiet", "ext.extract(apply)"],
                "action_sigs": ["wheel@leftPane(-600)", "click@list[0]", "wait@quiet", "ext.extract(apply)", "click@apply"],
                "reward": 1.8,
                "success": True,
                "created_at": datetime.now() - timedelta(days=5)
            },
            {
                "id": 2,
                "host": "ca.indeed.com",
                "goal_hash": self.hash_goal(goal),
                "fingerprint": "fp_indeed_001",  # 相同指纹
                "page_state_meta": {"left_ratio": 0.33, "right_ratio": 0.67, "dpr": 1.25},
                "candidate_action_sigs": ["click@list[1]", "wait@quiet"],
                "action_sigs": ["click@list[1]", "wait@quiet"],
                "reward": 0.4,
                "success": False,
                "created_at": datetime.now() - timedelta(days=3)
            },
            {
                "id": 3,
                "host": "www.xiaohongshu.com",
                "goal_hash": self.hash_goal("expand_comments"),
                "fingerprint": "fp_xhs_001",
                "page_state_meta": {"left_ratio": 0.0, "right_ratio": 1.0, "dpr": 2.0},
                "candidate_action_sigs": ["scroll@comments", "click@expand", "wait@load"],
                "action_sigs": ["scroll@comments", "click@expand", "wait@load"],
                "reward": 1.2,
                "success": True,
                "created_at": datetime.now() - timedelta(days=1)
            }
        ]

        # 过滤条件
        filtered = [
            row for row in mock_data
            if (row["host"] == host if host else True) and
               (row["goal_hash"] == self.hash_goal(goal) if goal else True)
        ]

        return filtered

    def hash_goal(self, goal: str) -> str:
        """生成目标哈希"""
        return hashlib.sha256(goal.encode()).hexdigest()[:16]

    def group_by_fingerprint(self, histories: List[Dict]) -> Dict[str, List[Dict]]:
        """按指纹分组历史记录"""
        groups = defaultdict(list)

        for history in histories:
            fp_key = history["fingerprint"]
            groups[fp_key].append(history)

        return dict(groups)

    def generate_pairs_for_group(self, histories: List[Dict]) -> List[Dict]:
        """为同一指纹组生成偏好对"""
        pairs = []

        # 按奖励排序
        sorted_histories = sorted(histories, key=lambda x: x.get("reward", 0), reverse=True)

        # 生成偏好对
        for i, good in enumerate(sorted_histories):
            if good.get("reward", 0) < 0.8:  # 跳过低奖励的"好"示例
                continue

            for j, bad in enumerate(sorted_histories[i+1:], i+1):
                reward_margin = good.get("reward", 0) - bad.get("reward", 0)

                if reward_margin >= self.min_reward_margin:
                    pair = self.create_preference_pair(good, bad, reward_margin)
                    pairs.append(pair)

                    # 限制每个指纹的偏好对数量
                    if len(pairs) >= self.max_pairs_per_fingerprint:
                        break

            if len(pairs) >= self.max_pairs_per_fingerprint:
                break

        return pairs

    def create_preference_pair(self, preferred: Dict, rejected: Dict, margin: float) -> Dict:
        """创建偏好对"""
        fingerprint_data = {
            "host": preferred["host"],
            "fingerprint": preferred["fingerprint"],
            "page_meta": preferred.get("page_state_meta", {})
        }

        return {
            "fingerprint_hash": self.hash_fingerprint(fingerprint_data),
            "host": preferred["host"],
            "goal_hash": preferred.get("goal_hash"),

            "context": self.extract_context(preferred),

            "preferred_plan": self.build_microplan_from_history(preferred),
            "rejected_plan": self.build_microplan_from_history(rejected),

            "reward_preferred": preferred.get("reward", 0),
            "reward_rejected": rejected.get("reward", 0),
            "reward_margin": margin,

            "source_type": "trajectories",
            "preferred_history_id": preferred["id"],
            "rejected_history_id": rejected["id"],

            "quality_score": self.calculate_quality_score(preferred, rejected, margin),
            "teacher_verified": False,

            "dataset_split": "train",  # 默认为训练集

            "meta": {
                "why": f"preferred reaches better reward ({preferred.get('reward', 0):.2f} vs {rejected.get('reward', 0):.2f})",
                "preferred_success": preferred.get("success", False),
                "rejected_success": rejected.get("success", False),
                "step_count_diff": len(preferred.get("candidate_action_sigs", [])) - len(rejected.get("candidate_action_sigs", []))
            }
        }

    def calculate_quality_score(self, preferred: Dict, rejected: Dict, margin: float) -> float:
        """计算偏好对质量评分"""
        score = 0.0

        # 奖励差值越大越好
        score += min(margin, 1.0) * 0.4

        # 成功vs失败的对比更有价值
        if preferred.get("success") and not rejected.get("success"):
            score += 0.3

        # 步骤数量差异
        pref_steps = len(preferred.get("candidate_action_sigs", []))
        rej_steps = len(rejected.get("candidate_action_sigs", []))
        if pref_steps <= rej_steps:  # 更简洁的方案更好
            score += 0.2

        # 时间接近度（相近时间的对比更有意义）
        pref_time = preferred.get("created_at", datetime.now())
        rej_time = rejected.get("created_at", datetime.now())
        time_diff = abs((pref_time - rej_time).days)
        if time_diff <= 7:  # 一周内
            score += 0.1

        return min(score, 1.0)

    def filter_and_deduplicate(self, pairs: List[Dict]) -> List[Dict]:
        """过滤和去重偏好对"""
        # 按质量分数排序
        pairs.sort(key=lambda x: x.get("quality_score", 0), reverse=True)

        # 去重：基于计划内容的哈希
        seen_signatures = set()
        filtered_pairs = []

        for pair in pairs:
            # 生成偏好对的签名
            pref_sig = self.get_plan_signature(pair["preferred_plan"])
            rej_sig = self.get_plan_signature(pair["rejected_plan"])
            pair_signature = f"{pref_sig}|{rej_sig}"

            if pair_signature not in seen_signatures:
                seen_signatures.add(pair_signature)
                filtered_pairs.append(pair)
                self.stats["generated_pairs"] += 1
            else:
                self.stats["duplicate_pairs"] += 1

        return filtered_pairs

    def get_plan_signature(self, plan: Dict) -> str:
        """获取计划签名用于去重"""
        steps = plan.get("steps", [])
        signature_parts = []

        for step in steps:
            do = step.get("do", "")
            args = step.get("args", {})
            # 简化签名，忽略具体的坐标值
            if "bbox" in args:
                signature_parts.append(f"{do}@bbox")
            elif "at_bbox" in args:
                signature_parts.append(f"{do}@{args.get('amount', 'scroll')}")
            else:
                signature_parts.append(do)

        return ";".join(signature_parts)

    def split_dataset(self, pairs: List[Dict], train_ratio: float = 0.8, val_ratio: float = 0.1) -> Dict[str, List[Dict]]:
        """分割数据集"""
        import random
        random.shuffle(pairs)

        total = len(pairs)
        train_size = int(total * train_ratio)
        val_size = int(total * val_ratio)

        # 更新split标记
        for i, pair in enumerate(pairs):
            if i < train_size:
                pair["dataset_split"] = "train"
            elif i < train_size + val_size:
                pair["dataset_split"] = "val"
            else:
                pair["dataset_split"] = "test"

        return {
            "train": pairs[:train_size],
            "val": pairs[train_size:train_size + val_size],
            "test": pairs[train_size + val_size:]
        }

    async def generate_preference_pairs(self, host: str = None, goal: str = None,
                                      start_date: str = None, end_date: str = None) -> Dict[str, List[Dict]]:
        """生成偏好对的主函数"""
        logger.info(f"开始生成偏好对: host={host}, goal={goal}")

        # 获取历史数据
        histories = await self.get_historical_data(host, goal, start_date, end_date)
        self.stats["total_histories"] = len(histories)
        logger.info(f"获取到 {len(histories)} 条历史记录")

        # 按指纹分组
        fingerprint_groups = self.group_by_fingerprint(histories)
        self.stats["valid_fingerprints"] = len(fingerprint_groups)
        logger.info(f"分组到 {len(fingerprint_groups)} 个指纹")

        # 为每个组生成偏好对
        all_pairs = []
        for fp, group in fingerprint_groups.items():
            if len(group) < 2:  # 至少需要2个记录才能生成偏好对
                continue

            pairs = self.generate_pairs_for_group(group)
            all_pairs.extend(pairs)
            logger.info(f"指纹 {fp[:8]}... 生成 {len(pairs)} 个偏好对")

        # 过滤和去重
        filtered_pairs = self.filter_and_deduplicate(all_pairs)

        # 分割数据集
        dataset_splits = self.split_dataset(filtered_pairs)

        logger.info(f"最终生成偏好对: train={len(dataset_splits['train'])}, val={len(dataset_splits['val'])}, test={len(dataset_splits['test'])}")

        return dataset_splits

    def save_to_jsonl(self, pairs: List[Dict], output_path: str):
        """保存偏好对到JSONL文件"""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            for pair in pairs:
                f.write(json.dumps(pair, ensure_ascii=False, default=str) + '\n')

        logger.info(f"保存 {len(pairs)} 个偏好对到 {output_path}")

    def print_statistics(self):
        """打印统计信息"""
        print("\n" + "="*60)
        print("偏好对生成统计")
        print("="*60)
        print(f"总历史记录数: {self.stats['total_histories']}")
        print(f"有效指纹数: {self.stats['valid_fingerprints']}")
        print(f"生成偏好对数: {self.stats['generated_pairs']}")
        print(f"去重数量: {self.stats['duplicate_pairs']}")
        print(f"最小奖励差值: {self.min_reward_margin}")
        print(f"每指纹最大对数: {self.max_pairs_per_fingerprint}")

async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="生成DPO训练的偏好对数据")
    parser.add_argument("--host", help="目标域名过滤")
    parser.add_argument("--goal", help="目标任务过滤")
    parser.add_argument("--start-date", help="开始日期 (YYYY-MM-DD)")
    parser.add_argument("--end-date", help="结束日期 (YYYY-MM-DD)")
    parser.add_argument("--output-dir", default="data/prefs", help="输出目录")
    parser.add_argument("--min-margin", type=float, default=0.8, help="最小奖励差值")
    parser.add_argument("--max-pairs", type=int, default=10, help="每指纹最大偏好对数")

    args = parser.parse_args()

    # 创建生成器
    generator = PreferencePairGenerator(
        min_reward_margin=args.min_margin,
        max_pairs_per_fingerprint=args.max_pairs
    )

    # 生成偏好对
    dataset_splits = await generator.generate_preference_pairs(
        host=args.host,
        goal=args.goal,
        start_date=args.start_date,
        end_date=args.end_date
    )

    # 保存到文件
    for split, pairs in dataset_splits.items():
        output_path = f"{args.output_dir}/{split}.jsonl"
        generator.save_to_jsonl(pairs, output_path)

    # 打印统计
    generator.print_statistics()

    print(f"\n✅ 偏好对生成完成！输出目录: {args.output_dir}")

if __name__ == "__main__":
    asyncio.run(main())