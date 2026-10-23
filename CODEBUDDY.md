# CODEBUDDY.md — 译伴后端协作约定

更新日期：2026-10-22。适用于 `yiban-api`，结合本仓 README 和本轮用户指令使用。

## 开工与依据

先核对目录、分支、工作区和远程地址，再分批读取 README、本文件及相关源码。核实本机实际安装的适用技能和 SKILL.md 后再使用，首次说明真实名称与用途，不虚构技能或阅读记录。已授权范围内的常规可逆步骤继续完成，避免重复确认。

本仓与 `yiban-web`、`yiban-admin`、`bilingual-ebook-generator` 同级存放。中央资料在 `../bilingual-ebook-generator/`：需求文档 §3.5/3.6、数据库逻辑模型、任务状态机及任务/书库两份接口契约草案。按本次相关章节读取，不每轮扫描全部历史。

老师要求、用户决定和实现状态分别记录。当前采用 Gitee 主仓与 GitHub 镜像，校内 GitLab 留到最终阶段；中央资料的早期阶段与托管文字不覆盖本轮明确指令，不因旧“不写业务代码”永久阻止后续已授权实现。

## 起步与实现范围

本次来源为教师 Skills 压缩包中的 `sql-to-fastapi-restfulapi-scaffold/resources/templates/project_structure/`。这是基于模板适配的起步工程，来源、原文差异和散列在 docs。当前已有基础 HTTP、日志、OpenAPI 与健康检查，并落地账号数据库基础（`user` 模型 + Alembic 迁移，数据库默认关闭）与可显式启用的用户鉴权（`AUTH_ENABLED`，默认关闭）；管理员鉴权与其余业务链路仍未接入。

Python 3.12、uv、FastAPI、Pydantic 2 与 SQLAlchemy 的框架基础沿用起步项目。先按 uv.lock 安装，不因教师队列等模板素材存在而预先定案数据库、异步机制或生产架构。业务按用户明确批次推进，不将本次初始化边界当成永久禁令。

默认生命周期不连接数据库（`DATABASE_ENABLED=false`）、Redis或启动内存队列；启用数据库须显式配置译伴 `DATABASE_URL`，教师示例库（`api_security_*` 前缀）按库名结构化拒绝（`make_url` 解析，非整 URL 子串判断）；表结构由 Alembic 唯一管理、lifespan 不执行 create_all 或自动迁移；MySQL 8.4 默认 caching_sha2_password 认证，依赖含 `cryptography`。数据库集成测试只读 `TEST_DATABASE_URL` 并校验目标库名必须为 `yiban_api_test`，非译伴专用测试库拒绝执行迁移/写入。健康为 bootstrap 不代表业务或数据就绪。权限占位依赖默认拒绝；不得将其改为无条件通过、接受固定测试 Token 或使用 localStorage 标记充当真实权限。注册接口 `POST /api/v1/auth/register` 服务端固定 `role='user'`（忽略请求体 role）；密码 ≥8 字符且 UTF-8 ≤72 字节（超限拒绝不截断），bcrypt 哈希经 `asyncio.to_thread` 落库，重复 email 返回 409，响应绝不返回 `password_hash`。写接口 CSRF/Origin：`Origin` 精确匹配 `trusted_origins` 且携带 `X-Yiban-Request: 1`，缺失/不可信均 403（OPTIONS 预检由 CORS 中间件放行）；`cors_origins` 为显式白名单（凭据型 CORS 不得 `*`）。登录/me/退出：JWT 仅 HS256（`sub`/`jti`/`aud=user`/`exp`，不含角色快照），签发与验签统一用 `effective_jwt_secret_key` 并在启动阶段校验（拒绝空值/短密钥 <32 字节/教学默认值/`${...}` 占位符，不回退弱密钥）；`AUTH_ENABLED` 默认关闭（关闭时 login/me/logout 均返回 503，不签发/接受会话，检查先于数据库访问）；启用要求数据库已启用且密钥校验通过。每次鉴权验签后必须查库验证 `user_session` 存在且未撤销未过期、`jti`/`sub`/`aud=user`/`session_type=user` 一致、用户存在，身份与角色以数据库记录为准；退出置 `revoked_at` 立即失效。用户 Cookie `yiban_user_session` 必须 HttpOnly + SameSite=Lax + Secure（生产，开发 localhost 豁免）；`require_admin` 已真实实现（管理员会话 Cookie `yiban_admin_session` + `aud=admin` + `session_type=admin` + 查库 `role='admin'`，角色降级后 403）；`get_current_active_user`/`require_teacher`/`require_student` 等未接入权限入口继续默认拒绝。管理员端 `/admin/auth/*` 登录/me/退出复用上述鉴权，双端独立 Cookie/jti/会话、退出一端不撤销另一端、跨端 Token 错配 401；管理员登录先验凭据再查 role（凭据错 401、角色非 admin 403）；管理员创建仅受控 CLI `scripts/create_admin.py`（getpass 隐藏输入、复用注册校验、教师示例库拒绝、重复邮箱不覆盖）。

