"""DEBUG 环境变量与 debug 字段冲突的回归测试。

配置在导入时初始化并缓存（config/config_factory.py 的 lru_cache），且项目
env_file 使用绝对路径，故用隔离子进程验证环境变量与 dotenv 行为，避免导入
顺序、本机 .env 或环境变量污染测试结论。
"""

import json
import os
import subprocess
import sys


def _run_py(script: str, env: dict) -> subprocess.CompletedProcess:
    """在干净子进程中运行脚本；显式清除 DEBUG/YIBAN_DEBUG，再按需注入。"""
    merged = {
        k: v
        for k, v in os.environ.items()
        if k not in ("DEBUG", "YIBAN_DEBUG")
    }
    merged.update(env)
    return subprocess.run(
        [sys.executable, "-c", script],
        env=merged,
        capture_output=True,
        text=True,
    )


def _check_config(
    cls: str,
    process_env: dict,
    dotenv_content: str | None = None,
    extra_kwargs: str = "",
) -> dict:
    """在子进程中实例化配置类，返回属性/导出/extra 的核对结果。

    - dotenv_content 为 None 时用 _env_file=None 禁用 dotenv；
    - 否则写入临时 dotenv 文件并显式以 _env_file 传入，避免依赖本机 .env。
    """
    if dotenv_content is None:
        ctor = f"{cls}(_env_file=None{', ' + extra_kwargs if extra_kwargs else ''})"
        header = ""
        footer = ""
    else:
        ctor = f"{cls}(_env_file=f.name{', ' + extra_kwargs if extra_kwargs else ''})"
        header = (
            "import tempfile, os\n"
            "f = tempfile.NamedTemporaryFile('w', suffix='.env', delete=False)\n"
            f"f.write({dotenv_content!r})\n"
            "f.close()\n"
        )
        footer = "\nos.unlink(f.name)"
    script = (
        header
        + f"from config.config_unified import {cls}\n"
        + f"c = {ctor}\n"
        + "d = c.model_dump()\n"
        + "import json\n"
        + "print(json.dumps({\n"
        + "    'attr': c.debug,\n"
        + "    'attr_type': type(c.debug).__name__,\n"
        + "    'dump': d.get('debug'),\n"
        + "    'dump_type': type(d.get('debug')).__name__,\n"
        + "    'extra_debug': any(k.lower() == 'debug' for k in (c.model_extra or {})),\n"
        + "    'has_debug_key': 'debug' in d,\n"
        + "    'has_yiban_key': 'YIBAN_DEBUG' in d,\n"
        + "}))\n"
        + footer
    )
    result = _run_py(script, process_env)
    assert result.returncode == 0, f"stderr={result.stderr!r}"
    return json.loads(result.stdout.strip())


def _read_debug(env: dict) -> str:
    return _run_py("from config import settings; print(settings.debug)", env).stdout.strip()


