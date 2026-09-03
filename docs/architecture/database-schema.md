# 数据库设计：qed 库 qed_*/qt_* 表族（唯一事实源）

设计状态：Accepted
确认状态：暂定
实现状态：Implemented
最后更新：2026-09-03
需求方：QED-Engine（根仓库 REQ-026/REQ-029/REQ-030；2026-08-16 用户裁决知识层次重构）
关联代码：`src/qed_tracker/db/`（models/knowledge_repository/migrations）、`src/qed_tracker/database.py`、
`src/qed_tracker/courses.py`（migrations/data/math.json，规划退役）
关联测试：`tests/test_db_models.py`、`tests/test_knowledge_repository.py`、`tests/test_knowledge_api.py`、
`tests/test_db_three_table_smoke.py`、`tests/test_courses.py`（实现轮同步更新）
关联 ADR：[ADR 0001](../adr/0001-tracker-service-architecture.md)；根仓库 [ADR 0003](../../../docs/history/adr/v0.1/0003-shared-qed-database-independence.md)（命名空间隔离）与 [ADR 0009](../../../docs/history/adr/v0.1/0009-shared-qed-tables.md)（2026-08-16：新增 qed_* 共享表族）

> **唯一事实源声明**：本文件是 qed 库全部 `qed_*`（共享）与 `qt_*`（QED-Tracker 私有）表的
> **唯一当前事实源文档**（全库 DDL 与表结构），取代 `database-schema-ownership.md`（QED-023
> 时代留档）与 `three-table-schema.md`（三表模型，QED-028）。被取代文档保留只读、标注
> Retired/Superseded，不再作为实现依据。新增/修改表必须先更新本文件，再写 Alembic 迁移。
> **确认状态：暂定**——以代码现状为准的先行整理，正式稿五要素评审由 QED-044 收口。
> 按 [ADR 0005](../adr/0005-shared-tables-doc-location.md)，数据库设计分两区：
> **共享表（`qed_*`）**——跨项目契约（写权限、状态机写主体、Schema 变更流程）以
> [共享表设计](shared-tables.md) 为准；**项目专用表（`qt_*`）**——本仓库私有，契约即本文件。

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

## 表清单（6 张在用表）

```
qed_domain（领域，共享 qed_*）
  └── qed_course（课程，共享 qed_*）
        └── qt_knowledge（教程，qt_* 私有：一套教程 / 一组课程延展资料）
              └── qt_books（书库：域级书库，一册/一本书，选用状态+持有状态+补书优先级）
                    └── qt_sources（渠道尝试，一次一条）
qt_tasks（后台任务，qt_* 私有：一行一个后台任务记录）
```

| 表 | 中文表名 | 前缀 | 所有权 | 一行= | 状态 |
| --- | --- | --- | --- | --- | --- |
| `qed_domain` | 领域表 | 共享 | QED-Tracker 建表维护，其他项目只读 | 一个学科领域（math / math-advanced；扩展预留） | 在用（迁移 0006 建，0011 扩展） |
| `qed_course` | 课程表 | 共享 | 同上 | 一门课程（含阶段/先修/别名/顺序） | 在用（迁移 0006 建，0012 扩展） |
| `qt_knowledge` | 教程表 | 私有 | QED-Tracker | kind=tutorial：一套教程；kind=other_material：课程延展资料归类 | 在用（2026-09-03 两态重构） |
| `qt_books` | 书库表 | 私有 | QED-Tracker | 一册/一本书的选用状态与持有状态，承载补书优先级 | 在用（2026-09-03 书库化重构） |
| `qt_sources` | 渠道表 | 私有 | QED-Tracker | 一次渠道尝试 | 在用（0014 迁移重建，外键挂 book_id） |
| `qt_tasks` | 任务表 | 私有 | QED-Tracker | 一个后台任务记录（REQ-032） | 在用（迁移 0016 建） |

> 表/列中文注释：0007 迁移（`0007_table_comments`）从 `migrations/data/table_comments.json`
> （UTF-8，唯一事实源）应用到真实库；ORM 模型 `comment=` 与新建库 `create_all` 保持一致。
> 各表 SQL 中的 `COMMENT='...'` 即该表的中文表介绍（下表结构体已同步）。
> 列级中文注释的事实源为 `src/qed_tracker/migrations/data/table_comments.json`，
> 经 `scripts/apply_table_comments.py` 幂等应用到真实库（迁移加列不会自动应用注释，
> 加列后须跑一次；2026-08-28 已全量对齐 qed_domain/qed_course）。

