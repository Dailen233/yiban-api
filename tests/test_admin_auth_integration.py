"""管理员认证集成测试（需真实 MySQL 8.4 译伴专用测试库）。

覆盖：管理员登录/me/退出闭环、角色校验、双端隔离、跨端 Token 错配、
角色降级、会话持久化、AUTH_ENABLED 关闭。只读 TEST_DATABASE_URL。
"""

import asyncio
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from core import database as db
from core.database import ensure_test_database
from models.user import User
from models.user_session import UserSession
from utils.security import SecurityUtil

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
    from config import settings
    from app import create_app

    monkeypatch.setattr(settings, "database_enabled", True)
    monkeypatch.setattr(settings, "database_url", TEST_DATABASE_URL)
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "effective_jwt_secret_key", SECRET)
    with TestClient(create_app(), base_url="http://localhost") as c:
        yield c


def _create_user(email, role="user", password="password123", display_name="T"):
    async def _go():
        engine = create_async_engine(db._to_async_url(TEST_DATABASE_URL))
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as s:
                s.add(
                    User(
                        email=email,
                        password_hash=SecurityUtil.hash_password(password),
                        display_name=display_name,
                        role=role,
                    )
                )
                await s.commit()
        finally:
            await engine.dispose()

    asyncio.run(_go())


def _set_role(email: str, role: str) -> None:
    async def _go():
        engine = create_async_engine(db._to_async_url(TEST_DATABASE_URL))
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as s:
                user = (
                    await s.execute(select(User).where(User.email == email))
                ).scalar_one()
                user.role = role
                await s.commit()
        finally:
            await engine.dispose()

    asyncio.run(_go())


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


def _extract_cookie(resp, name: str) -> str:
    set_cookie = resp.headers.get("set-cookie", "")
    for part in set_cookie.split(","):
        part = part.strip()
        if part.startswith(f"{name}="):
            return part.split("=", 1)[1].split(";", 1)[0]
    raise AssertionError(f"未找到 cookie {name}")


def _admin_login(client, email, password="password123"):
    return client.post(
        "/api/v1/admin/auth/login",
        json={"email": email, "password": password},
        headers={"Origin": VALID_ORIGIN, "X-Yiban-Request": "1"},
    )


def test_admin_login_me_logout_flow(client):
    _create_user("admin@test.com", role="admin")

    r = _admin_login(client, "admin@test.com")
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "admin@test.com"
    assert body["role"] == "admin"
    assert "password" not in r.text
    assert "yiban_admin_session" in r.headers.get("set-cookie", "")

    assert client.get("/api/v1/admin/auth/me").status_code == 200

    r = client.post(
        "/api/v1/admin/auth/logout",
        headers={"Origin": VALID_ORIGIN, "X-Yiban-Request": "1"},
    )
    assert r.status_code == 204
    assert client.get("/api/v1/admin/auth/me").status_code == 401


def test_admin_login_wrong_password_401(client):
    _create_user("awrong@test.com", role="admin")
    assert _admin_login(client, "awrong@test.com", password="wrong-pass").status_code == 401


def test_admin_login_nonexistent_email_401(client):
    assert _admin_login(client, "ghost-admin@test.com").status_code == 401


def test_admin_login_non_admin_403(client):
    """凭据正确但角色是普通用户 → 403。"""
    _create_user("plain@test.com", role="user")
    r = _admin_login(client, "plain@test.com")
    assert r.status_code == 403


def test_admin_me_without_cookie_401(client):
    assert client.get("/api/v1/admin/auth/me").status_code == 401


def test_admin_login_persists_session_type_admin(client):
    _create_user("persist-admin@test.com", role="admin")
    assert _admin_login(client, "persist-admin@test.com").status_code == 200

    sessions = _fetch_sessions("persist-admin@test.com")
    assert len(sessions) == 1
    assert sessions[0].session_type == "admin"
    assert sessions[0].revoked_at is None


def test_admin_logout_revokes_token_immediately(client):
    _create_user("revoke-admin@test.com", role="admin")
    login_resp = _admin_login(client, "revoke-admin@test.com")
    token = _extract_cookie(login_resp, "yiban_admin_session")

    assert client.get("/api/v1/admin/auth/me").status_code == 200

    assert (
        client.post(
            "/api/v1/admin/auth/logout",
            headers={"Origin": VALID_ORIGIN, "X-Yiban-Request": "1"},
        ).status_code
        == 204
    )

    assert _fetch_sessions("revoke-admin@test.com")[0].revoked_at is not None
    client.cookies.set("yiban_admin_session", token)
    assert client.get("/api/v1/admin/auth/me").status_code == 401


