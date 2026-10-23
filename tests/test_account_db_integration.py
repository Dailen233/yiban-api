"""账号数据库集成测试（需真实 MySQL 8.4 独立测试库）。

运行方式（指向独立测试库，勿指向开发库或其他项目库）：
    DATABASE_URL='mysql+pymysql://user:pw@127.0.0.1:3307/yiban_api_test' \
    uv run --locked pytest -q tests/test_account_db_integration.py

未设置 DATABASE_URL 时本文件整体跳过；跳过不视为通过。
"""

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from core import database as db
from models.user import User, normalize_email

DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="需要真实 MySQL 8.4 独立测试库（DATABASE_URL）"
)

ROOT = Path(__file__).resolve().parents[1]


def _run_alembic(*args: str) -> subprocess.CompletedProcess:
    merged = dict(
        os.environ,
        DATABASE_URL=DATABASE_URL,
        FASTAPI_ENV="development",
        DATABASE_ENABLED="false",
    )
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=ROOT,
        env=merged,
        capture_output=True,
        text=True,
    )


@pytest.fixture
async def async_engine_fixture():
    engine = create_async_engine(db._to_async_url(DATABASE_URL))
    yield engine
    await engine.dispose()


@pytest.mark.asyncio
async def test_upgrade_downgrade_upgrade():
    """独立测试库上 upgrade → downgrade → upgrade 全链路。"""
    r = _run_alembic("upgrade", "head")
    assert r.returncode == 0, r.stderr
    r = _run_alembic("downgrade", "base")
    assert r.returncode == 0, r.stderr
    r = _run_alembic("upgrade", "head")
    assert r.returncode == 0, r.stderr


@pytest.mark.asyncio
async def test_user_persist_normalized_email_unique_and_rollback(async_engine_fixture):
    engine = async_engine_fixture
    async with engine.begin() as conn:
        # 清理限定独立测试库
        await conn.execute(text("DELETE FROM `user`"))

    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    # 持久化 + email 规范化 + UUID 主键生成
    async with SessionLocal() as session:
        u = User(
            email=normalize_email("  Foo@Bar.COM  "),
            password_hash="hashed-not-plaintext",
            display_name="Foo",
        )
        session.add(u)
        await session.commit()
        assert u.email == "foo@bar.com"
        assert u.id

    # 规范化后 email 唯一约束
    async with SessionLocal() as session:
        session.add(User(email="foo@bar.com", password_hash="x", display_name="Bar"))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    # 事务回滚：rollback 后不落库
    async with SessionLocal() as session:
        session.add(User(email="rollback@test.com", password_hash="x", display_name="Rb"))
        await session.flush()
        await session.rollback()
    async with SessionLocal() as session:
        rows = (await session.execute(text("SELECT 1 FROM `user` WHERE email='rollback@test.com'"))).scalars().all()
        assert rows == []


@pytest.mark.asyncio
async def test_utc_time_roundtrip_with_non_utc_offset(async_engine_fixture):
    engine = async_engine_fixture
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM `user`"))

    # 输入带 +08:00 偏移的时间，应转 UTC naive 存储
    aware = datetime(2026, 10, 23, 18, 0, 0, tzinfo=timezone(timedelta(hours=8)))
    utc_naive = aware.astimezone(timezone.utc).replace(tzinfo=None)
    assert utc_naive == datetime(2026, 10, 23, 10, 0, 0)

    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionLocal() as session:
        u = User(
            email="tz@test.com",
            password_hash="x",
            display_name="Tz",
            created_at=utc_naive,
            updated_at=utc_naive,
        )
        session.add(u)
        await session.commit()
        uid = u.id

    async with SessionLocal() as session:
        loaded = await session.get(User, uid)
        assert loaded.created_at.tzinfo is None
        assert loaded.created_at == utc_naive  # 读回 UTC naive，语义一致


@pytest.mark.asyncio
async def test_app_startup_shutdown_with_db_enabled(monkeypatch):
    from config import settings
    from fastapi.testclient import TestClient
    from app import create_app

    monkeypatch.setattr(settings, "database_enabled", True)
    monkeypatch.setattr(settings, "database_url", DATABASE_URL)

    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200
    # lifespan 关闭后引擎与会话工厂均已清理
    assert db.async_engine is None
    assert db.AsyncSessionLocal is None