## 共享表（`qed_*`，跨项目契约）

三项目可读；所有权与写权限（含 8900 离线降级直写例外）、exploration_stage 状态机写主体、
Schema 变更流程的**契约事实源**为[共享表设计](shared-tables.md)，本区维护其 DDL 与列语义。
`qed_llm_calls` 由根仓库建表维护，见下方存根节。

### qed_domain 表结构（表1，共享）

```sql
CREATE TABLE qed_domain (
  domain_id          VARCHAR(32)   NOT NULL,           -- PK：math（学科标识，扩展预留）
  name               VARCHAR(100)  NOT NULL,           -- 显示名（数学）
  description        TEXT          NOT NULL,           -- 学科介绍
  level              VARCHAR(50)   NOT NULL DEFAULT '',-- 探索范围（本科-硕士）
  scope              TEXT          NOT NULL,           -- 学科知识（管线暂不输出，置空）
  exploration_stage  VARCHAR(20)   NOT NULL DEFAULT '未开始', -- 流程状态（6 态契约见 shared-tables.md）
  classic_tracks     JSON          NOT NULL,           -- 课程方向 [{name,summary,kind}] 0~4 项
  stages             JSON          NOT NULL,           -- 学习阶段顺序（无默认值，后续可变更）
  path_results       JSON,                             -- 学习流程（notes/edges/graph_td）
  explore_pending    JSON,                             -- 探索待确认载荷（REQ-067-B12：审阅结果/失败原因）
  created_by         VARCHAR(16)   NOT NULL DEFAULT '',
  updated_by         VARCHAR(16)   NOT NULL DEFAULT '',
  created_at         DATETIME      NOT NULL,
  updated_at         DATETIME      NOT NULL,
  PRIMARY KEY (domain_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='领域表：按学科组织课程体系，一行一个学科，记录学科介绍、探索范围与学习阶段划分';
```

- 共享表：三项目可读；QED-Tracker 唯一写权限（Alembic 建表维护）。
- `level`：探索范围（管线 domain@v4 输出），描述该领域的默认学习阶段范围。
- `scope`：学科知识（领域边界描述），当前管线不输出，先置空。
- `exploration_stage`：流程状态枚举（未开始→已生成→探索中→待确认→已完成；探索中/待确认→
  失败。6 态契约、explore_pending 载荷与写主体见[共享表设计](shared-tables.md)状态机节；
  待确认/失败为 REQ-067-B10/B12 已裁决契约，**已实现**（迁移 0015 落地，库内为 6 态）。
- `classic_tracks`：课程方向（管线 domain@v4 输出），JSON 数组 [{name,summary,kind}]，0~4 项
  （kind=main 主干 / branch 分支）。
- `stages`：学习阶段顺序，无默认值，后续根据 LLM 生成结果确定。
- `path_results`：学习流程（领域探索管线输出，courses@v8 起由服务端按 prerequisites 推导），
  可空，包含 notes/edges/graph_td。

## qed_course 表结构（表2，共享）

```sql
CREATE TABLE qed_course (
  course_id          VARCHAR(64)   NOT NULL,         -- PK：01_math_analysis（与 catalogs 对齐）
  domain_id          VARCHAR(32)   NOT NULL,         -- FK → qed_domain.domain_id；索引
  sort_order         INT           NOT NULL,         -- 学习顺序（原 courses[] 数组序，DAG 拓扑序）
  name               VARCHAR(200)  NOT NULL,         -- 规范名（数学分析）
  aliases            JSON          NOT NULL,         -- list[str]：别名（高等数学（工科称呼））
  track              VARCHAR(50)   NOT NULL DEFAULT '',-- 课程所属学术方向（管线 courses@v8 输出）
  stage              VARCHAR(32)   NOT NULL,         -- 所属阶段（qed_domain.stages 之一）
  prerequisites      JSON          NOT NULL,         -- list[str]：先修 course_id 数组（主知识链路 DAG）
  related_targets    JSON          NOT NULL,         -- list[str]：已通过验收的关联 catalog 目标（现为空，随验收回填）
  description        VARCHAR(1000) NOT NULL DEFAULT '',-- 课程介绍
  exploration_stage  VARCHAR(20)   NOT NULL DEFAULT '未开始', -- 流程状态（6 态契约见 shared-tables.md）
  explore_pending    JSON,                             -- 探索待确认载荷（REQ-067-B12：tutorials 审阅结果/失败原因）
  created_by         VARCHAR(16)   NOT NULL DEFAULT '',
  updated_by         VARCHAR(16)   NOT NULL DEFAULT '',
  created_at         DATETIME      NOT NULL,
  updated_at         DATETIME      NOT NULL,
  PRIMARY KEY (course_id),
  KEY ix_qed_course_domain (domain_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='课程表：登记一门课程，记录课程名称、所属阶段、先修关系与学习顺序';
```

