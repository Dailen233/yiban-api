"""用户账号模型（任务 1：仅 `user` 表；`user_session` 留任务 3）。"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, text
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base
from models.types import UTCDateTime


def utcnow() -> datetime:
    """返回当前 UTC 时间（naive），用于 DATETIME 无时区列。

    MySQL `DATETIME(6)` 存储不带时区的 UTC 值：写入前转 UTC 并去掉 tzinfo，
    读取后按 UTC 语义解释；API 层再转为带时区的 ISO 8601。
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def normalize_email(email: str) -> str:
    """入库前规范化：strip + lower（仅对 email，不对密码）。"""
    return email.strip().lower()


class User(Base):
    """用户账号。

    物理结构（逻辑类型 enum('user','admin') 落地为 VARCHAR(16) + 应用层校验，
    避免 MySQL ENUM 后续增删角色的 ALTER 成本）：
    - id            VARCHAR(36)   PK，UUID 字符串（服务端生成）
    - email         VARCHAR(255)  UNIQUE、NOT NULL，入库前 strip+lower
    - password_hash VARCHAR(255)  NOT NULL，bcrypt 哈希（绝不明文）
    - display_name  VARCHAR(100)  NOT NULL
    - role          VARCHAR(16)   NOT NULL，默认 'user'（'user'/'admin'，服务端校验）
    - created_at    DATETIME(6)   NOT NULL，无时区 UTC，默认 utcnow
    - updated_at    DATETIME(6)   NOT NULL，无时区 UTC，默认/更新 utcnow
    """

    __tablename__ = "user"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(
        String(16), nullable=False, default="user", server_default=text("'user'")
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utcnow, onupdate=utcnow
    )
