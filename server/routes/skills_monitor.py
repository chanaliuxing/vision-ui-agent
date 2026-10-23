"""
Sprint J: Ä˝—ßåﬂ°API
–õÄ˝(≈µ—ß'˝êåãøﬂ°
"""

import asyncio
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field

from server.models.response import BaseResponse
from server.services.auth import get_current_user, User
from server.services.database import get_database

router = APIRouter(prefix="/skills/monitor", tags=["skills-monitor"])

# ===== pn!ã =====

class SkillMetrics(BaseModel):
    """Ä˝!ã"""
    skill_name: str
    version: str
    host: str
    runs: int
    success: int
    failures: int
    success_rate: float
    avg_steps: float
    avg_reward: float
    avg_latency_ms: int
    p95_latency_ms: int
    total_cost: float

class SkillTrendData(BaseModel):
    """Ä˝ãøpn"""
    date: str
    runs: int
    success: int
    success_rate: float
    avg_latency_ms: int

class SkillDashboardResponse(BaseModel):
    """Ä˝ÍhÿÕî"""
    summary: Dict[str, Any]
    top_skills: List[SkillMetrics]
    recent_trends: List[SkillTrendData]
    host_distribution: Dict[str, int]
    version_distribution: Dict[str, int]

class SkillErrorAnalysis(BaseModel):
    """Ä˝Ôê"""
    skill_name: str
    version: str
    error_type: str
    error_count: int
    error_rate: float
    sample_error: str

class SkillPerformanceHeatmap(BaseModel):
    """Ä˝'˝Ìõ˛pn"""
    skill_name: str
    host: str
    hour: int
    avg_latency_ms: int
    success_rate: float
    run_count: int

# ===== APIÔπ =====

