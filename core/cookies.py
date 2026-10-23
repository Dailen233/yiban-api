"""会话 Cookie 设置/删除（用户端与管理端共用）。

Path/Domain 设置与删除保持一致；HttpOnly + SameSite=Lax，生产环境 Secure。
"""

from fastapi import Response

from config import settings


def cookie_secure() -> bool:
    """生产环境 Cookie 必须 Secure；本地 HTTP 开发豁免。"""
    return settings.environment == "production"


def set_session_cookie(response: Response, name: str, token: str) -> None:
    response.set_cookie(
        key=name,
        value=token,
        httponly=True,
        samesite="lax",
        secure=cookie_secure(),
        path="/",
    )


def delete_session_cookie(response: Response, name: str) -> None:
    response.delete_cookie(key=name, path="/")
