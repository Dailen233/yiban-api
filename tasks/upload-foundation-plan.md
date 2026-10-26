# 译伴 TXT 上传模块 · 基础设计与实施清单（待评审）

> 状态：**待评审**。本文为「上传后端」首个切片的基础设计，供评审确认后直接实施，不含整书处理系统设计。
> 依据：中央资料《任务接口契约草案.md》（接口 1 + 通用约定）、《数据库逻辑模型草案.md》（§3.2 `upload_file`、§4.3 属主一致性）、《需求分析与设计文档说明.md》（§3.5、FR-01、FR-02、NFR-03、P10）。
> 边界：上传阶段**不解析正文**；正文提取、损坏内容判定属后续处理阶段（FR-02）。早期文档「不写业务代码」是历史阶段边界，非永久限制。

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
| 失败 | 未登录 401；鉴权关闭 503；CSRF/Origin 拒绝 403；非 `.txt` 422；空文件 422；大小超限 413；存储写入/DB 失败 500（不泄露路径/堆栈） |

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

### 2.3 错误语义与时间格式

- 错误响应沿用现有 `app/exceptions.py` 的统一 `ErrorResponse`（`{code, message, success, data}`），不新增外层。
- `created_at` 返回 **ISO 8601 UTC**（`YYYY-MM-DDTHH:MM:SS.ffffff+00:00`），由 `UTCDateTime` 读回的 aware UTC 经 Pydantic `datetime` 序列化得到。
- `ext` 小写、含前导点（`".txt"`），与中央草案 §3.2 口径一致；`size_bytes` 为实际落盘字节数；`sha256` 仅在存储侧校验，不出现在响应。

---

## 3. `upload_file` 物理模型与迁移

沿用已验收的 UUID 字符串主键、`UTCDateTime`（MySQL `DATETIME(6)` 无时区存 UTC）与 `ForeignKey`+索引写法（见 `models/user.py`、`models/user_session.py`）。

### 3.1 字段表

| 字段 | 物理类型 | NULL | 默认值 | 外键/索引 | 说明 |
|---|---|---|---|---|---|
| `id` | `VARCHAR(36)` | 否 | `uuid4()`（应用层） | PK | 文件记录 ID，服务端生成 |
| `owner_id` | `VARCHAR(36)` | 否 | — | FK → `user.id`，`index=True` | 属主，服务端派生自当前身份 |
| `original_name` | `VARCHAR(255)` | 否 | — | — | 原始文件名（**仅展示**，不作唯一标识、不作磁盘路径） |
| `storage_ref` | `VARCHAR(255)` | 否 | — | — | 服务端生成的**相对**存储引用（如 `{uuid}.txt`），不含绝对路径 |
| `ext` | `VARCHAR(16)` | 否 | — | — | 小写扩展名（首版 `.txt`） |
| `size_bytes` | `BIGINT` | 否 | — | — | 实际落盘字节数（20 MiB 内用 INT 足够，选 BIGINT 防未来扩容溢出） |
| `sha256` | `CHAR(64)` | 否 | — | — | 小写十六进制 SHA-256（完整性校验用；**不加唯一约束**） |
| `created_at` | `DATETIME(6)` | 否 | `utcnow()` | — | 上传时间（UTC 语义） |

### 3.2 约束与取舍

- **不设** `storage_ref` 唯一约束、`sha256` 全局唯一约束：同名或内容相同上传各自成独立记录，**不合并、不覆盖**。
- 属主一致性按中央草案 §4.3：`upload_file.owner_id` 由服务端派生；外键只保证「引用存在」，不保证「属主相等」，故**应用层强制**（本表仅服务端写 `owner_id = 当前用户`）。
- 只新增这一张表与迁移 0003，**不生成** task/chapter/paragraph/translation_unit/book/book_file；**不改**已验收的 0001/0002。

### 3.3 迁移

- 新迁移 `0003_create_upload_file_table.py`，`down_revision="0002"`；`downgrade()` 用 `op.drop_table("upload_file")`（MySQL 会一并清理外键约束），并在建表后 `op.create_index` 于 `owner_id`。
- 风格对齐 0001/0002（`mysql.DATETIME(fsp=6)`、`sa.String(36)` 主键、`sa.ForeignKey("user.id")`）。

