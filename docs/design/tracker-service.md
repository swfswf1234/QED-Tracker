# QED-Tracker 服务接口设计（tracker-service）

设计状态：Accepted
实现状态：In Progress
最后更新：2026-08-12
需求方：QED-Engine
关联代码：src/qed_tracker/api/（FastAPI 服务与后台任务层，服务化轮已实现）、src/qed_tracker/db/ 与
src/qed_tracker/database.py（qt_resources ORM、状态机仓库、双写登记，QED-012 已实现）、
src/qed_tracker/migrations/（Alembic 迁移 0001_qt_resources）
关联测试：tests/test_api.py（服务化轮新增 API 与任务层测试）、tests/test_db_models.py、
tests/test_db_registry.py、tests/test_db_mysql_smoke.py（QED_DB_SMOKE=1 本机冒烟）、8901 真实服务冒烟测试
关联 ADR：[ADR 0001](../adr/0001-tracker-service-architecture.md)
决策记录：2026-08-05 用户裁决——人机协同闭环：LLM 评估候选落库 → 人工确认后才下载 → 下载后
预览验收；拒绝/删除必填原因，文件硬删 + DB 记录留痕；CLI 同步支持闭环。
2026-08-05 复核裁决：统一 qed 库直写（维持 2026-08-04 裁决）；独立性铁律修订登记根仓库
ADR 0003（共享 qed 库实例、qt_*/af_* 表命名空间隔离）；pending_manual 补书扫描后转
`confirmed` 回归确认链路，不引入 `registered` 状态。

## 背景

QED-Engine 按 [ADR 0002](../../../docs/adr/0002-frontend-and-port-centralization.md) 统一全局
端口段：QED-Tracker 服务端口 8901。统一 CLI 与前端需要经 HTTP 调用本项目的搜索、下载、校验、
登记与 Axiom 推送能力；长操作（大 PDF 下载、百炼推荐）不能阻塞请求，须以后台任务 + 状态轮询
暴露。跨项目契约见根仓库[服务契约](../../../docs/design/service-contracts.md)与
[dataset 目录约定](../../../docs/design/dataset-conventions.md)。

## 所需变更

### 服务（src/qed_tracker/api/，端口 8901，前缀 `/api/v1`）

已实现端点（`src/qed_tracker/api/main.py`）：

| 方法/路径 | 行为 |
| --- | --- |
| `GET /health` | 存活检查 |
| `GET /books/search?q=&source=&limit=` | 同步：教材候选搜索 |
| `GET /papers/search?q=&category=&author=&limit=` | 同步：arXiv 候选搜索 |
| `GET /resources?status=&course_id=&kind=&language=` | 同步：资源清单查询（前端展示，按状态/课程过滤；含 `review_note` 字段，QED-020） |
| `GET /resources/{id}` | 同步：资源详情（含 llm_evaluation/catalog_ref/留痕字段） |
| `GET /resources/{id}/file` | 同步：PDF 预览流（仅 downloaded/approved 可访问；供 8903 验收台 iframe 内嵌） |
| `POST /resources/{id}/register` | 同步轻写：人工下载登记（QED-021，body `{relative_path}`，数据根内 PDF 校验 + SHA-256 去重 → downloaded） |
| `POST /resources/{id}/confirm` | 同步轻写：candidate → confirmed（人工确认下载；可选 body `{note}` 写入 review_note） |
| `POST /resources/{id}/backup` | 同步轻写：candidate/pending_manual → backup（QED-017 备选，不下载，可转正/放弃；可选 `{note}`） |
| `POST /resources/{id}/approve` | 同步轻写：downloaded → approved（验收通过） |
| `POST /resources/{id}/reject` | 同步轻写：candidate 或 downloaded → rejected；body `{reason}` 必填（缺省 422）；downloaded 时同步硬删文件，DB 记录保留留痕 |
| `GET /catalogs`、`GET /catalogs/{id}` | 同步：冻结目录与目标 |
| `POST /tasks/catalog/evaluate` | 后台任务：按课程批量评估（搜索源 → LLM 评估 → 候选落库；body `{course_id?}`，缺省=全目录；缺模型密钥时降级跳过评估） |
| `POST /tasks/books/download` | 后台任务：教材/习题下载（body `{resource_id}`，仅 confirmed 可触发，否则 409） |
| `GET /tasks`、`GET /tasks/{id}` | 任务列表与状态轮询 |

