# QED-Tracker API 设计文档（8901）

设计状态：Accepted
确认状态：暂定
实现状态：Implemented
最后更新：2026-09-01
关联代码：`src/qed_tracker/api/main.py`、`src/qed_tracker/api/tasks.py`
关联测试：`tests/test_api.py`、`tests/test_knowledge_api.py`、`tests/test_knowledge_import.py`、`tests/test_prompt_lab_api.py`、`tests/test_book_fetch.py`
关联 ADR：[ADR 0001](../adr/0001-tracker-service-architecture.md)

> **确认状态：暂定**——本版按 `src/qed_tracker/api/main.py` 代码现状整理（46 条路由全量，
> 分组口径对齐 [API 设计 Draft](../plans/2026-08-api-design.md)），尚未走正式稿五要素
> （接口/简介/输入/输出/范例）评审；正式稿由 QED-044 收口。DB 未配置时，五层端点按契约
> 统一 409「数据库未配置」（下文各端点不再重复标注）。

## 概述

QED-Tracker 通过 FastAPI 提供 HTTP 服务（默认端口 8901），前缀 `/api/v1`。端点按业务域分八组：

| 组 | 说明 | 端点数 |
| --- | --- | --- |
| ① 生命周期与健康 | 服务启停检测 | 1 |
| ② 领域与课程管理 | 共享表 CRUD + 手动领域导入（双轨[手动]） | 10 |
| ③ 教程状态机 | 查询与状态迁移（draft→confirmed→completed） | 6 |
| ④ 书籍生命周期与渠道 | 候选→下载→验收全生命周期 + 渠道留痕 + 自动取书 | 15 |
| ⑤ 任务管理 | 后台任务提交与轮询（唯一类型 `book_download`） | 3 |
| ⑥ LLM 候选搜索 | 教材/论文候选搜索 | 2 |
| ⑦ 目录 | 冻结目录查询 | 2 |
| ⑧ 探索评估与采纳 | 探索 dry-run（双轨[自动]）+ 课程知识采纳 + 探索审阅与重探（REQ-067-B12） | 7 |

只读查询同步返回；写操作提交后台任务（并发上限 2，`meta/tasks/` 落盘）或执行轻量状态迁移（同步）。

## ① 生命周期与健康

### `GET /api/v1/health`

健康检查端点。

**返回：**
```json
{"status": "ok"}
```

## ② 领域与课程管理

### `GET /api/v1/courses`

课程体系列表（qed_domain/qed_course 共享表，按领域分组全量，courses 按 sort_order 有序，无加工直接透出）。

**返回：** `CourseDomain[]` — 每个领域含
`domain_id / name / description / level / classic_tracks / exploration_stage / path_results / stages`
与 `courses[]`（每门：`course_id / name / aliases / track / stage / prerequisites / related_targets / description / exploration_stage`；审计列不透出）。

### `GET /api/v1/courses/{domain_id}`

单个学科课程体系详情（字段同上单元素）。

**路径参数：** `domain_id` — 学科标识（如 `math`）。

**错误：** 404 未知学科课程体系。

### `GET /api/v1/domains`

领域列表（扁平视图：domain_id/name/description/stages/level/scope/classic_tracks/path_results/exploration_stage）。

### `POST /api/v1/domains`

创建领域（201；`domain_id` 缺省服务端生成——规范名 slug 直用，否则 `d_<md5[:10]>`）。

**请求体：** `{name 必填, domain_id?, description?, stages?, level?, scope?, classic_tracks?}`
（显式 `domain_id` 须匹配 slug 规则 `^[a-z0-9][a-z0-9_-]{1,62}$`）。

**错误：** 409 DOMAIN_NAME_CONFLICT（name 或 domain_id 已存在）、422 INVALID_PARAMS。

### `PATCH /api/v1/domains/{domain_id}`

更新领域。可改字段：`description / stages / level / scope / classic_tracks / path_results / exploration_stage`
（`name`/`domain_id` 不可变）。空 body = no-op。

**错误：** 404 DOMAIN_NOT_FOUND。

### `DELETE /api/v1/domains/{domain_id}`

删除领域。**守卫：** 有课程 → 409 DOMAIN_NOT_EMPTY。

**错误：** 404 DOMAIN_NOT_FOUND。

### `POST /api/v1/domains/{domain_id}/courses`

创建课程（201；`course_id` 缺省服务端生成 `c_<md5[:10]>`，显式指定须匹配 slug 规则）。

