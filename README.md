# 译伴共享后端 · yiban-api

基于教师 `sql-to-fastapi-restfulapi-scaffold` 的基础工程，使用 Python 3.12 与 uv。用户端 `yiban-web`、管理端 `yiban-admin` 共用此后端；需求和历史原型位于同级 `bilingual-ebook-generator`。

## 当前状态

起步工程初始化已完成（应用工厂、配置、日志、健康检查、OpenAPI 和最小验收测试），并落地账号体系：`user` 模型 + `user_session` 会话表 + Alembic 迁移（数据库默认关闭）；注册、用户登录/me/退出、管理员受控创建 CLI 与管理员独立登录/me/退出均已实现。唯一业务以外的显式路由是 `GET /health`，另保留 FastAPI 文档入口。用户属主、上传、解析、翻译、任务、书库和导出尚未实现。

初始化时复制教师的 65 个基础模板文件，再完成项目元数据、启动和权限占位适配。不是教师模板原样导入；差异和逐文件散列见 [来源记录](docs/starter-source.md) 与 [来源清单](docs/starter-manifest.json)。

数据库默认关闭（`DATABASE_ENABLED=false`），bootstrap 仅初始化日志，不连接 MySQL、Redis，也不启动教学内存队列；启用数据库须显式配置译伴 `DATABASE_URL`，表结构由 Alembic 唯一管理（lifespan 不执行 `create_all` 或自动迁移）。`/health` 的 `status=ok` 只证明基础 HTTP 进程可用；`mode=bootstrap`、`business_ready=false` 明确表示尚未业务就绪。真实后台任务机制、存储仍按后续设计落实。

## 快速开始

```bash
cd ~/projects/yiban-api
uv sync --locked
uv run --locked pytest -q
uv run --locked uvicorn start:app --host 127.0.0.1 --port 8001 --reload
```

默认 bootstrap 无需 `.env`（不连接数据库、Redis 或队列）。启用真实鉴权时参考 `.env.example` 配置环境变量，不要覆盖已有私有 `.env`。

启动命令持续占用当前终端。另开终端检查：

```bash
curl --noproxy '*' http://127.0.0.1:8001/health
```

预期响应：

```json
{"status":"ok","service":"yiban-api","version":"0.1.0","mode":"bootstrap","business_ready":false}
```

开发文档：`http://127.0.0.1:8001/docs`；OpenAPI：`http://127.0.0.1:8001/openapi.json`。也可运行 `uv run --locked python start.py`，从配置读取绑定地址和端口，起步默认 `127.0.0.1:8001`。测试中的 HTTP 验收使用临时本地端口并自动结束进程。

`.python-version` 与 `pyproject.toml` 将本次支持范围限定为 Python 3.12 系列；依赖由 `uv.lock` 锁定。`requirements.txt` 从同一锁文件导出，仅兼容 pip 的运行时安装，开发测试使用 uv 默认 dev 依赖组。

## 目录与分层

| 位置 | 职责与当前状态 |
|---|---|
| `app/` | 应用工厂、生命周期、基础路由、中间件与异常装配 |
| `config/` | 教师的统一配置与环境工厂；标准入口为 `from config import settings` |
| `api/v1/` | 请求与响应入口；已注册 `/auth/*`（用户端）与 `/admin/auth/*`（管理端） |
| `service/` | 业务流程、校验与事务边界；`auth_service.py` 已实现注册/登录/退出 |
| `repository/`、`models/`、`schemas/` | 数据访问、ORM 和 Schema；`models/user.py`、`models/user_session.py` 为账号与会话实体，`repository/` 已有用户/会话仓储 |
| `core/` | 数据库、缓存、队列、会话 JWT（`token.py` 固定 HS256）、鉴权依赖（`permissions.py`）与 Cookie 工具 |
| `utils/`、`middleware/` | 通用工具（密码哈希在 `utils/security.py`）与可选中间件；缓存/队列/中间件默认不启动 |
| `tests/` | 无外部基础设施启动、鉴权开关/权限拒绝、真实 HTTP 启动及 MySQL 集成验收 |
| `docs/` | 起步来源、逐文件差异及变更补丁 |

后续保持 API → Service → Repository → Model，Schema 负责请求校验。API 不直接调用 Repository；跨表事务由业务流程统一控制，不能照搬按条 CRUD 自动提交的方式。模板工具与配置按实际需要逐步适配。

## 配置与权限边界

