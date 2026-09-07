# 数据库专用表设计（qt_knowledge / qt_books / qt_sources / qt_tasks / qt_selections）

设计状态：Accepted
实现状态：Implemented
确认状态：暂定
最后更新：2026-09-07
需求方：QED-Engine（根仓库 REQ-026/REQ-029/REQ-030；2026-08-16 用户裁决知识层次重构）
关联代码：`src/qed_tracker/db/models.py`、`src/qed_tracker/db/schema.py`、`src/qed_tracker/db/knowledge_repository.py`、`src/qed_tracker/db/selection_repository.py`、`src/qed_tracker/db/tasks_repository.py`
关联测试：`tests/test_db_models.py`、`tests/test_knowledge_repository.py`、`tests/test_knowledge_api.py`、`tests/test_schema.py`、`tests/test_schema_mysql_smoke.py`（实现轮同步更新）
关联架构：[数据库共享表设计](database-shared-tables.md)（`qed_*` 共享表族唯一事实源：DDL/列语义/写权限/Schema 变更流程）
关联 ADR：[ADR 0001](../adr/0001-tracker-service-architecture.md)、
[ADR 0006](../adr/0006-database-model-as-schema-rebuild.md)（模型即 schema + 重建式自愈，Alembic 退役）、
[ADR 0007](../adr/0007-database-docs-split-by-table-family.md)（按表族拆分与 DDL 展示统一）；
根仓库 [ADR 0003](../../../docs/history/adr/v0.1/0003-shared-qed-database-independence.md)（命名空间隔离）与
[ADR 0009](../../../docs/history/adr/v0.1/0009-shared-qed-tables.md)（2026-08-16：新增 qed_* 共享表族）

> **事实源声明（ADR 0007）**：本文件是 qed 库五张项目专用表（`qt_*`）的**设计文档唯一事实源**
> ——DDL、列语义、状态机与本项目中的作用均以本文件为准，并承载全库表清单与五层模型链路图。
> 实施事实源为 ORM 模型 `src/qed_tracker/db/models.py`（ADR 0006：模型即 schema，
> `ensure_schema` 启动自愈，表/列中文注释事实源 = 模型 `comment=`）；本文 DDL 为设计展示
> （行尾 `--` 注释、comment 不换行、表名/用途在代码块外），与模型 `comment=` 解耦。
> **确认状态：暂定**——转正评审由 QED-044 收口。共享表（`qed_*`）契约见
> [数据库共享表设计](database-shared-tables.md)，本文不重复。

## 背景与动机

原三表模型（qt_selections / qt_downloads / qt_sources，QED-028，已退役）存在以下缺口：

1. **缺领域/课程层次**：领域（subject）只存在于 `courses/math.json` 静态 JSON，课程体系元数据
   （阶段/先修/别名）不在 DB，三项目无法共享；
2. **缺指引检索的简介**：教材/习题集简介（用于指引后续候选检索）无处存放；
3. **缺审计字段**：无 `created_by` / `updated_by`；
4. **不承载论文/博客**：论文走 arXiv 下载 + `meta/resources/` JSON（kind=paper），MySQL 无索引；
   博客（课程延展资料）完全不在模型内；
5. **粒度错位**：qt_selections 一条=一套书，「套」与「候选/决定/下载/验证」四段进度混杂，
   多卷教材靠 vols JSON 表达，下载与验收入口在 qt_downloads 跨表。

2026-08-16 用户裁决：**重构为「领域 → 课程 → 教程（教程/资料归类）→ 书籍 → 渠道」五层模型**，
领域/课程表为三项目共享（新前缀 `qed_*`），书籍一行=一册/一卷/一个快照（取消册行表），
文件命名「物理名/展示名」分离，存量数据一次性迁移，旧表退役。

2026-09-03 用户裁决（QED-050-B/C）：**qt_books 书库化重构**——取消知识表外键
（knowledge_id），域级书库多对多引用；下载执行态与哈希/来源移交 qt_sources + 资源清单；
选用状态（decided/parallel/candidate/retired）与持有状态（owned/missing）解耦；
qt_knowledge 精简为两态（draft/confirmed），三段简介合并为套级散文 intro。