**请求体：** `{name 必填, course_id?, stage?, sort_order?, description?, aliases?, track?, prerequisites?}`。

**错误：** 404 DOMAIN_NOT_FOUND、409 COURSE_ALREADY_EXISTS、422 INVALID_PARAMS。

### `PATCH /api/v1/courses/{course_id}`

更新课程。可改字段：`stage / sort_order / description / aliases / track / prerequisites`
（`name`/`course_id` 不可变）。

**错误：** 404 COURSE_NOT_FOUND。

### `DELETE /api/v1/courses/{course_id}`

删除课程。**守卫：** 有教程 → 409 COURSE_HAS_KNOWLEDGE。

**错误：** 404 COURSE_NOT_FOUND。

### `POST /api/v1/domains/import`【手动导入】

手动领域 JSON 导入（QED-050，2026-08-29）：校验 manual@v1 契约 → 写 qed_domain + qed_course
（幂等 upsert）。body：`{"domain": {...}}`（内联）或 `{"file_path": "..."}`（本机可读文件）。
domain.exploration_stage=已完成（人工探索定稿）；courses 保持既有 stage（默认未开始）。

**请求体：**
```json
{"domain": {"domain": "math-advanced", "name": "数学（高等数学）", "classic_tracks": [{"name": "分析学", "summary": "...", "kind": "main"}], "stages": ["基础", "主干", "分支", "前沿"], "courses": [{"slug": "01_math_analysis", "name": "数学分析", "track": "分析学", "stage": "基础", "summary": "..."}]}}
```

**返回：** `{"domain_id": "math-advanced", "courses_created": N, "courses_updated": N, "exploration_stage": "已完成"}`

**错误：** 400 INVALID_PARAMS（校验失败/文件不可读/JSON 解析失败）、422 缺 domain/file_path。

**契约：** `src/qed_tracker/application/knowledge_import.py`（manual@v1 校验器，守护测试
tests/test_knowledge_import.py）。

## ③ 教程状态机

### `GET /api/v1/knowledge`

教程列表（默认过滤 rejected/superseded/failed 彻底隐藏行）。

**查询参数：**
- `course_id`（可选）— 按课程筛选
- `status`（可选）— 按状态筛选

**返回：** `KnowledgeRow[]`。

### `GET /api/v1/knowledge/{knowledge_id}`

教程详情（含关联书籍列表 `books[]`）。

**错误：** 404 教程不存在。

### `POST /api/v1/knowledge/{knowledge_id}/confirm`

确认教程（draft → confirmed）。可附带 textbook_ref、exercise_ref、简介。

**请求体（可选字段）：**
```json
{
  "textbook_ref": {"title": "...", "version": "...", "authors": ["..."]},
  "exercise_ref": {"title": "..."},
  "textbook_intro": "...",
  "exercise_intro": "..."
}
```

**错误：** 404 不存在、409 非法状态迁移。

### `POST /api/v1/knowledge/{knowledge_id}/complete`

完成教程（confirmed → completed；所辖书籍全部 verified 聚合触发亦可）。

**错误：** 404 不存在、409 非法状态迁移。

### `POST /api/v1/knowledge/{knowledge_id}/reject`

拒绝教程（需提供原因）。

**请求体：**
```json
{"reason": "不符合课程要求"}
```

**错误：** 404 不存在、409 非法状态迁移、422 缺少原因。

### `POST /api/v1/knowledge/{knowledge_id}/supersede`

标记教程过时（需提供原因）。

**请求体：**
```json
{"reason": "已有更新版本"}
```

**错误：** 404 不存在、409 非法状态迁移、422 缺少原因。

## ④ 书籍生命周期与渠道

### 书籍创建与渠道

#### `POST /api/v1/books`

新建书籍候选（candidate 态）。

**请求体（必填：knowledge_id + title）：**
```json
{
  "knowledge_id": "math-01-knowledge-001",
  "title": "数学分析原理",
  "kind": "textbook",
  "roles": ["main"],
  "part": "",
  "display_title": "教程1：数学分析原理（Rudin）",
  "authors": ["Walter Rudin"],
  "language": "en",
  "version": "v3",
  "source": "internet_archive",
  "original_url": "https://..."
}
```

**错误：** 422 缺少必填字段、404 knowledge_id 不存在。

#### `GET /api/v1/books/{book_id}/sources`

书籍的渠道列表（含失败留痕，详情消费方自行过滤 ok=1）。

**错误：** 404 书籍不存在。

#### `POST /api/v1/books/{book_id}/sources`

