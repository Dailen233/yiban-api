# 后端起步来源与初始化记录

日期：2026-10-22。本记录区分教师原始生成模板、译伴初始化适配和已验证能力。

## 来源

| 项目 | 记录 |
|---|---|
| 教师仓库 | https://gitee.com/ncepu-bj/ncepu_ideal-skills |
| 已核对压缩包 | `ncepu_ideal-skills-develop.zip` |
| SHA-256 | `a5a4ee0d4d4108f734f8b7308005eb33ba816d4725527c2b968f51005d225620` |
| 用户本机原始包 | `~/下载/ncepu_ideal-skills-develop.zip`，用户已验证散列一致 |
| 起步模板 | `ncepu_ideal-skills-develop/sql-to-fastapi-restfulapi-scaffold/resources/templates/project_structure/` |
| 模板原始文件数 | 65，其中 Python 文件 42 |
| 使用方式 | 完整复制基础结构，再做以下初始化适配；未按 SQL 生成业务表与 CRUD |

这是根据教师资源生成的项目实例，首次提交不是教师上游 Git 提交。原始 ZIP、目录和逐文件散列用于追溯，不能把本仓的提交号冒充上游版本。

逐文件原始散列、初始化后散列和修改状态见 [starter-manifest.json](starter-manifest.json)。[starter-adjustments.patch](starter-adjustments.patch) 只记录对原有模板文件的改动，新增说明、测试、锁文件等另列在清单中。

## 初始化适配

| 文件 | 改动与原因 |
|---|---|
| `pyproject.toml` | 替换生成占位符，命名 yiban-api、版本 0.1.0；本次支持 Python 3.12 系列 |
| `config/config_unified.py` | 项目名与版本；本机默认绑定 127.0.0.1:8001 |
| `.env.example` | 项目、缓存前缀和本机端口；示例 CORS 包含用户端 5173 与管理端 8888；数据库等字段标为后续参考 |
| `app/factory.py` | 基础生命周期只启用日志，不自动连接模板 MySQL、Redis或启动内存队列 |
| `app/routes.py` | 健康检查明确 bootstrap、business_ready=false；移除依赖不存在辅助函数的模板 /api/info |
| `core/permissions.py` | 移除对未生成学校 SsoUser 的依赖；兼容导入名均默认拒绝，HTTP 503，不授予角色或属主访问 |
| `core/__init__.py` | 同步权限占位说明，保留导入兼容 |
| `start.py` | 使用统一配置和 main 入口，默认本机 8001；不硬编码公开监听 |
| `requirements.txt` | 从 uv.lock 导出运行时依赖，解决原模板 pip 清单与 pyproject 不一致 |
| `docker/Dockerfile` | Python 基础镜像声明与本次 3.12 支持范围一致，未构建镜像 |
| `docker/docker-compose.yml` | 注释不存在的学校 SQL dump 挂载，不生成业务初始化 SQL |

新增 README、CODEBUDDY、Git/Docker 忽略规则、uv.lock、基础测试和来源资料。其余模板文件保留原文；格式历史不作为已完成全面规范化的声明。

## 依赖与运行环境

以 `pyproject.toml` 为主清单，`uv.lock` 锁定来自公开 PyPI 的解析结果。主要版本：FastAPI 0.159.1、Uvicorn 0.54.0、Pydantic 2.14.1、pydantic-settings 2.16.1、SQLAlchemy 2.1.6、pytest 9.1.1。它们是本次锁定值，不表述为教师指定版本或“当前最新版”。

`requirements.txt` 由以下命令生成，更新依赖后保持同步：

```bash
uv export --locked --no-dev --no-hashes --format requirements-txt --no-emit-project --output-file requirements.txt
```

准备环境使用 CPython 3.12.14、uv 0.12.23。用户本机是 Python 3.12.3、uv 0.13.0，本机尚需按 README 复验；不把准备环境结果冒充用户本机结果。

## 实际验证

| 检查 | 结果 |
|---|---|
| 原始压缩包散列 | 与用户本机提供的 SHA-256 一致 |
| Python 语法 | 初始化后的 44 个 Python 文件通过 AST 解析 |
| 安装与锁定 | uv 解析 41 个包并成功安装当前环境所需的 39 个包，生成 uv.lock |
| 测试 | `uv run --locked pytest -q`：6 passed，1 条上游测试客户端弃用提示 |
| 无基础设施启动 | 生命周期测试通过，不初始化 DB、缓存、队列 |
| 权限占位 | 普通/管理员依赖，无凭据或任意 Bearer 均返回 503，受保护处理不执行 |
| 真实 HTTP | 测试启动独立 Uvicorn，/health 和 /openapi.json 可读，进程自动清理 |