- 共享表：三项目可读；QED-Tracker 唯一写权限（Alembic 建表维护）。
- `track`：课程所属学术方向（管线 courses@v8 输出），如 "分析学"/"代数学"。
- `stage`：所属学习阶段（纵向），来自 qed_domain.stages。
- `description`：课程介绍（原 note 字段，2026-08-27 重命名与 qed_domain 同步）。
- `exploration_stage`：流程状态枚举（6 态，同 qed_domain，见上）；`explore_pending` 载荷与
  写主体契约见[共享表设计](shared-tables.md)（6 态已实现，迁移 0015）。

- **`courses/math.json` 退役**（2026-08-16 用户裁决）：表为课程体系唯一事实源；CLI/8903 改读表；
  `subject`/`stages` 迁入 qed_domain，`courses[]` 迁入本表（sort_order=数组序）。
- `related_targets` 规则延续主链路决策：只关联已通过二次确认评估（人工验收 approved）的课程目标。

### qed_llm_calls 表结构（LLM 调用审计，共享）

由 QED-Engine 后端 `call_log.py` 幂等建表维护（不在本仓库 Alembic 迁移链内），三项目均可写
（`service` 字段区分调用方）。DDL、列语义、写入路径与模板编号登记见
[共享表设计](shared-tables.md)表3，本文件不重复维护。

## 项目专用表（`qt_*`，QED-Tracker 私有）

仅本仓库读写，契约即本文件；对其他项目无同步义务。

### qt_knowledge 表结构（表3，私有）

一行 = 一套教程（kind=tutorial）或一组课程延展资料归类（kind=other_material）。

```sql
-- ============================================================
-- 表名：qt_knowledge
-- 用途：登记一套教程或一组课程延展资料，承载套级简介与教材/习题集引用数组。
--       引导资源检索与补书决策；knowledge_id 由服务端确定性生成。
-- ============================================================
CREATE TABLE qt_knowledge (
  knowledge_id  VARCHAR(32)   NOT NULL
                COMMENT '教程标识（主键）：kt-{课程缩写}-{set_no}，服务端生成，幂等',
  course_id     VARCHAR(32)   NOT NULL
                COMMENT '所属课程标识（外键 → qed_course.course_id）；索引',
  kind          ENUM('tutorial','other_material') NOT NULL DEFAULT 'tutorial'
                COMMENT '教程类型：tutorial=一套教程；other_material=课程延展资料归类',
  set_no        VARCHAR(4)    NOT NULL DEFAULT ''
                COMMENT '套标记：1~4=中文套号；en=英文对照套；空串=资料归类行',
  name          VARCHAR(128)  NOT NULL DEFAULT ''
                COMMENT '教程名：格式「教程N：作者《书名》」（模板约定）；资料归类行用分类名',
  position      ENUM('beginner','intermediate','advanced','comprehensive','elective') NOT NULL
                COMMENT '学习阶段（套级）：beginner=新手入门；intermediate=进阶；advanced=深度研究；comprehensive=全面系统；elective=选修拓展',
  intro         TEXT          NOT NULL
                COMMENT '套级简介（散文）：包含是什么（作者/学派/地位）、为何选、学什么、怎么学（用法与配套关系）、平行读物提及；120~350字',
  textbook_ref  JSON          NOT NULL
                COMMENT '教材引用数组：[{book_id, title, part, authors:[{name,role}], publisher, edition, year, language, roles}]；多卷各一条；book_id 落库后回填',
  exercise_ref  JSON          DEFAULT NULL
                COMMENT '习题集引用数组：同 textbook_ref 结构；NULL 表示教材 roles 已含 exercises（自含习题），无需独立习题集',
  parallel_ref  JSON          DEFAULT NULL
                COMMENT '平行读物引用数组：同 textbook_ref 结构（无 book_id）；服务端据此建 status=parallel 的书行',
  status        ENUM('draft','confirmed') NOT NULL DEFAULT 'draft'
                COMMENT '审阅状态：draft=探索中（LLM 产出待审）；confirmed=人工定稿（简介与引用已确认）；索引',
  confirmed_at  DATETIME      DEFAULT NULL
                COMMENT '人工定稿时间（draft → confirmed 时回填）',
  notes         TEXT          DEFAULT NULL
                COMMENT '审阅备注或退役说明（废弃/拆分/合并时记录原因与去向）',
  created_at    DATETIME      NOT NULL
                COMMENT '创建时间（首次导入时写入）',
  updated_at    DATETIME      NOT NULL
                COMMENT '最后更新时间（定稿/编辑/退役时更新）',
  PRIMARY KEY (knowledge_id),
  KEY idx_qt_knowledge_course (course_id),
  KEY idx_qt_knowledge_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='教程表：登记一套教程或一组课程延展资料，承载套级简介与教材/习题集/平行读物引用数组，指引资源检索与补书决策';
```

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