@router.get("/dashboard", response_model=SkillDashboardResponse)
async def get_skills_dashboard(
    days: int = Query(7, ge=1, le=30, description="ﬂ°)p"),
    host: Optional[str] = Query(None, description="	ﬂ«‰"),
    db=Depends(get_database)
):
    """∑÷Ä˝—ßÍhÿpn"""
    try:
        # Ñ˙Â‚aˆ
        where_conditions = [f"day >= CURRENT_DATE - INTERVAL '{days} days'"]
        params = []

        if host:
            where_conditions.append(f"host = ${len(params) + 1}")
            params.append(host)

        where_clause = " AND ".join(where_conditions)

        # ∑÷;SÇÅﬂ°
        summary_query = f"""
            SELECT
                COUNT(DISTINCT skill_name) as total_skills,
                COUNT(DISTINCT host) as total_hosts,
                SUM(runs) as total_runs,
                SUM(success) as total_success,
                SUM(failures) as total_failures,
                CASE WHEN SUM(runs) > 0 THEN SUM(success)::FLOAT / SUM(runs) ELSE 0 END as overall_success_rate,
                AVG(avg_latency_ms)::INT as avg_latency,
                SUM(total_cost) as total_cost
            FROM skill_stats_daily
            WHERE {where_clause}
        """

        summary = await db.fetchrow(summary_query, *params)

        # ∑÷íLú	(!p	
        top_skills_query = f"""
            SELECT
                skill_name,
                version,
                host,
                SUM(runs) as runs,
                SUM(success) as success,
                SUM(failures) as failures,
                CASE WHEN SUM(runs) > 0 THEN SUM(success)::FLOAT / SUM(runs) ELSE 0 END as success_rate,
                AVG(avg_steps) as avg_steps,
                AVG(avg_reward) as avg_reward,
                AVG(avg_latency_ms)::INT as avg_latency_ms,
                AVG(p95_latency_ms)::INT as p95_latency_ms,
                SUM(total_cost) as total_cost
            FROM skill_stats_daily
            WHERE {where_clause}
            GROUP BY skill_name, version, host
            ORDER BY runs DESC
            LIMIT 10
        """

        top_skills_data = await db.fetch(top_skills_query, *params)
        top_skills = [
            SkillMetrics(
                skill_name=row["skill_name"],
                version=row["version"],
                host=row["host"] or "unknown",
                runs=row["runs"] or 0,
                success=row["success"] or 0,
                failures=row["failures"] or 0,
                success_rate=float(row["success_rate"] or 0),
                avg_steps=float(row["avg_steps"] or 0),
                avg_reward=float(row["avg_reward"] or 0),
                avg_latency_ms=row["avg_latency_ms"] or 0,
                p95_latency_ms=row["p95_latency_ms"] or 0,
                total_cost=float(row["total_cost"] or 0)
            )
            for row in top_skills_data
        ]

        # ∑÷ãøpn	Â	
        trends_query = f"""
            SELECT
                day,
                SUM(runs) as runs,
                SUM(success) as success,
                CASE WHEN SUM(runs) > 0 THEN SUM(success)::FLOAT / SUM(runs) ELSE 0 END as success_rate,
                AVG(avg_latency_ms)::INT as avg_latency_ms
            FROM skill_stats_daily
            WHERE {where_clause}
            GROUP BY day
            ORDER BY day
        """

        trends_data = await db.fetch(trends_query, *params)
        recent_trends = [
            SkillTrendData(
                date=row["day"].strftime("%Y-%m-%d"),
                runs=row["runs"] or 0,
                success=row["success"] or 0,
                success_rate=float(row["success_rate"] or 0),
                avg_latency_ms=row["avg_latency_ms"] or 0
            )
            for row in trends_data
        ]

        # ∑÷ﬂ
        host_dist_query = f"""
            SELECT host, SUM(runs) as runs
            FROM skill_stats_daily
            WHERE {where_clause}
            GROUP BY host
            ORDER BY runs DESC
        """

        host_dist_data = await db.fetch(host_dist_query, *params)
        host_distribution = {
            row["host"] or "unknown": row["runs"] or 0
            for row in host_dist_data
        }

        # ∑÷H,
        version_dist_query = f"""
            SELECT version, SUM(runs) as runs
            FROM skill_stats_daily
            WHERE {where_clause}
            GROUP BY version
            ORDER BY runs DESC
        """

        version_dist_data = await db.fetch(version_dist_query, *params)
        version_distribution = {
            row["version"]: row["runs"] or 0
            for row in version_dist_data
        }

        return SkillDashboardResponse(
            summary={
                "total_skills": summary["total_skills"] or 0,
                "total_hosts": summary["total_hosts"] or 0,
                "total_runs": summary["total_runs"] or 0,
                "total_success": summary["total_success"] or 0,
                "total_failures": summary["total_failures"] or 0,
                "overall_success_rate": float(summary["overall_success_rate"] or 0),
                "avg_latency": summary["avg_latency"] or 0,
                "total_cost": float(summary["total_cost"] or 0),
                "period_days": days
            },
            top_skills=top_skills,
            recent_trends=recent_trends,
            host_distribution=host_distribution,
            version_distribution=version_distribution
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"∑÷Íhÿpn1%: {str(e)}")

