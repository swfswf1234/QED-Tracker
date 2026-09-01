# 教材探索与下载：手动+自动双轨 + 知识体系梳理（QED-043 联动）

状态：Draft（待用户评审后按 ADR 0003 迁 design/）
最后更新：2026-08-29
任务类型：Plan
需求方：QED-Tracker 内部（用户审定）；探索语义与根仓库 REQ-064/065 对齐；QED-043 长期任务联动
关联文档：[prompt 优化模块设计](2026-08-prompt-optimization.md)（Accepted）、[下载流程现状分析与优化方向](2026-08-download-flow.md)（Current）、[QED-Engine 探索对齐承接设计](../history/baselines/2026-08-engine-exploration-alignment.md)（已归档）、[API 设计](2026-08-api-design.md)（Draft）、[shared-tables](../architecture/shared-tables.md)（Accepted）、根仓库 [探索下载全流程计划](../../../docs/plans/2026-08-27-exploration-download-flow.md)
关联任务：todo 本计划行（新 QED-050）、[QED-043](../trackers/todo.md)（prompt 优化），QED-047/048（dry-run/采纳端点已实现）

## 一、目标与成功标准

将「领域、课程、教程、书目确定 + 下载导入系统」从纯自动（LLM）扩展为**手动+自动双轨**，
两条轨道共用同一状态机链路（qt_knowledge / qt_books），并通过前端（根仓库 8903/8900）按流程同步驱动。
同时按用户裁定重构领域知识语义（QED-043 联动），并把「标准答案」知识沉淀为 `docs/knowledge/` 下的独立文件。

成功标准：

1. `docs/knowledge/<domain>.json`（领域标准答案）+ `docs/knowledge/<domain>/{course_id}.json`（每课程一个）建立，数学（`math-advanced`）为第一份正本；
2. 手动探索链路跑通：领域 JSON 导入写 qed_domain/qed_course；课程 JSON 导入走 A2 建 qt_knowledge draft；
3. 手动下载链路跑通：本地 PDF 路径导入 → 校验 → 拷入数据根 → qt_books downloaded；
4. QED-043 语义升级落地：stage 四档【基础/主干/分支/前沿】、classic_tracks 带 kind（main/branch）、entry_requirements 一句话；
5. 全量门禁（pytest + ruff + test_documentation.py）全绿。

## 二、关键用户裁定（2026-08-29 生效）

| # | 裁决 | 内容 |
|---|---|---|
| D1 | 实现方案 A | 薄壳导入层 + 复用现有能力；手动/自动共用 qt_knowledge/qt_books 状态机同一链路；前端按流程同步实现（前端侧在根仓库） |
| D2 | 手动探索录入粒度 | 分两段：领域导入=仅写共享表（qed_domain/qed_course）；课程导入=复用 A2（draft 态），人工按确认→书籍→下载流程走 |
| D3 | 手动下载语义 | 外部路径导入 + 数据根内登记：`POST /books/{id}/import`，本地 PDF（可在数据根外）→ 校验 → 拷贝入数据根 → 登记 downloaded |
| D4 | 接口形态 | API + CLI 双形态；CLI 命令组 `domains import` / `knowledge import` / `books import` 分别挂现有命令组 |
| D5 | classic_tracks 结构 | 每项加 `kind`（`main`=主干方向 / `branch`=分支方向）；数学四条主线（分析学/代代数/概率与统计/几何与拓扑）均为 main |
| D6 | entry_requirements | 由字符串数组改为**一句话字符串**（如「高中数学全部内容扎实」） |
| D7 | stage 四档统一 | `TIERS` 与 `qed_course.stage`、`qed_domain.stages` 统一为【基础/主干/分支/前沿】；论文驱动内容归「前沿」；tier 不再作为独立层级轴 |
| D8 | 领域导入后域状态 | `qed_domain.exploration_stage = 已完成`（人工探索定稿语义）；courses 保持「未开始」（课程层由后续流程推进） |
| D9 | 课程 JSON 书目路径 | `target_path` 为期望落盘路径标准答案（`raw/<domain>/<course>/…`）；导入落盘以其为准，登记时回写真实相对路径校验 |
| D10 | 离线直连模式 | 第一轮不做（不经 API 直读写 DB），M6 真实验证后按需加 |

