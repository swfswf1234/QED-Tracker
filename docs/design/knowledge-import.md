# 知识录入设计（手动入口与标准答案目录）

设计状态：Accepted
实现状态：In Progress
确认状态：已确认
最后更新：2026-09-07
关联代码：`src/qed_tracker/application/knowledge_import.py`、`src/qed_tracker/db/knowledge_repository.py`（含 `tutorial_name` 命名函数与 `adopt_tutorials` 先查后建幂等）、`src/qed_tracker/api/main.py`（domains/import、courses/knowledge、knowledge/{id}/confirm）、`src/qed_tracker/cli.py`（domains/knowledge import、mainline new/review 命名路径）
关联测试：`tests/test_knowledge_import.py`、`tests/test_cli_knowledge_import.py`、`tests/test_prompt_lab_api.py`（A2）、`tests/test_main_line_cli.py`（mainline 命名）、`tests/test_knowledge_repository.py` 与 `tests/test_knowledge_api.py`（教程命名规范）
关联 ADR：[ADR 0001](../adr/0001-tracker-service-architecture.md)、[ADR 0008](../adr/0008-design-doc-scope-reshuffle.md)

> 本文档承接原 plans `2026-09-knowledge-import.md`、`2026-08-knowledge-dual-flow.md` 与
> `2026-09-qt-schema-restructure.md` 的已确认裁决，作为**手动知识入口 + docs/knowledge
> 标准答案目录**的唯一设计事实源。qt_* 表结构 DDL 见
> [数据库专用表设计](../architecture/database-private-tables.md)，qed_* 共享表契约与状态机
> 写主体见[数据库共享表设计](../architecture/database-shared-tables.md)，本文档只链接不复制。

## 目的与边界

QED-050 设计手动+自动双轨知识获取：
- **自动轨**：LLM 探索管线（见[探索管线设计](exploration-pipeline.md)）。
- **手动轨**：人工整理 JSON 后经 API/CLI 导入，**跳过 LLM 探索直接给答案写库**，但**流程
  语义仍走 LLM 探索流程**（同状态机、同审阅阶段），仅"答案来源"不同。

手动轨适用于：已有标准答案知识目录的领域（如 math-advanced）、人工整理的课程体系、
外部 PDF 直接导入。

## 三种手动入口

| 模式 | API 端点 | CLI 命令 | 写入表 | 来源标记 |
| --- | --- | --- | --- | --- |
| 领域 JSON 导入 | `POST /api/v1/domains/import` | `qed-tracker domains import <json>` | qed_domain（可含 qed_course，见六步流程） | `source=manual` |
| 课程 JSON 导入 | `POST /api/v1/courses/{course_id}/knowledge` | `qed-tracker knowledge import <json>` | qt_knowledge + qt_books | `source=manual` |
| 书籍 PDF 导入 | `POST /api/v1/books/{book_id}/import` | `qed-tracker books import <id> <path>` | qt_books + qt_sources | `channel=local_import` |

> 书籍 PDF 导入属于下载链（PDF 校验、sha256 去重、拷入数据根、渠道留痕），**下载执行语义
> 由[下载管线设计](download-pipeline.md)承载**（2026-09-04 确认晋升：
> 五阶段下载链，检索→确认→下载→机器验收→登记；人工导入跳过下载与初筛门槛，保留
> 完整性校验，与自动路径汇合同一登记服务）。本文档只登记其入口与登记方向；书籍组端点
> 已按 QED-050-D 重接线（见「实现状态与待对齐」书籍组行）。

## 领域 JSON 契约（manual@v1）

`docs/knowledge/<domain>.json` 同构，由 `validate_domain` 校验（契约守护：
`test_knowledge_docs_domain_conforms_to_contract`）：

```json
{
  "domain": "math-advanced",
  "name": "数学（高等数学）",
  "description": "...",
  "level": "本科",
  "scope": "...",
  "entry_requirements": "一句话",
  "classic_tracks": [{"name": "分析学", "summary": "...", "kind": "main"}],
  "stages": ["基础", "主干", "分支", "前沿"],
  "anchor_courses": ["数学分析"],
  "courses": [
    {"course_id": "01_math_analysis", "name": "数学分析", "track": "分析学",
     "stage": "基础", "aliases": [], "summary": "...", "prerequisites": []}
  ]
}
```

