# 数据库设计：qed 库 qed_*/qt_* 表族（唯一事实源）

设计状态：Accepted
实现状态：Plan
最后更新：2026-08-16
需求方：QED-Engine（根仓库 REQ-026/REQ-029/REQ-030；2026-08-16 用户裁决知识层次重构）
关联代码：`src/qed_tracker/db/`（models/selection_repository/migrations）、`src/qed_tracker/database.py`、
`src/qed_tracker/courses.py`（courses/math.json，规划退役）
关联测试：`tests/test_db_models.py`、`tests/test_selection_repository.py`、`tests/test_selections_api.py`、
`tests/test_db_three_table_smoke.py`、`tests/test_courses.py`（实现轮同步更新）
关联 ADR：[ADR 0001](../adr/0001-tracker-service-architecture.md)；根仓库 [ADR 0003](../../../docs/adr/0003-shared-qed-database-independence.md)（命名空间隔离）与 [ADR 0009](../../../docs/adr/0009-shared-qed-tables.md)（2026-08-16：新增 qed_* 共享表族）

> **唯一事实源声明**：本文件是 qed 库全部 `qed_*`（共享）与 `qt_*`（QED-Tracker 私有）表的
> **唯一当前事实源文档**，取代 `database-schema-ownership.md`（QED-023 时代留档）与
> `three-table-schema.md`（三表模型，QED-028）。被取代文档保留只读、标注 Retired/Superseded，
> 不再作为实现依据。新增/修改表必须先更新本文件，再写 Alembic 迁移。

## 背景与动机

现三表模型（qt_selections / qt_downloads / qt_sources，QED-028）存在以下缺口：

1. **缺领域/课程层次**：领域（subject）只存在于 `courses/math.json` 静态 JSON，课程体系元数据
   （阶段/先修/别名）不在 DB，三项目无法共享；
2. **缺指引检索的简介**：教材/习题集简介（用于指引后续候选检索）无处存放；
3. **缺审计字段**：无 `created_by` / `updated_by`；
4. **不承载论文/博客**：论文走 arXiv 下载 + `meta/resources/` JSON（kind=paper），MySQL 无索引；
   博客（课程延展资料）完全不在模型内；
5. **粒度错位**：qt_selections 一条=一套书，「套」与「候选/决定/下载/验证」四段进度混杂，
   多卷教材靠 vols JSON 表达，下载与验收入口在 qt_downloads 跨表。

2026-08-16 用户裁决：**重构为「领域 → 课程 → 知识行（教程/资料归类）→ 书行 → 渠道」五层模型**，
领域/课程表为三项目共享（新前缀 `qed_*`），书行一行=一册/一卷/一个快照（取消册行表），
文件命名「物理名/展示名」分离，存量数据一次性迁移，旧表退役。

## 表清单（5 张新表 + 2 张退役）

```
qed_domain（领域，共享 qed_*）
  └── qed_course（课程，共享 qed_*）
        └── qt_knowledge（知识行，qt_* 私有：一套教程 / 一组课程延展资料）
              └── qt_books（书行：一册/一卷/一个快照，候选→决定→下载→验证全生命周期）
                    └── qt_sources（渠道尝试，一次一条）
```

| 表 | 前缀 | 所有权 | 一行= | 状态 |
| --- | --- | --- | --- | --- |
| `qed_domain` | 共享 | QED-Tracker 建表维护，其他项目只读 | 一个学科（math；预留扩展） | 本轮新增（规划迁移 0006） |
| `qed_course` | 共享 | 同上 | 一门课程（含阶段/先修/别名/顺序） | 本轮新增 |
| `qt_knowledge` | 私有 | QED-Tracker | kind=tutorial：一套教程；kind=other_material：课程延展资料归类 | 本轮新增 |
| `qt_books` | 私有 | QED-Tracker | 一个文件单元（书的一册/一篇论文/一个博客快照） | 本轮新增 |
| `qt_sources` | 私有 | QED-Tracker | 一次渠道尝试 | 迁移重建（外键改挂 book_id） |
| `qt_selections` / `qt_downloads` | 私有 | — | — | 存量迁移后退役（drop） |