## 三、总体图景（双轨同链路）

```
探索轨                                                 下载轨
┌ 自动：LLM dry-run → 勾选采纳 ┐                   ┌ 自动：fetch 任务（搜索→候选→下载）┐
│  DomainPipeline/CoursePipeline│                  │  BookService + DownloadManager    │
│  → A2 → qt_knowledge(draft)   │                  │  → qt_books(downloaded)           │
└──────────────────────────────┘                   └─────────────────────────────────┘
┌ 手动：JSON→校验→导入 ─────────┐                  ┌ 手动：本地PDF→校验→拷入数据根→登记 ┐
│  领域JSON→qed_domain/course    │                  │  POST /books/{id}/import           │
│  课程JSON→A2(draft)            │                  │  → qt_books(downloaded)            │
└──────────────────────────────┘                   └─────────────────────────────────┘
       汇合点: qt_knowledge(confirmed) + qt_books(candidate/decided)
                             │
                             用户「决定」→「开始下载」（自动 fetch 或 手动 import 均可）
                             │
                             qt_books(downloaded) → verify → complete
                             │
                             knowledge(completed) → qed_course.exploration_stage = 已完成（G2 修复）
```

两轨唯一差异在「候选书籍如何产生 + 文件如何进入数据根」；**登记、去重、校验、状态机、验收全部复用**。

### 3.1 探索流程时序（教材角度）

```
自动轨（LLM 辅助）                                    手动轨（知识录入）
───────────────                                       ──────────────────
① POST /prompt-explores/dry-run                       ① 人工整理领域 JSON → docs/knowledge/<domain>.json
   （DomainPipeline domain@v3→courses@v5→path@v5）      ② POST /domains/import（校验器 manual@v1 校验）
   报告返回（确认弹窗流可携 confirm_name_override）           → qed_domain(+stages/classic_tracks/…)
                                                             + qed_course×N（courses[] → upsert）
                                                             domain.exploration_stage=已完成（D8）
② POST /courses/{id}/prompt-explores/dry-run           ③ 人工整理课程 JSON → docs/knowledge/<domain>/<course>.json
   （CoursePipeline tutorials@v1）                       ④ POST /courses/{id}/knowledge（A2，source=manual）
   推荐套列表（2~4 套）                                     → qt_knowledge(draft)×套（含 textbook_ref/exercise_ref）
   用户在 8900 侧勾选（≤4 上限）                             用户审阅 draft
┌────────────────────────── 汇合 ──────────────────────────┐
⑤ 用户「确认」：qt_knowledge(draft→confirmed)，按决定引用自动建 qt_books(candidate) 书籍
└──────────────────────────────────────────────────────────┘
⑥ 用户「决定」：qt_books(candidate→decided) → 进入下载轨
```

### 3.2 下载流程时序（教材角度）

```
自动轨（渠道搜索）                                       手动轨（本地文件）
───────────────                                         ──────────────────
① POST /books/{id}/fetch（202→task_id）                 ① 人工下载 PDF（任意路径，可在数据根外）
   → loading 搜索（title+authors，limit=8）               ② POST /books/{id}/import
   → 逐候选（600s 预算看门狗）                               {file_path, target_path?}
   → DownloadManager 下载（重试+退避+PDF 校验）                → inspect_pdf（魔数+页数）
   → add_source(channel, ok=...) 留痕                     → sha256 去重（命中复用）
   → complete_download 或 fail_download                    → 拷入数据根 raw/<domain>/<course>/（target_path 为准，
   （失败→人工指引：候选链接清单）                              _<sha8> 命名规则补足）
→ qt_books(downloaded) | failed                          → Inventory 登记 + 建书籍
                                                         → add_source(channel=local_import) 留痕
                                                         → qt_books(downloaded)
┌────────────────────────── 汇合 ──────────────────────────┐
③ 用户「验收」：qt_books(downloaded→verified)
④ 套内全部书籍 verified → qt_knowledge(completed)（聚合）
⑤ knowledge complete → qed_course.exploration_stage=已完成（G2 修复，本批补实现）
└──────────────────────────────────────────────────────────┘
```

