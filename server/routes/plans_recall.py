"""
Sprint H: Plans Recall API
GET /plans/recall - 相似轨迹检索API
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Query, HTTPException, Depends
from pydantic import BaseModel
import time

# 这里应该导入真实的数据库连接和服务
# from server.services.database import get_db_connection
from server.services.embeddings import embedding_service, build_fingerprint_text

logger = logging.getLogger(__name__)

router = APIRouter()

class RecallRequest(BaseModel):
    """检索请求模型"""
    fingerprint: Optional[str] = None
    host: Optional[str] = None
    goal_hash: Optional[str] = None
    k: int = 5
    min_reward: float = 0.5
    since: str = "90d"

class RecallRef(BaseModel):
    """检索引用模型"""
    history_id: int
    host: str
    goal_hash: Optional[str]
    avg_reward: float
    step_templates: List[str]
    meta: Dict[str, Any]
    similarity_score: Optional[float] = None

class RecallResponse(BaseModel):
    """检索响应模型"""
    k: int
    refs: List[RecallRef]
    query_time_ms: int
    method: str  # "vector" | "filter"

# 模拟数据库服务
class MockRecallService:
    """模拟回想服务 - 在实际项目中应该连接真实数据库"""

    def __init__(self):
        self.mock_data = [
            {
                "id": 1,
                "host": "ca.indeed.com",
                "goal_hash": "apply_job",
                "reward": 1.8,
                "candidate_action_sigs": ["wheel@leftPane(-600)", "click@list[i]", "wait@quiet", "ext.extract(apply)"],
                "page_state_meta": {"left_ratio": 0.33, "right_ratio": 0.67, "dpr": 1.25},
                "fingerprint": "fp_indeed_001",
                "fingerprint_embed": [0.1] * 1024,  # 模拟向量
                "created_at": "2024-09-12T10:00:00Z"
            },
            {
                "id": 2,
                "host": "ca.indeed.com",
                "goal_hash": "apply_job",
                "reward": 1.5,
                "candidate_action_sigs": ["scroll@down(300)", "click@list[i+1]", "wait@quiet", "click@apply"],
                "page_state_meta": {"left_ratio": 0.30, "right_ratio": 0.70, "dpr": 1.0},
                "fingerprint": "fp_indeed_002",
                "fingerprint_embed": [0.2] * 1024,
                "created_at": "2024-09-11T15:30:00Z"
            },
            {
                "id": 3,
                "host": "www.xiaohongshu.com",
                "goal_hash": "expand_comments",
                "reward": 1.2,
                "candidate_action_sigs": ["scroll@comments", "click@expand", "wait@load"],
                "page_state_meta": {"left_ratio": 0.0, "right_ratio": 1.0, "dpr": 2.0},
                "fingerprint": "fp_xhs_001",
                "fingerprint_embed": [0.3] * 1024,
                "created_at": "2024-09-10T09:15:00Z"
            }
        ]

    async def recall_by_vector(self, fingerprint: str, k: int, min_reward: float, since: str) -> List[Dict]:
        """基于向量相似度检索"""
        # 在实际实现中，这里应该：
        # 1. 将 fingerprint 转换为嵌入向量
        # 2. 在数据库中执行向量相似度查询
        # 3. 返回 Top-k 结果

        # 模拟：从现有数据中查找同host的记录，按reward排序
        filtered = [
            row for row in self.mock_data
            if row["reward"] >= min_reward
        ]

        # 模拟向量相似度排序（这里简单按reward排序）
        filtered.sort(key=lambda x: x["reward"], reverse=True)

        return filtered[:k]

    async def recall_by_filter(self, host: str, goal_hash: Optional[str], k: int,
                              min_reward: float, since: str) -> List[Dict]:
        """基于过滤条件检索"""
        filtered = [
            row for row in self.mock_data
            if (row["host"] == host and
                row["reward"] >= min_reward and
                (not goal_hash or row["goal_hash"] == goal_hash))
        ]

        # 按奖励排序
        filtered.sort(key=lambda x: x["reward"], reverse=True)

        return filtered[:k]

# 全局服务实例
recall_service = MockRecallService()

async def convert_to_recall_refs(rows: List[Dict], method: str) -> List[RecallRef]:
    """将数据库行转换为RecallRef对象"""
    refs = []

    for row in rows:
        ref = RecallRef(
            history_id=row["id"],
            host=row["host"],
            goal_hash=row.get("goal_hash"),
            avg_reward=row["reward"],
            step_templates=row.get("candidate_action_sigs", [])[:6],  # 限制长度
            meta=row.get("page_state_meta", {}),
            similarity_score=None  # 在向量检索时可以添加相似度分数
        )
        refs.append(ref)

    return refs

@router.get("/plans/recall", response_model=RecallResponse)
async def recall_similar_plans(
    fingerprint: Optional[str] = Query(None, description="指纹字符串（优先使用）"),
    host: Optional[str] = Query(None, description="目标域名"),
    goal_hash: Optional[str] = Query(None, description="目标哈希"),
    k: int = Query(5, ge=1, le=20, description="返回的引用数量"),
    min_reward: float = Query(0.5, ge=0.0, le=2.0, description="最小奖励阈值"),
    since: str = Query("90d", description="时间范围"),
):
    """
    检索相似的历史轨迹

    查询逻辑：
    1. 如果提供了 fingerprint，使用向量相似度检索
    2. 否则根据 host + goal_hash 进行过滤检索
    3. 返回 Top-k 成功轨迹摘要
    """
    start_time = time.time()

    # 验证参数
    if not fingerprint and not host:
        raise HTTPException(
            status_code=400,
            detail="Either 'fingerprint' or 'host' parameter is required"
        )

    try:
        if fingerprint:
            # 向量检索路径
            logger.info(f"Vector recall for fingerprint: {fingerprint[:20]}...")
            rows = await recall_service.recall_by_vector(
                fingerprint=fingerprint,
                k=k,
                min_reward=min_reward,
                since=since
            )
            method = "vector"

        else:
            # 过滤检索路径
            logger.info(f"Filter recall for host: {host}, goal: {goal_hash}")
            rows = await recall_service.recall_by_filter(
                host=host,
                goal_hash=goal_hash,
                k=k,
                min_reward=min_reward,
                since=since
            )
            method = "filter"

        # 转换为响应格式
        refs = await convert_to_recall_refs(rows, method)

        query_time = int((time.time() - start_time) * 1000)

        logger.info(f"Recall completed: {len(refs)} refs, {query_time}ms, method={method}")

        return RecallResponse(
            k=len(refs),
            refs=refs,
            query_time_ms=query_time,
            method=method
        )

    except Exception as e:
        logger.error(f"Recall failed: {e}")
        raise HTTPException(status_code=500, detail=f"Recall failed: {str(e)}")

@router.post("/plans/reflect")
async def create_reflection(
    history_id: int,
    critique: str,
    suggestions: Optional[Dict[str, Any]] = None,
    reward_before: Optional[float] = None,
    tags: Optional[List[str]] = None
):
    """
    创建计划反思记录

    Args:
        history_id: 关联的历史记录ID
        critique: 反思文本
        suggestions: 结构化建议
        reward_before: 反思前的奖励值
        tags: 标签（如 'auto', 'manual'）
    """
    try:
        # 在实际实现中，这里应该插入到 plan_reflections 表
        reflection_data = {
            "history_id": history_id,
            "critique": critique,
            "suggestions": suggestions or {},
            "reward_before": reward_before,
            "tags": tags or ["auto"],
            "created_at": time.time()
        }

        logger.info(f"Created reflection for history_id {history_id}: {critique[:50]}...")

        # 模拟返回插入的ID
        return {
            "id": 12345,
            "history_id": history_id,
            "created_at": reflection_data["created_at"]
        }

    except Exception as e:
        logger.error(f"Failed to create reflection: {e}")
        raise HTTPException(status_code=500, detail=f"Reflection creation failed: {str(e)}")

# 实际项目中的数据库查询示例
"""
async def vector_similarity_query(fingerprint_embed: List[float], k: int, min_reward: float, since: str):
    query = '''
    WITH seed AS (
        SELECT $1::vector AS query_vec
    )
    SELECT h.id, h.host, h.goal_hash, h.reward, h.candidate_action_sigs, h.page_state_meta,
           h.fingerprint_embed <#> seed.query_vec AS similarity_score
    FROM plans_history h, seed
    WHERE h.reward >= $2
      AND h.created_at > (now() - $3::interval)
      AND h.fingerprint_embed IS NOT NULL
    ORDER BY h.fingerprint_embed <#> seed.query_vec
    LIMIT $4
    '''

    return await db.fetch(query, fingerprint_embed, min_reward, since, k)

async def filter_query(host: str, goal_hash: Optional[str], k: int, min_reward: float, since: str):
    query = '''
    SELECT id, host, goal_hash, reward, candidate_action_sigs, page_state_meta
    FROM plans_history
    WHERE host = $1
      AND ($2::text IS NULL OR goal_hash = $2)
      AND reward >= $3
      AND created_at > (now() - $4::interval)
    ORDER BY reward DESC
    LIMIT $5
    '''

    return await db.fetch(query, host, goal_hash, min_reward, since, k)
"""

# 健康检查端点
@router.get("/plans/recall/health")
async def health_check():
    """健康检查"""
    try:
        # 检查嵌入服务状态
        providers = embedding_service.get_available_providers()

        return {
            "status": "healthy",
            "embedding_providers": len(providers),
            "default_provider": next((p["provider"] for p in providers if p["is_default"]), None)
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unhealthy")

if __name__ == "__main__":
    # 测试代码
    import uvicorn
    from fastapi import FastAPI

    app = FastAPI(title="Plans Recall API")
    app.include_router(router)

    uvicorn.run(app, host="0.0.0.0", port=8003)