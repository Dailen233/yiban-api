"""用户会话仓储（单条数据访问）。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.user_session import UserSession


class UserSessionRepository:
    """user_session 表单条访问。事务边界由 Service 控制。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, session: UserSession) -> UserSession:
        """新增单条（add + flush 生成 UUID 主键），不 commit。"""
        self.db.add(session)
        await self.db.flush()
        return session

    async def get_by_jti(self, jti: str) -> UserSession | None:
        """按 jti 查单条；无则返回 None。"""
        result = await self.db.execute(
            select(UserSession).where(UserSession.jti == jti)
        )
        return result.scalar_one_or_none()