添加渠道记录。

**请求体：**
```json
{
  "channel": "internet_archive",
  "provider_id": "ia-12345",
  "page_url": "https://...",
  "download_url": "https://...",
  "file_keywords": "filename.pdf",
  "ok": true,
  "note": "可用"
}
```

### 登记与导入（双轨[手动]）

#### `POST /api/v1/books/{book_id}/register`

人工下载登记（candidate → downloaded 直转）。relative_path 必须存在且为 PDF。

**请求体：**
```json
{"relative_path": "raw/books/math-qe/01/textbook_rudin.pdf"}
```

**错误：** 400 路径不在数据根内/PDF 校验失败、404 文件/书籍不存在、422 缺少路径、409 非法状态迁移。

#### `POST /api/v1/books/{book_id}/import`

手动下载导入（QED-050，2026-08-29）：本地 PDF（可在数据根外）→ PDF 校验 → 拷入数据根 →
登记 downloaded（candidate/decided → downloaded 直转）+ 渠道留痕 `channel=local_import`。

**请求体：**
```json
{"file_path": "C:/downloads/textbook.pdf", "target_path": "raw/math-advanced/01_math_analysis/斯图尔特微积分.pdf"}
```

- `target_path` 为期望落盘相对路径（基础名不含 sha，落盘自动补 `_<sha8>`）；缺省按
  `raw/<domain>/<course_id>/<safe_name>_<sha8>.pdf` 规则推导；文件必须 resolve 在数据根内；
- 文件在数据根外 → 经 tmp 暂存区原子落盘；数据根内且为目标位置 → 原地登记（不移动）；
- 同 sha256 已有书籍 → 复用既有行（complete_download 语义），不重复落文件。

**错误：** 400 target_path 越界/非 PDF/拷贝失败、404 文件/书籍不存在、422 缺 file_path、409 非法状态迁移。

### 状态迁移（轻量，同步）

#### `POST /api/v1/books/{book_id}/decide`

决定下载（candidate → decided）。

#### `POST /api/v1/books/{book_id}/start`

开始下载（decided → downloading）。

#### `POST /api/v1/books/{book_id}/fail`

标记下载失败（downloading → failed）。

#### `POST /api/v1/books/{book_id}/retry`

重试下载（failed → downloading）。

#### `POST /api/v1/books/{book_id}/complete`

完成下载（downloading → downloaded）。需提供 sha256 与 relative_path。

**请求体：**
```json
{
  "sha256": "64位十六进制",
  "relative_path": "raw/books/math-qe/01/file.pdf",
  "page_count": 300,
  "absolute_path": "/full/path",
  "file_name": "textbook_abc12345.pdf"
}
```

**错误：** 422 sha256 格式错误或缺字段、404 不存在、409 非法状态迁移。

#### `POST /api/v1/books/{book_id}/verify`

验证书籍（downloaded → verified）。

#### `POST /api/v1/books/{book_id}/reject`

拒绝书籍（需提供原因）。

**请求体：**
```json
{"reason": "文件损坏", "note": ""}
```

#### `POST /api/v1/books/{book_id}/supersede`

标记书籍过时（需提供原因）。

**请求体：**
```json
{"reason": "已有更好版本"}
```

#### `POST /api/v1/books/{book_id}/cancel`

取消复位（downloading → decided，方案 A 2026-08-28）。仅 downloading 可取消：失联下载/
进程重启遗留的书籍回到待执行；其余状态 409（candidate 用 decide，failed 用 retry）。

**请求体（可选）：** `{"note": "失联复位", "by": "web"}`

### 自动取书（双轨[自动]）

#### `POST /api/v1/books/{book_id}/fetch`

自动取书（方案 A 2026-08-28）：提交 `book_download` 后台任务（202 返回 `{task_id, book_id}`）。

执行链：状态校验（仅 candidate/decided/failed，否则 409；candidate 自动 decide）→ start
（downloading）→ 以书籍 title+authors 构造检索词搜索（limit=8）→ 按序逐候选下载 →
成功：`add_source(ok=true)` + `complete_download`（→ downloaded）；单候选失败/超时留痕
后换下一候选；全部失败：书籍 → failed，任务 error 附逐候选摘要与人工下载指引
（metadata_only 候选链接清单）。

超时语义：每候选总预算 `QED_FETCH_ATTEMPT_TIMEOUT`（默认 600s），预算内无响应/未完成即
切换下一候选；每次尝试的 staging 文件名带唯一 tag，孤儿线程不污染后续候选。

