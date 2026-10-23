"""
Sprint H: 轨迹回忆服务
提供向量相似度检索，支持指纹和轨迹双重检索
"""
import logging
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import json
import time
from datetime import datetime, timedelta

from .embeddings import embedding_service, build_fingerprint_text, build_trajectory_text

logger = logging.getLogger(__name__)


@dataclass
class RecallQuery:
    """回忆查询参数"""
    fingerprint: Optional[str] = None
    trajectory: Optional[List[str]] = None
    host: Optional[str] = None
    goal_hash: Optional[str] = None
    page_state_meta: Optional[Dict] = None
    candidate_action_sigs: Optional[List[str]] = None
    action_sigs: Optional[List[str]] = None
    k: int = 5
    min_similarity: float = 0.7
    provider: Optional[str] = None


@dataclass
class RecallResult:
    """回忆结果"""
    id: int
    host: str
    fingerprint: str
    page_state_meta: Dict
    candidate_action_sigs: List[str]
    action_sigs: List[str]
    reward: float
    success: bool
    fingerprint_similarity: float
    trajectory_similarity: float
    combined_similarity: float
    created_at: datetime


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

    async def fetch_many(self, query: str, params: List = None) -> List[Dict]:
        """查询多行"""
        logger.debug(f"Fetching: {query[:100]}...")

        # 模拟返回历史数据
        if "SELECT id, host, fingerprint" in query:
            return [
                {
                    "id": 1,
                    "host": "ca.indeed.com",
                    "fingerprint": "8a9c2f...",
                    "page_state_meta": {"left_ratio": 0.33, "right_ratio": 0.67, "dpr": 1.25},
                    "candidate_action_sigs": ["wheel@leftPane(-600)", "click@list[i]", "wait@quiet"],
                    "action_sigs": ["wheel@leftPane(-600)", "click@list[i]", "wait@quiet", "ext.extract"],
                    "reward": 0.85,
                    "success": True,
                    "fingerprint_embed": [0.1] * 1024,  # 模拟嵌入向量
                    "trajectory_embed": [0.2] * 1024,
                    "created_at": datetime.now() - timedelta(days=5)
                },
                {
                    "id": 2,
                    "host": "www.xiaohongshu.com",
                    "fingerprint": "9b8d3e...",
                    "page_state_meta": {"left_ratio": 0.25, "right_ratio": 0.75, "dpr": 2.0},
                    "candidate_action_sigs": ["scroll@comments", "click@expand"],
                    "action_sigs": ["scroll@comments", "click@expand", "wait@load"],
                    "reward": 0.92,
                    "success": True,
                    "fingerprint_embed": [0.3] * 1024,
                    "trajectory_embed": [0.4] * 1024,
                    "created_at": datetime.now() - timedelta(days=3)
                },
                {
                    "id": 3,
                    "host": "ca.indeed.com",
                    "fingerprint": "7f6e5d...",
                    "page_state_meta": {"left_ratio": 0.35, "right_ratio": 0.65, "dpr": 1.0},
                    "candidate_action_sigs": ["click@search", "type@query"],
                    "action_sigs": ["click@search", "type@query", "click@submit"],
                    "reward": 0.78,
                    "success": True,
                    "fingerprint_embed": [0.5] * 1024,
                    "trajectory_embed": [0.6] * 1024,
                    "created_at": datetime.now() - timedelta(days=1)
                }
            ]
        return []


