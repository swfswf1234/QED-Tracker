# 架构文档索引

状态：Current
最后更新：2026-09-09

本目录保存当前系统结构、运行拓扑、数据不变量、共享表跨项目契约、代码与设计的映射关系。
文档分类与元数据规则见[文档治理规范](../standards/doc-governance.md)。

## 当前文档

| 文档 | 设计状态 | 实现状态 | 内容 |
| --- | --- | --- | --- |
| [系统总览](system-overview.md) | Accepted | Implemented | 职责边界、运行模式（独立/组件）、模块职责、数据布局、系统不变量与架构符合度 |
| [代码与设计映射表](code-map.md) | Accepted | Implemented | 受管代码与测试的映射唯一事实源 |
| [主链路架构](main-line.md) | Accepted | Implemented | 领域课程梳理 → 教材寻找 → 下载 → 人工验收的主链路体系 |
| [QED-Tracker API 设计文档（8901）](api.md) | Accepted（已确认） | Implemented | FastAPI 8901 主线 31 条路由按五组业务域（服务与任务/领域与课程/探索评估与采纳/教程/书籍与渠道）六要素契约 + 非主线 7 条附录一览（代码 38 条）；另含外部接口：Axiom-Flow 消费面（8902） |
| [数据库专用表设计](database-private-tables.md) | Accepted | Implemented | qed 库 `qt_*` 专用表族 DDL 唯一事实源（qt_knowledge/qt_books/qt_sources/qt_tasks/qt_selections；全库表清单与五层模型链路图） |
| [数据库共享表设计](database-shared-tables.md) | Accepted | Implemented | 共享表 qed_domain/qed_course/qed_llm_calls DDL 与跨项目契约唯一事实源（写权限、状态机写主体、Schema 自愈与变更流程；归属 QED-Tracker，其他项目同步） |

具体来源协议和持久化字段属于[下载管线设计](../design/download-pipeline.md)，Axiom HTTP 细节属于[架构 API](api.md)「外部接口：Axiom-Flow 消费面」。