- `domain` 须匹配 slug 规则（小写字母/数字/下划线/连字符，`^[a-z0-9][a-z0-9_-]{1,62}$`）。
- `classic_tracks` 最多 4 个方向，`kind`= `main`（主干）/ `branch`（分支）。
- `stages` 四档 `基础/主干/分支/前沿`。
- `courses[].track` 须逐字取自 classic_tracks（或为空）；`stage` ∈ stages；`prerequisites`
  引用须为本批课程、无自环/循环。
- 可选 `extensions_planned`（扩展规划）。
- **course_id 命名规则（2026-09-03 确定）**：`course_id` 的**唯一事实源 = 领域标准答案**
  （`docs/knowledge/<domain>.json` 的 `courses[].course_id`），分两类：
  - **catalog 对齐课程**：沿用冻结目录 `catalogs/math-qe.json` 的编号式 slug
    （`01_math_analysis`、`02_linear_algebra`、`11_probability`…，O1 决议对齐）；
  - **扩展课程**：语义 slug（小写字母/数字/下划线，禁连字符，如 `abstract_algebra`、
    `complex_analysis`）。
  LLM 探索报告输出的 course_id 只是**提案**（dry-run 预览），不构成事实；
  `apply-results` 落库以人工选定为准，与标准答案对齐时采用标准答案 ID（避免两套 ID 并存）。

## 课程 JSON 契约（数据文件版，2026-09-03 用户裁决）

`docs/knowledge/<domain>/<course_id>.json` 同构。**数据文件版**：顶层为
`domain_id`/`course_id`/`course_name`，每套教程显式携带生成好的
`knowledge_id`（`kt-{abbr}-{set_no}`）与 `textbook_ref[].book_id`（`{abbr}-b{NN}`）：

```json
{
  "domain_id": "math-advanced",
  "course_id": "01_math_analysis",
  "course_name": "数学分析",
  "tutorials": [
    {
      "knowledge_id": "kt-01ma-1",
      "kind": "tutorial",
      "set_no": "1",
      "name": "教程1：比廷杰《微积分及其应用》",
      "position": "beginner",
      "intro": "…120~字散文…",
      "textbook_ref": [
        {"book_id": "01ma-b01", "title": "微积分及其应用", "part": "",
         "authors": [{"name": "比廷杰", "role": "author"}, {"name": "杨奇", "role": "translator"}],
         "publisher": "机械工业出版社", "edition": "原书第8版", "year": 2006,
         "language": "zh", "roles": ["textbook", "exercises"]}
      ],
      "exercise_ref": null,
      "parallel_ref": null
    }
  ]
}
```

- 字段级规则（对齐 LLM 模板 `validate` 与导入校验器 `validate_course`）：
  - `set_no`：1~4 中文套 / `en` 英文对照 / 空串=资料归类行（0=other_material 顺序行）。
  - `position` 五档：`beginner/intermediate/advanced/comprehensive/elective`。
  - `intro`：120 字以上套级散文（是什么/为何选/学什么/怎么学/提及平行读物）。
  - `textbook_ref`：非空数组，多卷各一条；`exercise_ref` 为 `null` 或数组（roles 须含
    `exercises`）；`parallel_ref` 为 `null` 或数组。
  - ref 条目字段：`title`（≤256）、`part`（受控：空串/上册/下册/Vol.1~3）、
    `authors`（结构化 `[{name, role:"author|translator"}]`，非空）、`publisher`/`edition`、
    `year`（整数或 null）、`language`（`zh`/`en`）、`roles`（`textbook`/`exercises`/`solutions`）。
- `test_knowledge_import.py::test_knowledge_docs_courses_conform_to_contract` 遍历
  `docs/knowledge/math-advanced/*.json`（含 `template.json` 契约范本）守护本契约。

## ID 生成规则（文件显式 + LLM 机械生成，2026-09-03 裁决）

