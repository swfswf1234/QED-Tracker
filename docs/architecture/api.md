# QED-Tracker API 设计文档（8901）

设计状态：Accepted
确认状态：已确认
实现状态：Implemented
最后更新：2026-09-11
关联代码：`src/qed_tracker/api/main.py`、`src/qed_tracker/api/tasks.py`
关联测试：`tests/test_api.py`、`tests/test_knowledge_api.py`、`tests/test_book_api.py`、`tests/test_knowledge_import.py`、`tests/test_prompt_lab_api.py`、`tests/test_book_fetch.py`、`tests/test_exploration_stage.py`
关联 ADR：[ADR 0001](../adr/0001-tracker-service-architecture.md)

> **确认状态：已确认**——2026-09-09 经用户转正评审（QED-044 收口），本文件为 8901 API 唯一事实源。
> 端点口径：**主线端点按五组写六要素 + 非主线端点 7 条附录一览**；探索阶段端点 2 条已
> 实现并入②组；代码注册路由以 `src/qed_tracker/api/main.py` 为准（QED-060 新增
> start/fail/verify/cancel）。DB 未配置时，五层端点
> 按契约统一 409「数据库未配置」（下文各端点不再重复标注）。
>
> 本文件另含 **8902 消费面契约**（文末「外部接口」节）：QED-Tracker 作为客户端消费
> Axiom-Flow API 的反向契约，与 8901 提供面分列。
>
> ②③ 组按[知识录入设计](../design/knowledge-import.md)与[探索管线设计](../design/exploration-pipeline.md)
> 目标契约登记；④⑤ 组已按 QED-050-D 书库化实现重写（2026-09-06），设计事实源见
> [下载管线设计](../design/download-pipeline.md)。

## 概述

QED-Tracker 通过 FastAPI 提供 HTTP 服务（默认端口 8901），前缀 `/api/v1`，CORS 允许前端
8903 源。端点按业务域分五组主线：

| 组 | 说明 | 端点数 |
| --- | --- | --- |
| ① 服务与任务 | 健康检查 + 后台任务轮询契约 | 2 |
| ② 领域与课程 | 共享表维护（领域/课程 CRUD + 手动导入，双轨[手动]）+ 探索阶段确认端点 + 课程体系与领域详情只读 | 12 |
| ③ 探索评估与采纳 | 探索 dry-run（双轨[自动]）+ 课程知识采纳 + 探索审阅与重探（REQ-067-B12） | 7 |
| ④ 教程 | 教程查询/定稿迁移（draft→confirmed 两态）+ 教程级批量取书 | 4 |
| ⑤ 书籍与渠道 | 书库化创建 + 登记导入 + 渠道留痕 + 书级自动取书（双轨[自动]） | 6 |

只读查询同步返回；写操作提交后台任务（`qt_tasks` 表落盘，并发上限 2，同类型 dedup 查重）
或执行轻量状态迁移（同步）。

**六要素约定**：每个端点按 **接口 / 描述 / 输入 / 输出 / 范例 / 解释** 表述——「接口」即标题
（方法 + 路径）；「输入」列路径参数、查询参数与请求体字段；「输出」列成功状态码与响应结构、
错误状态码；「范例」给可复制的 JSON；「解释」给语义、幂等、状态机与设计文档链接。

## 端点分类索引

> **双轨约定**：`双轨[手动]` 表示用户直接操作（人工录入/审阅），`双轨[自动]` 表示 LLM 后台执行
> （模型推理+自动下载）。定义详见[系统概览](system-overview.md)「手动/自动双轨在架构中的落点」节。

| 方法/路径 | 分类 | 执行模式 | LLM | 说明 |
| --- | --- | --- | --- | --- |
| `GET /api/v1/health` | 只读 | 同步 | - | 健康检查 |
| `GET /api/v1/tasks/{task_id}` | 只读 | 同步 | - | 后台任务轮询 |
| `GET /api/v1/courses` | 只读 | 同步 | - | 课程体系列表 |
| `GET /api/v1/courses/{domain_id}` | 只读 | 同步 | - | 单领域课程详情（待确认态优先回 courses.json） |
| `GET /api/v1/domains/{id}` | 只读 | 同步 | - | 领域详情（已生成态优先回 domains.json） |
| `GET /api/v1/knowledge` | 只读 | 同步 | - | 教程列表 |
| `GET /api/v1/knowledge/{id}` | 只读 | 同步 | - | 教程详情 |
| `GET /api/v1/books/{id}/sources` | 只读 | 同步 | - | 书籍渠道列表 |
| `POST /api/v1/domains` | 双轨[手动] | 同步 | - | 创建领域 |
| `PATCH /api/v1/domains/{id}` | 双轨[手动] | 同步 | - | 更新领域 |
| `DELETE /api/v1/domains/{id}` | 双轨[手动] | 同步 | - | 删除领域 |
| `POST /api/v1/domains/import` | 双轨[手动] | 同步 | - | 手动领域 JSON 导入 |
| `POST /api/v1/domains/{id}/courses/import` | 双轨[手动] | 同步 | - | 手动导入课程 |
| `POST /api/v1/domains/{id}/courses` | 双轨[手动] | 同步 | - | 创建课程 |
| `PATCH /api/v1/courses/{id}` | 双轨[手动] | 同步 | - | 更新课程 |
| `DELETE /api/v1/courses/{id}` | 双轨[手动] | 同步 | - | 删除课程 |
| `POST /api/v1/courses/{id}/knowledge` | 双轨[手动] | 同步 | - | 采纳推荐建教程 |
| `POST /api/v1/knowledge/{id}/confirm` | 双轨[手动] | 同步 | - | 确认教程（draft→confirmed） |
| `PATCH /api/v1/knowledge/{id}` | 双轨[手动] | 同步 | - | 更新教程 |
| `DELETE /api/v1/knowledge/{id}` | 双轨[手动] | 同步 | - | 删除教程 |
| `POST /api/v1/books` | 双轨[手动] | 同步 | - | 书库化创建 |
| `POST /api/v1/books/{id}/sources` | 双轨[手动] | 同步 | - | 添加渠道记录 |
| `POST /api/v1/books/{id}/register` | 双轨[手动] | 同步 | - | 原地登记已有 PDF |
| `POST /api/v1/books/{id}/import` | 双轨[手动] | 同步 | - | 人工导入 PDF |
| `POST /api/v1/domains/{id}/apply-results` | 双轨[手动] | 同步 | - | 确认领域探索结果 |
| `POST /api/v1/courses/{id}/apply-results` | 双轨[手动] | 同步 | - | 确认课程探索结果 |
| `POST /api/v1/prompt-explores/dry-run` | 双轨[自动] | 同步 | Yes | 领域探索评估（domain@v4） |
| `POST /api/v1/courses/{id}/prompt-explores/dry-run` | 双轨[自动] | 同步 | Yes | 课程探索评估（tutorials@v2） |
| `POST /api/v1/domains/{id}/confirm` | 混合（手动触发→异步 LLM） | 同步触发 | 条件 | domains.json 含 courses 时同步写 courses.json（待确认，无 LLM）；否则异步提交 courses@v8 |
| `POST /api/v1/domains/{id}/re-explore` | 双轨[自动] | 202 异步 | Yes | 重置领域探索（domain@v4） |
| `POST /api/v1/courses/{id}/re-explore` | 双轨[自动] | 202 异步 | Yes | 重置课程探索（tutorials@v2） |
| `POST /api/v1/knowledge/{id}/fetch` | 双轨[自动] | 202 异步 | Yes | 教程级批量取书 |
| `POST /api/v1/books/{id}/fetch` | 双轨[自动] | 202 异步 | Yes | 书级自动取书 |
| `POST /api/v1/books/{id}/start` | 双轨[手动] | 同步 | - | 开始下载（decided→downloading） |
| `POST /api/v1/books/{id}/fail` | 双轨[手动] | 同步 | - | 标记下载失败（downloading→failed） |
| `POST /api/v1/books/{id}/verify` | 双轨[手动] | 同步 | - | 验收通过（downloaded→verified） |
| `POST /api/v1/books/{id}/cancel` | 双轨[手动] | 同步 | - | 取消下载（downloading→decided，仅 downloading 可取消） |
| `GET /api/v1/books/search` | 非主线 | 同步 | - | 教材候选搜索 |
| `GET /api/v1/papers/search` | 非主线 | 同步 | - | 论文候选搜索 |
| `GET /api/v1/catalogs` | 非主线 | 同步 | - | 目录列表 |
| `GET /api/v1/catalogs/{id}` | 非主线 | 同步 | - | 目录详情 |
| `GET /api/v1/domains` | 非主线 | 同步 | - | 领域列表（扁平） |
| `GET /api/v1/tasks` | 非主线 | 同步 | - | 任务列表 |
| `POST /api/v1/tasks/{task_type}` | 非主线 | 202 异步 | - | 提交后台任务（基础设施） |

