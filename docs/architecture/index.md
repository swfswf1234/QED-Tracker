# 架构文档索引

状态：Current
最后更新：2026-08-12

本目录保存当前系统结构、运行拓扑、数据不变量、代码与设计的映射关系。
文档分类与元数据规则见[文档规范](../standards/documentation.md)。

## 当前文档

| 文档 | 设计状态 | 实现状态 | 内容 |
| --- | --- | --- | --- |
| [系统总览](system-overview.md) | Accepted | Implemented | 职责边界、运行拓扑、模块职责、数据布局、系统不变量与架构符合度 |
| [代码与设计映射表](code-map.md) | Accepted | Implemented | 受管代码、DesignRef 与测试的映射唯一事实源 |
| [主链路架构](main-line.md) | Accepted | Implemented | 领域课程梳理 → 教材寻找 → 下载 → 人工验收的主链路体系（与 evaluate 平行） |
| [8901 API 接口文档](api.md) | Accepted | Implemented | FastAPI 8901 端点分类（生命周期/数据查询/资源操作/LLM 业务）与契约 |
| [数据库设计](database-schema.md) | Accepted | Plan | qed 库 qed_*/qt_* 表族唯一事实源（领域/课程/知识行/书行/渠道五层模型） |

具体来源协议和持久化字段属于[下载与清单设计](../design/acquisition-and-inventory.md)，Axiom HTTP 细节属于[服务与外部接口设计](../design/tracker-service.md)「外部接口：Axiom-Flow 消费面」。
