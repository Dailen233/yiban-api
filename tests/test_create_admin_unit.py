"""管理员创建 CLI 异常注入单元测试（无需数据库）。

用 FakeSession 注入 commit 阶段异常，验证安全输出、退出状态与回滚/关闭。
"""

import pymysql
from sqlalchemy.exc import IntegrityError, OperationalError

from schemas.auth import RegisterRequest


def _run_with_fake_session(monkeypatch, capsys, commit_exc):
    import scripts.create_admin as cli

    events = {"rolled_back": False, "closed": False}

    class _FakeResult:
        def scalar_one_or_none(self):
            return None

    class _FakeSession:
        def __init__(self, engine):
            pass

        def execute(self, *args, **kwargs):
            return _FakeResult()

        def add(self, obj):
            pass

        def commit(self):
            if commit_exc is not None:
                raise commit_exc

        def rollback(self):
            events["rolled_back"] = True

        def close(self):
            events["closed"] = True

    monkeypatch.setattr(cli, "Session", _FakeSession)

    payload = RegisterRequest(
        email="x@test.com", password="secret-password-123", display_name="X"
    )
    code = cli._create_admin(object(), payload)
    err = capsys.readouterr().err
    return code, err, events


def _dup(email_key: str) -> IntegrityError:
    orig = pymysql.err.IntegrityError(1062, f"Duplicate entry 'x' for key '{email_key}'")
    return IntegrityError("INSERT", {}, orig)


def test_commit_duplicate_email_reports_exists(monkeypatch, capsys):
    code, err, events = _run_with_fake_session(
        monkeypatch, capsys, _dup("user.email")
    )
    assert code == 1
    assert "已存在" in err
    assert "secret-password-123" not in err
    assert events["rolled_back"] is True
    assert events["closed"] is True


def test_commit_other_integrity_not_misreported(monkeypatch, capsys):
    """非 email 唯一冲突不应误报为重复邮箱。"""
    code, err, events = _run_with_fake_session(
        monkeypatch, capsys, _dup("user.id")
    )
    assert code == 1
    assert "完整性错误" in err
    assert "已存在" not in err
    assert "secret-password-123" not in err
    assert events["rolled_back"] is True
    assert events["closed"] is True


def test_commit_other_db_error_generic(monkeypatch, capsys):
    """权限不足等数据库异常：通用失败提示，不泄露错误码/堆栈/密码。"""
    orig = pymysql.err.OperationalError(1142, "INSERT command denied to user")
    exc = OperationalError("INSERT", {}, orig)
    code, err, events = _run_with_fake_session(monkeypatch, capsys, exc)
    assert code == 1
    assert "数据库写入错误" in err
    assert "secret-password-123" not in err
    assert "1142" not in err
    assert "Traceback" not in err
    assert events["rolled_back"] is True
    assert events["closed"] is True
