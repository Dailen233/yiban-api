"""基础状态路由；健康响应不代表业务或数据库就绪。"""

from fastapi import FastAPI

from config import settings


def setup_routes(app: FastAPI) -> None:
    @app.get("/health", tags=["基础状态"])
    async def health_check() -> dict:
        return {
            "status": "ok",
            "service": settings.project_name,
            "version": settings.project_version,
            "mode": "bootstrap",
            "business_ready": False,
        }
