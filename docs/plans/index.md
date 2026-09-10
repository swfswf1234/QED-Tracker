# 计划索引

状态：Current
最后更新：2026-09-09

本目录只保存尚未关闭的跨模块实施计划。任务状态以[待办列表](../trackers/todo.md)为准；计划完成后将关闭证据写入 completed，并删除计划正文，详细差异由 Git 保留。过时计划归档至 [历史基线](../history/index.md)。

> 2026-09-09 验收收口轮：QED-050 / QED-050-E / QED-053 / QED-010 / QED-014 验收关闭，
> `2026-09-integration-issues.md`（QED-014，归档至
> [历史基线](../history/baselines/2026-09-09-qed014-integration-issues.md)）、
> `2026-09-db-schema-rework.md`（QED-053）、`2026-09-data-lifecycle.md`（QED-050-E）
> 移出本目录（差异由 Git 保留）。
> 2026-09-09 文档清理轮（QED-056）：`2026-08-download-flow.md`（QED-026 收尾）、
> `2026-08-main-line-curriculum.md`（QED-026）、`2026-09-download-implementation.md`（QED-050-D）、
> `2026-08-db-api-docs-completion.md`（QED-044）、`2026-09-fix-import-stage-guard.md`（QED-014 问题 6）
> 随任务关闭删除（未完事项迁入[遗留问题清单](2026-09-doc-cleanup-leftovers.md)，差异由 Git 保留）。
> 更早：探索 / 知识录入 / 下载登记 / 领域探索设计已晋升为设计文档：[探索管线设计](../design/exploration-pipeline.md)、
> [知识录入设计](../design/knowledge-import.md)、[下载管线设计](../design/download-pipeline.md)
> （2026-09-04 用户确认晋升）。原 `2026-09-download-registration.md`（旧八态口径）随之删除；
> 原 `2026-09-exploration-pipeline.md`、`2026-09-exploration-overview.md`、
> `2026-09-knowledge-import.md`、`2026-09-qt-schema-restructure.md`、
> `2026-09-pipeline-4mode-verification.md`、`2026-08-prompt-optimization.md`、
> `2026-08-prompt-optimization-progress.md` 已删除；`2026-08-prompt-explore-baseline.md` 与
> `2026-08-knowledge-dual-flow.md` 已归档至 [历史基线](../history/baselines/)。

## 活跃计划

- [来源探索与评估](2026-09-source-discovery.md)（2026-09-07，QED-054）：来源评估矩阵、渠道连通性/中文覆盖实测、待探索清单（持续工作）；2026-09-07 自 design/ 移入 plans（ADR 0008），设计契约部分已并入[下载管线设计](../design/download-pipeline.md)；2026-09-09 并入 REQ-020①② 承接口径。

- [文档清理遗留问题清单](2026-09-doc-cleanup-leftovers.md)（2026-09-09，QED-056）：2026-09-09 文档清理轮的遗留缺陷与裁决事项登记；代码级修复执行归 QED-057。

## 已完成计划

- [Exploration Stage Enhancement（REQ-067-B10 + B12）](../history/baselines/2026-08-31-req067-b10-b12-exploration-stage.md)（2026-08-31，REQ-067-B12 已实现）：启动清理脏 exploration_stage + 新增「待确认」状态 + apply-results/re-explore 端点（领域+课程）；数据库新增 explore_pending JSON 字段；状态机 5态→6态。86 passed（17 新测 + 69 回归）。**已归档至 history/baselines/**。

- [QED-039 文档体系范本对齐](../history/baselines/2026-08-docs-restructure-alignment.md)（2026-09-01，15/15 任务完成）：按 ADR 0010 对齐三层结构（architecture/design/trackers）；database-schema.md 移入 architecture/、project-status.md 移入 trackers/、api.md 新建、三态文档归档、7 份索引更新、契约测试同步。**已归档至 history/baselines/**。

- 真实百炼与 arXiv 冒烟（QED-005）2026-08-20 并入 QED-010，随 QED-010 验收关闭（2026-09-09，见[完成台账](../trackers/completed.md)）。
