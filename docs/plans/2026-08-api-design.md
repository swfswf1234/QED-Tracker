# QED-Tracker API 设计文档（8901）

状态：Draft（待审阅）
最后更新：2026-08-28
端口：8901，前缀 `/api/v1`
关联代码：`src/qed_tracker/api/main.py`（685 行）、`src/qed_tracker/api/tasks.py`
关联测试：`tests/test_api.py`、`tests/test_knowledge_api.py`、`tests/test_prompt_lab_api.py`

## 端点总览

| # | 分组 | 端点数 | 说明 |
|---|---|---|---|
| ① | 服务生命周期 | 1 | 健康检查 |
| ② | 目录 | 2 | 下载清单查询（frozen JSON） |
| ③ | 课程体系只读 | 2 | 按领域分组查询 + 单领域查询 |
| ④ | 领域管理 | 5 | 领域 CRUD + 手动 JSON 导入（A4，QED-050） |
| ⑤ | 课程管理 | 3 | 课程创建/更新/删除 |
| ⑥ | 知识探索评估 | 2 | 领域 dry-run + 课程 dry-run（A1，QED-047，已实现） |
| ⑦ | 后台任务 | 3 | 基础设施保留（deprecated，当前无注册 handler） |
| ⑧ | 课程知识采纳 | 1 | 采纳探索推荐建 qt_knowledge 草稿行（A2，已实现） |
| | **合计** | **19** | |

## ① 服务生命周期

### `GET /api/v1/health`

健康检查。

**响应 200：**
```json
{"status": "ok"}
```

---

## ② 目录

目录为 frozen JSON 下载清单（`catalogs/math-qe.json`），记录已完成的教材与习题集目标。与 qed_course 独立——目录是"下载什么"，qed_course 是"有哪些课程"。

### `GET /api/v1/catalogs`

列出所有目录 ID。

**响应 200：**
```json
[{"id": "math-qe"}]
```

### `GET /api/v1/catalogs/{catalog_id}`

目录详情（含全部 targets）。

**路径参数：** `catalog_id` — 目录标识（如 `math-qe`）

**响应 200：**
```json
{
  "id": "math-qe",
  "name": "数学QE书单",
  "description": "...",
  "status": "frozen",
  "targets": [
    {
      "id": "01-rudin-zh",
      "course_id": "01_math_analysis",
      "course_name": "数学分析",
      "kind": "book",
      "title": "数学分析原理",
      "authors": ["Walter Rudin"],
      "query": "...",
      "roles": ["textbook"],
      "set_no": "1"
    }
  ]
}
```

**错误：** 404 目录不存在

---

## ③ 课程体系只读

从共享表 qed_domain/qed_course 读取，纯只读无加工。前端学习中心消费。

### `GET /api/v1/courses`

全量课程体系（按领域分组，sort_order 有序）。

**响应 200：**
```json
[
  {
    "domain_id": "math",
    "name": "数学",
    "description": "学科介绍",
    "level": "本科-硕士",
    "classic_tracks": [{"name": "分析学", "summary": "..."}],
    "stages": ["基础", "进阶"],
    "courses": [
      {
        "course_id": "01_math_analysis",
        "name": "数学分析",
        "aliases": ["高等数学（工科称呼）"],
        "track": "分析学",
        "stage": "基础",
        "prerequisites": [],
        "related_targets": [],
        "description": "课程介绍",
        "exploration_stage": "未开始"
      }
    ]
  }
]
```

### `GET /api/v1/courses/{domain_id}`

单领域课程体系详情（响应结构同上，单元素数组）。

**路径参数：** `domain_id` — 领域标识（如 `math`）

**错误：** 404 未知领域

---

## ④ 领域管理

REQ-059 手工维护端点。Web UI DownloadsTree 组件活跃消费（create/update/delete domain + create course）。

### `GET /api/v1/domains`

