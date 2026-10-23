"""API v1 路由包

脚手架生成表模块后，在此追加：
    from api.v1.xxx import router as xxx_router
    v1_router.include_router(xxx_router)
"""

from fastapi import APIRouter

from api.auth import router as auth_router

v1_router = APIRouter()
v1_router.include_router(auth_router)

__all__ = ["v1_router"]
