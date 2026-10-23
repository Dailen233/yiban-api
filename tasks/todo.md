# 账号基础落地实施任务

> 状态：**待评审**。对应 `tasks/plan.md`。PingCode：**未关联**（未提供真实编号，不编造）。
> 每个任务完成后系统保持可运行；验收标准为「构建了正确的东西」，叠加在项目通用完成门槛（测试通过、无新告警、不泄露秘密）之上。

## 任务 1：MySQL 连接、User 模型及对应迁移基础

**Description**：接入 MySQL 8.4 LTS 连接与 Alembic（表结构唯一入口）；建立 `user` 表首个迁移（email UK、`DATETIME(6)` 无时区 UTC 约定）；lifespan **只初始化/释放连接资源，不 `create_all`、不自动迁移**；开发库与独立集成测试库隔离（`DATABASE_URL` 注入，不连接其他项目数据库，配置缺失/连接失败明确报错、不回退教师示例库）；处理基线测试的 `ALLOWED_HOSTS` 依赖（见下）。

**Acceptance criteria:**
- [x] `user` 模型与首个迁移脚本落地：`email` UNIQUE、`DATETIME(6)` 无时区 UTC、UUID 主键、`role` 默认 `'user'`；`UTCDateTime` 列类型绑定实现写入前转 UTC、读回恢复 UTC 语义（编译为 `DATETIME(6)`）；离线 SQL 验证通过（`DEFAULT 'user'`、`UNIQUE(email)`、`DATETIME(6)`）。
- [x] 测试库保护：集成测试只读 `TEST_DATABASE_URL`（不回退 `DATABASE_URL`）、`ensure_test_database` 限定目标库名 `yiban_api_test`（结构化 `make_url` 解析，非子串判断），缺失跳过、非法报错；新增无需数据库的保护测试证明开发库/教师库/其他库/非法 URL 在迁移/写入前被拒绝；连接失败时引擎释放、全局状态不残留。
- [x] 真实 MySQL 8.4（8.4.13）上的 `upgrade`→`downgrade`→`upgrade` 与持久化、规范化 email 唯一约束、事务回滚、UTC 时间往返（含非 UTC 偏移 + 微秒）验收，四项集成测试均真实执行通过。
- [x] 基线测试 `tests/test_production_config.py` 子进程显式 `ALLOWED_HOSTS`（JSON 数组）与 `DATABASE_ENABLED=false`，不依赖私有 `.env`；数据库默认关闭、启用时配置缺失或教师示例库按库名结构化拒绝；lifespan 仅初始化/释放连接资源，不 `create_all`、不自动迁移。

**Verification:**
- [x] `uv run alembic upgrade head --sql`（离线生成 SQL，验证迁移脚本）。
- [x] 带 `TEST_DATABASE_URL` 的完整回归 `DEBUG=release uv run --locked pytest -q`：40 passed、0 skipped（基础 36 + 集成 4）。
- [x] `uv run alembic upgrade head` + `downgrade -1`（仅独立测试库 `yiban_api_test`）。

**Dependencies:** None

**Files likely touched:** `alembic.ini`、`alembic/env.py`、`alembic/versions/*`、`models/user.py`、`config/config_unified.py`（database_url/数据库启用校验）、`app/factory.py`（lifespan 连接资源初始化/释放）、`tests/test_production_config.py`（基线修正）

**Estimated scope:** M（3-5 文件）

---

## 任务 2：注册接口闭环

**Description**：实现注册：邮箱/密码/昵称校验（含密码 ≥8 字符、UTF-8 ≤72 字节，超限拒绝不截断）、bcrypt 哈希（`run_in_executor` 不阻塞事件循环）、落库、重复邮箱 409、服务端固定普通角色 `'user'`（忽略请求体 role）；**同批启用注册写接口 CSRF/Origin 校验，并准备精确可信 Origin 配置、`X-Yiban-Request: 1` 自定义请求头及必要的 CORS/OPTIONS 预检支持**。

**Acceptance criteria:**
- [x] 注册成功 201，返回 `{id, email, display_name, role='user'}`；请求体携带 `role` 被忽略，绝不落库为 admin（集成测试验证）。
- [x] 重复 email → 409；密码 <8 字符或 UTF-8 编码 >72 字节 → 422（不截断、不 strip/lower、不做 SQL/XSS 黑名单清理）。
- [x] 注册写接口 CSRF/Origin：可信来源通过；恶意/缺失 Origin 拒绝、缺 `X-Yiban-Request` 请求头拒绝、OPTIONS 预检由 CORS 中间件放行；响应不返回 `password_hash`；bcrypt 哈希经 `asyncio.to_thread` 执行不阻塞异步。

**Verification:**
- [x] 真实 MySQL 8.4.13 集成测试：注册成功/重复 409/角色固定/bcrypt 哈希 5 项全通过（含并发同邮箱仅一条成功、另一条 409）。
- [x] 带 `TEST_DATABASE_URL` 完整回归 `DEBUG=release uv run --locked pytest -q`：72 passed、0 skipped。
- [x] 修正：并发重复注册（写入/flush/commit 同处异常边界，仅 email 唯一冲突转 409）；校验响应不回显原始输入（防密码泄露）；邮箱规范化后 ≤255 字符。HTTP 层补充非法 body 422、Origin=null 403、OPTIONS 预检 200。

