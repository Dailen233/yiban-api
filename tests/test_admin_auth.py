"""管理员鉴权基础测试（无需数据库）。

覆盖：AUTH_ENABLED 关闭 503、CSRF/Origin、登录 200/401/403、Cookie、me/退出。
HTTP 层通过依赖替换隔离数据库。
"""

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from app import create_app
from config import settings
from core.permissions import require_admin
from utils.custom_exceptions import AuthenticationException

VALID_ORIGIN = "http://localhost:5173"
SECRET = "test-random-secret-key-0123456789-abcdef"


@pytest.fixture(autouse=True)
def _random_secret(monkeypatch):
    monkeypatch.setattr(settings, "effective_jwt_secret_key", SECRET)


class _AdminStub:
    id = "a1"
    email = "admin@test.com"
    display_name = "Admin"
    role = "admin"


class _AdminLoginService:
    def __init__(self, exc=None):
        self.exc = exc

    async def admin_login(self, payload):
        if self.exc:
            raise self.exc
        return _AdminStub(), "admin-token"


class _LogoutService:
    async def logout(self, token, aud="user"):
        return None


def _admin_client(monkeypatch, service=None, current_admin=None):
    from service.dependencies import get_auth_service

    monkeypatch.setattr(settings, "auth_enabled", True)
    app = create_app()

    if service is not None:
        async def svc_override():
            return service

        app.dependency_overrides[get_auth_service] = svc_override

    if current_admin is not None:
        async def admin_override():
            return current_admin

        app.dependency_overrides[require_admin] = admin_override

    return TestClient(app, base_url="http://localhost")


# ---- AUTH_ENABLED 关闭 → 503（先于数据库访问）----

def test_require_admin_standalone_disabled_returns_503(monkeypatch):
    """require_admin 单独依赖：AUTH_ENABLED 关闭先返回 503（不因数据库 500）。"""
    monkeypatch.setattr(settings, "auth_enabled", False)
    app = FastAPI()

    @app.get("/admin-protected")
    async def protected(admin=Depends(require_admin)):
        raise AssertionError("不应到达")

    assert TestClient(app).get("/admin-protected").status_code == 503


def test_admin_login_disabled_returns_503(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", False)
    client = TestClient(create_app(), base_url="http://localhost")
    r = client.post(
        "/api/v1/admin/auth/login",
        json={"email": "a@b.com", "password": "password123"},
        headers={"Origin": VALID_ORIGIN, "X-Yiban-Request": "1"},
    )
    assert r.status_code == 503


def test_admin_me_disabled_returns_503(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", False)
    assert TestClient(create_app(), base_url="http://localhost").get(
        "/api/v1/admin/auth/me"
    ).status_code == 503


def test_admin_logout_disabled_returns_503(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", False)
    client = TestClient(create_app(), base_url="http://localhost")
    r = client.post(
        "/api/v1/admin/auth/logout",
        headers={"Origin": VALID_ORIGIN, "X-Yiban-Request": "1"},
    )
    assert r.status_code == 503


# ---- CSRF / 登录 HTTP 层 ----

def test_admin_login_requires_csrf_origin(monkeypatch):
    client = _admin_client(monkeypatch, _AdminLoginService())
    r = client.post(
        "/api/v1/admin/auth/login",
        json={"email": "admin@test.com", "password": "password123"},
    )
    assert r.status_code == 403


def test_admin_login_options_preflight_passes():
    """合法 OPTIONS 预检由 CORS 中间件放行。"""
    client = TestClient(create_app(), base_url="http://localhost")
    r = client.options(
        "/api/v1/admin/auth/login",
        headers={
            "Origin": VALID_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-yiban-request, content-type",
        },
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == VALID_ORIGIN


def test_admin_login_success_sets_cookie(monkeypatch):
    client = _admin_client(monkeypatch, _AdminLoginService())
    r = client.post(
        "/api/v1/admin/auth/login",
        json={"email": "admin@test.com", "password": "password123"},
        headers={"Origin": VALID_ORIGIN, "X-Yiban-Request": "1"},
    )
    assert r.status_code == 200
    assert r.json()["role"] == "admin"
    assert "yiban_admin_session=" in r.headers.get("set-cookie", "")
    assert "password" not in r.text
    assert "admin-token" not in r.text  # JSON 不回传 JWT


def test_admin_login_invalid_credentials_401(monkeypatch):
    client = _admin_client(
        monkeypatch, _AdminLoginService(exc=AuthenticationException("邮箱或密码错误"))
    )
    r = client.post(
        "/api/v1/admin/auth/login",
        json={"email": "admin@test.com", "password": "wrong-password"},
        headers={"Origin": VALID_ORIGIN, "X-Yiban-Request": "1"},
    )
    assert r.status_code == 401


def test_admin_login_non_admin_403(monkeypatch):
    """凭据正确但角色不是 admin → 403（不泄露为 401）。"""
    client = _admin_client(
        monkeypatch,
        _AdminLoginService(
            exc=HTTPException(status_code=403, detail="需要管理员权限")
        ),
    )
    r = client.post(
        "/api/v1/admin/auth/login",
        json={"email": "user@test.com", "password": "password123"},
        headers={"Origin": VALID_ORIGIN, "X-Yiban-Request": "1"},
    )
    assert r.status_code == 403


# ---- me / 退出 ----

def test_admin_me_returns_admin(monkeypatch):
    client = _admin_client(monkeypatch, current_admin=_AdminStub())
    r = client.get("/api/v1/admin/auth/me")
    assert r.status_code == 200
    assert r.json()["email"] == "admin@test.com"
    assert r.json()["role"] == "admin"


def test_admin_logout_returns_204_and_clears_cookie(monkeypatch):
    client = _admin_client(monkeypatch, _LogoutService(), current_admin=_AdminStub())
    client.cookies.set("yiban_admin_session", "admin-token")
    r = client.post(
        "/api/v1/admin/auth/logout",
        headers={"Origin": VALID_ORIGIN, "X-Yiban-Request": "1"},
    )
    assert r.status_code == 204
    assert "yiban_admin_session" in r.headers.get("set-cookie", "")
