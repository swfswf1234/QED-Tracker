# 计划索引

状态：Current
最后更新：2026-08-28

本目录只保存尚未关闭的跨模块实施计划。任务状态以[待办列表](../trackers/todo.md)为准；计划完成后将关闭证据写入 completed，并删除计划正文，详细差异由 Git 保留。过时计划归档至 [历史基线](../history/index.md)（如 2026-08-service-and-book-download 已归档）。

## 活跃计划

- [QED-Engine 探索对齐承接设计](2026-08-engine-exploration-alignment.md)（2026-08-28，QED-047/048，需求方：根仓库 REQ-064/065）：课程层探索 dry-run 端点 + shared-tables.md 写权限修订 + exploration_stage 写主体澄清 + api-design GET /courses 领域级探索字段补充；含待移交项（test_documentation.py 白名单补行，移交审阅）。

- [领域探索 prompt 优化基线](2026-08-prompt-explore-baseline.md)（2026-08-25，QED-043 长期任务）：v3 三步管线首轮全链路真实结果冻结（qed_llm_calls 073~079：高等数学 12 门 + 计算机科学与技术 16 门双批 ready）；后续模板/先验优化一律以该基线对照；与参考文本的差距观察仅作候选线索，真实对照口径待用户评估确定。
- [prompt 优化模块设计](2026-08-prompt-optimization.md)（2026-08-24，QED-043 长期任务）：领域知识探索 v3 三步管线（domain@v1 名称校验+确认流 / courses@v3 清华命名基准禁拆学期 / path@v3 tier 四档+先修无环）+ priors.py 领域先验注册；模板集中注册 `src/qed_tracker/prompt_lab/templates.py`（版本化，审核入口）；调用记录全进共享表 `qed_llm_calls`（REQ-060 根仓库已实现）；dry-run 评估端点已上线；后续 Phase B 正式流程。
- [完整数据库设计文档与 API 设计文档](2026-08-db-api-docs-completion.md)（2026-08-26，QED-044 长期任务）：architecture 两份固定文档升级为完整版（全表族 ER/字段字典/迁移史 + 全部路由五要素成文）；前置门禁 QED-010/011/014/026 完成前只维护不重构；承接 QED-039「API 文档内容完善」；QED-043 Phase 3/4 为首批子集。
- [主链路第一版](2026-08-main-line-curriculum.md)（2026-08-12，QED-026）：课程梳理 → 教材条目（五要素）→ LLM 预填评价 → 人工评审 → 下载 → 验收 → 移交根仓库；CLI 跑通 00/01/02 三门基础课验证。设计见[主链路设计](../design/main-line-curriculum.md)。
- 真实百炼与 arXiv 冒烟（QED-005）属于外部验收阻塞，直接保留在待办列表中。