2026-09-04 用户裁决（QED-050-D）：**书库化 DDL 落地（迁移 0018 无条件重建）**——两表当前为空，
不保数据、不做旧结构探测；qt_books 增 `original_title` 可空列（外文原版书名，支撑原版检索，
裁决 5）；qt_sources 存量保留（MySQL 挂起 FK 检查后重建，FK 对新表自愈）。

## 表族总览（全库 7 张在用表）

```
qed_domain（领域，共享 qed_*）
  └── qed_course（课程，共享 qed_*）
        └── qt_knowledge（教程，qt_* 私有：一套教程 / 一组课程延展资料）
              └── qt_books（书库：域级书库，一册/一本书，选用状态+持有状态+补书优先级）
                    └── qt_sources（渠道尝试，一次一条）
qt_tasks（后台任务，qt_* 私有：一行一个后台任务记录）
qt_selections（论文选择报告，qt_* 私有：一行一个选择报告，论文链专用）
```

共享表（`qed_domain` / `qed_course` / `qed_llm_calls`）的 DDL 与契约见
[数据库共享表设计](database-shared-tables.md)；本文件维护五张 `qt_*` 专用表。

| 表 | 中文表名 | 所有权 | 一行= | 状态 |
| --- | --- | --- | --- | --- |
| `qt_knowledge` | 教程表 | QED-Tracker 私有 | kind=tutorial：一套教程；kind=other_material：课程延展资料归类 | 在用（2026-09-03 两态重构；ADR 0006 起随模型重建） |
| `qt_books` | 书库表 | QED-Tracker 私有 | 一册/一本书的选用状态与持有状态，承载补书优先级 | 在用（2026-09-03 书库化重构；ADR 0006 起随模型重建） |
| `qt_sources` | 渠道表 | QED-Tracker 私有 | 一次渠道尝试 | 在用（外键挂 book_id） |
| `qt_tasks` | 任务表 | QED-Tracker 私有 | 一个后台任务记录（REQ-032） | 在用 |
| `qt_selections` | 论文选择报告表 | QED-Tracker 私有 | 一个论文选择报告（REQ-032，替代 meta/selections/ JSON） | 在用 |

> 表/列中文注释（ADR 0006 起）：事实源为 ORM 模型 `comment=`（建表即带），
> `ensure_schema` 重建/补建的表随模型自带注释。本文各表 SQL 尾行 `COMMENT='...'`
> 即该表的中文表介绍（与模型一致）。

---

## qt_knowledge 表结构（表1，私有）

**表名**：qt_knowledge（教程表）。**用途**：登记一套教程或一组课程延展资料，承载套级简介与
教材/习题集/平行读物引用数组，引导资源检索与补书决策；knowledge_id 由服务端确定性生成。
**一行 =** 一套教程（kind=tutorial）或一组课程延展资料归类（kind=other_material）。

```sql
CREATE TABLE qt_knowledge (
  knowledge_id  VARCHAR(32)  NOT NULL, -- PK：kt-{课程缩写}-{set_no}，服务端生成，幂等
  course_id     VARCHAR(32)  NOT NULL, -- FK → qed_course.course_id；索引
  kind          ENUM('tutorial','other_material') NOT NULL DEFAULT 'tutorial', -- 教程类型：一套教程 / 延展资料归类
  set_no        VARCHAR(4)   NOT NULL DEFAULT '', -- 套标记（见列说明）
  name          VARCHAR(128) NOT NULL DEFAULT '', -- 教程名「教程N：作者《书名》」；资料归类行用分类名
  position      ENUM('beginner','intermediate','advanced','comprehensive','elective') NOT NULL, -- 学习阶段（套级五档，见列说明）
  intro         TEXT         NOT NULL, -- 套级简介（散文，六要素，120~350 字，见列说明）
  textbook_ref  JSON         NOT NULL, -- 教材引用数组（见列说明）
  exercise_ref  JSON         DEFAULT NULL, -- 习题集引用数组；NULL=教材自含习题
  parallel_ref  JSON         DEFAULT NULL, -- 平行读物引用数组；服务端据此建 parallel 书行
  status        ENUM('draft','confirmed') NOT NULL DEFAULT 'draft', -- 审阅状态两态；索引
  confirmed_at  DATETIME     DEFAULT NULL, -- 人工定稿时间（draft → confirmed 时回填）
  notes         TEXT         DEFAULT NULL, -- 审阅备注或退役说明（废弃/拆分/合并时记录原因与去向）
  created_at    DATETIME     NOT NULL, -- 创建时间（首次导入时写入）
  updated_at    DATETIME     NOT NULL, -- 最后更新时间（定稿/编辑/退役时更新）
  PRIMARY KEY (knowledge_id),
  KEY ix_qt_knowledge_course_id (course_id),
  KEY ix_qt_knowledge_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='教程表：登记一套教程或一组课程延展资料，承载套级简介与教材/习题集/平行读物引用数组，指引资源检索与补书决策';
```

