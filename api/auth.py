"""认证接口（注册/登录/me/退出）。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from core.cookies import delete_session_cookie, set_session_cookie
from core.csrf import require_trusted_origin
from core.permissions import USER_SESSION_COOKIE, get_current_user, require_auth_enabled
from models.user import User
from schemas.auth import LoginRequest, RegisterRequest, RegisterResponse, UserResponse
from service.auth_service import AuthService
from service.dependencies import get_auth_service

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_trusted_origin)],
)
async def register(
    payload: RegisterRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> RegisterResponse:
    """注册普通用户，服务端固定 role='user'。"""
    return await auth_service.register(payload)


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
    """登录：签发 JWT + 持久化会话，设置用户 Cookie；响应不回传 JWT。"""
    user, token = await auth_service.login(payload)
    set_session_cookie(response, USER_SESSION_COOKIE, token)
    return user


@router.get("/me", response_model=UserResponse, dependencies=[Depends(require_auth_enabled)])
async def me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    """返回当前用户身份（以数据库记录为准，不信任 Token 角色快照）。"""
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        display_name=current_user.display_name,
        role=current_user.role,
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
    _current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """退出：撤销会话 jti + 清除 Cookie，返回 204。"""
    token = request.cookies.get(USER_SESSION_COOKIE, "")
    await auth_service.logout(token, aud="user")
    delete_session_cookie(response, USER_SESSION_COOKIE)
