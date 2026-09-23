# ADR 索引

状态：Current
最后更新：2026-09-21
当前版本：v1.0

本目录登记影响长期约束的架构决策：决定、理由、后果和取代关系。规则见
[ADR 治理规范](../standards/adr-governance.md)；已承接归档机制见
[ADR 0010](0010-absorbed-adr-archival.md)。

## 当前决定

| 编号 | 标题 | 领域 | 决策阶段 | 状态 | 取代关系 |
| --- | --- | --- | --- | --- | --- |
| [0001](0001-tracker-service-architecture.md) | 服务化与统一配置接入（8901 API + 后台任务轮询 + 根 .env 直读 + dataset/qed-tracker 布局） | API 与任务 | v0.6 | Accepted | — |
| [0006](0006-database-model-as-schema-rebuild.md) | v0.1 数据库策略：模型即 schema + 重建式自愈（Alembic 链退役；ensure_schema 缺表补建/不一致重建含共享表；qed_llm_calls 增量化自愈不 DROP；db/ 集中管理；JSON 标准答案备份基准） | 数据与持久化 | v0.1 | Accepted | — |
| [0010](0010-absorbed-adr-archival.md) | 已承接 ADR 的归档机制（新增 Absorbed 状态，归档至 history/adr/；判定需用户确认且逐条决定有承接落点） | 工程治理 | v1.0 | Accepted | — |

下一个可用编号：0011

## 已承接归档（Absorbed）

以下 ADR 的决策内容已完整并入稳定文档（各文头部「承接落点」行为准），正文保留决策理由，
位于 [../history/adr/](../history/adr/0002-version-cleanup-governance.md)：

| 编号 | 标题 | 承接落点 |
| --- | --- | --- |
| [0002](../history/adr/0002-version-cleanup-governance.md) | 版本末期文档整理长效机制 | doc-governance「版本末期文档整理」节 |
| [0003](../history/adr/0003-pending-design-location.md) | 待评审设计的目录流转 | doc-governance 分类表与「文档生命周期」 |
| [0004](../history/adr/0004-standards-governance-alignment.md) | 规范体系对齐根仓库治理模式 | standards/ 五文与根 CLAUDE.md（产物即落点） |
| [0005](../history/adr/0005-shared-tables-doc-location.md) | 共享表文档迁入 architecture/ | database-shared-tables.md + 跨项目协作规范（决定③被 0007 取代） |
| [0007](../history/adr/0007-database-docs-split-by-table-family.md) | 数据库设计文档按表族拆分 | database-shared/private-tables.md 两文自承载 |
| [0008](../history/adr/0008-design-doc-scope-reshuffle.md) | 设计文档域职责重划 | design/index.md 职责登记处 + doc-governance 分类表 |
| [0009](../history/adr/0009-closed-plan-archival.md) | 关闭计划默认归档 docs/history/ | doc-governance「归档与删除」两态判定 |

## 规则

- 改变系统边界、公开 API、持久化语义或端口时必须新增 ADR。
- Rejected/Superseded ADR 永久进入 `../history/adr/`；决策已被稳定文档完整承接的
  Accepted ADR 经用户确认后转 Absorbed 同路径归档（[ADR 0010](0010-absorbed-adr-archival.md)）。
