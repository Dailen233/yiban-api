# 账号基础落地方案

> 状态：**待评审**。本文为账号模块（注册/登录/角色/会话）的基础落地规划，不包含上传、翻译、任务、书库等后续链路。范围以需求 §3.5「首个真实可运行里程碑」中的账号项 + FR-14/15 + G11 为依据。
>
> 本文所有「推荐」均为**本项目拟定**，供评审；不是「老师要求」，也不等于「用户已确认」。涉及待确认的产品项（P12 等）明确标注状态。

## 1. 概览与依据

### 1.1 目标
落地服务端账号体系：基础注册/登录、服务端用户身份与角色、管理员独立入口。用户端与管理端共享后端，但角色与入口隔离；用户身份与角色由服务端校验，作为后续 `owner_id` 派生的唯一依据。

### 1.2 依据（只读核对）
- 需求 §3.5：账号「注册/登录，书籍与任务归属到用户，权限服务端校验」；管理端最小集「管理员独立登录 + 任务列表/失败查看」。
- FR-14：注册/登录，登录后记录归属到具体用户，受保护路由与资源按属主校验；注册字段/密码策略/找回密码见 P12。
- FR-15：管理员独立入口登录；首版仅任务/失败只读查看（P14 拟定默认）。
- NFR-03：文件与下载链接不被公开枚举/猜测，访问控制机制设计阶段确定。
- G11：记录归属到用户、服务端权限校验、管理员独立角色与入口。
- 数据库逻辑模型 §3.1 `user`、§4.3 属主一致性（冗余 `owner_id` + 服务端强制，非靠物理外键保证）。

### 1.3 当前代码现状（决定复用/替换）
- `core/database.py`：纯异步 `AsyncEngine` + `async_sessionmaker`，`get_async_session` 依赖注入；`_to_async_url` 已支持 `mysql+pymysql → mysql+aiomysql`。
- `models/base.py`：`BaseModel`（仅 `to_dict`/`update_from_dict`，无公共字段）、`TimestampMixin`、`SoftDeleteMixin`。
- `utils/security.py`：`SecurityUtil.hash_password/verify_password` 直接使用 `bcrypt`（已锁定 bcrypt 5.0.0）。
- `utils/auth.py`：`JWTAuthenticator`（PyJWT 2.15.1），从 `config` 读 `secret_key/algorithm/access_token_expire_minutes`。
- `core/permissions.py`：当前 `get_current_user` 为占位，一律 503 拒绝；`require_admin` 等别名同源。
- `config/config_unified.py`：已有 `secret_key`、`jwt_secret_key`、`algorithm="HS256"`、`access_token_expire_minutes`、`refresh_token_expire_days` 及 `effective_jwt_secret_key`。
- 锁定依赖：`sqlalchemy 2.1.6`、`aiomysql 0.3.2`、`aiosqlite 0.22.1`、`pymysql 1.2.3`、`bcrypt 5.0.0`、`passlib 1.7.4`、`pyjwt 2.15.1`。

## 2. 推荐结论

### 2.1 数据库与迁移

**推荐：开发、数据库集成测试、部署统一使用 MySQL 8.4 LTS；迁移工具 Alembic；纯逻辑测试不接数据库，SQLite 不作为 MySQL 迁移与约束的验收依据。**