规划中（未实现，属 QED-010「CLI 转 HTTP 客户端」范围，实现后同步本表）：`GET /selections`、
`GET /selections/{id}`（论文选择报告）、`POST /tasks/papers/download`、`POST /tasks/recommend`
（百炼论文推荐）、`POST /tasks/catalog/run`（目录批处理）、`POST /tasks/scan`（数据根扫描登记）、
`POST /tasks/axiom/push`（Axiom 上传，默认不解析）。

任务模型（落盘 `meta/tasks/<task-id>.json`）：`{task_id, type, status, progress, created_at,
updated_at, params, result, error}`；`result` 含 `resource_id`、`relative_path`、
`selection_id` 等，供前端"任务 → 文件"跳转。并发上限 2；同 sha256 幂等复用。CORS 允许
`http://127.0.0.1:8903` 源（8903 下载工作台直连本服务，无代理）。

### 配置（`config.py`）

- 直读根 `.env` 的 `QED_*` 变量：`QWEN_API_KEY`（百炼）、`QED_MODEL`、`QED_AXIOM_URL`
  （默认 `http://127.0.0.1:8902`）、`QED_TRACKER_PORT`（默认 8901）、`QED_PROXY`
  （代理访问，绕开 archive.org/openlibrary.org 的 DNS 污染与限流）。
- 本地 TOML 与旧 `QED_TRACKER_*` 变量（`QED_TRACKER_LLM_API_KEY`、`QED_TRACKER_SOURCES`
  等）退役；`QED_TRACKER_PORT` / `QED_TRACKER_URL` 为服务端口变量保留。无配置时内置最小
  默认值 + 启动尾注提醒。
- 根 `.env` 由统一 CLI `qed` 启动服务时注入；独立启动 `qed-tracker serve` 时自动从当前
  目录向上查找根 `.env` 并注入 `QED_*` 与供应商密钥（不覆盖已显式设置的环境变量），
  无 `.env` 时降级运行。
- 服务入口：`qed-tracker serve [--host 127.0.0.1] [--port 8901]`；启动先执行
  `upgrade_database()`，MySQL 迁移失败仅警告、服务照常启动（登记/任务明确报错）。

### 数据布局（数据根默认 `dataset/qed-tracker/`）

```text
dataset/qed-tracker/
├── raw/books/{inbox,math-qe/<course-id>}/        # 教材
├── raw/exercises/inbox/                          # 习题集（kind=exercise 独立）
├── raw/papers/<year>/                            # 论文
├── meta/{resources,selections,transfers,tasks}/  # JSON 状态
└── tmp/downloads/<task-id>.part                  # 下载临时区（原子落盘后清理）
```

文件名规则：`<slug>_<sha256前8>.pdf`（论文为 `<arxiv-id>_<sha256前8>.pdf`）。
存量数据不迁移；`.qed-tracker/` 状态目录迁移到 `meta/`。

### CLI（`cli.py`）

转 HTTP 客户端：默认等待任务完成；`--no-wait` 输出 `task_id`；`--json` 保留。独立脚本入口
`qed-tracker` 在统一 CLI `qed` 承接后退役（见根仓库计划 Phase 1/2）。

**规划中（QED-010，未实现）**：闭环命令 `catalog evaluate [--course]`、`resources
list [--status] [--course]`、`resources show <id>`、`resources confirm <id>`、`resources
reject <id> --reason <原因>`、`resources approve <id>`、`books download <id>`。当前闭环经
8901 API 或 CLI 既有直连命令（如 `catalog run --download`）完成，无前端时由 `qed` CLI / API
客户端承接。

### 配置（补充：统一数据库，2026-08-04 用户裁决）

- 直读根 `.env` 的 `QED_DB_*` 变量（`QED_DB_HOST/PORT/NAME/USER/PASSWORD`）：MySQL 8 新建
  `qed` 库，三项目共用；本服务只使用 `qt_*` 前缀表，不读写 Axiom-Flow 的 `af_*` 表。
- 无 `QED_DB_PASSWORD` 时数据库相关能力（登记/查询）降级：服务与 CLI 正常启动，登记暂缓并
  输出提醒；不因缺库缺密阻塞下载主链路。

### MySQL 资源登记索引（QED-012，新增）

资源事实源仍为 `meta/resources/<sha256>.json`（文件状态事实，schema 不变）；MySQL
`qt_resources` 为查询/展示索引，双写一致性由登记服务保证。

