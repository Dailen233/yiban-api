"""管理员创建 CLI 集成测试（需真实 MySQL 8.4 译伴专用测试库）。

通过 subprocess 以 stdin 输入驱动 scripts/create_admin.py，验证创建、重复邮箱、
密码不一致与教师示例库拒绝。只读 TEST_DATABASE_URL。
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from core import database as db
from core.database import ensure_test_database
from models.user import User
from utils.security import SecurityUtil

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="需要 TEST_DATABASE_URL 指向译伴专用测试库 yiban_api_test",
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module", autouse=True)
def _guard_test_db():
    ensure_test_database(TEST_DATABASE_URL)


def _run_alembic(*args: str) -> subprocess.CompletedProcess:
    merged = dict(
        os.environ,
        DATABASE_URL=TEST_DATABASE_URL,
        FASTAPI_ENV="development",
        DATABASE_ENABLED="false",
    )
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=ROOT,
        env=merged,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def prepared_schema():
    r = _run_alembic("upgrade", "head")
    assert r.returncode == 0, r.stderr
    yield
    r = _run_alembic("downgrade", "base")
    assert r.returncode == 0, r.stderr


def _run_cli(stdin_text: str, database_url: str) -> subprocess.CompletedProcess:
    merged = dict(
        os.environ, DATABASE_URL=database_url, FASTAPI_ENV="development"
    )
    return subprocess.run(
        [sys.executable, "-m", "scripts.create_admin"],
        cwd=ROOT,
        env=merged,
        input=stdin_text,
        capture_output=True,
        text=True,
    )


def _fetch_user(email: str) -> User | None:
    with Session(create_engine(TEST_DATABASE_URL)) as s:
        return s.execute(select(User).where(User.email == email)).scalar_one_or_none()


def _create_user(
    email: str,
    role: str = "user",
    password: str = "userpassword1",
    display_name: str = "U",
) -> None:
    with Session(create_engine(TEST_DATABASE_URL)) as s:
        s.add(
            User(
                email=email,
                password_hash=SecurityUtil.hash_password(password),
                display_name=display_name,
                role=role,
            )
        )
        s.commit()


def test_create_admin_creates_admin(prepared_schema):
    r = _run_cli(
        "cli-admin@test.com\nCLI Admin\npassword123\npassword123\n",
        TEST_DATABASE_URL,
    )
    assert r.returncode == 0, r.stderr
    assert "cli-admin@test.com" in r.stdout

    user = _fetch_user("cli-admin@test.com")
    assert user is not None
    assert user.role == "admin"
    assert SecurityUtil.verify_password("password123", user.password_hash)


def test_create_admin_duplicate_email_does_not_overwrite(prepared_schema):
    first = _run_cli(
        "dup@test.com\nDup\npassword123\npassword123\n", TEST_DATABASE_URL
    )
    assert first.returncode == 0, first.stderr
    original_hash = _fetch_user("dup@test.com").password_hash

    second = _run_cli(
        "dup@test.com\nDup\nnewpassword456\nnewpassword456\n", TEST_DATABASE_URL
    )
    assert second.returncode == 1
    assert "已存在" in second.stderr

    # 未覆盖密码、未静默提升角色（仍是原记录）
    user = _fetch_user("dup@test.com")
    assert user.password_hash == original_hash
    assert user.role == "admin"


def test_create_admin_password_mismatch(prepared_schema):
    r = _run_cli(
        "mismatch@test.com\nM\npassword123\ndifferent456\n", TEST_DATABASE_URL
    )
    assert r.returncode == 1
    assert "不一致" in r.stderr
    assert _fetch_user("mismatch@test.com") is None


def test_create_admin_rejects_teacher_sample_db(prepared_schema):
    r = _run_cli(
        "",
        "mysql+pymysql://u:p@127.0.0.1:3306/api_security_demo",
    )
    assert r.returncode == 1
    assert "教师示例库" in r.stderr


def test_create_admin_duplicate_existing_user_unchanged(prepared_schema):
    """已有 role=user 账号，再用相同规范化邮箱创建管理员 → 失败且原账号不变。"""
    _create_user("existing@test.com", role="user", password="userpassword1")
    original = _fetch_user("existing@test.com")

    # 相同邮箱（大小写 + 首尾空格）经规范化后命中已有账号
    r = _run_cli(
        "  EXISTING@TEST.COM \nExisting Admin\nadminpass123\nadminpass123\n",
        TEST_DATABASE_URL,
    )
    assert r.returncode == 1
    assert "已存在" in r.stderr

    after = _fetch_user("existing@test.com")
    assert after.id == original.id
    assert after.role == "user"
    assert after.password_hash == original.password_hash
