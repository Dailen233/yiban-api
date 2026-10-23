"""受控创建管理员账号的 CLI 脚本。

运行方式（密码经 getpass 隐藏输入，不通过命令行参数传递）：
    uv run python -m scripts.create_admin

复用现有 ``user`` 表、RegisterRequest 校验、bcrypt 哈希与事务机制；
连接数据库遵守明确译伴 DATABASE_URL 与教师示例库拒绝规则。
"""

import sys
from getpass import getpass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from config import settings
from core.database import is_teacher_sample_db
from models.user import User
from schemas.auth import RegisterRequest
from utils.security import SecurityUtil


def _validate(email: str, password: str, display_name: str) -> RegisterRequest | None:
    """复用注册校验；失败仅输出安全提示，不打印原始输入/密码/哈希。"""
    try:
        return RegisterRequest(
            email=email, password=password, display_name=display_name
        )
    except ValidationError as exc:
        for err in exc.errors():
            field = ".".join(str(loc) for loc in err.get("loc", []) if loc != "body")
            print(f"校验失败：{field} {err.get('msg')}", file=sys.stderr)
        return None


def _create_admin(engine, payload: RegisterRequest) -> int:
    with Session(engine) as session:
        existing = session.execute(
            select(User).where(User.email == payload.email)
        ).scalar_one_or_none()
        if existing is not None:
            print(
                f"邮箱 {payload.email} 已存在（当前角色: {existing.role}），"
                "未创建、未覆盖密码",
                file=sys.stderr,
            )
            return 1

        admin = User(
            email=payload.email,
            password_hash=SecurityUtil.hash_password(payload.password),
            display_name=payload.display_name,
            role="admin",
        )
        session.add(admin)
        session.commit()
        print(f"管理员已创建：{admin.email}（id={admin.id}，role={admin.role}）")
        return 0


def main() -> int:
    url = settings.database_url
    if not url:
        print("未配置 DATABASE_URL，无法创建管理员", file=sys.stderr)
        return 1
    if is_teacher_sample_db(url):
        print("不能使用教师示例库（api_security_*）创建管理员", file=sys.stderr)
        return 1

    email = input("管理员邮箱: ").strip()
    display_name = input("显示名: ").strip()
    password = getpass("密码: ")
    if password != getpass("再次输入密码: "):
        print("两次输入的密码不一致", file=sys.stderr)
        return 1

    payload = _validate(email, password, display_name)
    if payload is None:
        return 1

    engine = create_engine(url)
    try:
        return _create_admin(engine, payload)
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