**执行模式说明**：
- **同步**：请求阻塞等待结果返回
- **202 异步**：请求立即返回 `task_id`，需轮询 `GET /tasks/{task_id}` 获取结果
- **混合**：用户操作同步完成，内部异步提交 LLM 任务

## ① 服务与任务

### `GET /api/v1/health`

- **描述：** 健康检查（服务存活探测）。
- **输入：** 无。
- **输出：** 200 `{"status": "ok"}`。
- **范例：**
  ```json
  {"status": "ok"}
  ```
- **解释：** 前端/CLI 探测 8901 是否在线；服务启动即返回，与数据库可用性无关
  （DB 未配置时仍 200）。

### `GET /api/v1/tasks/{task_id}`

- **描述：** 后台任务详情（202 写操作的统一轮询契约）。
- **输入：** 路径参数 `task_id` — 任务标识。
- **输出：** 200 `TaskRecord`（task_id/task_type/status/params/progress/message/result/error/
  created_at/updated_at）；404 任务不存在。
- **范例：**
  ```json
  {
    "task_id": "task_book_download_001",
    "task_type": "book_download",
    "status": "succeeded",
    "progress": 100,
    "message": "完成",
    "result": {"ok": true, "book_id": "mathanalysis-b01", "file_path": "raw/math/math_analysis/数学分析_a1b2c3d4.pdf"},
    "error": ""
  }
  ```
- **解释：** status 走 `queued → running → succeeded/failed` 状态机（qt_tasks 表承载，
  见[数据库专用表设计](database-private-tables.md)）；`result` 载荷结构随任务类型
  （见③④⑤各组取书/重探端点的任务 result 说明）。

## ② 领域与课程

> **`courses.json` 生命周期（2026-09-11 QED-061）**：`raw/{domain_id}/courses.json` 是领域
> 探索第二轮的**中间态**文件（confirm 含 courses 分支 / courses@v8 handler / `courses/import`
> 捷径写入，`待确认` 态供审阅）。领域 `apply-results` 到达 `已完成` 时，其内容被**反写进
> `raw/{domain_id}/domains.json`（含最终课程）并删除该文件**；此后领域层只保留可重新导入的
> `domains.json`。本组各端点对 courses.json 的读取仅发生在 `待确认` 及之前。

### `GET /api/v1/courses`

- **描述：** 课程体系列表（读共享表 qed_domain/qed_course，按领域分组全量，courses 按
  sort_order 有序，无加工直接透出）。
- **输入：** 无。
- **输出：** 200 `CourseDomain[]` — 每个领域含
  `domain_id / name / description / level / classic_tracks / exploration_stage / path_results / stages`
  与 `courses[]`（每门：`course_id / name / aliases / track / stage / prerequisites /
  related_targets / description / exploration_stage`；审计列不透出）。
