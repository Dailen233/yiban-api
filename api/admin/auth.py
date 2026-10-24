"""管理员认证接口（任务 4）。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from core.cookies import delete_session_cookie, set_session_cookie
from core.csrf import require_trusted_origin
from core.permissions import ADMIN_SESSION_COOKIE, require_admin, require_auth_enabled
from models.user import User
from schemas.auth import LoginRequest, UserResponse
from service.auth_service import AuthService
from service.dependencies import get_auth_service

router = APIRouter(prefix="/admin/auth", tags=["管理员认证"])


@router.post(
    "/login",
    response_model=UserResponse,
    dependencies=[Depends(require_auth_enabled), Depends(require_trusted_origin)],
)
async def login(
    payload: LoginRequest,
    response: Response,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> UserResponse:
    """管理员登录：验凭据 + 检查 role=admin，签发 aud=admin 会话 + Cookie。"""
    admin, token = await auth_service.admin_login(payload)
    set_session_cookie(response, ADMIN_SESSION_COOKIE, token)
    return admin


@router.get("/me", response_model=UserResponse)
async def me(
    admin: Annotated[User, Depends(require_admin)],
) -> UserResponse:
    """返回当前管理员身份（以数据库记录为准）。"""
    return UserResponse(
        id=admin.id,
        email=admin.email,
        display_name=admin.display_name,
        role=admin.role,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_auth_enabled), Depends(require_trusted_origin)],
)
async def logout(
    request: Request,
    response: Response,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    _admin: Annotated[User, Depends(require_admin)],
) -> None:
    """管理员退出：撤销当前 admin 会话 jti + 清除管理员 Cookie，返回 204。"""
    token = request.cookies.get(ADMIN_SESSION_COOKIE, "")
    await auth_service.logout(token, aud="admin")
    delete_session_cookie(response, ADMIN_SESSION_COOKIE)