**Dependencies:** 任务 1

**Files likely touched:** `schemas/auth.py`、`repository/user_repository.py`、`service/auth_service.py`、`api/auth.py`、`app/`（注册路由装配 + CSRF/Origin 校验）、`config/config_unified.py`（可信 Origin/CORS）

**Estimated scope:** M（3-5 文件）

---

## 任务 3：用户登录/me/退出、会话与鉴权闭环

**Description**：实现 `user_session` 模型 + 迁移；登录签发 JWT（`sub`/`aud=user`/`role` 快照/`jti`/`exp`）并写 `user_session`；**真实签名密钥校验在任务 3 生效（任何真实 JWT 签发前）**；`get_current_user` 真实实现（每次鉴权同时验证 JWT 签名与 `exp`、`session.user_id == JWT.sub`、`session.jti == JWT.jti`、`user_session` 存在且未过期未撤销、`user` 存在，并校验 `aud`/`session_type`/端点绑定）；退出置 `revoked_at` 立即失效；登录/退出写接口 CSRF/Origin（复用并扩展任务 2 的可信 Origin 校验与 `X-Yiban-Request` 请求头）、httpOnly cookie、凭据型 CORS 显式 origin 配置在本批生效。

**Acceptance criteria:**
- [ ] 登录签发 JWT + 写 `user_session(session_type='user')`；JWT `exp` 与 `session.expires_at` 换算到同一 UTC 时刻、过期比较正确；过期/伪造/已撤销 token 均 401；退出后原 token 立即 401。
- [ ] `me` 未认证/过期/退出后 401；每次鉴权满足 `session.user_id == JWT.sub`、`session.jti == JWT.jti` 且 `aud`/`session_type`/端点绑定；身份与角色由服务端查库得出（不信任 Token 内角色快照）。
- [ ] 真实密钥校验生效（拒绝空值/教学默认值/`${PROD_SECRET_KEY}` 占位符）；登录/退出 CSRF/Origin（可信通过、恶意/缺失/null 拒绝、缺请求头拒绝、预检通过）；httpOnly + SameSite=Lax + Secure（开发 localhost 豁免）cookie；`cors_origins` 显式白名单并允许 `X-Yiban-Request`。

**Verification:**
- `uv run --locked pytest -q tests/ -k auth`（会话/鉴权聚焦测试，覆盖过期、退出、越权、密钥校验、Cookie/CORS、CSRF）。

**Dependencies:** 任务 2

**Files likely touched:** `models/user_session.py`、`alembic/versions/*`、`core/permissions.py`、`service/auth_service.py`、`api/auth.py`、`config/config_unified.py`（密钥校验、CORS）、`app/middleware.py`/`app/config.py`（Cookie/CORS/CSRF 装配）

**Estimated scope:** M（3-5 文件）

---

## 任务 4：管理员受控创建、独立登录、角色校验与双端会话隔离

**Description**：管理员受控创建（脚本/CLI，无公开注册、无默认密码）；`/admin/auth/*` 登录/me/退出；`require_admin` 服务端查库校验 `role='admin'`；双端通过 `session_type`/JWT `aud`/不同 Cookie 名绑定隔离；管理端写接口 CSRF/Origin 复用（可信 Origin + `X-Yiban-Request: 1`）。真实密钥校验已在任务 3 生效。

**Acceptance criteria:**
- [ ] 管理员登录仅 `role='admin'` 成功；普通用户访问 `/admin/*` 403（不信任客户端或旧 Token 角色）。
- [ ] 用户端退出仅撤销 `session_type='user'` 对应会话，不误清管理员会话（反之亦然）；双端 Cookie/`aud`/`session_type` 绑定校验。
- [ ] 管理端写接口 CSRF/Origin 复用（可信通过、恶意/缺失/null 拒绝、缺请求头拒绝、预检通过）。

**Verification:**
- `uv run --locked pytest -q tests/ -k admin`（管理员与双端隔离聚焦测试）。
- `uv run --locked pytest -q`（全量回归）。

**Dependencies:** 任务 3

**Files likely touched:** `scripts/create_admin.py`、`api/admin_auth.py`、`core/permissions.py`（`require_admin`）、`service/auth_service.py`、`app/`（管理端 CSRF/Origin 复用装配）

**Estimated scope:** M（3-5 文件）

---

## Checkpoint：任务 1-2 后
- [ ] 迁移可执行、可回滚（独立测试库）；注册闭环通过（重复邮箱、密码边界、角色固定、CSRF/Origin）。

## Checkpoint：任务 3-4 后
- [ ] `uv run --locked pytest -q` 全绿；重复注册/错误凭据/过期/退出/越权/密钥校验/CSRF/双端隔离路径全部覆盖。

## 后续任务（不在本批，记录边界）
- 属主派生的真正落地（upload_file/task/book 的 `owner_id` 服务端注入）留到对应资源实现时验证。
- 邮箱验证、找回密码、用户禁用/角色管理、RBAC、完整审计属 P12 / M2，不在本批。
