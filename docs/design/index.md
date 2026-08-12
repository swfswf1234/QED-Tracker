# 设计索引

状态：Current
最后更新：2026-08-12

- [下载与清单](acquisition-and-inventory.md)：来源协议、选择规则、可靠下载、资源 schema 和失败语义。
- [arXiv 论文智能发现](paper-discovery.md)：目标档案、百炼检索规划、评分、选择报告和显式下载。
- [与 Axiom-Flow 的交互规范](axiom-handoff.md)：跨项目交接接口、传输记录、幂等边界和失败语义
  （跨项目契约以根仓库为准，本文件只链接不复制）。
- [服务接口设计](tracker-service.md)（Accepted，需求方 QED-Engine）：8901 API、后台任务与轮询、
  配置与数据布局迁移、qed 库 MySQL 资源登记（qt_resources）、基础书单 math-qe-v2 与批量下载。
- [来源探索与评估](source-discovery.md)：发现合适下载路径、淘汰不合适路径的目标、评估矩阵、
  合规边界（libgen 类不纳入）与探索流程。
- [人工评审优化](review-round-dedup.md)（Accepted，需求方 QED-Engine）：evaluate 同源去重、
  file_hint 例外与 review_note 人工评审留痕。
- [治理契约范本对齐](governance-contract-alignment.md)（Accepted，QED-022）：守护契约测试的
  契约头六字段、守护面清单与编写约定对齐根仓库范本。
- [数据库设计](database-schema-ownership.md)（Accepted，QED-023）：qed 库 `qt_*` 表清单、表结构
  与迁移的事实源文档。
- [主链路设计](main-line-curriculum.md)（Draft 待评审）：课程体系数据模型（courses/math.json）、
  教材条目五要素（版本/评价/建议/渠道/状态）、渠道记录与 CLI 流程；与 evaluate 平行。

> 文档类别固定：设计文档按上述类别维护，不随意增加；新能力先入 [待办列表](../trackers/todo.md)
> 为 Plan，方案确定后再进入设计文档（如套标记字段 set_no，见
> [归档基线](../history/baselines/catalog-set-field.md)）。

用户命令查[日常操作](../guides/operations.md)，系统级边界查[系统总览](../architecture/system-overview.md)。跨项目契约（端口、环境变量、dataset 布局）以 QED-Engine 根仓库 `docs/` 为准。