### qt_books 表结构（表4，私有）

一行 = 一册/一卷/一本书籍（教材、习题集、题解、论文、博客快照）。
**书库化（2026-09-03 D2 裁决）**：域级书库，多套教程可引用同一本书（多对多）；
下载执行细节由 qt_sources + 资源清单承载。

```sql
-- ============================================================
-- 表名：qt_books
-- 用途：域级书库，登记一册/一本书的选用状态与持有状态，承载补书优先级。
--       下载执行由 qt_sources 承载；book_id 由服务端确定性生成。
-- ============================================================
CREATE TABLE qt_books (
  book_id         VARCHAR(32)   NOT NULL
                  COMMENT '书籍标识（主键）：{课程缩写}-b{NN}，服务端生成，域内全局唯一',
  title           VARCHAR(256)  NOT NULL
                  COMMENT '书名（真实名称，支持 zh/en）',
  part            VARCHAR(8)    NOT NULL DEFAULT ''
                  COMMENT '卷标识（受控值）：空串=单卷本；上册/下册=中文卷；Vol.1/2/3=英文卷',
  authors         JSON          NOT NULL
                  COMMENT '作者列表：[{name:"姓名", role:"author|translator"}]；role 区分原作者与译者（支撑中译本检索）',
  publisher       VARCHAR(128)  NOT NULL DEFAULT ''
                  COMMENT '出版社名称',
  edition         VARCHAR(64)   NOT NULL DEFAULT ''
                  COMMENT '版本/版次（如 第3版、2nd Edition）',
  year            SMALLINT      DEFAULT NULL
                  COMMENT '出版年份（如 2020；未知填 NULL）',
  language        ENUM('zh','en') NOT NULL
                  COMMENT '主要语言：zh=中文（含中译本）；en=英文',
  roles           JSON          NOT NULL
                  COMMENT '书籍角色：["textbook"] 或 ["textbook","exercises"] 或 ["exercises"] 或 ["solutions"]；solutions=题解（独立角色）',
  status          ENUM('decided','parallel','candidate','retired') NOT NULL DEFAULT 'candidate'
                  COMMENT '选用状态：decided=已入选引用数组（推荐使用）；parallel=平行读物（intro 提及）；candidate=候选待选；retired=退役；索引',
  retire_reason   VARCHAR(500)  NOT NULL DEFAULT ''
                  COMMENT '退役原因（status=retired 时必填）：如「合并至 bk-xx」/「拆分为 bk-xx + bk-yy」/「已过时」',
  holding         ENUM('owned','missing') NOT NULL DEFAULT 'missing'
                  COMMENT '持有状态：owned=PDF 已到手且校验通过；missing=未持有（需要补书）；索引',
  file_path       VARCHAR(512)  DEFAULT NULL
                  COMMENT 'PDF 文件路径（数据根相对路径）；holding=owned 时回填',
  priority        TINYINT       DEFAULT NULL
                  COMMENT '补书优先级（人工运营填写）：0=P0 最高；1=P1 中等；2=P2 低等；NULL=未定；索引',
  notes           TEXT          DEFAULT NULL
                  COMMENT '备注：候选比较 / 来源渠道 / 渠道探索信息 / 拆合去向等',
  domain_id       VARCHAR(32)   NOT NULL DEFAULT ''
                  COMMENT '所属领域标识（冗余；按域查询书库用）；索引',
  created_at      DATETIME      NOT NULL
                  COMMENT '创建时间（首次导入时写入）',
  updated_at      DATETIME      NOT NULL
                  COMMENT '最后更新时间（状态变更/编辑时更新）',
  PRIMARY KEY (book_id),
  KEY idx_qt_books_status (status),
  KEY idx_qt_books_holding (holding),
  KEY idx_qt_books_priority (priority),
  KEY idx_qt_books_domain (domain_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='书库表：域级书库，登记一册/一本书的选用状态与持有状态，承载补书优先级；下载执行由 qt_sources 承载';
```

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
  同一本书可被多套教程引用（共享同一 book_id）。
