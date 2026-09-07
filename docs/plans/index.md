# 计划索引

状态：Current
最后更新：2026-09-07

本目录只保存尚未关闭的跨模块实施计划。任务状态以[待办列表](../trackers/todo.md)为准；计划完成后将关闭证据写入 completed，并删除计划正文，详细差异由 Git 保留。过时计划归档至 [历史基线](../history/index.md)。

> 探索 / 知识录入 / 下载登记 / 领域探索设计已晋升为设计文档：[探索管线设计](../design/exploration-pipeline.md)、
> [知识录入设计](../design/knowledge-import.md)、[下载管线设计](../design/download-pipeline.md)
> （2026-09-04 用户确认晋升）。原 `2026-09-download-registration.md`（旧八态口径）随之删除；
> 原 `2026-09-exploration-pipeline.md`、`2026-09-exploration-overview.md`、
> `2026-09-knowledge-import.md`、`2026-09-qt-schema-restructure.md`、
> `2026-09-pipeline-4mode-verification.md`、`2026-08-prompt-optimization.md`、
> `2026-08-prompt-optimization-progress.md` 已删除；`2026-08-prompt-explore-baseline.md` 与
> `2026-08-knowledge-dual-flow.md` 已归档至 [历史基线](../history/baselines/)。

## 活跃计划

- [v0.1 数据库重构](2026-09-db-schema-rework.md)（2026-09-06，QED-053）：模型即 schema + 重建式自愈（[ADR 0006](../adr/0006-database-model-as-schema-rebuild.md)）——ensure_schema 缺表补建/不一致重建、qed_llm_calls 增量自愈、db/ 收编（engine/schema/repositories）、Alembic 链退役；阶段二「确认时写 JSON」另行评审。

- [下载登记实现计划](2026-09-download-implementation.md)（2026-09-04，QED-050-D）：五阶段下载链的分阶段实现——前置门（迁移 0018 + original_title 列 + 失效引用修复）、验收原语与配置、LLM 顾问与渠道 enrich、五阶段编排与登记服务、API/CLI 重接、文档同步与门禁。设计见[下载管线设计](../design/download-pipeline.md)。**注**：0018 前置随 ADR 0006 由 ensure_schema 重建语义承接。

- [数据生命周期设计](2026-09-data-lifecycle.md)（2026-09-01，QED-050-E）：知识/探索/书籍三态生命周期 + 交叉点 + 清理策略 + 数据根规范 + 退役规则。阶段二优化目标：全状态路径测试 + 交叉点验证。

- [来源探索与评估](2026-09-source-discovery.md)（2026-09-07，QED-054）：来源评估矩阵、渠道连通性/中文覆盖实测、待探索清单（持续工作）；2026-09-07 自 design/ 移入 plans（ADR 0008），设计契约部分已并入[下载管线设计](../design/download-pipeline.md)。

- [完整数据库设计文档与 API 设计文档](2026-08-db-api-docs-completion.md)（2026-08-26，QED-044 长期任务）：architecture 固定文档升级为完整版（数据库文档按表族拆分两文 [ADR 0007](../adr/0007-database-docs-split-by-table-family.md) + 全部路由六要素成文）；2026-09-07 正式稿已成文（api.md 主线 30 条五组六要素 + 非主线 7 条附录；数据库文档 database-private-tables.md / database-shared-tables.md），转正评审待办；承接 QED-039「API 文档内容完善」。原 `2026-08-api-design.md`（API 设计 Draft）素材并入 architecture/api.md 后已删除。
- [主链路第一版](2026-08-main-line-curriculum.md)（2026-08-12，QED-026）：课程梳理 → 教材条目（五要素）→ LLM 预填评价 → 人工评审 → 下载 → 验收 → 移交根仓库；CLI 跑通 00/01/02 三门基础课验证。设计见[主链路设计](../design/main-line-curriculum.md)。
- [下载流程现状分析与优化方向](2026-08-download-flow.md)（2026-08-28，QED-026 收尾）：三条链路（catalog run / mainline CLI / books API）现状 + 状态机事实 + 下载器/清单层事实 + 成功率/准确率优化点分析 + 验收标准提案（含 REQ-020② 找得率口径）+ REQ-032 双轨登记 + 已知缺口（confirm 覆写/course 回写/tmp 契约）。

## 已完成计划

- [Exploration Stage Enhancement（REQ-067-B10 + B12）](../history/baselines/2026-08-31-req067-b10-b12-exploration-stage.md)（2026-08-31，REQ-067-B12 已实现）：启动清理脏 exploration_stage + 新增「待确认」状态 + apply-results/re-explore 端点（领域+课程）；数据库新增 explore_pending JSON 字段；状态机 5态→6态。86 passed（17 新测 + 69 回归）。**已归档至 history/baselines/**。

- [QED-039 文档体系范本对齐](../history/baselines/2026-08-docs-restructure-alignment.md)（2026-09-01，15/15 任务完成）：按 ADR 0010 对齐三层结构（architecture/design/trackers）；database-schema.md 移入 architecture/、project-status.md 移入 trackers/、api.md 新建、三态文档归档、7 份索引更新、契约测试同步。**已归档至 history/baselines/**。

- 真实百炼与 arXiv 冒烟（QED-005）属于外部验收阻塞，直接保留在待办列表中。
