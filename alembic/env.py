"""Alembic 迁移环境：与运行时读取同一套显式数据库配置。

迁移使用同步驱动（pymysql）执行 DDL；运行时由 core.database._to_async_url
转为 aiomysql。二者共享 settings.database_url（环境变量 DATABASE_URL）。
"""

import sys
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool

# 确保可 import 项目模块（config / core / models）
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import settings  # noqa: E402
from core.database import Base, is_teacher_sample_db  # noqa: E402
import models.user  # noqa: F401,E402  # 注册 User 到 Base.metadata

target_metadata = Base.metadata


def _database_url() -> str:
    url = settings.database_url
    if not url:
        raise RuntimeError("DATABASE_URL 未配置，无法执行迁移")
    if is_teacher_sample_db(url):
        raise RuntimeError("不能使用教师示例库执行迁移，请显式配置译伴 DATABASE_URL")
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(_database_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
