# 译伴 TXT 上传模块 · 基础实施清单（待评审）

> 状态：**待评审**。对应 `tasks/upload-foundation-plan.md`。评审通过后实施；实施前不运行迁移、不改代码。
> PingCode：**未关联**（未提供真实编号，不编造）。
> 范围：仅「登录用户上传 `.txt` → 私有存储 → 元数据入库 → 按属主读元数据」的最小闭环，不创建任务/翻译/书库。

---

## 任务拆解（一个上传闭环，非独立 PR）

### 任务 1：`upload_file` 模型与迁移 0003

**涉及文件**
- 新增 `models/upload_file.py`
- 新增 `alembic/versions/0003_create_upload_file_table.py`
- 修改 `models/__init__.py`（导出 `UploadFile`）

**Description**：按 plan §3 建模 `upload_file`（UUID `String(36)` 主键、`owner_id` FK+索引、`original_name VARCHAR(255)`、`storage_ref VARCHAR(255)` **UNIQUE**、`ext VARCHAR(16)`、`size_bytes BIGINT`、`sha256 CHAR(64)`、`created_at UTCDateTime`）。迁移 `down_revision="0002"`，可升级/可回滚。

**完成标准（Verification）**
- [ ] 迁移 `upgrade`/`downgrade` 往返成功（受保护 `yiban_api_test`）。
- [ ] 不修改 0001/0002；`owner_id` 有索引；`storage_ref` 唯一约束；外键指向 `user.id`。
- [ ] 不生成 task/章节/翻译/书库等表。

---

### 任务 2：私有存储层与上传配置口径

**涉及文件**
- 新增 `service/upload_storage.py`（纯存储：写临时、fsync、`os.link` 无覆盖发布、删除）
- 修改 `config/config_unified.py`（`BaseConfig` 增 `upload_max_file_bytes`/`upload_allowed_extensions`/`upload_storage_dir`）
- 修改 `.gitignore`（加 `storage/`）

**Description**：本地私有目录 `storage/uploads/`（服务端生成相对 `storage_ref`）；流式分块写 `.part` → 累计 `size_bytes`/`sha256` → 超限即拒并清理 → `fsync` + `os.link` 无覆盖发布。阻塞 I/O 经 `run_in_threadpool`。上传大小上限可配置 20 MiB（20971520 字节，待评审）。

**完成标准（Verification）**
- [ ] 默认 bootstrap（`database_enabled=False`）仅 import 代码**不初始化**上传存储、不创建目录。
- [ ] 上传配置口径与教师模板 `max_file_size`/`allowed_file_extensions` 死字段切割，不读死字段。
- [ ] 写入异常/超限/客户端中断清理临时 `.part` 文件（单元测试用临时目录）。
- [ ] `storage_ref` 不含绝对路径、不含客户端文件名；同名内容不同 `storage_ref`。
- [ ] **无覆盖发布**：发布用 `os.link`，人为制造存储名碰撞时 `FileExistsError` → 原文件/原记录不被覆盖、不被误删（见任务 4 测试）。
- [ ] 阻塞 I/O（写/fsync/link/unlink）均经线程池，不直接阻塞事件循环。

---

### 任务 3：Service / Repository / Schema 与两个接口

**涉及文件**
- 新增 `repository/upload_file_repository.py`
- 新增 `service/upload_service.py`
- 新增 `schemas/upload.py`
- 新增 `api/v1/uploads.py`
- 修改 `api/v1/__init__.py`（注册路由）
- 修改 `service/dependencies.py`（追加 `get_upload_service`）

**Description**：`POST /api/v1/uploads`（201，`{file_id, original_name, ext, size_bytes, created_at}`）与 `GET /api/v1/uploads/{file_id}`（200；不存在/他人统一 404）。`owner_id` 服务端派生自 `get_current_user`；写接口复用 `require_auth_enabled` + `require_trusted_origin`。Service 控制事务与失败补偿（覆盖 add/flush/commit 三阶段，见 plan §4.3/§4.4），Repository 只做单条 create/get_owned。

