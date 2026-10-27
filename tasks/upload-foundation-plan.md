# 译伴 TXT 上传模块 · 基础设计与实施清单（待评审）

> 状态：**待评审**。本文为「上传后端」首个切片的基础设计，供评审确认后直接实施，不含整书处理系统设计。
> 依据：中央资料《任务接口契约草案.md》（接口 1 + 通用约定）、《数据库逻辑模型草案.md》（§3.2 `upload_file`、§4.3 属主一致性）、《需求分析与设计文档说明.md》（§3.5、FR-01、FR-02、NFR-03、P10）。
> 边界：上传阶段**不解析正文**；正文提取、损坏内容判定属后续处理阶段（FR-02）。早期文档「不写业务代码」是历史阶段边界，非永久限制。
> 本轮核实依据：锁定版本 **FastAPI 0.159.1 / Starlette 1.9.0 / Pydantic 2.14.1** 源码（`.venv/lib/python3.12/site-packages/`）。

---

## 1. 范围与结论

本批仅覆盖「登录用户上传一个 `.txt` 文件 → 落私有存储 → 元数据入库 → 按属主读取元数据」的最小闭环。**不创建 task、不翻译、不建书库**；`upload_file` 是本批唯一的物理表（加一条迁移 0003）。

**推荐方案（明确结论，非罗列选项）**：

| 决策点 | 推荐 |
|---|---|
| 接口 | `POST /api/v1/uploads`（201）+ `GET /api/v1/uploads/{file_id}`（本批**拟新增**的实现契约） |
| 承载 | multipart/form-data，文件字段 `file`，原始文件名取 multipart 文件名 |
| 物理表 | `upload_file`，UUID `String(36)` 主键 + `UTCDateTime`（MySQL `DATETIME(6)` UTC），一条迁移 0003 |
| 存储 | 本地私有目录 `storage/uploads/`（服务端生成相对 `storage_ref`，Git 忽略），不接对象存储/新基础设施 |
| 大小限制 | 可配置 **20 MiB（20 × 1024 × 1024 = 20971520 字节）**，流式累计实际字节，**待评审（P10 未确认）** |
| 首版格式 | 仅 `.txt`；上传阶段保留原始字节，不做去噪/翻译/黑名单清洗 |

---

## 2. 最小接口契约

### 2.1 上传 `POST /api/v1/uploads`

| 项 | 内容 |
|---|---|
| 请求 | multipart/form-data；字段 `file`（必填，二进制）；原始文件名取 multipart 部分的 `filename`，**不取**任何 JSON/表单里的自定义文件名字段 |
| 鉴权 | 用户端会话（`get_current_user`，Cookie `yiban_user_session`）；写接口复用 `require_auth_enabled` + `require_trusted_origin`（Origin 精确匹配 + `X-Yiban-Request: 1`） |
| 成功 | **201**，响应 `{ "file_id", "original_name", "ext", "size_bytes", "created_at" }` |
| 失败 | 未登录 401；鉴权关闭 503；CSRF/Origin 拒绝 403；非 `.txt` 422；空文件/非法文件名 422；大小超限 413；存储写入/DB 失败 500（不泄露路径/堆栈） |

- **不返回** `storage_ref`、磁盘路径或公开文件 URL（NFR-03）。
- `owner_id` 一律由 `current_user.id` 服务端派生；客户端夹带任何 `owner_id` 字段均被忽略、不改变归属。

### 2.2 元数据读取 `GET /api/v1/uploads/{file_id}`（**本批拟新增的实现契约**）

> 明确声明：中央草案只规定了上传接口（接口 1）与「下载/读取须经服务端鉴权并校验属主」的原则；**本元数据读取接口是本批为前端联调与自查而拟新增的实现契约，不冒充中央草案已有规定**。

| 项 | 内容 |
|---|---|
| 请求 | 路径参数 `file_id`（UUID 字符串）；无请求体 |
| 鉴权 | 用户端会话（`get_current_user`）+ `require_auth_enabled` |
| 成功 | **200**，响应 `{ "file_id", "original_name", "ext", "size_bytes", "created_at" }`（与上传响应同构） |
| 失败 | 未登录 401；鉴权关闭 503；`file_id` 不存在、**或属于他人**，统一返回 **404**（不泄露他人文件是否存在） |

- 只返回当前用户拥有的文件元数据；`storage_ref`、物理路径、文件内容均不返回。
- **仅有管理员会话不能代替用户端会话**；管理员身份不自动获得他人文件访问权（读取私有内容属后续审核上下文，本批不实现）。

### 2.3 错误语义、时间格式与状态码口径

