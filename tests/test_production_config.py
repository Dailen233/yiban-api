"""ProductionConfig 文档字段默认值与生产环境文档禁用行为的回归测试。

配置在导入时初始化并缓存，故用隔离子进程验证；子进程显式控制
FASTAPI_ENV / DEBUG / YIBAN_DEBUG，避免继承本机环境与 .env 影响。
"""

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


def test_production_config_instantiates_without_docs_kwargs():
    """ProductionConfig 无需显式传入文档字段即可实例化，三者均为 None，debug 默认 False。"""
    script = (
        "from config.config_unified import ProductionConfig\n"
        "c = ProductionConfig(_env_file=None)\n"
        "print(c.docs_url, c.redoc_url, c.openapi_url, c.debug, type(c.debug).__name__)\n"
    )
    result = _run_py(script, {})
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "None None None False bool"


def test_production_app_disables_docs_and_serves_health():
    """生产环境真实应用可创建，/health 返回 bootstrap，/docs /redoc /openapi.json 返回 404。"""
    script = (
        "import logging\n"
        "logging.disable(logging.CRITICAL)\n"  # 隔离控制台日志，避免混入 stdout
        "from fastapi.testclient import TestClient\n"
        "from app import create_app\n"
        "app = create_app()\n"
        # production 的 debug=False 启用 TrustedHostMiddleware，仅允许 localhost/127.0.0.1\n"
        "with TestClient(app, base_url='http://localhost') as client:\n"
        "    h = client.get('/health')\n"
        "    d = client.get('/docs')\n"
        "    r = client.get('/redoc')\n"
        "    o = client.get('/openapi.json')\n"
        "    print(h.status_code, h.json().get('mode'), h.json().get('business_ready'))\n"
        "    print(d.status_code, r.status_code, o.status_code)\n"
    )
    result = _run_py(
        script,
        {"FASTAPI_ENV": "production", "YIBAN_DEBUG": "false", "DEBUG": "release"},
    )
    assert result.returncode == 0, result.stderr
    lines = result.stdout.strip().splitlines()
    assert lines[0] == "200 bootstrap False"
    assert lines[1] == "404 404 404"