class RecallService:
    """轨迹回忆服务"""

    def __init__(self, db: DatabaseConnection = None):
        self.db = db or DatabaseConnection()
        self.stats = {
            "total_queries": 0,
            "total_results": 0,
            "avg_query_time": 0.0
        }

    async def ensure_connection(self):
        """确保数据库连接"""
        if not self.db.connection:
            await self.db.connect()

    def _calculate_cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """计算余弦相似度"""
        import math

        # 计算点积
        dot_product = sum(a * b for a, b in zip(vec1, vec2))

        # 计算向量长度
        magnitude1 = math.sqrt(sum(a * a for a in vec1))
        magnitude2 = math.sqrt(sum(a * a for a in vec2))

        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0

        return dot_product / (magnitude1 * magnitude2)

    async def _get_candidates_from_db(self, host: str = None, limit: int = 100) -> List[Dict]:
        """从数据库获取候选历史记录"""
        await self.ensure_connection()

        query = """
        SELECT id, host, fingerprint, page_state_meta,
               candidate_action_sigs, action_sigs, reward, success,
               fingerprint_embed, trajectory_embed, created_at
        FROM plans_history
        WHERE fingerprint_embed IS NOT NULL
          AND trajectory_embed IS NOT NULL
          AND success = TRUE
        """

        params = []
        if host:
            query += " AND host = $1"
            params.append(host)

        query += " ORDER BY reward DESC, created_at DESC LIMIT $" + str(len(params) + 1)
        params.append(limit)

        return await self.db.fetch_many(query, params)

    async def recall_similar_trajectories(self, query: RecallQuery) -> List[RecallResult]:
        """回忆相似轨迹"""
        start_time = time.time()

        try:
            # 1. 构建查询嵌入向量
            query_fp_text = None
            query_traj_text = None
            query_fp_embed = None
            query_traj_embed = None

            if query.fingerprint or query.page_state_meta:
                # 构建指纹文本
                fp_row = {
                    "host": query.host or "",
                    "fingerprint": query.fingerprint or "",
                    "page_state_meta": query.page_state_meta or {}
                }
                query_fp_text = build_fingerprint_text(fp_row)

            if query.trajectory or query.candidate_action_sigs or query.action_sigs:
                # 构建轨迹文本
                traj_row = {
                    "candidate_action_sigs": query.candidate_action_sigs or query.action_sigs or query.trajectory,
                    "action_sigs": query.action_sigs or query.trajectory or []
                }
                query_traj_text = build_trajectory_text(traj_row)

            # 2. 生成查询嵌入
            if query_fp_text:
                query_fp_embed = await embedding_service.embed_single(
                    query_fp_text, query.provider, 1024
                )

            if query_traj_text:
                query_traj_embed = await embedding_service.embed_single(
                    query_traj_text, query.provider, 1024
                )

            if not query_fp_embed and not query_traj_embed:
                logger.warning("No valid query embeddings generated")
                return []

            # 3. 获取候选记录
            candidates = await self._get_candidates_from_db(query.host, limit=200)

            if not candidates:
                logger.info("No candidate trajectories found")
                return []

            # 4. 计算相似度
            results = []
            for candidate in candidates:
                fp_sim = 0.0
                traj_sim = 0.0

                # 指纹相似度
                if query_fp_embed and candidate.get("fingerprint_embed"):
                    fp_sim = self._calculate_cosine_similarity(
                        query_fp_embed, candidate["fingerprint_embed"]
                    )

                # 轨迹相似度
                if query_traj_embed and candidate.get("trajectory_embed"):
                    traj_sim = self._calculate_cosine_similarity(
                        query_traj_embed, candidate["trajectory_embed"]
                    )

                # 组合相似度（加权平均）
                if query_fp_embed and query_traj_embed:
                    combined_sim = 0.4 * fp_sim + 0.6 * traj_sim  # 轨迹权重更高
                elif query_fp_embed:
                    combined_sim = fp_sim
                elif query_traj_embed:
                    combined_sim = traj_sim
                else:
                    combined_sim = 0.0

                # 过滤低相似度结果
                if combined_sim >= query.min_similarity:
                    result = RecallResult(
                        id=candidate["id"],
                        host=candidate["host"],
                        fingerprint=candidate["fingerprint"],
                        page_state_meta=candidate["page_state_meta"] or {},
                        candidate_action_sigs=candidate["candidate_action_sigs"] or [],
                        action_sigs=candidate["action_sigs"] or [],
                        reward=candidate["reward"],
                        success=candidate["success"],
                        fingerprint_similarity=fp_sim,
                        trajectory_similarity=traj_sim,
                        combined_similarity=combined_sim,
                        created_at=candidate["created_at"]
                    )
                    results.append(result)

            # 5. 排序并限制结果
            results.sort(key=lambda x: x.combined_similarity, reverse=True)
            final_results = results[:query.k]

            # 6. 更新统计
            query_time = time.time() - start_time
            self.stats["total_queries"] += 1
            self.stats["total_results"] += len(final_results)
            self.stats["avg_query_time"] = (
                (self.stats["avg_query_time"] * (self.stats["total_queries"] - 1) + query_time) /
                self.stats["total_queries"]
            )

            logger.info(f"Recall query completed: {len(final_results)} results in {query_time:.3f}s")
            return final_results

        except Exception as e:
            logger.error(f"Recall query failed: {e}")
            raise

    async def recall_by_fingerprint(self, host: str, fingerprint: str,
                                   page_state_meta: Dict = None,
                                   k: int = 5, provider: str = None) -> List[RecallResult]:
        """基于指纹的回忆"""
        query = RecallQuery(
            host=host,
            fingerprint=fingerprint,
            page_state_meta=page_state_meta,
            k=k,
            provider=provider
        )
        return await self.recall_similar_trajectories(query)

    async def recall_by_trajectory(self, trajectory: List[str],
                                  host: str = None, k: int = 5,
                                  provider: str = None) -> List[RecallResult]:
        """基于轨迹的回忆"""
        query = RecallQuery(
            trajectory=trajectory,
            host=host,
            k=k,
            provider=provider
        )
        return await self.recall_similar_trajectories(query)

    def get_stats(self) -> Dict[str, Any]:
        """获取服务统计"""
        return self.stats.copy()


# 全局服务实例
recall_service = RecallService()


# 便利函数
async def recall_similar(fingerprint: str = None, trajectory: List[str] = None,
                        host: str = None, k: int = 5,
                        provider: str = None) -> List[RecallResult]:
    """便利函数：回忆相似轨迹"""
    if fingerprint:
        return await recall_service.recall_by_fingerprint(host, fingerprint, k=k, provider=provider)
    elif trajectory:
        return await recall_service.recall_by_trajectory(trajectory, host=host, k=k, provider=provider)
    else:
        raise ValueError("Must provide either fingerprint or trajectory")


# 测试函数
async def test_recall_service():
    """测试回忆服务"""
    try:
        # 测试指纹回忆
        fp_results = await recall_service.recall_by_fingerprint(
            host="ca.indeed.com",
            fingerprint="8a9c2f...",
            page_state_meta={"left_ratio": 0.33, "right_ratio": 0.67, "dpr": 1.25}
        )
        print(f"Fingerprint recall: {len(fp_results)} results")

        # 测试轨迹回忆
        traj_results = await recall_service.recall_by_trajectory(
            trajectory=["wheel@leftPane(-600)", "click@list[i]", "wait@quiet"],
            host="ca.indeed.com"
        )
        print(f"Trajectory recall: {len(traj_results)} results")

        # 显示统计
        stats = recall_service.get_stats()
        print(f"Service stats: {stats}")

        return True

    except Exception as e:
        print(f"Recall test failed: {e}")
        return False


if __name__ == "__main__":
    asyncio.run(test_recall_service())