def test_generic_debug_release_does_not_break_import():
    """通用 DEBUG=release 不应导致配置导入失败；显式 YIBAN_DEBUG=true 读取为 True bool。"""
    result = _run_py(
        "from config import settings; print(settings.debug, type(settings.debug).__name__)",
        {"FASTAPI_ENV": "development", "DEBUG": "release", "YIBAN_DEBUG": "true"},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "True bool"


def test_yiban_debug_true_false():
    assert _read_debug({"FASTAPI_ENV": "development", "YIBAN_DEBUG": "true"}) == "True"
    assert _read_debug({"FASTAPI_ENV": "development", "YIBAN_DEBUG": "false"}) == "False"


def test_yiban_debug_priority_over_generic_debug():
    """YIBAN_DEBUG 与通用 DEBUG 同时存在时，属性与导出均为 bool 且一致。"""
    info = _check_config("DevelopmentConfig", {"YIBAN_DEBUG": "false", "DEBUG": "release"})
    assert info["attr"] is False and info["attr_type"] == "bool"
    assert info["dump"] is False and info["dump_type"] == "bool"
    assert info["extra_debug"] is False


def test_environment_defaults_without_yiban_debug():
    """未配置 YIBAN_DEBUG 且禁用 dotenv 时，各环境保持原有默认值且为 bool。"""
    for env_cls, expected in (
        ("DevelopmentConfig", True),
        ("TestingConfig", True),
        ("StagingConfig", False),
    ):
        info = _check_config(env_cls, {})
        assert info["attr"] is expected and info["attr_type"] == "bool", env_cls
        assert info["dump"] is expected and info["dump_type"] == "bool", env_cls
    # production 存在独立的 docs_url/redoc_url/openapi_url=None 必填缺陷
    # （预先存在、非本轮引入），显式补齐三个 None 单独验证 debug 默认值。
    info = _check_config(
        "ProductionConfig",
        {},
        extra_kwargs="docs_url=None, redoc_url=None, openapi_url=None",
    )
    assert info["attr"] is False and info["attr_type"] == "bool"


def test_each_environment_yiban_debug_toggle_and_docker():
    """各环境可用 YIBAN_DEBUG 取反覆盖默认值；DockerConfig 继承该行为。"""
    for env_cls, default in (
        ("DevelopmentConfig", True),
        ("TestingConfig", True),
        ("StagingConfig", False),
        ("DockerConfig", True),
    ):
        override = "false" if default else "true"
        info = _check_config(env_cls, {"YIBAN_DEBUG": override})
        assert info["attr"] is (not default), env_cls
        assert info["attr_type"] == "bool", env_cls


def test_invalid_yiban_debug_rejected():
    """非法 YIBAN_DEBUG 仍应明确报校验错误，而非静默转为默认值。"""
    result = _run_py(
        "from config import settings; print(settings.debug)",
        {"FASTAPI_ENV": "development", "YIBAN_DEBUG": "notabool"},
    )
    assert result.returncode != 0
    assert result.stderr.strip()


def test_app_imports_and_health_under_debug_release():
    """DEBUG=release 下真实应用入口可导入，健康检查正常。"""
    script = (
        "from fastapi.testclient import TestClient\n"
        "from app import create_app\n"
        "with TestClient(create_app()) as client:\n"
        "    r = client.get('/health')\n"
        "    print(r.status_code, r.json().get('mode'), r.json().get('business_ready'))\n"
    )
    result = _run_py(script, {"FASTAPI_ENV": "development", "DEBUG": "release"})
    assert result.returncode == 0, result.stderr
    assert "200 bootstrap False" in result.stdout


def test_legacy_dotenv_debug_does_not_pollute_export():
    """旧 dotenv DEBUG 不得以小写键进入 extra，从而遮蔽 debug 字段导出。"""
    info = _check_config(
        "DevelopmentConfig",
        {"DEBUG": "release", "YIBAN_DEBUG": "false"},
        dotenv_content="DEBUG=true\n",
    )
    assert info["attr"] is False and info["attr_type"] == "bool"
    assert info["dump"] is False and info["dump_type"] == "bool"
    assert info["extra_debug"] is False
    assert info["has_debug_key"] is True
    assert info["has_yiban_key"] is False


def test_legacy_debug_alone_consistent():
    """仅旧 dotenv DEBUG 存在（无 YIBAN_DEBUG）时，属性与导出仍一致为 bool 默认值。"""
    info = _check_config("DevelopmentConfig", {}, dotenv_content="DEBUG=true\n")
    assert info["attr"] is True and info["attr_type"] == "bool"
    assert info["dump"] is True and info["dump_type"] == "bool"
    assert info["extra_debug"] is False


def test_dotenv_yiban_debug_process_priority():
    """进程 YIBAN_DEBUG 优先于 dotenv 同名变量。"""
    info = _check_config(
        "DevelopmentConfig",
        {"YIBAN_DEBUG": "false"},
        dotenv_content="YIBAN_DEBUG=true\n",
    )
    assert info["attr"] is False and info["attr_type"] == "bool"
    assert info["dump"] is False and info["dump_type"] == "bool"


def test_template_generates_yiban_debug():
    """配置模板生成器应输出 YIBAN_DEBUG 及正确生成值，而非旧 DEBUG（显式配置值）。"""
    script = (
        "from config.manage import generate_env_template\n"
        "t = generate_env_template('development')\n"
        "lines = t.splitlines()\n"
        "print(any(l.startswith('YIBAN_DEBUG=') for l in lines), "
        "any(l.startswith('DEBUG=') for l in lines))\n"
        "print([l for l in lines if l.startswith('YIBAN_DEBUG=')])\n"
    )
    result = _run_py(script, {"FASTAPI_ENV": "development", "YIBAN_DEBUG": "true"})
    assert result.returncode == 0, result.stderr
    lines = result.stdout.strip().splitlines()
    assert lines[0] == "True False"  # 有 YIBAN_DEBUG、无独立 DEBUG 行
    assert lines[1] == "['YIBAN_DEBUG=true']"  # 显式 YIBAN_DEBUG=true 的生成值