## 四、QED-043 语义升级（M1）

### 4.1 stage 四档统一（D7）

| 档位 | 语义 | 归属 |
|---|---|---|
| 基础 | 入门基石课 | 无先修或浅先修的学科奠基课 |
| 主干 | 方向主干课 | 某主干方向的必修核心 |
| 分支 | 方向细分/拓展课 | 主干方向的专门化分支 |
| 前沿 | 研究前沿/论文驱动 | 以论文、研究前沿为主的内容（含 papers kind） |

- `templates.py` `TIERS = ("基础", "主干", "分支", "前沿")`（原（基础/进阶/核心/冲刺）退役）；
- `path@v4 → v5`：tier 值域与解释同步；graph TD 分组沿用 tier；
- `qed_domain.stages` 值域 `["基础","主干","分支","前沿"]`；`qed_course.stage` 取值于它；
- `courses@v4 → v5`：track 必须取 classic_tracks 中 `kind=main` 的方向名。

### 4.2 classic_tracks 带 kind（D5）

- `domain@v2 → v3`：classic_tracks 每项 `{name, summary, kind}`；当前领域 2~4 个 main；
- 分支方向（kind=branch）作为未来扩展方向预留，可承载 extensions_planned 的归置。

### 4.3 entry_requirements 一句话（D6）

- `domain@v2 → v3`：entry_requirements 由 `_str_list`（数组）改为 `_text`（单字符串）；
- 语义：入门起点一句话描述。示例「高中数学全部内容扎实」。

### 4.4 版本升级清单

| 模板 | 版本 | 变更 |
|---|---|---|
| domain-explore/domain | v2→v3 | classic_tracks 带 kind；entry_requirements 单值；文案解释主干/分支 |
| domain-explore/courses | v4→v5 | track 限定 kind=main；无 stage 输出（在 path 步分配） |
| domain-explore/path | v4→v5 | TIERS 四档替换；tier 解释更新 |
| course-explore/tutorials | v1（不动） | 课程教材探索不涉 tier/stage |
| priors.py | 无版本 | tracks_hint 文案同步「四条主干方向」 |

## 五、docs/knowledge/ 知识目录（M2）

### 5.1 目录布局

```
docs/knowledge/
├── math-advanced.json                    # 领域标准答案（2026-08-29 自 plans/domain-math-advanced.json 迁入，
│                                         #   domain_id=math-advanced，含四档 stages + tracks kind）
└── math-advanced/                        # 按领域划分的课程结果（每课程一个文件）
    ├── 01_math_analysis.json
    ├── 02_linear_algebra.json
    └── 11_probability.json
```

> 2026-08-29 用户裁决：原「domains/ 扁平 + courses/ 扁平」方案作废，改为领域文件放 `docs/knowledge/` 根、
> 课程 JSON 放领域同名子目录 `docs/knowledge/<domain>/`。旧正本（`docs/plans/`、`docs/guides/` 两份
> `domain-math-advanced.json`）已删除，knowledge/ 为新正本（git 历史保留）。

### 5.2 领域 JSON 契约（manual@v1，校验器守护）

```json
{
  "domain": "math-advanced",
  "name": "数学（高等数学）",
  "scope": "大学以上数学专业课程，以数学系课程体系为准",
  "description": "…（两句：经典定性 + 研究/学习范围与分界）",
  "level": "本科-硕士",
  "entry_requirements": "高中数学全部内容扎实",
  "classic_tracks": [
    {"name": "分析学", "summary": "…", "kind": "main"},
    {"name": "代数学", "summary": "…", "kind": "main"},
    {"name": "概率与统计", "summary": "…", "kind": "main"},
    {"name": "几何与拓扑", "summary": "…", "kind": "main"}
  ],
  "stages": ["基础", "主干", "分支", "前沿"],
  "anchor_courses": ["数学分析", "高等代数", "概率论与数理统计"],
  "courses": [
    {"slug": "mathematical_analysis", "name": "数学分析", "track": "分析学",
     "stage": "基础", "aliases": ["微积分", "Analysis"], "summary": "…", "prerequisites": []}
  ],
  "extensions_planned": []
}
```