- **authors 结构化**：`[{name, role:"author|translator"}]`，支撑中译本检索
  （译者标注用于下载查询词：原版名 vs 译本名）。
- **holding 语义**：显式化「PDF 是否到手」（旧 status 下载机隐含），与选用状态解耦。
- **补书优先级**：`priority` 列由人工运营填写，LLM 不输出（运营决策）。

### qt_sources 表结构（表5，私有）

现状延续，仅外键更名挂书籍。**0014 迁移（2026-08-28）**：修复 alembic 链遗留的旧结构
（download_id），按本节 DDL 重建并改挂 book_id 外键（真实存量行级映射由
migrate_knowledge.py 完成）。

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

### qt_tasks 表结构（表6，私有）

一行 = 一个后台任务记录（REQ-032），替代 `meta/tasks/` JSON 文件。迁移 0016 建表。

```sql
CREATE TABLE qt_tasks (
  task_id         VARCHAR(100)  NOT NULL,         -- PK：任务标识
  type            VARCHAR(50)   NOT NULL,         -- 任务类型（book_download / domain_explore / course_explore）
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
- **写权限**：QED-Tracker 唯一写权限（TaskManager 通过 `manager.submit()` 写入，`manager.complete_task()` 更新）。
- **清理策略**：succeeded 记录可定期清理；failed 记录保留用于排查。

## 状态机汇总与迁移合法性

| 层 | 状态机 | 终态 | 非法迁移（API 409） |
| --- | --- | --- | --- |
| qt_knowledge | draft → confirmed（2026-09-03 D1 两态） | confirmed | 终态任何迁移；rejected/superseded/completed 已退役（废弃改 notes） |
| qt_books | candidate → decided / parallel；candidate / decided / parallel → retired（D3 选用四态） | retired（retire_reason 必填） | 终态任何迁移；下载执行态（downloading/downloaded/verified）已由 qt_sources + 资源清单承接，不再属于 qt_books |
| qt_sources | 无（仅 ok 标记） | — | — |

## 迁移与存量说明

- 建表与存量迁移均已执行完成：迁移 0006 建五层表（课程种子 `migrations/data/math.json`）+
  `application/migrate_knowledge.py` 一次性迁入存量（以 `knowledge_id` 与书籍
  `sha256`/`title+part` 为幂等键，可重放）；`qt_sources` 经 0014 重建（外键挂 book_id）。
- 迁移 0015（`add_explore_pending`）：为 `qed_domain`/`qed_course` 新增 `explore_pending` JSON
  列，承载探索待确认载荷（REQ-067-B12）；6 态状态机生效。
- 迁移 0016（`qt_tasks`）：新建 `qt_tasks` 表（REQ-032），替代 `meta/tasks/` JSON 文件，
  一行一个后台任务记录（task_id/type/status/params/progress/message/result/error）。
- **表重建声明（2026-09-03 用户裁决）**：`qt_knowledge` / `qt_books` 按新 DDL（两态 / 书库化）
  **推倒重建，不做旧→新数据映射**——领域课程与标准答案目录（`docs/knowledge/`）重放导入，
  下载 PDF 全部为新文件（无历史下载态），无需存量迁移。qt-schema-restructure 中的"存量迁移
  策略"（旧 status 映射、字段映射）**不采纳**。
- 历史映射细节（旧三表 → 五层的逐表映射、备份快照策略）见 Git 历史与
  [共享表设计](shared-tables.md)迁移史；退役旧表已清理，不再列于本文件表清单。

## 共享表所有权与根仓库契约变更

- **表命名空间**（根仓库 [ADR 0009](../../../docs/history/adr/v0.1/0009-shared-qed-tables.md) 补充 0003，需同步 QED-Engine）：
  - `qt_*`：QED-Tracker 私有；`af_*`：Axiom-Flow 私有（不变）；
  - **新增 `qed_*` 共享前缀表族**（qed_domain / qed_course）：所有权 QED-Tracker
    （Alembic 建表维护），其他项目只读不写；共享表 schema 变更须先经根仓库登记。
- 根仓库 `docs/design/database-design.md` 登记 qed_* 表清单与所有权；
  `docs/design/service-contracts.md` 同步「共享表 + 只读」约定。
- 本仓库课程体系 JSON 退役为运行数据源（迁移种子保留于 `src/qed_tracker/migrations/data/math.json`，
  数据迁入 qed_course；`pyproject.toml` package-data 改含 `migrations/data/*.json`）。

## 接口/契约影响

- CLI/8903：课程体系读取改读 qed_course（`courses list/show` 语义不变）；书单/主链路
  `mainline` 命令族改读写 qt_knowledge/qt_books（new/review/download/verify/approve/reject 映射
  到新状态机）；channels 汇总仍读 qt_sources。
- 书籍 `candidate → decided` 对应旧表1 `candidate → confirmed`；`verified` 对应旧表2 `approved`。
- 论文/博客：进入 qt_books（kind=paper/blog），快照落盘统一链路（HTML→PDF 或归档，实现计划明确）。

### 课程体系只读端点（QED-033，8901 透出）

新增 `GET /api/v1/courses`（按领域分组全量）与 `GET /api/v1/courses/{domain_id}`（单领域详情），
直接透出 qed_domain/qed_course 共享表数据，**纯只读、无任何加工**（QED-Engine 后端仅转发，
数据加工对 QED-Engine 透明）：

| 方法/路径 | 响应 | 错误语义 |
| --- | --- | --- |
| `GET /api/v1/courses` | `[{domain_id, name, description, level, classic_tracks, exploration_stage, path_results, stages, courses:[{course_id, name, aliases, track, stage, prerequisites, related_targets, description, exploration_stage}]}]`；domains 按 domain_id 有序，courses 按 sort_order 有序 | DB 未配置 → 409「数据库未配置」 |
| `GET /api/v1/courses/{domain_id}` | 单领域 curriculum（同上单元素） | 未知 domain → 404；DB 未配置 → 409 |

- 字段与 `src/qed_tracker/courses.py` 的 `Curriculum`/`Course` dataclass 一致（课程不透出
  created_at 等审计列），CLI（`courses list/show`）与 API 单一事实源。
- 支撑根仓库 REQ-035「课程体系数据源切换」（8900 `tracker_client.list_courses` 透传本端点，
  前端学习中心 courseMeta 改读本端点）。

### 书籍响应契约（QED-034，8901 透出）

`GET /api/v1/knowledge/{knowledge_id}` 的书籍数组（`books[]`）与书籍相关响应，每行**必含**
`title` 与 `display_title`（源自 `QtBook.to_dict()`，全列透出）：

- `title`：规范化书名（不含卷号，如 微积分学教程）。
- `display_title`：展示名 = title + part（可人工覆盖，不含 hash），**前端一律消费
  display_title**；`file_name` 为物理落盘名（可含 sha256 短 hash），只在文件操作场景使用。
- `kind`/`roles`：QED-034 退休 supplement/solutions 后取值 `textbook`/`exercise`/`paper`/
  `blog`/`other` 与 `textbook`/`exercises`/`reference`；题解、答案册与习题集统一
  `kind=exercise`、`roles=["exercises"]`，教材含习题 → `roles=["textbook","exercises"]`。

## 验证方式

1. 单元：models 枚举/状态机迁移合法性（非法迁移 409）、repository 增删改查（SQLite mock）。
2. 迁移：0006 建表 + 存量迁移幂等测试（备份快照 → 重放不产生重复行）。
3. 冒烟：8901 服务启动 upgrade_database；CLI courses/mainline 命令走真实 qed 库（QED_DB_SMOKE=1）。
4. 文档治理：`tests/test_documentation.py` 全绿（本文件登记索引、旧文档标注被取代）。

## 成功标准（回执条件）

- 本文件转 Accepted 且实现轮通过 QED-Tracker 全量门禁（`pytest tests -q`、ruff、
  `tests/test_documentation.py`、8901 冒烟）。
- 根仓库 ADR 0003 修订 + database-design.md 登记完成。
- 回执根仓库 REQ-026/REQ-029/REQ-030（提交号 + 测试输出）。

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
10. **唯一数据库设计文档**：本文件为唯一事实源，旧设计文档（database-schema-ownership.md /
    three-table-schema.md）标注被取代留档。
