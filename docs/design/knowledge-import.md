# 知识录入设计（手动入口与标准答案目录）

设计状态：Accepted
实现状态：Implemented
确认状态：已确认
最后更新：2026-09-11
关联代码：`src/qed_tracker/application/knowledge_import.py`、`src/qed_tracker/application/domain_file.py`（domains.json/courses.json/tutorials.json 读写层）、`src/qed_tracker/db/knowledge_repository.py`（含 `tutorial_name` 命名函数与 `adopt_tutorials` 先查后建幂等）、`src/qed_tracker/api/main.py`（domains/import、domains/{id}/confirm 双分支、domains/{id}/courses/import、courses/knowledge、knowledge/{id}/confirm）、`src/qed_tracker/cli.py`（domains/knowledge import、mainline new/review 命名路径）
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
- **手动轨**：人工整理 JSON 后经 API/CLI 导入，**跳过 LLM 探索直接给答案**（confirm 含
  courses 分支 / courses/import 捷径可零 LLM 消耗推进到审阅点），但**流程
  语义仍走 LLM 探索流程**（同状态机、同审阅阶段），仅"答案来源"不同。

手动轨适用于：已有标准答案知识目录的领域（如 math-advanced）、人工整理的课程体系、
外部 PDF 直接导入。

## 三种手动入口

| 模式 | API 端点 | CLI 命令 | 写入表 | 来源标记 |
| --- | --- | --- | --- | --- |
| 领域 JSON 导入 | `POST /api/v1/domains/import` | `qed-tracker domains import <json>` | 不直接写表（只落 `raw/{domain_id}/domains.json` + 置**已生成**，经 confirm 双分支后写库，见六步流程） | `—`（source 参数已退役） |
| 课程 JSON 导入 | `POST /api/v1/courses/{course_id}/knowledge` | `qed-tracker knowledge import <json>` | qt_knowledge + qt_books | `source=manual` |
| 书籍 PDF 导入 | `POST /api/v1/books/{book_id}/import` | `qed-tracker books import <id> <path>` | qt_books + qt_sources | `channel=local_import` |

