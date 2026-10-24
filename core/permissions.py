"""鉴权依赖。

``get_current_user`` / ``get_current_admin`` 真实实现：验签 + 查库验证会话与身份，
以数据库记录为准；``require_admin`` 额外查库确认当前 role=admin。
尚未实施的教学权限入口继续默认拒绝（解除与 ``get_current_user`` 的别名关系，
避免误放行）。
"""

from datetime import datetime, timezone
from typing import Any, NoReturn

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from core.database import get_async_session
from core.token import decode_session_token
from models.user import User
from models.user_session import UserSession
from utils.custom_exceptions import AuthenticationException

USER_SESSION_COOKIE = "yiban_user_session"
ADMIN_SESSION_COOKIE = "yiban_admin_session"


async def require_auth_enabled() -> None:
    """鉴权开关未启用时拒绝（503），先于任何数据库访问。

    关闭鉴权时 login/me/logout 均返回 503；即使数据库也关闭，也不会因解析
    数据库依赖而返回 500。
    """
    if not settings.auth_enabled:
        raise HTTPException(status_code=503, detail="鉴权服务未启用")


async def _get_session_by_jti(db: AsyncSession, jti: str) -> UserSession | None:
    result = await db.execute(
        select(UserSession).where(UserSession.jti == jti)
    )
    return result.scalar_one_or_none()


async def _authenticate(
    request: Request,
    db: AsyncSession,
    cookie_name: str,
    aud: str,
    session_type: str,
) -> User:
    """从指定 Cookie 验签 JWT 并查库验证会话与身份，返回数据库中的用户。

    验证链：签名/exp/aud/sub/jti → 会话存在、未撤销、未过期 → jti/sub 与
    session 一致 → session_type 匹配 → user 存在。身份与角色以数据库为准。
    """
    token = request.cookies.get(cookie_name)
    if not token:
        raise HTTPException(status_code=401, detail="未认证")

    try:
        payload = decode_session_token(token, aud=aud)
    except AuthenticationException as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    jti = str(payload.get("jti") or "")
    session = await _get_session_by_jti(db, jti)
    if session is None:
        raise HTTPException(status_code=401, detail="会话不存在")
    if session.revoked_at is not None:
        raise HTTPException(status_code=401, detail="会话已退出")
    if session.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="会话已过期")
    if session.jti != jti or session.user_id != str(payload.get("sub") or ""):
        raise HTTPException(status_code=401, detail="会话与令牌不匹配")
    if session.session_type != session_type:
        raise HTTPException(status_code=401, detail="会话类型不匹配")

    user = await db.get(User, session.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_async_session),
) -> User:
    """用户端鉴权（Cookie=yiban_user_session, aud=user, session_type=user）。"""
    return await _authenticate(
        request, db, USER_SESSION_COOKIE, aud="user", session_type="user"
    )


async def get_current_admin(
    request: Request,
    db: AsyncSession = Depends(get_async_session),
) -> User:
    """管理员会话鉴权（Cookie=yiban_admin_session, aud=admin, session_type=admin）。"""
    return await _authenticate(
        request, db, ADMIN_SESSION_COOKIE, aud="admin", session_type="admin"
    )


async def require_admin(request: Request) -> User:
    """真实管理员鉴权：验签 + 查库验证会话，并确认当前 role=admin。

    无有效认证/Token/会话绑定错误 → 401；已认证但数据库角色不足 → 403。
    单独作为依赖使用时，AUTH_ENABLED 关闭先返回 503（先于数据库访问，不因
    解析数据库依赖而 500）。
    """
    if not settings.auth_enabled:
        raise HTTPException(status_code=503, detail="鉴权服务未启用")

    from core.database import AsyncSessionLocal

    if AsyncSessionLocal is None:
        raise HTTPException(status_code=503, detail="数据库未初始化")

    async with AsyncSessionLocal() as db:
        admin = await _authenticate(
            request, db, ADMIN_SESSION_COOKIE, aud="admin", session_type="admin"
        )
        if admin.role != "admin":
            raise HTTPException(status_code=403, detail="需要管理员权限")
        return admin


async def _unimplemented_permission() -> NoReturn:
    """尚未实施的教学权限入口，默认拒绝。"""
    raise HTTPException(status_code=503, detail="该权限入口尚未接入")


# 模板兼容名：全部解除与 get_current_user 的别名关系，避免误放行。
get_current_sso_user = _unimplemented_permission
get_current_active_user = _unimplemented_permission
require_teacher = _unimplemented_permission
require_student = _unimplemented_permission


class PermissionChecker:
    """占位检查器不授予任何角色或资源访问权限。"""

    @staticmethod
    def check_user_access_to_resource(*args: Any, **kwargs: Any) -> bool:
        return False

    @staticmethod
    def check_admin_permission(*args: Any, **kwargs: Any) -> bool:
        return False

    @staticmethod
    def check_teacher_permission(*args: Any, **kwargs: Any) -> bool:
        return False


def check_resource_ownership(resource_owner_id: str, resource_type: str = "general"):
    """属主校验未接入时，返回默认拒绝的依赖。"""
    return _unimplemented_permission
