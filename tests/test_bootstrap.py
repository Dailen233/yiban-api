"""验证起步工程的边界与真实 HTTP 启动，不包含业务功能占位测试。"""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
import pytest

from app import create_app
from core import cache, database, queue
from core.permissions import get_current_active_user, require_admin


def test_bootstrap_does_not_start_external_services(monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError("基础工程不能启动数据库、缓存或任务队列")

    for module, name in (
        (database, "create_database_pool"),
        (cache, "init_cache"),
        (queue, "start_queue"),
    ):
        monkeypatch.setattr(module, name, forbidden)

    with TestClient(create_app()) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {
            "status": "ok",
            "service": "yiban-api",
            "version": "0.1.0",
            "mode": "bootstrap",
            "business_ready": False,
        }
        assert client.get("/docs").status_code == 200
        schema = client.get("/openapi.json").json()
        assert "/health" in schema["paths"]
        assert "/api/v1/auth/register" in schema["paths"]
        assert database.async_engine is None
        assert cache.cache_manager.backend_type == "uninitialized"


@pytest.mark.parametrize("dependency", [get_current_active_user, require_admin])
@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer arbitrary-token"}])
def test_unimplemented_auth_never_grants_access(dependency, headers):
    app = FastAPI()

    @app.get("/protected")
    async def protected(user=Depends(dependency)):
        raise AssertionError("未接入真实鉴权时不能执行受保护处理")

    with TestClient(app) as client:
        assert client.get("/protected", headers=headers).status_code == 503


def test_uvicorn_bootstrap_over_http(tmp_path):
    """启动独立进程，验证真实 HTTP 与 OpenAPI，并清理进程。"""
    root = Path(__file__).resolve().parents[1]
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    log_path = tmp_path / "uvicorn.log"
    opener = build_opener(ProxyHandler({}))
    env = dict(os.environ, FASTAPI_ENV="development")
    with log_path.open("w+") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "start:app", "--host", "127.0.0.1",
             "--port", str(port), "--no-access-log"],
            cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 20
            while True:
                if process.poll() is not None:
                    pytest.fail("Uvicorn 提前退出：" + log_path.read_text())
                try:
                    with opener.open(f"http://127.0.0.1:{port}/health", timeout=1) as response:
                        assert response.status == 200
                        payload = json.load(response)
                    break
                except URLError:
                    if time.monotonic() >= deadline:
                        pytest.fail("启动超时：" + log_path.read_text())
                    time.sleep(0.1)
            assert payload["mode"] == "bootstrap"
            assert payload["business_ready"] is False
            with opener.open(f"http://127.0.0.1:{port}/openapi.json", timeout=2) as response:
                assert json.load(response)["info"]["title"] == "yiban-api"
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