> 书籍 PDF 导入属于下载链（PDF 校验、sha256 去重、拷入数据根、渠道留痕），**下载执行语义
> 由[下载管线设计](download-pipeline.md)承载**（2026-09-04 确认晋升：
> 五阶段下载链，检索→确认→下载→机器验收→登记；人工导入跳过下载与初筛门槛，保留
> 完整性校验，与自动路径汇合同一登记服务）。本文档只登记其入口与登记方向；书籍组端点
> 已按 QED-050-D 重接线（见「实现状态与待对齐」书籍组行）。
>
> **落盘一致性（2026-09-11 QED-061）**：课程 JSON 导入（`POST /courses/{course_id}/knowledge`）
> 与 LLM 探索轨写**同一课程知识文件** `raw/<domain_id>/<course_id>/tutorials.json`——
> 导入时按采纳结果幂等覆盖，课程目录不存在则创建；完成后（`已完成`）该文件即课程定稿知识
> JSON。领域导入 `domains.json` 的完成后反写见[探索管线设计](exploration-pipeline.md)
> 「已完成落盘收口」。
>
> **dataset JSON 例外（2026-09-11 REQ-078）**：上述知识 JSON（`domains.json`/`tutorials.json`，
> 及中间态 `courses.json`）落 `raw/` 是根仓库 dataset 契约「dataset 内不维护 JSON 状态事实源」
> 的**例外**——状态事实源仍在 DB，JSON 只作知识正本与重导入输入；根侧口径见
> [dataset 约定](../../../docs/design/dataset-conventions.md)「探索产物 JSON 例外」。

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
    {"course_id": "math_analysis", "name": "数学分析", "track": "分析学",
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
- **course_id 命名规则（2026-09-11 更新）**：`course_id` 的**唯一事实源 = 领域标准答案**
  （`docs/knowledge/<domain>.json` 的 `courses[].course_id`），统一为**有意义的英文语义 slug**
  （小写字母/数字/下划线，禁连字符，如 `math_analysis`、`linear_algebra`、`probability`、
  `ordinary_differential_equations`）。**不再使用编号前缀**（旧 `01_math_analysis`、
  `11_probability` 退役）。冻结目录 `catalogs/math-qe.json` 的 `course_id` 与知识标准答案
  逐字对齐并重新冻结；扩展课程同样用语义 slug（`abstract_algebra`、`complex_analysis`）。
  LLM 探索报告输出的 course_id 只是**提案**（dry-run 预览），不构成事实；
  `apply-results` 落库以人工选定为准，与标准答案对齐时采用标准答案 ID（避免两套 ID 并存）。
- **domain_id 命名规则（2026-09-11 更新）**：`domain_id` 为有意义的英文语义 slug
  （小写字母/数字/连字符/下划线，如 `math-advanced`、`computer-science`）。生成优先级：
  ① 调用方显式提供；② ASCII 名称机械 slug 化；③ **中文名等无法派生时返回 422 要求显式提供**
  （不再用 `d_<md5>` 兜底）。

## 课程 JSON 契约（数据文件版，2026-09-03 用户裁决）

`docs/knowledge/<domain>/<course_id>.json` 同构。**数据文件版**：顶层为
`domain_id`/`course_id`/`course_name`，每套教程显式携带生成好的
`knowledge_id`（`kt-{abbr}-{set_no}`）与 `textbook_ref[].book_id`（`{abbr}-b{NN}`）：

```json
{
  "domain_id": "math-advanced",
  "course_id": "math_analysis",
  "course_name": "数学分析",
  "tutorials": [
    {
      "knowledge_id": "kt-mathanalysis-1",
      "kind": "tutorial",
      "set_no": "1",
      "name": "教程1：比廷杰《微积分及其应用》",
      "position": "beginner",
      "intro": "…120~字散文…",
      "textbook_ref": [
        {"book_id": "mathanalysis-b01", "title": "微积分及其应用", "part": "",
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

## ID 生成规则（文件显式 + LLM 机械生成，2026-09-11 更新）

| 路径 | 来源 | 规则 |
| --- | --- | --- |
| 手动导入 | 文件显式携带 | 服务端校验格式（`kt-{abbr}-{set_no}` / `{abbr}-b{NN}`）并做重复检测，直接落库 |
| LLM 探索采纳（A2 adopt） | 服务端生成 | `course_abbr` 按下方规则机械生成；book_id 域内 `max+1` 递增 |

- **course_abbr 规则（2026-09-11 裁决，全名 + 超长缩略）**：
  - `course_abbr = course_id` 去下划线（`math_analysis`→`mathanalysis`、`linear_algebra`→
    `linearalgebra`、`probability`→`probability`）；
  - 当去下划线后长度 **> 20** 时，改用**词首字母缩略**（acronym）：
    `ordinary_differential_equations`→`ode`、`partial_differential_equations`→`pde`、
    `data_structures_and_algorithms`→`dsa`、`machine_learning_basics`→`mlb`；
  - 缩略须保证同域内唯一；`knowledge_id`/`book_id` 总长须 ≤ 列宽 32。
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

## 手动六步流程（API 与 CLI 同路径）

手动录入复用 LLM 探索状态机（线性链路，与[探索管线设计](exploration-pipeline.md)两轮时序一致）；
**API 路径**需要 `已生成` 与 `待确认` 两极（分别对应第一轮/第二轮待确认点，用户可修改再确认）；
**CLI 路径**同样经 8901 走同一流程（CLI 直接定稿语义与 `source=cli` 已退役，见「CLI 语义」）：

| 步 | 触发 | 端点 | 状态转移 | 写表 |
| --- | --- | --- | --- | --- |
| 1 | 上传领域 JSON（只落盘，不含课程写入） | `POST /api/v1/domains/import`（无 source） | 无 → **已生成**（第一轮报告就绪） | 写 domains.json |
| 2 | 用户确认 domain（可先 PATCH 修改） | `POST /api/v1/domains/{id}/confirm`（双分支） | 含 courses → **待确认**（task_id=null）；不含 → **探索中**（异步 courses@v8） | 含 courses 分支写 courses.json |
| 3 | 课程名单就绪（两条到达路径） | a) 轮询 `GET /api/v1/tasks/{task_id}`；b) 捷径 `POST /api/v1/domains/{id}/courses/import` | 探索中 → **待确认** | 写 courses.json（捷径分支） |
| 4 | 用户确认课程名单（apply 全保留语义） | `POST /api/v1/domains/{id}/apply-results` | 待确认 → **已完成** | 领域探索管线完成 |
| 5 | 逐门课程探索（tutorials@v2） | `POST /api/v1/courses/{course_id}/prompt-explores/dry-run` + 后台 run | 课程行：→ 探索中 → 待确认 | 教程 pending |
| 6 | 用户审阅教程（确认或修改并确认） | `POST /api/v1/courses/{course_id}/apply-results` | 待确认 → **已完成** | tutorials 落库 |

- **步骤 1**：`POST /domains/import` 写入 `raw/{domain_id}/domains.json`，不直接写库
  （领域须已存在，不存在 → 404 DOMAIN_NOT_FOUND）。
- **步骤 2（confirm 双分支）**：读取 `raw/{domain_id}/domains.json` → upsert domain 后分派：
  - **含 `courses`** → 直接写 `raw/{domain_id}/courses.json` + 置 `待确认` + `task_id=null`
    （手动导入零 LLM 消耗直达第二轮审阅点）；
  - **不含 `courses`** → 异步提交 courses@v8 任务 + 置 `探索中` + 返回 `task_id` 供轮询。
- **步骤 3（两条到达路径）**：
  - a) 轮询 `GET /tasks/{task_id}` 等 courses@v8 完成；完成后写 `raw/{domain_id}/courses.json`，置 `待确认`；
  - b) 手动捷径 `POST /domains/{id}/courses/import` 直接写课程名单 JSON（守卫：仅 `已生成`/`探索中`
    可调，非法状态 → 409；JSON 无课程 → 400 INVALID_PARAMS）。
- **步骤 4**：复用 `apply-results`：手动场景无"删除未选课程"语义，`selected_courses` 省略/为空 =
  全部保留；落库前把 `courses.json` 幂等同步进 `qed_course`（courses_kept=0 事故的根因修复）。
  **完成后落盘收口（2026-09-11 QED-061）**：领域 `已完成` 时把最终保留课程反写进
  `raw/{domain_id}/domains.json` 并删除 `courses.json`（细则见
  [探索管线设计](exploration-pipeline.md)「已完成落盘收口」）。
- **步骤 6**：课程 `已完成` 时按最终保留集合就地定稿
  `raw/{domain_id}/{course_id}/tutorials.json`（回填 `knowledge_id`/`book_id`）。
- 步骤 5-6 复用现有课程探索 dry-run + apply-results。

### 与 LLM 探索路径的差异

| 维度 | LLM 探索 | 手动导入 |
| --- | --- | --- |
| courses@v8 来源 | LLM 生成 | 用户提供的 JSON（confirm 含 courses 分支 / courses/import 捷径可整段跳过 courses@v8） |
| 审阅轮数 | 两轮（domain + courses） | 两轮（同 LLM） |
| 状态转移 | 8900 驱动 | 8901 端点驱动 |

## CLI 语义（与 API 同路径，经 8901）

- `qed-tracker domains import <json>`：本地 `validate_domain` → `POST /domains/import`
  （请求体 `{"domain": data}`，**无 source 参数**）→ 只写 `raw/{domain_id}/domains.json` +
  置领域 `exploration_stage=已生成`；后续经 `domains confirm <domain_id>` 走 confirm 双分支。
  （CLI 一次定稿语义与 `source=cli` 已退役，2026-09-09。）
- `qed-tracker knowledge import <json>`：本地 `validate_course`（数据文件版契约）→
  `POST /courses/{id}/knowledge`（`source=manual`）→ 按 refs 幂等建 decided/parallel 书行并
  回填 `book_id`；仍为 draft 的套逐套 `POST /knowledge/{id}/confirm` 定稿，已确认套跳过，
  重放可续（导入即确认+书库就绪）。

## docs/knowledge 标准答案目录（正本契约）

```
docs/knowledge/
├── <domain>.json                    # 领域 JSON（manual@v1）
├── computer-science.json            # 领域 JSON（3 主干方向 + 7 门基础/主干课）
└── math-advanced/
    ├── template.json                # 课程 JSON 契约范本（数据文件版，空占位）
    ├── math_analysis.json
    ├── linear_algebra.json
    ├── probability.json
    └── ...
```

- 该目录是**标准答案数据**（探索产出的对照基准），作为 `qed_domain`/`qed_course`/`qt_knowledge`/
  `qt_books` 的事实输入，**不参与文档导航治理**（见[文档治理规范](../standards/doc-governance.md)）。
- `math-advanced.json` 12 门课程（四档 + kind）、`computer-science.json` 5 门（LLM 时代语境），
  实际课程清单以文件为准。
- 契约守护：`test_knowledge_import.py` 的文档合规测试遍历并校验这些文件。
- 下载（PDF 落盘）由下载链 QED-050-D 承接：refs 只登记 `book_id`/元数据，`file_path` 由
  `qt_books.holding=owned` + `file_path` 在下载登记时填充。

## 实现状态与待对齐（Phase 2 清单，2026-09-09 收口）

原 Phase 2 待对齐项已全部落地：

| 项 | 收口结果 |
| --- | --- |
| course 校验器契约 | 已实现数据文件版 `validate_course`（`domain_id`/`course_id`/`course_name` + 显式 `knowledge_id`/`book_id`，`tests/test_knowledge_import.py` 守护） |
| 手动导入的审阅链 | 已按六步流程实现：`confirm` 双分支 + `courses/import` 手动捷径 + `GET /domains/{id}`/`GET /courses/{domain_id}` 确认视图（QED-050-D 联调接线） |
| 书籍组端点（register/import/decide/start/fail/retry/complete/verify/reject/supersede/cancel/fetch） | **已实现（2026-09-06，QED-050-D；2026-09-11 QED-060 扩展）**：书级/教程级 fetch 与 import/register 重接线（[下载管线设计](download-pipeline.md)），旧八态端点 decide/retry/complete/reject/supersede 删除，start/fail/verify/cancel 4 个以新语义恢复（下载生命周期），契约见[架构 API](../architecture/api.md) ⑤ 组 |
| `import_domain` 落地范围 | 已对齐：`POST /domains/import` 只写文件 + 置已生成，courses 由 confirm 双分支/`courses/import` 写（`source` 参数退役） |
| template.json | 已是数据文件版契约范本（`docs/knowledge/math-advanced/template.json`，干净文件名，`test_knowledge_docs_courses_conform_to_contract` 守护） |

残余跟踪：8901 全链路真实环境冒烟与联调收口已随 QED-010/QED-014 验收关闭（2026-09-09，见[完成台账](../trackers/completed.md)）。

## 关联文档

| 文档 | 关系 |
| --- | --- |
| [探索管线设计](exploration-pipeline.md) | 自动轨（LLM）与手动轨共用同一状态机 |
| [下载管线设计](download-pipeline.md) | 书籍 PDF 导入的下载执行语义（唯一事实源） |
| [数据库共享表设计](../architecture/database-shared-tables.md) | 状态机写主体（领域 6 态 / 课程 5 态）、写权限例外（唯一事实源） |
| [数据库专用表设计](../architecture/database-private-tables.md) | qt_knowledge/qt_books DDL 与 ID 规则（qed_domain/qed_course 见共享表设计） |
| [架构 API](../architecture/api.md) | domains/import、courses/knowledge、knowledge/confirm 端点定义 |
| [探索管线设计](exploration-pipeline.md) 基线 | 标准答案数据为探索产出对照基准 |
| [教程命名规范设计（已归档）](../history/baselines/2026-08-tutorial-naming.md) | 已并入本文档「教程命名规范」节（2026-09-07，ADR 0008） |

## 变更记录

| 日期 | 变更 | 说明 |
| --- | --- | --- |
| 2026-09-11 | 补课程知识 JSON 落盘一致性（QED-061） | 手动/采纳路径与 LLM 探索轨写同一 `raw/<domain>/<course>/tutorials.json`；领域反写见探索管线设计 |
| 2026-09-09 | 六步流程与 CLI 语义对齐实现 + Phase 2 收口 | 流程表写入 confirm 双分支与 `courses/import` 捷径；CLI `domains import` 语义改为经 8901 同流程（`source=cli` 退役）；Phase 2 清单五项全部收口，实现状态转 Implemented |
| 2026-09-07 | 并入教程命名规范（ADR 0008） | 自 tutorial-naming.md 并入命名格式、mainline 命名路径、前端展示边界与决策登记；书籍下载链接改指 download-pipeline.md |