---

## 4. 私有存储与一致性

### 4.1 位置与命名

- 私有目录 **`storage/uploads/`**，位于静态资源与公开下载目录之外，新增到 `.gitignore`（`storage/`）。
- `storage_ref` 为服务端生成：`f"{uuid4().hex}{ext}"`（相对路径，`ext` 首版 `.txt`）。**不拼接、不信任客户端文件名**（防路径穿越与同名冲突）。
- 存储代码集中、简单：一个 `service/upload_storage.py`（或 `core/storage.py`）封装「写临时文件 → 最终落盘 → 删除文件」，不预建插件体系、不启动对象存储/消息队列等新基础设施。

### 4.2 写入操作顺序（推荐）

```
1. 校验扩展名（小写后 == ".txt"）→ 拒绝非 .txt（422）
2. 服务端生成 storage_ref + 临时文件名 storage_ref + ".part"
3. 流式分块读取 UploadFile → 写临时文件；边写边累计 size_bytes、更新 sha256
4. size_bytes 超限 → 删除临时文件，拒绝（413）
5. 写完 fsync + 原子 rename 到最终 storage_ref
6. 构造 upload_file 记录 → repository.add + flush → db.commit
7. 若第 6 步 commit 失败 → 删除第 5 步已落盘文件（补偿），再抛 500
```

- 临时文件 `.part` 与最终文件都写在同一 `storage/uploads/` 下；`rename` 保证「半成品」不成为可见的最终文件。
- 客户端中断（上传中途断开）→ 第 3 步异常时 `finally` 删除 `.part` 临时文件。

### 4.3 失败补偿与残留文件边界（不夸大保证）

- **能保证**：写入异常/大小超限/DB 提交失败这三类，在进程内主动删除临时或已落盘文件。
- **不能保证（明确边界）**：进程在第 5 步后、第 6 步前被 kill，或 DB 提交成功后进程崩溃，可能残留孤儿文件；**数据库事务不能回滚物理文件**，这是已知边界，不声称已解决。
- 处理策略（后续或本批兜底，标注）：孤儿文件清理不阻塞上传主链路；建议后续批次做「启动或定时扫描 `.part` 超时文件」清理。本批只保证主流程的补偿与清理责任，不实现后台清理服务。

---

## 5. 上传规则与配置

### 5.1 首版规则（仅 `.txt`）

