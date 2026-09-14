# 论文探索与下载链路整合（paper-pipeline-alignment）

状态：Draft
任务类型：Plan
最后更新：2026-09-14
需求方：用户
目标项目：QED-Tracker
评审方：用户
关联设计：[论文发现设计](../design/paper-discovery.md)、[探索管线设计](../design/exploration-pipeline.md)、[下载管线设计](../design/download-pipeline.md)
关联 Tracker：QED-068
归档判定：待关闭时按 [ADR 0009](../adr/0009-closed-plan-archival.md) 做 Retain/Delete 两态判定

## 目标与成功标准

先如实登记论文探索与下载链路的现状，再参照现有教程探索链路给出整合的简要计划。
**本轮只做现状说明与简要计划，不实现。**

成功标准：现状说明完整、与教程探索链路的差异对照清晰、整合计划经用户评审通过。

## 现状（论文链路）

- 检索：`src/qed_tracker/providers/arxiv.py`（关键词/分类/作者/ID 查询）。
- LLM 顾问：`src/qed_tracker/providers/bailian.py`（生成检索计划 + 候选评分；经 `llm_client.py`）。
- 服务：`src/qed_tracker/application/papers.py`（`recommend` = 检索计划 → 候选去重/排除已有 →
  评分排序 → 推荐；`download` = 从固定选择报告按序号显式下载）。
- 存储：`src/qed_tracker/db/selection_repository.py`（`qt_selections` 报告表，替代 `meta/selections/` JSON）。
- CLI：`papers search/get/recommend/profiles/selections list|show|download`。
- 设计：[论文发现设计](../design/paper-discovery.md)（目标档案 schema v1、评分 50%/30%/20%、阈值 70、
  选择报告 schema v1）。
- 边界：模型只生成检索计划与可审阅评分，不写资源事实；下载由用户引用固定报告 + 一基序号显式执行，
  **不自动下载**。

## 现状（教程探索链路，整合参照）

- 编排：`src/qed_tracker/prompt_lab/pipeline.py` + `templates.py`（domain@v4 / courses@v8 / tutorials@v2）。
- 状态机：`qed_domain`/`qed_course` 的 `exploration_stage` + `explore_pending`；apply-results /
  re-explore / adopt（见[数据库共享表设计](../architecture/database-shared-tables.md)）。
- 交互：dry-run（不写表，仅 `qed_llm_calls` 审计）→ 人工确认 → 采纳落库。
- 落盘：`raw/<domain>/domains.json`、`raw/<domain>/<course>/tutorials.json`（知识正本，见
  [探索管线设计](../design/exploration-pipeline.md)）。
- 存储：`qt_knowledge`/`qt_books`（[数据库专用表设计](../architecture/database-private-tables.md)）。

## 差异对照（待细化）

| 维度 | 教程探索链路 | 论文链路 |
| --- | --- | --- |
| 管线编排 | `prompt_lab` 模板化（版本化模板 id） | `papers.py` 内联逻辑 |
| 状态机 | `exploration_stage` 多态 + 人工采纳 | 报告快照 `status`（无状态机） |
| 落盘 | `domains.json`/`tutorials.json` 知识正本 | `qt_selections` 报告 |
| 下载 | 五阶段取书 + 通用登记 | 固定报告序号下载 |
| 审计 | `qed_llm_calls` + `qt_sources` | `qed_llm_calls` + `qt_selections` |
| 入口 | 8901 后台任务 + dry-run + CLI | CLI + 即时查询端点 |

## 整合简要计划（待细化）

1. 统一编排抽象：论文检索计划/评估对齐 `prompt_lab` 的模板化与审计口径（与 QED-067 的
   LangChain 编排协同）。
2. 状态与交互对齐：评估是否为论文引入探索式「dry-run → 人工确认 → 采纳」流程。
3. 下载边界评估：论文 PDF 是否并入通用下载/登记服务（保持「不自动下载」边界）。
4. 端点/CLI 对齐：是否走后台任务（202 + 轮询）与统一错误码。

## 非目标

本轮不实现任何代码改动；不改变论文「不自动下载」与「模型不写资源事实」边界。

## 关闭与归档

关闭时按 [ADR 0009](../adr/0009-closed-plan-archival.md) 做 Retain/Delete 两态判定；
设计确定后按 [ADR 0003](../adr/0003-pending-design-location.md) 迁入 `design/`。
