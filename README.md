# 译伴共享后端 · yiban-api

基于教师 `sql-to-fastapi-restfulapi-scaffold` 的基础工程，使用 Python 3.12 与 uv。用户端 `yiban-web`、管理端 `yiban-admin` 共用此后端；需求和历史原型位于同级 `bilingual-ebook-generator`。

## 当前状态

本批只完成起步工程初始化：应用工厂、配置、日志、健康检查、OpenAPI 和最小验收测试。唯一业务以外的显式路由是 `GET /health`，另保留 FastAPI 文档入口。账号、用户属主、上传、解析、翻译、任务、书库和导出尚未实现。

初始化时复制教师的 65 个基础模板文件，再完成项目元数据、启动和权限占位适配。不是教师模板原样导入；差异和逐文件散列见 [来源记录](docs/starter-source.md) 与 [来源清单](docs/starter-manifest.json)。

默认启动仅初始化日志，不连接 MySQL、Redis，也不启动教学内存队列。`/health` 的 `status=ok` 只证明基础 HTTP 进程可用；`mode=bootstrap`、`business_ready=false` 明确表示尚未业务就绪。真实后台任务机制、数据库与存储仍按后续设计落实。

## 快速开始

```bash
cd ~/projects/yiban-api
uv sync --locked
cp .env.example .env
uv run --locked pytest -q
uv run --locked uvicorn start:app --host 127.0.0.1 --port 8001 --reload
```

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
| `api/v1/` | 后续请求与响应入口；当前尚未注册业务资源 |
| `service/` | 后续业务流程、校验、计数和事务边界，当前仅模板骨架 |
| `repository/`、`models/`、`schemas/` | 数据访问、ORM 和 Schema 基础，尚无译伴业务实体 |
| `core/` | 数据库、缓存、队列模板及默认拒绝的权限占位依赖 |
| `utils/`、`middleware/` | 继承的工具与可选中间件；并不等于所有模板能力已验收 |
| `tests/` | 无外部基础设施启动、权限占位拒绝及真实 HTTP 启动验收 |
| `docs/` | 起步来源、逐文件差异及变更补丁 |

后续保持 API → Service → Repository → Model，Schema 负责请求校验。API 不直接调用 Repository；跨表事务由业务流程统一控制，不能照搬按条 CRUD 自动提交的方式。模板工具与配置按实际需要逐步适配。

## 配置与权限边界

- `.env` 及运行日志、上传文件、数据库文件、虚拟环境不提交。示例配置不是真实凭据或生产配置。
- `.env.example` 中的数据库、Redis、JWT 等字段属于继承的后续配置参考，当前启动不连接这些基础设施，也没有登录和签发会话端点。
- `core.permissions` 保留必要导入名称，但权限依赖统一返回 HTTP 503，检查器不授予权限。兼容名称中的 `sso/teacher/student` 不代表译伴采用学校账号模型；真实实现须按 user、角色、属主与管理内容访问边界重写。
- 教师密码/JWT、缓存、队列、部署与其他工具模块仍需后续专门验收；不能据文件存在声称业务或生产能力已完成。
- 选择配置环境使用进程变量 `FASTAPI_ENV`，本次默认 development。真实数据库、角色、服务密钥及运行策略在对应里程碑接入，前端不保存服务端秘密。

## 部署

起步阶段附带的容器与运维素材（`docker/`、`deploy/`）已作为教学参考裁剪移除，不再随仓库保留；来源与删除记录见 [来源记录](docs/starter-source.md)。后续部署方案按项目设计阶段确定，云服务器部署目标（G1）保留不变；本批未启动任何容器或运维服务。

## Git 与后续范围

仓库与前端同级放置，使用 `master` 稳定分支、`develop` 集成分支以及 `feature/*`、`fix/*`、`docs/*`。Gitee 为 `origin` 和 PR 合并入口，GitHub 为 `github` 镜像，同步相同提交；校内 GitLab 留到最终提交阶段。保留起步根提交，不在两平台各自合并同一变更。

首个真实里程碑按中央需求 §3.5 推进：注册登录、TXT、英语到中文、真实翻译、后台进度、预览、EPUB、个人书库与重新下载，以及最小只读管理查看。状态、失败、幂等入库、重试新建 task 与属主规则按已有设计草案落实，当前均尚未实现。

详见 [CODEBUDDY.md](CODEBUDDY.md)。本批没有业务表、DDL、迁移或通用业务 CRUD，不将工程初始化等同于完成核心链路。