- **范例：**
  ```json
  [
    {
      "domain_id": "math",
      "name": "数学",
      "description": "学科介绍",
      "level": "本科-硕士",
      "classic_tracks": [{"name": "分析学", "summary": "..."}],
      "exploration_stage": "未开始",
      "path_results": null,
      "stages": ["基础", "进阶"],
      "courses": [
        {
          "course_id": "math_analysis",
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
- **解释：** 共享表只读契约（QED-Tracker 建表维护、其他项目只读），表设计见
  [数据库共享表设计](database-shared-tables.md)；前端学习中心消费。

### `GET /api/v1/courses/{domain_id}`

- **描述：** 单领域课程体系详情（响应结构同上，单元素数组）；`待确认` 状态优先返回
  `courses.json` 文件数据（探索结果以 JSON 文件为唯一事实源，apply-results 前尚未落库）。
- **输入：** 路径参数 `domain_id` — 领域标识（如 `math`）。
- **输出：** 200 同上单元素数组；`待确认` 且 `raw/{domain_id}/courses.json` 存在时，课程数组
  为 JSON 文件原样结构（字段含 `summary`，与落库后的 `description` 不同名）并附加
  `path`（探索派生路径）与 `source: "json_file"` 标记；文件缺失时回退数据库视图。
  404 未知领域。
- **范例：**
  ```json
  [{"domain_id": "math", "name": "数学", "courses": ["…同 GET /api/v1/courses 单门课程结构…"]}]
  ```
- **解释：** 前端按领域拉取课程体系的视图端点；字段语义与共享表列一一对应；`json_file`
  分支使审阅页在 apply-results 落库前即可读到探索产出（与②组 confirm 写 `courses.json`、
  ③组 apply-results 的「先同步后采纳」语义配套）。

### `POST /api/v1/domains`

- **描述：** 创建领域（REQ-059 手工维护端点，前端 DownloadsTree 组件活跃消费）。
- **输入：** 请求体：

  | 字段 | 类型 | 必填 | 说明 |
  |---|---|---|---|
  | name | string | 是 | 领域名称（≤100 字符，唯一性检查） |
  | domain_id | string | 否 | 领域标识（缺省服务端生成；显式指定须匹配 course_id 格式规则 `^[a-z0-9][a-z0-9_-]{1,62}$`） |
  | description | string | 否 | 学科介绍 |
  | stages | string[] | 否 | 学习阶段列表 |
  | level | string | 否 | 探索范围标签（如"本科-硕士"） |
  | scope | string | 否 | 学科知识/领域边界描述 |
  | classic_tracks | object[] | 否 | 课程方向 [{name, summary, kind}]（0~4 项；kind=main 主干/branch 分支） |

- **输出：** 201 领域完整字典；409 `DOMAIN_NAME_CONFLICT`（name 或 domain_id 已存在）；
  422 `INVALID_PARAMS`。
- **范例：**
  ```json
  // 请求
  {"name": "数学", "level": "本科-硕士", "stages": ["基础", "进阶"]}

  // 响应 201
  {"domain_id": "math", "name": "数学", "description": "", "stages": ["基础", "进阶"], "level": "本科-硕士"}
  ```
- **解释：** `domain_id` 生成（2026-09-11 QED-062）：① 调用方显式提供；② ASCII 名称机械
  kebab slug 化（小写字母/数字/连字符）；③ 中文名等无法派生时 **422 `INVALID_PARAMS`** 要求
  显式提供（不再用 `d_<md5>` 兜底）。

### `PATCH /api/v1/domains/{domain_id}`

- **描述：** 更新领域维护字段（空 body = no-op）。
- **输入：** 路径参数 `domain_id`；请求体可选字段 `description / stages / level / scope /
  classic_tracks / path_results / exploration_stage`（`name`/`domain_id` 不可变）。
- **输出：** 200 扁平领域视图；404 `DOMAIN_NOT_FOUND`。
- **范例：**
  ```json
  {"description": "数学（本科-博士）", "exploration_stage": "探索中"}
  ```
- **解释：** `path_results`/`exploration_stage` 为探索产物落库收口（A3 扩展，探索 apply
  场景直写）；常规维护不应手工改这两列——探索流程见③组与
  [探索管线设计](../design/exploration-pipeline.md)。

### `DELETE /api/v1/domains/{domain_id}`

- **描述：** 删除领域。
- **输入：** 路径参数 `domain_id`。
- **输出：** 200 `{"ok": "true"}`；404 `DOMAIN_NOT_FOUND`；409 `DOMAIN_NOT_EMPTY`（领域下有课程）。
- **范例：**
  ```json
  {"ok": "true"}
  ```
- **解释：** 硬删除；守卫防止课程体系连带误删（删课程须先清领域下课程）。

### `GET /api/v1/domains/{domain_id}`

- **描述：** 领域详情；`已生成` 状态优先返回 `domains.json` 文件数据（手动导入后的待确认
  第一轮，报告以 JSON 文件为唯一事实源），其余状态从数据库读取。
- **输入：** 路径参数 `domain_id` — 领域标识（如 `math`）。
- **输出：** 200 领域字典 + `courses[]`；`已生成` 且 `raw/{domain_id}/domains.json` 存在时，
  name/description/stages/level/scope/classic_tracks/courses 以 JSON 文件为准并附
  `source: "json_file"`，`exploration_stage` 仍取自数据库；文件缺失时回退数据库视图
  （字段同 `GET /api/v1/courses` 单领域视图，无 `scope`）。404 `DOMAIN_NOT_FOUND`。
- **范例：**
  ```json
  // 响应 200（已生成 + domains.json 存在）
  {
    "domain_id": "math-advanced", "name": "数学（高等数学）",
    "description": "…", "stages": ["基础", "主干", "分支", "前沿"],
    "level": "本科", "scope": "…", "classic_tracks": [{"name": "分析学", "summary": "...", "kind": "main"}],
    "courses": [{"course_id": "math_analysis", "name": "数学分析", "summary": "..."}],
    "exploration_stage": "已生成", "source": "json_file"
  }
  ```
- **解释：** 六步流程第 1 步（`POST /domains/import`）后的审阅视图端点：前端在 confirm 前
  经此读取导入文件内容；confirm 后（探索中/待确认/已完成）回到数据库视图。

### `POST /api/v1/domains/import`【手动导入】

- **描述：** 手动领域 JSON 导入（QED-050，2026-09-03 六步流程第 1 步）：校验 manual@v1 契约 →
  写入 `raw/{domain_id}/domains.json` 文件暂存 → 更新既有领域 `exploration_stage=已生成`。
  **只写文件不落库**（课程落库由第 2/3 步 confirm / courses/import 承接）；领域行必须已存在，
  本端点不创建领域。
- **输入：** 请求体（二选一）：

  | 字段 | 类型 | 必填 | 说明 |
  |---|---|---|---|
  | domain | object | * | 内联领域 JSON（manual@v1 契约） |
  | file_path | string | * | 本机可读文件路径（与 domain 二选一） |

  领域 JSON 契约要点：`domain`（标识）/ `name` / `description` / `level` / `scope` /
  `classic_tracks[{name,summary,kind}]` / `stages`（四档）/
  `courses[{course_id,name,track,stage,aliases,summary,prerequisites}]`（courses 可空，空时
  confirm 走 LLM 探索分支）。
- **输出：** 200 `{"domain_id", "file_path", "exploration_stage": "已生成", "message"}`；
  400 `INVALID_PARAMS`（校验失败/文件不可读/JSON 解析失败）；404 `DOMAIN_NOT_FOUND`
  （领域不存在，须先 `POST /domains` 创建）；422 缺 domain/file_path。
- **范例：**
  ```json
  // 请求
  {"domain": {"domain": "math-advanced", "name": "数学（高等数学）", "classic_tracks": [{"name": "分析学", "summary": "...", "kind": "main"}], "stages": ["基础", "主干", "分支", "前沿"], "courses": [{"course_id": "math_analysis", "name": "数学分析", "track": "分析学", "stage": "基础", "summary": "..."}]}}

  // 响应 200
  {"domain_id": "math-advanced", "file_path": "raw/math-advanced/domains.json", "exploration_stage": "已生成", "message": "领域知识已写入文件，状态更新为已生成"}
  ```
- **解释：**
  - 落盘语义：写入 `QED_DATA_ROOT/raw/{domain_id}/domains.json`（重复导入覆盖，幂等）；
    仅更新既有领域的 `exploration_stage=已生成`，不写任何表行、不写 explore_pending。
  - 历史口径（2026-09-08 前）曾有 `source` 参数（`manual`/`explore`/`cli`）与 D8 一次落库
    语义，现均已退役：`source` 参数不再读取，CLI `domains import` 与 API 走同一六步流程
    （见[知识录入设计](../design/knowledge-import.md)）。
  - 契约守护：`src/qed_tracker/application/knowledge_import.py`（manual@v1 校验器）+
    `tests/test_knowledge_import.py`。

### `POST /api/v1/domains/{domain_id}/confirm`

- **描述：** 确认领域知识（双轨[手动]确认步，六步流程第 2 步）：读取 domains.json →
  upsert QedDomain；**双分支**——domains.json 已含 courses（手动导入）时直接同步写
  `courses.json`（不触发 LLM）；无 courses（LLM 探索轨）时异步提交 courses@v8 后台任务。
- **输入：** 路径参数 `domain_id`；无 body。
- **输出：** 200 `{domain_id, task_id, exploration_stage, message}`（`task_id` 手动分支为
  `null`）；404 `FILE_NOT_FOUND`。
- **范例：**
  ```json
  // 响应 200（domains.json 含 courses —— 手动导入分支）
  {"domain_id": "math", "task_id": null, "exploration_stage": "待确认", "message": "领域已确认，课程已从导入文件同步"}

  // 响应 200（无 courses —— LLM 探索分支）
  {"domain_id": "math", "task_id": "task_domain_explore_courses_001", "exploration_stage": "探索中", "message": "已提交 courses@v8 后台任务，轮询 GET /api/v1/tasks/{task_id} 等待完成"}
  ```
- **解释：** 读取 `raw/{domain_id}/domains.json` → upsert domain：
  - **手动导入分支**：domains.json `courses` 非空 → 原样组装写入
    `raw/{domain_id}/courses.json`，状态直接置 `待确认`（跳过 LLM 与探索中），`task_id=null`；
  - **LLM 探索分支**：`courses` 为空 → 异步提交 `domain_explore_courses` 后台任务
    （只跑 courses@v8）→ 状态置 `探索中`，返回 task_id 供轮询。
  幂等（重复 confirm 只覆盖不重复创建）；见[知识录入设计](../design/knowledge-import.md)。

### `POST /api/v1/domains/{domain_id}/courses/import`

- **描述：** 从 domains.json 读取 courses 并写入 qed_course（双轨[手动]确认步）。
- **输入：** 路径参数 `domain_id`；无 body。
- **输出：** 200 `{domain_id, courses_created, courses_updated, exploration_stage: "待确认"}`；
  400 `INVALID_PARAMS`（domains.json 无课程数据）；404 `FILE_NOT_FOUND` /
  `DOMAIN_NOT_FOUND`；409 `INVALID_TRANSITION`（状态须为 `已生成` 或 `探索中`）。
- **范例：**
  ```json
  // 响应 200
  {
    "domain_id": "math",
    "courses_created": 12,
    "courses_updated": 0,
    "exploration_stage": "待确认"
  }
  ```
- **解释：** 读取 `raw/{domain_id}/domains.json` → 逐条 upsert `qed_course`（新课程
  `sort_order`=数组序；既有课程更新详情字段，`exploration_stage`/`related_targets` 不触碰）
  → 状态变为 `待确认`。守卫接受 `已生成`（手动导入第 1 步后）与 `探索中`（LLM 探索中）——
  2026-09-09 自「仅探索中」放宽（QED-055，根仓库 REQ-067 手动导入六步流程第 3 步）。

### `POST /api/v1/domains/{domain_id}/courses`

- **描述：** 在领域下创建课程。
- **输入：** 路径参数 `domain_id`；请求体：

  | 字段 | 类型 | 必填 | 说明 |
  |---|---|---|---|
  | name | string | 是 | 课程名称 |
  | course_id | string | 否 | 课程标识（2026-09-11 QED-062：显式优先；缺省由 ASCII 名称生成 snake slug；中文名等无法派生 → 422 `INVALID_PARAMS`；显式指定须匹配 course_id 格式规则） |
  | stage | string | 否 | 所属阶段（值域来自 qed_domain.stages） |
  | sort_order | int | 否 | 学习顺序（默认 0） |
  | description | string | 否 | 课程介绍 |
  | aliases | string[] | 否 | 别名列表 |
  | track | string | 否 | 课程所属学术方向（classic_tracks 之一） |
  | prerequisites | string[] | 否 | 先修 course_id 数组 |

- **输出：** 201 完整课程字典（`row.to_dict()` 含全部 16 列）；404 `DOMAIN_NOT_FOUND`；
  409 `COURSE_ALREADY_EXISTS`；422 `INVALID_PARAMS`。
- **范例：**
  ```json
  // 请求
  {"name": "数学分析", "course_id": "math_analysis", "stage": "基础", "track": "分析学"}

  // 响应 201
  {"course_id": "math_analysis", "name": "数学分析", "stage": "基础", "track": "分析学", "sort_order": 0, "…": "其余列见 qed_course"}
  ```
- **解释：** `course_id` 显式指定用于与标准答案 JSON / 目录对齐的场景；格式规则同
  共享表列约束（见[数据库共享表设计](database-shared-tables.md)）。

### `PATCH /api/v1/courses/{course_id}`

- **描述：** 更新课程（空 body = no-op）。
- **输入：** 路径参数 `course_id`；请求体可选字段 `stage / sort_order / description / aliases /
  track / prerequisites / exploration_stage / explore_pending`（`name`/`course_id` 不可变）。
- **输出：** 200 完整课程字典；404 `COURSE_NOT_FOUND`；422 `INVALID_PARAMS`
  （`exploration_stage` 不在课程 5 态值域，或 `explore_pending` 非对象/非 null）。
- **范例：**
  ```json
  {"stage": "主干", "prerequisites": ["00_foundations"], "exploration_stage": "探索中"}
  ```
- **解释：** 2026-09-11 REQ-077（D3=B）：本端点支持 `exploration_stage`/`explore_pending`，
  8900 课程阶段流转改经此端点（不再直写共享表）。`exploration_stage` 值域为**课程 5 态**
  `未开始/探索中/待确认/已完成/失败`——**不含「已生成」**（仅领域保留），非法值返回 422
  `INVALID_PARAMS`；`explore_pending.kind` 仅 `review_results`/`name_confirmation`/`error`
  三形态。领域阶段流转见 `PATCH /domains/{id}`，探索审阅见③组。

### `DELETE /api/v1/courses/{course_id}`

- **描述：** 删除课程。
- **输入：** 路径参数 `course_id`。
- **输出：** 200 `{"ok": "true"}`；404 `COURSE_NOT_FOUND`；409 `COURSE_HAS_KNOWLEDGE`（课程下有教程）。
- **范例：**
  ```json
  {"ok": "true"}
  ```
- **解释：** 硬删除；守卫防止教程引用悬空（删课程须先删/迁移其教程）。

## ③ 探索评估与采纳

> 探索双轨：dry-run 评估（双轨[自动]，同步、不落库）与人工录入（双轨[手动]，经②组
> domains/import）两条轨；本组另含探索审阅与重探（REQ-067-B12）。设计见
> [探索管线设计](../design/exploration-pipeline.md)、[知识录入设计](../design/knowledge-import.md)。

### `POST /api/v1/prompt-explores/dry-run`

- **描述：** 领域知识探索**评估模式**（同步执行，非 202）：不入任务队列；不写任何表，唯一
  痕迹是 `qed_llm_calls` 的 LLM 日志（模板 domain-explore/`domain@v4` 单步管线）。
  只预览领域结构（classic_tracks/stages/level），不生成课程列表；courses@v8
  在 confirm-domain 后由后台异步任务执行。
- **输入：** 请求体：

  | 字段 | 类型 | 必填 | 说明 |
  |---|---|---|---|
  | domain_name | string | 是 | 领域名称（非空且 ≤100 字符） |
  | scope_hint | string | 否 | 范围说明（默认"本科-硕士"） |
  | mode | string | 否 | `direct` / `text` / `doc`，默认 `direct` |
  | ref_text | string | 否 | 参考文本（mode=text 时必填，≤10000 字符） |
  | ref_doc_path | string | 否 | 参考文档路径（mode=doc 时必填，须为可读文件） |
  | confirm_name_override | string | 否 | 名称确认后以规范名重发 |

- **输出：** 200 `{"dry_run": true, "confirmation_required": false, "report": {...}, "calls": [...]}`；
  名称确认分支 `{"dry_run": true, "confirmation_required": true, "name_check": {...}}`；
  400 `INVALID_PARAMS`（参数/doc 文件不可读）；409 `LLM_UNAVAILABLE`（未配置 API_KEY 或
  管线初始化失败）；502 管线错误码透传（`LLM_UNAVAILABLE` / `BUDGET_EXHAUSTED` 等）。
- **范例：**
  ```json
  // 请求
  {"domain_name": "数学", "mode": "direct"}

  // 响应 200
  {
    "dry_run": true,
    "confirmation_required": false,
    "report": {
      "domain": {"name": "数学", "level": "本科-硕士", "stages": ["基础", "主干", "分支", "前沿"], "classic_tracks": [{"name": "分析学", "summary": "...", "kind": "main"}]},
      "courses": null
    },
    "calls": [
      {"step": "domain", "template_id": "domain-explore/domain@v4", "duration_ms": 39900}
    ]
  }
  ```
- **解释：** P12 阶段一名称确认：规范名待人工确认后以 `confirm_name_override` 重新发起；
  dry-run 是采纳（`POST /courses/{course_id}/knowledge`）与导入（②组 domains/import）前的
  零副作用评估入口。

### `POST /api/v1/courses/{course_id}/prompt-explores/dry-run`

- **描述：** 课程教材探索 dry-run（QED-047 A1）：同步单步 tutorials@v2，不写任何表
  （qt_* 与 qed_* 均不写），唯一痕迹是 qed_llm_calls；与领域 dry-run 对称（校验序
  mode→key→404→管线）。课程行从 qed_course 实读（course_id 透传给管线，含
  description/aliases/stage/prerequisites）。
- **输入：** 路径参数 `course_id`；请求体可选 `mode`（direct/text/doc，默认 direct）、
  `ref_text`（mode=text 必填）、`ref_doc_path`（mode=doc 必填）。
- **输出：** 200 `{"dry_run": true, "report": {...推荐套列表...}, "calls": [...]}`；
  400 `INVALID_PARAMS`；404 `COURSE_NOT_FOUND`；409 `LLM_UNAVAILABLE`；502 管线错误透传。
- **范例：**
  ```json
  // 请求
  {"mode": "direct"}

  // 响应 200
  {
    "dry_run": true,
    "report": {
      "course": {"course_id": "math_analysis", "name": "数学分析"},
      "tutorials": [
        {"set_no": "1", "name": "教程1：作者《书名》", "position": "beginner", "intro": "…六要素简介…",
         "textbook_ref": [{"title": "书名", "part": "", "authors": [{"name": "作者", "role": "author"}], "publisher": "出版社", "edition": "第3版", "year": 2006, "language": "zh", "roles": ["textbook"]}],
         "exercise_ref": null, "parallel_ref": null}
      ]
    },
    "calls": [{"step": "tutorials", "template_id": "course-explore/tutorials@v2", "duration_ms": 45000}]
  }
  ```
- **解释：** `report.tutorials` 即采纳端点 `POST /courses/{course_id}/knowledge` 的
  `tutorials` 输入结构（审阅后可直传采纳）；8901 离线时本端点不可达——采纳步骤依赖本端点
  产物，根仓库探索会话挂起等待（X3 确认）；课程探索状态（exploration_stage）由 8900 经
  `PATCH /courses/{id}` 推进（REQ-077 D3=B），本端点自身不写。

### `POST /api/v1/courses/{course_id}/knowledge`

- **描述：** 采纳推荐建教程（QED-047 A2，201）：tutorials@v2 输出格式，每套建 **draft**
  qt_knowledge 行并预填 `set_no/name/position/intro/textbook_ref/exercise_ref/parallel_ref`；
  经 textbook_ref/exercise_ref 建 `status=decided` 书行、parallel_ref 建 `status=parallel`
  书行并回填 `book_id`。
- **输入：** 路径参数 `course_id`；请求体：

  | 字段 | 类型 | 必填 | 说明 |
  |---|---|---|---|
  | tutorials | object[] | 是 | 采纳的推荐套子集（1~6 套），结构同课程 dry-run 的 tutorials[i] |
  | source | string | 否 | `explore`（默认，自动探索采纳）/ `manual`（人工录入），仅作来源标记 |

  每套校验：set_no 非空 ≤4 / name 非空 ≤128 / position 五档 / intro ≥120 字 /
  textbook_ref 非空数组 / exercise_ref、parallel_ref 为 null 或数组。
- **输出：** 201 `{"created": [{"knowledge_id", "set_no", "name", "status": "draft", "existing": false}]}`；
  404 `COURSE_NOT_FOUND`；409 `SET_NO_CONFLICT`；422 `INVALID_PARAMS`。
- **范例：**
  ```json
  // 请求
  {"source": "manual", "tutorials": [{"set_no": "1", "name": "教程1：比廷杰《微积分及其应用》", "position": "beginner", "intro": "…120 字以上…", "textbook_ref": [{"title": "微积分及其应用", "part": "", "authors": [{"name": "比廷杰", "role": "author"}], "publisher": "高等教育出版社", "edition": "", "year": 2006, "language": "zh", "roles": ["textbook"]}], "exercise_ref": null, "parallel_ref": null}]}

  // 响应 201
  {"created": [{"knowledge_id": "kt-mathanalysis-1", "set_no": "1", "name": "教程1：比廷杰《微积分及其应用》", "status": "draft", "existing": false}]}
  ```
- **解释：** 语义定稿（adopt_tutorials 仓储）：
  - **幂等**：命中既有行 → 返回该行且 `existing: true`，不改动已落库内容；
  - **套号冲突**：同 set_no 被不同教程占用 → 409 `SET_NO_CONFLICT`；
  - **同源可空**：`exercise_ref: null` 放行（教材 roles 含 exercises 时自含习题）；
  - **roles 强制**：textbook.roles 必须为数组且含 `textbook`；exercise 非 null 时 roles 必须
    含 `exercises`；422 不通过；
  - **target_path 透传**：ref 字典全量透传（含课程知识 JSON 期望落盘路径标准答案 D9，
    导入落盘与登记回写由其驱动）；
  - **状态不推进**：exploration_stage 属验收终态，由导入/apply-results 层管理，本端点不动；
  - knowledge_id 由服务端按 `kt-{课程缩写}-{set_no}` 规则生成（见
    [数据库专用表设计](database-private-tables.md) qt_knowledge 节）。

### `POST /api/v1/domains/{domain_id}/apply-results`

- **接口：** POST `/api/v1/domains/{domain_id}/apply-results`，路径参数 `domain_id`。
- **描述：** 确认领域探索结果（待确认 → 已完成）：先从 `courses.json` 幂等同步课程入
  qed_course（courses@v8 与手动 confirm 分支只写 JSON 文件不写库），再选择要保留的课程，
  删除其余。
- **输入：** body `{selected_courses: string[]}`（必填，选中的课程 ID 列表）。
- **输出：** 200 `{domain_id, courses_kept}`；404 领域不存在；409 当前状态非「待确认」；422 selected_courses 非数组。
- **范例：**
  ```json
  // 请求
  {"selected_courses": ["math_analysis", "abstract_algebra"]}

  // 响应
  {"domain_id": "math", "courses_kept": 2}
  ```
- **解释：** 前置同步（2026-09-08 修复，问题 4）：`_sync_courses_from_json_to_db` 在采纳前
  把 `raw/{domain_id}/courses.json` 的课程逐条 upsert 入库（无文件则跳过）——courses@v8
  任务与 confirm 手动分支均只产出 JSON 文件，未经同步直接查询 qed_course 会得到 0 门
  （courses_kept=0 事故根因）。随后进入采纳：删除未选课程；设计见
  [REQ-067-B10/B12 探索阶段设计](../history/baselines/2026-08-31-req067-b10-b12-exploration-stage.md)，
  状态机登记见[数据库共享表设计](database-shared-tables.md)状态机节。

### `POST /api/v1/domains/{domain_id}/re-explore`

- **接口：** POST `/api/v1/domains/{domain_id}/re-explore`，路径参数 `domain_id`。
- **描述：** 重置领域探索（待确认 → 探索中）：清除 explore_pending，提交后台重新探索任务。
- **输入：** body `{description?: string, mode?: string}`（可选；description 覆盖领域描述，mode 默认 "direct"）。
- **输出：** 202 `{task_id}`；404 领域不存在；409 当前状态非「待确认」。
- **范例：**
  ```json
  // 请求
  {"description": "数学（本科-博士）", "mode": "web"}

  // 响应
  {"task_id": "task_math_reexplore_001"}
  ```
- **解释：** 重探结果回到「待确认」，再次走 apply-results 确认或 re-explore 循环；
  任务经 `GET /api/v1/tasks/{task_id}` 轮询。

### `POST /api/v1/courses/{course_id}/apply-results`

- **接口：** POST `/api/v1/courses/{course_id}/apply-results`，路径参数 `course_id`。
- **描述：** 确认课程探索结果（待确认 → 已完成）：选择要保留的教程，删除其余。
- **输入：** body `{selected_tutorials: string[]}`（必填，选中的教程 set_no 列表）。
- **输出：** 200 `{course_id, tutorials_kept}`；404 课程不存在；409 当前状态非「待确认」；422 selected_tutorials 非数组。
- **范例：**
  ```json
  // 请求
  {"selected_tutorials": ["1", "2"]}

  // 响应
  {"course_id": "math_analysis", "tutorials_kept": 2}
  ```
- **解释：** 与领域 apply-results 对称；删除的教程行连同其书引用关系一并清理
  （书行为域级资产，不随教程删除）。

### `POST /api/v1/courses/{course_id}/re-explore`

- **接口：** POST `/api/v1/courses/{course_id}/re-explore`，路径参数 `course_id`。
- **描述：** 重置课程探索（待确认 → 探索中）：清除 explore_pending，提交后台重新探索任务。
- **输入：** body `{description?: string, mode?: string}`（可选；description 覆盖课程描述，mode 默认 "direct"）。
- **输出：** 202 `{task_id}`；404 课程不存在；409 当前状态非「待确认」。
- **范例：**
  ```json
  // 请求
  {"mode": "web"}

  // 响应
  {"task_id": "task_course_reexplore_001"}
  ```
- **解释：** 与领域 re-explore 对称；任务经 `GET /api/v1/tasks/{task_id}` 轮询。

## ④ 教程

> 两态契约（2026-09-03 D1 裁决）：`draft → confirmed`，confirmed 为终态。
> `reject`/`supersede`/`complete` 端点**已删除**（两态后无此语义，废弃/退役改 `notes` 记录），
> 不属于当前运行时。设计见[知识录入设计](../design/knowledge-import.md)。

### `GET /api/v1/knowledge`

- **描述：** 教程列表（两态 draft/confirmed）。
- **输入：** 查询参数 `course_id`（可选，按课程筛选）、`status`（可选，按状态筛选）。
- **输出：** 200 `KnowledgeRow[]`（`row.to_dict()` 全列，列语义见
  [数据库专用表设计](database-private-tables.md) qt_knowledge 节）。
- **范例：**
  ```json
  [{"knowledge_id": "kt-mathanalysis-1", "course_id": "math_analysis", "kind": "tutorial", "set_no": "1", "name": "教程1：…", "position": "beginner", "status": "draft", "textbook_ref": [], "exercise_ref": null, "parallel_ref": null, "confirmed_at": null}]
  ```
- **解释：** CLI `mainline review` 与前端教程列表消费；列表不含 `books[]`
  （聚合视图见详情端点）。

### `GET /api/v1/knowledge/{knowledge_id}`

- **描述：** 教程详情（含关联书籍列表 `books[]`）。
- **输入：** 路径参数 `knowledge_id` — 教程标识（如 `kt-mathanalysis-1`）。
- **输出：** 200 教程行 + `books[]`（**由 refs 数组聚合**：从 `textbook_ref[]`/`exercise_ref[]`/
  `parallel_ref[]` 内的 `book_id` 汇总，每行为 `QtBook.to_dict()` 全列）；404 教程不存在。
- **范例：**
  ```json
  {
    "knowledge_id": "kt-mathanalysis-1", "course_id": "math_analysis", "kind": "tutorial", "status": "draft",
    "textbook_ref": [{"book_id": "mathanalysis-b01", "title": "数学分析", "roles": ["textbook"]}],
    "books": [{"book_id": "mathanalysis-b01", "title": "数学分析", "holding": "missing", "status": "decided"}]
  }
  ```
- **解释：** 书籍响应契约（books[] 聚合规则、无 display_title/sha256 等列）见
  [数据库专用表设计](database-private-tables.md)「书籍响应契约」节；教程级取书
  （下条 fetch）与本端点共用 refs 聚合语义。

### `POST /api/v1/knowledge/{knowledge_id}/confirm`

- **描述：** 确认教程（draft → confirmed 定稿）。
- **输入：** 路径参数 `knowledge_id`；无 body。
- **输出：** 200 教程视图（`status=confirmed`，`confirmed_at` 回填，含 `books[]`）；
  404 教程不存在；409 非法状态迁移。
- **范例：**
  ```json
  {"knowledge_id": "kt-mathanalysis-1", "status": "confirmed", "confirmed_at": "2026-09-07T10:00:00"}
  ```
- **解释：** confirmed 为终态（无再迁移）；定稿后 refs 引用书集即为推荐书单，
  取书按 refs 驱动（见[知识录入设计](../design/knowledge-import.md)）。

### `PATCH /api/v1/knowledge/{knowledge_id}`

- **描述：** 更新教程信息（name、position、intro 等字段）。
- **输入：** 路径参数 `knowledge_id`；请求体可选字段：`name`、`position`、`intro`、`set_no`、`kind`、`notes`。
- **输出：** 200 返回更新后的教程详情（含 `books[]`）；404 教程不存在。
- **范例：**
  ```json
  // 请求
  PATCH /api/v1/knowledge/kt-cs01-1
  {
    "name": "教程1：算法导论（CLRS）",
    "position": "intermediate"
  }

  // 响应
  {
    "knowledge_id": "kt-cs01-1",
    "course_id": "cs01",
    "name": "教程1：算法导论（CLRS）",
    "position": "intermediate",
    "intro": "本教程介绍算法设计与分析的基本概念...",
    "status": "draft",
    "books": []
  }
  ```
- **解释：** 部分更新，只修改提供的字段；`knowledge_id` 和 `course_id` 不可变。

### `DELETE /api/v1/knowledge/{knowledge_id}`

- **描述：** 物理删除教程及其孤立的书库数据。
- **输入：** 路径参数 `knowledge_id`。
- **输出：** 200 `{"ok": "true"}`；404 教程不存在。
- **范例：**
  ```json
  // 请求
  DELETE /api/v1/knowledge/kt-cs01-1

  // 响应
  {"ok": "true"}
  ```
- **解释：** 物理删除教程记录；同时清理不再被任何教程引用的孤立书库数据（`qt_books`、`qt_sources`）；
  仍被其他教程引用的书会被保留。

### `POST /api/v1/knowledge/{knowledge_id}/fetch`

- **描述：** 教程级批量取书（双轨[自动]）：refs 聚合书集（去重）→ 排除已 owned → 默认仅
  decided（textbook_ref + exercise_ref 引用）→ 单任务**顺序逐书**（预算逐书独立）；
  部分失败不中断，成功的书保持 owned，失败的书汇总进任务 result + 人工指引。
  五阶段编排（检索 → 确认[预筛→enrich→LLM] → 下载[候选级预算] → staging 机器验收 →
  mark_owned 登记）。
- **输入：** 路径参数 `knowledge_id`；请求体可选 `{"include_parallel": true}` — 显式纳入
  parallel_ref 引用。
- **输出：** 202 `{"task_id": "...", "knowledge_id": "..."}`；任务 result：
  `{"ok", "knowledge_id", "include_parallel", "processed": [{"book_id", "ok", "file_path"?, "skipped"?, "reason"?|"error"?}], "failed_count"}`；
  404 教程不存在；409 `TASK_ALREADY_RUNNING`（同教程已有活动任务）。
- **范例：**
  ```json
  // 请求
  {"include_parallel": false}

  // 响应 202
  {"task_id": "task_tutorial_fetch_001", "knowledge_id": "kt-mathanalysis-1"}
  ```
- **解释：** 同书/同教程 dedup 查重仅计 queued/running（失败/完成不阻塞重提）；取书语义
  详见[下载管线设计](../design/download-pipeline.md)；CLI
  `mainline download` 消费本端点并轮询。

## ⑤ 书籍与渠道

> 书库化契约（QED-050-D，2026-09-06 实现对齐；2026-09-11 QED-060 扩展）：`qt_books` 为
> 域级书库（选用四态 decided/parallel/candidate/retired + 持有态 holding owned/missing +
> 下载生命周期 downloading/downloaded/verified/failed），行内无归属列（归属由教程 refs
> 承载）；登记唯一写入口为 `mark_owned`（同时置 `status=downloaded`）；下载执行语义由
> qt_sources + 资源清单承接。旧「八态下载机」的 decide/retry/complete/reject/supersede
> 端点保持删除；**下载生命周期端点 start/fail/verify/cancel 为 2026-09-11 QED-060 新增**
> （见下方）。设计见[下载管线设计](../design/download-pipeline.md)。

### `POST /api/v1/books`

- **描述：** 书库化创建（201）：域级书库登记一本书（无 knowledge_id，归属由教程 refs 承载）。
- **输入：** 路径参数无；请求体（必填：book_id + title）：

  | 字段 | 类型 | 必填 | 说明 |
  |---|---|---|---|
  | book_id | string | 是 | 格式 `{abbr}-b{NN}`（服务端生成口径） |
  | title | string | 是 | 书名 |
  | original_title | string | 否 | 外文原版书名（支撑原版检索；无则省略） |
  | part | string | 否 | 卷标识（空串=单卷本；上册/下册；Vol.1/2/3） |
  | authors | object[] | 否 | `[{name, role}]`（role=author/translator） |
  | publisher | string | 否 | 出版社 |
  | edition | string | 否 | 版次 |
  | year | int | 否 | 出版年份（整数或 null） |
  | language | string | 否 | `zh`/`en`（zh 含中译本） |
  | roles | string[] | 否 | textbook/exercises/solutions |
  | status | string | 否 | candidate/decided/parallel/retired/downloading/downloaded/verified/failed（默认 candidate） |
  | domain_id | string | 否 | 所属领域（按域查书库用） |
  | notes | string | 否 | 备注 |

- **输出：** 201 书行（`row.to_dict()` 全列）；409 `BOOK_ALREADY_EXISTS`；
  422 `INVALID_PARAMS`（book_id 格式错误/缺 title/值域错误）。
- **范例：**
  ```json
  // 请求
  {
    "book_id": "mathanalysis-b01",
    "title": "数学分析",
    "original_title": "Principles of Mathematical Analysis",
    "authors": [{"name": "Rudin", "role": "author"}],
    "publisher": "高等教育出版社",
    "edition": "第3版",
    "year": 2006,
    "language": "zh",
    "roles": ["textbook"],
    "status": "candidate",
    "domain_id": "math"
  }

  // 响应 201
  {"book_id": "mathanalysis-b01", "title": "数学分析", "holding": "missing", "status": "candidate", "priority": null}
  ```
- **解释：** 常规书行由采纳端点（③组）自动创建（decided/parallel）；本端点供人工补录
  （默认 candidate，如论文/博客快照、手动候选）；退役（retired + retire_reason）与补书
  优先级（priority）属运营维护语义，见[数据库专用表设计](database-private-tables.md)
  qt_books 节。

### `GET /api/v1/books/{book_id}/sources`

- **描述：** 书籍的渠道列表。
- **输入：** 路径参数 `book_id`。
- **输出：** 200 渠道行数组（**含失败留痕 ok=0**，详情消费方自行过滤）；404 书籍不存在。
- **范例：**
  ```json
  [{"source_id": "src_ab12cd34", "channel": "internet_archive", "ok": true, "note": "可用", "attempted_at": "2026-09-01T08:00:00"}]
  ```
- **解释：** 成功渠道归因与渠道有效性评估的数据面（qt_sources 表，见
  [数据库专用表设计](database-private-tables.md)）；CLI `mainline channels` 全量遍历聚合同一数据。

### `POST /api/v1/books/{book_id}/sources`

- **描述：** 添加渠道记录（一次渠道尝试一条）。
- **输入：** 路径参数 `book_id`；请求体：

  | 字段 | 类型 | 必填 | 说明 |
  |---|---|---|---|
  | channel | string | 否 | manual / internet_archive / open_library / google_books / libgen_li（默认 manual） |
  | provider_id | string | 否 | 渠道内标识 |
  | page_url | string | 否 | 详情页 URL |
  | download_url | string | 否 | 下载 URL |
  | file_keywords | string | 否 | 多关键词空格分隔（人工下载检索词） |
  | ok | bool | 否 | 尝试是否成功（默认 false） |
  | note | string | 否 | 备注 |

- **输出：** 200 渠道行（创建后的记录）；404 书籍不存在。
- **范例：**
  ```json
  {"channel": "internet_archive", "provider_id": "ia-12345", "page_url": "https://...", "download_url": "https://...", "file_keywords": "filename.pdf", "ok": true, "note": "可用"}
  ```
- **解释：** 人工下载成功后补记 `channel=manual, ok=true` 留痕；失败尝试也记录
  （ok=0）供渠道评估——LLM 判断不写资源事实，资源事实只经本端点与自动下载链路落库。

### `POST /api/v1/books/{book_id}/register`

- **描述：** 原地登记（双轨[手动]）：数据根内已有文件直接登记为持有。
- **输入：** 路径参数 `book_id`；请求体 `{"relative_path": "..."}`（数据根相对路径）。
- **输出：** 200 登记结果（`mark_owned` 落 holding=owned + file_path 回填 + 渠道留痕
  `channel=local_import`）；400 路径不在数据根内/PDF 校验失败；404 `FILE_NOT_FOUND` /
  `BOOK_NOT_FOUND`；422 缺 relative_path。
- **范例：**
  ```json
  // 请求
  {"relative_path": "raw/math/math_analysis/math_analysis.pdf"}

  // 响应
  {"book_id": "mathanalysis-b01", "holding": "owned", "file_path": "raw/math/math_analysis/math_analysis.pdf"}
  ```
- **解释：** 完整性校验（魔数 + pypdf + sha256；**跳过初筛门槛**）→ `mark_owned` 唯一写
  入口；文件不移动（与 import 的 tmp 暂存落盘相对）。

### `POST /api/v1/books/{book_id}/import`

- **描述：** 人工导入（双轨[手动]，D3）：本地 PDF（可在数据根外）校验后落盘并登记持有。
- **输入：** 路径参数 `book_id`；请求体：

  | 字段 | 类型 | 必填 | 说明 |
  |---|---|---|---|
  | file_path | string | 是 | 本机源文件路径 |
  | target_path | string | 否 | 期望落盘相对路径（D9：期望路径不含 sha，落盘自动补 `_<sha8>`）；缺省经 refs 反查默认桶 `raw/<domain>/<course_id>/<safe_title>_<sha8>.pdf` |

- **输出：** 200 登记结果（`mark_owned` + 渠道留痕 `channel=local_import`）；
  400 target_path 越界/非 PDF/拷贝失败；404 `FILE_NOT_FOUND` / `BOOK_NOT_FOUND`；
  422 缺 file_path / `NO_COURSE_REF`（反查不到课程，要求显式 target_path）；
  409 `TARGET_CONFLICT`（目标已存在且不同内容，不覆盖用户文件）。
- **范例：**
  ```json
  // 请求
  {"file_path": "C:/downloads/textbook.pdf", "target_path": "raw/math/math_analysis/斯图尔特微积分.pdf"}

  // 响应
  {"book_id": "mathanalysis-b01", "holding": "owned", "file_path": "raw/math/math_analysis/斯图尔特微积分_a1b2c3d4.pdf"}
  ```
- **解释：** 完整性校验（魔数 + pypdf + sha256；**跳过初筛门槛**）→ tmp 暂存原子落盘 →
  登记；目标已存在且同 sha256 → 复用既有文件不重复落盘；resolve 后必须在数据根内。

### `POST /api/v1/books/{book_id}/fetch`

- **描述：** 书级取书（双轨[自动]，单册走完整五阶段：检索 → 确认[预筛→enrich→LLM] →
  下载[候选级预算] → staging 机器验收 → mark_owned 登记），提交后台任务。
- **输入：** 路径参数 `book_id`；无 body。
- **输出：** 202 `{"task_id": "...", "book_id": "..."}`；任务 result：
  `{"ok", "book_id", "skipped", "reason"?, "file_path"?}`；404 `BOOK_NOT_FOUND`；
  409 `BOOK_RETIRED`（retired 书不可取）/ `TASK_ALREADY_RUNNING`（同书已有活动任务）。
- **范例：**
  ```json
  // 响应 202
  {"task_id": "task_book_download_001", "book_id": "mathanalysis-b01"}
  ```
- **解释：** 已 owned → 编排层 no-op（`skipped: true`）；与教程级 fetch（④组）共用五阶段
  编排与 dedup 规则；结果经 `GET /api/v1/tasks/{task_id}` 轮询；
  CLI `books fetch <book_id>` 消费本端点。

### `POST /api/v1/books/{book_id}/start`

- **描述：** 开始下载（2026-09-11 QED-060）：`decided → downloading`。
- **输入：** 路径参数 `book_id`；无 body。
- **输出：** 200 书行全列；404 `BOOK_NOT_FOUND`；409 非法迁移（`INVALID_TRANSITION`）。
- **范例：**
  ```json
  {"book_id": "mathanalysis-b01", "status": "downloading", "holding": "missing"}
  ```
- **解释：** 五阶段编排在进入下载前内部调用；本端点供前端/人工推进状态机。
  设计见[下载管线设计](../design/download-pipeline.md)、[数据库专用表设计](database-private-tables.md)状态机节。

### `POST /api/v1/books/{book_id}/fail`

- **描述：** 标记下载失败（2026-09-11 QED-060）：`downloading → failed`（holding 仍 missing）。
- **输入：** 路径参数 `book_id`；无 body。
- **输出：** 200 书行全列；404 `BOOK_NOT_FOUND`；409 非法迁移。
- **范例：**
  ```json
  {"book_id": "mathanalysis-b01", "status": "failed", "holding": "missing"}
  ```
- **解释：** 失败后可再次提交 `fetch`（`failed → downloading`）重试。

### `POST /api/v1/books/{book_id}/verify`

- **描述：** 验收通过（2026-09-11 QED-060）：`downloaded → verified`（下载终态）。
- **输入：** 路径参数 `book_id`；无 body。
- **输出：** 200 书行全列；404 `BOOK_NOT_FOUND`；409 非法迁移。
- **范例：**
  ```json
  {"book_id": "mathanalysis-b01", "status": "verified", "holding": "owned", "file_path": "raw/math-advanced/math_analysis/数学分析_ab12cd34.pdf"}
  ```
- **解释：** 与 `mainline verify`（只读复核）区别：本端点做状态迁移，只读复核不改状态。

### `POST /api/v1/books/{book_id}/cancel`

- **描述：** 取消下载（2026-09-11 QED-060）：`downloading → decided`（复位）。
- **输入：** 路径参数 `book_id`；无 body。
- **输出：** 200 书行全列；404 `BOOK_NOT_FOUND`；409 非法迁移（仅 `downloading` 可 cancel）。
- **解释：** 用于解除卡死的 `downloading`，使书可重新取书；不删除已落盘文件。

## 错误码

| 状态码 | 含义 |
| --- | --- |
| 200 | 成功 |
| 201 | 资源创建成功 |
| 202 | 任务已接受（后台执行） |
| 400 | 请求格式错误（INVALID_PARAMS：校验失败/文件不可读/JSON 解析失败/PDF 校验失败/路径越界） |
| 404 | 资源不存在（DOMAIN_NOT_FOUND / COURSE_NOT_FOUND，及教程/书籍/文件/目录/任务的 plain-detail 404） |
| 409 | 冲突与守卫：DOMAIN_NAME_CONFLICT / COURSE_ALREADY_EXISTS / COURSE_HAS_KNOWLEDGE / DOMAIN_NOT_EMPTY / SET_NO_CONFLICT / BOOK_ALREADY_EXISTS / BOOK_RETIRED / NO_COURSE_REF / TASK_ALREADY_RUNNING / TARGET_CONFLICT / LLM_UNAVAILABLE / INVALID_TRANSITION（非法状态迁移）/ 数据库未配置 |
| 422 | 参数校验失败（缺必填字段、格式错误、值域错误） |
| 502 | 上游模型调用失败（管线错误码透传：LLM_UNAVAILABLE / BUDGET_EXHAUSTED 等） |

## 非主线端点附录

以下 7 条端点**全链路流程（评估→确认→下载→验收→登记→展示）未消费**，代码保留不删，
登记于此以对齐「主线端点 + 非主线 7 条」口径（代码路由数以 `main.py` 为准）：

| 方法/路径 | 说明 | 备注/消费方 |
| --- | --- | --- |
| `GET /api/v1/books/search` | 教材候选搜索（多来源并行，参数 q 必填、limit 1-50、source 过滤） | search 类直连端点；主线取书走五阶段编排，不经此端点 |
| `GET /api/v1/papers/search` | 论文候选搜索（arXiv；参数 q/category/author/limit） | search 类直连端点；论文链见[论文发现设计](../design/paper-discovery.md) |
| `GET /api/v1/catalogs` | 已注册目录列表（`[{"id": "math-qe"}]`） | [下载管线设计](../design/download-pipeline.md)「math-qe 冻结书单与 catalog 冻结目录链」（frozen JSON 下载清单） |
| `GET /api/v1/catalogs/{catalog_id}` | 目录详情（含全部 targets） | 同上；404 目录不存在 |
| `GET /api/v1/domains` | 领域列表（扁平视图，不含嵌套课程） | 领域维度视图；主线课程体系视图为 `GET /api/v1/courses`，领域详情为 `GET /api/v1/domains/{domain_id}`（②组） |
| `GET /api/v1/tasks` | 任务列表（全部） | 任务基础设施；主线只按 task_id 轮询 |
| `POST /api/v1/tasks/{task_type}` | 提交后台任务（202；类型 book_download/tutorial_fetch/domain_explore/domain_explore_courses/course_explore） | 任务基础设施；取书两类建议走④⑤组专用端点以获得 dedup 查重 |

## 探索阶段任务实例与目录范例

> 探索阶段已实现的 2 条端点（`POST /domains/{id}/confirm`、`POST /domains/{id}/courses/import`）
> 已并入②组六要素；本节保留任务实例与目录详情范例。

### `POST /api/v1/tasks/domain_explore_courses`

- **描述：** 提交 domain_explore_courses 后台任务（只跑 courses@v8）。
- **输入：** 请求体 `{domain_id, mode?}`。
- **输出：** 202 `{task_id}`。
- **解释：** 由 `POST /domains/{id}/confirm` 自动触发，无需手动调用。

目录详情范例（`GET /api/v1/catalogs/{catalog_id}`）：

```json
{
  "id": "math-qe",
  "name": "数学QE书单",
  "description": "...",
  "status": "frozen",
  "targets": [
    {"id": "01-rudin-zh", "course_id": "math_analysis", "course_name": "数学分析", "kind": "book", "title": "数学分析原理", "authors": ["Walter Rudin"], "query": "...", "roles": ["textbook"], "set_no": "1"}
  ]
}
```

## 外部接口（消费面）：Axiom-Flow（8902）

> 本节是 **QED-Tracker 消费 Axiom-Flow API 的接口契约**（客户端 `src/qed_tracker/axiom.py`）：
> 定义本仓库实际调用的端点、请求/响应、错误语义与交互边界。**Axiom-Flow 全量 API 的事实源在
> 其仓库**（api/main.py + docs/design/web-workbench.md），本文件只记录消费面契约，不复制全量
> 端点，避免双源漂移。跨项目事实（端口、dataset、qed 库）只链接根仓库契约。

### 实现状态

- **CLI 已实现**：`src/qed_tracker/axiom.py`（`AxiomClient`）、`src/qed_tracker/cli.py`
  `axiom push` 命令（提交与执行）、`src/qed_tracker/inventory.py`（传输记录落点）、
  `QED_AXIOM_URL` 默认 `http://127.0.0.1:8902`（`config.py`）。
