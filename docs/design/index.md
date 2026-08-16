# 设计索引

状态：Current
最后更新：2026-08-16

文档类别固定：设计文档按下列类别维护，不随意增加；新能力先入 [待办列表](../trackers/todo.md)
为 Plan，方案确定后再进入设计文档（如套标记字段 set_no，见
[归档基线](../history/baselines/catalog-set-field.md)）。

## 接口契约

- [服务与外部接口设计](tracker-service.md)（Accepted，需求方 QED-Engine）：8901 API 提供面
  （端点/后台任务/轮询/状态机）、**外部接口：Axiom-Flow 消费面（8902 端点契约/错误语义/
  传输记录/失败语义）**、配置与数据布局、qed 库 MySQL 资源登记（qt_resources）、基础书单
  math-qe-v2 与批量下载。

## 能力设计

- [下载与清单](acquisition-and-inventory.md)：来源协议、选择规则、可靠下载、资源 schema 和失败语义。
- [arXiv 论文智能发现](paper-discovery.md)：目标档案、百炼检索规划、评分、选择报告和显式下载。
- [主链路设计](main-line-curriculum.md)（Accepted，QED-026 实现完成）：课程体系数据模型
  （courses/math.json）、教材条目五要素（版本/评价/建议/渠道/状态）、渠道记录与 CLI 流程；
  与 evaluate 平行。

## 评审与来源

- [人工评审优化](review-round-dedup.md)（Accepted，需求方 QED-Engine）：evaluate 同源去重、
  file_hint 例外与 review_note 人工评审留痕。
- [来源探索与评估](source-discovery.md)：发现合适下载路径、淘汰不合适路径的目标、评估矩阵、
  合规边界（libgen 类不纳入）与探索流程。

## 数据设计

- [数据库设计](database-schema.md)（Accepted，2026-08-16 用户裁决知识层次重构）：qed 库
  `qed_*`（共享）与 `qt_*`（QED-Tracker 私有）表族**唯一事实源文档**——领域/课程/知识行/
  书行/渠道五层模型（qed_domain → qed_course → qt_knowledge → qt_books → qt_sources）、
  状态机、文件命名（物理名/展示名）、存量迁移与共享表所有权。
  - 取代留档：`database-schema-ownership.md`（QED-023，Retired）与
    `three-table-schema.md`（QED-028，被取代）不再作为当前实现依据。

## 治理

- [治理契约范本对齐](governance-contract-alignment.md)（Accepted，QED-022）：守护契约测试的
  契约头六字段、守护面清单与编写约定对齐根仓库范本。

用户命令查[日常操作](../guides/operations.md)，系统级边界查[系统总览](../architecture/system-overview.md)。跨项目契约（端口、环境变量、dataset 布局）以 QED-Engine 根仓库 `docs/` 为准。