- 表 `qt_resources` 字段：`resource_id`（= `sha256:<digest>`，下载后回填）、`sha256`、`kind`
  （book|exercise|paper）、`title`、`authors`（JSON 数组）、`language`（zh|en）、`year`、
  `edition`、`source`（JSON：provider / page_url / download_url）、`retrieved_at`（下载时间）、
  `relative_path`、`page_count`、`status`（candidate | confirmed | downloading | downloaded |
  approved | rejected | failed | pending_manual | not_found | backup）、`llm_evaluation`（JSON：score
  0-100 / verdict / summary / model / evaluated_at，模型只写评估不写事实）、`catalog_ref`
  （JSON：catalog_id / target_id / course_id）、`confirmed_at`、`downloaded_at`、
  `approved_at`、`rejected_at`、`reject_reason`、`rejected_by`（api|cli|web）、`created_at`。
- 资源状态机（2026-08-05 用户裁决，人机协同闭环；2026-08-06 增补人工评估三态 QED-017）：

  ```text
  [catalog/evaluate 任务·按课程] 搜索源 → qwen 评估 → 候选落库
      ↓
  candidate ──confirm(确定)──→ confirmed ──download 任务──→ downloading ──成功──→ downloaded
      │  │                        │                             │失败→failed（可重新触发）
      │  │──backup(备选)──→ backup ──confirm──→ confirmed（转正下载）
      │  │                    └──reject(原因)──→ rejected（放弃备选）
      │  │
      │──reject(否定,原因)──→ rejected（候选级，无文件）
  downloaded ──预览+approve──→ approved（待 Axiom-Flow 解析）
      │
      └──预览+reject(原因)──→ rejected（文件硬删，DB 记录保留）
  ```

  - 人工评估三态（QED-017，2026-08-06 用户裁决）：**确定** = `confirm`（进入下载流程）、
    **备选** = `backup`（新状态，不下载，可后续转正或放弃）、**否定** = `reject`（原因必填）。
    评估与验收分离：下载完成后另经 `approve` 验收。中文教材候选确定优先；中文不可得时英文
    候选由人工决定确定或备选（无中文 target 的课程如 11/12/13 直接评估英文）。
  - `pending_manual`：书单目标已确认但来源不可得（如中文教材），前端展示"待人工补充"；人工
    补书 = 文件放入目标目录后执行扫描登记，状态转 `confirmed` 并回填文件信息，经确认/下载链路
    回归；也可先标记 `backup` 等待补书。
  - 非法迁移（如未 confirm 即下载、rejected 后再验收）返回 409；reject 缺 reason 返回 422。
  - rejected 资源 DB 记录永不删除；后续评估任务按 catalog_ref + title/sha256 跳过同源已拒候选
    （backup/approved/rejected 行均视为已评估，评估任务跳过不重复推荐）。
- 登记顺序：PDF 落盘 → 写资源 JSON → 写 MySQL（已实现：下载任务 progress 70 处经
  ResourceRegistry.register_downloaded 双写，同 sha256 幂等复用既有记录，主键由
  `cand_<md5>` 迁移为 `sha256:<digest>`）；任一步失败任务失败并保留可重放现场（重复
  提交同 sha256 幂等复用既有记录）。
- 数据库栈与迁移：已采用 SQLAlchemy 2.0 ORM + Alembic（`alembic.ini` + `src/qed_tracker/migrations/`，
  URL 由 QED_DB_* 构造不写死；迁移脚本须保持纯 ASCII，Windows locale 编码读取）。
  迁移应用入口 `upgrade_database()` 供服务启动与冒烟复用；「ORM 框架旧禁令」
  （`tests/test_documentation.py` LEGACY_PATTERNS 与 `tests/test_cli_architecture.py` 禁导入
  清单）随实现轮同步移除，并更新对应治理测试。

### 表结构评估结论（2026-08-06，QED-017）

人工评估三态引入时评估过表结构方案：**不需要重新设计/新增 DDL**。理由：

- 三态决策用状态机表达（`status` 字符串列：candidate/confirmed/backup/rejected），
  状态即决策，查询与前端映射简单；
- 留痕列已覆盖：`confirmed_at`（确定）、`rejected_at/reject_reason/rejected_by`（否定）、
  backup 迁移时间可查 `created_at/updated_at`；LLM 评估与人工评估天然分层
  （`llm_evaluation` 只写模型结论，人工决策走状态迁移）；
- 若后续需要「人工评估记录」审计视图（谁、何时、何种决策），再加 `assessed_at`/`assessed_by`
  列（Alembic 迁移），不影响现有数据。

