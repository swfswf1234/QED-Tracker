# 计划索引

状态：Current
最后更新：2026-08-25

本目录只保存尚未关闭的跨模块实施计划。任务状态以[待办列表](../trackers/todo.md)为准；计划完成后将关闭证据写入 completed，并删除计划正文，详细差异由 Git 保留。过时计划归档至 [历史基线](../history/index.md)（如 2026-08-service-and-book-download 已归档）。

## 活跃计划

- [领域探索 prompt 优化基线](2026-08-prompt-explore-baseline.md)（2026-08-25，QED-043 长期任务）：v3 三步管线首轮全链路真实结果冻结（qed_llm_calls 073~079：高等数学 12 门 + 计算机科学与技术 16 门双批 ready）；后续模板/先验优化一律以该基线对照；与参考文本的差距观察仅作候选线索，真实对照口径待用户评估确定。
- [prompt 优化模块设计](2026-08-prompt-optimization.md)（2026-08-24，QED-043 长期任务）：领域知识探索 v3 三步管线（domain@v1 名称校验+确认流 / courses@v3 清华命名基准禁拆学期 / path@v3 tier 四档+先修无环）+ priors.py 领域先验注册；模板集中注册 `src/qed_tracker/prompt_lab/templates.py`（版本化，审核入口）；调用记录全进共享表 `qed_llm_calls`（REQ-060 根仓库已实现）；run 聚合私有表 `qt_prompt_runs`（迁移 0010）；dry-run 评估端点已上线；后续 Phase B 正式流程（课程管线 + qt_prompt_runs 落库 + apply/review 端点组 + promptlab CLI）。
- [主链路第一版](2026-08-main-line-curriculum.md)（2026-08-12，QED-026）：课程梳理 → 教材条目（五要素）→ LLM 预填评价 → 人工评审 → 下载 → 验收 → 移交根仓库；CLI 跑通 00/01/02 三门基础课验证。设计见[主链路设计](../design/main-line-curriculum.md)。
- 真实百炼与 arXiv 冒烟（QED-005）属于外部验收阻塞，直接保留在待办列表中。