要点：
- `domain` 为领域标识（对应 qed_domain.domain_id，`math-advanced`）；`stages` 显式列出四档（qed_domain.stages）；
- `courses[].stage` 逐门人工定档（见 5.4）；`track` 取值于 classic_tracks 的 main 方向；
- `anchor_courses`（基石课清单）保留（自原 domain-math-advanced.json）；
- 本契约与 LLM 模板契约（domain@v3 输出）同源但**独立**：手动文件经轻量校验器，LLM 输出经 `validate`。

### 5.3 课程 JSON 契约（课程导入输入；兼容 golden 范本）

```json
{
  "meta": {"contract": "course-knowledge/manual@v1", "confirmed_at": "…", "purpose": "…"},
  "domain": "math-advanced",
  "course": {"course_id": "01_math_analysis", "name": "数学分析", "aliases": []},
  "tutorials": [
    {
      "set_no": "1",
      "set_name": "教程1：斯图尔特微积分（Stewart）",
      "textbook": {"title": "斯图尔特微积分", "original_title": "Calculus: Early Transcendentals",
                   "authors": ["Stewart"], "version": {"edition": "第九版（图灵数学经典，上下册）",
                   "publisher": "人民邮电出版社", "year": 2025},
                   "roles": ["textbook", "exercises"], "position": "beginner",
                   "intro": "…", "target_path": "raw/math-advanced/01_math_analysis/斯图尔特微积分.pdf"},
      "exercise": null,
      "reason": "…"
    }
  ]
}
```

要点：
- 结构与 A1/golden `tutorials[i]` 同构（可直接转换为 A2 body 的 tutorials 数组）；
- `target_path` 为**期望落盘相对路径**（D9），附加于 textbook/exercise；A2 采纳时透传进 textbook_ref/exercise_ref（ref 为开放 JSON）；
- **target_path 格式（2026-08-29 用户裁定）**：基础名**不含 sha 后缀**（如 `raw/math-advanced/01_math_analysis/斯图尔特微积分.pdf`）——
  保证知识文件稳定、不依赖文件内容；导入落盘时按数据根命名规则补 `_<sha8>`（与 ResourceService 命名一致）；
- 多套通过 set_no 区分（1~4 中文套 / en 英文套）。

### 5.4 逐门人工定档清单（M2 知识梳理裁决点）

对 `docs/knowledge/math-advanced.json` 12 门课按 stage 四档逐门定档（2026-08-29 用户确认按建议表执行）：

| 课程（slug） | 原 stage | 定档 |
|---|---|---|
| mathematical_analysis | 基础 | 基础 |
| advanced_algebra | 基础 | 基础 |
| probability_and_mathematical_statistics | 基础 | 基础 |
| abstract_algebra | 进阶 | 主干 |
| ordinary_differential_equations | 进阶 | 主干 |
| complex_analysis | 进阶 | 主干 |
| real_analysis | 进阶 | 主干 |
| point_set_topology | 进阶 | 主干 |
| partial_differential_equations | 进阶 | 分支 |
| functional_analysis | 进阶 | 分支 |
| stochastic_processes | 进阶 | 分支 |
| differential_geometry | 进阶 | 分支 |

（12 门=3 基础 + 5 主干 + 4 分支；「前沿」留给论文/研究方向课，extensions_planned 中的方向课届时按前沿或分支判定。）

## 六、手动探索链路（M4/M5，D2/D4）

### 6.1 领域导入