领域列表（扁平，不含嵌套课程）。

**响应 200：**
```json
[
  {"domain_id": "math", "name": "数学", "description": "...", "stages": ["基础", "进阶"],
   "level": "本科-硕士", "scope": "...", "classic_tracks": [{"name": "分析学", "summary": "...", "kind": "main"}]}
]
```

### `POST /api/v1/domains`

创建领域（`domain_id` 可选：指定则校验 slug 合法性与冲突，缺省服务端生成；范本导入/目录对齐场景用）。

**请求 Body：**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| name | string | 是 | 领域名称（≤100 字符，唯一性检查） |
| domain_id | string | 否 | 领域标识（slug 格式，冲突 409；缺省生成 d_<hash>） |
| description | string | 否 | 学科介绍 |
| stages | string[] | 否 | 学习阶段列表 |
| level | string | 否 | 探索范围标签（如"本科-硕士"） |
| scope | string | 否 | 学科知识/领域边界描述 |
| classic_tracks | object[] | 否 | 课程方向 [{name, summary, kind}]（0~4 项；kind=main 主干/branch 分支，2026-08-29 语义升级） |

**响应 201：**
```json
{"domain_id": "math", "name": "数学", "description": "...", "stages": [...],
 "level": "本科-硕士", "scope": "...", "classic_tracks": [...]}
```

**错误：** 409 DOMAIN_NAME_CONFLICT（名称重复）| 422 name 为空

### `POST /api/v1/domains/import`（A4，QED-050，**已实现** 2026-08-29）

手动领域 JSON 导入（标准答案录入）：校验 manual@v1 契约 → 写 qed_domain + qed_course（幂等 upsert）。
与领域探索 apply（PATCH /domains 逐项）不同——本端点是**一整份知识定稿**的一次性落库入口。

**请求 Body（二选一）：**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| domain | object | * | 内联领域 JSON（契约：readme「领域 JSON 契约（manual@v1）」） |
| file_path | string | * | 本机可读文件路径（EOF 模式与 domain 二选一） |

领域 JSON 契约要点：`domain`（标识，如 math-advanced）/ `name` / `description` / `level` /
`scope` / `entry_requirements`（一句话）/ `classic_tracks[{name,summary,kind}]` /
`stages`（四档）/ `anchor_courses` / `courses[{slug,name,track,stage,aliases,summary,prerequisites}]` /
`extensions_planned`。

**落库语义（D8）：**
- domain：不存在→创建；存在→更新维护字段（description/level/scope/stages/classic_tracks；name 不可变）；
  `exploration_stage=已完成`（人工探索定稿）；
- courses：逐条 upsert（slug→course_id；详情字段 update，sort_order=课程数组顺序用于新建）；
  既有课程 exploration_stage/related_targets 不触碰；
- `entry_requirements`/`anchor_courses`/`extensions_planned` 属文件侧知识，qed_domain 无对应列，
  **不落库**（保留在 docs/knowledge 正本）。

**响应 200：**
```json
{"domain_id": "math-advanced", "courses_created": 12, "courses_updated": 0, "exploration_stage": "已完成"}
```

**错误：** 400 INVALID_PARAMS（校验失败/文件不可读/JSON 解析失败）| 422 缺 domain 与 file_path

**契约守护：** `src/qed_tracker/application/knowledge_import.py`（validate_domain/manual@v1）+
`tests/test_knowledge_import.py`。

### `PATCH /api/v1/domains/{domain_id}`

更新领域（仅 description/stages；name 不可变）。空 body = no-op。

**路径参数：** `domain_id`

**请求 Body：** 可选字段 `description`、`stages`、`level`、`scope`、`classic_tracks`（exploration_stage 由探索流程管理，不收）

> **A3 扩展（已实现 2026-08-28）**：本端点已支持可选字段 `path_results`、
> `exploration_stage`——探索产物落库收口（两列属「探索产物只归本仓库写」；领域探索
> apply 场景）。契约测试守护：`test_patch_domain_updates_path_results_and_stage`。

