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