- **错误响应结构对齐现有 `app/exceptions.py`**：统一 `ErrorResponse`，字段为 `{ success, code, message, data, timestamp }`；其中 `timestamp` 由 `BaseResponse` 的 `default_factory` 生成。**HTTP 状态码与响应体 `code` 是两层**：HTTP 状态码在响应行，响应体 `code` 是 `ResponseCode` 业务码。
- 现有映射关系（本批**不改**）：`BaseAPIException` 走 `api_exception_handler`（`code` 与 HTTP 状态码一致）；`HTTPException` 走 `http_exception_handler`（404→`NOT_FOUND`、405→`METHOD_NOT_ALLOWED`、≥500→`INTERNAL_SERVER_ERROR`、其余→`BAD_REQUEST`）。上传模块 CSRF/未登录复用现有 `require_trusted_origin`/`get_current_user`（沿用其现有状态码行为，不修改账号错误映射）。
- **413 待评审**：现有 `ResponseCode` 无「Payload Too Large」项。推荐大小超限用 `HTTPException(413)`；按现有 `http_exception_handler` 会映射为响应体 `code=400`（HTTP 仍 413）。**是否新增 `PAYLOAD_TOO_LARGE` 响应码留待评审，本批不扩、不改全局映射。**
- **时间格式**：`created_at` 为 `UTCDateTime` 读回的 aware UTC `datetime`；FastAPI 响应经 `jsonable_encoder` 序列化为 **ISO 8601 UTC、`+00:00` 后缀**（如 `2026-10-27T12:34:56.789012+00:00`），**不使用 `Z` 后缀**（已实测：`jsonable_encoder` 对 aware UTC 输出 `+00:00`，与 Pydantic `model_dump_json` 的 `Z` 不同）。
- `ext` 小写、含前导点（`".txt"`）；`size_bytes` 为实际落盘字节数；`sha256` 仅在存储侧校验，不出现在响应。

---

## 3. `upload_file` 物理模型与迁移

沿用已验收的 UUID 字符串主键、`UTCDateTime`（MySQL `DATETIME(6)` 无时区存 UTC）与 `ForeignKey`+索引写法（见 `models/user.py`、`models/user_session.py`）。

### 3.1 字段表

| 字段 | 物理类型 | NULL | 默认值 | 外键/索引 | 说明 |
|---|---|---|---|---|---|
| `id` | `VARCHAR(36)` | 否 | `uuid4()`（应用层） | PK | 文件记录 ID，服务端生成 |
| `owner_id` | `VARCHAR(36)` | 否 | — | FK → `user.id`，`index=True` | 属主，服务端派生自当前身份 |
| `original_name` | `VARCHAR(255)` | 否 | — | — | 原始文件名（**仅展示**，不作唯一标识、不作磁盘路径） |
| `storage_ref` | `VARCHAR(255)` | 否 | — | **UNIQUE** | 服务端生成的**相对**存储引用（如 `{uuid}.txt`），不含绝对路径；**唯一约束防覆盖** |
| `ext` | `VARCHAR(16)` | 否 | — | — | 小写扩展名（首版 `.txt`） |
| `size_bytes` | `BIGINT` | 否 | — | — | 实际落盘字节数（20 MiB 内 INT 足够，选 BIGINT 防未来扩容溢出） |
| `sha256` | `CHAR(64)` | 否 | — | — | 小写十六进制 SHA-256（完整性校验；**不加唯一约束**） |
| `created_at` | `DATETIME(6)` | 否 | `utcnow()` | — | 上传时间（UTC 语义） |

### 3.2 约束与取舍

- **`storage_ref` 加唯一约束**：与「内容去重」明确区分——`sha256`、`original_name` 均**不唯一**，允许同名/同内容独立上传；`storage_ref` 唯一只保证「一条记录对应一个存储文件，不覆盖」。
- 属主一致性按中央草案 §4.3：`upload_file.owner_id` 由服务端派生；外键只保证「引用存在」，不保证「属主相等」，故**应用层强制**（本表仅服务端写 `owner_id = 当前用户`）。
- 只新增这一张表与迁移 0003，**不生成** task/chapter/paragraph/translation_unit/book/book_file；**不改**已验收的 0001/0002。

### 3.3 迁移

- 新迁移 `0003_create_upload_file_table.py`，`down_revision="0002"`；`downgrade()` 用 `op.drop_table("upload_file")`（MySQL 会一并清理外键约束），并在建表后 `op.create_index` 于 `owner_id`；`storage_ref` 建唯一约束。
- 风格对齐 0001/0002（`mysql.DATETIME(fsp=6)`、`sa.String(36)` 主键、`sa.ForeignKey("user.id")`、`sa.UniqueConstraint`）。

