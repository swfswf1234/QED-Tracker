# 知识录入设计（手动入口与标准答案目录）

设计状态：Accepted
实现状态：In Progress
确认状态：暂定
最后更新：2026-09-03
关联代码：`src/qed_tracker/application/knowledge_import.py`、`src/qed_tracker/db/knowledge_repository.py`、`src/qed_tracker/api/main.py`（domains/import、courses/knowledge、knowledge/{id}/confirm）、`src/qed_tracker/cli.py`（domains/knowledge import）
关联测试：`tests/test_knowledge_import.py`、`tests/test_cli_knowledge_import.py`、`tests/test_prompt_lab_api.py`（A2）
关联 ADR：[ADR 0001](../adr/0001-tracker-service-architecture.md)

> 本文档承接原 plans `2026-09-knowledge-import.md`、`2026-08-knowledge-dual-flow.md` 与
> `2026-09-qt-schema-restructure.md` 的已确认裁决，作为**手动知识入口 + docs/knowledge
> 标准答案目录**的唯一设计事实源。表结构 DDL 见[数据库设计](../architecture/database-schema.md)，
> 状态机写主体见[共享表设计](../architecture/shared-tables.md)，本文档只链接不复制。

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
> 归 QED-050-D 重规划**（下载链设计见 `docs/plans/2026-09-download-registration.md`），
> 本文档只登记其入口与登记方向；当前 `qt_books` 书库化后该组端点旧状态机已失效（见
> [实现状态与待对齐]）。

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
| 1 | 上传领域 JSON（只登记 domain，不含课程写入） | `POST /api/v1/domains/import`（无 source） | 无 → **已生成**（第一轮报告就绪） | 只 qed_domain |
| 2 | 用户确认 domain（可先 PATCH 修改） | `POST /api/v1/domains/{id}/confirm-domain` | 已生成 → **探索中**（进入第二轮） | — |
| 3 | 由领域 JSON 的 courses 写入课程 | `POST /api/v1/domains/{id}/courses/import` | 探索中 → **待确认**（第二轮报告就绪） | 只 qed_course |
| 4 | 用户确认课程名单（apply 全保留语义） | `POST /api/v1/domains/{id}/apply-results` | 待确认 → **已完成** | 领域探索管线完成 |
| 5 | 逐门课程探索（tutorials@v2） | `POST /api/v1/courses/{course_id}/prompt-explores/dry-run` + 后台 run | 课程行：→ 探索中 → 待确认 | 教程 pending |
| 6 | 用户审阅教程（确认或修改并确认） | `POST /api/v1/courses/{course_id}/apply-results` | 待确认 → **已完成** | tutorials 落库 |

- **步骤 2** 需要新增「已生成→探索中」确认端点（8900 线上写主体在手动模式不存在，由 8901 补齐）。
- **步骤 3** 需要新增课程写入端点（`/domains/{id}/courses/import`），写入即置「待确认」。
- 步骤 4 复用 `apply-results`：手动场景无"删除未选课程"语义，`selected_courses` 省略/为空 =
  全部保留。
- 步骤 5-6 复用现有课程探索 dry-run + apply-results。

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
| 书籍组端点（register/import/decide/start/fail/retry/complete/verify/reject/supersede/cancel/fetch） | 旧八态下载机契约（qt_books 书库化后失效） | 归 QED-050-D 重规划，本文档不再描述 |
| `import_domain` 落地范围 | 写 domain+courses、`source` 语义 | 六步流程（步骤 1 只写 domain，courses 由步骤 3 写） |
| template.json | 旧契约 + 文件名含零宽字符 | 数据文件版契约范本，干净文件名 |

## 关联文档

| 文档 | 关系 |
| --- | --- |
| [探索管线设计](exploration-pipeline.md) | 自动轨（LLM）与手动轨共用同一状态机 |
| [共享表设计](../architecture/shared-tables.md) | 6 态状态机写主体、写权限例外（唯一事实源） |
| [数据库设计](../architecture/database-schema.md) | qed_domain/qed_course/qt_knowledge/qt_books DDL 与 ID 规则 |
| [架构 API](../architecture/api.md) | domains/import、courses/knowledge、knowledge/confirm 端点定义 |
| [探索管线设计](exploration-pipeline.md) 基线 | 标准答案数据为探索产出对照基准 |