- **8901 API 未暴露**：`src/qed_tracker/api/main.py` 无任何 axiom 路由。原 QED-010 规划项
  `POST /tasks/axiom/push` 未在 QED-010（已按主链路范围验收关闭，2026-09-09）中实现；
  如需 axiom 端点服务化另行立项。

### 端点契约（消费面 3 端点）

QED-Tracker 客户端（`src/qed_tracker/axiom.py`）只消费以下 3 个端点。基准地址默认
`http://127.0.0.1:8902`（由 `QED_AXIOM_URL` 配置覆盖）。

**1. GET /api/v1/health — 健康检查**

| 项 | 内容 |
| --- | --- |
| 用途 | 上传前确认 Axiom-Flow 在线 |
| 请求 | 无 |
| 响应 200 | `{"status": "ok", "version": "0.3.0"}` |
| 调用处 | `AxiomClient.health()`（`axiom push` 第一步） |

**2. POST /api/v1/documents — 上传 PDF**

| 项 | 内容 |
| --- | --- |
| 用途 | 交付已登记 PDF（multipart） |
| 请求 | `file` 字段（multipart），MIME `application/pdf`；仅接受 `.pdf` 后缀 |
| 响应 201 | `DocumentResponse`：`{id, filename, content_hash, page_count, status, created_at}` |
| 错误 | 400（非 PDF / 无法导入）、413（超过大小限制，默认 `max_upload_bytes`）、422（校验失败） |
| 幂等 | Axiom-Flow 按 PDF 内容哈希处理重复导入（返回既有文档，不重复入库） |
| 调用处 | `AxiomClient.push()`；上传前必须已找到登记资源与实际 PDF |