**响应 200：** 扁平领域视图（同上）

**错误：** 404 DOMAIN_NOT_FOUND

### `DELETE /api/v1/domains/{domain_id}`

删除领域。

**路径参数：** `domain_id`

**守卫：** 有课程 → 409 DOMAIN_NOT_EMPTY

**响应 200：**
```json
{"ok": "true"}
```

**错误：** 404 DOMAIN_NOT_FOUND | 409 DOMAIN_NOT_EMPTY

---

## ⑤ 课程管理

### `POST /api/v1/domains/{domain_id}/courses`

在领域下创建课程（`course_id` 可选：指定则校验 slug 合法性与冲突，缺省服务端生成；范本导入/目录对齐场景用）。

**路径参数：** `domain_id`

**请求 Body：**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| name | string | 是 | 课程名称 |
| course_id | string | 否 | 课程标识（slug 格式，冲突 409；缺省生成 c_<hash>；与 catalogs 的 NN_slug 对齐） |
| stage | string | 否 | 所属阶段（值域来自 qed_domain.stages） |
| sort_order | int | 否 | 学习顺序（默认 0） |
| description | string | 否 | 课程介绍 |
| aliases | string[] | 否 | 别名列表 |
| track | string | 否 | 课程所属学术方向（classic_tracks 之一） |
| prerequisites | string[] | 否 | 先修 course_id 数组 |

**响应 201：** 完整课程字典（`row.to_dict()`，含全部 15 列）

**错误：** 404 DOMAIN_NOT_FOUND | 409 COURSE_ALREADY_EXISTS | 422 name 为空 / id 非法

### `PATCH /api/v1/courses/{course_id}`

更新课程（stage/sort_order/description/aliases/track/prerequisites；name 不可变；exploration_stage 由探索流程管理）。空 body = no-op。

**路径参数：** `course_id`

**请求 Body：** 可选字段 `stage`、`sort_order`、`description`、`aliases`、`track`、`prerequisites`

**响应 200：** 完整课程字典

**错误：** 404 COURSE_NOT_FOUND

### `DELETE /api/v1/courses/{course_id}`

删除课程。

**路径参数：** `course_id`

**守卫：** 有知识行 → 409 COURSE_HAS_KNOWLEDGE

**响应 200：**
```json
{"ok": "true"}
```

**错误：** 404 COURSE_NOT_FOUND | 409 COURSE_HAS_KNOWLEDGE

---

## ⑥ 知识探索评估

### `POST /api/v1/prompt-explores/dry-run`

同步执行领域探索管线（domain@v2 + courses@v4 + path@v4），不入任务队列，不写任何表。唯一痕迹是 qed_llm_calls 的 LLM 日志。

**请求 Body：**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| domain_name | string | 是 | 领域名称（≤100 字符） |
| mode | string | 否 | `direct` / `text` / `doc`，默认 `direct` |
| scope_hint | string | 否 | 范围说明（默认"本科-硕士"） |
| ref_text | string | 否 | 参考文本（mode=text 时必填，≤10000 字符） |
| ref_doc_path | string | 否 | 参考文档路径（mode=doc 时必填，须为可读文件） |
| confirm_name_override | string | 否 | 名称确认后以规范名重发 |

**响应 200（名称需确认）：**
```json
{
  "dry_run": true,
  "confirmation_required": true,
  "name_check": {"input": "...", "final_name": "...", "valid": false, "reason": "..."}
}
```

