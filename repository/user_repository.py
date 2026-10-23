"""用户仓储（单条数据访问）。

约定：本层仅单条 create/get；事务边界由 Service 控制，本层不 commit。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.user import User


class UserRepository:
    """user 表单条访问。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, user: User) -> User:
        """新增单条（add + flush 生成 UUID 主键），不 commit。"""
        self.db.add(user)
        await self.db.flush()
        return user

    async def get_by_email(self, email: str) -> User | None:
        """按规范化后的 email 查单条；无则返回 None。"""
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()
