"""
Sprint I: Planner版本管理和A/B测试部署系统
"""

import asyncio
import logging
import time
import json
import os
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()

# 模型定义
class PlannerVersionCreate(BaseModel):
    """创建Planner版本"""
    name: str = Field(..., description="版本名称")
    version: str = Field(..., description="版本号")
    type: str = Field(..., description="类型: prompt | lora | fine_tuned")
    base_provider: str = Field(..., description="基础提供商")
    base_model: str = Field(..., description="基础模型")
    model_path: Optional[str] = Field(None, description="模型路径")
    config: Optional[Dict[str, Any]] = Field(None, description="配置参数")
    prompt_template: Optional[str] = Field(None, description="Prompt模板")
    notes: Optional[str] = Field(None, description="说明")

class PlannerVersionResponse(BaseModel):
    """Planner版本响应"""
    id: int
    name: str
    version: str
    type: str
    base_provider: str
    base_model: str
    status: str
    created_at: datetime
    deployed_at: Optional[datetime]
    training_metrics: Optional[Dict[str, Any]]
    eval_metrics: Optional[Dict[str, Any]]

class ABAssignmentCreate(BaseModel):
    """创建A/B分配"""
    host: str = Field(..., description="目标域名")
    strategy: str = Field(..., description="策略名称")
    planner_version_id: int = Field(..., description="Planner版本ID")
    traffic_pct: int = Field(20, ge=1, le=100, description="流量百分比")
    user_filters: Optional[Dict[str, Any]] = Field(None, description="用户过滤条件")
    device_filters: Optional[Dict[str, Any]] = Field(None, description="设备过滤条件")
    failure_threshold: float = Field(0.1, description="失败率阈值")
    cost_threshold: float = Field(1.3, description="成本阈值倍数")

class ABAssignmentResponse(BaseModel):
    """A/B分配响应"""
    id: int
    host: str
    strategy: str
    planner_version_id: int
    traffic_pct: int
    enabled: bool
    failure_threshold: float
    cost_threshold: float
    created_at: datetime
    updated_at: datetime

class DeploymentStatus(BaseModel):
    """部署状态"""
    version_id: int
    version_name: str
    status: str
    traffic_pct: int
    current_metrics: Dict[str, Any]
    health_status: str