**响应 200（成功）：**
```json
{
  "dry_run": true,
  "confirmation_required": false,
  "report": {
    "domain": {"name": "数学", "level": "本科-硕士", ...},
    "directions": [...],
    "courses": [...],
    "path": {"notes": "...", "edges": [...], "graph_td": "graph TD\n..."}
  },
  "calls": [
    {"step": "domain", "template_id": "domain-explore/domain@v2", "duration_ms": 39900},
    {"step": "courses", "template_id": "domain-explore/courses@v4", "duration_ms": 95500},
    {"step": "path", "template_id": "domain-explore/path@v4", "duration_ms": 47300}
  ]
}
```

**错误：**
| 状态码 | 错误码 | 说明 |
|---|---|---|
| 400 | INVALID_PARAMS | 参数错误（domain_name 空/超长、mode 非法、doc 文件不可读） |
| 409 | LLM_UNAVAILABLE | 未配置 API_KEY 或 LLM 初始化失败 |
| 502 | LLM_UNAVAILABLE / BUDGET_EXHAUSTED | 模型调用失败 |

### `POST /api/v1/courses/{course_id}/prompt-explores/dry-run`（A1，QED-047，**已实现** 2026-08-28）

同步执行课程教材探索管线（course-explore tutorials@v1 单步），与领域 dry-run 对称：
**不写任何表**（qt_* 与 qed_* 均不写），唯一痕迹是 qed_llm_calls 的 LLM 日志。
课程行从 qed_course 实读（course_id 透传给管线，含 description/aliases/stage/prerequisites）。

**路径参数：** `course_id` — 课程标识（如 `01_math_analysis`）

**请求 Body：**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| mode | string | 否 | `direct` / `text` / `doc`，默认 `direct` |
| ref_text | string | 否 | 参考文本（mode=text 时必填，≤10000 字符） |
| ref_doc_path | string | 否 | 参考文档路径（mode=doc 时必填，须为可读文件） |

**响应 200：**
```json
{
  "dry_run": true,
  "report": {
    "course": {"course_id": "01_math_analysis", "name": "数学分析", "...": "课程行透传"},
    "tutorials": [
      {
        "proposal_id": "pp_hex12",
        "set_no": "1",
        "set_name": "中文章教程名+作者（≤60 字）",
        "textbook": {"title": "中文书名", "original_title": "...", "roles": ["textbook"],
                      "position": "beginner", "intro": "六要素 100~300 字"},
        "exercise": {"title": "...", "roles": ["exercises"], "position": "...", "intro": "..."},
        "reason": "推荐理由（≤50 字）"
      }
    ]
  },
  "calls": [{"step": "tutorials", "template_id": "course-explore/tutorials@v1", "duration_ms": 45000}]
}
```

**边界与语义：**
- 推荐套数 2~4（模板校验「宁缺勿滥」）；根仓库 ≤4 上限逻辑在根仓库侧，本仓库只返回候选；
- 8901 离线时本端点不可达——采纳步骤依赖本端点产物，根仓库探索会话挂起等待（X3 确认，
  见 [engine-exploration-alignment](2026-08-engine-exploration-alignment.md) 评审记录）；
- 课程探索状态（exploration_stage）由 8900 在探索会话管理中直写（写权限例外），本端点自身不写。

**错误：**
| 状态码 | 错误码 | 说明 |
|---|---|---|
| 400 | INVALID_PARAMS | 参数错误（mode 非法、doc 文件不可读） |
| 404 | COURSE_NOT_FOUND | 课程不存在 |
| 409 | LLM_UNAVAILABLE | 未配置 API_KEY 或 LLM 初始化失败 |
| 502 | LLM_UNAVAILABLE / BUDGET_EXHAUSTED | 模型调用失败 |

---

## ⑦ 后台任务

> **状态：deprecated。** 基础设施（TaskManager/TaskStore/TaskRecord）完整保留，但当前无注册 handler。
> POST 提交恒返回 404「未知任务类型」，GET 列表恒返回空数组。后续若有新异步任务可重新注册 handler 激活。

### `GET /api/v1/tasks`

任务列表（当前恒返回空数组）。

### `GET /api/v1/tasks/{task_id}`

任务详情。