- `.env` 及运行日志、上传文件、数据库文件、虚拟环境不提交。示例配置不是真实凭据或生产配置。
- `.env.example` 中的数据库、Redis、JWT 等字段属于继承的后续配置参考；默认 bootstrap 不连接这些基础设施。真实鉴权需显式启用（`AUTH_ENABLED=true` + `DATABASE_ENABLED=true` + 有效密钥），启用后才有登录/me/退出与会话签发。
- `core.permissions` 的 `get_current_user`/`require_admin` 已真实实现（验签 + 查库 + 角色校验，JWT 不含角色快照）；未实施权限入口（`get_current_active_user`/`require_teacher`/`require_student`）仍返回 503。兼容名称中的 `sso/teacher/student` 不代表译伴采用学校账号模型。
- 缓存、队列、部署与其他模板工具模块仍需后续专门验收；不能据文件存在声称业务或生产能力已完成。
- 选择配置环境使用进程变量 `FASTAPI_ENV`，本次默认 development。真实数据库、角色、服务密钥及运行策略在对应里程碑接入，前端不保存服务端秘密。
- 调试开关使用专用环境变量 `YIBAN_DEBUG`（`true`/`false`），不再读取通用 `DEBUG`；旧的 `DEBUG` 配置项需迁移为 `YIBAN_DEBUG`。

## 部署

起步阶段附带的容器与运维素材（`docker/`、`deploy/`）已作为教学参考裁剪移除，不再随仓库保留；来源与删除记录见 [来源记录](docs/starter-source.md)。后续部署方案按项目设计阶段确定，云服务器部署目标（G1）保留不变；本批未启动任何容器或运维服务。

### 本地账号联调环境（开发库）

前端联调使用独立开发库 `yiban_api_dev`（容器 `yiban-mysql-84-dev`、端口 `127.0.0.1:3307`），与测试实例隔离。初始化、启动、迁移、冒烟验证、停止与管理员 CLI 见 [本地开发文档](docs/local-development.md)。

### 本地 MySQL 8.4 测试实例（数据库集成验收用）

数据库集成测试需要译伴专用 MySQL 8.4 实例（独立测试库 `yiban_api_test`，仅本机监听，**仅供集成验收、不作为后续前端开发库**）。本机 Docker 需 root 权限时，由你在终端输入 sudo 密码启动（命令与文档均不含密码）：

1. 生成随机凭据到被 Git 忽略的 `.env.test-db`：
   ```bash
   python -c "import secrets; print('MYSQL_ROOT_PASSWORD='+secrets.token_urlsafe(24)); print('MYSQL_DATABASE=yiban_api_test'); print('MYSQL_USER=yiban'); print('MYSQL_PASSWORD='+secrets.token_urlsafe(24)); print('MYSQL_PORT=3308')" > .env.test-db
   ```
2. 启动容器（使用 `--env-file`，密码不写入命令）：
   ```bash
   sudo docker compose --env-file .env.test-db -f docker-compose.mysql.yml up -d
   ```
   容器名 `yiban-mysql-84-test`、卷 `yiban_mysql_test_data`、端口 `127.0.0.1:3308`。
3. 连接验证（用 `.env.test-db` 中的 `yiban` 用户密码）：
   ```bash
   TEST_DATABASE_URL='mysql+pymysql://yiban:<password>@127.0.0.1:3308/yiban_api_test' \
   uv run --locked pytest -q tests/test_account_db_integration.py
   ```
   集成测试只读 `TEST_DATABASE_URL` 并校验目标库名必须为 `yiban_api_test`，非译伴专用测试库会拒绝执行迁移/写入。

## Git 与后续范围

仓库与前端同级放置，使用 `master` 稳定分支、`develop` 集成分支以及 `feature/*`、`fix/*`、`docs/*`。Gitee 为 `origin` 和 PR 合并入口，GitHub 为 `github` 镜像，同步相同提交；校内 GitLab 留到最终提交阶段。保留起步根提交，不在两平台各自合并同一变更。

首个真实里程碑按中央需求 §3.5 推进：注册登录（已实现）、TXT、英语到中文、真实翻译、后台进度、预览、EPUB、个人书库与重新下载，以及最小只读管理查看。上传、翻译、任务、书库与导出尚未实现；状态、失败、幂等入库、重试新建 task 与属主规则按已有设计草案落实，当前均尚未实现。

详见 [CODEBUDDY.md](CODEBUDDY.md)。账号体系已落地：`user` 表 + `user_session` 会话表 + Alembic 迁移（数据库默认关闭），注册、用户登录/me/退出、管理员受控创建 CLI 与独立会话均已实现；通用业务 CRUD、上传、翻译、任务与书库链路仍未实现，不将账号验收等同于完成核心业务链路。