该弃用提示来自 Starlette TestClient 当前对 httpx 的兼容路径，不是功能失败；本批未屏蔽提示。测试没有验证真实登录、JWT 业务会话、多用户属主、翻译、数据库事务或导出，也没有运行 Docker、部署或业务迁移。

## 首次提交与后续

本包不附 `.git/`，也不虚构尚未产生的首次提交号。在用户本机验收后，以上初始化实例作为首个代码提交推送到两平台的 master、develop；根提交可用 `git rev-list --max-parents=0 HEAD` 查询。后续业务按独立功能分支推进。

未定的物理数据库、持久任务机制、文件存储和真实会话按设计阶段落实。教师的工具、部署模板及教学角色不自动成为译伴的最终方案。

## 后续裁剪记录

- **日期**：2026-10-23。
- **范围**：删除起步阶段附带的容器与运维教学素材——`docker/`（Dockerfile、docker-compose.yml、README.md，共 3 个文件）、`deploy/`（16 个文件）及根目录 `.dockerignore`；同步修订 `README.md` 与 `CODEBUDDY.md` 中相关现状表述。
- **原因**：这些教学容器与运维素材在当前初始化批次未启用，当前运行链不依赖它们；删除不改变运行时代码、依赖或启动行为，后续云服务器部署仍按 G1 和项目部署设计落实。
- **实际验证**：`env -u DEBUG uv run --locked pytest -q`：6 passed，1 条上游弃用警告；`git diff --check` 无空白错误；健康检查、文档入口、OpenAPI、无外部基础设施启动、权限占位默认拒绝等既有行为保持不变。普通命令 `uv run --locked pytest -q` 曾受本机 `DEBUG=release` 环境变量影响而失败（`debug` 字段布尔解析冲突），该配置兼容问题留后续批次处理。
- **快照边界**：本文件「来源」「初始化适配」「实际验证」各节，以及 `starter-manifest.json`、`starter-adjustments.patch` 描述的均为**首次提交时的快照**（65 个模板文件、逐文件散列与初始化差异），保持字节不变；本次裁剪不改变该快照追溯。原有初始化适配记录保持原貌。

## DEBUG 环境变量冲突修复记录

- **日期**：2026-10-23。
- **根因**：
  1. `debug: bool` 字段由 pydantic-settings 默认从同名环境变量 `DEBUG` 读取，进程存在非布尔 `DEBUG=release`（部署/构建环境常见）时布尔解析失败，导致配置导入失败。
  2. 改用 `validation_alias="YIBAN_DEBUG"` 后读取问题解决，但 dotenv 中旧 `DEBUG` 键在 `case_sensitive=False` 下被小写为 `debug`，在 `extra="allow"` 下进入 `model_extra`，进而以小写 `debug` 键遮蔽 `model_dump()` 中同名字段的导出（属性为 bool、导出却为字符串）。
- **修复**：
  1. 对 `BaseConfig` 及各环境子类的 `debug` 字段加 `validation_alias="YIBAN_DEBUG"`，保留内部 `debug` 字段名、`settings.debug` 访问与 `model_dump()` 导出字段名。
  2. `BaseConfig` 的 `model_config` 加 `dotenv_filtering="only_existing"`，让 dotenv 源只匹配已定义字段、不把未匹配键引入 extra，在加载边界消除旧 `DEBUG` 键对导出的遮蔽；子类经 model_config 继承合并自动生效（含 `DockerConfig`）。该规则会忽略 dotenv 中全部未声明字段、保留已声明字段及其别名的读取，后续新增配置需在配置类中声明字段，否则其 dotenv 值会被忽略。
  3. 同步 `config/manage.py` 模板生成、`.env.example`、`.env.docker` 与 `README.md`。
