# 架构文档索引

状态：Current
最后更新：2026-08-31

本目录保存当前系统结构、运行拓扑、数据不变量、共享表跨项目契约、代码与设计的映射关系。
文档分类与元数据规则见[文档治理规范](../standards/doc-governance.md)。

## 当前文档

| 文档 | 设计状态 | 实现状态 | 内容 |
| --- | --- | --- | --- |
| [系统总览](system-overview.md) | Accepted | Implemented | 职责边界、运行模式（独立/组件）、模块职责、数据布局、系统不变量与架构符合度 |
| [代码与设计映射表](code-map.md) | Accepted | Implemented | 受管代码与测试的映射唯一事实源 |
| [主链路架构](main-line.md) | Accepted | Implemented | 领域课程梳理 → 教材寻找 → 下载 → 人工验收的主链路体系 |
| [QED-Tracker API 设计文档（8901）](api.md) | Accepted（确认状态：暂定） | Implemented | FastAPI 8901 全部 42 条路由按八组业务域（生命周期/领域课程/教程/书籍/任务/LLM 搜索/目录/探索采纳）与契约；正式稿五要素由 QED-044 收口 |
| [数据库设计](database-schema.md) | Accepted | Implemented | qed 库 qed_*/qt_* 表族 DDL 唯一事实源（分共享表/项目专用表两区；领域/课程/教程/书籍/渠道五层模型） |
| [共享表设计](shared-tables.md) | Accepted | Implemented | 共享表 qed_domain/qed_course/qed_llm_calls 跨项目契约唯一事实源（写权限、状态机写主体、Schema 变更流程；归属 QED-Tracker，其他项目同步） |

具体来源协议和持久化字段属于[下载与清单设计](../design/acquisition-and-inventory.md)，Axiom HTTP 细节属于[服务与外部接口设计](../design/tracker-service.md)「外部接口：Axiom-Flow 消费面」。