@router.get("/errors", response_model=List[SkillErrorAnalysis])
async def get_skill_errors(
    days: int = Query(7, ge=1, le=30, description="ﬂ°)p"),
    skill_name: Optional[str] = Query(None, description="Ä˝«‰"),
    limit: int = Query(20, ge=1, le=100, description="‘ﬁ∞Up"),
    db=Depends(get_database)
):
    """∑÷Ä˝Ôê"""
    try:
        # Ñ˙Â‚aˆ
        where_conditions = [
            f"DATE(started_at) >= CURRENT_DATE - INTERVAL '{days} days'",
            "success = false",
            "error_message IS NOT NULL"
        ]
        params = []

        if skill_name:
            where_conditions.append(f"skill_name = ${len(params) + 1}")
            params.append(skill_name)

        where_clause = " AND ".join(where_conditions)

        # ÔêÂ‚
        errors_query = f"""
            WITH error_stats AS (
                SELECT
                    skill_name,
                    version,
                    CASE
                        WHEN error_message LIKE '%timeout%' THEN 'timeout'
                        WHEN error_message LIKE '%not found%' THEN 'element_not_found'
                        WHEN error_message LIKE '%validation%' THEN 'validation_error'
                        WHEN error_message LIKE '%permission%' THEN 'permission_error'
                        ELSE 'other'
                    END as error_type,
                    COUNT(*) as error_count,
                    error_message
                FROM skill_execution_logs
                WHERE {where_clause}
                GROUP BY skill_name, version, error_type, error_message
            ),
            total_runs AS (
                SELECT
                    skill_name,
                    version,
                    COUNT(*) as total_count
                FROM skill_execution_logs
                WHERE DATE(started_at) >= CURRENT_DATE - INTERVAL '{days} days'
                GROUP BY skill_name, version
            )
            SELECT
                e.skill_name,
                e.version,
                e.error_type,
                SUM(e.error_count) as error_count,
                CASE WHEN t.total_count > 0 THEN SUM(e.error_count)::FLOAT / t.total_count ELSE 0 END as error_rate,
                (array_agg(e.error_message ORDER BY e.error_count DESC))[1] as sample_error
            FROM error_stats e
            LEFT JOIN total_runs t ON e.skill_name = t.skill_name AND e.version = t.version
            GROUP BY e.skill_name, e.version, e.error_type, t.total_count
            ORDER BY error_count DESC
            LIMIT ${len(params) + 1}
        """

        params.append(limit)
        errors_data = await db.fetch(errors_query, *params)

        return [
            SkillErrorAnalysis(
                skill_name=row["skill_name"],
                version=row["version"],
                error_type=row["error_type"],
                error_count=row["error_count"],
                error_rate=float(row["error_rate"] or 0),
                sample_error=row["sample_error"] or ""
            )
            for row in errors_data
        ]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"∑÷Ôê1%: {str(e)}")

@router.get("/heatmap", response_model=List[SkillPerformanceHeatmap])
async def get_performance_heatmap(
    skill_name: str = Query(..., description="Ä˝"),
    days: int = Query(7, ge=1, le=30, description="ﬂ°)p"),
    db=Depends(get_database)
):
    """∑÷Ä˝'˝Ìõ˛pn	ˆ	"""
    try:
        # '˝Ìõ˛Â‚
        heatmap_query = """
            SELECT
                skill_name,
                host,
                EXTRACT(HOUR FROM started_at) as hour,
                AVG(execution_time_ms)::INT as avg_latency_ms,
                COUNT(*) FILTER (WHERE success = true)::FLOAT / COUNT(*) as success_rate,
                COUNT(*) as run_count
            FROM skill_execution_logs
            WHERE skill_name = $1
              AND DATE(started_at) >= CURRENT_DATE - INTERVAL '%s days'
            GROUP BY skill_name, host, EXTRACT(HOUR FROM started_at)
            ORDER BY host, hour
        """ % days

        heatmap_data = await db.fetch(heatmap_query, skill_name)

        return [
            SkillPerformanceHeatmap(
                skill_name=row["skill_name"],
                host=row["host"] or "unknown",
                hour=int(row["hour"]),
                avg_latency_ms=row["avg_latency_ms"] or 0,
                success_rate=float(row["success_rate"] or 0),
                run_count=row["run_count"] or 0
            )
            for row in heatmap_data
        ]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"∑÷'˝Ìõ˛1%: {str(e)}")