class PlannerDeploymentService:
    """Planner部署服务"""

    def __init__(self):
        self.versions_db = {}  # 模拟版本数据库
        self.assignments_db = {}  # 模拟分配数据库
        self.performance_cache = {}  # 性能数据缓存
        self._initialize_mock_data()

    def _initialize_mock_data(self):
        """初始化模拟数据"""
        # 默认版本
        self.versions_db = {
            1: {
                "id": 1,
                "name": "baseline_agentq",
                "version": "1.0.0",
                "type": "prompt",
                "base_provider": "claude-3.5",
                "base_model": "claude-3-5-sonnet-20241022",
                "status": "prod",
                "created_at": datetime.now() - timedelta(days=30),
                "deployed_at": datetime.now() - timedelta(days=25),
                "eval_metrics": {"success_rate": 0.75, "avg_steps": 4.2, "avg_tokens": 120}
            },
            2: {
                "id": 2,
                "name": "baseline_mcts",
                "version": "1.0.0",
                "type": "prompt",
                "base_provider": "gpt-4o",
                "base_model": "gpt-4o-mini",
                "status": "staging",
                "created_at": datetime.now() - timedelta(days=20),
                "deployed_at": None,
                "eval_metrics": {"success_rate": 0.72, "avg_steps": 4.8, "avg_tokens": 135}
            }
        }

        # 默认分配
        self.assignments_db = {
            1: {
                "id": 1,
                "host": "ca.indeed.com",
                "strategy": "agentq",
                "planner_version_id": 1,
                "traffic_pct": 80,
                "enabled": True,
                "failure_threshold": 0.1,
                "cost_threshold": 1.3,
                "created_at": datetime.now() - timedelta(days=25),
                "updated_at": datetime.now() - timedelta(days=25)
            }
        }

    async def create_planner_version(self, version_data: PlannerVersionCreate) -> PlannerVersionResponse:
        """创建新的Planner版本"""
        # 检查名称是否已存在
        for v in self.versions_db.values():
            if v["name"] == version_data.name:
                raise HTTPException(status_code=400, detail=f"Version name '{version_data.name}' already exists")

        # 生成新ID
        new_id = max(self.versions_db.keys()) + 1 if self.versions_db else 1

        # 创建版本记录
        version_record = {
            "id": new_id,
            "name": version_data.name,
            "version": version_data.version,
            "type": version_data.type,
            "base_provider": version_data.base_provider,
            "base_model": version_data.base_model,
            "model_path": version_data.model_path,
            "config": version_data.config or {},
            "prompt_template": version_data.prompt_template,
            "status": "training",  # 新版本从training状态开始
            "notes": version_data.notes,
            "created_at": datetime.now(),
            "deployed_at": None,
            "training_metrics": None,
            "eval_metrics": None
        }

        self.versions_db[new_id] = version_record

        logger.info(f"Created planner version: {version_data.name} (ID: {new_id})")

        return PlannerVersionResponse(**version_record)

    async def update_version_status(self, version_id: int, status: str, metrics: Dict[str, Any] = None) -> PlannerVersionResponse:
        """更新版本状态"""
        if version_id not in self.versions_db:
            raise HTTPException(status_code=404, detail="Version not found")

        valid_statuses = ["training", "staging", "prod", "deprecated", "rollback"]
        if status not in valid_statuses:
            raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")

        version = self.versions_db[version_id]
        old_status = version["status"]
        version["status"] = status

        # 更新部署时间
        if status == "prod" and old_status != "prod":
            version["deployed_at"] = datetime.now()

        # 更新指标
        if metrics:
            if status in ["staging", "prod"]:
                version["eval_metrics"] = metrics
            elif status == "training":
                version["training_metrics"] = metrics

        logger.info(f"Updated version {version_id} status: {old_status} -> {status}")

        return PlannerVersionResponse(**version)

    async def create_ab_assignment(self, assignment_data: ABAssignmentCreate) -> ABAssignmentResponse:
        """创建A/B分配"""
        # 验证版本存在
        if assignment_data.planner_version_id not in self.versions_db:
            raise HTTPException(status_code=404, detail="Planner version not found")

        # 验证版本状态
        version = self.versions_db[assignment_data.planner_version_id]
        if version["status"] not in ["staging", "prod"]:
            raise HTTPException(status_code=400, detail="Version must be in staging or prod status")

        # 检查流量分配冲突
        await self._validate_traffic_allocation(assignment_data.host, assignment_data.strategy, assignment_data.traffic_pct)

        # 生成新ID
        new_id = max(self.assignments_db.keys()) + 1 if self.assignments_db else 1

        # 创建分配记录
        assignment_record = {
            "id": new_id,
            "host": assignment_data.host,
            "strategy": assignment_data.strategy,
            "planner_version_id": assignment_data.planner_version_id,
            "traffic_pct": assignment_data.traffic_pct,
            "enabled": True,
            "user_filters": assignment_data.user_filters or {},
            "device_filters": assignment_data.device_filters or {},
            "failure_threshold": assignment_data.failure_threshold,
            "cost_threshold": assignment_data.cost_threshold,
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }

        self.assignments_db[new_id] = assignment_record

        logger.info(f"Created A/B assignment: {assignment_data.host}/{assignment_data.strategy} -> version {assignment_data.planner_version_id} ({assignment_data.traffic_pct}%)")

        return ABAssignmentResponse(**assignment_record)

    async def _validate_traffic_allocation(self, host: str, strategy: str, new_traffic_pct: int):
        """验证流量分配不超过100%"""
        total_traffic = 0

        for assignment in self.assignments_db.values():
            if (assignment["host"] == host and
                assignment["strategy"] == strategy and
                assignment["enabled"]):
                total_traffic += assignment["traffic_pct"]

        if total_traffic + new_traffic_pct > 100:
            raise HTTPException(
                status_code=400,
                detail=f"Traffic allocation would exceed 100% ({total_traffic + new_traffic_pct}%)"
            )

    async def get_active_assignments(self, host: str = None, strategy: str = None) -> List[ABAssignmentResponse]:
        """获取活跃的A/B分配"""
        assignments = []

        for assignment in self.assignments_db.values():
            if not assignment["enabled"]:
                continue

            if host and assignment["host"] != host:
                continue

            if strategy and assignment["strategy"] != strategy:
                continue

            assignments.append(ABAssignmentResponse(**assignment))

        return assignments

    async def disable_assignment(self, assignment_id: int) -> ABAssignmentResponse:
        """禁用A/B分配"""
        if assignment_id not in self.assignments_db:
            raise HTTPException(status_code=404, detail="Assignment not found")

        assignment = self.assignments_db[assignment_id]
        assignment["enabled"] = False
        assignment["updated_at"] = datetime.now()

        logger.info(f"Disabled A/B assignment {assignment_id}")

        return ABAssignmentResponse(**assignment)

    async def get_deployment_status(self, host: str = None) -> List[DeploymentStatus]:
        """获取部署状态"""
        statuses = []

        for assignment in self.assignments_db.values():
            if not assignment["enabled"]:
                continue

            if host and assignment["host"] != host:
                continue

            version = self.versions_db.get(assignment["planner_version_id"])
            if not version:
                continue

            # 获取当前性能指标（模拟）
            current_metrics = await self._get_current_metrics(
                assignment["planner_version_id"],
                assignment["host"]
            )

            # 评估健康状态
            health_status = self._evaluate_health_status(
                current_metrics,
                assignment["failure_threshold"],
                assignment["cost_threshold"]
            )

            statuses.append(DeploymentStatus(
                version_id=version["id"],
                version_name=version["name"],
                status=version["status"],
                traffic_pct=assignment["traffic_pct"],
                current_metrics=current_metrics,
                health_status=health_status
            ))

        return statuses

    async def _get_current_metrics(self, version_id: int, host: str) -> Dict[str, Any]:
        """获取当前性能指标"""
        # 模拟实时指标
        import random

        base_success_rate = 0.75
        base_avg_steps = 4.5
        base_cost = 0.02

        # 根据版本ID添加一些变化
        version_factor = (version_id % 3) * 0.05

        return {
            "success_rate": min(0.95, base_success_rate + version_factor + random.uniform(-0.05, 0.05)),
            "avg_steps": base_avg_steps + random.uniform(-0.5, 0.5),
            "avg_cost_per_run": base_cost + random.uniform(-0.005, 0.005),
            "total_runs": random.randint(50, 200),
            "error_rate": random.uniform(0.02, 0.08),
            "avg_latency_ms": random.randint(800, 1500),
            "last_updated": datetime.now().isoformat()
        }

    def _evaluate_health_status(self, metrics: Dict, failure_threshold: float, cost_threshold: float) -> str:
        """评估健康状态"""
        success_rate = metrics.get("success_rate", 0)
        error_rate = metrics.get("error_rate", 0)
        cost = metrics.get("avg_cost_per_run", 0)

        # 基准成本（这里使用固定值，实际应该从配置获取）
        baseline_cost = 0.02

        if error_rate > failure_threshold:
            return "unhealthy"
        elif cost > baseline_cost * cost_threshold:
            return "cost_warning"
        elif success_rate < 0.7:
            return "performance_warning"
        else:
            return "healthy"

    async def auto_rollback_check(self):
        """自动回退检查"""
        rollback_actions = []

        for assignment_id, assignment in self.assignments_db.items():
            if not assignment["enabled"]:
                continue

            version_id = assignment["planner_version_id"]
            version = self.versions_db.get(version_id)

            if not version or version["status"] != "prod":
                continue

            # 获取当前指标
            metrics = await self._get_current_metrics(version_id, assignment["host"])
            health_status = self._evaluate_health_status(
                metrics,
                assignment["failure_threshold"],
                assignment["cost_threshold"]
            )

            # 检查是否需要回退
            if health_status == "unhealthy":
                logger.warning(f"Auto-rollback triggered for assignment {assignment_id}: {health_status}")

                # 禁用当前分配
                assignment["enabled"] = False
                assignment["updated_at"] = datetime.now()

                # 标记版本为回退状态
                version["status"] = "rollback"

                rollback_actions.append({
                    "assignment_id": assignment_id,
                    "version_id": version_id,
                    "reason": health_status,
                    "metrics": metrics
                })

        return rollback_actions

