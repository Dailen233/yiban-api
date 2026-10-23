"""账号数据库基础（不接真实数据库）。

覆盖：email 规范化、UTC 时间工具、User 物理结构、数据库启用配置校验、日志脱敏。
数据库集成测试（迁移/约束/事务/时间往返）见 test_account_db_integration.py。
"""

from datetime import datetime, timedelta, timezone

import pytest

from core import database
from core.database import ensure_test_database, get_database_name, is_teacher_sample_db
from models.types import UTCDateTime
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
        assert isinstance(c.type, UTCDateTime)  # DATETIME(6) UTC 语义列


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


@pytest.mark.asyncio
async def test_create_database_pool_connection_failure_releases_engine(monkeypatch):
    """连接失败时引擎被释放、全局状态不残留。"""
    from config import settings

    # 指向本机未监听端口，触发连接失败
    monkeypatch.setattr(
        settings,
        "database_url",
        "mysql+pymysql://u:p@127.0.0.1:65530/yiban_api_test",
    )
    # 显式清零全局状态，确保测试独立
    monkeypatch.setattr(database, "async_engine", None)
    monkeypatch.setattr(database, "AsyncSessionLocal", None)

    with pytest.raises(Exception):
        await database.create_database_pool()

    assert database.async_engine is None
    assert database.AsyncSessionLocal is None


def test_utcdatetime_bind_converts_aware_to_naive_utc():
    """应用层把带 +08:00 偏移的 aware 时间转 UTC naive，保留微秒。"""
    t = UTCDateTime()
    aware = datetime(2026, 10, 23, 18, 0, 0, 123456, tzinfo=timezone(timedelta(hours=8)))
    bound = t.process_bind_param(aware, None)
    assert bound.tzinfo is None
    assert bound == datetime(2026, 10, 23, 10, 0, 0, 123456)


def test_utcdatetime_result_restores_utc_semantics():
    """应用层读回 naive 时标记为 aware UTC。"""
    t = UTCDateTime()
    naive = datetime(2026, 10, 23, 10, 0, 0, 123456)
    result = t.process_result_value(naive, None)
    assert result.tzinfo is timezone.utc
    assert result.replace(tzinfo=None) == naive


def test_get_database_name_parses_structurally():
    assert get_database_name("mysql+pymysql://u:p@h/yiban_api_test") == "yiban_api_test"
    assert get_database_name("mysql+pymysql://u:p@h:3306/yiban_api_dev") == "yiban_api_dev"
    assert get_database_name("mysql+pymysql://u:p@h/api_security_demo") == "api_security_demo"


def test_is_teacher_sample_db_by_db_name():
    assert is_teacher_sample_db("mysql+pymysql://u:p@h/api_security_demo") is True
    assert is_teacher_sample_db("mysql+pymysql://u:p@h/yiban_api_test") is False


@pytest.mark.parametrize(
    "url",
    [
        "mysql+pymysql://u:p@h/yiban_api_dev",
        "mysql+pymysql://u:p@h/api_security_demo",
        "mysql+pymysql://u:p@h/yiban_api_prod",
        "mysql+pymysql://u:p@h/other_db",
    ],
)
def test_ensure_test_database_rejects_non_test_db(url):
    with pytest.raises(ValueError, match="yiban_api_test"):
        ensure_test_database(url)


def test_ensure_test_database_rejects_invalid_url():
    with pytest.raises(ValueError, match="无效的数据库 URL"):
        ensure_test_database("not-a-valid-url")


def test_ensure_test_database_accepts_test_db():
    assert ensure_test_database("mysql+pymysql://u:p@h/yiban_api_test") == "yiban_api_test"
