"""认证业务服务（任务 2：仅注册）。"""

import asyncio

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.user import User, normalize_email
from repository.user_repository import UserRepository
from schemas.auth import RegisterRequest, RegisterResponse
from utils.custom_exceptions import ConflictException
from utils.security import SecurityUtil


class AuthService:
    """认证业务。登录/会话留任务 3。"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)

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
        await self.user_repo.create(user)
        try:
            await self.db.commit()
        except IntegrityError:
            # 并发下唯一约束兜底
            await self.db.rollback()
            raise ConflictException("该邮箱已注册") from None

        return RegisterResponse(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=user.role,
        )
