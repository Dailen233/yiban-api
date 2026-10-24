"""create user_session table

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_session",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("user.id"),
            nullable=False,
        ),
        sa.Column("jti", sa.String(36), nullable=False, unique=True),
        sa.Column(
            "session_type",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'user'"),
        ),
        sa.Column("expires_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("revoked_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
    )
    op.create_index("ix_user_session_user_id", "user_session", ["user_id"])


def downgrade() -> None:
    # 直接删表：MySQL 会一并清理外键约束及其所需索引（先删索引会被 FK 拒绝）
    op.drop_table("user_session")
