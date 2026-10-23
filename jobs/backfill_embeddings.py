#!/usr/bin/env python3
"""
Sprint H: 嵌入向量回填作业
对历史 plans_history 回填 fingerprint_embed / trajectory_embed
运行方式：python jobs/backfill_embeddings.py --since=30d --batch-size=50
"""
import os
import sys
import asyncio
import argparse
import logging
from pathlib import Path
from typing import List, Dict, Any
import time
from datetime import datetime, timedelta

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from server.services.embeddings import (
    embedding_service, build_fingerprint_text, build_trajectory_text
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DatabaseConnection:
    """数据库连接（简化实现）"""

    def __init__(self):
        self.connection = None

    async def connect(self):
        """连接数据库"""
        try:
            # 这里应该是真实的数据库连接
            # 例如：asyncpg.connect(os.getenv("DATABASE_URL"))
            logger.info("Connected to database (mock)")
            self.connection = "mock_connection"
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            raise

    async def execute(self, query: str, params: List = None):
        """执行SQL"""
        logger.debug(f"Executing: {query[:100]}...")
        # 模拟执行
        return []

    async def fetch_many(self, query: str, params: List = None) -> List[Dict]:
        """查询多行"""
        logger.debug(f"Fetching: {query[:100]}...")

        # 模拟返回数据
        if "SELECT id, host, fingerprint" in query:
            return [
                {
                    "id": 1,
                    "host": "ca.indeed.com",
                    "fingerprint": "8a9c2f...",
                    "page_state_meta": {"left_ratio": 0.33, "right_ratio": 0.67, "dpr": 1.25},
                    "candidate_action_sigs": ["wheel@leftPane(-600)", "click@list[i]", "wait@quiet"],
                    "action_sigs": ["wheel@leftPane(-600)", "click@list[i]", "wait@quiet", "ext.extract"]
                },
                {
                    "id": 2,
                    "host": "www.xiaohongshu.com",
                    "fingerprint": "9b8d3e...",
                    "page_state_meta": {"left_ratio": 0.25, "right_ratio": 0.75, "dpr": 2.0},
                    "candidate_action_sigs": ["scroll@comments", "click@expand"],
                    "action_sigs": ["scroll@comments", "click@expand", "wait@load"]
                }
            ]
        return []


class EmbeddingBackfiller:
    """嵌入向量回填器"""

    def __init__(self, db: DatabaseConnection):
        self.db = db
        self.stats = {
            "total_processed": 0,
            "successful_updates": 0,
            "failed_updates": 0,
            "start_time": None,
            "end_time": None
        }

    async def get_pending_rows(self, since: str, batch_size: int) -> List[Dict]:
        """获取需要回填的行"""
        query = """
        SELECT id, host, fingerprint, page_state_meta,
               candidate_action_sigs, action_sigs
        FROM plans_history
        WHERE created_at > (now() - $1::interval)
          AND (fingerprint_embed IS NULL OR trajectory_embed IS NULL)
        ORDER BY created_at DESC
        LIMIT $2
        """

        return await self.db.fetch_many(query, [since, batch_size])

    async def update_embeddings(self, rows: List[Dict],
                               fp_embeddings: List[List[float]],
                               traj_embeddings: List[List[float]]):
        """批量更新嵌入向量"""
        query = """
        UPDATE plans_history
        SET fingerprint_embed = $2, trajectory_embed = $3, updated_at = now()
        WHERE id = $1
        """

        for i, row in enumerate(rows):
            try:
                await self.db.execute(query, [
                    row["id"],
                    fp_embeddings[i],
                    traj_embeddings[i]
                ])
                self.stats["successful_updates"] += 1
                logger.debug(f"Updated embeddings for row {row['id']}")

            except Exception as e:
                logger.error(f"Failed to update row {row['id']}: {e}")
                self.stats["failed_updates"] += 1

    async def process_batch(self, since: str, batch_size: int, provider: str = None) -> int:
        """处理一批数据"""
        # 获取待处理的行
        rows = await self.get_pending_rows(since, batch_size)

        if not rows:
            logger.info("No more rows to process")
            return 0

        logger.info(f"Processing batch of {len(rows)} rows")

        # 构建文本
        fp_texts = [build_fingerprint_text(row) for row in rows]
        traj_texts = [build_trajectory_text(row) for row in rows]

        # 生成嵌入向量
        try:
            logger.info("Generating fingerprint embeddings...")
            fp_embeddings = await embedding_service.embed_batch(fp_texts, provider, 1024)

            logger.info("Generating trajectory embeddings...")
            traj_embeddings = await embedding_service.embed_batch(traj_texts, provider, 1024)

            # 更新数据库
            logger.info("Updating database...")
            await self.update_embeddings(rows, fp_embeddings, traj_embeddings)

            self.stats["total_processed"] += len(rows)
            return len(rows)

        except Exception as e:
            logger.error(f"Batch processing failed: {e}")
            self.stats["failed_updates"] += len(rows)
            return 0

    async def run_backfill(self, since: str = "30d", batch_size: int = 50,
                          provider: str = None, max_batches: int = None):
        """运行回填任务"""
        self.stats["start_time"] = datetime.now()
        logger.info(f"Starting embedding backfill: since={since}, batch_size={batch_size}")

        batches_processed = 0
        total_rows = 0

        try:
            while max_batches is None or batches_processed < max_batches:
                rows_processed = await self.process_batch(since, batch_size, provider)

                if rows_processed == 0:
                    break

                total_rows += rows_processed
                batches_processed += 1

                logger.info(f"Processed batch {batches_processed}: {rows_processed} rows")

                # 避免过载，批次间暂停
                await asyncio.sleep(1)

        except KeyboardInterrupt:
            logger.info("Backfill interrupted by user")
        except Exception as e:
            logger.error(f"Backfill failed: {e}")
            raise
        finally:
            self.stats["end_time"] = datetime.now()
            await self.print_summary()

    async def print_summary(self):
        """打印统计摘要"""
        duration = (self.stats["end_time"] - self.stats["start_time"]).total_seconds()

        logger.info("=" * 60)
        logger.info("EMBEDDING BACKFILL SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info(f"Total processed: {self.stats['total_processed']}")
        logger.info(f"Successful updates: {self.stats['successful_updates']}")
        logger.info(f"Failed updates: {self.stats['failed_updates']}")

        if self.stats["total_processed"] > 0:
            success_rate = (self.stats["successful_updates"] / self.stats["total_processed"]) * 100
            logger.info(f"Success rate: {success_rate:.1f}%")

            if duration > 0:
                rate = self.stats["total_processed"] / duration
                logger.info(f"Processing rate: {rate:.2f} rows/second")

        logger.info("=" * 60)


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Backfill embeddings for plans_history")
    parser.add_argument("--since", default="30d", help="Time range (e.g., '30d', '7d', '24h')")
    parser.add_argument("--batch-size", type=int, default=50, help="Batch size for processing")
    parser.add_argument("--provider", help="Embedding provider (openai, sentence_transformers, mock)")
    parser.add_argument("--max-batches", type=int, help="Maximum number of batches to process")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be processed without updating")

    args = parser.parse_args()

    # 连接数据库
    db = DatabaseConnection()
    await db.connect()

    # 显示可用的嵌入提供商
    providers = embedding_service.get_available_providers()
    logger.info(f"Available embedding providers: {[p['provider'] for p in providers]}")

    if args.provider:
        logger.info(f"Using specified provider: {args.provider}")
    else:
        default_provider = next((p for p in providers if p["is_default"]), None)
        if default_provider:
            logger.info(f"Using default provider: {default_provider['provider']}")

    if args.dry_run:
        logger.info("DRY RUN MODE - No updates will be made")
        # 在dry run模式下，可以显示要处理的数据概览
        backfiller = EmbeddingBackfiller(db)
        rows = await backfiller.get_pending_rows(args.since, args.batch_size)
        logger.info(f"Would process {len(rows)} rows in first batch")
        return

    # 运行回填
    backfiller = EmbeddingBackfiller(db)
    await backfiller.run_backfill(
        since=args.since,
        batch_size=args.batch_size,
        provider=args.provider,
        max_batches=args.max_batches
    )

    logger.info("Embedding backfill completed")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Backfill stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Backfill failed: {e}")
        sys.exit(1)