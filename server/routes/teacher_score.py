"""
Sprint I: Teacher评分服务 (RLAIF)
提供AI助教模型对候选计划的评分和偏好排序
"""

import asyncio
import logging
import time
import hashlib
import json
from typing import List, Dict, Any, Optional, Tuple
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
import aiohttp

logger = logging.getLogger(__name__)

router = APIRouter()

class CandidatePlan(BaseModel):
    """候选计划模型"""
    plan_id: str
    steps: List[Dict[str, Any]]
    metadata: Optional[Dict[str, Any]] = None

class TeacherScoreRequest(BaseModel):
    """Teacher评分请求"""
    context: Dict[str, Any] = Field(..., description="评分上下文")
    candidates: List[CandidatePlan] = Field(..., description="候选计划列表")
    teacher_config: Optional[Dict[str, str]] = Field(default=None, description="Teacher配置")

class TeacherScoreResponse(BaseModel):
    """Teacher评分响应"""
    scores: List[float] = Field(..., description="各候选的评分(0-1)")
    preference_ranking: List[int] = Field(..., description="偏好排序(索引)")
    rationales: List[str] = Field(..., description="评分理由")
    confidence_score: float = Field(..., description="整体置信度")
    teacher_info: Dict[str, str] = Field(..., description="Teacher信息")