# 全局服务实例
deployment_service = PlannerDeploymentService()

# API端点
@router.post("/deploy/planner", response_model=PlannerVersionResponse)
async def create_planner_version(version_data: PlannerVersionCreate):
    """创建新的Planner版本"""
    return await deployment_service.create_planner_version(version_data)

@router.put("/deploy/planner/{version_id}/status")
async def update_planner_status(
    version_id: int,
    status: str,
    metrics: Optional[Dict[str, Any]] = None
):
    """更新Planner版本状态"""
    return await deployment_service.update_version_status(version_id, status, metrics)

@router.post("/deploy/ab", response_model=ABAssignmentResponse)
async def create_ab_assignment(assignment_data: ABAssignmentCreate):
    """创建A/B测试分配"""
    return await deployment_service.create_ab_assignment(assignment_data)

@router.get("/deploy/ab/active")
async def get_active_assignments(host: str = None, strategy: str = None):
    """获取活跃的A/B分配"""
    return await deployment_service.get_active_assignments(host, strategy)

@router.delete("/deploy/ab/{assignment_id}")
async def disable_ab_assignment(assignment_id: int):
    """禁用A/B分配"""
    return await deployment_service.disable_assignment(assignment_id)

@router.get("/deploy/status")
async def get_deployment_status(host: str = None):
    """获取部署状态"""
    return await deployment_service.get_deployment_status(host)