**3. POST /api/v1/documents/{document_id}/parse-jobs — 创建解析任务**

| 项 | 内容 |
| --- | --- |
| 用途 | 显式创建解析任务（默认不调用，仅 `--parse` 时） |
| 请求体 | `{"page_start": 1, "page_end": null}`（可选；页码从 1 开始，两端均包含；仅用户提供时出现） |
| 响应 202 | `CommandResponse`：`{"job": {...}, "created": true\|false}` |
| 错误 | 404（文档不存在）、409（非法状态）、422（校验失败） |
| 边界 | 页码上界、任务幂等、预算与人工审阅规则由 Axiom-Flow 负责，QED-Tracker 不复制或绕过 |
| 调用处 | `AxiomClient.push(parse=True)`；CLI 要求页码参数与 `--parse` 同时使用 |

**统一错误结构**：所有错误响应 `{"error": {"code": "<code>", "message": "<摘要>", "details": {...}}}`；
本仓库客户端将失败包装为 `AxiomError`（带 HTTP 状态码与 ≤500 字响应摘要）。

**全量 API 一览（事实源链接）**：Axiom-Flow `/api/v1` 还提供文档查询、解析运行、页面/知识点
审阅、工作簿、评测等 30+ 端点，本仓库不使用，对接以 Axiom-Flow 侧为准（Axiom-Flow
`docs/design/web-workbench.md` / 源码 api/main.py 与 api/schemas.py，位于 Axiom-Flow 仓库）。

