# 设计索引

状态：Current
最后更新：2026-09-07

本文档是**设计文档职责登记处**（ADR 0008）：每篇设计文档唯一负责一块能力或运行面，
类别固定为下列三组；后续 plans/ 文档归档晋升或新增设计文档，**先查本登记处确定唯一
归属**，禁止同类内容多文并存。新能力先入 [待办列表](../trackers/todo.md)
为 Plan，方案确定后再进入设计文档（如套标记字段 set_no，见
[归档基线](../history/baselines/catalog-set-field.md)）。

## 能力设计

- [主链路设计](main-line-curriculum.md)（Accepted/Implemented，QED-026）：**管**主链路 CLI
  全流程口径（courses/mainline/books 命令组、mainline download 经 8901 五阶段取书、verify
  只读复核、channels 渠道聚合）与存续决策；**不管**取书编排与登记语义（下载管线）。
- [探索管线设计](exploration-pipeline.md)（Accepted，QED-050-A/B）：**管**LLM 探索管线契约
  （领域两步 domain@v4+courses@v8、课程单步 tutorials@v2、模板版本化、dry-run/run、CLI
  domains explore）；**不管**采纳后的录入与取书。
- [知识录入设计](knowledge-import.md)（Accepted，QED-050-C）：**管**手动录入入口（领域/课程
  JSON + PDF 书籍导入）、数据文件版课程契约、ID 生成规则、A2 采纳语义、教程命名规范
  （QED-036 并入，ADR 0008）、六步手动流程、docs/knowledge 标准答案正本契约；**不管**PDF
  落盘登记细节（下载管线）。
- [下载管线设计](download-pipeline.md)（Accepted/Implemented，QED-050-D）：**管**下载全链
  唯一事实源——来源协议、math-qe 冻结书单与 catalog 严格匹配、数学课程选书要求、五阶段
  自动取书、人工导入、通用下载器与资源登记原语、课程闭环派生口径；**不管**论文链/探索
  管线/服务配置/Axiom 交付。
- [arXiv 论文智能发现](paper-discovery.md)（Implemented，按已实现能力保留于本目录，演进方向见
  [路线图](../trackers/roadmap.md)）：**管**目标档案、百炼检索规划、评分、选择报告和显式
  下载；**不管**通用下载器与资源 schema（下载管线）。

## 服务与运行

- [服务管理中心设计](service-management.md)（Accepted/Implemented，REQ-017①/REQ-043，
  ADR 0008 由 service-lifecycle + model-mode-config 合并新建）：**管**服务运行面唯一事实
  源——启停脚本契约、PID/日志运行事实、8900 接入契约、平台约束、`.env` 与模型模式
  （密钥唯一变量 `API_KEY`，ARCH-017）、多项目约定导航；**不管**业务管线与端点契约。

## 数据设计

- [数据库专用表设计](../architecture/database-private-tables.md)（Accepted，[ADR 0007](../adr/0007-database-docs-split-by-table-family.md)
  拆分）：**管**qed 库 `qt_*`（QED-Tracker 私有）表族 DDL 与状态机、五层模型链路图、文件
  命名与用户裁决记录。
- [数据库共享表设计](../architecture/database-shared-tables.md)：**管**共享表 `qed_*`
  （qed_domain/qed_course/qed_llm_calls）DDL 与跨项目契约唯一事实源（写权限、状态机写主体、
  Schema 自愈与变更流程；[ADR 0005](../adr/0005-shared-tables-doc-location.md) 迁入
  architecture/，归属 QED-Tracker，其他项目同步）。
  - 被取代文档已移入 [历史留档](../history/)：`database-schema-ownership.md`（QED-023，Retired）
    与 `three-table-schema.md`（QED-028，Superseded）。

2026-09-07 类别调整（ADR 0008）：tracker-service.md 拆散退役（Axiom 消费面→
[架构 API](../architecture/api.md)、配置→服务管理中心、书单→下载管线）；acquisition-and-inventory
并入下载管线；service-lifecycle 与 model-mode-config 合并为服务管理中心；source-discovery 移入
[计划目录](../plans/2026-09-source-discovery.md)（QED-054）；tutorial-naming 并入知识录入；
「接口契约/评审与来源/治理」三类解散。

用户命令查[操作指南](../guides/operations.md)，系统级边界查[系统总览](../architecture/system-overview.md)。跨项目契约（端口、环境变量、dataset 布局）以 QED-Engine 根仓库 `docs/` 为准。
