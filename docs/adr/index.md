# ADR 索引

状态：Current
最后更新：2026-08-21
当前版本：v0.1.0

本目录登记影响长期约束的架构决策：决定、理由、后果和取代关系。规则见
[ADR 治理规范](../standards/adr-governance.md)。

## 当前决定

| 编号 | 标题 | 领域 | 决策阶段 | 状态 | 取代关系 |
| --- | --- | --- | --- | --- | --- |
| [0001](0001-tracker-service-architecture.md) | 服务化与统一配置接入（8901 API + 后台任务轮询 + 根 .env 直读 + dataset/qed-tracker 布局） | API 与任务 | v0.6 | Accepted | — |
| [0002](0002-version-cleanup-governance.md) | 版本末期文档整理长效机制（version-cleanup 标准 + QED-039 长期跟踪） | 工程治理 | v0.1 | Accepted | — |

下一个可用编号：0003

## 规则

- 改变系统边界、公开 API、持久化语义或端口时必须新增 ADR。
- Rejected/Superseded ADR 永久进入 `../history/adr/`。