## qed_domain 表结构（表1，共享）

```sql
CREATE TABLE qed_domain (
  domain_id     VARCHAR(32)   NOT NULL,           -- PK：math（学科标识，扩展预留）
  name          VARCHAR(100)  NOT NULL,           -- 显示名（数学）
  description   TEXT          NOT NULL,           -- 体系说明（迁自 courses/math.json）
  stages        JSON          NOT NULL,           -- 学习阶段顺序 ["本科基础","本科进阶","研究生基础","QE冲刺"]
  created_by    VARCHAR(16)   NOT NULL DEFAULT '',
  updated_by    VARCHAR(16)   NOT NULL DEFAULT '',
  created_at    DATETIME      NOT NULL,
  updated_at    DATETIME      NOT NULL,
  PRIMARY KEY (domain_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='qed_domain';
```

- 共享表：三项目可读；QED-Tracker 唯一写权限（Alembic 建表维护）。
- `stages` 为领域级阶段顺序（原 math.json 顶层 `stages`）。

## qed_course 表结构（表2，共享）

```sql
CREATE TABLE qed_course (
  course_id       VARCHAR(64)   NOT NULL,         -- PK：01_math_analysis（与 catalogs 对齐）
  domain_id       VARCHAR(32)   NOT NULL,         -- FK → qed_domain.domain_id；索引
  sort_order      INT           NOT NULL,         -- 学习顺序（原 courses[] 数组序，DAG 拓扑序）
  name            VARCHAR(200)  NOT NULL,         -- 规范名（数学分析）
  aliases         JSON          NOT NULL,         -- list[str]：别名（高等数学（工科称呼））
  stage           VARCHAR(32)   NOT NULL,         -- 所属阶段（qed_domain.stages 之一）
  prerequisites   JSON          NOT NULL,         -- list[str]：先修 course_id 数组（主知识链路 DAG）
  related_targets JSON          NOT NULL,         -- list[str]：已通过验收的关联 catalog 目标（现为空，随验收回填）
  note            VARCHAR(1000) NOT NULL DEFAULT '',
  created_by      VARCHAR(16)   NOT NULL DEFAULT '',
  updated_by      VARCHAR(16)   NOT NULL DEFAULT '',
  created_at      DATETIME      NOT NULL,
  updated_at      DATETIME      NOT NULL,
  PRIMARY KEY (course_id),
  KEY ix_qed_course_domain (domain_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='qed_course';
```

- **`courses/math.json` 退役**（2026-08-16 用户裁决）：表为课程体系唯一事实源；CLI/8903 改读表；
  `subject`/`stages` 迁入 qed_domain，`courses[]` 迁入本表（sort_order=数组序）。
- `related_targets` 规则延续主链路决策：只关联已通过二次确认评估（人工验收 approved）的课程目标。

## qt_knowledge 表结构（表3，私有）

一行 = 一套教程（kind=tutorial）或 一组课程延展资料归类（kind=other_material）。

```sql
CREATE TABLE qt_knowledge (
  knowledge_id    VARCHAR(100)  NOT NULL,         -- PK：kn_<md5>（稳定，候选期即生成）
  domain_id       VARCHAR(32)   NOT NULL,         -- 冗余领域（与 qed_course 一致）；索引
  course_id       VARCHAR(64)   NOT NULL,         -- FK → qed_course.course_id；索引
  kind            VARCHAR(24)   NOT NULL,         -- tutorial / other_material
  set_no          VARCHAR(4)    NOT NULL DEFAULT '', -- 套标记 "1"~"4" 中文 / "en" 英文对照 / ''（资料归类行）
  name            VARCHAR(200)  NOT NULL DEFAULT '', -- 教程名/归类名（数学分析 套一 / 01-数学分析-延展资料）
  textbook_ref    JSON          NULL,             -- 教材决定 {title, version}；多卷同 title 自动归入；other_material=NULL
  exercise_ref    JSON          NULL,             -- 习题集决定 {title, version}；教材含习题时可为 NULL
  textbook_intro  TEXT          NOT NULL,         -- 教材简介，指引检索（LLM 预填 + 人工审）
  exercise_intro  TEXT          NOT NULL,         -- 习题集简介，指引检索
  materials_intro TEXT          NOT NULL,         -- 延展资料归类简介（kind=other_material 用；指引论文/博客检索）
  status          VARCHAR(24)   NOT NULL,         -- 索引；KnowledgeStatus 枚举
  reject_reason   VARCHAR(1000) NOT NULL DEFAULT '',
  supersede_reason VARCHAR(1000) NOT NULL DEFAULT '',
  created_by      VARCHAR(16)   NOT NULL DEFAULT '',
  updated_by      VARCHAR(16)   NOT NULL DEFAULT '',
  created_at      DATETIME      NOT NULL,
  confirmed_at    DATETIME      NULL,
  completed_at    DATETIME      NULL,
  rejected_at     DATETIME      NULL,
  superseded_at   DATETIME      NULL,
  updated_at      DATETIME      NOT NULL,
  PRIMARY KEY (knowledge_id),
  KEY ix_qt_knowledge_course (course_id),
  KEY ix_qt_knowledge_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='qt_knowledge';
```