**`POST /api/v1/domains/import`**（body：`{"domain": {...}}` 或 `{"file_path": "..."}`）
- 校验：轻量校验器（manual@v1 schema）——检查 domain/name/classic_tracks(kind)/stages/courses(stage∈stages, track∈main)；
- 落库：domain 存在→更新维护字段（description/level/scope/stages/classic_tracks/entry_requirements 对应列）；不存在→创建；
  courses 逐条 upsert（slug→course_id）；`exploration_stage=已完成`（D8）；courses=未开始；
- 冲突：course 已存在且关键字段异 → 409；幂等：同键同值 → 更新（no-op）返回既有；
- **字段映射缺口（2026-08-29 落实）**：`entry_requirements`/`anchor_courses`/`extensions_planned`
  为文件侧知识，qed_domain **无对应列**（共享表不加列，避免跨项目迁移）→ 校验通过但不落库，
  保留在 docs/knowledge 正本；`courses[].summary` → qed_course.description；
- 响应：`{"domain_id": "math", "courses_updated": N, "courses_created": N}`。

CLI：`qed-tracker domains import <json-path>`（读文件→构造 body→调 8901 API→打印报告；无 API 时错误提示走 D10 后续）。

### 6.2 课程导入（复用 A2）

**`POST /api/v1/courses/{course_id}/knowledge`**（`source: "manual"` → 修为 `manual`）
- 现状已支持 adopt（A2，`adopt_tutorials`），本轮仅扩校验：
  - `source` 值域 `explore`（默认）/ `manual`，非法值 422；来源标记透传不落列（qt_knowledge 无 source 列）；
  - **roles 强制（2026-08-29 落地增强，全来源）**：textbook.roles 必须含 `textbook`；
    exercise 非 null 时 roles 必须含 `exercises`；
  - **target_path 全量透传**：textbook/exercise 为全量 dict 透传进 ref（`dict(textbook)` 保留
    target_path，D9）；手动导入落盘与登记回写由它驱动；
- 状态机：draft 起点不变；用户 confirm 自动建书籍（既有行为）。

CLI：`qed-tracker knowledge import <course-json>`（读文件→validate_course→调 A2（source=manual））。
**导入即定稿（2026-08-31 行为变更，QED-050 手动轨）**：采纳后对新建/仍 draft 的套逐套
`POST /knowledge/{id}/confirm`（显式回传 JSON 里的 refs/双 intro——confirm 空 body 会以 `{}`
覆盖预填 refs，须防），并按 refs 幂等 `POST /books` 建 candidate 册（textbook/exercise 各一，
同名册不重复建行）；已 confirmed/completed 的套跳过确认、仍补册，重放可续。CLI 路径直达
「已确认+候选册就绪」，前端/API 路径维持 draft→确认接口→已确认不变（D2 状态机不变）。

## 七、手动下载链路（M6，D3）

**`POST /api/v1/books/{book_id}/import`**（body：`{"file_path": "...", "target_path": "..."?}`）

流程（复用既有能力，零重复状态机逻辑）：
1. `file_path` 解析（本地绝对/相对路径，可在数据根外）；找不到 → 404；
2. `inspect_pdf`（魔数 `%PDF` + 页数阈值）异常 → 400；
3. sha256 全文计算；`repo.complete_download` 同哈希命中既有书籍 → 复用（不重复落文件）；
4. 目标路径解析：优先 `target_path`（D9；基础名不含 sha → 落盘自动补 `_<sha8>`），缺省规则
   `raw/<domain_id>/<course_id>/<safe_name>_<sha8>.pdf`；强制 `resolve` 后 `relative_to(data_root)`（越界 → 400）；
5. 外部文件 → 先写 tmp 暂存（`downloads_tmp_dir`）→ `os.replace` 原子落盘 raw/；数据根内为目标位置 → 原地登记（不移动）；
6. `repo.complete_download(book_id, sha256, relative_path, page_count, …)`（candidate→downloaded 直转）；
7. `repo.add_source(channel="local_import", ok=True, download_url=…, note="手工导入")` 留痕。