| 路径 | 来源 | 规则 |
| --- | --- | --- |
| 手动导入 | 文件显式携带 | 服务端校验格式（`kt-{abbr}-{set_no}` / `{abbr}-b{NN}`）并做重复检测，直接落库 |
| LLM 探索采纳（A2 adopt） | 服务端生成 | abbr = `course_id` 去下划线（`01_math_analysis`→`01mathanalysis`，≤32 列宽安全）；book_id 域内 `max+1` 递增 |

- **格式**：`knowledge_id = kt-{course_abbr}-{set_no}`；`book_id = {course_abbr}-b{NN}`
  （NN 域内全局递增序号，按 `domain_id` 分组）。
- **幂等键**：knowledge = (course_id, kind, set_no)；book = (title, part, language, edition)。
- 命中复用既有行；同 set_no 被不同教程占用 → `AdoptionConflict`（API 409）。
- 不再维护"课程缩写人工映射表"：手动路径由数据文件自带，LLM 路径用机械规则。

## A2 采纳语义（adopt_tutorials，新契约）

`POST /api/v1/courses/{course_id}/knowledge`（`source` ∈ `explore`/`manual`，仅作来源标记）：

- 每套建 **draft** 教程行，预填 `set_no/name/position/intro/textbook_ref/exercise_ref/parallel_ref`；
- `textbook_ref`/`exercise_ref` → 建 `status=decided` 书行 + 回填 `book_id`；
  `parallel_ref` → 建 `status=parallel` 书行；
- 幂等：同 course_id+kind+set_no 命中复用；单事务批量提交；
- 错误码：404 COURSE_NOT_FOUND / 409 SET_NO_CONFLICT / 422 INVALID_PARAMS。

## 教程命名规范（tutorials@v2，QED-036）

> **决策登记（2026-08-20 评审定案，QED-036 实现完成）**：
> 1. **方案 A**：`textbook_ref` 扩展为 `{title, version, authors}`，命名规则成为纯函数
>    `tutorial_name(set_no, title, authors)`（只依赖教程自身，draft 期即可生成规范名）；
> 2. `mainline new` 增 `--set-no`（有则规范名，否则保持原始 title）；`mainline review` 增
>    `--title/--author`（缺省从规范名剥离「教程{set_no}：」前缀与（作者）后缀回退）；
> 3. 改名后幂等键兼容：按 `(course, kind, set_no)` 先查后建（knowledge_id 含 name，
>    重放不产生重复行）。幂等键现由 `adopt_tutorials` 承接；`migrate` 命令与存量迁移脚本
>    已随旧三表路径退役删除（QED-050-D Phase 6）。

> **决策登记（2026-09-03 tutorials@v2）**：name 格式变更为「教程{set_no}：{首作者}《{书名}》」
> （作者在前、书名在后、书名号包裹），与新 JSON 模板对齐。旧格式「教程{set_no}：{书名}（{作者}）」
> 退役。

> **决策登记**：2026-08-18 根仓库用户裁决（ARCH-015 前端重构 D5）：教程命名由 QED-Tracker
> 数据侧统一，前端原样展示；name 为空时前端兜底「教程{set_no}」（前端已实现）。本规范只定
> 数据侧命名，不涉及前端展示逻辑。

对 `kind=tutorial` 的教程（命名默认生成路径，`name` 列仍允许人工覆盖）：

| set_no | 命名格式 | 示例 |
| --- | --- | --- |
| "1"~"4"（中文套） | `教程{set_no}：{首作者}《{书名}》` | `教程1：Rudin《数学分析原理》` |
| "en"（英文对照套） | `教程en：{首作者}《{书名}》` | `教程en：Rudin《Principles of Mathematical Analysis》` |
| ''（空，异常/资料行） | `教程：{首作者}《{书名}》` | 兜底，不鼓励出现 |

- 对 `kind=other_material`（课程延展资料归类）：**不加「教程N」前缀**，保持归类名
  （如 `01-数学分析-延展资料`）。
- 书名/作者取自**教材决定引用**（`textbook_ref`）或该套教材书籍；无作者信息时省略
  （作者部分），退化为 `教程{set_no}：{书名}`。
