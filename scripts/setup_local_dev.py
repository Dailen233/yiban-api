"""生成本地账号联调的私有配置（.env.dev-db / .env.dev-api）。

仅首次生成、防覆盖；文件已存在时复用并校验，不重新生成密码/密钥。权限 600。
脚本只输出文件名与结果，不打印密码、JWT 密钥或带凭据 URL。

运行（项目根目录）：
    uv run python scripts/setup_local_dev.py
"""

import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_ENV = ROOT / ".env.dev-db"
API_ENV = ROOT / ".env.dev-api"

DEV_DB = "yiban_api_dev"
DEV_PORT = "3307"
DEV_USER = "yiban"


def _write_env(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def _read_env(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def _ensure_db_env() -> bool:
    if DB_ENV.exists():
        data = _read_env(DB_ENV)
        if data.get("MYSQL_DATABASE", DEV_DB) != DEV_DB:
            print(f"{DB_ENV.name} 的 MYSQL_DATABASE 不是 {DEV_DB}，请检查", file=sys.stderr)
            return False
        if not data.get("MYSQL_PASSWORD"):
            print(f"{DB_ENV.name} 缺少 MYSQL_PASSWORD，请检查", file=sys.stderr)
            return False
        print(f"{DB_ENV.name} 已存在，复用（不重新生成密码）")
        return True

    _write_env(
        DB_ENV,
        [
            "MYSQL_ROOT_PASSWORD=" + secrets.token_urlsafe(24),
            "MYSQL_DATABASE=" + DEV_DB,
            "MYSQL_USER=" + DEV_USER,
            "MYSQL_PASSWORD=" + secrets.token_urlsafe(24),
            "MYSQL_PORT=" + DEV_PORT,
        ],
    )
    print(f"已生成 {DB_ENV.name}（随机凭据，权限 600）")
    return True


def _ensure_api_env() -> bool:
    if not DB_ENV.exists():
        print(f"{DB_ENV.name} 不存在，无法生成 {API_ENV.name}", file=sys.stderr)
        return False

    db = _read_env(DB_ENV)
    db_user = db.get("MYSQL_USER", DEV_USER)
    db_password = db.get("MYSQL_PASSWORD", "")
    db_port = db.get("MYSQL_PORT", DEV_PORT)

    if API_ENV.exists():
        data = _read_env(API_ENV)
        problems = []
        if data.get("FASTAPI_ENV", "development") != "development":
            problems.append("FASTAPI_ENV 不是 development")
        if data.get("DATABASE_ENABLED", "").lower() != "true":
            problems.append("DATABASE_ENABLED 不是 true")
        if data.get("AUTH_ENABLED", "").lower() != "true":
            problems.append("AUTH_ENABLED 不是 true")
        secret = data.get("JWT_SECRET_KEY", "")
        if len(secret.encode("utf-8")) < 32:
            problems.append("JWT_SECRET_KEY 缺失或不足 32 字节")
        if problems:
            for p in problems:
                print(f"{API_ENV.name} 校验失败：{p}", file=sys.stderr)
            return False
        print(f"{API_ENV.name} 已存在，复用（不重新生成密钥）")
        return True

    if not db_password:
        print(f"{DB_ENV.name} 缺少 MYSQL_PASSWORD", file=sys.stderr)
        return False

    # 只在首次生成时把凭据 URL 写入私有文件；不打印
    db_url = (
        f"mysql+pymysql://{db_user}:{db_password}@127.0.0.1:{db_port}/{DEV_DB}"
        "?charset=utf8mb4"
    )
    _write_env(
        API_ENV,
        [
            "FASTAPI_ENV=development",
            "DATABASE_ENABLED=true",
            "AUTH_ENABLED=true",
            "DATABASE_URL=" + db_url,
            "JWT_SECRET_KEY=" + secrets.token_urlsafe(48),
            # 单引号包裹 JSON 数组：uv --env-file 会剥离外层单引号但保留内部双引号，
            # 从而得到合法 JSON；若直接写双引号，uv 会剥离内部双引号导致解析失败。
            "CORS_ORIGINS='[\"http://localhost:5173\",\"http://localhost:5174\"]'",
            "TRUSTED_ORIGINS='[\"http://localhost:5173\",\"http://localhost:5174\"]'",
            "ALLOWED_HOSTS='[\"localhost\",\"127.0.0.1\"]'",
            "HOST=127.0.0.1",
            "PORT=8001",
        ],
    )
    print(f"已生成 {API_ENV.name}（随机 JWT 密钥，权限 600）")
    return True


def main() -> int:
    if not _ensure_db_env():
        return 1
    if not _ensure_api_env():
        return 1
    print("本地联调配置就绪")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
