# 本地账号联调环境

供译伴前端联调使用的最小本地环境：独立开发库 `yiban_api_dev` + 私有配置 + 复用启动命令。账号接口实现保持不变。

## 资源边界

| 项 | 开发实例 | 测试实例（勿混用） |
|---|---|---|
| Compose 项目名 | `yiban-api-dev` | 默认项目名（`yiban-api`） |
| 容器名 | `yiban-mysql-84-dev` | `yiban-mysql-84-test` |
| 端口 | `127.0.0.1:3307` | `127.0.0.1:3308` |
| 数据库 | `yiban_api_dev` | `yiban_api_test` |
| 数据卷 | `yiban_mysql_dev_data` | `yiban_mysql_test_data` |
| 配置文件 | `docker-compose.dev.yml` + `.env.dev-db` | `docker-compose.mysql.yml` + `.env.test-db` |

开发实例仅用于本地账号联调；集成验收仍使用测试实例，二者凭据与数据卷互不影响。

## 1. 初始化私有配置（首次）

生成被 Git 忽略的 `.env.dev-db`、`.env.dev-api`（随机密码与 JWT 密钥，权限 600，不打印内容）。文件已存在时复用并校验，不覆盖、不重新生成。

```bash
cd ~/projects/yiban-api
uv run python scripts/setup_local_dev.py
```

## 2. 启动开发库

Docker 需要 root 权限时，由你在终端输入 sudo 密码（密码不写入命令）：

```bash
sudo docker compose -f docker-compose.dev.yml --env-file .env.dev-db up -d
```

启动后只读确认版本与库名（不打印凭据）：

```bash
sudo docker exec yiban-mysql-84-dev mysql --version
uv run --env-file .env.dev-api --locked python -c \
  "from sqlalchemy.engine import make_url; from config import settings; \
   print('db=', make_url(settings.database_url).database); \
   print('enabled=', settings.database_enabled, settings.auth_enabled); \
   print('env=', settings.environment.value); \
   print('cors=', settings.cors_origins); \
   print('trusted=', settings.trusted_origins)"
```

预期 `db=yiban_api_dev`、`enabled=True True`、`env=development`、Origin 为两个预留前端地址。

## 3. 迁移（仅对开发库）

```bash
uv run --env-file .env.dev-api --locked alembic upgrade head
uv run --env-file .env.dev-api --locked alembic current
```

不要将 `TEST_DATABASE_URL` 指向开发库，也不要对开发库执行 `downgrade`/清库；测试库不做迁移或数据操作。

## 4. 启动后端

```bash
uv run --env-file .env.dev-api --locked uvicorn start:app --host 127.0.0.1 --port 8001 --reload
```

后端地址 `http://127.0.0.1:8001`；`/docs` 与 `/openapi.json` 可用。

## 5. 冒烟验证（Cookie jar，不打印 JWT）

```bash
# 健康检查
curl --noproxy '*' http://127.0.0.1:8001/health

# 注册（替换 <随机邮箱>，密码 ≥8 字符）
curl --noproxy '*' -i -X POST http://127.0.0.1:8001/api/v1/auth/register \
  -H 'Content-Type: application/json' -H 'Origin: http://localhost:5173' -H 'X-Yiban-Request: 1' \
  -d '{"email":"smoke-<随机>@test.com","password":"Smoke1234!","display_name":"smoke"}'

# 登录（Cookie jar 保存会话）
curl --noproxy '*' -i -c /tmp/yiban.cookies -X POST http://127.0.0.1:8001/api/v1/auth/login \
  -H 'Content-Type: application/json' -H 'Origin: http://localhost:5173' -H 'X-Yiban-Request: 1' \
  -d '{"email":"smoke-<随机>@test.com","password":"Smoke1234!"}'

# me（携带 Cookie jar）
curl --noproxy '*' -i -b /tmp/yiban.cookies http://127.0.0.1:8001/api/v1/auth/me

# 退出
curl --noproxy '*' -i -b /tmp/yiban.cookies -c /tmp/yiban.cookies -X POST http://127.0.0.1:8001/api/v1/auth/logout \
  -H 'Origin: http://localhost:5173' -H 'X-Yiban-Request: 1'

# 退出后再次 me 应为 401
curl --noproxy '*' -i -b /tmp/yiban.cookies http://127.0.0.1:8001/api/v1/auth/me

# 两个预留前端 Origin 的 CORS 预检（应为 200 且回显允许 Origin）
for o in http://localhost:5173 http://localhost:5174; do
  curl --noproxy '*' -i -X OPTIONS http://127.0.0.1:8001/api/v1/auth/login \
    -H "Origin: $o" -H 'Access-Control-Request-Method: POST' \
    -H 'Access-Control-Request-Headers: x-yiban-request, content-type'
done
```

## 6. 管理员账号（受控 CLI，不预置密码）

```bash
uv run --env-file .env.dev-api --locked python -m scripts.create_admin
```

按提示输入邮箱、显示名与密码（getpass 隐藏，二次确认）。

## 7. 停止

```bash
sudo docker compose -f docker-compose.dev.yml --env-file .env.dev-db down
```

`down` 保留数据卷；仅删数据时加 `-v`（慎用，会丢失开发数据）。