---

## 4. 私有存储与一致性

### 4.1 位置、命名与无覆盖发布

- 私有目录 **`storage/uploads/`**，位于静态资源与公开下载目录之外，新增到 `.gitignore`（`storage/`）。
- `storage_ref` 为服务端生成：`f"{uuid4().hex}{ext}"`（相对路径，`ext` 首版 `.txt`）。**不拼接、不信任客户端文件名**（防路径穿越与同名冲突）。
- **文件系统无覆盖发布**：普通 `os.rename` 在 Linux 上原子但**可能覆盖已存在目标**，不能作为「不覆盖」保证。推荐：写临时文件 `storage_ref + ".part"` → `fsync` → **`os.link(part_path, final_path)`（硬链接，原子，目标已存在则抛 `FileExistsError`）** → `os.unlink(part_path)`。`os.link` 在同一文件系统（`storage/uploads/` 内）可用；若 `FileExistsError`（人为碰撞）则删除 `.part` 并报冲突，**不覆盖原文件/原记录**。
- 存储代码集中、简单：一个 `service/upload_storage.py` 封装「写临时文件 → fsync → 无覆盖发布 → 删除文件」，不预建插件体系、不启动对象存储/消息队列等新基础设施。

### 4.2 阻塞 I/O 执行方式

- 文件写、`fsync`、`os.link`、`os.unlink`、`os.remove` 均为**阻塞 I/O**；统一经 `fastapi.concurrency.run_in_threadpool`（或 `starlette.concurrency.run_in_threadpool`）在线程池执行，**不直接阻塞异步事件循环**。
- `UploadFile.read(size)` / `write()` 在文件滚盘后已由 Starlette 走线程池（源码 `run_in_threadpool`）；Service 从 `UploadFile` 分块读、写最终存储同样经线程池。

### 4.3 写入操作顺序与数据库写入三阶段

```
1. 校验扩展名（小写后 == ".txt"）→ 拒绝非 .txt（422）
2. 校验 original_name（见 §5.1 规则）→ 非法拒绝（422）
3. 服务端生成 storage_ref + 临时文件名 storage_ref + ".part"
4. 流式分块读 UploadFile → 线程池写 .part；边写边累计 size_bytes、更新 sha256
5. size_bytes 超限 → 删除 .part，拒绝（413）
6. fsync(.part) → os.link(.part → storage_ref)（无覆盖发布）→ unlink(.part)
7. 构造 upload_file 记录 → repository.add + flush（flush 触发 INSERT，未提交）
8. db.commit（提交事务）
```

数据库写入分三阶段，**不能只捕获 commit**：

| 阶段 | 动作 | 失败语义 |
|---|---|---|
| `add` | 对象入 session，未发 SQL | 无失败风险点 |
| `flush` | 发 INSERT SQL（含唯一约束校验），**未提交** | 失败（如 `storage_ref` 唯一冲突、外键失败）→ **确认未提交**，rollback + 删文件 + 报错 |
| `commit` | 提交事务 | 见 §4.4 |

### 4.4 提交结果三态与保守补偿

| 结果 | 判定 | 处理 |
|---|---|---|
| **确认未提交** | `flush` 阶段确定性失败（唯一约束 1062、外键失败等，事务可回滚） | rollback + 删除已发布文件，报错（可安全删除） |
| **提交成功** | `commit` 正常返回无异常 | 文件 + 记录均就绪，返回 201 |
| **结果不明** | `commit` 抛连接中断/超时（如 `OperationalError` 连接丢失），无法确定是否已提交 | **保守保留文件**，返回安全 500，记录待核对事项（含 `storage_ref`），**不删除文件**（避免误删已入库记录对应的文件） |

- **不因「结果不明」直接认定数据库未落库并删除最终文件**；不引入分布式事务、不引入后台清理服务（保守 + 简单）。

### 4.5 孤儿文件与残留边界（分别写清，不笼统）

| 崩溃/失败时点 | 结果 |
|---|---|
| `.part` 写入期间崩溃 | 残留 `.part` 临时文件（无记录）；可安全清理 |
| `os.link` 发布后、`commit` 前崩溃 | 残留最终文件、**无记录** → 孤儿文件（需人工/后续清理） |
| `commit` 成功后崩溃 | 文件 + 记录**均在**，**无孤儿文件** |
| `commit` 已提交但响应发送失败 | 文件 + 记录均在；客户端视为失败会**重试产生新记录**（新 `storage_ref`，不覆盖、不孤儿），属「至少一次」语义，不在本批消重 |

