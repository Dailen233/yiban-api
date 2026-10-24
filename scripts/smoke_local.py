"""本地账号联调安全冒烟（httpx 内存 Cookie jar，不输出任何敏感值）。

仅输出状态码与必要身份字段；不打印请求密码、Cookie 值、Set-Cookie 原文、JWT
或带凭据 URL。使用随机邮箱与随机密码；覆盖 /health、注册→登录→me→退出→再次
me(401) 与三个预留前端 Origin 的 CORS 预检。

运行（后端已启动后）：
    uv run --env-file .env.dev-api --locked python scripts/smoke_local.py
"""

import secrets
import sys

import httpx

BASE_URL = "http://localhost:8001"
ORIGINS = [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:5175",
]


def _rand_email() -> str:
    return f"smoke-{secrets.token_hex(6)}@test.com"


def _rand_password() -> str:
    return "Smoke-" + secrets.token_urlsafe(9)


def main() -> int:
    email = _rand_email()
    password = _rand_password()
    failures: list[str] = []

    with httpx.Client(base_url=BASE_URL) as c:
        r = c.get("/health")
        print(f"/health -> {r.status_code} status={r.json().get('status')}")
        if r.status_code != 200 or r.json().get("status") != "ok":
            failures.append("health")

        r = c.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password, "display_name": "smoke"},
            headers={"Origin": ORIGINS[0], "X-Yiban-Request": "1"},
        )
        body = r.json()
        print(f"register -> {r.status_code} role={body.get('role')}")
        if r.status_code != 201 or body.get("role") != "user":
            failures.append("register")

        r = c.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
            headers={"Origin": ORIGINS[0], "X-Yiban-Request": "1"},
        )
        has_cookie = "yiban_user_session" in c.cookies
        print(f"login -> {r.status_code} has_cookie={has_cookie}")
        if r.status_code != 200 or not has_cookie:
            failures.append("login")

        r = c.get("/api/v1/auth/me")
        print(f"me -> {r.status_code} role={r.json().get('role')}")
        if r.status_code != 200:
            failures.append("me")

        r = c.post(
            "/api/v1/auth/logout",
            headers={"Origin": ORIGINS[0], "X-Yiban-Request": "1"},
        )
        print(f"logout -> {r.status_code}")
        if r.status_code != 204:
            failures.append("logout")

        r = c.get("/api/v1/auth/me")
        print(f"me after logout -> {r.status_code}")
        if r.status_code != 401:
            failures.append("me_after_logout")

    for origin in ORIGINS:
        r = httpx.options(
            BASE_URL + "/api/v1/auth/login",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "x-yiban-request, content-type",
            },
        )
        allow = r.headers.get("access-control-allow-origin")
        print(f"OPTIONS {origin} -> {r.status_code} allow={allow}")
        if r.status_code != 200 or allow != origin:
            failures.append(f"preflight:{origin}")

    if failures:
        print(f"SMOKE_FAIL: {failures}", file=sys.stderr)
        return 1
    print("SMOKE_OK: 冒烟全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