- **统一 MySQL 8.4 LTS**：依据 MySQL 官方发布模型（https://dev.mysql.com/doc/refman/8.4/en/mysql-releases.html），8.4 是首个 LTS（长期支持）版本（2024-04-30 GA），面向「稳定特性 + 较长支持周期」的场景，适合新项目基线；8.0 已进入仅修复阶段、剩余支持周期短于 8.4 LTS。NFR-06 最终云服务器部署，逻辑模型含多表外键与属主一致性；`aiomysql`/`pymysql` 已锁定，`core/database.py` 已支持。开发、数据库集成测试、部署三者用同一引擎与版本，迁移与约束（唯一索引、外键、事务）以 MySQL 8.4 实际行为为准。**仅调整规划，不安装、升级或操作本机已有数据库。**
- **数据库启用方式**：未启用数据库时，应用保持 bootstrap「无外部数据库依赖」的现有运行边界；启用后必须使用**显式配置的译伴数据库**（`DATABASE_URL`），**配置缺失或连接失败应明确报错**，不得回退到教师示例库。
- **迁移工具 Alembic（表结构唯一入口）**（新增依赖，待批准）：SQLAlchemy 官方迁移，`autogenerate` 生成版本、`upgrade/downgrade` 可回滚；**Alembic 是表结构版本与变更的唯一入口**。lifespan **只初始化、释放数据库连接资源，不执行 `create_all` 或自动升级迁移**。每个迁移版本只引用当时已定义的模型字段，**模型与其迁移在同一批次落地**，避免「迁移引用了后续批次才定义的字段」。
- **测试分层**：① 无需数据库的基础测试（校验、哈希、会话撤销规则、路由语义）用 mock/内存替身，不接数据库；② 迁移/约束/事务测试使用**独立 MySQL 测试库**（如 `yiban_api_test`），与开发库（`yiban_api_dev`）隔离、`DATABASE_URL` 注入，**不连接其他项目数据库**；`upgrade`/`downgrade` 验证**限定在独立测试库**，不对已有开发数据执行回滚验收。
- **主键**：`id` 用 UUID 字符串（`str(uuid4())`，服务端生成），与逻辑模型 `string id` 一致。
- **时间语义（UTC，收敛约定）**：推荐 MySQL 用 **`DATETIME(6)` 存储不带时区的 UTC 值**；应用**写入前转 UTC**，**读取后恢复 UTC 语义**（按 UTC 解释）；**API 输出带时区的 ISO 8601**（如 `2026-10-23T10:00:00Z`）；**JWT `exp` 与 `session.expires_at` 表示同一到期时刻**（`exp` 为 Unix 时间戳，`expires_at` 为 UTC `DATETIME(6)`，换算到同一 UTC 时刻比较）。本方案已明确「无时区 UTC 列 + 应用层 UTC 约定」，不再保留「设置连接时区或应用层处理」等未选择表述。
- **email 规范化与唯一性**：入库前 `strip().lower()`（仅对 email，不对密码）；`UNIQUE(email)` 唯一索引防重复注册；校验走 Pydantic `EmailStr`（需 `email-validator`，新增依赖，待批准）或显式正则。
- **逻辑关联 vs 物理外键**：物理外键只保证「引用存在」，不保证「属主相等」；属主一致性（§4.3 两条不变量）由服务端强制。物理层是否加外键、复合外键或触发器辅助，留数据库物理模型单独评审。

### 2.2 最小账号模型

以逻辑模型 §3.1 为起点，只设计账号与所选会话方案必需的表，共 **2 张**：`user`、`user_session`。

**`user`（账号）**
| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | String | PK | UUID |
| email | String | UNIQUE, NOT NULL | 登录标识，入库前规范化（仅 email） |
| password_hash | String | NOT NULL | bcrypt 哈希，绝不明文 |
| display_name | String | NOT NULL | 显示名/昵称 |
| role | Enum('user','admin') | NOT NULL, 默认 'user' | 服务端校验，前端隐藏菜单不构成边界 |
| created_at / updated_at | DateTime | NOT NULL | UTC |

**`user_session`（会话追踪与撤销）**
| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | String | PK | UUID |
| user_id | String | FK → user.id, NOT NULL | 会话归属 |
| jti | String | UNIQUE, NOT NULL | JWT 的 `jti`，用于退出撤销 |
| session_type | Enum('user','admin') | NOT NULL | 区分用户端/管理端会话 |
| expires_at | DateTime | NOT NULL | 与 access token `exp` 一致（UTC） |
| revoked_at | DateTime | nullable | 退出/注销时间；非空即失效 |
| created_at | DateTime | NOT NULL | 登录时间 |

> `user_session` 只是**会话追踪与撤销记录**，不等同于完整审计系统；完整审计（谁/何时/做了什么，含管理员查看文件留痕）属 M2/操作日志，不在本表承担。

**与逻辑草案的差异**：新增 `user_session`（草案未建模会话，属实现层）；`user` 增加 `updated_at`。首版**不**加 `is_active`/禁用状态（属 M2），**不**一次性生成 upload_file/task/book 等业务表。