- **数据库事务不能回滚物理文件**：这是明确边界，不声称已解决。
- **清理操作失败只能尽力补偿**：删除文件失败（权限/磁盘）不能承诺所有异常下都无残留；记录日志并继续返回业务结果。**不承诺「任何异常都无残留」**。

---

## 5. 上传规则与配置

### 5.1 首版规则（仅 `.txt`，文件名规则已选定）

| 场景 | 处理 |
|---|---|
| 扩展名非 `.txt`（含大小写归一化后） | 拒绝（422），提示仅支持 `.txt` |
| 大小写 `.TXT` / `.Txt` | 归一化小写后接受 |
| 文件名缺失（空） | 拒绝（422） |
| 文件名超长（>255 字符） | 拒绝（422） |
| **文件名含路径分隔符/目录遍历（`/`、`\`、`..`）** | **拒绝（422）**（选定唯一规则，不再「可接受或转义」两可） |
| 空文件（0 字节） | 拒绝（422） |
| 文件内容 | **保留原始字节**，不做正文去噪、翻译、SQL/XSS 黑名单清洗（正文处理属后续 FR-02） |

> 路径分隔符规则已选定为**拒绝**：`original_name` 仅展示但含分隔符会在前端/日志造成歧义，统一拒绝更简单可预期；存储名始终服务端生成，不受此规则影响。

### 5.2 大小限制口径（推荐，待评审）

- **P10 的 20 MB 尚未确认**。推荐暂用可配置 **20 MiB = 20971520 字节**，单位与字节数显式写死，状态标**待评审**，不写成用户已确认。
- 新增上传专用字段（挂在 `BaseConfig`，`DevelopmentConfig` 按需覆盖）：
  - `upload_max_file_bytes: int = 20971520`（20 MiB，文件本体，权威判定）
  - `upload_allowed_extensions: list[str] = [".txt"]`（首版）
  - `upload_storage_dir: str = "storage/uploads"`（私有目录）

### 5.3 请求体限制的生效阶段（锁定版本源码核实）

**锁定版本已有能力**（`starlette/formparsers.py`、`fastapi/routing.py`、`fastapi/dependencies/utils.py` 实测）：

- `MultiPartParser.max_part_size = 1 MiB`：**只限制非文件字段**（`on_part_data` 中 `self._current_part.file is None` 分支才检查），**不限制文件大小**；`max_files`/`max_fields` 默认 1000。FastAPI 调 `request.form()` 时用默认值，不传自定义上限。
- `SpooledTemporaryFile(max_size=1 MiB)`：文件在内存累积到 1 MiB 后滚落磁盘，是**内存/磁盘阈值，不是文件大小限制**。
- Starlette/FastAPI **无整个请求体上限**；锁定版本**无法在解析期间限制文件大小**（`max_part_size` 不作用于文件）。

**实际执行顺序**（`routing.py::get_request_handler` 先读 body、`dependencies/utils.py::solve_dependencies` 后解依赖）：

1. **multipart 解析（先于鉴权）**：`request.form()` → `MultiPartParser.parse()` 流式读请求体；非文件字段受 1 MiB 限制，文件字段流式写入 `SpooledTemporaryFile`（1 MiB 后滚盘，**无大小上限**）。
2. **依赖鉴权**：`require_auth_enabled` → `require_trusted_origin` → `get_current_user`。
3. **处理函数**：Service 从 `UploadFile`（SpooledTemporaryFile）分块读，写最终存储并累计 `size_bytes`。

**推论（必须写清）**：
- 文件大小限制**只能**在步骤 3（Service 流式累计实际字节）权威判定；**不能**把 `max_part_size`（限非文件字段）或 `SpooledTemporaryFile`（仅阈值）当成文件大小限制，**不能只信任 `Content-Length`**（可伪造/缺失）。
- 鉴权前文件已落入 `SpooledTemporaryFile`（临时，FastAPI 用 `file_stack.push_async_callback(body.close)` 在请求结束自动关闭删除，**无永久残留**）；未鉴权大文件会短暂占用临时磁盘，此为锁定版本默认行为，本批**不自定义中间件**在解析期间拦截（不升级依赖）。
- 整个请求体上限（multipart 开销 + 文件）锁定版本无内置；可选：在依赖层读 `Content-Length` 做**早期粗判**（若存在且 > `upload_max_file_bytes + 1 MiB` 余量则 413），但仅加速拒绝、**不作为最终依据**，最终仍以步骤 3 累计为准。

### 5.4 现有死配置追踪与推荐口径

实测追踪（本轮只读核实）：

| 现有字段 | 定义位置 | 实际调用 | 结论 |
|---|---|---|---|
| `max_request_size` | Base=10 MiB / Dev=50 MiB | 仅 `config/manage.py:112` 展示 | **死配置**，无上传逻辑读取 |
| `max_file_size` | Base=50 MiB / Dev=100 MiB | 同上 | **死配置** |
| `upload_dir` / `quarantine_dir` | Base/Dev/Testing 各自定义 | 仅 manage 展示 | **死配置** |
| `allowed_file_extensions` / `allowed_mime_types` | Base 含多种教学格式 | 仅定义 + `field_validator` 列表，无读取 | **死配置** |

- 推荐：上传模块只读新增的 `upload_max_file_bytes`/`upload_allowed_extensions`/`upload_storage_dir`，**不改、不复用**上述死字段（避免「只改 `max_file_size` 这个没人读的字段」的假生效）。

---

## 6. 上传失败响应（不泄露内部细节）

- **核实 `app/exceptions.py`**：`general_exception_handler` 中 `detail = str(exc) if settings.debug else "服务器内部错误"`。即 `debug=True`（开发/测试默认）时，未捕获异常的 `str(exc)` 会回显（可能含绝对路径、SQL 参数、内部异常文本）。
- 设计：上传 Service **显式捕获预期失败**并转换为安全 500，不依赖全局兜底回显：
  - 文件系统失败（`OSError`/`FileExistsError`/写盘失败）→ 捕获后转为安全 500（如「文件保存失败」），不泄露路径。
  - 数据库失败（`SQLAlchemyError`/`IntegrityError`）→ 捕获后按 §4.3/§4.4 处理，安全 500，不泄露 SQL/参数。
  - 业务校验失败（扩展名/文件名/空文件/大小）→ 用明确异常/状态码（§2.3），非 500。
- **不重构全局异常体系、不改账号接口**；仅上传模块自管预期失败。补充 `debug=True` 下的失败注入验收（§见 todo）。

---

## 7. Service / Repository 分层

沿用已验收模式（`AuthService` 控制事务、`Repository` 只做单条数据访问）：

- `models/upload_file.py`：`UploadFile` 模型（字段见 §3）。
- `repository/upload_file_repository.py`：`create()`（add+flush 不 commit）、`get_owned(id, owner_id)`（`WHERE id=? AND owner_id=?`，不存在/他人返回 None）。
- `service/upload_service.py`：编排「校验 → 流式落盘 → 计算 sha256/size → 入库（add/flush/commit）→ 失败补偿（§4.4）」；事务边界在 Service，阻塞 I/O 经线程池。
- `service/upload_storage.py`：纯存储操作（写临时、fsync、无覆盖发布、删除），不碰数据库、不 import Service。
- `schemas/upload.py`：`UploadResponse`（`{file_id, original_name, ext, size_bytes, created_at}`）。
- `api/v1/uploads.py`：路由（`POST /uploads`、`GET /uploads/{file_id}`），注册进 `api/v1/__init__.py`。
- `service/dependencies.py`：追加 `get_upload_service`。

---

## 8. 待评审点与相对中央草案的新增决定

**待评审（未确认，不写成用户/老师已确认）**：
- P10 上传大小上限：推荐可配置 20 MiB（20971520 字节），待确认。
- 是否新增 `PAYLOAD_TOO_LARGE` 响应码（413 与响应体 `code` 对齐）：本批不扩、不改全局映射，待评审。
- 首版是否在创建任务前做「TXT 可读性浅探针」（中央草案标注【待决】）：本批上传阶段**不做**。

**相对中央草案的本批新增决定（我方建议）**：
- `GET /api/v1/uploads/{file_id}` 元数据读取接口为本批拟新增实现契约（§2.2，不冒充草案已有）。
- 上传专用配置三字段（§5.2）与教师模板死字段切割；`storage_ref` 唯一约束 + `os.link` 无覆盖发布（§3、§4）。
- `size_bytes` 用 `BIGINT`、`sha256` 不唯一、`original_name` 仅展示；文件名含路径分隔符**拒绝**（§5.1）。
- 提交结果三态 + 保守保留文件的补偿（§4.4）。

---

## 9. 边界（本轮）

- 本轮仅产出本文件与 `tasks/upload-foundation-todo.md`，**不运行迁移、不修改运行时代码/依赖/私有配置/数据库，不改前端与中央资料仓库，不停止现有服务**。
- 不扩展成整书处理系统；不修改已验收的账号架构（鉴权、Cookie、会话撤销、AUTH_ENABLED 行为不变）。
- 上传成功仅代表「文件已保存 + 元数据入库」，**不等于**创建任务、翻译完成或整书业务就绪。