@router.get("/real-time")
async def get_real_time_metrics(
    limit: int = Query(50, ge=1, le=200, description="‘ﬁ∞Up"),
    db=Depends(get_database)
):
    """∑÷ûˆÄ˝gL"""
    try:
        # ûˆgL∞U
        real_time_query = """
            SELECT
                id,
                skill_name,
                version,
                host,
                success,
                execution_time_ms,
                error_message,
                started_at,
                finished_at
            FROM skill_execution_logs
            WHERE started_at >= NOW() - INTERVAL '1 hour'
            ORDER BY started_at DESC
            LIMIT $1
        """

        recent_executions = await db.fetch(real_time_query, limit)

        #  —5üﬂ°
        recent_stats_query = """
            SELECT
                COUNT(*) as total_runs,
                COUNT(*) FILTER (WHERE success = true) as successful_runs,
                AVG(execution_time_ms)::INT as avg_latency,
                COUNT(DISTINCT skill_name) as active_skills
            FROM skill_execution_logs
            WHERE started_at >= NOW() - INTERVAL '5 minutes'
        """

        recent_stats = await db.fetchrow(recent_stats_query)

        # ;√Ä˝íL
        active_skills_query = """
            SELECT
                skill_name,
                COUNT(*) as runs,
                COUNT(*) FILTER (WHERE success = true)::FLOAT / COUNT(*) as success_rate
            FROM skill_execution_logs
            WHERE started_at >= NOW() - INTERVAL '15 minutes'
            GROUP BY skill_name
            ORDER BY runs DESC
            LIMIT 10
        """

        active_skills = await db.fetch(active_skills_query)

        return {
            "timestamp": datetime.now().isoformat(),
            "recent_stats": {
                "total_runs": recent_stats["total_runs"] or 0,
                "successful_runs": recent_stats["successful_runs"] or 0,
                "success_rate": float(recent_stats["successful_runs"] or 0) / max(recent_stats["total_runs"] or 1, 1),
                "avg_latency": recent_stats["avg_latency"] or 0,
                "active_skills": recent_stats["active_skills"] or 0
            },
            "recent_executions": [
                {
                    "id": row["id"],
                    "skill_name": row["skill_name"],
                    "version": row["version"],
                    "host": row["host"],
                    "success": row["success"],
                    "execution_time_ms": row["execution_time_ms"],
                    "error_message": row["error_message"],
                    "started_at": row["started_at"].isoformat() if row["started_at"] else None,
                    "finished_at": row["finished_at"].isoformat() if row["finished_at"] else None
                }
                for row in recent_executions
            ],
            "active_skills": [
                {
                    "skill_name": row["skill_name"],
                    "runs": row["runs"],
                    "success_rate": float(row["success_rate"] or 0)
                }
                for row in active_skills
            ]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"∑÷ûˆ1%: {str(e)}")

