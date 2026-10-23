"""登录/me/退出集成测试（需真实 MySQL 8.4 译伴专用测试库）。

只读 TEST_DATABASE_URL，缺失跳过、目标非 yiban_api_test 时报错。
"""

import asyncio
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from core import database as db
from core.database import ensure_test_database
from models.user import User
from models.user_session import UserSession

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="需要 TEST_DATABASE_URL 指向译伴专用测试库 yiban_api_test",
)

ROOT = Path(__file__).resolve().parents[1]
VALID_ORIGIN = "http://localhost:5173"
SECRET = "test-random-secret-key-0123456789-abcdef"


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
    r = _run_alembic("upgrade", "head")
    assert r.returncode == 0, r.stderr
    yield
    r = _run_alembic("downgrade", "base")
    assert r.returncode == 0, r.stderr


@pytest.fixture
def client(prepared_schema, monkeypatch):
    """启用数据库 + 真实鉴权的应用 TestClient（显式注入临时随机密钥）。"""
    from config import settings
    from app import create_app

    monkeypatch.setattr(settings, "database_enabled", True)
    monkeypatch.setattr(settings, "database_url", TEST_DATABASE_URL)
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "effective_jwt_secret_key", SECRET)
    with TestClient(create_app(), base_url="http://localhost") as c:
        yield c


def _register(client, email, password="password123", display_name="测试用户"):
    return client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "display_name": display_name},
        headers={"Origin": VALID_ORIGIN, "X-Yiban-Request": "1"},
    )


def _login(client, email, password="password123"):
    return client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers={"Origin": VALID_ORIGIN, "X-Yiban-Request": "1"},
    )


def _extract_cookie_token(resp) -> str:
    set_cookie = resp.headers.get("set-cookie", "")
    for part in set_cookie.split(","):
        part = part.strip()
        if part.startswith("yiban_user_session="):
            return part.split("=", 1)[1].split(";", 1)[0]
    raise AssertionError("未找到会话 cookie")


def _fetch_sessions(email: str):
    async def _go():
        engine = create_async_engine(db._to_async_url(TEST_DATABASE_URL))
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as s:
                user = (
                    await s.execute(select(User).where(User.email == email))
                ).scalar_one()
                return (
                    await s.execute(
                        select(UserSession).where(UserSession.user_id == user.id)
                    )
                ).scalars().all()
        finally:
            await engine.dispose()

    return asyncio.run(_go())


def _expire_sessions(email: str) -> None:
    async def _go():
        engine = create_async_engine(db._to_async_url(TEST_DATABASE_URL))
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as s:
                user = (
                    await s.execute(select(User).where(User.email == email))
                ).scalar_one()
                sessions = (
                    await s.execute(
                        select(UserSession).where(UserSession.user_id == user.id)
                    )
                ).scalars().all()
                for session in sessions:
                    session.expires_at = datetime.now(timezone.utc) - timedelta(
                        minutes=1
                    )
                await s.commit()
        finally:
            await engine.dispose()

    asyncio.run(_go())


def test_register_login_me_logout_flow(client):
    """完整闭环：注册 → 登录 → me → 退出 → me 401。"""
    assert _register(client, "flow@test.com").status_code == 201

    r = _login(client, "flow@test.com")
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "flow@test.com"
    assert body["role"] == "user"
    assert "password" not in r.text  # 不泄露密码/哈希/JWT

    # TestClient 自动携带登录 Cookie
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 200
    assert r.json()["email"] == "flow@test.com"

    r = client.post(
        "/api/v1/auth/logout",
        headers={"Origin": VALID_ORIGIN, "X-Yiban-Request": "1"},
    )
    assert r.status_code == 204

    # 退出后 Cookie 已清除 → me 401
    assert client.get("/api/v1/auth/me").status_code == 401


def test_login_requires_csrf_origin(client):
    """登录无 Origin → 403（复用注册的 CSRF 校验）。"""
    assert _register(client, "csrf@test.com").status_code == 201
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "csrf@test.com", "password": "password123"},
    )
    assert r.status_code == 403


def test_login_wrong_password_401(client):
    assert _register(client, "wrong@test.com").status_code == 201
    r = _login(client, "wrong@test.com", password="wrong-password")
    assert r.status_code == 401


def test_login_nonexistent_email_401(client):
    """不存在的邮箱与错误密码统一 401，不泄露账号存在性。"""
    r = _login(client, "ghost@test.com")
    assert r.status_code == 401


def test_me_without_cookie_401(client):
    assert client.get("/api/v1/auth/me").status_code == 401


def test_login_persists_session(client):
    """登录后 user_session 持久化一条 session_type='user' 且未撤销。"""
    assert _register(client, "persist@test.com").status_code == 201
    assert _login(client, "persist@test.com").status_code == 200

    sessions = _fetch_sessions("persist@test.com")
    assert len(sessions) == 1
    assert sessions[0].session_type == "user"
    assert sessions[0].revoked_at is None


def test_logout_revokes_token_immediately(client):
    """退出前保存原 Token，退出后再请求 me 立即 401。"""
    assert _register(client, "revoke@test.com").status_code == 201
    login_resp = _login(client, "revoke@test.com")
    token = _extract_cookie_token(login_resp)

    assert client.get("/api/v1/auth/me").status_code == 200

    r = client.post(
        "/api/v1/auth/logout",
        headers={"Origin": VALID_ORIGIN, "X-Yiban-Request": "1"},
    )
    assert r.status_code == 204

    sessions = _fetch_sessions("revoke@test.com")
    assert sessions[0].revoked_at is not None

    # 原 Token 再请求 me → 401（服务端已撤销）
    client.cookies.set("yiban_user_session", token)
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_rejects_forged_token_401(client):
    """伪造签名 Token → 401。"""
    forged = pyjwt.encode(
        {
            "sub": "u",
            "jti": "j",
            "aud": "user",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        "wrong-secret-key-0123456789abcdef",
        algorithm="HS256",
    )
    client.cookies.set("yiban_user_session", forged)
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_rejects_expired_session_401(client):
    """JWT 未过期但会话 expires_at 已过期 → 401。"""
    assert _register(client, "expired@test.com").status_code == 201
    login_resp = _login(client, "expired@test.com")
    token = _extract_cookie_token(login_resp)

    _expire_sessions("expired@test.com")
    client.cookies.set("yiban_user_session", token)
    assert client.get("/api/v1/auth/me").status_code == 401


def test_login_cookie_attributes(client):
    """登录响应 Set-Cookie：HttpOnly、SameSite=Lax、Path=/。"""
    assert _register(client, "cookie@test.com").status_code == 201
    r = _login(client, "cookie@test.com")
    set_cookie = r.headers.get("set-cookie", "")
    assert "yiban_user_session=" in set_cookie
    assert "httponly" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()
    assert "path=/" in set_cookie.lower()