def test_dual_login_isolated_sessions(client):
    """同一管理员同时登录两端：独立 Cookie/jti/会话，退出一端不影响另一端。"""
    _create_user("dual@test.com", role="admin")

    # 用户端登录
    user_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "dual@test.com", "password": "password123"},
        headers={"Origin": VALID_ORIGIN, "X-Yiban-Request": "1"},
    )
    user_token = _extract_cookie(user_resp, "yiban_user_session")

    # 管理端登录
    admin_resp = _admin_login(client, "dual@test.com")
    admin_token = _extract_cookie(admin_resp, "yiban_admin_session")

    assert user_token != admin_token
    assert len(_fetch_sessions("dual@test.com")) == 2

    # 用户端退出 → 原 user token 立即 401，管理员 me 仍 200
    client.cookies.clear()
    client.cookies.set("yiban_user_session", user_token)
    assert (
        client.post(
            "/api/v1/auth/logout",
            headers={"Origin": VALID_ORIGIN, "X-Yiban-Request": "1"},
        ).status_code
        == 204
    )
    client.cookies.set("yiban_user_session", user_token)
    assert client.get("/api/v1/auth/me").status_code == 401
    client.cookies.clear()
    client.cookies.set("yiban_admin_session", admin_token)
    assert client.get("/api/v1/admin/auth/me").status_code == 200

    # 重新登录用户端 → 退出管理端 → 原 admin token 401，用户 me 仍 200
    client.cookies.clear()
    user_resp2 = client.post(
        "/api/v1/auth/login",
        json={"email": "dual@test.com", "password": "password123"},
        headers={"Origin": VALID_ORIGIN, "X-Yiban-Request": "1"},
    )
    user_token2 = _extract_cookie(user_resp2, "yiban_user_session")

    client.cookies.clear()
    client.cookies.set("yiban_admin_session", admin_token)
    assert (
        client.post(
            "/api/v1/admin/auth/logout",
            headers={"Origin": VALID_ORIGIN, "X-Yiban-Request": "1"},
        ).status_code
        == 204
    )
    client.cookies.set("yiban_admin_session", admin_token)
    assert client.get("/api/v1/admin/auth/me").status_code == 401
    client.cookies.clear()
    client.cookies.set("yiban_user_session", user_token2)
    assert client.get("/api/v1/auth/me").status_code == 200


def test_admin_role_downgraded_403(client):
    """管理员数据库角色改为普通用户后，旧管理员会话访问管理接口 → 403。"""
    _create_user("downgrade@test.com", role="admin")
    login_resp = _admin_login(client, "downgrade@test.com")
    token = _extract_cookie(login_resp, "yiban_admin_session")

    assert client.get("/api/v1/admin/auth/me").status_code == 200

    _set_role("downgrade@test.com", "user")

    client.cookies.set("yiban_admin_session", token)
    assert client.get("/api/v1/admin/auth/me").status_code == 403


def test_cross_endpoint_token_rejected(client):
    """用户端 Token 填入管理员 Cookie（反之亦然）→ 401（aud 绑定拒绝）。"""
    _create_user("cross@test.com", role="admin")

    user_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "cross@test.com", "password": "password123"},
        headers={"Origin": VALID_ORIGIN, "X-Yiban-Request": "1"},
    )
    user_token = _extract_cookie(user_resp, "yiban_user_session")

    admin_resp = _admin_login(client, "cross@test.com")
    admin_token = _extract_cookie(admin_resp, "yiban_admin_session")

    # 用户 Token 填入管理员 Cookie → admin me 401
    client.cookies.clear()
    client.cookies.set("yiban_admin_session", user_token)
    assert client.get("/api/v1/admin/auth/me").status_code == 401

    # 管理员 Token 填入用户 Cookie → user me 401
    client.cookies.clear()
    client.cookies.set("yiban_user_session", admin_token)
    assert client.get("/api/v1/auth/me").status_code == 401


def test_admin_login_cookie_attributes(client):
    _create_user("cookie-admin@test.com", role="admin")
    r = _admin_login(client, "cookie-admin@test.com")
    set_cookie = r.headers.get("set-cookie", "")
    assert "yiban_admin_session=" in set_cookie
    assert "httponly" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()
    assert "path=/" in set_cookie.lower()


def test_admin_auth_disabled_503_no_session(prepared_schema, monkeypatch):
    """鉴权关闭、数据库开启：管理员三个接口 503，登录不新增会话。"""
    from config import settings
    from app import create_app

    monkeypatch.setattr(settings, "database_enabled", True)
    monkeypatch.setattr(settings, "database_url", TEST_DATABASE_URL)
    monkeypatch.setattr(settings, "auth_enabled", False)
    monkeypatch.setattr(settings, "effective_jwt_secret_key", SECRET)

    _create_user("off-admin@test.com", role="admin")

    with TestClient(create_app(), base_url="http://localhost") as c:
        assert _admin_login(c, "off-admin@test.com").status_code == 503
        assert c.get("/api/v1/admin/auth/me").status_code == 503
        assert (
            c.post(
                "/api/v1/admin/auth/logout",
                headers={"Origin": VALID_ORIGIN, "X-Yiban-Request": "1"},
            ).status_code
            == 503
        )

    assert len(_fetch_sessions("off-admin@test.com")) == 0
