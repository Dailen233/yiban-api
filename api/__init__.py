"""API 路由包

Greenfield：导出 api_router；create_app 通过 register_routers 挂载。
按表生成的子路由由脚手架追加到 api/v1/__init__.py。
"""

from fastapi import FastAPI, APIRouter

from . import v1

api_router = APIRouter()
api_router.include_router(v1.v1_router, prefix="/v1")


def register_routers(app: FastAPI, prefix: str = "/api") -> None:
    """注册全部 API 路由（默认 /api/v1/...）"""
    app.include_router(api_router, prefix=prefix)


__all__ = ["api_router", "register_routers"]