- 命名落点：采纳路径（`adopt_tutorials`）经 `tutorial_name` 生成规范名幂等落行；
  CLI `mainline new` 有 `--set-no` 时按规范生成（否则保持 title，draft 期命名人工可改名）。
- 真实 MySQL 冒烟（2026-08-20）完成存量 01 数学分析 3 行 `name` 修正并经 8901
  `GET /knowledge` 透出（当时格式「书名（作者）」，2026-09-03 起按 tutorials@v2 新格式
  生成）；证据归档 [QED-036 证据目录](../history/qed-036-tutorial-naming/index.md)。

## confirm 简化

`POST /api/v1/knowledge/{knowledge_id}/confirm`：自身不带 body，`draft → confirmed` +
回填 `confirmed_at`。`reject/supersede/complete` 端点已删除（两态后无此语义，废弃改
`notes` 记录）；课程完成由导入/apply-results 层管理，不在教程行冗余。

## knowledge 详情 books 由 refs 聚合（2026-09-03 裁决）

`GET /api/v1/knowledge/{knowledge_id}` 的 `books[]` 不再按 `knowledge_id` 查书库（qt_books 已
无该列），改为从 `textbook_ref[]`/`exercise_ref[]`/`parallel_ref[]` 内的 `book_id` 聚合展示。

## 手动六步流程（API 路径含两态，CLI 跳过）

手动录入复用 LLM 探索状态机（线性链路，与[探索管线设计](exploration-pipeline.md)两轮时序一致）；
**API 路径**需要 `已生成` 与 `待确认` 两极（分别对应第一轮/第二轮待确认点，用户可修改再确认），
**CLI 路径**跳过这两极直接推进：

| 步 | 触发 | 端点 | 状态转移 | 写表 |
| --- | --- | --- | --- | --- |
| 1 | 上传领域 JSON（只登记 domain，不含课程写入） | `POST /api/v1/domains/import`（无 source） | 无 → **已生成**（第一轮报告就绪） | 写 JSON 文件 |
| 2 | 用户确认 domain（可先 PATCH 修改） | `POST /api/v1/domains/{id}/confirm` | 已生成 → **探索中**（异步提交 courses@v8） | — |
| 3 | courses@v8 完成（后台任务） | `GET /api/v1/tasks/{task_id}`（轮询） | 探索中 → **待确认** | 写 courses.json |
| 4 | 用户确认课程名单（apply 全保留语义） | `POST /api/v1/domains/{id}/apply-results` | 待确认 → **已完成** | 领域探索管线完成 |
| 5 | 逐门课程探索（tutorials@v2） | `POST /api/v1/courses/{course_id}/prompt-explores/dry-run` + 后台 run | 课程行：→ 探索中 → 待确认 | 教程 pending |
| 6 | 用户审阅教程（确认或修改并确认） | `POST /api/v1/courses/{course_id}/apply-results` | 待确认 → **已完成** | tutorials 落库 |

- **步骤 1**：`POST /domains/import` 写入 `raw/{domain_id}/domains.json`，不直接写库。
- **步骤 2**：`POST /domains/{id}/confirm` 读取 JSON → upsert domain + 异步提交 courses@v8 任务 →
  返回 `task_id` 供轮询；状态变为 `探索中`。
- **步骤 3**：轮询 `GET /tasks/{task_id}` 等待 courses@v8 完成；完成后写入
  `raw/{domain_id}/courses.json`，状态变为 `待确认`。
- **步骤 4**：复用 `apply-results`：手动场景无"删除未选课程"语义，`selected_courses` 省略/为空 =
  全部保留。
- 步骤 5-6 复用现有课程探索 dry-run + apply-results。

### 与 LLM 探索路径的差异

| 维度 | LLM 探索 | 手动导入 |
| --- | --- | --- |
| courses@v8 来源 | LLM 生成 | 用户提供的 JSON |
| 审阅轮数 | 两轮（domain + courses） | 两轮（同 LLM） |
| 状态转移 | 8900 驱动 | 8901 端点驱动 |

## CLI 语义（跳过已生成/待确认）

