# 计划索引

状态：Current
最后更新：2026-09-01

本目录只保存尚未关闭的跨模块实施计划。任务状态以[待办列表](../trackers/todo.md)为准；计划完成后将关闭证据写入 completed，并删除计划正文，详细差异由 Git 保留。过时计划归档至 [历史基线](../history/index.md)（如 2026-08-service-and-book-download 已归档）。

## 活跃计划

- [QED-Tracker 探索功能总览](2026-09-exploration-overview.md)（2026-09-01）：探索功能统一入口文档——管线架构（领域三步/课程单步）、端点清单（dry-run/apply-results/re-explore）、6 态状态机、跨项目对齐、基线与优化、手动探索。整合各子文档索引。

- [LLM 探索管线设计](2026-09-exploration-pipeline.md)（2026-09-01，QED-050-A/B）：领域三步管线（domain@v3 + courses@v5 + path@v5）+ 课程单步（tutorials@v1）+ dry-run 语义 + 6 态状态机 + explore_pending 载荷 + 写权限例外 + 先验注入 + 模板版本化。阶段二优化目标：模板审核 + 真实冒烟 + 错误处理完备。

- [手动知识导入设计](2026-09-knowledge-import.md)（2026-09-01，QED-050-C）：三种导入模式（领域 JSON + 课程 JSON + 书籍 PDF）+ manual@v1 schema 契约 + 校验逻辑 + 写入语义（导入即确认/D8/G2）+ 知识目录规范。阶段二优化目标：全链路测试 + schema 冻结。

- [下载流程与登记设计](2026-09-download-registration.md)（2026-09-01，QED-050-D）：三条触发链路 + 自动下载流程 + 手动导入流程 + 验收登记流程 + qt_books 状态机 + PDF 校验 + 渠道记录。阶段二优化目标：三门基础课闭环 + 渠道记录完备。

- [数据生命周期设计](2026-09-data-lifecycle.md)（2026-09-01，QED-050-E）：知识/探索/书籍三态生命周期 + 交叉点 + 清理策略 + 数据根规范 + 退役规则。阶段二优化目标：全状态路径测试 + 交叉点验证。

- [教材探索与下载双轨 + 知识体系梳理](2026-08-knowledge-dual-flow.md)（2026-08-29，QED-050）：手动+自动双轨共用 qt_knowledge/qt_books 状态机同一链路；手动领域导入（POST /domains/import）写共享表、课程导入复用 A2（draft）、手动下载（POST /books/{id}/import 外部路径→数据根内登记）；QED-043 语义升级（stage 四档【基础/主干/分支/前沿】/classic_tracks.kind/entry_requirements 一句话）；docs/knowledge/ 标准答案知识目录（math-advanced.json + math-advanced/{course_id}.json 含 target_path）。

- [QED-Engine 探索对齐承接设计](../history/baselines/2026-08-engine-exploration-alignment.md)（已归档，QED-047/048，需求方：根仓库 REQ-064/065）：课程层探索 dry-run 端点 + shared-tables.md 写权限修订 + exploration_stage 写主体澄清 + api-design GET /courses 领域级探索字段补充。

- [领域探索 prompt 优化基线](2026-08-prompt-explore-baseline.md)（2026-08-25，QED-043 长期任务）：v3 三步管线首轮全链路真实结果冻结（qed_llm_calls 073~079：高等数学 12 门 + 计算机科学与技术 16 门双批 ready）；后续模板/先验优化一律以该基线对照；与参考文本的差距观察仅作候选线索，真实对照口径待用户评估确定。
- [prompt 优化模块设计](2026-08-prompt-optimization.md)（2026-08-24，QED-043 长期任务）：领域知识探索 v3 三步管线（domain@v1 名称校验+确认流 / courses@v3 清华命名基准禁拆学期 / path@v3 tier 四档+先修无环）+ priors.py 领域先验注册；模板集中注册 `src/qed_tracker/prompt_lab/templates.py`（版本化，审核入口）；调用记录全进共享表 `qed_llm_calls`（REQ-060 根仓库已实现）；dry-run 评估端点已上线；后续 Phase B 正式流程。
- [完整数据库设计文档与 API 设计文档](2026-08-db-api-docs-completion.md)（2026-08-26，QED-044 长期任务）：architecture 两份固定文档升级为完整版（全表族 ER/字段字典/迁移史 + 全部路由五要素成文）；前置门禁 QED-010/011/014/026 完成前只维护不重构；承接 QED-039「API 文档内容完善」；QED-043 Phase 3/4 为首批子集。
- [主链路第一版](2026-08-main-line-curriculum.md)（2026-08-12，QED-026）：课程梳理 → 教材条目（五要素）→ LLM 预填评价 → 人工评审 → 下载 → 验收 → 移交根仓库；CLI 跑通 00/01/02 三门基础课验证。设计见[主链路设计](../design/main-line-curriculum.md)。
- [下载流程现状分析与优化方向](2026-08-download-flow.md)（2026-08-28，QED-026 收尾）：三条链路（catalog run / mainline CLI / books API）现状 + 状态机事实 + 下载器/清单层事实 + 成功率/准确率优化点分析 + 验收标准提案（含 REQ-020② 找得率口径）+ REQ-032 双轨登记 + 已知缺口（confirm 覆写/course 回写/tmp 契约）。

## 已完成计划

- [Exploration Stage Enhancement（REQ-067-B10 + B12）](../history/baselines/2026-08-31-req067-b10-b12-exploration-stage.md)（2026-08-31，REQ-067-B12 已实现）：启动清理脏 exploration_stage + 新增「待确认」状态 + apply-results/re-explore 端点（领域+课程）；数据库新增 explore_pending JSON 字段；状态机 5态→6态。86 passed（17 新测 + 69 回归）。**已归档至 history/baselines/**。

- [QED-039 文档体系范本对齐](../history/baselines/2026-08-docs-restructure-alignment.md)（2026-09-01，15/15 任务完成）：按 ADR 0010 对齐三层结构（architecture/design/trackers）；database-schema.md 移入 architecture/、project-status.md 移入 trackers/、api.md 新建、三态文档归档、7 份索引更新、契约测试同步。**已归档至 history/baselines/**。

- 真实百炼与 arXiv 冒烟（QED-005）属于外部验收阻塞，直接保留在待办列表中。