### 2.3 密码与会话

**密码哈希（推荐 bcrypt，复用现有）**：
- 复用 `utils/security.SecurityUtil.hash_password/verify_password`（bcrypt 5.0.0，`bcrypt.gensalt()` 默认 **cost 12**）。
- **长度与字节上限**：最小长度 **8 字符**（待评审 P12）；密码以 **UTF-8 编码后超过 72 字节时明确拒绝（422）**，**不截断**——bcrypt 算法只取前 72 字节，截断会让 `abcd…（72 字节前缀相同）` 的不同密码被误判为相同，故必须在应用层先校验长度。
- **不做任何预处理**：密码**原样**传入 bcrypt，**不 strip、不 lower、不做 SQL/XSS 黑名单清理**（`validate_input`/`sanitize_input` 属反模式，对密码既无意义又会误伤合法强密码）。
- **不阻塞异步**：bcrypt 哈希是同步 CPU 密集操作，在 async 端调用时经 `run_in_executor`/线程池执行，避免阻塞事件循环。
- **复用边界**：仅复用 `SecurityUtil.hash_password/verify_password`；**不**把同文件中的 `validate_input`/`sanitize_input`（正则黑名单）等工具接入账号流程。
- **替换**：`passlib` 已 0 处 import，属冗余依赖，列为后续清理（本轮不动 `pyproject.toml`/`uv.lock`）。**新增依赖**：Alembic（迁移）、`email-validator`（若用 `EmailStr`），均待批准。

**会话（JWT + 服务端会话撤销）**：复用 `utils/auth.JWTAuthenticator`（PyJWT 2.15.1，HS256），签发短期 access token（`sub=user_id`、`aud`、`role` 快照、`jti`、`exp`）。**每次鉴权同时验证：① JWT 签名与 `exp`；② `user_session` 记录存在、`expires_at` 未过、`revoked_at IS NULL`；③ `session.user_id == JWT.sub` 且 `session.jti == JWT.jti`；④ `session.session_type`、JWT `aud` 与当前端点绑定一致；⑤ `user` 存在且 `role` 与当前校验要求一致**——管理权限**不信任客户端或旧 Token 中的角色快照**，以服务端查 `user.role` 为准。

- **过期**：`exp`/`expires_at` 到期 → 401。
- **退出失效**：`POST /logout` 将对应 `user_session.revoked_at` 置为当前时间，该 `jti` 立即失效（不等 `exp`）。
- **双端隔离**：
  - 会话 `session_type` 区分用户端/管理端；JWT `aud`（audience）区分 `user`/`admin`；**用户端与管理端使用不同 Cookie 名**（如 `yiban_user_session` / `yiban_admin_session`）。
  - 校验时要求「Cookie 名 ↔ `aud` ↔ `session_type` ↔ 当前端点」四者一致，缺一即 401/403。
  - **用户端退出仅撤销 `session_type='user'` 的对应会话**，不误清管理员会话（反之亦然）。
  - 管理端登录额外校验 `user.role == 'admin'`；普通用户 token 访问 `/admin/*` 由服务端角色校验拒绝（403）。

