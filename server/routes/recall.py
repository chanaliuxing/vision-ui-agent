"""
Sprint H: Recall API路由
提供轨迹回忆的HTTP接口
"""
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import logging
from datetime import datetime

from ..services.recall import recall_service, RecallQuery, RecallResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recall", tags=["recall"])


# Pydantic模型
class RecallRequest(BaseModel):
    """回忆请求模型"""
    fingerprint: Optional[str] = Field(None, description="页面指纹")
    trajectory: Optional[List[str]] = Field(None, description="动作轨迹序列")
    host: Optional[str] = Field(None, description="目标网站域名")
    goal_hash: Optional[str] = Field(None, description="目标哈希")
    page_state_meta: Optional[Dict[str, Any]] = Field(None, description="页面状态元数据")
    candidate_action_sigs: Optional[List[str]] = Field(None, description="候选动作签名")
    action_sigs: Optional[List[str]] = Field(None, description="实际动作签名")
    k: int = Field(5, ge=1, le=50, description="返回结果数量")
    min_similarity: float = Field(0.7, ge=0.0, le=1.0, description="最小相似度阈值")
    provider: Optional[str] = Field(None, description="嵌入提供商")

    class Config:
        json_schema_extra = {
            "example": {
                "fingerprint": "8a9c2f...",
                "host": "ca.indeed.com",
                "page_state_meta": {
                    "left_ratio": 0.33,
                    "right_ratio": 0.67,
                    "dpr": 1.25
                },
                "trajectory": ["wheel@leftPane(-600)", "click@list[i]", "wait@quiet"],
                "k": 5,
                "min_similarity": 0.7
            }
        }


class RecallResponse(BaseModel):
    """回忆响应模型"""
    id: int
    host: str
    fingerprint: str
    page_state_meta: Dict[str, Any]
    candidate_action_sigs: List[str]
    action_sigs: List[str]
    reward: float
    success: bool
    fingerprint_similarity: float
    trajectory_similarity: float
    combined_similarity: float
    created_at: datetime

    class Config:
        json_schema_extra = {
            "example": {
                "id": 1,
                "host": "ca.indeed.com",
                "fingerprint": "8a9c2f...",
                "page_state_meta": {"left_ratio": 0.33, "right_ratio": 0.67, "dpr": 1.25},
                "candidate_action_sigs": ["wheel@leftPane(-600)", "click@list[i]", "wait@quiet"],
                "action_sigs": ["wheel@leftPane(-600)", "click@list[i]", "wait@quiet", "ext.extract"],
                "reward": 0.85,
                "success": True,
                "fingerprint_similarity": 0.92,
                "trajectory_similarity": 0.88,
                "combined_similarity": 0.90,
                "created_at": "2025-09-17T10:30:00Z"
            }
        }


class RecallStatsResponse(BaseModel):
    """回忆统计响应模型"""
    total_queries: int
    total_results: int
    avg_query_time: float

    class Config:
        json_schema_extra = {
            "example": {
                "total_queries": 150,
                "total_results": 432,
                "avg_query_time": 0.245
            }
        }


@router.post("/similar", response_model=List[RecallResponse])
async def recall_similar_trajectories(request: RecallRequest):
    """
    回忆相似轨迹

    根据提供的指纹、轨迹或其他特征，检索相似的历史成功轨迹。
    支持指纹相似度和轨迹相似度的组合检索。
    """
    try:
        # 转换为内部查询对象
        query = RecallQuery(
            fingerprint=request.fingerprint,
            trajectory=request.trajectory,
            host=request.host,
            goal_hash=request.goal_hash,
            page_state_meta=request.page_state_meta,
            candidate_action_sigs=request.candidate_action_sigs,
            action_sigs=request.action_sigs,
            k=request.k,
            min_similarity=request.min_similarity,
            provider=request.provider
        )

        # 执行回忆查询
        results = await recall_service.recall_similar_trajectories(query)

        # 转换为响应模型
        response = [
            RecallResponse(
                id=result.id,
                host=result.host,
                fingerprint=result.fingerprint,
                page_state_meta=result.page_state_meta,
                candidate_action_sigs=result.candidate_action_sigs,
                action_sigs=result.action_sigs,
                reward=result.reward,
                success=result.success,
                fingerprint_similarity=result.fingerprint_similarity,
                trajectory_similarity=result.trajectory_similarity,
                combined_similarity=result.combined_similarity,
                created_at=result.created_at
            )
            for result in results
        ]

        logger.info(f"Recalled {len(response)} similar trajectories")
        return response

    except Exception as e:
        logger.error(f"Recall API error: {e}")
        raise HTTPException(status_code=500, detail=f"回忆查询失败: {str(e)}")


