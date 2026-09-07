# ADR 0007：数据库设计文档按表族拆分（共享/专用两文 + DDL 展示统一）

状态：Accepted
日期：2026-09-07
最后更新：2026-09-07
领域：工程治理
决策阶段：v0.1
取代：[ADR 0005](0005-shared-tables-doc-location.md)（部分——仅其决定③「全库 DDL 单文档两区」条款）
被取代：—

## 背景

QED-044 文档收敛轮发现数据库设计文档的三个问题：

1. **单文档两区耦合两表族**：`architecture/database-schema.md` 以「共享表（`qed_*`）+
   项目专用表（`qt_*`）」两区承载全库 DDL，跨项目契约（`qed_*`，根仓库登记同步）与本项目
   私有实现（`qt_*`，随本项目自由演进）耦合在同一文件，违反「一个事实一个维护位置」的
   粒度要求——两表族的读者、同步节奏与变更主体都不同。
2. **DDL 展示风格不一致**：qt_knowledge / qt_books 的 DDL 用代码块内 `-- ====` 头注释与
   多行悬挂的 `COMMENT '...'` 子句，与 `qed_*` 表的紧凑风格（行尾 `--` 注释）不一致，可读性差。
3. **迁移史口径过时**：shared-tables.md 的「迁移史」节仍按 Alembic 链表述，与
   [ADR 0006](0006-database-model-as-schema-rebuild.md)（Alembic 链退役、模型即 schema +
   `ensure_schema` 重建自愈）冲突。

2026-09-07 用户裁决按表族拆分为两份架构文档（QED-044 承载实施）。

## 决定

1. **`architecture/shared-tables.md` 改名 `architecture/database-shared-tables.md`**
   （H1：数据库共享表设计）：三张共享表（qed_domain / qed_course / qed_llm_calls）完整设计
   （DDL、列说明、状态机、写权限、Schema 变更流程）与「在本项目中的作用」的唯一事实源。
2. **`architecture/database-schema.md` 改名 `architecture/database-private-tables.md`**
   （H1：数据库专用表设计）：五张专用表（qt_knowledge / qt_books / qt_sources / qt_tasks /
   qt_selections）完整设计的唯一事实源，并承载全库表清单与五层模型链路图；共享表文档只保留
   三表 ER 子图。
3. **两文互链互不复制**：一个事实一个维护位置——共享表契约条款（写权限、状态机写主体、
   Schema 变更流程、根仓库登记回执）只在共享表文档；qt 表 DDL 只在专用表文档。
4. **DDL 展示统一规范**（两文同一套规则）：紧凑 CREATE TABLE、每列一行、行尾 `--` 短注释、
   注释不换行；表名/用途/一行=什么写在代码块外正文；超长列语义用代码块外「列说明表」承载；
   真实 DDL 的表/列中文注释事实源仍为 ORM 模型 `comment=`（ADR 0006），文档展示风格与其解耦。
5. **ADR 0005 决定①②继续有效**：共享表文档归属 QED-Tracker、根仓库 `database-design.md`
   登记同步点、「共享表 schema 变更先经根仓库登记」流程均不变；本 ADR 仅取代其决定③
   （database-schema.md 保持全库 DDL 事实源地位、单文档分共享/专用两区）。

## 后果

- 好处：共享表契约文档对根仓库的同步面更小更稳（只含三张共享表）；qt_* 文档随本项目独立
  演进，不再牵动跨项目登记；DDL 展示可扫读、两文风格一致。
- 成本：一次全库引用替换（约 25 + 15 处：AGENTS.md、doc-governance、code-map、design/plans/
  trackers 交叉引用、守护白名单与源码注释三处）；API 设计文档同轮按六要素重写（QED-044，
  属不改语义的文档整理，不另立 ADR）。
- 风险：根仓库侧对 `shared-tables.md` 的引用路径在回执同步前出现旧路径——本仓库侧由
  `tests/test_documentation.py` 白名单与 `rg` 清零检查兜底；根仓库侧以回执任务跟踪。

## 关联

- 关联标准：[文档治理规范](../standards/doc-governance.md)（一个事实一个维护位置、
  版本末期文档整理清单）
- 关联文档：[数据库共享表设计](../architecture/database-shared-tables.md)、
  [数据库专用表设计](../architecture/database-private-tables.md)、
  [QED-Tracker API 设计文档（8901）](../architecture/api.md)
- 关联 ADR：[ADR 0005](0005-shared-tables-doc-location.md)（部分取代）、
  [ADR 0006](0006-database-model-as-schema-rebuild.md)（模型即 schema 口径）
- 承载任务：QED-044（完整数据库设计文档与 API 设计文档，todo 登记）