## ⑤ 任务管理

### `GET /api/v1/tasks`

任务列表（全部）。

**返回：** `TaskRecord[]` — 含 task_id/task_type/status/result 等。

### `GET /api/v1/tasks/{task_id}`

任务详情。

**错误：** 404 任务不存在。

### `POST /api/v1/tasks/{task_type}`

提交后台任务（返回 202 Accepted）。

**路径参数：** `task_type` — 当前唯一注册类型 `book_download`（请求体 `{"book_id": "..."}`）。

**返回：** `{"task_id": "..."}`

**错误：** 404 未知任务类型。

## ⑥ LLM 候选搜索

### `GET /api/v1/books/search`

教材候选搜索（多来源并行，返回候选列表）。

**查询参数：**
- `q`（必填）— 搜索关键词
- `limit`（可选，默认10，范围1-50）— 最大返回数
- `source`（可选）— 按来源过滤

**返回：** `Candidate[]` — 含 title/authors/provider/availability/links 等。

### `GET /api/v1/papers/search`

论文候选搜索（arXiv；百炼评分走 papers 建议链）。

**查询参数：**
- `q`（可选）— 关键词
- `category`（可选）— arXiv 分类
- `author`（可选）— 作者
- `limit`（可选，默认10，范围1-50）

**返回：** `Candidate[]`。

## ⑦ 目录

### `GET /api/v1/catalogs`

已注册目录列表。

**返回：** `[{"id": "math-qe"}]`。

### `GET /api/v1/catalogs/{catalog_id}`

目录详情（含全部目标）。

**错误：** 404 目录不存在。

## ⑧ 探索评估与采纳

### 探索 dry-run（双轨[自动]，评估模式）

#### `POST /api/v1/prompt-explores/dry-run`

领域知识探索**评估模式**（同步执行，非 202）：不入任务队列；不写任何表，唯一痕迹是
`qed_llm_calls` 的 LLM 日志（模板 domain-explore/`domain@v3` → `courses@v6` → `path@v5`）。

**body：** `{domain_name 必填（非空且 ≤100 字符）, scope_hint?（默认 DEFAULT_SCOPE 本科-硕士）, mode? direct/text/doc 默认 direct, ref_text?, ref_doc_path?, confirm_name_override?}`

**返回：**
```json
{"dry_run": true, "confirmation_required": false, "report": {"domain": {}, "directions": [], "courses": [], "path": {"graph_td": "..."}}, "calls": [{"step": "domain", "template_id": "domain-explore/domain@v3", "duration_ms": 0}]}
```

**名称确认分支：** `{"dry_run": true, "confirmation_required": true, "name_check": {...}}`
（P12 阶段一：规范名待人工确认，确认后以 `confirm_name_override` 重新发起）。

**错误：** 400 INVALID_PARAMS（参数/doc 文件不可读/管线 INVALID_PARAMS）→ 409 LLM_UNAVAILABLE
（未配置 API_KEY 或管线初始化失败）→ 502 LLM_UNAVAILABLE/BUDGET_EXHAUSTED 等管线错误码透传。

#### `POST /api/v1/courses/{course_id}/prompt-explores/dry-run`

课程教材探索 dry-run（QED-047，A1）：同步单步 tutorials@v1，不写任何表，与领域 dry-run 对称
（校验序 mode→key→404→管线）。

**body：** `{mode? direct/text/doc, ref_text?, ref_doc_path?}`

**返回：** `{"dry_run": true, "report": {...推荐套列表...}, "calls": [...]}`

**错误：** 400 INVALID_PARAMS、404 COURSE_NOT_FOUND、409 LLM_UNAVAILABLE、502 管线错误透传。

### 课程知识采纳

#### `POST /api/v1/courses/{course_id}/knowledge`

采纳推荐建教程（QED-047 A2，201）：每套建 draft qt_knowledge 行并预填六字段；
幂等/套号冲突语义见仓储（adopt_tutorials）。`source` 取 `explore`（默认，自动探索采纳）或
`manual`（人工录入），仅作来源标记。

**请求体：**
```json
{"source": "explore", "tutorials": [{"set_no": "1", "set_name": "教程1", "textbook": {"title": "...", "roles": ["textbook"]}, "exercise": null}]}
```

**校验：** 1~4 套；每套 set_no（非空 ≤4 字符）/set_name（非空 ≤200 字符）/textbook.title 非空
且 roles 含 `textbook`；exercise 可为 null（同源）或含 title 且 roles 含 `exercises`。