- **状态机**：`draft`（探索中）→ `confirmed`（定稿，简介/决定引用确认）→ `completed`
  （所辖书行全部 verified）；`rejected` / `superseded` 终态（彻底隐藏，仅 DB 留痕）。
- **创建时机**（2026-08-16 用户裁决）：探索开始时建 draft（mainline new 落库），定稿时
  （mainline review）LLM 预填两段简介 + 人工审，转 confirmed；下载进度不冗余在知识行
  （由书行聚合）。
- **决定引用**：`textbook_ref` / `exercise_ref` 存 `{title, version}`（书名级引用，不含逐册）；
  多卷书行同 `title`（part 不同）自动归入该引用。候选/决定/下载/验证状态仍在书行。

## qt_books 表结构（表4，私有）

一行 = 一册/一卷/一个快照（书的一卷、一篇论文、一个博客快照）；**取消独立册行表**
（2026-08-16 用户裁决）：多卷按「XXX 第一册 / 第二册」写成独立书行（part 区分）。

```sql
CREATE TABLE qt_books (
  book_id         VARCHAR(100)  NOT NULL,         -- PK：bk_<md5>（稳定）
  knowledge_id    VARCHAR(100)  NOT NULL,         -- FK → qt_knowledge.knowledge_id；索引
  kind            VARCHAR(16)   NOT NULL,         -- textbook / exercise / supplement / paper / blog / other
  roles           JSON          NOT NULL,         -- list[str]：textbook/exercise/solutions…（教材含习题 → ["textbook","exercise"]）
  title           VARCHAR(500)  NOT NULL,         -- 书名（不含卷，如 微积分学教程）
  part            VARCHAR(32)   NOT NULL DEFAULT '', -- 卷标识：'' / 第一册 / 上册 / 博文一、二、三…
  display_title   VARCHAR(500)  NOT NULL,         -- 展示名 = title+part，可人工覆盖，不含 hash
  file_name       VARCHAR(500)  NOT NULL DEFAULT '', -- 实际落盘文件名（display 的 slug + sha256 前 8）
  authors         JSON          NOT NULL,         -- list[str]
  language        VARCHAR(8)    NOT NULL DEFAULT '',
  version         JSON          NOT NULL,         -- {edition, publisher, year, detail}
  source          JSON          NULL,             -- 候选来源/下载方案（provider/page_url/download_url/links）
  original_url    VARCHAR(1000) NOT NULL DEFAULT '', -- 博客/网页原始 URL；paper 为 arXiv 页
  sha256          VARCHAR(64)   NULL,             -- UNIQUE；下载成功后回填（候选期 NULL）
  relative_path   VARCHAR(500)  NOT NULL DEFAULT '', -- 相对数据根路径（raw/books/...）
  absolute_path   VARCHAR(1000) NOT NULL DEFAULT '', -- QED-Engine dataset 目录下的绝对路径，验证后回填
  page_count      INT           NULL,
  status          VARCHAR(24)   NOT NULL,         -- 索引；BookStatus 枚举
  reject_reason   VARCHAR(1000) NOT NULL DEFAULT '',
  rejected_by     VARCHAR(16)   NOT NULL DEFAULT '',
  supersede_reason VARCHAR(1000) NOT NULL DEFAULT '',
  review_note     VARCHAR(1000) NOT NULL DEFAULT '', -- 审理备注
  created_by      VARCHAR(16)   NOT NULL DEFAULT '',
  updated_by      VARCHAR(16)   NOT NULL DEFAULT '',
  created_at      DATETIME      NOT NULL,
  decided_at      DATETIME      NULL,
  downloaded_at   DATETIME      NULL,
  verified_at     DATETIME      NULL,
  rejected_at     DATETIME      NULL,
  superseded_at   DATETIME      NULL,
  updated_at      DATETIME      NOT NULL,
  PRIMARY KEY (book_id),
  UNIQUE KEY uq_qt_books_knowledge_title_part (knowledge_id, title, part),
  UNIQUE KEY uq_qt_books_sha256 (sha256),
  KEY ix_qt_books_knowledge (knowledge_id),
  KEY ix_qt_books_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='qt_books';
```