@router.post("/deploy/rollback/check")
async def check_auto_rollback(background_tasks: BackgroundTasks):
    """手动触发自动回退检查"""
    rollback_actions = await deployment_service.auto_rollback_check()

    return {
        "rollback_count": len(rollback_actions),
        "actions": rollback_actions
    }

@router.get("/deploy/versions")
async def list_planner_versions():
    """列出所有Planner版本"""
    versions = [
        PlannerVersionResponse(**version)
        for version in deployment_service.versions_db.values()
    ]
    return sorted(versions, key=lambda x: x.created_at, reverse=True)

# 后台任务：定期自动回退检查
async def periodic_rollback_check():
    """定期自动回退检查任务"""
    while True:
        try:
            await asyncio.sleep(300)  # 每5分钟检查一次
            rollback_actions = await deployment_service.auto_rollback_check()

            if rollback_actions:
                logger.info(f"Periodic rollback check: {len(rollback_actions)} actions taken")

        except Exception as e:
            logger.error(f"Periodic rollback check failed: {e}")

if __name__ == "__main__":
    # 测试代码
    import uvicorn
    from fastapi import FastAPI

    app = FastAPI(title="Planner Deployment API")
    app.include_router(router)

    # 启动后台任务
    @app.on_event("startup")
    async def startup():
        asyncio.create_task(periodic_rollback_check())

    uvicorn.run(app, host="0.0.0.0", port=8005)