### 列说明

| 列名 | 说明 |
|---|---|
| `knowledge_id` | 教程标识（主键）：`kt-{课程缩写}-{set_no}`，服务端生成，幂等 |
| `course_id` | 所属课程标识（外键 → qed_course.course_id）；索引 |
| `kind` | `tutorial`=一套教程；`other_material`=课程延展资料归类 |
| `set_no` | 套标记：1~4=中文套号；en=英文对照套；空串=资料归类行 |
| `name` | 教程名：格式「教程N：作者《书名》」（模板约定）；资料归类行用分类名 |
| `position` | 学习阶段（套级）：beginner=新手入门；intermediate=进阶；advanced=深度研究；comprehensive=全面系统；elective=选修拓展 |
| `intro` | 套级简介（散文）：包含是什么（作者/学派/地位）、为何选、学什么、怎么学（用法与配套关系）、平行读物提及；120~350 字 |
| `textbook_ref` | 教材引用数组：[{book_id, title, part, authors:[{name,role}], publisher, edition, year, language, roles}]；多卷各一条；book_id 落库后回填 |
| `exercise_ref` | 习题集引用数组：同 textbook_ref 结构；NULL 表示教材 roles 已含 exercises（自含习题），无需独立习题集 |
| `parallel_ref` | 平行读物引用数组：同 textbook_ref 结构；服务端据此建 status=parallel 的书行并回填 book_id |
| `status` | 审阅状态：draft=探索中（LLM 产出待审）；confirmed=人工定稿（简介与引用已确认）；索引 |
| `confirmed_at` | 人工定稿时间（draft → confirmed 时回填） |
| `notes` | 审阅备注或退役说明（废弃/拆分/合并时记录原因与去向） |
| `created_at` / `updated_at` | 创建时间 / 最后更新时间 |

### 设计要点

- **状态机（两态，2026-09-03 D1 裁决）**：`draft`（探索中）→ `confirmed`（定稿）。
  废弃/退役语义由 `notes` 字段承载，不再有 rejected / superseded / completed 终态。
  课程完成由导入/apply-results 层管理，不冗余在教程行。
- **ID 生成（D4 裁决，2026-09-03 裁决修订）**：`kt-{course_abbr}-{set_no}`。手动导入路径
  由数据文件显式携带（文件内 `knowledge_id` 已写 `kt-01ma-1`），服务端校验格式 + 去重检测；
  LLM 探索采纳路径由服务端按 `course_id` 去下划线机械生成（`01_math_analysis`→`01mathanalysis`）。
  不维护人工"课程缩写映射表"。
- **引用数组**：`textbook_ref` / `exercise_ref` / `parallel_ref` 均为 JSON 数组。
  多卷书籍各占一条（同 title 不同 part）；author 结构化 `[{name, role:"author|translator"}]`。
  `parallel_ref` 中的书目由服务端建 `qt_books` 行（status=parallel）。
- **uq 约束**：不建 DB 级 `uq_course_set`（other_material 多行 set_no='' 会冲突），
  沿用应用层幂等查重（AdoptionConflict）。

### 在本项目中的作用

- 主链路（课程梳理→教材寻找→取书→复核）的核心实体：采纳端点 `POST /courses/{course_id}/knowledge`
  建 draft 行并预填 set_no/name/position/intro/引用数组；`POST /knowledge/{knowledge_id}/confirm`
  人工定稿；CLI `mainline new/review` 读写本表。
- 教程级取书的驱动源：`GET /knowledge/{knowledge_id}` 由 refs 数组聚合书籍列表，
  `POST /knowledge/{knowledge_id}/fetch` 按 refs 引用书集发起批量取书
  （见[下载管线设计](../design/download-pipeline.md)）。