class TeacherService:
    """Teacher评分服务"""

    def __init__(self):
        self.cache = {}  # 简单内存缓存
        self.rubric = self.load_scoring_rubric()

    def load_scoring_rubric(self) -> Dict[str, Any]:
        """加载评分标准"""
        return {
            "criteria": {
                "security": {
                    "weight": 0.25,
                    "description": "保持域名与容器边界，无越权动作"
                },
                "efficiency": {
                    "weight": 0.20,
                    "description": "步数、等待、滚动成本"
                },
                "reliability": {
                    "weight": 0.25,
                    "description": "关键按钮可见性和可点击概率"
                },
                "robustness": {
                    "weight": 0.20,
                    "description": "抗动态波动能力(wait_quiet/视区滚动)"
                },
                "compliance": {
                    "weight": 0.10,
                    "description": "是否采纳过去反思建议"
                }
            },
            "score_range": [0.0, 1.0],
            "preference_threshold": 0.1  # 最小偏好差异
        }

    def generate_cache_key(self, context: Dict, candidates: List[CandidatePlan]) -> str:
        """生成缓存键"""
        context_str = json.dumps(context, sort_keys=True)
        candidates_str = json.dumps([
            {"steps": c.steps, "metadata": c.metadata}
            for c in candidates
        ], sort_keys=True)

        combined = f"{context_str}|{candidates_str}"
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    async def score_candidates(self, request: TeacherScoreRequest) -> TeacherScoreResponse:
        """为候选计划评分"""
        # 检查缓存
        cache_key = self.generate_cache_key(request.context, request.candidates)
        if cache_key in self.cache:
            logger.info(f"Cache hit for scoring request: {cache_key}")
            cached_result = self.cache[cache_key]
            cached_result["teacher_info"]["cache_hit"] = True
            return TeacherScoreResponse(**cached_result)

        # 获取Teacher配置
        teacher_config = request.teacher_config or {
            "provider": "claude-3.5",
            "model": "claude-3-5-sonnet-20241022"
        }

        # 执行评分
        try:
            scores, rationales, confidence = await self._score_with_llm(
                request.context,
                request.candidates,
                teacher_config
            )

            # 生成偏好排序
            preference_ranking = self._generate_preference_ranking(scores)

            result = {
                "scores": scores,
                "preference_ranking": preference_ranking,
                "rationales": rationales,
                "confidence_score": confidence,
                "teacher_info": {
                    "provider": teacher_config["provider"],
                    "model": teacher_config["model"],
                    "version": "1.0",
                    "cache_hit": False
                }
            }

            # 缓存结果
            self.cache[cache_key] = result

            return TeacherScoreResponse(**result)

        except Exception as e:
            logger.error(f"Teacher scoring failed: {e}")
            raise HTTPException(status_code=500, detail=f"Scoring failed: {str(e)}")

    async def _score_with_llm(self, context: Dict, candidates: List[CandidatePlan],
                             config: Dict) -> Tuple[List[float], List[str], float]:
        """使用LLM进行评分"""
        # 构建评分提示
        prompt = self._build_scoring_prompt(context, candidates)

        # 调用LLM
        response = await self._call_teacher_llm(prompt, config)

        # 解析响应
        scores, rationales, confidence = self._parse_llm_response(response, len(candidates))

        return scores, rationales, confidence

    def _build_scoring_prompt(self, context: Dict, candidates: List[CandidatePlan]) -> str:
        """构建评分提示"""
        host = context.get("host", "unknown")
        goal = context.get("goal_hash", "unknown")
        page_meta = context.get("page_state_meta", {})

        prompt = f"""你是UI自动化专家，需要对候选的自动化计划进行评分和排序。

**任务上下文:**
- 目标网站: {host}
- 执行目标: {goal}
- 页面布局: left_ratio={page_meta.get('left_ratio', 0.5)}, right_ratio={page_meta.get('right_ratio', 0.5)}

**评分标准 (总分1.0):**
1. 安全性 (0.25): 是否保持在目标域名内，无越权操作
2. 效率性 (0.20): 步骤数量、等待时间、滚动成本
3. 可靠性 (0.25): 目标元素的可见性和可点击概率
4. 鲁棒性 (0.20): 对页面动态变化的适应能力
5. 合规性 (0.10): 是否遵循最佳实践

**候选计划:**
"""

        for i, candidate in enumerate(candidates):
            prompt += f"\n候选 {i+1} (ID: {candidate.plan_id}):\n"
            for j, step in enumerate(candidate.steps[:5]):  # 限制显示步骤
                action = step.get("do", "unknown")
                args = step.get("args", {})
                prompt += f"  {j+1}. {action}"

                if "bbox" in args:
                    prompt += " -> 点击目标元素"
                elif "at_bbox" in args and "amount" in args:
                    prompt += f" -> 滚动 {args['amount']}px"
                elif "text_any_of" in args:
                    prompt += f" -> 查找按钮: {args['text_any_of']}"

                prompt += "\n"

        prompt += f"""
**要求输出JSON格式:**
{{
  "analysis": "总体分析",
  "scores": [候选1评分, 候选2评分, ...],  # 0.0-1.0范围
  "rationales": ["候选1评分理由", "候选2评分理由", ...],
  "confidence": 整体置信度  # 0.0-1.0范围
}}

请按照评分标准给出客观、详细的评分和理由。"""

        return prompt

    async def _call_teacher_llm(self, prompt: str, config: Dict) -> str:
        """调用Teacher LLM"""
        # 这里应该调用实际的LLM API
        # 为了演示，返回模拟响应

        await asyncio.sleep(0.5)  # 模拟API延迟

        # 模拟LLM响应
        mock_response = {
            "analysis": "分析了候选计划的安全性、效率性和可靠性",
            "scores": [0.85, 0.72, 0.68],  # 假设有3个候选
            "rationales": [
                "步骤序列合理，包含必要的等待和验证，安全性良好",
                "缺少等待步骤，可能在动态页面上失败",
                "步骤过于简单，可能遗漏关键操作"
            ],
            "confidence": 0.82
        }

        return json.dumps(mock_response, ensure_ascii=False)

    def _parse_llm_response(self, response: str, num_candidates: int) -> Tuple[List[float], List[str], float]:
        """解析LLM响应"""
        try:
            data = json.loads(response)

            scores = data.get("scores", [])
            rationales = data.get("rationales", [])
            confidence = data.get("confidence", 0.5)

            # 验证和填充
            while len(scores) < num_candidates:
                scores.append(0.5)  # 默认中等分数

            while len(rationales) < num_candidates:
                rationales.append("评分理由未提供")

            # 标准化分数到0-1范围
            scores = [max(0.0, min(1.0, float(s))) for s in scores[:num_candidates]]

            return scores, rationales[:num_candidates], max(0.0, min(1.0, float(confidence)))

        except Exception as e:
            logger.warning(f"Failed to parse LLM response: {e}")
            # 返回默认值
            default_scores = [0.5] * num_candidates
            default_rationales = ["解析失败，使用默认评分"] * num_candidates
            return default_scores, default_rationales, 0.3

    def _generate_preference_ranking(self, scores: List[float]) -> List[int]:
        """生成偏好排序"""
        # 按分数从高到低排序，返回原始索引
        indexed_scores = [(score, i) for i, score in enumerate(scores)]
        indexed_scores.sort(key=lambda x: x[0], reverse=True)

        return [i for _, i in indexed_scores]

    def get_statistics(self) -> Dict[str, Any]:
        """获取服务统计"""
        return {
            "cache_size": len(self.cache),
            "rubric_version": "1.0",
            "supported_providers": ["claude-3.5", "gpt-4o", "mock"],
            "scoring_criteria": list(self.rubric["criteria"].keys())
        }

