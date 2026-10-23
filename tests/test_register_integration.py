"""注册接口集成测试（需真实 MySQL 8.4 译伴专用测试库）。

运行方式：
    TEST_DATABASE_URL='mysql+pymysql://yiban:<password>@127.0.0.1:3308/yiban_api_test' \
    uv run --locked pytest -q tests/test_register_integration.py

只读 TEST_DATABASE_URL，缺失跳过、目标非 yiban_api_test 时报错。
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import bcrypt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from core import database as db
from core.database import ensure_test_database
from models.user import User

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="需要 TEST_DATABASE_URL 指向译伴专用测试库 yiban_api_test",
)

ROOT = Path(__file__).resolve().parents[1]
VALID_ORIGIN = "http://localhost:5173"


@pytest.fixture(scope="module", autouse=True)
def _guard_test_db():
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
    """每个集成测试独立准备表结构，不依赖其他测试先执行。"""
    r = _run_alembic("upgrade", "head")
    assert r.returncode == 0, r.stderr
    yield
    r = _run_alembic("downgrade", "base")
    assert r.returncode == 0, r.stderr


@pytest.fixture
def client(prepared_schema, monkeypatch):
    """启用数据库的应用 TestClient（显式配置，不依赖私有 .env）。"""
    from config import settings
    from app import create_app

    monkeypatch.setattr(settings, "database_enabled", True)
    monkeypatch.setattr(settings, "database_url", TEST_DATABASE_URL)
    with TestClient(create_app(), base_url="http://localhost") as c:
        yield c


def _register(client, **overrides):
    data = {"email": "new@test.com", "password": "password123", "display_name": "新用户"}
    data.update(overrides)
    return client.post(
        "/api/v1/auth/register",
        json=data,
        headers={"Origin": VALID_ORIGIN, "X-Yiban-Request": "1"},
    )


def _fetch_password_hash(email: str) -> str:
    async def _go():
        engine = create_async_engine(db._to_async_url(TEST_DATABASE_URL))
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as s:
                user = (
                    await s.execute(select(User).where(User.email == email))
                ).scalar_one()
                return user.password_hash
        finally:
            await engine.dispose()

    return asyncio.run(_go())


def test_register_success(client):
    r = _register(client, email="Foo@Test.com")
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "foo@test.com"  # 规范化 strip + lower
    assert body["display_name"] == "新用户"
    assert body["role"] == "user"  # 服务端固定普通角色
    assert body["id"]
    assert "password_hash" not in body  # 绝不回传哈希


def test_register_duplicate_email_conflict(client):
    assert _register(client, email="dup@test.com").status_code == 201
    r = _register(client, email="DUP@Test.com")  # 规范化后相同
    assert r.status_code == 409


def test_register_ignores_role_in_body(client):
    """请求体携带 role='admin' 被忽略，绝不落库为 admin。"""
    r = _register(client, email="role@test.com", role="admin")
    assert r.status_code == 201
    assert r.json()["role"] == "user"


def test_register_stores_bcrypt_hash(client):
    """密码经 bcrypt 哈希落库，非明文，可校验。"""
    r = _register(client, email="hash@test.com", password="password123")
    assert r.status_code == 201
    hashed = _fetch_password_hash("hash@test.com")
    assert hashed != "password123"
    assert bcrypt.checkpw(b"password123", hashed.encode())
