# 8901 API 接口文档

设计状态：Accepted
实现状态：Implemented
最后更新：2026-08-24
关联代码：`src/qed_tracker/api/main.py`、`src/qed_tracker/api/tasks.py`
关联测试：`tests/test_api.py`、`tests/test_knowledge_api.py`
关联 ADR：[ADR 0001](../adr/0001-tracker-service-architecture.md)

## 概述

QED-Tracker 通过 FastAPI 提供 HTTP 服务（默认端口 8901），前缀 `/api/v1`。端点按业务语义分为四类：

| 类别 | 说明 | 端点数 |
| --- | --- | --- |
| ① 服务生命周期与健康 | 服务启停检测 | 1 |
| ② 数据查询 | 只读查询课程体系、知识行、书行、渠道、目录、资源 | 7 |
| ③ 资源生命周期操作 | 状态迁移、创建、登记、任务提交 | 16 |
| ④ LLM 检索课程教程·选书业务 | 教材/论文候选搜索 | 2 |
| ⑤ 探索域 | 课程层/新建领域层 LLM 探索 + 手工维护 + prompt 优化评估 | 14 |

只读查询同步返回；写操作提交后台任务（并发上限 2）或执行轻量状态迁移（同步）。

## ① 服务生命周期与健康

### `GET /api/v1/health`

健康检查端点。

**返回：**
```json
{"status": "ok"}
```

## ② 数据查询

### `GET /api/v1/courses`

课程体系列表（qed_domain/qed_course 共享表，按领域分组全量，sort_order 有序）。

**返回：** `CourseDomain[]` — 每个领域含 domain_id/name/description/stages/courses 数组。

### `GET /api/v1/courses/{domain_id}`

单个学科课程体系详情。

**路径参数：** `domain_id` — 学科标识（如 `math`）。

**错误：** 404 未知学科课程体系。

### `GET /api/v1/knowledge`

知识行列表（默认过滤 rejected/superseded/failed）。

**查询参数：**
- `course_id`（可选）— 按课程筛选
- `status`（可选）— 按状态筛选

**返回：** `KnowledgeRow[]`。

### `GET /api/v1/knowledge/{knowledge_id}`

知识行详情（含关联书行列表）。

**路径参数：** `knowledge_id` — 知识行 ID。

**错误：** 404 知识行不存在。

### `GET /api/v1/books/{book_id}/sources`

书行的渠道列表。

**路径参数：** `book_id` — 书行 ID。

**错误：** 404 书行不存在。

### `GET /api/v1/catalogs`

已注册目录列表。

**返回：** `[{"id": "math-qe"}]`。

### `GET /api/v1/catalogs/{catalog_id}`

目录详情（含全部目标）。

**路径参数：** `catalog_id` — 目录标识。

**错误：** 404 目录不存在。

## ③ 资源生命周期操作

### 知识行状态迁移

#### `POST /api/v1/knowledge/{knowledge_id}/confirm`

确认知识行（candidate → confirmed）。可附带 textbook_ref、exercise_ref、简介。

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

#### `POST /api/v1/knowledge/{knowledge_id}/complete`

完成知识行（confirmed → completed）。

**错误：** 404 不存在、409 非法状态迁移。

#### `POST /api/v1/knowledge/{knowledge_id}/reject`

拒绝知识行（需提供原因）。

**请求体：**
```json
{"reason": "不符合课程要求"}
```

**错误：** 404 不存在、409 非法状态迁移、422 缺少原因。

#### `POST /api/v1/knowledge/{knowledge_id}/supersede`

标记知识行过时（需提供原因）。

**请求体：**
```json
{"reason": "已有更新版本"}
```

**错误：** 404 不存在、409 非法状态迁移、422 缺少原因。

### 书行操作

#### `POST /api/v1/books`

新建书行候选（candidate 态）。

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

#### `POST /api/v1/books/{book_id}/register`

人工下载登记（candidate → downloaded 直转）。relative_path 必须存在且为 PDF。

**请求体：**
```json
{"relative_path": "raw/books/math-qe/01/textbook_rudin.pdf"}
```

**错误：** 400 路径不在数据根内、404 文件/书行不存在、422 缺少路径、409 非法状态迁移。

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

**错误：** 422 sha256 格式错误或缺字段、409 非法状态迁移。

#### `POST /api/v1/books/{book_id}/verify`

验证书行（downloaded → verified）。

#### `POST /api/v1/books/{book_id}/reject`

拒绝书行（需提供原因）。

**请求体：**
```json
{"reason": "文件损坏", "note": ""}
```

#### `POST /api/v1/books/{book_id}/supersede`

标记书行过时（需提供原因）。

**请求体：**
```json
{"reason": "已有更好版本"}
```

### 任务管理

#### `GET /api/v1/tasks`

任务列表（全部）。

**返回：** `TaskRecord[]` — 含 task_id/task_type/status/result 等。

#### `GET /api/v1/tasks/{task_id}`

任务详情。

**路径参数：** `task_id` — 任务 ID。

**错误：** 404 任务不存在。

#### `POST /api/v1/tasks/{task_type}`

提交后台任务（返回 202 Accepted）。

**路径参数：** `task_type` — 任务类型（如 `books_search`、`papers_search`）。

**请求体：** 任务参数（类型相关）。

**返回：** `{"task_id": "..."}`

**错误：** 404 未知任务类型。

## ④ LLM 检索课程教程·选书业务