# 全局服务实例
teacher_service = TeacherService()

@router.post("/teacher/score", response_model=TeacherScoreResponse)
async def score_candidates(request: TeacherScoreRequest):
    """
    对候选计划进行Teacher评分

    Args:
        request: 包含上下文和候选计划的评分请求

    Returns:
        包含分数、排序和理由的评分响应
    """
    if len(request.candidates) == 0:
        raise HTTPException(status_code=400, detail="At least one candidate required")

    if len(request.candidates) > 10:
        raise HTTPException(status_code=400, detail="Too many candidates (max 10)")

    start_time = time.time()

    try:
        result = await teacher_service.score_candidates(request)

        # 记录评分事件
        duration = time.time() - start_time
        logger.info(f"Teacher scoring completed: {len(request.candidates)} candidates, "
                   f"{duration:.2f}s, confidence={result.confidence_score:.2f}")

        return result

    except Exception as e:
        logger.error(f"Teacher scoring failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/teacher/stats")
async def get_teacher_stats():
    """获取Teacher服务统计信息"""
    return teacher_service.get_statistics()

@router.delete("/teacher/cache")
async def clear_teacher_cache():
    """清空Teacher评分缓存"""
    cache_size = len(teacher_service.cache)
    teacher_service.cache.clear()

    return {
        "message": f"Cache cleared, removed {cache_size} entries",
        "cache_size": 0
    }

@router.get("/teacher/rubric")
async def get_scoring_rubric():
    """获取评分标准"""
    return teacher_service.rubric

# 批量评分端点
@router.post("/teacher/batch_score")
async def batch_score_candidates(requests: List[TeacherScoreRequest]):
    """批量评分多个候选集合"""
    if len(requests) > 20:
        raise HTTPException(status_code=400, detail="Too many batch requests (max 20)")

    results = []
    start_time = time.time()

    for i, request in enumerate(requests):
        try:
            result = await teacher_service.score_candidates(request)
            results.append({
                "index": i,
                "success": True,
                "result": result
            })
        except Exception as e:
            logger.error(f"Batch scoring failed for request {i}: {e}")
            results.append({
                "index": i,
                "success": False,
                "error": str(e)
            })

    duration = time.time() - start_time
    successful = sum(1 for r in results if r["success"])

    logger.info(f"Batch scoring completed: {successful}/{len(requests)} successful, {duration:.2f}s")

    return {
        "total_requests": len(requests),
        "successful_requests": successful,
        "processing_time_seconds": duration,
        "results": results
    }

if __name__ == "__main__":
    # 测试代码
    import uvicorn
    from fastapi import FastAPI

    app = FastAPI(title="Teacher Scoring API")
    app.include_router(router)

    # 测试数据
    async def test_teacher_scoring():
        test_context = {
            "host": "ca.indeed.com",
            "goal_hash": "apply_job",
            "page_state_meta": {"left_ratio": 0.33, "right_ratio": 0.67}
        }

        test_candidates = [
            CandidatePlan(
                plan_id="plan_1",
                steps=[
                    {"do": "wheel_coordinates", "args": {"at_bbox": "@ps.panes.left.rect", "amount": -600}},
                    {"do": "click_coordinates", "args": {"bbox": "@ps.lists[0].itemRects[0]"}},
                    {"do": "wait_for", "args": {"until": {"type": "ext.wait_quiet"}}},
                    {"do": "ext.extract", "args": {"mode": "find_button_bbox", "text_any_of": ["Apply"]}}
                ]
            ),
            CandidatePlan(
                plan_id="plan_2",
                steps=[
                    {"do": "click_coordinates", "args": {"bbox": "@ps.lists[0].itemRects[1]"}},
                    {"do": "wait_for", "args": {"timeout": 3000}}
                ]
            )
        ]

        request = TeacherScoreRequest(
            context=test_context,
            candidates=test_candidates
        )

        result = await teacher_service.score_candidates(request)
        print("Teacher scoring result:", result)

    @app.on_event("startup")
    async def startup():
        await test_teacher_scoring()

    uvicorn.run(app, host="0.0.0.0", port=8004)