**错误：** 404 COURSE_NOT_FOUND、409 SET_NO_CONFLICT、422 INVALID_PARAMS。

### 探索审阅与重探（REQ-067-B12，2026-09-01 已实现）

探索完成后写「待确认」（explore_pending 载荷），由用户在前端审阅后触发采纳或重探。
设计见 [REQ-067-B10/B12 探索阶段设计](../history/baselines/2026-08-31-req067-b10-b12-exploration-stage.md)，
契约登记见[共享表设计](shared-tables.md)状态机节。

#### `POST /api/v1/domains/{domain_id}/apply-results`

**接口：** POST `/api/v1/domains/{domain_id}/apply-results`，路径参数 `domain_id`。
**简介：** 确认领域探索结果（待确认 → 已完成）：选择要保留的课程，删除其余。
**输入：** body `{selected_courses: string[]}`（必填，选中的课程 ID 列表）。
**输出：** 200 `{domain_id, courses_kept}`；404 领域不存在；409 当前状态非「待确认」；422 selected_courses 非数组。
**范例：**
```json
// 请求
POST /api/v1/domains/math/apply-results
{"selected_courses": ["01_math_analysis", "02_algebra"]}

// 响应
{"domain_id": "math", "courses_kept": 2}
```

#### `POST /api/v1/domains/{domain_id}/re-explore`

**接口：** POST `/api/v1/domains/{domain_id}/re-explore`，路径参数 `domain_id`。
**简介：** 重置领域探索（待确认 → 探索中）：清除 explore_pending，提交后台重新探索任务。
**输入：** body `{description?: string, mode?: string}`（可选；description 覆盖领域描述，mode 默认 "web"）。
**输出：** 202 `{task_id}`；404 领域不存在；409 当前状态非「待确认」。
**范例：**
```json
// 请求
POST /api/v1/domains/math/re-explore
{"description": "数学（本科-博士）", "mode": "web"}

// 响应
{"task_id": "task_math_reexplore_001"}
```

#### `POST /api/v1/courses/{course_id}/apply-results`

**接口：** POST `/api/v1/courses/{course_id}/apply-results`，路径参数 `course_id`。
**简介：** 确认课程探索结果（待确认 → 已完成）：选择要保留的教程，删除其余。
**输入：** body `{selected_tutorials: string[]}`（必填，选中的教程 set_no 列表）。
**输出：** 200 `{course_id, tutorials_kept}`；404 课程不存在；409 当前状态非「待确认」；422 selected_tutorials 非数组。
**范例：**
```json
// 请求
POST /api/v1/courses/01_math_analysis/apply-results
{"selected_tutorials": ["1", "2"]}

// 响应
{"course_id": "01_math_analysis", "tutorials_kept": 2}
```

#### `POST /api/v1/courses/{course_id}/re-explore`

**接口：** POST `/api/v1/courses/{course_id}/re-explore`，路径参数 `course_id`。
**简介：** 重置课程探索（待确认 → 探索中）：清除 explore_pending，提交后台重新探索任务。
**输入：** body `{description?: string, mode?: string}`（可选；description 覆盖课程描述，mode 默认 "web"）。
**输出：** 202 `{task_id}`；404 课程不存在；409 当前状态非「待确认」。
**范例：**
```json
// 请求
POST /api/v1/courses/01_math_analysis/re-explore
{"mode": "web"}

// 响应
{"task_id": "task_course_reexplore_001"}
```

## 错误码

| 状态码 | 含义 |
| --- | --- |
| 200 | 成功 |
| 201 | 资源创建成功 |
| 202 | 任务已接受（后台执行） |
| 400 | 请求格式错误（INVALID_PARAMS：校验失败/文件不可读/PDF 校验失败/路径越界） |
| 404 | 资源不存在（DOMAIN_NOT_FOUND / COURSE_NOT_FOUND，及教程/书籍/文件/目录/任务的 plain-detail 404） |
| 409 | 冲突与守卫（DOMAIN_NAME_CONFLICT / COURSE_ALREADY_EXISTS / COURSE_HAS_KNOWLEDGE / DOMAIN_NOT_EMPTY / SET_NO_CONFLICT / LLM_UNAVAILABLE / 非法状态迁移 / 数据库未配置） |
| 422 | 参数校验失败（缺必填字段、格式错误） |
| 502 | 上游模型调用失败（管线错误码透传：LLM_UNAVAILABLE / BUDGET_EXHAUSTED 等） |