- `qed-tracker domains import <json>`：本地 `validate_domain` → `POST /domains/import`
  （`source=cli`）→ 一次写 domain + courses，置领域 `exploration_stage=已完成`。
- `qed-tracker knowledge import <json>`：本地 `validate_course` → `POST /courses/{id}/knowledge`
  （`source=manual`）→ 对每套 draft 自动 `confirm` 至 `confirmed`（含 refs 数组），并按 refs
  建候选册（导入即确认+建候选册）。

## docs/knowledge 标准答案目录（正本契约）

```
docs/knowledge/
├── <domain>.json                    # 领域 JSON（manual@v1）
├── computer-science.json            # 领域 JSON（3 主干方向 + 7 门基础/主干课）
└── math-advanced/
    ├── template.json                # 课程 JSON 契约范本（数据文件版，空占位）
    ├── 01_math_analysis.json
    ├── 02_linear_algebra.json
    ├── 11_probability.json
    └── ...
```

- 该目录是**标准答案数据**（探索产出的对照基准），作为 `qed_domain`/`qed_course`/`qt_knowledge`/
  `qt_books` 的事实输入，**不参与文档导航治理**（见[文档治理规范](../standards/doc-governance.md)）。
- `math-advanced.json` 12 门课程（四档 + kind）、`computer-science.json` 5 门（LLM 时代语境），
  实际课程清单以文件为准。
- 契约守护：`test_knowledge_import.py` 的文档合规测试遍历并校验这些文件。
- 下载（PDF 落盘）由下载链 QED-050-D 承接：refs 只登记 `book_id`/元数据，`file_path` 由
  `qt_books.holding=owned` + `file_path` 在下载登记时填充。

## 实现状态与待对齐（Phase 2 清单）

| 项 | 当前 | 目标 |
| --- | --- | --- |
| course 校验器契约 | `validate_course` 期望 `{domain, course{course_id,name}}` | 数据文件版（`domain_id`/`course_id`/`course_name` + 显式 `knowledge_id`/`book_id`） |
| 手动导入的审阅链 | 导入→已生成；apply-results 需待确认（断链） | 按本文档六步流程（新增步骤 2/3 端点） |
| 书籍组端点（register/import/decide/start/fail/retry/complete/verify/reject/supersede/cancel/fetch） | 旧八态下载机契约（qt_books 书库化后失效） | **已实现（2026-09-06，QED-050-D）**：书级/教程级 fetch 与 import/register 重接线（[下载管线设计](download-pipeline.md)），9 个旧八态端点删除，契约见[架构 API](../architecture/api.md) ④ 组 |
| `import_domain` 落地范围 | 写 domain+courses、`source` 语义 | 六步流程（步骤 1 只写 domain，courses 由步骤 3 写） |
| template.json | 旧契约 + 文件名含零宽字符 | 数据文件版契约范本，干净文件名 |

## 关联文档

| 文档 | 关系 |
| --- | --- |
| [探索管线设计](exploration-pipeline.md) | 自动轨（LLM）与手动轨共用同一状态机 |
| [下载管线设计](download-pipeline.md) | 书籍 PDF 导入的下载执行语义（唯一事实源） |
| [数据库共享表设计](../architecture/database-shared-tables.md) | 6 态状态机写主体、写权限例外（唯一事实源） |
| [数据库专用表设计](../architecture/database-private-tables.md) | qt_knowledge/qt_books DDL 与 ID 规则（qed_domain/qed_course 见共享表设计） |
| [架构 API](../architecture/api.md) | domains/import、courses/knowledge、knowledge/confirm 端点定义 |
| [探索管线设计](exploration-pipeline.md) 基线 | 标准答案数据为探索产出对照基准 |
| [教程命名规范设计（已归档）](../history/baselines/2026-08-tutorial-naming.md) | 已并入本文档「教程命名规范」节（2026-09-07，ADR 0008） |

## 变更记录

| 日期 | 变更 | 说明 |
| --- | --- | --- |
| 2026-09-07 | 并入教程命名规范（ADR 0008） | 自 tutorial-naming.md 并入命名格式、mainline 命名路径、前端展示边界与决策登记；书籍下载链接改指 download-pipeline.md |