### 交互规范（与 Axiom-Flow / QED-Engine）

| 边界 | 约定 |
| --- | --- |
| 端口 | Axiom-Flow 默认 `8902`（根仓库 ADR 0002；保留 8000 兼容） |
| 数据边界 | QED-Tracker 不导入 Axiom-Flow Python 包、不访问其 MySQL（`af_*` 表）、不写入其数据目录；交接只走 HTTP API |
| dataset | Axiom-Flow 解析产物指向根仓库 `dataset/axiom-flow/parsed/`（Phase 3，ALN-003）；QED-Tracker 交付 PDF（`axiom push`）见[下载管线设计](../design/download-pipeline.md) |
| qed 库 | 共享实例、表命名空间隔离（`qt_*` / `af_*` / 共享 `qed_*`），见[数据库专用表设计](database-private-tables.md)（全库表族总览） |
| 前端入口 | 8903 前端只连 8900 网关（ADR 0007），浏览器不直连 8902 |

### 传输记录（客户端行为事实）

成功上传后，本仓库将结果写入 `meta/transfers/axiom/<sha256>.json`，包含：`schema_version`、
QED `resource_id` 和 Axiom 服务 URL；Axiom `document_id`、完整文档响应和 UTC 推送时间；
显式解析成功时的 `parse_command` 响应。传输记录是下游交接状态，不得写入单资源 JSON，
也不得改变 PDF 的 `resource_id`。

### 失败语义

- 健康检查、连接、上传、服务限制或解析提交失败均返回运行错误和有限长度的 HTTP 摘要。
- 上传失败时不写成功传输记录，也不修改本地资源事实。
- 上传成功而解析提交失败时，保留 Axiom 已导入文档，将 `parse_error` 写入传输记录，然后向 CLI 返回失败。
- 工具不自动删除已上传文档，也不自动重试可能产生费用的解析任务。
- 再次推送同一资源依赖 Axiom 的内容哈希幂等语义，本项目不通过共享状态实现下游去重。
