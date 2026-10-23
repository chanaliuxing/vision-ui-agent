"""
Sprint H: Recall API服务
轨迹回忆和相似度检索的FastAPI应用
"""
import os
import sys
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from server.routes.recall import router as recall_router

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    logger.info("Starting Recall API service...")

    try:
        # 初始化嵌入服务
        from server.services.embeddings import embedding_service
        providers = embedding_service.get_available_providers()
        logger.info(f"Initialized embedding providers: {[p['provider'] for p in providers]}")

        # 初始化回忆服务
        from server.services.recall import recall_service
        await recall_service.ensure_connection()
        logger.info("Initialized recall service")

        yield

    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        raise

    # 关闭时清理
    logger.info("Shutting down Recall API service...")


# 创建FastAPI应用
app = FastAPI(
    title="Recall API",
    description="Sprint H: 轨迹回忆和相似度检索服务",
    version="1.0.0",
    lifespan=lifespan
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(recall_router)


@app.get("/health")
async def health_check():
    """服务健康检查"""
    try:
        from server.services.recall import recall_service
        from server.services.embeddings import embedding_service

        # 检查回忆服务
        await recall_service.ensure_connection()

        # 检查嵌入服务
        providers = embedding_service.get_available_providers()

        return {
            "status": "healthy",
            "service": "recall-api",
            "version": "1.0.0",
            "database": "connected",
            "embedding_providers": len(providers),
            "available_providers": [p["provider"] for p in providers],
            "recall_stats": recall_service.get_stats()
        }

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Service unhealthy: {str(e)}")


@app.get("/")
async def root():
    """API根端点"""
    return {
        "message": "Sprint H: Recall API Service",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "recall_similar": "/recall/similar",
            "recall_by_fingerprint": "/recall/by-fingerprint",
            "recall_by_trajectory": "/recall/by-trajectory",
            "recall_stats": "/recall/stats",
            "docs": "/docs",
            "redoc": "/redoc"
        }
    }


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """全局异常处理"""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"}
    )


if __name__ == "__main__":
    # 从环境变量读取配置
    host = os.getenv("RECALL_API_HOST", "0.0.0.0")
    port = int(os.getenv("RECALL_API_PORT", "8003"))

    logger.info(f"Starting Recall API on {host}:{port}")

    uvicorn.run(
        "app_recall:app",
        host=host,
        port=port,
        reload=True,
        access_log=True
    )