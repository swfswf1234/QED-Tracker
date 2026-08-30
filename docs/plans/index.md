# 计划索引

状态：Current
最后更新：2026-08-28

本目录只保存尚未关闭的跨模块实施计划。任务状态以[待办列表](../trackers/todo.md)为准；计划完成后将关闭证据写入 completed，并删除计划正文，详细差异由 Git 保留。过时计划归档至 [历史基线](../history/index.md)（如 2026-08-service-and-book-download 已归档）。

## 活跃计划

- [教材探索与下载双轨 + 知识体系梳理](2026-08-knowledge-dual-flow.md)（2026-08-29，QED-050）：手动+自动双轨共用 qt_knowledge/qt_books 状态机同一链路；手动领域导入（POST /domains/import）写共享表、课程导入复用 A2（draft）、手动下载（POST /books/{id}/import 外部路径→数据根内登记）；QED-043 语义升级（stage 四档【基础/主干/分支/前沿】/classic_tracks.kind/entry_requirements 一句话）；docs/knowledge/ 标准答案知识目录（math-advanced.json + math-advanced/{course_id}.json 含 target_path）。

- [领域探索状态接管（REQ-067 B8）](2026-08-30-req067-b8-explore-orchestration.md)（2026-08-30，QED-051，需求方：根仓库 REQ-067 §B2/B6/B7/B8）：领域探索启动/执行/落库/名称确认由 8901 任务层驱动；exploration_stage 五态（含失败）单写方=QED-Tracker；新端点 explore/confirm-name + qed_domain.explore_pending（迁移 0015）；apply 全量自动落库；随文修订 REQ-064 领域侧写主体口径。配套回执：[2026-08-30-req067-a-import-api-reply.md](2026-08-30-req067-a-import-api-reply.md)（REQ-067-A ①~④ 契约回执与评审修正）。

- [REQ-067-A 导入契约回执](2026-08-30-req067-a-import-api-reply.md)（2026-08-30，QED-050 收尾）：导入端点/校验/错误码现状契约回执（manual@v1），含根仓库计划的 4 项评审修正；A 档可即日开工，不受 QED-051 阻塞。

- [领域探索状态接管（REQ-067 B8）实施计划](2026-08-30-req067-b8-impl-plan.md)（2026-08-30，QED-051）：设计稿的落地实施（迁移 0015 / 状态机 domain_explore / explore·confirm-name 端点 / 视图透出 explore_pending / 文档同步）。

- [QED-Engine 探索对齐承接设计](2026-08-engine-exploration-alignment.md)（2026-08-28，QED-047/048，需求方：根仓库 REQ-064/065）：课程层探索 dry-run 端点 + shared-tables.md 写权限修订 + exploration_stage 写主体澄清 + api-design GET /courses 领域级探索字段补充；含待移交项（test_documentation.py 白名单补行，移交审阅）。

- [领域探索 prompt 优化基线](2026-08-prompt-explore-baseline.md)（2026-08-25，QED-043 长期任务）：v3 三步管线首轮全链路真实结果冻结（qed_llm_calls 073~079：高等数学 12 门 + 计算机科学与技术 16 门双批 ready）；后续模板/先验优化一律以该基线对照；与参考文本的差距观察仅作候选线索，真实对照口径待用户评估确定。
- [prompt 优化模块设计](2026-08-prompt-optimization.md)（2026-08-24，QED-043 长期任务）：领域知识探索 v3 三步管线（domain@v1 名称校验+确认流 / courses@v3 清华命名基准禁拆学期 / path@v3 tier 四档+先修无环）+ priors.py 领域先验注册；模板集中注册 `src/qed_tracker/prompt_lab/templates.py`（版本化，审核入口）；调用记录全进共享表 `qed_llm_calls`（REQ-060 根仓库已实现）；dry-run 评估端点已上线；后续 Phase B 正式流程。
- [完整数据库设计文档与 API 设计文档](2026-08-db-api-docs-completion.md)（2026-08-26，QED-044 长期任务）：architecture 两份固定文档升级为完整版（全表族 ER/字段字典/迁移史 + 全部路由五要素成文）；前置门禁 QED-010/011/014/026 完成前只维护不重构；承接 QED-039「API 文档内容完善」；QED-043 Phase 3/4 为首批子集。
- [主链路第一版](2026-08-main-line-curriculum.md)（2026-08-12，QED-026）：课程梳理 → 教材条目（五要素）→ LLM 预填评价 → 人工评审 → 下载 → 验收 → 移交根仓库；CLI 跑通 00/01/02 三门基础课验证。设计见[主链路设计](../design/main-line-curriculum.md)。
- [下载流程现状分析与优化方向](2026-08-download-flow.md)（2026-08-28，QED-026 收尾）：三条链路（catalog run / mainline CLI / books API）现状 + 状态机事实 + 下载器/清单层事实 + 成功率/准确率优化点分析 + 验收标准提案（含 REQ-020② 找得率口径）+ REQ-032 双轨登记 + 已知缺口（confirm 覆写/course 回写/tmp 契约）。

- 真实百炼与 arXiv 冒烟（QED-005）属于外部验收阻塞，直接保留在待办列表中。