**凭据存储与传输边界**：
- `password_hash` 只存 bcrypt 哈希；`user_session` 只存 `jti`，不存原始 token；任何响应不返回 `password_hash`。
- **Cookie**：httpOnly + SameSite=Lax + Secure；**生产** `Secure` 必须开启（HTTPS），**本机开发** http + localhost 下 Secure 按环境豁免。前端 `fetch` 带 `credentials:'include'`，不接触 token——不照搬原型 `localStorage` 模拟鉴权。
- **CSRF/Origin 校验（浏览器 JSON API 推荐规则）**：本项目首版为浏览器 JSON API，写接口（注册、登录、退出及管理端对应写接口）要求**精确匹配可信 Origin**，并携带**固定自定义请求头 `X-Yiban-Request: 1`**；**缺失、`null`、不可信 Origin，或缺少该请求头时拒绝（403）**，本方案**不使用 Referer 兜底**。固定请求头不是登录凭据（仅触发预检、参与 CSRF 防御）；SameSite=Lax 作为补充防护。脚本与测试需显式发送可信 Origin 与该请求头。GET/HEAD 不产生状态变更；OPTIONS 预检正常处理（放行预检、仅校验实际写请求）。
- **凭据型 CORS**：`cors_allow_credentials=True` 时 `cors_origins` 必须是**精确 origin 白名单**（不得 `*`），并显式允许 `X-Yiban-Request` 请求头。**各环境现状已核对**：`DevelopmentConfig` 为 localhost 列表、`StagingConfig`/`ProductionConfig` 为示例域名列表（这些是显式列表），只有 `BaseConfig` 与未覆盖的 `TestingConfig` 仍是 `cors_origins=["*"]` 且 `credentials=True` 的矛盾组合——需在对应批次把后者改为显式列表，而不是把 `*` 概括成所有环境现状。
- **HTTPS 与密钥**：生产强制 HTTPS + Secure cookie；**真实签名密钥校验提前到任务 3（任何真实 JWT 签发前生效）**：校验实际使用的 `effective_jwt_secret_key`，**拒绝空值、教学默认值（`dev-secret-key-…`/`test-secret-key-…`/`staging-secret-key-…`）及 `${PROD_SECRET_KEY}` 等占位字符串**——不是只检查 `PROD_SECRET_KEY` 环境变量是否存在，而是校验最终生效的密钥值本身。bootstrap 未启用真实鉴权时保持现有运行边界，不要求提交真实密钥。`secret_key` 来自环境变量、绝不硬编码或提交。

### 2.4 最小接口契约

统一前缀 `/api/v1`，响应沿用 `schemas/response.py`（`success/code/message/data`）与 `utils/custom_exceptions.py` 语义。时间字段输出 ISO 8601 UTC。

**用户端（Cookie：`yiban_user_session`，JWT `aud=user`）**
| 方法/路径 | 请求 | 成功响应 | 错误 |
|---|---|---|---|
| POST `/auth/register` | `{email, password, display_name}` | 201，`{id, email, display_name, role}` | 409 邮箱已存在；422 校验/密码超长 |
| POST `/auth/login` | `{email, password}` | 200，`{id, email, display_name, role}` + Set-Cookie | 401 凭据错误（不泄露存在性） |
| GET `/auth/me` | 需会话 | 200，当前身份 | 401 未认证/过期/已退出 |
| POST `/auth/logout` | 需会话 | 204 + 清 cookie + 撤销 jti | 401 |

**管理端（独立入口，Cookie：`yiban_admin_session`，JWT `aud=admin`）**
| 方法/路径 | 请求 | 成功响应 | 错误 |
|---|---|---|---|
| POST `/admin/auth/login` | `{email, password}` | 200，管理员身份 + Set-Cookie | 401 凭据错误；403 非 admin |
| GET `/admin/auth/me` | 需 admin 会话 | 200，管理员身份 | 401 未认证；403 非 admin |
| POST `/admin/auth/logout` | 需 admin 会话 | 204 + 清 cookie + 撤销 | 401 |

**关键语义**：
- 普通注册**不能指定角色**：`role` 由服务端强制 `'user'`，忽略/拒绝请求体中的 `role`。
- **管理员受控创建**：无公开管理员注册、无固定默认密码；通过受控脚本/CLI（如扩展 `config/manage.py` 或独立 `scripts/create_admin`）创建，具体方式**待定**。
- **身份与角色由服务端校验**：`get_current_user` 从占位改为真实解析 JWT → 查 `user_session` → 查 `user`，返回 `(id, role)`；后续 `upload_file/task/book` 的 `owner_id` 一律由服务端从 `current_user.id` 派生，不采纳客户端传入的属主，为 §4.3 属主一致性提供依据。

## 3. 模型差异（相对逻辑草案）

| 项 | 逻辑草案 | 本方案 | 说明 |
|---|---|---|---|
| `user` 表字段 | id/email/password_hash/display_name/role/created_at | 一致，另加 `updated_at` | 便于审计更新；首版不加 `is_active`（属 M2） |
| 会话表 | 未建模 | 新增 `user_session`（含 `session_type`） | 实现「退出后服务端失效」、双端隔离与审计记录 |
| `password_hash` 策略 | 【待决：bcrypt/argon2 及加盐】 | 定为 bcrypt（cost 12，≤72 字节） | 待评审确认 |
| 角色模型 | 单 `role` 列 vs 独立 admin 表 vs RBAC【待决】 | 沿用单 `role` 列 | 管理员数量少、功能最小；RBAC 留 M2 评估 |

