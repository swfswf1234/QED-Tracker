# 计划索引

状态：Current
最后更新：2026-09-11

本目录只保存尚未关闭的跨模块实施计划。任务状态以[待办列表](../trackers/todo.md)为准；计划完成后将关闭证据写入 completed，正文默认归档至 [历史基线](../history/index.md)（[ADR 0009](../adr/0009-closed-plan-archival.md)；Delete 仅限内容已完全并入固定文档且无独立查阅价值、或用户明确指示）。

> 2026-09-09 验收收口轮：QED-050 / QED-050-E / QED-053 / QED-010 / QED-014 验收关闭，
> `2026-09-integration-issues.md`（QED-014，归档至
> [历史基线](../history/baselines/2026-09-09-qed014-integration-issues.md)）、
> `2026-09-db-schema-rework.md`（QED-053）、`2026-09-data-lifecycle.md`（QED-050-E）
> 移出本目录（差异由 Git 保留）。
> 2026-09-09 文档清理轮（QED-056）：`2026-08-download-flow.md`（QED-026 收尾）、
> `2026-08-main-line-curriculum.md`（QED-026）、`2026-09-download-implementation.md`（QED-050-D）、
> `2026-08-db-api-docs-completion.md`（QED-044）、`2026-09-fix-import-stage-guard.md`（QED-014 问题 6）
> 随任务关闭删除（未完事项迁入[遗留问题清单](../history/baselines/2026-09-doc-cleanup-leftovers.md)，差异由 Git 保留）。
> 更早：探索 / 知识录入 / 下载登记 / 领域探索设计已晋升为设计文档：[探索管线设计](../design/exploration-pipeline.md)、
> [知识录入设计](../design/knowledge-import.md)、[下载管线设计](../design/download-pipeline.md)
> （2026-09-04 用户确认晋升）。原 `2026-09-download-registration.md`（旧八态口径）随之删除；
> 原 `2026-09-exploration-pipeline.md`、`2026-09-exploration-overview.md`、
> `2026-09-knowledge-import.md`、`2026-09-qt-schema-restructure.md`、
> `2026-09-pipeline-4mode-verification.md`、`2026-08-prompt-optimization.md`、
> `2026-08-prompt-optimization-progress.md` 已删除；`2026-08-prompt-explore-baseline.md` 与
> `2026-08-knowledge-dual-flow.md` 已归档至 [历史基线](../history/baselines/)。
> 2026-09-11 任务关闭轮（QED-058 / QED-059 / L-15/L-16）：
> `2026-09-11-agent-doc-governance.md`（QED-058）、`2026-09-11-book-import-domain-fix.md`（QED-059）、
> `2026-09-knowledge-patch-delete.md`（L-15/L-16）、`2026-09-knowledge-patch-delete-implementation.md`（L-15/L-16）
> 随任务关闭删除（差异由 Git 保留）。
> 2026-09-11 本期收尾轮（QED-011/042/045/046/056/057/063/064/065）：
> `2026-09-11-exploration-contract-alignment.md`（QED-063/064/065）、
> `2026-09-doc-cleanup-leftovers.md`（QED-056/057）按 [ADR 0009](../adr/0009-closed-plan-archival.md)
> 归档至[历史基线](../history/baselines/)（不再删除）。

## 活跃计划

- [来源探索与评估](2026-09-source-discovery.md)（2026-09-07，QED-054）：来源评估矩阵、渠道连通性/中文覆盖实测、待探索清单（持续工作）；2026-09-07 自 design/ 移入 plans（ADR 0008），设计契约部分已并入[下载管线设计](../design/download-pipeline.md)；2026-09-09 并入 REQ-020①② 承接口径。

## 已完成计划

- [探索契约对齐（REQ-076/077/078）](../history/baselines/2026-09-11-exploration-contract-alignment.md)（2026-09-11，QED-063/064/065）：课程探索 6→5 态 + `explore_pending.kind` 归一、`PATCH /courses` 支持 `exploration_stage`/`explore_pending`（含 5 态校验、8900 直写白名单调整）、dataset JSON 例外口径确认。**已按 ADR 0009 归档至 history/baselines/**。

- [文档清理遗留问题清单](../history/baselines/2026-09-doc-cleanup-leftovers.md)（2026-09-11，QED-056/057 关闭）：全部遗留项处置完成（L-01/L-05/L-06/L-14 修复、L-07/L-08/L-10 维持现状、L-09/L-11 PASS、L-13 保留于 QED-054）。**已按 ADR 0009 归档至 history/baselines/**。

- 书籍状态机与下载链路收口（QED-060）（2026-09-11）：八态闭环 + cancel/retry + 教程级批处理修复 + 下载落盘统一真实 `domain_id`；计划已删除，结果见[完成台账](../trackers/completed.md)。

- 探索产物落盘收口（QED-061）（2026-09-11）：领域 `domains.json` 反写、`courses.json` 删除、课程 `tutorials.json` 定稿、手动/采纳路径落盘一致；计划已删除，结果见[完成台账](../trackers/completed.md)。

- 有意义 ID 生成（QED-062）（2026-09-11）：domain/course 英文语义化 + 中文名 422 + course_abbr 超长缩略 + catalog 重新冻结；计划已删除，结果见[完成台账](../trackers/completed.md)。

- L-15/L-16 知识更新与删除端点（QED-056）（2026-09-11）：`PATCH /api/v1/knowledge/{id}` 和 `DELETE /api/v1/knowledge/{id}` 端点实现——KnowledgeRepository `update_knowledge`/`delete_knowledge` 方法 + API 端点 + 测试覆盖 + API 文档更新。计划已删除（Git 保留）。

- book_import 端点 domain_id 修复（QED-059）（2026-09-11）：修复导入书籍时目标路径使用默认 `domain_id="math"` 而非书籍实际 `domain_id` 的缺陷。计划已删除（Git 保留）。

- Agent 开发文档体系（QED-058）（2026-09-11）：AGENTS.md 统一骨架 + 标准映射落地（guides 六步流程节 + 口径核对 + 文档门禁）。计划已删除（Git 保留）。

- [Exploration Stage Enhancement（REQ-067-B10 + B12）](../history/baselines/2026-08-31-req067-b10-b12-exploration-stage.md)（2026-08-31，REQ-067-B12 已实现）：启动清理脏 exploration_stage + 新增「待确认」状态 + apply-results/re-explore 端点（领域+课程）；数据库新增 explore_pending JSON 字段；状态机 5态→6态。86 passed（17 新测 + 69 回归）。**已归档至 history/baselines/**。

- [QED-039 文档体系范本对齐](../history/baselines/2026-08-docs-restructure-alignment.md)（2026-09-01，15/15 任务完成）：按 ADR 0010 对齐三层结构（architecture/design/trackers）；database-schema.md 移入 architecture/、project-status.md 移入 trackers/、api.md 新建、三态文档归档、7 份索引更新、契约测试同步。**已归档至 history/baselines/**。

- 真实百炼与 arXiv 冒烟（QED-005）2026-08-20 并入 QED-010，随 QED-010 验收关闭（2026-09-09，见[完成台账](../trackers/completed.md)）。
