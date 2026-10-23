"""会话/鉴权基础测试（无需数据库）。

覆盖：密钥校验、JWT 签发/验签（aud/exp/声明/伪造）、登录/me/退出 HTTP 行为、
Cookie 属性、CSRF/Origin 复用。HTTP 层通过依赖替换隔离数据库。
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from app import create_app
from config import settings
from core.token import (
    create_session_token,
    decode_session_token,
    validate_jwt_secret_key,
)
from utils.custom_exceptions import AuthenticationException

RANDOM_SECRET = "test-random-secret-key-0123456789-abcdef"  # ≥32 字节
VALID_ORIGIN = "http://localhost:5173"


@pytest.fixture(autouse=True)
def _random_secret(monkeypatch):
    monkeypatch.setattr(settings, "effective_jwt_secret_key", RANDOM_SECRET)


def _expires(minutes: int = 5) -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


# ---- 密钥校验 ----

def test_validate_secret_rejects_empty():
    with pytest.raises(ValueError):
        validate_jwt_secret_key("")
    with pytest.raises(ValueError):
        validate_jwt_secret_key(None)


@pytest.mark.parametrize(
    "secret",
    [
        "your-secret-key-change-in-production",
        "dev-secret-key-not-for-production-use-only",
        "test-secret-key-for-testing-only",
        "staging-secret-key-must-be-changed",
        "${PROD_SECRET_KEY}",
    ],
)
def test_validate_secret_rejects_weak(secret):
    with pytest.raises(ValueError):
        validate_jwt_secret_key(secret)


def test_validate_secret_rejects_short():
    with pytest.raises(ValueError):
        validate_jwt_secret_key("short-key")


def test_validate_secret_accepts_random():
    validate_jwt_secret_key(RANDOM_SECRET)


# ---- JWT 签发/验签 ----

def test_session_token_roundtrip():
    token = create_session_token(sub="u1", jti="j1", aud="user", expires_at=_expires())
    payload = decode_session_token(token, aud="user")
    assert payload["sub"] == "u1"
    assert payload["jti"] == "j1"
    assert payload["aud"] == "user"


def test_session_token_rejects_wrong_audience():
    token = create_session_token(sub="u1", jti="j1", aud="user", expires_at=_expires())
    with pytest.raises(AuthenticationException):
        decode_session_token(token, aud="admin")


def test_session_token_rejects_expired():
    expires = datetime.now(timezone.utc) - timedelta(minutes=1)
    token = create_session_token(sub="u1", jti="j1", aud="user", expires_at=expires)
    with pytest.raises(AuthenticationException):
        decode_session_token(token, aud="user")


def test_session_token_rejects_forged():
    forged = jwt.encode(
        {"sub": "u1", "jti": "j1", "aud": "user", "exp": _expires()},
        "wrong-secret-key-0123456789-abcdef",
        algorithm="HS256",
    )
    with pytest.raises(AuthenticationException):
        decode_session_token(forged, aud="user")


def test_session_token_requires_claims():
    missing_jti = jwt.encode(
        {"sub": "u1", "aud": "user", "exp": _expires()},
        RANDOM_SECRET,
        algorithm="HS256",
    )
    with pytest.raises(AuthenticationException):
        decode_session_token(missing_jti, aud="user")


# ---- HTTP 层（依赖替换，隔离数据库）----

def _auth_client(monkeypatch, service, current_user=None):
    from service.dependencies import get_auth_service

    app = create_app()

    async def svc_override():
        return service

    app.dependency_overrides[get_auth_service] = svc_override

    if current_user is not None:
        from core.permissions import get_current_user

        async def user_override():
            return current_user

        app.dependency_overrides[get_current_user] = user_override

    return TestClient(app, base_url="http://localhost")


class _LoginService:
    async def login(self, payload):
        raise AuthenticationException("邮箱或密码错误")


def test_login_invalid_credentials_returns_401(monkeypatch):
    client = _auth_client(monkeypatch, _LoginService())
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "a@b.com", "password": "wrong-password"},
        headers={"Origin": VALID_ORIGIN, "X-Yiban-Request": "1"},
    )
    assert r.status_code == 401


class _OkLoginService:
    async def login(self, payload):
        from schemas.auth import UserResponse

        return (
            UserResponse(
                id="u1", email="a@b.com", display_name="A", role="user"
            ),
            "test-token",
        )


def test_login_sets_http_only_cookie_and_no_token_in_body(monkeypatch):
    client = _auth_client(monkeypatch, _OkLoginService())
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "a@b.com", "password": "password123"},
        headers={"Origin": VALID_ORIGIN, "X-Yiban-Request": "1"},
    )
    assert r.status_code == 200
    assert r.json()["role"] == "user"
    set_cookie = r.headers.get("set-cookie", "")
    assert "yiban_user_session=test-token" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie.lower() or "samesite=lax" in set_cookie.lower()
    assert "test-token" not in r.text  # JWT 仅在 Cookie，不回传 body


def test_login_requires_csrf_origin(monkeypatch):
    client = _auth_client(monkeypatch, _OkLoginService())
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "a@b.com", "password": "password123"},
    )
    assert r.status_code == 403


class _UserStub:
    id = "u1"
    email = "a@b.com"
    display_name = "A"
    role = "user"


def test_me_returns_current_user(monkeypatch):
    client = _auth_client(
        monkeypatch, _LoginService(), current_user=_UserStub()
    )
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 200
    assert r.json() == {
        "id": "u1",
        "email": "a@b.com",
        "display_name": "A",
        "role": "user",
    }


class _LogoutService:
    async def logout(self, token):
        return None


def test_logout_returns_204_and_clears_cookie(monkeypatch):
    client = _auth_client(
        monkeypatch, _LogoutService(), current_user=_UserStub()
    )
    client.cookies.set("yiban_user_session", "test-token")
    r = client.post(
        "/api/v1/auth/logout",
        headers={"Origin": VALID_ORIGIN, "X-Yiban-Request": "1"},
    )
    assert r.status_code == 204
    assert "yiban_user_session" in r.headers.get("set-cookie", "")