---

## qt_books 表结构（表2，私有）

**表名**：qt_books（书库表）。**用途**：域级书库，登记一册/一本书的选用状态与持有状态，
承载补书优先级；下载执行由 qt_sources 承载；book_id 由服务端确定性生成。
**一行 =** 一册/一卷/一本书籍（教材、习题集、题解、论文、博客快照）。
**书库化（2026-09-03 D2 裁决）**：域级书库，多套教程可引用同一本书（多对多）；行内无归属列
（归属由教程 refs 承载）。

```sql
CREATE TABLE qt_books (
  book_id         VARCHAR(32)  NOT NULL, -- PK：{课程缩写}-b{NN}，服务端生成，域内全局唯一
  title           VARCHAR(256) NOT NULL, -- 书名（真实名称，支持 zh/en）
  original_title  VARCHAR(256) DEFAULT NULL, -- 原题（外文原版书名，支撑原版检索；无则 NULL）
  part            VARCHAR(8)   NOT NULL DEFAULT '', -- 卷标识（受控值，见列说明）
  authors         JSON         NOT NULL, -- 作者列表 [{name, role}]（见列说明）
  publisher       VARCHAR(128) NOT NULL DEFAULT '', -- 出版社名称
  edition         VARCHAR(64)  NOT NULL DEFAULT '', -- 版本/版次（如 第3版、2nd Edition）
  year            SMALLINT     DEFAULT NULL, -- 出版年份（未知填 NULL）
  language        ENUM('zh','en') NOT NULL, -- 主要语言：zh=中文（含中译本）；en=英文
  roles           JSON         NOT NULL, -- 书籍角色（见列说明）
  status          ENUM('decided','parallel','candidate','retired') NOT NULL DEFAULT 'candidate', -- 选用状态四态（见列说明）；索引
  retire_reason   VARCHAR(500) NOT NULL DEFAULT '', -- 退役原因（status=retired 时必填）
  holding         ENUM('owned','missing') NOT NULL DEFAULT 'missing', -- 持有状态（见列说明）；索引
  file_path       VARCHAR(512) DEFAULT NULL, -- PDF 文件路径（数据根相对路径）；holding=owned 时回填
  priority        TINYINT      DEFAULT NULL, -- 补书优先级（人工运营填写）；索引
  notes           TEXT         DEFAULT NULL, -- 备注：候选比较 / 来源渠道 / 拆合去向等
  domain_id       VARCHAR(32)  NOT NULL DEFAULT '', -- 所属领域标识（冗余；按域查询书库用）；索引
  created_at      DATETIME     NOT NULL, -- 创建时间（首次导入时写入）
  updated_at      DATETIME     NOT NULL, -- 最后更新时间（状态变更/编辑时更新）
  PRIMARY KEY (book_id),
  KEY ix_qt_books_status (status),
  KEY ix_qt_books_holding (holding),
  KEY ix_qt_books_priority (priority),
  KEY ix_qt_books_domain_id (domain_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='书库表：域级书库，登记一册/一本书的选用状态与持有状态，承载补书优先级；下载执行由 qt_sources 承载';
```

### 列说明

| 列名 | 说明 |
|---|---|
| `book_id` | 书籍标识（主键）：`{课程缩写}-b{NN}`，服务端生成，域内全局唯一 |
| `title` / `original_title` | 书名（真实名称，支持 zh/en）；原题为外文原版书名（裁决 5，支撑原版检索；无则 NULL） |
| `part` | 卷标识（受控值）：空串=单卷本；上册/下册=中文卷；Vol.1/2/3=英文卷 |
| `authors` | 作者列表：[{name:"姓名", role:"author|translator"}]；role 区分原作者与译者（支撑中译本检索） |
| `publisher` / `edition` / `year` / `language` | 出版社 / 版次 / 出版年份（未知 NULL）/ 主要语言（zh 含中译本） |
| `roles` | 书籍角色：["textbook"] 或 ["textbook","exercises"] 或 ["exercises"] 或 ["solutions"]；solutions=题解（独立角色） |
| `status` | 选用状态：decided=已入选引用数组（推荐使用）；parallel=平行读物（intro 提及）；candidate=候选待选；retired=退役；索引 |
| `retire_reason` | 退役原因（status=retired 时必填）：如「合并至 bk-xx」/「拆分为 bk-xx + bk-yy」/「已过时」 |
| `holding` | 持有状态：owned=PDF 已到手且校验通过；missing=未持有（需要补书）；索引 |
| `file_path` | PDF 文件路径（数据根相对路径）；holding=owned 时回填 |
| `priority` | 补书优先级（人工运营填写）：0=P0 最高；1=P1 中等；2=P2 低等；NULL=未定；索引 |
| `notes` | 备注：候选比较 / 来源渠道 / 渠道探索信息 / 拆合去向等 |
| `domain_id` | 所属领域标识（冗余列；按域查询书库用）；索引 |
| `created_at` / `updated_at` | 创建时间 / 最后更新时间 |