> **登记口径**：本端点与既有 `POST /books/{id}/register` 对齐——只登记 qt_books + qt_sources；
> Inventory（meta/resources JSON）双轨登记属 REQ-032 课题，本批不引入（避免双轨漂移）。

错误：400 路径越界/非 PDF | 404 文件不存在/书籍不存在 | 409 sha256 冲突/状态非法 | 422 缺参。

CLI：`qed-tracker books import <book_id> <file_path> [--target raw/...]`。

> **G2 修复顺带**：knowledge complete（聚合）时回写 `qed_course.exploration_stage = 已完成`（当前 `complete_knowledge` 仅置 knowledge 行，缺回写）。

## 八、实施顺序

| 阶段 | 内容 | 验收 |
|---|---|---|
| M1 | QED-043 语义升级（3 模板 v+1 + priors + 契约测试更新） | 相关单测全绿 |
| M2 | 知识梳理：math-advanced.json 重整理（5.2/5.4）+ 3 课程 JSON（5.3，含 target_path）；旧正本（plans/guides）删除、golden 引用同步 | 与契约交叉校验（test_documentation + 校验器冒烟） |
| M3 | 流程文档两篇（本研究设计文档为依据；探索/下载两条时序入本目录） | 索引/todo 登记 |
| M4 | 领域导入链（校验器 + POST /domains/import + CLI domains import） | 单测 + CLI 冒烟 |
| M5 | 课程导入链（A2 manual 校验扩展 + CLI knowledge import） | 单测 + CLI 冒烟 |
| M6 | 手动下载链（POST /books/{id}/import + CLI books import + Inventory 衔接；G2 回写修复） | 单测 + 真实文件冒烟 |
| M7 | api.md/api-design/shared-tables/main-line-curriculum 同步 + test_documentation 白名单 + todo 登记 + 全量门禁 | pytest + ruff + test_documentation.py 全绿 |

### 实现记录（2026-08-29，M1~M7 完成）

| 工作项 | 实现 | 测试 |
|---|---|---|
| M1 | templates.py domain@v3/courses@v5/path@v5 + TIERS 四档 + priors tracks_hint；pipeline 跨步校验 track 限 main | test_prompt_lab.py 契约更新（+kind/单值/四档用例），27+ 用例 |
| M2 | docs/knowledge/math-advanced.json（12 门四档 + kind）+ 3 课程 JSON（target_path）；旧正本删除、golden/progress 文档引用同步 | test_knowledge_import.py 正本合规测试 ×2 |
| M3 | 探索/下载双轨时序入本文档 §三.1/§三.2 | — |
| M4 | `application/knowledge_import.py`（validate_domain/validate_course）+ `POST /domains/import` + CLI `domains import` | test_knowledge_import.py（校验器参数化 + API 契约 + 正本合规） |
| M5 | A2 source 值域/roles 强制扩展 + CLI `knowledge import` | 同上（source/manual 3 用例） |
| M6 | `POST /books/{id}/import`（外部路径→暂存→原子落盘→登记+留痕）+ CLI `books import`；**G2 修复**：complete_knowledge 全教程 completed 回写 course.exploration_stage | 同上（import 6 用例 + G2 1 用例） |
| M7 | api.md / api-design（④ A4 + ⑧ 语义）/ shared-tables（kind+四档）/ main-line-curriculum（标注）/ README 同步；test_documentation 白名单 ± | 白名单 2 行 |

门禁：**402 passed + 3 skipped + ruff clean + test_documentation.py 全绿**（362 → 402，+40 用例）。

**移交（用户确认后提交）**：本批改动日志见 git diff；CLI 冒烟对运行中的 8901（旧版本）返回
405 Method Not Allowed——属预期（新端点待服务重启生效），验证请重启 `qed-tracker serve`。

### 第二轮：计算机范本（2026-08-29 追加，QED-050 延续）

用户裁决：domain_id=computer-science；接口方案=复用既有 dry-run 端点（mode=text+ref_text），
AI 自主判断课程数量。

