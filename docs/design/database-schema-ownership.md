# 数据库设计：qt_* 表结构（qed 库）

设计状态：Retired
实现状态：Retired（QED-030：qt_resources 已 drop；2026-08-16 知识层次重构后整体被
[database-schema.md](database-schema.md) 取代）
最后更新：2026-08-16
关联代码：`src/qed_tracker/db/`（models/selection_repository/migrations）、`src/qed_tracker/database.py`
关联测试：`tests/test_db_models.py`、`tests/test_selection_repository.py`、`tests/test_db_three_table_smoke.py`
关联 ADR：[ADR 0001](../adr/0001-tracker-service-architecture.md)；承接根仓库 ADR 0003（共享 qed 库、表命名空间隔离）
需求方：QED-Engine（根仓库 REQ-026，QED-023；2026-08-09 用户裁决：qt_* 表结构由本仓库确认并维护）

> **退役声明（2026-08-16）**：本文描述的 qt_resources 登记索引已随 0005_drop_resources 删除；
> QED-028 三表模型（qt_selections/qt_downloads/qt_sources）已随知识层次重构被
> [database-schema.md](database-schema.md)（qed_domain/qed_course/qt_knowledge/qt_books/qt_sources
> 五层模型）取代。**本文仅作历史留档，不再作为当前依据。**

> 本文是 **QED-Tracker 数据库设计的事实源文档**：qed 库 `qt_*` 表的清单、结构、索引与迁移。
> 跨项目约定（共享 qed 库实例、表命名空间隔离）见根仓库 ADR 0003 与
> [database-design.md](../../../docs/design/database-design.md)（根仓库指引与规划）。

## 背景与边界

- 三项目共享 `qed` 库（根仓库 ADR 0003），**本仓库只使用 `qt_*` 前缀表**；Axiom-Flow 用 `af_*`。
- 资源事实源 = 数据根 `meta/resources/<sha256>.json`（单资源 JSON，schema 不变）；MySQL
  `qt_resources` 为**查询/展示索引**，双写一致性由登记服务保证（落盘 → 资源 JSON → MySQL，
  任一步失败任务失败且可重放）。
- 无 `QED_DB_PASSWORD` 时降级运行（服务可起，索引写跳过）。

## 表清单

| 表 | 用途 | 状态 |
| --- | --- | --- |
| `qt_resources` | 资源登记查询索引（候选/确认/下载/验收/拒绝全状态） | 已实现（迁移 0001 + 0002） |

新增表规则：先在本文件登记表清单与结构（先文档后实现），再写 Alembic 迁移。

## qt_resources 表结构

```sql
CREATE TABLE qt_resources (
  resource_id   VARCHAR(100)  NOT NULL,           -- 主键：cand_<md5>（候选期）/ sha256:<digest>（下载后）
  sha256        VARCHAR(64)   NULL,               -- 唯一（uq_qt_resources_sha256）
  kind          VARCHAR(16)   NOT NULL,           -- book / exercise / supplement / paper
  title         VARCHAR(500)  NOT NULL,
  authors       JSON          NOT NULL,           -- list[str]
  language      VARCHAR(8)    NOT NULL DEFAULT '',
  year          VARCHAR(16)   NOT NULL DEFAULT '',
  edition       VARCHAR(64)   NOT NULL DEFAULT '',
  source        JSON          NOT NULL,           -- 来源名/ID/URL/检索时间（dict）
  retrieved_at  DATETIME      NULL,
  relative_path VARCHAR(500)  NOT NULL DEFAULT '',
  page_count    INT           NULL,
  status        VARCHAR(24)   NOT NULL,           -- 索引；ResourceStatus 枚举
  llm_evaluation JSON         NULL,               -- LLM 评估（可审阅，不写资源事实）
  catalog_ref   JSON          NULL,               -- {catalog_id, course_id, target_id}
  confirmed_at  DATETIME      NULL,
  downloaded_at DATETIME      NULL,
  approved_at   DATETIME      NULL,
  rejected_at   DATETIME      NULL,
  reject_reason VARCHAR(1000) NOT NULL DEFAULT '',
  rejected_by   VARCHAR(16)   NOT NULL DEFAULT '',
  review_note   VARCHAR(1000) NOT NULL DEFAULT '', -- 人工评审建议（QED-020 增列）
  created_at    DATETIME      NOT NULL,
  PRIMARY KEY (resource_id),
  UNIQUE KEY uq_qt_resources_sha256 (sha256),
  KEY ix_qt_resources_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

- **引擎/字符集**：InnoDB + utf8mb4（中文内容）。
- **resource_id 迁移**：候选期 `cand_<md5>`；下载登记后迁移为 `sha256:<digest>`（主键由
  `cand_<md5>` 迁移，同 sha256 幂等复用既有记录）。
- **status 状态机**：candidate / confirmed / downloading / downloaded / approved / rejected /
  failed / pending_manual / not_found / backup（轻量迁移同步，非法迁移 409）。
- **双写**：JSON 事实源为唯一事实；qt_resources 仅查询索引。登记顺序落盘 → 资源 JSON → MySQL。

## 迁移管理

- Alembic（`alembic.ini` + `src/qed_tracker/migrations/`），URL 由 `QED_DB_*` 构造不写死；
  迁移脚本须保持**纯 ASCII**（Windows locale 编码读取，`migrations/env.py` 声明）。
- 迁移应用入口 `upgrade_database()`（服务启动与冒烟复用）。
- 已应用迁移：`0001_qt_resources`（建表）、`0002_review_note`（review_note 增列，QED-020）。

## 现状与成功标准（QED-023 回执）

- 本文件 + `src/qed_tracker/db/` 迁移为 `qt_*` 表结构事实源（tracker-service.md 链接本文件）。
- 确认后回执根仓库 REQ-026；根仓库 database-design.md 补登记 qt_* 表清单摘要并收尾为指引与规划。