### 设计要点

- **状态机（选用四态 + retired，2026-09-03 D3 裁决）**：

  ```text
  candidate（候选待选）──decided（已入选引用数组）──→ decided
      │                                                │
      │──parallel（平行读物，intro 提及）                │──→ retired（退役/拆分/合并，reason 必填）
      └──retired（退役，reason 必填）                    │
  ```

  - `decided`：已被某套教程的 textbook_ref / exercise_ref 引用（推荐使用）。
  - `parallel`：仅在某套 intro 散文中提及的平行读物（不直接推荐，供扩展）。
  - `retired`：退役终态（废弃/拆分/合并），`retire_reason` 必填记录去向。
- **多对多引用**：无 knowledge_id 列；归属由 qt_knowledge.refs 数组中的 book_id 承载。
  同一本书可被多套教程引用（共享同一 book_id）；ref.roles 权威留在知识侧，
  书行 roles 按引用种类落（textbook_ref→["textbook"]、exercise_ref→["exercises"]、parallel_ref→[]）。
- **original_title（裁决 5，2026-09-04）**：可空列；检索词规则集 ①（`original_title + 第一作者姓`）
  的输入，人工导入/采纳时可选回填。
- **holding 语义**：显式化「PDF 是否到手」（旧 status 下载机隐含），与选用状态解耦。
- **补书优先级**：`priority` 列由人工运营填写，LLM 不输出（运营决策）。

### 在本项目中的作用

- 域级书库与补书运营的事实源：五阶段取书（检索→确认→下载→staging 机器验收→登记）的
  目标与 `holding=owned` 落点；登记唯一写入口为 `mark_owned`（详见
  [下载管线设计](../design/download-pipeline.md)）。
- 书级取书 `POST /books/{book_id}/fetch` 与教程级取书 `POST /knowledge/{knowledge_id}/fetch`
  的操作对象；人工导入 `POST /books/{book_id}/import`、原地登记 `POST /books/{book_id}/register`
  落 holding=owned 并回填 file_path。
- 论文/博客也进本表（roles 承载类型），快照落盘统一链路。

---

## qt_sources 表结构（表3，私有）

**表名**：qt_sources（渠道表）。**用途**：记录为某本书尝试的下载渠道及成败，用于归因成功
来源与评估渠道有效性。**一行 =** 一次渠道尝试。

现状延续，仅外键更名挂书籍。**0014 迁移（2026-08-28）**：修复 alembic 链遗留的旧结构
（download_id），按本节 DDL 重建并改挂 book_id 外键（历史存量经 qt_sources_legacy 留档）。
**0018 迁移（2026-09-06）**：qt_books 重建时保留本表（MySQL 挂起 FK 检查，FK 对新表自愈）。

```sql
CREATE TABLE qt_sources (
  source_id       VARCHAR(100)  NOT NULL,         -- PK：src_<md5>
  book_id         VARCHAR(100)  NOT NULL,         -- FK → qt_books.book_id；索引
  channel         VARCHAR(24)   NOT NULL,         -- manual / internet_archive / open_library / google_books / libgen_li
  provider_id     VARCHAR(200)  NOT NULL DEFAULT '',
  page_url        VARCHAR(1000) NOT NULL DEFAULT '',
  download_url    VARCHAR(1000) NOT NULL DEFAULT '',
  file_keywords   VARCHAR(500)  NOT NULL DEFAULT '', -- 多关键词空格分隔（人工下载检索词）
  ok              TINYINT(1)    NOT NULL DEFAULT 0,  -- 尝试是否成功（失败尝试留痕不展示）
  note            VARCHAR(1000) NOT NULL DEFAULT '',
  attempted_at    DATETIME      NOT NULL,
  PRIMARY KEY (source_id),
  KEY ix_qt_sources_book (book_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='渠道表：记录为某本书尝试的下载渠道及成败，用于归因成功来源与评估渠道有效性';
```

