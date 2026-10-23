"""译伴基础应用工厂；当前仅装配日志、HTTP 与路由。"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from api import register_routers
from config import settings
from core.database import close_database_pool, create_database_pool
from core.token import validate_jwt_secret_key
from utils.logger import get_logger, setup_logging

from .config import AppConfig
from .exceptions import setup_exception_handlers
from .middleware import setup_middleware
from .routes import setup_routes

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """默认（database_enabled=False）不连接数据库、Redis 或任务队列。

    启用数据库后仅初始化、释放连接资源；不执行 create_all 或自动迁移
    （表结构由 Alembic 唯一管理）。
    """
    setup_logging(level=settings.log_level)
    if settings.auth_enabled and not settings.database_enabled:
        raise ValueError("启用真实鉴权必须同时启用数据库")
    if settings.auth_enabled:
        # 密钥校验先于连接池创建：弱密钥直接失败，不残留连接池
        validate_jwt_secret_key(settings.effective_jwt_secret_key)
        logger.info("真实鉴权已启用")
    try:
        if settings.database_enabled:
            await create_database_pool()
            logger.info("译伴基础工程启动；数据库连接池已初始化")
        else:
            logger.info("译伴基础工程启动；业务基础设施尚未接入")
        yield
    finally:
        if settings.database_enabled:
            await close_database_pool()
        logger.info("译伴基础工程关闭")


def create_app() -> FastAPI:
    """创建基础应用，真实业务按后续批次注册。"""
    app = FastAPI(**AppConfig.get_app_config(), lifespan=lifespan)
    if not settings.debug:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    setup_middleware(app)
    setup_exception_handlers(app)
    setup_routes(app)
    register_routers(app)
    return app
