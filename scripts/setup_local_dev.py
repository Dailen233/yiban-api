"""生成本地账号联调的私有配置（.env.dev-db / .env.dev-api）。

仅首次生成、防覆盖；文件已存在时复用并校验，不重新生成密码/密钥；权限收紧到 600。
脚本只输出文件名与结果，不打印密码、JWT 密钥或带凭据 URL。

运行（项目根目录）：
    uv run python scripts/setup_local_dev.py
"""

import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]

DEV_DB = "yiban_api_dev"
DEV_HOST = "127.0.0.1"
DEV_PORT = "3307"
DEV_USER = "yiban"
DEV_CONTAINER = "yiban-mysql-84-dev"
DEV_VOLUME = "yiban_mysql_dev_data"
API_ORIGINS = ["http://localhost:5173", "http://localhost:5174"]
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]


def _read_env(path: Path) -> dict[str, str]:
    """用 dotenv 解析（正确处理单/双引号），返回键值映射。"""
    return dict(dotenv_values(str(path)))


def _write_env(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def _tighten_perms(path: Path) -> None:
    if path.exists() and (os.stat(path).st_mode & 0o777) != 0o600:
        os.chmod(path, 0o600)


def _parse_origins(raw: str) -> list[str] | None:
    """把 Origin 值（JSON 数组或逗号分隔）解析为 list；失败返回 None。"""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list) and all(isinstance(x, str) for x in parsed):
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return parts or None


def _check_db_env(db: dict[str, str]) -> list[str]:
    problems: list[str] = []
    if db.get("MYSQL_DATABASE") != DEV_DB:
        problems.append("MYSQL_DATABASE 不是 yiban_api_dev")
    if not db.get("MYSQL_USER"):
        problems.append("缺少 MYSQL_USER")
    if not db.get("MYSQL_PASSWORD"):
        problems.append("缺少 MYSQL_PASSWORD")
    if not db.get("MYSQL_ROOT_PASSWORD"):
        problems.append("缺少 MYSQL_ROOT_PASSWORD")
    if db.get("MYSQL_PORT", "") != DEV_PORT:
        problems.append("MYSQL_PORT 不是 3307")
    return problems


def _check_api_env(api: dict[str, str], db: dict[str, str]) -> list[str]:
    problems: list[str] = []
    if api.get("FASTAPI_ENV", "development") != "development":
        problems.append("FASTAPI_ENV 不是 development")
    if api.get("DATABASE_ENABLED", "").lower() != "true":
        problems.append("DATABASE_ENABLED 不是 true")
    if api.get("AUTH_ENABLED", "").lower() != "true":
        problems.append("AUTH_ENABLED 不是 true")
    secret = api.get("JWT_SECRET_KEY", "")
    if len(secret.encode("utf-8")) < 32:
        problems.append("JWT_SECRET_KEY 缺失或不足 32 字节")

    if _parse_origins(api.get("CORS_ORIGINS", "")) != API_ORIGINS:
        problems.append("CORS_ORIGINS 不是预期的两个前端 Origin（5173/5174）")
    if _parse_origins(api.get("TRUSTED_ORIGINS", "")) != API_ORIGINS:
        problems.append("TRUSTED_ORIGINS 不是预期的两个前端 Origin（5173/5174）")

    raw = api.get("DATABASE_URL", "")
    if not raw:
        problems.append("缺少 DATABASE_URL")
        return problems
    try:
        url = make_url(raw)
    except Exception:
        problems.append("DATABASE_URL 无法解析")
        return problems

    db_name = url.database or ""
    if db_name == "yiban_api_test":
        problems.append("DATABASE_URL 指向测试库 yiban_api_test")
    elif db_name.startswith("api_security_"):
        problems.append("DATABASE_URL 指向教师示例库")
    elif db_name != DEV_DB:
        problems.append("DATABASE_URL 目标库不是 yiban_api_dev")

    if url.host not in ("127.0.0.1", "localhost"):
        problems.append("DATABASE_URL 主机不是本机")
    if str(url.port) != db.get("MYSQL_PORT", DEV_PORT):
        problems.append("DATABASE_URL 端口与数据库配置不一致")
    if url.username != db.get("MYSQL_USER", ""):
        problems.append("DATABASE_URL 用户名与数据库配置不一致")
    if url.password != db.get("MYSQL_PASSWORD", ""):
        problems.append("DATABASE_URL 密码与数据库配置不一致")
    return problems


