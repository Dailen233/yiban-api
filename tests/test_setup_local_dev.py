"""scripts/setup_local_dev.py 的回归测试。

使用临时目录与资源状态替身，覆盖重复执行不覆盖、错误目标库、凭据不一致、
配置丢失但资源仍存在等路径。绝不接触真实 .env.dev-db / .env.dev-api。
"""

from pathlib import Path

import pytest

import scripts.setup_local_dev as setup


def _write(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _db_lines(user="yiban", password="dbpw123456", port="3307") -> list[str]:
    return [
        "MYSQL_ROOT_PASSWORD=rootpw123456",
        "MYSQL_DATABASE=yiban_api_dev",
        "MYSQL_USER=" + user,
        "MYSQL_PASSWORD=" + password,
        "MYSQL_PORT=" + port,
    ]


def _api_lines(
    db_user="yiban",
    db_password="dbpw123456",
    db_port="3307",
    db="yiban_api_dev",
    secret="s" * 48,
    cors=None,
) -> list[str]:
    url = f"mysql+pymysql://{db_user}:{db_password}@127.0.0.1:{db_port}/{db}?charset=utf8mb4"
    if cors is None:
        cors = '["http://localhost:5173","http://localhost:5174"]'
    return [
        "FASTAPI_ENV=development",
        "DATABASE_ENABLED=true",
        "AUTH_ENABLED=true",
        "DATABASE_URL=" + url,
        "JWT_SECRET_KEY=" + secret,
        "CORS_ORIGINS='" + cors + "'",
        "TRUSTED_ORIGINS='" + cors + "'",
        "ALLOWED_HOSTS='[\"localhost\",\"127.0.0.1\"]'",
        "HOST=127.0.0.1",
        "PORT=8001",
    ]


def test_duplicate_run_does_not_overwrite(tmp_path, capsys):
    db = tmp_path / ".env.dev-db"
    api = tmp_path / ".env.dev-api"
    _write(db, _db_lines(password="dbpw123456"))
    _write(api, _api_lines(db_password="dbpw123456", secret="k" * 48))
    db_before = db.read_text()
    api_before = api.read_text()

    assert setup.main(root=tmp_path, probe=lambda: "absent") == 0
    assert db.read_text() == db_before
    assert api.read_text() == api_before
    # 权限收紧到 600
    assert (db.stat().st_mode & 0o777) == 0o600
    assert (api.stat().st_mode & 0o777) == 0o600


def test_api_url_points_to_test_db_rejected(tmp_path, capsys):
    db = tmp_path / ".env.dev-db"
    api = tmp_path / ".env.dev-api"
    _write(db, _db_lines())
    _write(api, _api_lines(db="yiban_api_test"))

    assert setup.main(root=tmp_path, probe=lambda: "absent") == 1
    out = capsys.readouterr().err
    assert "yiban_api_test" in out


def test_api_url_points_to_teacher_db_rejected(tmp_path, capsys):
    db = tmp_path / ".env.dev-db"
    api = tmp_path / ".env.dev-api"
    _write(db, _db_lines())
    _write(api, _api_lines(db="api_security_demo"))

    assert setup.main(root=tmp_path, probe=lambda: "absent") == 1
    assert "教师示例库" in capsys.readouterr().err


def test_api_credential_mismatch_rejected(tmp_path, capsys):
    db = tmp_path / ".env.dev-db"
    api = tmp_path / ".env.dev-api"
    _write(db, _db_lines(password="dbpw123456"))
    _write(api, _api_lines(db_password="DIFFERENT-password"))

    assert setup.main(root=tmp_path, probe=lambda: "absent") == 1
    assert "密码" in capsys.readouterr().err


def test_api_origin_wrong_rejected(tmp_path, capsys):
    db = tmp_path / ".env.dev-db"
    api = tmp_path / ".env.dev-api"
    _write(db, _db_lines())
    _write(api, _api_lines(cors='["http://evil.example.com"]'))

    assert setup.main(root=tmp_path, probe=lambda: "absent") == 1
    assert "CORS_ORIGINS" in capsys.readouterr().err


def test_db_missing_api_exists_stops(tmp_path, capsys):
    api = tmp_path / ".env.dev-api"
    _write(api, _api_lines())

    assert setup.main(root=tmp_path, probe=lambda: "absent") == 1
    # 不自动生成新数据库密码
    assert not (tmp_path / ".env.dev-db").exists()


def test_db_missing_resource_exists_stops(tmp_path, capsys):
    assert setup.main(root=tmp_path, probe=lambda: "exists") == 1
    assert not (tmp_path / ".env.dev-db").exists()


def test_db_missing_resource_unknown_stops(tmp_path, capsys):
    assert setup.main(root=tmp_path, probe=lambda: "unknown") == 1
    assert not (tmp_path / ".env.dev-db").exists()


def test_first_run_generates_both(tmp_path):
    assert setup.main(root=tmp_path, probe=lambda: "absent") == 0

    db = tmp_path / ".env.dev-db"
    api = tmp_path / ".env.dev-api"
    assert db.exists() and api.exists()
    assert (db.stat().st_mode & 0o777) == 0o600
    assert (api.stat().st_mode & 0o777) == 0o600

    # 生成的 API 配置与数据库配置一致，且通过脚本自身校验
    from sqlalchemy.engine import make_url

    db_data = setup._read_env(db)
    api_data = setup._read_env(api)
    url = make_url(api_data["DATABASE_URL"])
    assert url.database == "yiban_api_dev"
    assert url.host == "127.0.0.1"
    assert str(url.port) == db_data["MYSQL_PORT"] == "3307"
    assert url.username == db_data["MYSQL_USER"] == "yiban"
    assert url.password == db_data["MYSQL_PASSWORD"]
    assert setup._check_api_env(api_data, db_data) == []