@router.get("/by-fingerprint", response_model=List[RecallResponse])
async def recall_by_fingerprint(
    host: str = Query(..., description="目标网站域名"),
    fingerprint: str = Query(..., description="页面指纹"),
    k: int = Query(5, ge=1, le=50, description="返回结果数量"),
    provider: Optional[str] = Query(None, description="嵌入提供商")
):
    """
    基于指纹回忆相似轨迹

    使用页面指纹检索相似的历史成功轨迹。
    """
    try:
        results = await recall_service.recall_by_fingerprint(
            host=host,
            fingerprint=fingerprint,
            k=k,
            provider=provider
        )

        response = [
            RecallResponse(
                id=result.id,
                host=result.host,
                fingerprint=result.fingerprint,
                page_state_meta=result.page_state_meta,
                candidate_action_sigs=result.candidate_action_sigs,
                action_sigs=result.action_sigs,
                reward=result.reward,
                success=result.success,
                fingerprint_similarity=result.fingerprint_similarity,
                trajectory_similarity=result.trajectory_similarity,
                combined_similarity=result.combined_similarity,
                created_at=result.created_at
            )
            for result in results
        ]

        return response

    except Exception as e:
        logger.error(f"Fingerprint recall API error: {e}")
        raise HTTPException(status_code=500, detail=f"指纹回忆失败: {str(e)}")


@router.post("/by-trajectory", response_model=List[RecallResponse])
async def recall_by_trajectory(
    trajectory: List[str] = Body(..., description="动作轨迹序列"),
    host: Optional[str] = Body(None, description="目标网站域名"),
    k: int = Body(5, ge=1, le=50, description="返回结果数量"),
    provider: Optional[str] = Body(None, description="嵌入提供商")
):
    """
    基于轨迹回忆相似轨迹

    使用动作轨迹序列检索相似的历史成功轨迹。
    """
    try:
        results = await recall_service.recall_by_trajectory(
            trajectory=trajectory,
            host=host,
            k=k,
            provider=provider
        )

        response = [
            RecallResponse(
                id=result.id,
                host=result.host,
                fingerprint=result.fingerprint,
                page_state_meta=result.page_state_meta,
                candidate_action_sigs=result.candidate_action_sigs,
                action_sigs=result.action_sigs,
                reward=result.reward,
                success=result.success,
                fingerprint_similarity=result.fingerprint_similarity,
                trajectory_similarity=result.trajectory_similarity,
                combined_similarity=result.combined_similarity,
                created_at=result.created_at
            )
            for result in results
        ]

        return response

    except Exception as e:
        logger.error(f"Trajectory recall API error: {e}")
        raise HTTPException(status_code=500, detail=f"轨迹回忆失败: {str(e)}")


@router.get("/stats", response_model=RecallStatsResponse)
async def get_recall_stats():
    """
    获取回忆服务统计信息

    返回查询次数、结果数量、平均查询时间等统计数据。
    """
    try:
        stats = recall_service.get_stats()
        return RecallStatsResponse(**stats)

    except Exception as e:
        logger.error(f"Stats API error: {e}")
        raise HTTPException(status_code=500, detail=f"获取统计信息失败: {str(e)}")


@router.get("/health")
async def recall_health_check():
    """
    回忆服务健康检查

    检查回忆服务和相关依赖的状态。
    """
    try:
        # 检查数据库连接
        await recall_service.ensure_connection()

        # 检查嵌入服务
        from ..services.embeddings import embedding_service
        providers = embedding_service.get_available_providers()

        return {
            "status": "healthy",
            "database": "connected",
            "embedding_providers": len(providers),
            "available_providers": [p["provider"] for p in providers],
            "stats": recall_service.get_stats()
        }

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }