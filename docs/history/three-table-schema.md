# 三表模型数据库设计：qt_selections / qt_downloads / qt_sources

设计状态：Superseded
实现状态：Superseded（2026-08-16：被 [database-schema.md](database-schema.md) 知识层次重构
（qed_domain/qed_course/qt_knowledge/qt_books/qt_sources）取代）
最后更新：2026-08-16
关联代码：`src/qed_tracker/db/`（models/knowledge_repository/migrations）、`src/qed_tracker/database.py`
关联测试：`tests/test_db_models.py`、`tests/test_knowledge_repository.py`、`tests/test_knowledge_api.py`、`tests/test_db_three_table_smoke.py`
关联 ADR：[ADR 0001](../adr/0001-tracker-service-architecture.md)；承接根仓库 ADR 0003（共享 qed 库、表命名空间隔离）
需求方：QED-Engine（根仓库 REQ-029/REQ-030，QED-028/029；2026-08-13 用户裁决三表模型）
模型视图与 API 契约：根仓库 [downloads-three-table-model.md](../../../docs/design/downloads-three-table-model.md)

> **取代声明（2026-08-16）**：本文描述的 qt_selections/qt_downloads/qt_sources 三表模型已被
> [database-schema.md](database-schema.md)（领域 → 课程 → 知识行 → 书行 → 渠道五层模型）取代：
> qt_selections → qt_knowledge + qt_books，qt_downloads → qt_books（一册一行，title+part），
> qt_sources 外键改挂书行。**本文仅作历史留档（QED-028/029 时代），不再作为实现依据。**

## 背景与动机

qt_resources 一张表混装候选/确认/下载/验收/否定 10 态，无「一套书」概念（册数靠
target id 后缀 `01-fikhtengolts-v1` 表达）；主链路 JSON（`meta/main-line/`）独立维护
课程→教材条目→验收移交，五要素与资源体系统全解耦。双轨并存 → 数据分散、状态语义
不一、前端无法分层展示。用户裁决（2026-08-13）：**统一为三表，逐级一对多**。

```
qt_selections（选课表，一条=一套书）
  └── qt_downloads（册级下载明细，FK selection_id）
        └── qt_sources（渠道尝试，FK download_id）
```

## 表清单

| 表 | 用途 | 状态 |
| --- | --- | --- |
| `qt_resources` | 资源登记查询索引（旧状态机，迁移后退役只读） | 已实现（迁移 0001 + 0002）；本轮新增 0003 |
| `qt_selections` | 选课表/书单（第一阶段选定的课程与书籍，一条=一套书） | 本轮新增（迁移 0003） |
| `qt_downloads` | 册级下载明细（各教材/习题集下载情况，一册一条） | 本轮新增（迁移 0003） |
| `qt_sources` | 渠道尝试（人工/自动渠道下载记录，一次尝试一条） | 本轮新增（迁移 0003） |

## qt_selections 表结构（表1）

```sql
CREATE TABLE qt_selections (
  selection_id    VARCHAR(100)  NOT NULL,           -- PK：cand_<md5>（候选期），确认后保持稳定（不迁移主键）
  course_id       VARCHAR(64)   NOT NULL,           -- 所属课程；索引
  title           VARCHAR(500)  NOT NULL,           -- 套书主标题（如《微积分学教程》）
  authors         JSON          NOT NULL,           -- list[str]
  roles           JSON          NOT NULL,           -- list[str]：textbook/exercises/solutions/reference（一套可兼教材+习题集）
  version         JSON          NOT NULL,           -- {edition, publisher, year, language, detail}
  vols            JSON          NOT NULL,           -- list[str]：册列表 ["v1","v2","answers"]（单册为 []）
  set_no          VARCHAR(4)    NOT NULL DEFAULT '',-- 套标记 "1"~"4" 中文 / "en" 英文对照 / '' 无配套
  evaluation      JSON          NULL,               -- LLM 预填 来源/文本/权威性/套候选（可审阅，候选期填充）
  note            VARCHAR(1000) NOT NULL DEFAULT '',-- 评审建议（人工填写）
  status          VARCHAR(24)   NOT NULL,           -- 索引；SelectionStatus 枚举
  reject_reason   VARCHAR(1000) NOT NULL DEFAULT '',
  rejected_by     VARCHAR(16)   NOT NULL DEFAULT '',
  supersede_reason VARCHAR(1000) NOT NULL DEFAULT '',-- superseded 原因（被新版本替代）
  created_at      DATETIME      NOT NULL,
  confirmed_at    DATETIME      NULL,
  superseded_at   DATETIME      NULL,
  rejected_at     DATETIME      NULL,
  PRIMARY KEY (selection_id),
  KEY ix_qt_selections_course (course_id),
  KEY ix_qt_selections_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='qt_selections';
```

- **status 状态机（表1 生命周期）**：`candidate → confirmed / backup / rejected`；
  `confirmed → superseded`（被新版本替代，人工在评估/评审时执行）；`backup → confirmed`
  （备选转正，可逆）。rejected/superseded 为**终态**（彻底隐藏：任何接口默认过滤，
  仅 DB 留痕，前端无查看入口）。