def _probe_docker_resources() -> str:
    """探测开发容器/数据卷是否存在。

    返回 'exists' / 'absent' / 'unknown'。权限不足或 docker 不可用时返回 'unknown'，
    不把「无法确认」误判为「资源不存在」。
    """
    try:
        r = subprocess.run(
            ["docker", "ps", "-a", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            return "unknown"
        if DEV_CONTAINER in set(r.stdout.split()):
            return "exists"

        r2 = subprocess.run(
            ["docker", "volume", "ls", "--format", "{{.Name}}"],
            capture_output=True, text=True, timeout=10,
        )
        if r2.returncode != 0:
            return "unknown"
        if any(DEV_VOLUME in v for v in r2.stdout.split()):
            return "exists"
        return "absent"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "unknown"


def _ensure_db_env(db_env: Path, api_env: Path, probe) -> bool:
    if db_env.exists():
        data = _read_env(db_env)
        problems = _check_db_env(data)
        if problems:
            for p in problems:
                print(f"{db_env.name} 校验失败：{p}", file=sys.stderr)
            return False
        _tighten_perms(db_env)
        print(f"{db_env.name} 已存在，复用（不重新生成密码）")
        return True

    # 数据库配置缺失：任何可能导致凭据不一致/破坏已有数据的情况都停止，不自动换密码。
    if api_env.exists():
        print(
            f"{db_env.name} 缺失但 {api_env.name} 已存在：为避免凭据不一致，"
            "不自动生成新数据库密码，请手动补齐数据库配置或同时重建两份配置。",
            file=sys.stderr,
        )
        return False

    state = probe()
    if state == "exists":
        print(
            f"{db_env.name} 缺失且检测到开发容器/数据卷已存在：不自动生成新密码，"
            "避免与已有数据卷凭据不一致，请手动补齐数据库配置。",
            file=sys.stderr,
        )
        return False
    if state == "unknown":
        print(
            f"{db_env.name} 缺失且无法确认开发容器/数据卷是否存在（Docker 权限不足或不可用）："
            "为避免破坏已有数据，不自动生成新密码，请用 sudo 确认后再处理。",
            file=sys.stderr,
        )
        return False

    _write_env(
        db_env,
        [
            "MYSQL_ROOT_PASSWORD=" + secrets.token_urlsafe(24),
            "MYSQL_DATABASE=" + DEV_DB,
            "MYSQL_USER=" + DEV_USER,
            "MYSQL_PASSWORD=" + secrets.token_urlsafe(24),
            "MYSQL_PORT=" + DEV_PORT,
        ],
    )
    print(f"已生成 {db_env.name}（随机凭据，权限 600）")
    return True


def _ensure_api_env(db_env: Path, api_env: Path) -> bool:
    if not db_env.exists():
        print(f"{db_env.name} 不存在，无法校验/生成 {api_env.name}", file=sys.stderr)
        return False

    db = _read_env(db_env)

    if api_env.exists():
        data = _read_env(api_env)
        problems = _check_api_env(data, db)
        if problems:
            for p in problems:
                print(f"{api_env.name} 校验失败：{p}", file=sys.stderr)
            return False
        _tighten_perms(api_env)
        print(f"{api_env.name} 已存在，复用（不重新生成密钥）")
        return True

    db_user = db.get("MYSQL_USER", DEV_USER)
    db_password = db.get("MYSQL_PASSWORD", "")
    db_port = db.get("MYSQL_PORT", DEV_PORT)
    # 只在首次生成时把凭据 URL 写入私有文件；不打印
    db_url = (
        f"mysql+pymysql://{db_user}:{db_password}@{DEV_HOST}:{db_port}/{DEV_DB}"
        "?charset=utf8mb4"
    )
    _write_env(
        api_env,
        [
            "FASTAPI_ENV=development",
            "DATABASE_ENABLED=true",
            "AUTH_ENABLED=true",
            "DATABASE_URL=" + db_url,
            "JWT_SECRET_KEY=" + secrets.token_urlsafe(48),
            # 单引号包裹 JSON 数组：uv --env-file 会剥离外层单引号但保留内部双引号，
            # 从而得到合法 JSON；dotenv_values 读取时同样能还原为 JSON 数组字符串。
            "CORS_ORIGINS='[\"http://localhost:5173\",\"http://localhost:5174\"]'",
            "TRUSTED_ORIGINS='[\"http://localhost:5173\",\"http://localhost:5174\"]'",
            "ALLOWED_HOSTS='[\"localhost\",\"127.0.0.1\"]'",
            "HOST=127.0.0.1",
            "PORT=8001",
        ],
    )
    print(f"已生成 {api_env.name}（随机 JWT 密钥，权限 600）")
    return True


def main(root: Path | None = None, probe=None) -> int:
    root = root or ROOT
    if probe is None:
        probe = _probe_docker_resources
    db_env = root / ".env.dev-db"
    api_env = root / ".env.dev-api"

    if not _ensure_db_env(db_env, api_env, probe):
        return 1
    if not _ensure_api_env(db_env, api_env):
        return 1
    print("本地联调配置就绪")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