@router.get("/comparison")
async def compare_skills(
    skill_names: str = Query(..., description="Ä˝h˜î"),
    days: int = Query(7, ge=1, le=30, description="ﬂ°)p"),
    db=Depends(get_database)
):
    """‘É*Ä˝Ñ'˝"""
    try:
        skills_list = [name.strip() for name in skill_names.split(",")]

        if len(skills_list) > 5:
            raise HTTPException(status_code=400, detail=" Í˝‘É5*Ä˝")

        # Ñ˙`M&
        placeholders = ",".join(f"${i+1}" for i in range(len(skills_list)))

        comparison_query = f"""
            SELECT
                skill_name,
                version,
                SUM(runs) as total_runs,
                SUM(success) as total_success,
                CASE WHEN SUM(runs) > 0 THEN SUM(success)::FLOAT / SUM(runs) ELSE 0 END as success_rate,
                AVG(avg_steps) as avg_steps,
                AVG(avg_reward) as avg_reward,
                AVG(avg_latency_ms)::INT as avg_latency_ms,
                AVG(p95_latency_ms)::INT as p95_latency_ms,
                SUM(total_cost) as total_cost
            FROM skill_stats_daily
            WHERE skill_name IN ({placeholders})
              AND day >= CURRENT_DATE - INTERVAL '{days} days'
            GROUP BY skill_name, version
            ORDER BY total_runs DESC
        """

        comparison_data = await db.fetch(comparison_query, *skills_list)

        # °ó¯˘'˝
        if comparison_data:
            max_runs = max(row["total_runs"] or 0 for row in comparison_data)
            max_success_rate = max(row["success_rate"] or 0 for row in comparison_data)
            min_latency = min(row["avg_latency_ms"] or float('inf') for row in comparison_data)

        result = []
        for row in comparison_data:
            relative_metrics = {}
            if comparison_data:
                relative_metrics = {
                    "usage_score": (row["total_runs"] or 0) / max(max_runs, 1),
                    "reliability_score": (row["success_rate"] or 0) / max(max_success_rate, 0.01),
                    "performance_score": min_latency / max(row["avg_latency_ms"] or 1, 1)
                }

            result.append({
                "skill_name": row["skill_name"],
                "version": row["version"],
                "metrics": {
                    "total_runs": row["total_runs"] or 0,
                    "total_success": row["total_success"] or 0,
                    "success_rate": float(row["success_rate"] or 0),
                    "avg_steps": float(row["avg_steps"] or 0),
                    "avg_reward": float(row["avg_reward"] or 0),
                    "avg_latency_ms": row["avg_latency_ms"] or 0,
                    "p95_latency_ms": row["p95_latency_ms"] or 0,
                    "total_cost": float(row["total_cost"] or 0)
                },
                "relative_metrics": relative_metrics
            })

        return {
            "compared_skills": skills_list,
            "period_days": days,
            "comparison_data": result,
            "generated_at": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ä˝‘É1%: {str(e)}")

@router.post("/trigger-aggregation", response_model=BaseResponse)
async def trigger_stats_aggregation(
    target_date: Optional[str] = Query(None, description="ÓÂ (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_user),
    db=Depends(get_database)
):
    """K®Ê—ﬂ°pnZ"""
    try:
        # ÄUCP¿Â
        if not current_user.email.endswith("@admin.com"):
            raise HTTPException(status_code=403, detail=" Å°XCP")

        if target_date:
            from datetime import datetime
            date_obj = datetime.strptime(target_date, "%Y-%m-%d").date()
        else:
            date_obj = date.today()

        # (Z˝p
        await db.execute("SELECT aggregate_skill_stats($1)", date_obj)

        return BaseResponse(
            success=True,
            message=f"Ä˝ﬂ°pnZå: {date_obj}"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Zﬂ°pn1%: {str(e)}")

@router.get("/health")
async def get_monitor_health(db=Depends(get_database)):
    """∑÷—ß˚ﬂe∑∂"""
    try:
        # ¿Âpnìﬁ•
        await db.fetchval("SELECT 1")

        # ¿Âpn∞ú¶
        latest_execution = await db.fetchval("""
            SELECT MAX(started_at) FROM skill_execution_logs
        """)

        # ¿Âﬂ°pn∞ú¶
        latest_stats = await db.fetchval("""
            SELECT MAX(day) FROM skill_stats_daily
        """)

        # °ópnﬁ
        now = datetime.now()
        execution_lag = None
        stats_lag = None

        if latest_execution:
            execution_lag = (now - latest_execution).total_seconds()

        if latest_stats:
            stats_lag = (now.date() - latest_stats).days

        health_status = "healthy"
        issues = []

        # ¿Âpn∞ú¶
        if execution_lag and execution_lag > 3600:  # 1ˆ
            health_status = "degraded"
            issues.append(f"gLÂ◊ﬁ {execution_lag/3600:.1f} ˆ")

        if stats_lag and stats_lag > 1:  # 1)
            health_status = "degraded"
            issues.append(f"ﬂ°pnﬁ {stats_lag} )")

        return {
            "status": health_status,
            "timestamp": now.isoformat(),
            "data_freshness": {
                "latest_execution": latest_execution.isoformat() if latest_execution else None,
                "latest_stats": latest_stats.isoformat() if latest_stats else None,
                "execution_lag_seconds": execution_lag,
                "stats_lag_days": stats_lag
            },
            "issues": issues
        }

    except Exception as e:
        return {
            "status": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }