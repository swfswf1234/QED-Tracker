# v0.1 数据库重构实施计划

状态：Current
任务类型：B
最后更新：2026-09-06
需求方：QED-Tracker（QED-053，[ADR 0006](../adr/0006-database-model-as-schema-rebuild.md)）
目标项目：QED-Tracker
评审方：用户

> 本计划承接 2026-09-06 用户裁决与 [ADR 0006](../adr/0006-database-model-as-schema-rebuild.md)：
> v0.1 探索期表数据无价值，Alembic 迁移链退役，改为「模型即 schema + 启动自愈」；
> 数据库连接管理与建表自愈全部收敛到 `src/qed_tracker/db/`。
> 只登记实现顺序、文件落点与验证门；契约事实以 ADR 0006 与
> [数据库专用表设计](../architecture/database-private-tables.md) 为准。

## 阶段一（主体）：模型即 schema + db/ 收编 ✅/进行中

| 项 | 文件 | 内容 |
|---|---|---|
| 连接管理 ✅ | `src/qed_tracker/db/engine.py`（新，迁自 `src/qed_tracker/database.py`） | `mysql_url`/`create_engine_for`（QueuePool：pool_pre_ping/pool_recycle=3600/pool_size=5/max_overflow=10）/`session_factory`/`utc_now`/`dispose`；原 `database.py` 删除 |
| 快照自愈 ✅ | `src/qed_tracker/db/schema.py`（新） | `ensure_schema(engine)`：Base.metadata 7 张声明表缺表补建、列集/主键不一致 DROP+CREATE（统一含 qed_*，MySQL 挂起 FK 检查）；幂等；只碰声明表 + `qed_llm_calls` |
| qed_llm_calls 增量自愈 ✅ | 同上 | 缺失按权威 DDL（对齐根仓库 `call_log.py`）建表；已有表缺 REQ-060 列（task/step/review_status/review_note）则 `ALTER ADD COLUMN`；绝不 DROP |
| 论文选择收编 ✅ | `src/qed_tracker/db/selection_repository.py`（新，迁自 `selection_store.py`） | `SelectionStore`/`SelectionStoreError`；原文件删除 |
| 任务存储收编 ✅ | `src/qed_tracker/db/tasks_repository.py`（新） | `TaskRecord`/`TaskStore`/`ActiveTaskExists`；`api/tasks.py` 只留 `TaskManager`（调度器） |
| 调用方统一 ✅ | `src/qed_tracker/api/main.py`、`cli.py`、`db/knowledge_repository.py`、`llm_client.py`、`application/papers.py`、`db/__init__.py` | 全部改走 `db/engine.py`；`_serve` 的 `upgrade_database` → `ensure_schema`（失败仍软降级） |
| 退役删除 ✅ | `alembic.ini`、`src/qed_tracker/migrations/`（18 版本 + data/）、`src/qed_tracker/database.py`、`src/qed_tracker/selection_store.py`、`scripts/apply_table_comments.py` | 注释事实源改回 ORM `comment=`（models.py 建表即带） |
| 依赖与打包 ✅ | `pyproject.toml` | 移除 `alembic>=1.13.0`；package-data 去掉 `migrations/data/*.json` |
| 单元测试 ✅ | `tests/test_schema.py`（新 5 项，SQLite） | 缺表补建/幂等/列不一致重建/qed_llm_calls 缺列增量补齐且不 DROP/未声明表不碰 |
| MySQL 冒烟 ✅ | `tests/test_schema_mysql_smoke.py`（新，默认 skip） | 仅允许 `QED_DB_SMOKE=1` 且 `QED_DB_NAME=qed_test` 时执行（防误触共享 qed 库）；幂等自愈 + 7 表契约列 + qed_llm_calls 扩展列断言 |
| 旧迁移测试退役 ✅ | `tests/test_migration_0014.py`、`tests/test_migration_0018.py`、`tests/test_db_three_table_smoke.py` | 删除（迁移链与语义消失） |
| CLI 架构测试适配 ✅ | `tests/test_cli_architecture.py` | `upgrade_database` mock → `ensure_schema`；scripts 守卫仅 qed_tracker_service.py |
| 文档同步 | `docs/architecture/database-private-tables.md`、`docs/architecture/code-map.md`、`docs/standards/local-dev.md`、`docs/design/download-pipeline.md`、`AGENTS.md` | 表清单补 qt_selections（7 张）、迁移史改重建策略、注释事实源改 models.py、db 模块登记与删除行清理、local-dev alembic.ini 提及清理、设计文档 0018 前置表述改写 |
| 门禁 | — | `tests/test_schema.py` 等定向 + 全量（库化测试恢复后）全绿；qed_test 冒烟人工执行 |

## 阶段二：确认时写 JSON（后续子阶段）

- 方向（ADR 0006 决定 6）：领域/课程/教程确认端点校验并写入/更新 `docs/knowledge/` 标准答案
  JSON（manual@v1 契约，校验入口 `application/knowledge_import.py` 已有），再 upsert DB；
  JSON 与 DB 对比作为事后校验与回放依据；下载链维持 staging 验收后登记。
- 具体契约与端点改动（哪些确认端点动、幂等规则、@user 流程）在本阶段**先行单独评审**，
  不随阶段一实现。

## 待办注记

- 阶段一实施期间，8 个承载「未提交书库化测试增量」的测试文件曾被误伤；其中 7 个已从
  HEAD 恢复并重打 import 补丁，`tests/test_book_api.py`（untracked 新文件）保留损坏副本，
  未提交增量由用户自编辑器 Local History/备份恢复；恢复前全量门禁依赖这些文件的库化版本。