| 场景 | 处理 |
|---|---|
| 扩展名非 `.txt`（含大小写） | 拒绝（422），提示仅支持 `.txt` |
| 大小写 `.TXT` / `.Txt` | 归一化小写后接受（扩展名比较不区分大小写） |
| 缺失文件名 | 拒绝（422） |
| 文件名过长（>255 字符） | 拒绝（422） |
| 文件名含路径分隔符（`/`、`\`、`..`） | 不影响落盘（存储名服务端生成），`original_name` 仅作展示；仍可接受或按展示层转义 |
| 空文件（0 字节） | 拒绝（422） |
| 文件内容 | **保留原始字节**，不做正文去噪、翻译、SQL/XSS 黑名单清洗（正文处理属后续 FR-02） |

### 5.2 大小限制口径（推荐，待评审）

- **P10 的 20 MB 尚未确认**。推荐暂用可配置 **20 MiB = 20 × 1024 × 1024 = 20971520 字节**，单位与字节数显式写死，状态标**待评审**，不写成用户已确认。
- 必须区分三层，**不能只信任 `Content-Length`**（可伪造/缺失）：

| 层 | 字段（推荐） | 判定方式 |
|---|---|---|
| 业务文件大小限制 | `upload_max_file_bytes = 20971520` | 流式分块读取时**累计实际字节数**，超限即拒（权威判定） |
| 整个请求体限制 | 不新增字段；multipart 请求体 = 文件 + 表单 + boundary，略大于文件 | 可选：早期用 `Content-Length` 粗判加速拒绝，但**不作为最终依据** |
| multipart 解析阶段 | 依赖 Starlette `UploadFile`（`SpooledTemporaryFile`）默认行为 | 大文件自动落临时磁盘，不整读内存 |

### 5.3 现有死配置追踪与推荐口径

实测追踪（本轮只读核实）：

| 现有字段 | 定义位置 | 实际调用 | 结论 |
|---|---|---|---|
| `max_request_size` | `config_unified.py` Base=10 MiB / Dev=50 MiB | 仅 `config/manage.py:112` 展示 | **死配置**，无上传逻辑读取 |
| `max_file_size` | Base=50 MiB / Dev=100 MiB | 同上 | **死配置** |
| `upload_dir` / `quarantine_dir` | Base/Dev/Testing 各自定义 | 仅 manage 展示 | **死配置** |
| `allowed_file_extensions` / `allowed_mime_types` | Base 含多种教学格式 | 仅定义 + `field_validator` 列表，无读取 | **死配置** |

- 推荐：**新增上传模块唯一有效口径**（挂在 `BaseConfig`，`DevelopmentConfig` 按需覆盖），不改上述未被读取的字段、也不复用它作为上传限制依据：
  - `upload_max_file_bytes: int = 20971520`（20 MiB，待评审）
  - `upload_allowed_extensions: list[str] = [".txt"]`（首版）
  - `upload_storage_dir: str = "storage/uploads"`（私有目录，Git 忽略）
- 避免「只改 `max_file_size` 这个没人读的字段」这种假生效；上传模块只读上述新字段。

---

## 6. Service / Repository 分层

沿用已验收模式（`AuthService` 控制事务、`Repository` 只做单条数据访问）：

- `models/upload_file.py`：`UploadFile` 模型（字段见 §3）。
- `repository/upload_file_repository.py`：`create()`（add+flush 不 commit）、`get_owned(id, owner_id)`（`WHERE id=? AND owner_id=?`，不存在/他人返回 None）。
- `service/upload_service.py`：编排「校验 → 流式落盘 → 计算 sha256/size → 入库 → commit → 失败补偿删除文件」；事务边界在 Service（`try/except` 内 commit，失败 rollback + 删文件）。
- `service/upload_storage.py`：纯存储操作（写临时、rename、删除），不碰数据库、不 import Service。
- `schemas/upload.py`：`UploadResponse`（`{file_id, original_name, ext, size_bytes, created_at}`）。
- `api/v1/uploads.py`：路由（`POST /uploads`、`GET /uploads/{file_id}`），注册进 `api/v1/__init__.py`。
- `service/dependencies.py`：追加 `get_upload_service`。

---

## 7. 待评审点与相对中央草案的新增决定

**待评审（未确认，不写成用户/老师已确认）**：
- P10 上传大小上限：推荐可配置 20 MiB（20971520 字节），待确认。
- 首版是否需要在创建任务前做「TXT 可读性浅探针」（中央草案标注【待决】）：本批上传阶段**不做**，只在扩展名/大小/空文件层面校验，正文可读性留任务处理阶段。

**相对中央草案的本批新增决定（我方建议）**：
- `GET /api/v1/uploads/{file_id}` 元数据读取接口为本批拟新增实现契约（§2.2，不冒充草案已有）。
- 上传专用配置口径三个字段（§5.3），与教师模板遗留的 `max_file_size` 等死字段切割。
- `size_bytes` 用 `BIGINT`、`sha256` 不加唯一约束、`original_name` 仅展示（§3）。

---

## 8. 边界（本轮）

- 本轮仅产出本文件与 `tasks/upload-foundation-todo.md`，**不运行迁移、不修改运行时代码/依赖/私有配置/数据库，不改前端与中央资料仓库，不停止现有服务**。
- 不扩展成整书处理系统；不修改已验收的账号架构（鉴权、Cookie、会话撤销、AUTH_ENABLED 行为不变）。
- 上传成功仅代表「文件已保存 + 元数据入库」，**不等于**创建任务、翻译完成或整书业务就绪。
