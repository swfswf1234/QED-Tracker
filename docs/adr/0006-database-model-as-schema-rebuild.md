# ADR 0006：v0.1 数据库策略——模型即 schema + 重建式自愈（Alembic 链退役）

状态：Accepted
日期：2026-09-06
最后更新：2026-09-06
领域：数据与持久化
决策阶段：v0.1
取代：—
被取代：—

## 背景

本仓库数据库曾由 Alembic 迁移链管理（0001→0018，18 个迁移文件）。现状暴露的客观事实：

1. 链上 0001~0005、0008~0010 是「建了又被 DROP」的历史残骸，仅对从零 replay 有意义；
2. `downgrade` 实际不可用（QED-046 已知缺陷：0008 downgrade 引用不存在的索引；0018
   直接 `RuntimeError`），链只有单向升级能力；
3. 0018 的实现方式本来就是「从 ORM 模型无条件 DROP+重建」（两表为空、不保数据），
   说明 ORM 模型已是 schema 的事实源，迁移只是它的投影；
4. 服务启动 `upgrade_database(settings)` 每次联跑，但 schema 变更却要维护双份（模型+迁移）。

2026-09-06 用户裁决（探索期约束）：v0.1 属探索阶段，表数据无价值、迁移无用武之地；
改为**删表重建**策略；数据库连接管理与建表/自愈全部收敛到 `src/qed_tracker/db/`。

## 决定

1. **ORM 即 schema**：`src/qed_tracker/db/models.py` 的 `Base.metadata` 是唯一事实源；
   `ensure_schema(engine)` 启动自愈——缺表 `create_all` 补建；列集/主键与模型不一致时
   DROP+CREATE 全表重建（**统一规则，含共享表 `qed_*`**）；幂等可重复执行。
2. **Alembic 链退役**：删除 `alembic.ini` 与迁移目录 migrations/（含 data 种子与
   注释 JSON）；不再维护 revision 链与 `alembic_version` 表。未来 v0.2 起若有真实数据
   需要演进，可从新基线重新引入 Alembic（本决定不构成永久不可逆）。
3. **只管理声明表**：`ensure_schema` 只碰 `Base.metadata` 内 7 张表 +
   `qed_llm_calls`；其他任何表（含其他项目的）不碰。
4. **`qed_llm_calls` 增量化自愈**（根仓库建表维护的共享审计表，三项目均有真实审计数据）：
   缺失则按权威 DDL 建表；已有表缺 REQ-060 扩展列（task/step/review_status/review_note）
   则 `ALTER ADD COLUMN` 补齐；**绝不 DROP 重建**（与根仓库 `call_log.py` 的
   `ensure_table`+`ensure_columns` 加法策略一致，保护审计历史）。
5. **连接管理集中化**：引擎/连接池（QueuePool 参数化）/session 工厂/dispose/utc_now
   统一于 `db/engine.py`；后台任务与论文选择的读写层收编为 `db/tasks_repository.py`、
   `db/selection_repository.py`；所有数据库操作集中于 `db/` 且不再有数据库层之外的
   `qed_tracker.database` 模块。
6. **JSON 标准答案为备份与对比基准**：领域/课程/教程的标准答案 JSON（`docs/knowledge/`）
   是数据源基准，数据库是运行视图；确认（领域/课程/教程）时同步维护 JSON，替代表/
   重建后可经确认流程重放。下载链维持「staging 验收 → 确认后登记」的临时区-成品区隔离。
7. **共享表契约回执**：`qed_*` 结构变化同样走重建自愈，完成后回执根仓库
   （ADR 0003/0009 登记同步），不静默偏离跨项目契约。

## 后果

- 好处：单一事实源（模型）、移除全部迁移维护成本；启动自愈把「schema 漂移」变成
  自修复而非人工排障；数据库操作模块化，职责收敛到 `db/`。
- 成本：失去逐版本 DDL 历史（Git 历史仍可追溯）；已有表结构不一致时**自动丢弃重来**
  （v0.1 数据无价值前提下可接受——启动前如需保留，人工快照兜底）；
  `downgrade` 能力消失（本仓库原已不可用）。
- 风险：共享表被整库重建时，其他项目短暂只读到新结构——由「共享表 schema 变更先经
  根仓库登记」流程与回执兜底；`qed_llm_calls` 用加法自愈规避审计数据损坏。
- 验证：`tests/test_schema.py`（SQLite：缺表补建/不一致重建/幂等/未声明表豁免/增量自愈）、
  `tests/test_schema_mysql_smoke.py`（真实 MySQL 冒烟，仅允许在 `qed_test` 库执行，
  默认 skip）。

## 关联

- 关联标准：[文档治理规范](../standards/doc-governance.md)、
  [测试架构与门禁](../standards/testing.md)、[本地开发环境](../standards/local-dev.md)
- 关联文档：[数据库专用表设计](../architecture/database-private-tables.md)、
  [数据库共享表设计](../architecture/database-shared-tables.md)（迁移史改写为「Schema 自愈」，
  2026-09-07 按表族拆分，见 ADR 0007）、
  [代码映射](../architecture/code-map.md)（db 模块登记）、
  [下载管线设计](../design/download-pipeline.md)（0018 前置依赖表述）
- 关联 ADR：[ADR 0001](0001-tracker-service-architecture.md)（服务化，数据库入口沿用）、
  根仓库 ADR 0003/0009（共享表命名空间与所有权）
- 承载任务：QED-053（v0.1 数据库重构，todo 登记）
- 固定文档落点：[数据库专用表设计](../architecture/database-private-tables.md)「Schema 自愈（ADR 0006：模型即 schema）」节