**完成标准（Verification）**
- [ ] 上传成功返回不泄露 `storage_ref`/路径/公开 URL。
- [ ] `owner_id` 由当前身份派生，客户端夹带 `owner_id` 不改变归属。
- [ ] 管理员会话（`yiban_admin_session`）不能用于本接口；管理员不自动获得他人文件访问权。
- [ ] 错误沿用 `ErrorResponse`（含 `timestamp`）；时间 `created_at` 为 ISO 8601 UTC（`+00:00` 后缀）。
- [ ] **预期失败转安全 500**：文件系统/数据库失败显式捕获，`debug=True` 下也不回显绝对路径/SQL 参数/堆栈（见任务 4 测试）。

---

### 任务 4：测试与真实 MySQL 验收

**涉及文件**
- 新增 `tests/test_upload_*.py`（单元 + 集成）

**Description**：单元测试（文件流用临时目录、假 Storage/Repository 替身）覆盖规则分支与一致性三态；集成测试用受保护 `TEST_DATABASE_URL`（`yiban_api_test`）与临时上传目录。

**完成标准（Verification）—— 下列验收项全部通过，跳过不得算通过**
- [ ] 合法 TXT：真实保存、元数据入库、`sha256` 与 `size_bytes` 正确、响应不泄露存储位置。
- [ ] 不支持扩展名（含 `.docx`/`.epub`/`.pdf`）、大小边界（等于/略超 20 MiB）、空文件、异常文件名（缺失/超长/路径分隔符 `/`/`\`/`..`/大小写）。
- [ ] 未登录 401、鉴权关闭 503、CSRF/Origin 拒绝 403。
- [ ] 两个用户隔离：A 看不到 B 的文件；B 的 `file_id` 对 A 返回 404；客户端指定他人属主无效。
- [ ] 同名重复上传不覆盖已有文件（各自独立 `storage_ref` 与记录）。
- [ ] **存储名碰撞**：人为制造相同 `storage_ref`，原文件、原记录不被覆盖或误删。
- [ ] **一致性三态**：`flush` 确定性失败（唯一冲突）→ rollback + 删文件；`commit` 成功 → 文件+记录就绪；`commit` 结果不明（连接中断）→ 保守保留文件、返回安全 500、记录待核对，**不删文件**。
- [ ] **清理失败尽力补偿**：删除失败不承诺无残留，记录日志并继续返回业务结果。
- [ ] **请求体限制**：缺失 `Content-Length` 仍正确拒绝超限文件（以累计字节为准）；整体请求超限的早期粗判（可选）不误伤合法文件；文件大小边界判定正确；请求结束 `SpooledTemporaryFile` 释放（临时资源不残留）。
- [ ] **`debug=True` 失败注入**：文件写失败、DB 提交失败时响应为安全 500，不含绝对路径/SQL 参数/内部异常文本。
- [ ] 真实 MySQL 迁移与持久化验证；**存量账号行为不回归**（完整回归含账号测试仍通过）。

---

## 边界（测试与实施）

- 数据库集成测试**只用**受保护 `TEST_DATABASE_URL`（`yiban_api_test`）；文件测试**只用临时目录**；不对开发库或真实上传目录做清空/回滚。
- 上传成功仅代表「文件已保存 + 元数据入库」，不等于创建任务/翻译完成/整书业务就绪。
- 不修改已验收账号接口、鉴权行为、依赖、锁文件、来源快照。

---

## 老师最新要求（实施阶段完成，均保持未完成）

> 以下为老师补充的交付要求，评审通过后随实施完成；本轮仅记录，不做、不勾选。

- [ ] **关键源码阅读与手写练习**：上传相关关键源码（FastAPI/Starlette multipart 解析、依赖鉴权、UploadFile 分块、Service/Repository 分层）阅读并**手写**必要练习，记录实际学习内容；**不以自动生成代码代替个人理解**。
- [ ] **Apipost 维护**：新增两个接口同步维护 Apipost 请求、参数说明、成功/失败示例，并做可恢复备份。
- [ ] **DBeaver 只读核对**：通过 DBeaver 只读核对 `upload_file` 字段、约束、属主与实际上传记录。