## 分层与数据规则

- API 只调用 Service，Schema 校验请求；数据访问在 Repository，业务流程与跨表事务由 Service 控制。列表和过滤等按实际设计组织，避免逐页/逐表复制。
- 尚未授权业务表批量生成；不把所有表都暴露通用 CRUD，不生成允许普通用户任意改 task.status 或 owner_id 的接口。
- 完成流程的 book → book_file → task.done 须在明确事务中一致写入；不照搬模板逐条 Repository commit。物理 EPUB 文件和数据库记录的一致性另行设计，唯一索引只防重复记录。
- 属主由服务端派生并校验，保持 upload_file → task → book 属主一致。普通用户请求不能指定他人 owner_id；管理员只读任务元数据不等于读取私有内容，内容访问另按上下文与审计设计。
- 新任务 service/style 必填，model 按服务能力可空，配置随任务快照。服务密钥不入任务快照或前端配置。
- 结构为 task → chapter → paragraph → translation_unit，保留各层序号、原段落及对齐。目录/页眉页脚识别按受控证据处理，不凭重复行或 The end 固定词删除正文。
- status 与 stage 分开；done_units 包含成功与失败单元，失败单元保留原文。total_units=0 不计算百分比；切分完仍为 0 则失败。翻译 100% 不等于完成排版、EPUB 和入库。
- failed task 为不可变失败终态，手动重试新建 task；可空且唯一 retry_of_task_id 让重复请求返回已有直接子 task 及实际状态，子任务再失败继续链式重试。默认整书重跑，不承诺断点续做。
- 条件状态更新、派生计数、迟到回调与幂等写入需共同保证，不认为唯一键自动解决重复计数或终态回退。
- 数据库物理模型单独评审，按课程规范与最终设计落实；不把脚手架的物理外键、主键或状态 PATCH 默认策略直接当成译伴结论。

## 接口与交付

首个真实里程碑为 TXT、英语到中文、单家真实翻译服务、后台任务与进度、对照预览、EPUB、个人书库与重新下载；管理员独立入口和任务/失败只读查看。EPUB/PDF 输入、其他语言、PDF 导出、完整管理、PWA、书签、阅读位置和第三方登录按后续安排，不取消最终目标。

任务与书籍按稳定 ID 精确读取，同名不同配置各自成书。无效/他人 bookId 对外统一提示，不泄露存在性；长书按章节/段落分页，下载须 task.done 且文件实际可读，不暴露 storage_ref。已有接口草案不是已上线服务，接入时统一错误、字段与会话契约。

Gitee origin 为 PR 合并入口，GitHub github 镜像相同提交。master 稳定、develop 集成，从 develop 建 feature/fix/docs 分支。单人自查，不虚构第二审批人或 CI；保护设置以平台实际配置为准。保留根提交，不强推、不覆盖未提交工作，关联 PingCode 实际任务编号。

验证使用 `uv sync --locked` 与 `uv run --locked pytest -q`。测试覆盖基础生命周期、默认拒绝与真实 Uvicorn HTTP；不表述为真实鉴权或业务验收。仅改 Markdown 时检查差异和来源即可，不重复构建。依赖、配置或启动改动运行对应检查；继承的未验收模块按功能逐步验证。

汇报修改文件、行为、实际检查、限制，以及提交、推送、合并、部署的真实状态。起步附带的容器/运维教学素材已裁剪移除；未授权时不启动新服务、连接现有项目数据库或执行初始化 SQL。