| 工作项 | 实现 | 测试 |
|---|---|---|
| M-A courses@v6 | courses@v5→v6（_validate_courses 下限 4→3，适配精炼探索场景） | test_prompt_lab.py：3 门通过/2 门拒绝 |
| M-B 计算机先验 | priors.py `DOMAIN_PRIORS["计算机科学与技术"]`（三主干方向/命名规范/anchor/level/capstone 大模型） | test_prior_computer_science_registered |
| M-C 计算机范本 | `docs/knowledge/computer-science.json`：3 条 main 方向 + 5 门基础/主干课（程序设计基础/数据结构与算法/计算机组成与体系结构/操作系统/机器学习基础） | test_knowledge_docs_computer_science_conforms |

前端测试 payload 示例：
`POST /api/v1/prompt-explores/dry-run` `{"domain_name": "计算机科学与技术", "mode": "text", "ref_text": "现在是AI时代，需要基于最新的科技状况来学习，首先是计算机基础要打牢，其次是LLM相关知识要追逐前沿，现在开始探索，假设是大学开始学习的这个阶段"}`

> **O1 开放问题（本批不修，待裁决）**：`docs/knowledge/math-advanced.json` 课程 slug
> （mathematical_analysis 等）与既有 `qed_course.course_id`（01_math_analysis 等，catalog NN_slug
> 对齐）不一致——`domains import` 时 slug 直作 course_id 会另建 13 行重复课程。处置选项：
> ① 知识文件 courses[] 增 `course_id` 字段（与 catalog 对齐，导入优先用它）；② 导入时按
> aliases/命名映射表复用既有行；③ 数学领域不接受导入、计算机领域（无冲突）先行。

## 九、边界事项与待办（用户知会）

| # | 事项 | 处置 |
|---|---|---|
| B1 | stage 值域变更（qed_domain.stages / main-line-curriculum 示例）跨仓库共享表语义 | **已同步（2026-08-29）**：shared-tables.md（kind+四档）/ main-line-curriculum.md（历史留档标注）；**待**：根仓库知会（值域变更属共享表契约） |
| B2 | 前端（8903/8900）「按流程同步实现」属根仓库侧 | 本批只保端点契约稳定（A1/A2 既有 + domains/import + books/import）并与 api-design 同步；回执根仓库 |
| B3 | 领域导入 qed_domain 多字段（scope/path_results 等）写权限：导入属本仓库（写权限方），天然合规 | 不越 8900 直写例外范围 |
| B4 | 领域正本位置 | **已落实（2026-08-29）**：`docs/knowledge/math-advanced.json` 为新正本；旧副本 `docs/plans/domain-math-advanced.json`、`docs/guides/domain-math-advanced.json` 已删除（git 历史保留）；golden JSON meta 引用已同步 |
| B5 | 离线直连模式（D10） | 第一轮不做，M6 后按需评估 |

## 十、回滚

- 本计划前期为文档轮（无代码回滚面）；后端点为新增（domains/import、books/import），回滚=移除路由注册；A2 校验扩展为增量。
- 知识文件（M2）为新增文件，回滚=删除对应文件；模板版本升级（M1）经 git 历史保留旧版。

## 十一、开发环境备注（执行注意）

- 测试/门禁运行环境：**conda 环境 `qed_env`**（Python ≥3.12，项目 `requires-python = ">=3.12"`）。
  系统默认 `python`（anaconda base 3.10.9）**不能**运行本仓库测试/安装（版本不满足，且 `qed_tracker` 未安装）。
- 运行方式：`conda run -n qed_env python -m pytest …`；若需安装包用 `conda run -n qed_env python -m pip install -e ".[dev]"`。
- 已注意：用 `python -m pip install -e ".[dev]"`（base 3.10）会因版本约束失败或超时，切勿在 base 环境执行。

---
*本文档为流程梳理 + 设计正文（ADR 0003：Draft 随计划在 plans/ 承载）；确定后迁 `docs/design/`。实现顺序：模板语义升级（M1）→ 知识整理（M2）→ 手动链路（M4~M6）。*