**错误：** 404 任务不存在

### `POST /api/v1/tasks/{task_type}`

提交后台任务（202 Accepted）。

**响应 202：**
```json
{"task_id": "..."}
```

**错误：** 404 未知任务类型

---

## ⑧ 课程知识采纳（A2，**已实现** 2026-08-28）

### `POST /api/v1/courses/{course_id}/knowledge`

采纳课程探索推荐（或人工录入），为课程创建 draft `qt_knowledge` 行（每套一条，
kind=tutorial）。预填六字段：set_no / set_name / textbook_ref / exercise_ref /
textbook_intro / exercise_intro——修复根仓库反馈 §8 缺陷 3（旧 adopt 落库预填全空）。
状态机起点 draft，后续走既有 confirm → books 流程。

**路径参数：** `course_id`

**请求 Body：**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| tutorials | object[] | 是 | 采纳的推荐套子集（1~4 套），结构同 A1 响应 tutorials[i]（set_no/set_name/textbook/exercise/position/reason） |
| source | string | 否 | 来源标识：`explore`（默认）/ `manual`（当前透传保留，未落列） |

**响应 201：**
```json
{"created": [{"knowledge_id": "kn_...", "set_no": "1", "name": "...", "status": "draft", "existing": false}]}
```

**语义定稿（2026-08-28 实现落定 / 2026-08-29 QED-050 补充）：**
- **幂等**：同 course + set_no + set_name（id 规则 `kn_md5(domain, course, kind, set_no, name)`）
  命中既有行 → 返回该行且 `existing: true`，不改动已落库内容；
- **套号冲突**：同 set_no 被不同知识行占用（同名不同 id 或异名）→ 409 `SET_NO_CONFLICT`；
- **同源可空**：`exercise: null` 放行（textbook.roles 须含 exercises 由 A1 管线校验；
  manual 来源轻校验仅要求 exercise 为 null 或含 title），落库 exercise_ref=null；
- **roles 强制（2026-08-29 增强）**：textbook.roles 必须为数组且含 `textbook`；
  exercise 非 null 时 roles 必须含 `exercises`（原轻校验仅查 title）；422 不通过；
- **source 值域（2026-08-29）**：`explore`（默认）/ `manual`，非法值 422；来源标记透传
  不落列（qt_knowledge 无 source 列），manual 来源经 CLI `knowledge import` 复用本端点；
- **target_path 透传**：textbook/exercise 为全量 dict 透传进 ref（含 `target_path`——课程
  知识 JSON 期望落盘路径标准答案，D9；导入落盘与登记回写由其驱动）；
- **状态不推进**：exploration_stage 属验收终态，由 knowledge complete 聚合回写，本端点不动。

**错误：** 404 COURSE_NOT_FOUND | 409 SET_NO_CONFLICT | 422 INVALID_PARAMS

---

## 错误码汇总

| 状态码 | 错误码 | 说明 |
|---|---|---|
| 200 | — | 成功 |
| 201 | — | 资源创建成功 |
| 202 | — | 任务已接受（后台执行） |
| 400 | INVALID_PARAMS | 请求格式错误 |
| 404 | DOMAIN_NOT_FOUND / COURSE_NOT_FOUND | 资源不存在 |
| 409 | DOMAIN_NAME_CONFLICT | 领域名重复 / domain_id 已存在 |
| 409 | COURSE_ALREADY_EXISTS | course_id 已存在 |
| 409 | DOMAIN_NOT_EMPTY | 领域下有课程，不可删除 |
| 409 | COURSE_HAS_KNOWLEDGE | 课程下有知识行，不可删除 |
| 409 | LLM_UNAVAILABLE | LLM 未配置或初始化失败 |
| 422 | INVALID_PARAMS | 缺必填字段 |
| 502 | LLM_UNAVAILABLE / BUDGET_EXHAUSTED | 模型调用失败 |