### 书单与 LLM 筛选评估（QED-013，新增）

- 书单 `math-qe-v2`：以 `D:\coding\dataset\textbooks` 现有索引为蓝本（用户已筛选，覆盖 13 门
  课程），每门课程两组：**中文教材组**（优先中文版经典教材中译本）与**对应习题集组**；英文
  经典原版作补充；含字段 course_id / title / authors / language(zh|en) / kind(textbook|
  exercise) / edition / note（可选项）。
- qwen 辅助（`QED_MODEL`，复用百炼供应商既有能力）：`POST /tasks/catalog/evaluate` 按课程
  批量——对每门课程的书目做结构化补全与候选评分（是否推荐、理由）；**宁缺勿滥**——模型不确定
  的候选不收录；模型输出只生成可审阅评估（写入 `llm_evaluation`），不写资源事实、不自动下载
  （沿用论文发现的约束）。
- 人工确认下载：评估任务只产出 `candidate` 状态候选；下载必须经
  `POST /resources/{id}/confirm`（8903 前端或 CLI）确认后由 `POST /tasks/books/download`
  执行（仅 confirmed 可触发）。候选级拒绝走 `POST /resources/{id}/reject`（填原因，无文件）。
- 下载后验收：8903 验收台经 `GET /resources/{id}/file` 预览；验收通过 `approve` 转 approved
  （待 Axiom-Flow 解析），不通过 `reject` 填原因（文件硬删，DB 记录保留留痕）。
- 来源不可得的中文书登记 `status=pending_manual`；扫描补书后经确认下载链路回归。
- 人工评估三态与中文优先（QED-017）：见上文状态机增补；评估动作均经 8901 同步轻量端点
  （`confirm` / `backup` / `reject`），前端 8903 提供按课程评估视图（中文候选优先展示）。
- 来源探索（QED-018）：合适下载路径的发现与淘汰是持续目标，评估矩阵与探索流程见
  [来源探索与评估设计](source-discovery.md)；版权敏感源（libgen 类）不纳入。
- 探索更优书籍：作为候选后置任务，不阻塞基础书单（见路线图"目录与批处理"）。

## 接口/契约影响

- Axiom-Flow 地址默认改为 `http://127.0.0.1:8902`（现状 8000）。
- `QED_TRACKER_LLM_API_KEY` / `DASHSCOPE_API_KEY` 读取路径退役，改读 `QWEN_API_KEY`。
- 新增根 `.env` `QED_DB_*` 直读（qed 库，qt_* 表；跨项目契约见根仓库 service-contracts.md）。
- 资源 schema 不变（`file.relative_path` 相对数据根）；目录结构变化（`books/` → `raw/books/`）
  属内部布局，资源 JSON 记录随新路径生成；MySQL `qt_resources` 为新增查询索引（双写）。
- 资源登记新增 `status` 状态机（candidate/confirmed/downloading/downloaded/approved/rejected/
  failed/pending_manual/not_found），仅 MySQL 侧体现，JSON 事实源不受影响。

## 验证方式

1. 单元：API 端点（TestClient，mock 应用层）与客户端（httpx MockTransport）离线测试。
2. 冒烟：真实启动 8901 服务 → 创建下载任务 → 轮询 → 校验 PDF 落位
   `dataset/qed-tracker/raw/books/inbox/` 且资源登记、任务记录完整。
3. 重复下载链路：同一资源二次下载返回既有记录（sha256 幂等），不产生重复文件。
4. 双写一致性：同一资源 JSON 与 `qt_resources` 字段一致；登记失败可重放（模拟落盘后写库失败
   的用例）。
5. 书单与评估链路：`catalog evaluate`（按课程）冒烟——候选落库（candidate）→ confirm →
   下载落位 `raw/books/math-qe/<course>/` → 验收 approve/reject（留痕）；不可得中文书登记
   `pending_manual`，扫描补书后转 `confirmed` 回归确认链路。
6. 降级：无根 `.env`（含无 `QED_DB_*`）时服务与 CLI 正常启动并输出尾注提醒。

## 回执条件

- 本设计转 Accepted 且 Phase 2 实现通过 QED-Tracker 全量门禁（`pytest tests -q`、ruff、
  `tests/test_documentation.py`、8901 冒烟）。
- 根仓库 `docs/trackers/todo.md` 收到完成回执，链接本文件与 QED-Tracker 任务 ID。
