# 账号基础落地实施任务

> 状态：**待评审**。对应 `tasks/plan.md`。PingCode：**未关联**（未提供真实编号，不编造）。
> 每个任务完成后系统保持可运行；验收标准为「构建了正确的东西」，叠加在项目通用完成门槛（测试通过、无新告警、不泄露秘密）之上。

## 任务 1：MySQL 连接、User 模型及对应迁移基础

**Description**：接入 MySQL 8.0 连接与 Alembic；建立 `user` 表首个迁移（email UK、UTC 时间约定）；lifespan 建池建表；开发库与数据库集成测试库隔离（`DATABASE_URL` 注入，不连接其他项目数据库）；处理基线测试的 `ALLOWED_HOSTS` 依赖（见下）。

**Acceptance criteria:**
- [ ] `user`（id/email UK/password_hash/display_name/role/created_at/updated_at）迁移可 `upgrade`/`downgrade`；email 唯一与规范化（strip+lower）约定落库。
- [ ] 开发库与集成测试库由 `DATABASE_URL` 隔离，纯逻辑测试不接数据库；集成测试连独立 MySQL 库。
- [ ] 基线测试 `tests/test_production_config.py` 的子进程显式设置 `ALLOWED_HOSTS=localhost,127.0.0.1`，不再依赖私有 `.env` 覆盖。

**Verification:**
- `uv run alembic upgrade head` + `alembic downgrade -1` 可执行。
- `uv run --locked pytest -q`（含基线测试修正后全绿）。

**Dependencies:** None

**Files likely touched:** `alembic.ini`、`alembic/env.py`、`alembic/versions/*`、`models/user.py`、`config/config_unified.py`（database_url）、`app/factory.py`（lifespan 建池/建表）、`tests/test_production_config.py`（基线修正）

**Estimated scope:** M（3-5 文件）

---

## 任务 2：注册接口闭环

**Description**：实现注册：邮箱/密码/昵称校验（含密码 ≥8 字符、UTF-8 ≤72 字节，超限拒绝不截断）、bcrypt 哈希（`run_in_executor` 不阻塞事件循环）、落库、重复邮箱 409、服务端固定普通角色 `'user'`（忽略请求体 role）。

**Acceptance criteria:**
- [ ] 注册成功 201，返回 `{id, email, display_name, role='user'}`；请求体携带 `role` 被忽略或拒绝，绝不落库为 admin。
- [ ] 重复 email → 409；密码 <8 字符或 UTF-8 编码 >72 字节 → 422（不截断、不 strip/lower、不做 SQL/XSS 黑名单清理）。
- [ ] 响应不返回 `password_hash`；哈希经线程池执行，不阻塞异步请求处理。

**Verification:**
- `uv run --locked pytest -q tests/ -k register`（注册闭环聚焦测试，覆盖重复邮箱、密码边界、角色固定）。

**Dependencies:** 任务 1

**Files likely touched:** `schemas/auth.py`、`repository/user_repository.py`、`service/auth_service.py`、`api/auth.py`、`app/`（注册路由装配）

**Estimated scope:** M（3-5 文件）

---

## 任务 3：用户登录/me/退出、会话与鉴权闭环

**Description**：实现 `user_session` 模型 + 迁移；登录签发 JWT（`sub`/`aud=user`/`role` 快照/`jti`/`exp`）并写 `user_session`；`get_current_user` 真实实现（每次鉴权同时验证 JWT 签名与 `exp`、`user_session` 存在且未过期未撤销、`user` 存在）；退出置 `revoked_at` 立即失效；httpOnly cookie、CSRF/Origin、凭据型 CORS 显式 origin 配置在本批生效。

**Acceptance criteria:**
- [ ] 登录签发 JWT + 写 `user_session(session_type='user')`；过期/伪造/已撤销 token 均 401；退出后原 token 立即 401。
- [ ] `me` 未认证/过期/退出后 401；身份与角色由服务端查库得出（不信任 Token 内角色快照）。
- [ ] 用户端会话 httpOnly + SameSite=Lax + Secure（开发 localhost 豁免）cookie；`cors_origins` 为显式列表（修正 BaseConfig/TestingConfig 的 `*`+credentials 矛盾）。

**Verification:**
- `uv run --locked pytest -q tests/ -k auth`（会话/鉴权聚焦测试，覆盖过期、退出、越权、Cookie/CORS）。

**Dependencies:** 任务 2

**Files likely touched:** `models/user_session.py`、`alembic/versions/*`、`core/permissions.py`、`service/auth_service.py`、`api/auth.py`、`config/config_unified.py`（CORS）、`app/middleware.py`/`app/config.py`（Cookie/CORS 装配）

**Estimated scope:** M（3-5 文件）

---

## 任务 4：管理员受控创建、独立登录、角色校验与双端会话隔离

**Description**：管理员受控创建（脚本/CLI，无公开注册、无默认密码）；`/admin/auth/*` 登录/me/退出；`require_admin` 服务端查库校验 `role='admin'`；双端通过 `session_type`/JWT `aud`/不同 Cookie 名绑定隔离；启用真实鉴权时拒绝教学默认密钥。

**Acceptance criteria:**
- [ ] 管理员登录仅 `role='admin'` 成功；普通用户访问 `/admin/*` 403（不信任客户端或旧 Token 角色）。
- [ ] 用户端退出仅撤销 `session_type='user'` 对应会话，不误清管理员会话（反之亦然）；双端 Cookie/`aud`/`session_type` 绑定校验。
- [ ] 启用真实鉴权时，`secret_key` 为教学默认值或 `PROD_SECRET_KEY` 未设置时拒绝启动/显式报错。

**Verification:**
- `uv run --locked pytest -q tests/ -k admin`（管理员与双端隔离聚焦测试）。
- `uv run --locked pytest -q`（全量回归）。

**Dependencies:** 任务 3

**Files likely touched:** `scripts/create_admin.py`、`api/admin_auth.py`、`core/permissions.py`（`require_admin`）、`service/auth_service.py`、`config/config_unified.py`（密钥校验）、`app/factory.py`

**Estimated scope:** M（3-5 文件）

---

## Checkpoint：任务 1-2 后
- [ ] 迁移可执行、可回滚；注册闭环通过（重复邮箱、密码边界、角色固定）。

## Checkpoint：任务 3-4 后
- [ ] `uv run --locked pytest -q` 全绿；重复注册/错误凭据/过期/退出/越权/双端隔离路径全部覆盖。

## 后续任务（不在本批，记录边界）
- 属主派生的真正落地（upload_file/task/book 的 `owner_id` 服务端注入）留到对应资源实现时验证。
- 邮箱验证、找回密码、用户禁用/角色管理、RBAC、完整审计属 P12 / M2，不在本批。
