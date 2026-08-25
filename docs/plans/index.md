# 计划索引

状态：Current
最后更新：2026-08-23

本目录只保存尚未关闭的跨模块实施计划。任务状态以[待办列表](../trackers/todo.md)为准；计划完成后将关闭证据写入 completed，并删除计划正文，详细差异由 Git 保留。过时计划归档至 [历史基线](../history/index.md)（如 2026-08-service-and-book-download 已归档）。

## 活跃计划

- [prompt 优化模块设计](2026-08-prompt-optimization.md)（2026-08-24，QED-042 长期任务）：领域/课程知识探索分步管线（领域 4 步 / 课程 2 步），模板集中注册 `src/qed_tracker/prompt_lab/templates.py`（版本化，审核入口）；调用记录全进共享表 `qed_llm_calls`（REQ-060 通知根仓库改造）；run 聚合私有表 `qt_prompt_runs`；`/api/v1/prompt-*` 端点组 + promptlab CLI；人工审核后 apply 落 qed_domain/qed_course。
- [探索 API 承接设计](2026-08-exploration-api-adoption.md)（2026-08-23，QED-040/041）：课程层探索端点组 + 新建领域探索/手工维护端点组，契约唯一事实源在根仓库（已冻结）。需求方：QED-Engine REQ-055/056。**2026-08-23 用户裁决**：按数据库/API/LLM 三线详规解耦、逐线评审后实施——数据库线 [探索运行表设计详规](2026-08-exploration-db-design.md)（Accepted）、API 线 [本地实现详规](2026-08-exploration-api-design.md)（Accepted）、LLM agent 线 [设计详规](2026-08-exploration-advisor-design.md)（Accepted，2026-08-24）。三线齐备，进入代码实现——[实现计划](2026-08-exploration-api-implementation.md)（2026-08-24）。
- [主链路第一版](2026-08-main-line-curriculum.md)（2026-08-12，QED-026）：课程梳理 → 教材条目（五要素）→ LLM 预填评价 → 人工评审 → 下载 → 验收 → 移交根仓库；CLI 跑通 00/01/02 三门基础课验证。设计见[主链路设计](../design/main-line-curriculum.md)。
- 真实百炼与 arXiv 冒烟（QED-005）属于外部验收阻塞，直接保留在待办列表中。