### `GET /api/v1/books/search`

教材候选搜索（多来源并行，返回候选列表）。

**查询参数：**
- `q`（必填）— 搜索关键词
- `limit`（可选，默认10，范围1-50）— 最大返回数
- `source`（可选）— 按来源过滤

**返回：** `Candidate[]` — 含 title/authors/provider/availability/links 等。

### `GET /api/v1/papers/search`

论文候选搜索（arXiv + 百炼评分）。

**查询参数：**
- `q`（可选）— 关键词
- `category`（可选）— arXiv 分类
- `author`（可选）— 作者
- `limit`（可选，默认10，范围1-50）

**返回：** `Candidate[]`。

## ⑤ 探索域端点

### 课程层探索

#### `POST /api/v1/courses/{course_id}/explore`

发起课程层探索（202Accepted）。mode=direct/text/doc；text 需 ref_text ≤10000 字符。

**校验序列：** 400 INVALID_PARAMS → 404 COURSE_NOT_FOUND → 409 CAPACITY_REACHED（active≥4）→ 409 COURSE_LOCKED（completed≥2）→ 幂等查重（running → 返回既有 run + deduplicated:true）→ 入队 202。

**返回：** `{"run_id", "task_id", "status": "running"}` 或 deduplicated 分支。

#### `GET /api/v1/explore-runs/{run_id}`

探索运行详情（孤儿兜底 TASK_LOST/TASK_FAILED）。

#### `POST /api/v1/explore-runs/{run_id}/adopt`

采纳推荐（selected proposal_id 数组）。**单事务**：知识行插入与 run 迁移同 session，任一失败全回滚。

**返回：** `{"adopted": [...], "remaining_slots", "run": {...}}`

#### `POST /api/v1/explore-runs/{run_id}/discard`

放弃探索（ready → discarded）。

#### `GET /api/v1/courses/{course_id}/explore-runs`

课程历史探索列表（limit+offset 分页）。

### 新建领域层探索

#### `POST /api/v1/curriculum-explore`

发起新建领域探索（202 Accepted）。必填 domain_name + mode。

**幂等：** running 命中 → deduplicated:true。

#### `GET /api/v1/curriculum-runs/{run_id}`

新建领域探索运行详情。

#### `POST /api/v1/curriculum-runs/{run_id}/apply`

应用课程体系变更（selected change_id 数组）。

**重探语义（R3）：** domain_name 命中既有领域 → create_domain 记 skipped（非 conflicts），create_course 挂靠已有领域。

**返回：** `{"applied", "conflicts", "skipped", "run": {...}}`

### 手工维护

#### `GET /api/v1/domains`

领域列表。

#### `PATCH /api/v1/domains/{domain_id}`

更新领域（仅 description/stages；name 不可变）。空 body = no-op。

#### `POST /api/v1/domains`

创建领域（服务端生成 domain_id）。body: `{name, description?, stages?}`。

**错误：** 409 DOMAIN_NAME_CONFLICT。

#### `POST /api/v1/domains/{domain_id}/courses`

创建课程（服务端生成 course_id）。body: `{name, stage?, sort_order?, note?}`。

#### `PATCH /api/v1/courses/{course_id}`

更新课程（仅 stage/sort_order/note；name 不可变）。

#### `DELETE /api/v1/courses/{course_id}`

删除课程。**守卫：** 有知识行 → 409 COURSE_HAS_KNOWLEDGE。

#### `DELETE /api/v1/domains/{domain_id}`

删除领域。**守卫：** 有课程 → 409 DOMAIN_NOT_EMPTY。

### prompt 优化评估（QED-043，评估模式）

#### `POST /api/v1/prompt-explores/dry-run`

领域知识探索**评估模式**（同步执行，非 202）：不走正式流程——不写 `qt_prompt_runs`、
不入任务队列；唯一痕迹是 `qed_llm_calls` 的 LLM 日志（`prompt_template=domain-explore/<step>@v1`）。

**body：** `{domain_name 必填, scope_hint?（默认本科-硕士）, mode? direct/text/doc 默认 direct, ref_text?, ref_doc_path?}`

**返回：** `{"dry_run": true, "report": {domain, directions, courses, path(含 graph_td)}, "calls": [{step, template_id, duration_ms}]}`

**错误：** 400 INVALID_PARAMS（参数/doc 文件不可读）→ 409 LLM_UNAVAILABLE（未配置 API_KEY）→ 502 LLM_UNAVAILABLE/BUDGET_EXHAUSTED（模型调用失败）。

模板事实源：`src/qed_tracker/prompt_lab/templates.py`（学科中立守护见 tests/test_prompt_lab.py）。

## 错误码

| 状态码 | 含义 |
| --- | --- |
| 200 | 成功 |
| 201 | 资源创建成功 |
| 202 | 任务已接受（后台执行） |
| 400 | 请求格式错误（INVALID_PARAMS） |
| 404 | 资源不存在（COURSE_NOT_FOUND / RUN_NOT_FOUND / DOMAIN_NOT_FOUND） |
| 409 | 冲突（CAPACITY_REACHED / COURSE_LOCKED / RUN_STATE_CONFLICT / DOMAIN_NAME_CONFLICT / COURSE_HAS_KNOWLEDGE / DOMAIN_NOT_EMPTY） |
| 422 | 参数校验失败（缺必填字段、格式错误） |
| 500 | 服务端错误（KNOWLEDGE_CREATE_FAILED） |