- **唯一性**：`uq_qt_books_knowledge_title_part`（同套同书同卷不重复建行）；
  `sha256` 全局唯一（幂等复用既有记录）。
- **状态机（四段，即用户「候选书目 → 最终决定书目 → 下载成功书目 → 确认下载正确书目」）**：

  ```text
  candidate ──decided（人工决定下载，录 decided_at）──→ decided
      │   │                                              │
      │   └──rejected（否定候选，原因必填）                │──→ downloading（任务运行中）
      │                                                  │      │
      │                                              downloaded（sha256+path 回填）
      │                                                  │──→ verified（人工验收确认正确）
      │                                                  └──→ rejected（文件硬删留痕）
      │──superseded（版本换代留痕，原因必填）←──decided/downloaded──┤
  ```

  - `downloading → failed`（下载失败，可重试 → downloading）；`candidate → downloaded`
    允许（人工下载登记 register 直转，需 sha256+path 已登记）。
  - `verified` 为终态（知识行 completed 由所辖书行全 verified 聚合触发）；
    `superseded` 允许从 candidate/decided/downloaded（版本换代留痕）。
  - rejected / superseded 为终态（彻底隐藏：任何接口默认过滤，仅 DB 留痕）。
- **命名规矩（2026-08-16 用户裁决）**：下载时 `.part` 临时区 → 校验通过后按 `file_name`
  原子改名落盘；`file_name` = display_title 规范 slug + sha256 前 8（物理名可含 hash）；
  `display_title` 只展示、不含 hash。用户界面只见展示名。
- **absolute_path**：QED-Engine dataset 目录下的绝对路径（如
  `D:\coding\QED-Engine\dataset\qed-tracker\raw\books\...`），验证/移交后回填，供人工打开核对。

## qt_sources 表结构（表5，私有）