- **selection_id**：候选期 `cand_<md5>`；确认后**保持稳定**（与 qt_resources 主键迁移
  不同，避免级联改表2 外键；「一条=一套书」身份即 MD5 内容身份）。
- **彻底隐藏语义**：列表/详情接口 `status NOT IN ('rejected','superseded')` 默认过滤
  （数据层实现，前端不依赖展示层过滤）。

## qt_downloads 表结构（表2）

```sql
CREATE TABLE qt_downloads (
  download_id     VARCHAR(100)  NOT NULL,           -- PK：download_<md5>
  selection_id    VARCHAR(100)  NOT NULL,           -- FK → qt_selections.selection_id；索引
  vol             VARCHAR(32)   NOT NULL DEFAULT '',-- 册标识 "v1"/"answers"；单册条目为空串
  roles           JSON          NOT NULL,           -- list[str]：册级角色；默认继承表1 roles，可显式覆盖（如 answers 册 = ["solutions"]）
  file_hint       VARCHAR(200)  NOT NULL DEFAULT '',-- 册提示（如「第三版 上」「习题答案」）
  sha256          VARCHAR(64)   NULL,               -- 唯一（uq_qt_downloads_sha256）
  relative_path   VARCHAR(500)  NOT NULL DEFAULT '',
  page_count      INT           NULL,
  status          VARCHAR(24)   NOT NULL,           -- 索引；DownloadStatus 枚举
  reject_reason   VARCHAR(1000) NOT NULL DEFAULT '',
  rejected_by     VARCHAR(16)   NOT NULL DEFAULT '',
  review_note     VARCHAR(1000) NOT NULL DEFAULT '',-- 审理备注（审理=人工打开绝对路径核对后填写）
  created_at      DATETIME      NOT NULL,
  downloaded_at   DATETIME      NULL,
  approved_at     DATETIME      NULL,
  rejected_at     DATETIME      NULL,
  PRIMARY KEY (download_id),
  UNIQUE KEY uq_qt_downloads_sha256 (sha256),
  KEY ix_qt_downloads_selection (selection_id),
  KEY ix_qt_downloads_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='qt_downloads';
```

- **status 状态机（表2，册级）**：`candidate → downloading → downloaded → approved / rejected`；
  `downloading → failed`（可重试 → downloading；重试经 candidate 再发起）；`candidate → downloaded`
  允许（人工下载登记 register 直转，qed-021 语义延续；需 sha256+path 已登记）。
  **验收（approve/reject）在表2 册级**，reject 必填 reject_reason，**硬删 + 留痕**（reject 后文件从数据根删除，DB 记录保留）。
- **candidate 态**：册下载的**预登记**——下载任务发起时先落 candidate（表1 confirmed 条目下
  按 vols 创建或人工显式预登记），任务启动转 downloading，完成转 downloaded。2026-08-13
  用户裁决：表2 需 candidate 态（先登记再下载，登记不成功不产生 downloading）。
- **册级 roles（2026-08-13 用户裁决）**：表2 `roles` 为册级独立角色列，**默认继承表1 套级
  roles**，册级可显式覆盖（如陈纪修 answers 册 = `["solutions"]`）；套内不同册类型不同时
  （教材册 textbook + 答案册 solutions）必须显式区分，前端展示与完成度聚合按册级 roles 判定。
- **表1 完成度聚合**：表1 条目的下载/验收进度由表2 各册 status 聚合（如
  「已下载 x/y 册」「approved x/y 册」），不冗余存表1。

## qt_sources 表结构（表3）

```sql
CREATE TABLE qt_sources (
  source_id       VARCHAR(100)  NOT NULL,           -- PK：src_<md5>
  download_id     VARCHAR(100)  NOT NULL,           -- FK → qt_downloads.download_id；索引
  channel         VARCHAR(24)   NOT NULL,           -- manual / internet_archive / open_library / google_books / libgen_li
  provider_id     VARCHAR(200)  NOT NULL DEFAULT '',-- 渠道内资源标识
  page_url        VARCHAR(1000) NOT NULL DEFAULT '',
  download_url    VARCHAR(1000) NOT NULL DEFAULT '',
  file_keywords   VARCHAR(500)  NOT NULL DEFAULT '',-- 多关键词空格分隔（人工下载检索词）
  ok              TINYINT(1)    NOT NULL DEFAULT 0,-- 尝试是否成功（失败尝试留痕不展示）
  note            VARCHAR(1000) NOT NULL DEFAULT '',
  attempted_at    DATETIME      NOT NULL,
  PRIMARY KEY (source_id),
  KEY ix_qt_sources_download (download_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='qt_sources';
```

- 表3 无状态机：一次渠道尝试一条记录；`ok` 表达成败。**失败尝试留痕不展示**（详情弹窗
  只展示 ok=1 的来源；失败记录仅供 source-discovery 矩阵统计与排查）。