- 无状态机：一次渠道尝试一条记录；`ok` 表达成败。失败尝试留痕不展示（详情只展示 ok=1 来源）。
- **定位（2026-08-16 用户确认）**：目的是了解**最终某本书是从哪个渠道获取成功的**（成功渠道
  归因），支撑渠道有效性评估与后续课程下载流程优化。历史参考意义有限——数学分析 12 册中
  9 册由人工（manual）获取（微积分学教程×3、数学分析习题课讲义×2、吉米多维奇×2、
  数学分析原理（鲁丁）×2），另 3 册经 archive.org 自动获取；**当前阶段以固定当前课程（定稿
  固化）为主，渠道优化流程从下一门课程开始**；表结构不变，记录即优化依据。人工获取书的
  自动渠道保留 ok=0 失败留痕（note 标注"自动下载失败，转人工"），成功渠道归因以 manual 为准。

### 在本项目中的作用

- 取书链路的渠道留痕：自动下载尝试与人工登记（`channel=local_import`）都落本表；
  CLI `mainline channels` 全量遍历 qt_books 聚合本表。
- 百炼/LLM 的判断**不写资源事实**：判断只落 qt_sources 留痕与 qed_llm_calls 审计，
  下载与登记由确定性服务执行（AGENTS.md 强制约束）。

---

## qt_tasks 表结构（表4，私有）

**表名**：qt_tasks（后台任务表）。**用途**：一行一个后台任务记录，替代 meta/tasks/ JSON 文件
（REQ-032；ADR 0006 起为 ensure_schema 声明表，无独立迁移）。

```sql
CREATE TABLE qt_tasks (
  task_id         VARCHAR(100)  NOT NULL,         -- PK：任务标识
  type            VARCHAR(50)   NOT NULL,         -- 任务类型（book_download / tutorial_fetch / domain_explore / course_explore）
  status          VARCHAR(24)   NOT NULL,         -- queued / running / succeeded / failed
  params          JSON          NOT NULL,         -- 任务参数
  progress        INT           NOT NULL DEFAULT 0, -- 进度（0-100）
  message         TEXT          NOT NULL,          -- 当前状态消息
  result          JSON          NULL,             -- 成功结果
  error           TEXT          NOT NULL,          -- 失败错误信息
  created_at      DATETIME      NOT NULL,
  updated_at      DATETIME      NOT NULL,
  PRIMARY KEY (task_id),
  KEY ix_qt_tasks_status (status),
  KEY ix_qt_tasks_type (type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='后台任务表：一行一个后台任务记录，替代 meta/tasks/ JSON 文件';
```

- **状态机**：`queued`（排队中）→ `running`（执行中）→ `succeeded`（成功）/ `failed`（失败）。
- **写权限**：QED-Tracker 唯一写权限（TaskManager 通过 `manager.submit()` 写入，
  `manager.complete_task()` 更新；调度器在 `src/qed_tracker/api/tasks.py`）。
- **清理策略**：succeeded 记录可定期清理；failed 记录保留用于排查。

### 在本项目中的作用

- 8901 写操作异步化的承载：取书（书级/教程级）与重探提交后台任务（202），结果经
  `GET /api/v1/tasks/{task_id}` 轮询；CLI fetch+轮询消费同一契约。
- 并发控制的事实承载：并发上限 2、同类型 dedup 查重（仅 queued/running 计入）。

---

## qt_selections 表结构（表5，私有）

**表名**：qt_selections（论文选择报告表）。**用途**：一行一个选择报告，替代 meta/selections/
JSON 文件（REQ-032；论文链[论文发现设计](../design/paper-discovery.md)的存储侧；ADR 0006 起
为 ensure_schema 声明表）。

