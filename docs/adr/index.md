# ADR 索引

状态：Current
最后更新：2026-08-31
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
| [0005](0005-shared-tables-doc-location.md) | 共享表文档迁入 architecture/（跨项目契约升格为架构固定文档；数据库设计分共享/专用两区） | 工程治理 | v0.1 | Accepted | — |

下一个可用编号：0006

## 规则

- 改变系统边界、公开 API、持久化语义或端口时必须新增 ADR。
- Rejected/Superseded ADR 永久进入 `../history/adr/`。
