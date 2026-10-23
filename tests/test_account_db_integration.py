"""账号数据库集成测试（需真实 MySQL 8.4 译伴专用测试库）。

运行方式（指向译伴专用测试库，勿指向开发库/教师库/其他项目库）：
    TEST_DATABASE_URL='mysql+pymysql://yiban:<password>@127.0.0.1:3308/yiban_api_test' \
    uv run --locked pytest -q tests/test_account_db_integration.py

本文件只读 TEST_DATABASE_URL（不回退 DATABASE_URL）；缺失时整体跳过，
存在但目标库不是 yiban_api_test 时报错（跳过不视为通过）。
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
from core.database import ensure_test_database
from models.user import User, normalize_email

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="需要 TEST_DATABASE_URL 指向译伴专用测试库 yiban_api_test",
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module", autouse=True)
def _guard_test_db():
    """TEST_DATABASE_URL 存在但非译伴专用测试库时报错（不跳过）。"""
    ensure_test_database(TEST_DATABASE_URL)


def _run_alembic(*args: str) -> subprocess.CompletedProcess:
    merged = dict(
        os.environ,
        DATABASE_URL=TEST_DATABASE_URL,
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
def prepared_schema():
    """每个集成测试独立准备表结构（upgrade head），不依赖其他测试先执行。"""
    r = _run_alembic("upgrade", "head")
    assert r.returncode == 0, r.stderr
    yield
    r = _run_alembic("downgrade", "base")
    assert r.returncode == 0, r.stderr


@pytest.fixture
async def session_factory(prepared_schema):
    """独立测试库上的会话工厂（表结构已由 prepared_schema 准备）。"""
    engine = create_async_engine(db._to_async_url(TEST_DATABASE_URL))
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def test_upgrade_downgrade_upgrade():
    """独立测试库上 upgrade → downgrade → upgrade 全链路。"""
    r = _run_alembic("upgrade", "head")
    assert r.returncode == 0, r.stderr
    r = _run_alembic("downgrade", "base")
    assert r.returncode == 0, r.stderr
    r = _run_alembic("upgrade", "head")
    assert r.returncode == 0, r.stderr
    r = _run_alembic("downgrade", "base")
    assert r.returncode == 0, r.stderr


@pytest.mark.asyncio
async def test_user_persist_normalized_email_unique_and_rollback(session_factory):
    """持久化、规范化 email 唯一约束、事务回滚（限定独立测试库）。"""
    SessionLocal = session_factory

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
        session.add(
            User(email="rollback@test.com", password_hash="x", display_name="Rb")
        )
        await session.flush()
        await session.rollback()
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                text("SELECT 1 FROM `user` WHERE email='rollback@test.com'")
            )
        ).scalars().all()
        assert rows == []


@pytest.mark.asyncio
async def test_utc_time_roundtrip_with_non_utc_offset(session_factory):
    """应用层把带 +08:00 偏移和微秒的 aware 时间转 UTC 存 DATETIME(6)，读回恢复 UTC 语义。"""
    SessionLocal = session_factory
    # 直接传原始 aware 时间（不替应用预先转换）
    aware = datetime(
        2026, 10, 23, 18, 30, 15, 123456, tzinfo=timezone(timedelta(hours=8))
    )
    expected_utc_naive = datetime(2026, 10, 23, 10, 30, 15, 123456)

    async with SessionLocal() as session:
        u = User(
            email="tz@test.com",
            password_hash="x",
            display_name="Tz",
            created_at=aware,
            updated_at=aware,
        )
        session.add(u)
        await session.commit()
        uid = u.id

    async with SessionLocal() as session:
        loaded = await session.get(User, uid)
        # 读回恢复 UTC 语义（aware UTC），微秒保留
        assert loaded.created_at.tzinfo is timezone.utc
        assert loaded.created_at.replace(tzinfo=None) == expected_utc_naive
        assert loaded.created_at.microsecond == 123456


@pytest.mark.asyncio
async def test_app_startup_shutdown_with_db_enabled(monkeypatch):
    """启用数据库后应用启停；显式控制 host 与数据库配置，不依赖私有 .env。"""
    from config import settings
    from fastapi.testclient import TestClient
    from app import create_app

    monkeypatch.setattr(settings, "database_enabled", True)
    monkeypatch.setattr(settings, "database_url", TEST_DATABASE_URL)

    # base_url 显式指定 localhost，避免依赖环境 host 配置
    with TestClient(create_app(), base_url="http://localhost") as client:
        assert client.get("/health").status_code == 200
    # lifespan 关闭后引擎与会话工厂均已清理，无残留
    assert db.async_engine is None
    assert db.AsyncSessionLocal is None