```sql
CREATE TABLE qt_selections (
  selection_id       VARCHAR(100)  NOT NULL,         -- PK：报告标识（sel-<时间>-<随机>）
  schema_version     INT           NOT NULL,         -- Schema 版本号
  status             VARCHAR(24)   NOT NULL,         -- planning / no_candidates / completed / ...
  created_at         VARCHAR(50)   NOT NULL,         -- 创建时间（ISO 格式）
  profile            JSON          NULL,             -- 论文档案
  temporary_goal     TEXT          NOT NULL,         -- 临时研究目标
  allowed_categories JSON          NULL,             -- 允许的 arXiv 分类
  search_plan        JSON          NULL,             -- 搜索计划
  search_failures    JSON          NULL,             -- 搜索失败记录
  excluded_existing  JSON          NULL,             -- 已排除的已有 arXiv ID
  candidates         JSON          NULL,             -- 候选论文列表
  assessments        JSON          NULL,             -- 评估结果
  recommendations    JSON          NULL,             -- 推荐列表
  model              JSON          NULL,             -- 模型元数据
  downloads          JSON          NULL,             -- 下载记录
  error              TEXT          NOT NULL,         -- 失败错误信息
  PRIMARY KEY (selection_id),
  KEY ix_qt_selections_status (status),
  KEY ix_qt_selections_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='论文选择报告表：一行一个选择报告，替代 meta/selections/ JSON 文件（REQ-032）';
```

- **写权限**：QED-Tracker 唯一写权限（`src/qed_tracker/db/selection_repository.py`：
  `save`/`load`/`list`）。
- 无状态机：状态为报告快照字段（planning/no_candidates/completed 等），由论文管线写入。

### 在本项目中的作用

- 论文发现链路的报告存储：每次论文选择会话（检索计划→候选评估→推荐）的完整快照落本表，
  供回溯与复核；`GET /api/v1/papers/search` 等检索端点为即时查询，不落本表。

---

## 状态机汇总与迁移合法性

| 层 | 状态机 | 终态 | 非法迁移（API 409） |
| --- | --- | --- | --- |
| qt_knowledge | draft → confirmed（2026-09-03 D1 两态） | confirmed | 终态任何迁移；rejected/superseded/completed 已退役（废弃改 notes） |
| qt_books | candidate → decided / parallel；candidate / decided / parallel → retired（D3 选用四态） | retired（retire_reason 必填） | 终态任何迁移；下载执行态（downloading/downloaded/verified）已由 qt_sources + 资源清单承接，不再属于 qt_books |
| qt_sources | 无（仅 ok 标记） | — | — |
| qt_tasks | queued → running → succeeded / failed | succeeded / failed | TaskManager 内部管理，API 不暴露迁移端点 |

## Schema 自愈（ADR 0006：模型即 schema）

**Alembic 迁移链已退役**（ADR 0006）：`alembic.ini` 与迁移目录 migrations/ 已删除，
`ensure_schema(engine)` 启动自愈取代 `alembic upgrade head`；历史链仅作 Git 历史追溯，
不再作为实现依据。

- **启动自愈规则**：`Base.metadata` 内 7 张声明表——缺失 → `create_all` 补建；列集/主键与
  模型不一致 → DROP+CREATE 全部重建（统一含共享表）；幂等；MySQL 下重建时挂起 FK 检查，
  `qt_sources` 外键对新表自愈。
- **`qed_llm_calls` 特判**：根仓库建表维护的共享审计表，缺失时按权威 DDL（对齐根仓库
  `call_log.py`）建表；已有表缺 REQ-060 扩展列（task/step/review_status/review_note）则
  `ALTER ADD COLUMN` 补齐；**绝不 DROP 重建**（保护三项目审计历史）。
- **历史关键节点（供追溯，非职责）**：0018（QED-050-D 书库化 DROP+重建 qt_knowledge/qt_books、
  增 original_title、选用四态 + holding + priority，downgrade 不支持——重放导入代替）；
  0016（qt_tasks 建表）；0015（explore_pending + 6 态状态机）；0014（qt_sources 重建挂
  book_id，历史存量经 qt_sources_legacy 留档，该留档表已随链退役）。
- 课程/领域种子不再经迁移写入：标准答案 JSON（`docs/knowledge/`）经确认流程导入
  （ADR 0006 决定 6），数据重建后可重放。

## 接口/契约影响