## 4. 实施批次

见 `tasks/todo.md`，共 4 批（按可验收行为重排）：

1. **MySQL 连接、User 模型及对应迁移基础**：MySQL 8.4 LTS 连接与独立测试库；`user` 模型 + 首个迁移；时间/email 规范化约定落地。
2. **注册接口闭环**：注册校验（含密码长度/字节上限）、bcrypt 哈希、落库、重复邮箱 409、服务端固定普通角色；注册写接口 CSRF/Origin 校验。
3. **用户登录/me/退出、会话与鉴权闭环**：`user_session` + 迁移、JWT 签发校验、真实密钥校验、退出撤销、`get_current_user` 真实实现、登录/退出 CSRF/Origin、Cookie/CORS 配置生效。
4. **管理员受控创建、独立登录、角色校验与双端会话隔离**：管理员受控创建、`/admin/auth/*`、`require_admin`、双端 `session_type`/`aud`/Cookie 隔离、管理端写接口 CSRF/Origin 复用。

数据库连接生命周期（lifespan 仅初始化/释放连接资源）在批次 1 生效；注册写接口 CSRF 在批次 2、登录/退出 CSRF 与真实密钥校验在批次 3、管理端写接口 CSRF 在批次 4，不全部推迟到最后一批。

## 5. 基线测试待办（首批实施前处理，本轮仅记录）

- `tests/test_production_config.py::test_production_app_disables_docs_and_serves_health` 用 `base_url='http://localhost'`，但 `ProductionConfig.allowed_hosts` 默认是 `["example.com","*.example.com","api.example.com"]`（示例域名，不含 localhost）。当前测试能过，是因为本机私有 `.env` 覆盖了 `ALLOWED_HOSTS`。
- **修正**：该测试子进程应显式设置 `ALLOWED_HOSTS`（如 `ALLOWED_HOSTS=localhost,127.0.0.1`），不依赖私有 `.env`。此修正放入批次 1 实施前处理；**本轮只记录任务，不修改运行时代码或测试代码**。

## 6. 风险与待评审项

| 项 | 状态 | 影响 | 建议 |
|---|---|---|---|
| MySQL 8.4 LTS 统一（开发/集成测试/部署） | 待评审 | 本地需 MySQL 8.4 实例 | 独立测试库 + 环境变量注入；SQLite 不作验收依据 |
| 会话承载 httpOnly cookie vs Bearer | 待评审 | 跨域/CSRF 复杂度 | 推荐双 Cookie + `aud`/`session_type` 绑定 |
| 密码策略（最小长度/复杂度） | 待评审（P12） | 注册校验 | 建议 ≥8 字符、≤72 字节；具体待定 |
| 邮箱验证、找回密码 | 建议首版不做（P12/FR-14 待定） | 未实现不得标已验证 | 留后续批次 |
| 管理员受控创建方式 | 待定 | 无公开注册、无默认密码 | 脚本/CLI 创建，具体待定 |
| 新依赖（Alembic、email-validator） | 待批准 | 锁文件变更 | 随批次 1/2 引入 |
| BaseConfig/TestingConfig 的 `cors_origins="*"`+credentials 矛盾 | 需修正 | 凭据型跨域 | 改为显式 origin 白名单 |
| 弱密钥/占位密钥（`effective_jwt_secret_key`） | 需拒绝 | 令牌可被伪造 | 任务 3 起校验并拒绝空值/教学默认值/`${PROD_SECRET_KEY}` 占位符 |
| 物理外键/主键/复合约束 | 留物理模型单独评审 | 属主一致性不靠 FK | 本方案只承诺服务端强制 |

## 7. 边界

本轮仅产出 `tasks/plan.md` 与 `tasks/todo.md`，保持运行时代码、依赖、锁文件、数据库、测试与其他仓库原样。不重复运行现有 19 项测试。PingCode：**未关联**（未提供真实编号，不编造）。
