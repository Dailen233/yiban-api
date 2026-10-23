"""用户会话模型（任务 3）。

仅保存会话追踪与撤销信息（jti），不保存原始 JWT。
"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base
from models.types import UTCDateTime
from models.user import utcnow


class UserSession(Base):
    """用户会话（user_session）。

    - id            VARCHAR(36) PK，UUID
    - user_id       VARCHAR(36) FK -> user.id，NOT NULL
    - jti           VARCHAR(36) UNIQUE，JWT 的 jti（退出撤销用）
    - session_type  VARCHAR(16) NOT NULL，默认 'user'（'user'/'admin'）
    - expires_at    DATETIME(6) NOT NULL，UTC，与 JWT exp 同一到期时刻
    - revoked_at    DATETIME(6) nullable，退出时间；非空即失效
    - created_at    DATETIME(6) NOT NULL，UTC，登录时间
    """

    __tablename__ = "user_session"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("user.id"), nullable=False, index=True
    )
    jti: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    session_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="user", server_default=text("'user'")
    )
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utcnow
    )