- CLI：主链路 `mainline` 命令族读写 qt_knowledge/qt_books（new/review 定稿两态、download 经
  8901 教程级取书、verify 只读复核、channels 全量遍历 qt_books 聚合 qt_sources；
  approve/reject 已删除，设计裁决 6）；`books fetch <book_id>` 书级取书（裁决 9 双入口）。
- 论文/博客：进入 qt_books（roles 承载类型），快照落盘统一链路（HTML→PDF 或归档，
  实现计划明确）。
- 课程体系只读端点（`GET /api/v1/courses`、`GET /api/v1/courses/{domain_id}`）读共享表，
  契约见[数据库共享表设计](database-shared-tables.md)与 [API 设计文档](api.md)。

### 书籍响应契约（8901 透出，QED-050-D 书库化后）

`GET /api/v1/knowledge/{knowledge_id}` 的书籍数组（`books[]`）由 **refs 数组聚合**
（textbook_ref/exercise_ref/parallel_ref 内 book_id 去重），每行为 `QtBook.to_dict()` 全列
（book_id/title/original_title/part/authors/publisher/edition/year/language/roles/status/
retire_reason/holding/file_path/priority/notes/domain_id/created_at/updated_at）：

- **无** `display_title` / `sha256` / `size` / `page_count` 列（书库化已删）——展示名由前端按
  `title + part` 组装；文件内容指纹只落 qt_sources.note 与资源清单 JSON。
- `holding=owned` 时 `file_path` 回填（数据根相对路径）；下载执行细节见 qt_sources。
- `roles` 取值 `textbook`/`exercises`/`solutions`；教材含习题 → `roles=["textbook","exercises"]`。

## 验证方式

1. 单元：models 枚举/状态机迁移合法性（非法迁移 409）、repository 增删改查（SQLite mock）。
2. schema 自愈：`tests/test_schema.py`（SQLite：缺表补建/列不一致重建/幂等/未声明表不碰/
   qed_llm_calls 缺列增量补齐且不 DROP）。
3. 冒烟：`tests/test_schema_mysql_smoke.py`（真实 MySQL，仅允许 `QED_DB_NAME=qed_test` 时执行，
   默认 skip）：ensure_schema 幂等 + 7 张表契约列 + qed_llm_calls 扩展列。
4. 服务启动：`qed-tracker serve` 执行 `ensure_schema`（DB 不可用时软降级，服务照常起）。
5. 文档治理：`tests/test_documentation.py` 全绿（本文件登记索引、ADR 0007 拆分关系）。

## 用户裁决记录（2026-08-16）

1. **替换重构**：新表族替代三表，存量迁移后旧表退役（不并行保留）。
2. **拆三表层次**：领域/课程/知识（教程层）三张表；领域/课程为三项目共享表（新前缀 `qed_*`），
   教程一行=一套教程。
3. **共享机制**：改根仓库契约（ADR 0003 / database-design.md / service-contracts.md），
   QED-Tracker 建表维护，其他项目只读。
4. **教程粒度**：一行=一套教程；教程选择（教材/习题集）为决定引用（书名+版本），
   候选书目存书籍（状态机四段：候选/决定/下载成功/确认正确）。
5. **简介生成时机**：探索定稿时 LLM 预填 + 人工审（指引后续检索）；教程探索开始即建
   draft，定稿转 confirmed。
6. **课程 JSON 退役**：courses/math.json 数据迁入 qed_course，表为主、JSON 退役。
7. **多卷教材建模**：取消册行表，书籍一行=一册/一卷/一个快照（part 区分）；教材含习题 →
   书籍 roles 标注，不另建行；论文/博客入书籍（kind=paper/blog），教程 kind=other_material
   作为课程延展资料归类行。
8. **博客落盘**：快照落盘统一链路（非 PDF 也产生文件），不存 URL 了事。
9. **文件命名**：物理名（display slug + 短 hash）/ 展示名（不含 hash）分离；下载校验成功后
   改名落盘；qt_books 增 `absolute_path`（QED-Engine dataset 目录绝对路径）。
10. **唯一数据库设计文档**：按表族分两文为唯一事实源（ADR 0007：共享表设计/专用表设计），
    旧设计文档（database-schema-ownership.md / three-table-schema.md）标注被取代留档。