- **更正说明**：pydantic-settings 会忽略未匹配的**环境变量**，但 `extra="allow"` 下 dotenv 源会把未匹配的 **dotenv 键**作为 extra 引入；本批以 `dotenv_filtering="only_existing"` 消除该差异。
- **验证**：`DEBUG=release uv run --locked pytest -q`：17 passed，1 条上游弃用警告。新增 `tests/test_debug_env_collision.py`（11 项）覆盖 DEBUG=release 导入、YIBAN_DEBUG true/false 与优先级、各环境默认值与取反、DockerConfig 继承、非法值拒绝、dotenv 污染与进程优先级、模板输出。
- **已知遗留**：`ProductionConfig` 的 `docs_url: None` / `redoc_url: None` / `openapi_url: None` 为 pydantic v2 下「必填 NoneType」缺陷，导致 production 环境直接实例化报错；该问题预先存在、与本批修复无关，留后续配置批处理。（已在下一批「生产配置文档字段缺省值修复记录」解决。）

## 生产配置文档字段缺省值修复记录

- **日期**：2026-10-23。
- **根因**：`ProductionConfig` 的 `docs_url: None` / `redoc_url: None` / `openapi_url: None` 三个字段把 `None` 当作类型注解（NoneType）而非默认值，pydantic v2 下视为「必填字段」，直接实例化报三个 missing 错误。
- **修复**：为三个字段补显式默认值 `None`（`docs_url: None = None` 等），保持原有 NoneType 约束及生产环境默认禁用文档的意图；`AppConfig.get_app_config()` 仍以 `getattr(settings, "docs_url", "/docs")` 读取，None 时 FastAPI 不挂载文档路由。
- **验证**：`DEBUG=release uv run --locked pytest -q`：19 passed，1 条上游弃用警告。新增 `tests/test_production_config.py`（2 项）覆盖：production 无需显式传入文档字段即可实例化（三者均为 None、debug 默认 False），以及隔离子进程下真实应用入口可创建、`/health` 返回 bootstrap、`/docs` `/redoc` `/openapi.json` 返回 404（production 的 TrustedHostMiddleware 仅允许 localhost/127.0.0.1）。移除 `tests/test_debug_env_collision.py` 中为绕过此缺陷而显式传入三个 None 的辅助参数。

## 账号数据库基础记录（任务 1）

- **日期**：2026-10-23。范围仅 `tasks/todo.md` 任务 1（数据库基础 + User 模型 + 首个迁移）；注册/登录/JWT/会话/管理员留后续批次。
- **实现**：
  1. 新增默认关闭的 `database_enabled`（`config/config_unified.py`）：关闭时 bootstrap 无外部数据库依赖；启用后必须显式配置译伴 `DATABASE_URL`，缺失或仍指向教师示例库（含 `api_security`）明确报错，不回退教师示例库。
  2. `core/database.py`：`create_database_pool` 连接测试失败时释放已建引擎、日志经 `_redact_url` 脱敏；`close_database_pool` 同时清理会话工厂；`app/factory.py` lifespan 仅在启用时初始化/释放连接资源，不 `create_all`、不自动迁移。
  3. `models/user.py`：`user` 表（id VARCHAR(36) UUID PK、email VARCHAR(255) UNIQUE、password_hash VARCHAR(255)、display_name VARCHAR(100)、role VARCHAR(16) 默认 `'user'`、created_at/updated_at `DATETIME(6)` 无时区 UTC）；`normalize_email`（strip+lower）、`utcnow`（naive UTC）。逻辑 enum('user','admin') 落地为 VARCHAR(16)+应用层校验。
  4. Alembic（1.20.1）+ `alembic/versions/0001_create_user_table.py`：模型与迁移同批落地；`alembic/env.py` 与运行时读同一套 `DATABASE_URL`（sync pymysql，运行时转 aiomysql）。
  5. 基线测试修正：`tests/test_production_config.py` 子进程显式 `ALLOWED_HOSTS`（环境变量下 list 字段需 JSON 数组）与 `DATABASE_ENABLED=false`，不再依赖私有 `.env`；`tests/conftest.py` 显式 `DATABASE_ENABLED=false`。
