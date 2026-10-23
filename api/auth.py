"""认证接口（任务 2：注册）。登录/me/退出留任务 3。"""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from core.csrf import require_trusted_origin
from schemas.auth import RegisterRequest, RegisterResponse
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
