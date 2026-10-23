"""注册接口基础测试（无需数据库）。"""

import asyncio

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.requests import Request

from app import create_app
from config import settings
from core.csrf import require_trusted_origin
from schemas.auth import RegisterRequest

VALID_ORIGIN = "http://localhost:5173"


def _client() -> TestClient:
    return TestClient(create_app(), base_url="http://localhost")


def _payload(**overrides):
    data = {"email": "a@b.com", "password": "password123", "display_name": "A"}
    data.update(overrides)
    return data


# ---- Schema 校验（Pydantic，无需数据库）----

def test_register_request_normalizes_email():
    r = RegisterRequest(
        email="  Foo@Bar.COM ", password="password123", display_name="Foo"
    )
    assert r.email == "foo@bar.com"
    assert r.password == "password123"  # 密码原样，不 strip/lower
    assert r.display_name == "Foo"


def test_register_request_rejects_invalid_email():
    with pytest.raises(ValidationError):
        RegisterRequest(email="not-an-email", password="password123", display_name="A")


def test_register_request_rejects_short_password():
    with pytest.raises(ValidationError):
        RegisterRequest(email="a@b.com", password="short", display_name="A")


def test_register_request_rejects_overlong_password_bytes():
    # 25 个中文字符 × 3 字节 = 75 字节 > 72，超限拒绝而非截断
    with pytest.raises(ValidationError):
        RegisterRequest(email="a@b.com", password="密" * 25, display_name="A")


def test_register_request_accepts_72_byte_password():
    r = RegisterRequest(email="a@b.com", password="a" * 72, display_name="A")
    assert len(r.password.encode("utf-8")) == 72


def test_register_request_rejects_blank_display_name():
    with pytest.raises(ValidationError):
        RegisterRequest(email="a@b.com", password="password123", display_name="   ")


def test_register_request_rejects_overlong_display_name():
    with pytest.raises(ValidationError):
        RegisterRequest(
            email="a@b.com", password="password123", display_name="名" * 101
        )


# ---- CSRF/Origin 校验（TestClient，无需数据库）----

def test_register_rejects_missing_origin():
    r = _client().post("/api/v1/auth/register", json=_payload())
    assert r.status_code == 403


def test_register_rejects_untrusted_origin():
    r = _client().post(
        "/api/v1/auth/register",
        json=_payload(),
        headers={"Origin": "http://evil.com", "X-Yiban-Request": "1"},
    )
    assert r.status_code == 403


def test_register_rejects_missing_csrf_header():
    r = _client().post(
        "/api/v1/auth/register", json=_payload(), headers={"Origin": VALID_ORIGIN}
    )
    assert r.status_code == 403


def test_register_rejects_invalid_csrf_header_value():
    r = _client().post(
        "/api/v1/auth/register",
        json=_payload(),
        headers={"Origin": VALID_ORIGIN, "X-Yiban-Request": "0"},
    )
    assert r.status_code == 403


def _make_request(headers: dict) -> Request:
    scope = {
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
    }
    return Request(scope)


def test_require_trusted_origin_rejects_missing_origin():
    with pytest.raises(HTTPException) as ei:
        asyncio.run(require_trusted_origin(_make_request({}), "1"))
    assert ei.value.status_code == 403


def test_require_trusted_origin_rejects_untrusted_origin():
    with pytest.raises(HTTPException) as ei:
        asyncio.run(
            require_trusted_origin(
                _make_request({"origin": "http://evil.com"}), "1"
            )
        )
    assert ei.value.status_code == 403


def test_require_trusted_origin_rejects_missing_header():
    with pytest.raises(HTTPException) as ei:
        asyncio.run(
            require_trusted_origin(_make_request({"origin": VALID_ORIGIN}), None)
        )
    assert ei.value.status_code == 403


def test_require_trusted_origin_accepts_valid():
    """可信 Origin + X-Yiban-Request: 1 通过校验（不抛 403）。"""
    asyncio.run(require_trusted_origin(_make_request({"origin": VALID_ORIGIN}), "1"))


# ---- 配置 ----

def test_trusted_origins_are_explicit():
    assert settings.trusted_origins and "*" not in settings.trusted_origins


def test_cors_origins_are_explicit():
    assert settings.cors_origins and "*" not in settings.cors_origins