现状延续，仅外键更名挂书行。

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='qt_sources';
```

- 无状态机：一次渠道尝试一条记录；`ok` 表达成败。失败尝试留痕不展示（详情只展示 ok=1 来源）。
- **定位（2026-08-16 用户确认）**：目的是了解**最终某本书是从哪个渠道获取成功的**（成功渠道
  归因），支撑渠道有效性评估与后续课程下载流程优化。历史参考意义有限——数学分析 12 册中约
  10 册由人工（manual）获取：**当前阶段以固定当前课程（定稿固化）为主，渠道优化流程从下一门
  课程开始**；表结构不变，记录即优化依据。

## 状态机汇总与迁移合法性

| 层 | 状态机 | 终态 | 非法迁移（API 409） |
| --- | --- | --- | --- |
| qt_knowledge | draft → confirmed → completed；draft/confirmed → rejected；confirmed/completed → superseded | rejected、superseded | completed 之后除 superseded 外任何迁移；终态任何迁移 |
| qt_books | candidate → decided → downloading → downloaded → verified；candidate/decided/downloaded → rejected；downloading → failed（→downloading 重试）；candidate → downloaded（register 直转，需 sha256+path）；candidate/decided/downloaded → superseded | verified、rejected、superseded | 终态任何迁移；downloaded 前须已登记 sha256+path；candidate → failed 不允许 |
| qt_sources | 无（仅 ok 标记） | — | — |

## 一次性存量迁移（迁移 0006 之后执行，服务端脚本）

| 存量 | 映射目标 |
| --- | --- |
| `courses/math.json` | qed_domain（subject/stages/name/description）+ qed_course（courses[]，sort_order=数组序） |
| `qt_selections`（一套书） | qt_knowledge（kind=tutorial；set_no；name=套名；textbook_ref/exercise_ref 由决定书行回填；简介先留空待 LLM 预填）+ 拆出书行 |
| `qt_selections.authors/roles/version` | 各书行 |
| `qt_downloads`（一册） | qt_books（一册一行：title 拆分卷名 → part；display_title=title+part；sha256/relative_path/page_count/status 映射；absolute_path 由 relative_path 拼数据根） |
| `qt_sources` | qt_sources（外键改挂新 book_id） |

- 幂等可重放：以 `knowledge_id`（=套内容 MD5）与书行 `sha256`/`title+part` 为幂等键。
- 迁移前全量备份快照（迁移测试用）；确认无误后 drop `qt_selections` / `qt_downloads`。
- 主链路 JSON（`meta/main-line/`）存量已按 QED-028 并入三表，随本次迁移一并入新表。

## 共享表所有权与根仓库契约变更

- **表命名空间**（根仓库 [ADR 0009](../../../docs/adr/0009-shared-qed-tables.md) 补充 0003，需同步 QED-Engine）：
  - `qt_*`：QED-Tracker 私有；`af_*`：Axiom-Flow 私有（不变）；
  - **新增 `qed_*` 共享前缀表族**（qed_domain / qed_course）：所有权 QED-Tracker
    （Alembic 建表维护），其他项目只读不写；共享表 schema 变更须先经根仓库登记。
- 根仓库 `docs/design/database-design.md` 登记 qed_* 表清单与所有权；
  `docs/design/service-contracts.md` 同步「共享表 + 只读」约定。
- 本仓库 `courses/math.json` 退役（数据迁入 qed_course；`pyproject.toml` package-data 同步移除）。

## 接口/契约影响

- CLI/8903：课程体系读取改读 qed_course（`courses list/show` 语义不变）；书单/主链路
  `mainline` 命令族改读写 qt_knowledge/qt_books（new/review/download/verify/approve/reject 映射
  到新状态机）；channels 汇总仍读 qt_sources。
- 书行 `candidate → decided` 对应旧表1 `candidate → confirmed`；`verified` 对应旧表2 `approved`。
- 论文/博客：进入 qt_books（kind=paper/blog），快照落盘统一链路（HTML→PDF 或归档，实现计划明确）。

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
   知识行一行=一套教程。
3. **共享机制**：改根仓库契约（ADR 0003 / database-design.md / service-contracts.md），
   QED-Tracker 建表维护，其他项目只读。
4. **知识行粒度**：一行=一套教程；教程选择（教材/习题集）为决定引用（书名+版本），
   候选书目存书行（状态机四段：候选/决定/下载成功/确认正确）。
5. **简介生成时机**：探索定稿时 LLM 预填 + 人工审（指引后续检索）；知识行探索开始即建
   draft，定稿转 confirmed。
6. **课程 JSON 退役**：courses/math.json 数据迁入 qed_course，表为主、JSON 退役。
7. **多卷教材建模**：取消册行表，书行一行=一册/一卷/一个快照（part 区分）；教材含习题 →
   书行 roles 标注，不另建行；论文/博客入书行（kind=paper/blog），知识行 kind=other_material
   作为课程延展资料归类行。
8. **博客落盘**：快照落盘统一链路（非 PDF 也产生文件），不存 URL 了事。
9. **文件命名**：物理名（display slug + 短 hash）/ 展示名（不含 hash）分离；下载校验成功后
   改名落盘；qt_books 增 `absolute_path`（QED-Engine dataset 目录绝对路径）。
10. **唯一数据库设计文档**：本文件为唯一事实源，旧设计文档（database-schema-ownership.md /
    three-table-schema.md）标注被取代留档。
