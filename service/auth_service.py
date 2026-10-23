"""认证业务服务（注册 + 登录/退出）。"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from core.token import create_session_token, decode_session_token
from models.user import User, normalize_email
from models.user_session import UserSession
from repository.user_repository import UserRepository
from repository.user_session_repository import UserSessionRepository
from schemas.auth import (
    LoginRequest,
    RegisterRequest,
    RegisterResponse,
    UserResponse,
)
from utils.custom_exceptions import AuthenticationException, ConflictException
from utils.security import SecurityUtil


def _is_email_unique_conflict(exc: IntegrityError) -> bool:
    """判断 IntegrityError 是否为 email 唯一约束冲突（MySQL 1062 Duplicate entry）。

    仅当错误码为 1062 且消息含 email 键名时才视为重复邮箱；其他完整性错误不吞掉。
    """
    orig = getattr(exc, "orig", None)
    if orig is None:
        return False
    args = getattr(orig, "args", ())
    if not args or args[0] != 1062:
        return False
    return "email" in str(args[1] if len(args) > 1 else args)


class AuthService:
    """认证业务：注册、登录、退出。"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)
        self.session_repo = UserSessionRepository(db)

    async def register(self, payload: RegisterRequest) -> RegisterResponse:
        """注册普通用户：查重 → bcrypt 哈希 → 落库，服务端固定 role='user'。"""
        email = normalize_email(payload.email)
        existing = await self.user_repo.get_by_email(email)
        if existing is not None:
            raise ConflictException("该邮箱已注册")

        # bcrypt 是同步 CPU 密集操作，经线程池执行不阻塞事件循环
        password_hash = await asyncio.to_thread(
            SecurityUtil.hash_password, payload.password
        )
        user = User(
            email=email,
            password_hash=password_hash,
            display_name=payload.display_name,
            role="user",  # 忽略请求体 role，服务端固定普通角色
        )
        try:
            # add + flush 与 commit 均处于异常边界内，flush 阶段唯一冲突不绕过捕获
            await self.user_repo.create(user)
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            if _is_email_unique_conflict(exc):
                raise ConflictException("该邮箱已注册") from None
            raise

        return RegisterResponse(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=user.role,
        )

    async def login(self, payload: LoginRequest) -> tuple[UserResponse, str]:
        """登录：查库验密码（不泄露账号存在性），签发 JWT + 持久化会话。"""
        if not settings.auth_enabled:
            # 服务层防御：开关关闭不得绕过路由签发真实会话
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="鉴权服务未启用")
        email = normalize_email(payload.email)
        user = await self.user_repo.get_by_email(email)
        if user is None:
            raise AuthenticationException("邮箱或密码错误")
        # bcrypt 校验经线程池执行，不阻塞事件循环
        valid = await asyncio.to_thread(
            SecurityUtil.verify_password, payload.password, user.password_hash
        )
        if not valid:
            raise AuthenticationException("邮箱或密码错误")

        jti = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=settings.access_token_expire_minutes
        )
        token = create_session_token(
            sub=user.id, jti=jti, aud="user", expires_at=expires_at
        )
        session = UserSession(
            user_id=user.id,
            jti=jti,
            session_type="user",
            expires_at=expires_at,
        )
        await self.session_repo.create(session)
        await self.db.commit()

        return (
            UserResponse(
                id=user.id,
                email=user.email,
                display_name=user.display_name,
                role=user.role,
            ),
            token,
        )

    async def logout(self, token: str) -> None:
        """退出：撤销当前会话 jti（幂等）。"""
        payload = decode_session_token(token, aud="user")
        jti = str(payload.get("jti") or "")
        session = await self.session_repo.get_by_jti(jti)
        if session is not None and session.revoked_at is None:
            session.revoked_at = datetime.now(timezone.utc)
            await self.db.commit()