- **新增依赖**：`alembic>=1.13.0`（解析到 1.20.1，含 mako、markupsafe）；`uv.lock`/`requirements.txt` 同步更新。
- **验证**：
  - 基础测试（不接数据库）`DEBUG=release uv run --locked pytest -q`：**25 passed、4 skipped**、1 条上游弃用警告。新增 `tests/test_account_db.py`（6 项：email 规范化、naive UTC、User 物理结构、日志脱敏、教师示例库/缺失 URL 拒绝）。
  - 迁移离线 SQL：`uv run alembic upgrade head --sql` 生成 `DEFAULT 'user'`、`UNIQUE(email)`、`DATETIME(6)`。
  - **数据库集成验收阻塞**：本机无 MySQL 8.4 实例。已尝试并排除：docker daemon 运行但当前用户 `dailen` 不在 `docker` 组且 `/var/run/docker.sock` 为 `root:docker`（`docker ps` 报 permission denied）；`sudo -n` 需密码；`containerd`/`ctr` 可用但 `/run/containerd/containerd.sock` 为 `root:root`（`ctr` 同样 permission denied）；无 podman/rootless docker；无 mysql/mysqld 二进制；端口 3306–3308 无监听；本机 `.env` 指向教师示例库 `api_security_demo`（非译伴专用库）。`tests/test_account_db_integration.py`（4 项：upgrade/downgrade/upgrade、持久化+唯一约束+事务回滚、UTC 时间往返、应用启停）已编写并以 `skipif` 标记，未运行；**跳过不视为通过**，待具备译伴专用 MySQL 8.4 实例后执行。
- **后续事项（本轮不实施）**：模板审查发现 `utils/audit.py` 模块级 `audit_logger = AuditLogger()` 在 `import app` 时即创建 `logs/audit/` 目录与两个 `RotatingFileHandler`（链：`app/middleware.py` → `middleware/__init__` → `audit_middleware` → `utils.audit`），即使审计中间件默认关闭；留待后续以惰性单例消除该导入副作用（副作用测试改用临时目录，不删除本机 logs/）。`passlib`/`aiosqlite` 依赖精简亦留后续，不混入本轮。
- **测试库保护与 UTC 转换修正（同批追加）**：
  1. 结构化 URL 校验：`core/database.py` 新增 `get_database_name`/`is_teacher_sample_db`/`ensure_test_database`（基于 `make_url` 解析库名，不再用整 URL 子串判断）；`create_database_pool` 与 `alembic/env.py` 均改用结构化判断教师示例库。
  2. 测试库保护：集成测试只读 `TEST_DATABASE_URL`（移除 `DATABASE_URL` 回退），`ensure_test_database` 限定目标库名 `yiban_api_test`；缺失跳过、非法报错。新增无需数据库的保护测试证明开发库/教师库/其他库/非法 URL 在迁移/删除/写入前被拒绝。
  3. 真实 UTC 转换：新增 `models/types.py::UTCDateTime`（`DATETIME(6)` 列类型绑定，`cache_ok=True`），写入前 aware→UTC naive、读回后恢复 aware UTC；`models/user.py` 的 created_at/updated_at 改用 `UTCDateTime`（编译仍为 `DATETIME(6)`）。UTC 测试直接传带 +08:00 偏移与微秒的原始 aware 时间，不替应用预先转换。
  4. 测试前置：每个集成测试独立准备/清理表结构（`prepared_schema` fixture upgrade→downgrade，不依赖 upgrade 测试先执行）；新增连接失败时引擎释放、全局状态不残留的行为测试；应用启停测试显式 `base_url='http://localhost'` 与数据库配置。
  5. 新增依赖 `cryptography>=42.0.0`（解析到 50.0.2，含 cffi/pycparser）：MySQL 8.0+/8.4 默认 caching_sha2_password 认证，PyMySQL/aiomysql 需 cryptography（官方：pymysql.readthedocs.io 建议 `PyMySQL[rsa]`）。
  6. 手动启动数据库：`docker-compose.mysql.yml`（容器 `yiban-mysql-84-test`、卷 `yiban_mysql_test_data`、端口 `127.0.0.1:3308`、`--default-time-zone=+00:00`）配合被 Git 忽略的 `.env.test-db`（随机凭据）；启动命令见 README。
- **真实 MySQL 8.4 集成验收通过（用户启动容器后）**：用户手动 `sudo docker compose` 启动 `yiban-mysql-84-test`（127.0.0.1:3308）。就绪检查确认 MySQL **8.4.13**、当前库 `yiban_api_test`、会话时区 `+00:00`、`utf8mb4/utf8mb4_0900_ai_ci`。四项集成测试真实执行全部通过（upgrade→downgrade→upgrade、持久化+规范化 email 唯一约束+事务回滚、UTC 时间往返含 +08:00 偏移与微秒、应用启停）；带 `TEST_DATABASE_URL` 的完整回归 **40 passed、0 skipped**（基础 36 + 集成 4）。`alembic upgrade head` + `downgrade -1` 在独立测试库 `yiban_api_test` 真实执行通过。
- **边界**：本文件「来源」「初始化适配」各节及 `starter-manifest.json`、`starter-adjustments.patch` 保持字节不变，仅追加本记录。