- `manual` 渠道：人工下载登记时生成（register 端点），file_keywords 存人工检索词。

## 状态机汇总与迁移合法性

| 层 | 状态机 | 终态 | 非法迁移（API 409） |
| --- | --- | --- | --- |
| 表1 qt_selections | candidate → confirmed/backup/rejected；confirmed → superseded；backup ⇄ confirmed | rejected、superseded | confirmed→candidate；rejected/superseded 任何迁移 |
| 表2 qt_downloads | candidate → downloading → downloaded；downloaded → approved/rejected；downloading → failed（可重试）；**candidate → downloaded（人工 register 直转，QED-021 语义延续 + D7 先登记再下载）** | approved、rejected | approved/rejected 任何迁移；downloading→downloaded 需已登记（sha256+path 非空）；candidate→downloaded（register）与 downloading→downloaded 均需 sha256+path 非空；candidate→failed 不允许 |
| 表3 qt_sources | 无（仅 ok 标记） | — | — |

## 一次性迁移（存量合并，迁移脚本 0003）

现有存量按映射导入三表，迁移完成后旧存储退役（qt_resources 不再写入、主链路 JSON
不再产生新数据；旧数据只读保留）。

| 存量 | 映射目标 |
| --- | --- |
| qt_resources `approved` | 表1 `confirmed`（edition/language → version；catalog_ref.course_id/target_id → course_id/set_no 推导） + 表2 对应册 `approved`（sha256/relative_path/page_count/vol 由 target_id 后缀推导） |
| qt_resources `confirmed` | 表1 `confirmed` + 表2 册 `downloaded`（按 downloaded_at 实际状态） |
| qt_resources `backup` | 表1 `backup` |
| qt_resources `rejected/not_found` | 表1 `rejected`（保留 reject_reason/rejected_by）——彻底隐藏 |
| qt_resources `downloading/failed/pending_manual/候选态` | 按实际状态映射表1 candidate/backup + 表2 downloading/failed |
| qt_resources `source`(JSON) | 表3 渠道记录（provider_id/page_url/download_url/retrieved_at→attempted_at → ok 按实际） |
| 主链路 JSON 条目（meta/main-line/<course_id>/<entry_id>.json） | 表1 条目（version/evaluation/advice→note；status reviewed+→confirmed、downloading→confirmed+表2 downloading、downloaded→confirmed+表2 downloaded、approved→confirmed+表2 approved、rejected→表1 rejected 留痕） |
| 主链路 `channels[]` | 表3 渠道尝试（channel/attempted_at/ok/note） |
| 主链路 `final_path` | 表2 `relative_path` |

- **册级 roles 迁移规则**：表2 行 roles 默认继承所在套（表1）roles；`vol`/`file_hint` 含
  「答案/解答/解析/题解」语义（如 `answers`、`01-demidovich_吉米多维奇数学分析习题集_2010`
  对应的 `01-feidinghui` 题解、`file_hint=习题答案`）→ 册级 roles=`["solutions"]`；否则继承。

- 迁移幂等可重放：以 sha256/主链路 entry_id 为幂等键，重复执行不产生重复行。
- 迁移前全量备份快照（迁移测试用）。
- **主链路 JSON 迁移后删除**（2026-08-13 用户裁决）：备份快照确认无误后，已导入的主链路
  JSON（`meta/main-line/`）物理删除；qt_resources 表与 `meta/resources/` JSON 保留只读
  （一致性仍在，退役标注）。
- 迁移脚本纯 ASCII（Alembic 迁移约定）。

## 迁移管理

- 新迁移 `0003_three_table`（修订号 `0003_three_table`，down_revision `0002_review_note`）：
  建三表；不删 qt_resources（退役只读）；数据迁移放服务端一次性脚本（独立模块，位于
  `src/qed_tracker/application/` 下，可重复运行，成功标志落 `meta/migrations/three_table.marker`）。
- 迁移应用入口沿用 `upgrade_database()`。

## 成功标准（QED-028 回执）

- 三表 DDL/迁移 + 状态机合法性测试（非法迁移 409）+ 存量迁移幂等测试全绿。
- API 契约（QED-029）与根仓库 [downloads-three-table-model.md §3](../../../docs/design/downloads-three-table-model.md)
  对齐：接口默认过滤 rejected/superseded/failed(表2 rejected/failed 默认过滤)；彻底隐藏验证
  （直接调接口亦不可见）。
- 回执根仓库 REQ-029/REQ-030（提交号 + 测试输出）。

## 用户裁决记录（2026-08-13）

1. **表2 需 candidate 态**：先登记再下载——下载任务发起时落 candidate，任务启动转
   downloading，完成转 downloaded（已并入表2 状态机）。
2. **主链路 JSON 迁移后旧文件可删除**：备份快照确认后物理删除（已并入迁移约定）。
3. **表1 backup 转正语义确认**：与旧 qt_resources 的 backup 转正（QED-017 三态）保持一致
   （backup ⇄ confirmed 可逆）。