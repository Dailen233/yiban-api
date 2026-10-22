"""译伴基础应用工厂；当前仅装配日志、HTTP 与路由。"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from api import register_routers
from config import settings
from utils.logger import get_logger, setup_logging

from .config import AppConfig
from .exceptions import setup_exception_handlers
from .middleware import setup_middleware
from .routes import setup_routes

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """基础工程不连接数据库、Redis 或启动任务队列。

    模板的基础设施模块保留供后续适配，不把课堂内存队列当成真实后台任务。
    """
    setup_logging(level=settings.log_level)
    logger.info("译伴基础工程启动；业务基础设施尚未接入")
    try:
        yield
    finally:
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
