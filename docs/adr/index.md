# ADR 索引

状态：Current
最后更新：2026-09-07
当前版本：v0.1.0

本目录登记影响长期约束的架构决策：决定、理由、后果和取代关系。规则见
[ADR 治理规范](../standards/adr-governance.md)。

## 当前决定

| 编号 | 标题 | 领域 | 决策阶段 | 状态 | 取代关系 |
| --- | --- | --- | --- | --- | --- |
| [0001](0001-tracker-service-architecture.md) | 服务化与统一配置接入（8901 API + 后台任务轮询 + 根 .env 直读 + dataset/qed-tracker 布局） | API 与任务 | v0.6 | Accepted | — |
| [0002](0002-version-cleanup-governance.md) | 版本末期文档整理长效机制（机制已并入文档治理规范「版本末期文档整理」节 + QED-039 长期跟踪） | 工程治理 | v0.1 | Accepted | — |
| [0003](0003-pending-design-location.md) | 待评审设计的目录流转（Draft 设计先入 plans/，确定后落 design/；范本：根仓库 ADR 0011） | 工程治理 | v0.1 | Accepted | — |
| [0004](0004-standards-governance-alignment.md) | 规范体系对齐根仓库治理模式（documentation.md 改名 doc-governance.md 并扩写、version-cleanup 并入、新增 testing 与跨项目协作标准、CLAUDE.md 引入） | 工程治理 | v0.1 | Accepted | — |
| [0005](0005-shared-tables-doc-location.md) | 共享表文档迁入 architecture/（跨项目契约升格为架构固定文档；数据库设计分共享/专用两区） | 工程治理 | v0.1 | Accepted | 决定③被 [0007](0007-database-docs-split-by-table-family.md) 部分取代 |
| [0006](0006-database-model-as-schema-rebuild.md) | v0.1 数据库策略：模型即 schema + 重建式自愈（Alembic 链退役；ensure_schema 缺表补建/不一致重建含共享表；qed_llm_calls 增量化自愈不 DROP；db/ 集中管理；JSON 标准答案备份基准） | 数据与持久化 | v0.1 | Accepted | — |
| [0007](0007-database-docs-split-by-table-family.md) | 数据库设计文档按表族拆分（shared-tables.md → database-shared-tables.md、database-schema.md → database-private-tables.md；两文互链互不复制；DDL 展示统一为紧凑行尾 `--` 注释风格） | 工程治理 | v0.1 | Accepted | 部分取代 [0005](0005-shared-tables-doc-location.md)（决定③） |
| [0008](0008-design-doc-scope-reshuffle.md) | 设计文档域职责重划（tracker-service 拆散退役；下载链合并改名 download-pipeline；新建 service-management 管理中心；source-discovery 移 plans；tutorial-naming 并入 knowledge-import；design/index.md 为职责登记处） | 工程治理 | v0.1 | Accepted | — |

下一个可用编号：0009

## 规则

- 改变系统边界、公开 API、持久化语义或端口时必须新增 ADR。
- Rejected/Superseded ADR 永久进入 `../history/adr/`。
