"""账号数据库基础（不接真实数据库）。

覆盖：email 规范化、UTC 时间工具、User 物理结构、数据库启用配置校验、日志脱敏。
数据库集成测试（迁移/约束/事务/时间往返）见 test_account_db_integration.py。
"""

from datetime import datetime, timezone

import pytest

from core import database
from models.user import User, normalize_email, utcnow


def test_normalize_email_strips_and_lowers():
    assert normalize_email("  Foo@Bar.COM  ") == "foo@bar.com"
    assert normalize_email("User@Example.com") == "user@example.com"
    assert normalize_email("a@b.co") == "a@b.co"


def test_utcnow_returns_naive_utc():
    now = utcnow()
    assert now.tzinfo is None
    utc_now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    assert abs((utc_now_naive - now).total_seconds()) < 5


def test_user_physical_structure():
    cols = User.__table__.columns

    id_col = cols["id"]
    assert id_col.primary_key is True
    assert id_col.type.length == 36

    email = cols["email"]
    assert email.type.length == 255
    assert email.nullable is False
    assert email.unique is True

    pw = cols["password_hash"]
    assert pw.type.length == 255
    assert pw.nullable is False

    name = cols["display_name"]
    assert name.type.length == 100
    assert name.nullable is False

    role = cols["role"]
    assert role.type.length == 16
    assert role.nullable is False
    assert role.default.arg == "user"

    for col_name in ("created_at", "updated_at"):
        c = cols[col_name]
        assert c.nullable is False
        assert c.type.fsp == 6  # DATETIME(6)，无时区 UTC naive


def test_redact_url_hides_credentials():
    url = "mysql+pymysql://user:secret@localhost:3306/yiban_api_dev"
    redacted = database._redact_url(url)
    assert "secret" not in redacted
    assert "user" not in redacted
    assert "localhost" in redacted
    assert "yiban_api_dev" in redacted


@pytest.mark.asyncio
async def test_create_database_pool_rejects_teacher_sample_db(monkeypatch):
    from config import settings

    monkeypatch.setattr(
        settings,
        "database_url",
        "mysql+pymysql://dev_user:123456@localhost:3306/api_security_demo",
    )
    with pytest.raises(ValueError, match="教师示例库"):
        await database.create_database_pool()


@pytest.mark.asyncio
async def test_create_database_pool_rejects_missing_url(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "database_url", None)
    with pytest.raises(ValueError, match="未配置 DATABASE_URL"):
        await database.create_database_pool()
