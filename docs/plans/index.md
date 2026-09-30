# 计划索引

状态：Current
最后更新：2026-09-30

本目录只保存尚未关闭的跨模块实施计划。任务状态以[待办列表](../trackers/todo.md)为准；计划完成后将关闭证据写入 completed，正文默认归档至 [历史基线](../history/index.md)（[ADR 0009](../history/adr/0009-closed-plan-archival.md)；Delete 仅限内容已完全并入固定文档且无独立查阅价值、或用户明确指示）。

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
> `2026-09-doc-cleanup-leftovers.md`（QED-056/057）按 [ADR 0009](../history/adr/0009-closed-plan-archival.md)
> 归档至[历史基线](../history/baselines/)（不再删除）。
> 2026-09-14 收尾轮（QED-066）：`2026-09-service-hardening.md`（REQ-017②③ + REQ-019）
> 按 [ADR 0009](../history/adr/0009-closed-plan-archival.md) 归档至[历史基线](../history/baselines/)。

## 活跃计划

- [来源探索与评估](2026-09-source-discovery.md)（2026-09-07，QED-054）：来源评估矩阵、渠道连通性/中文覆盖实测、待探索清单（持续工作）；2026-09-07 自 design/ 移入 plans（ADR 0008），设计契约部分已并入[下载管线设计](../design/download-pipeline.md)；2026-09-09 并入 REQ-020①② 承接口径。

- [本地 LLM 模型对接与 LangChain 编排](2026-09-14-local-llm-langchain.md)（2026-09-14 立项，2026-09-21 设计细化，QED-067，v1.0 主线）：经 8900 网关（`qed-engine` 模式）接入本地 qwen3.5 9B + LangChain(LCEL) 编排 prompt/pipeline，声明式 pipeline YAML/skill/MCP 只读工具白名单；示例链=领域探索三步（维基百科→MIT/Stanford/清华→综合报告）；子任务 067-1~5 承载于该计划，待用户评审。

- [DeepTutor 机制调研（审阅稿）](2026-09-21-deeptutor-survey.md)（2026-09-21，QED-067 附属调研）：I 检索与下载（arXiv 工具/查询派生 fallback/提示纪律、SSRF 逐跳复检、staging+manifest-last 原子入库）+ II 知识路线与编排（双模式校验/coverage 报告、draft→critique→revise+图校验兜底、字符串注册表、skill frontmatter、MCP 白名单与 deferred）；20 条借鉴点落点对照 + 9 条不照搬清单，待用户裁决（QED-067/068/069 归属）。

- [论文探索与下载链路整合](2026-09-14-paper-pipeline-alignment.md)（2026-09-14 立项，2026-09-21 详细化，QED-068）：参照 DeepTutor 调研稿的贴合本仓详细方案——068-1 arXiv 检索参数（相关度/过量抓取/年份窗口）、068-2 查询纪律与 fallback（plan@v2）、068-3 报告溯源与 coverage（schema v2）、068-5 8901 任务化、068-4 总体性优化收口（downloader 安全件/重复双报/文档收口）；本轮不实现，待评审排期。

- [下载链路评估](2026-09-14-download-channel-evaluation.md)（2026-09-14，QED-069）：`qt_sources` 渠道表现状说明 + 数据利用简要计划（本轮不实现）。

- [v1.0 后续任务链条梳理](2026-09-24-v1-task-chain.md)（2026-09-24 初稿 + 同日口径裁决，对照根仓库 ARCH-024 三线）：**v1.0 = 三主线全部交付 + ARCH-024 三线优化收口**；三主线交付口径与风险表、批次顺序（0 裁决轮 → A~D → E 收口轮 → 滚动项）、跨项目接口（网关 task/step REQ、8901 任务化衔接、根壳登记表回填、REQ-020② 回执）与集中待裁决项（调研稿 #4/#7、#11~#18）；只梳理登记，不实现。





- [百炼退役与本地链路独占](2026-09-28-bailian-retire-local-only.md)（2026-09-28 用户裁决立项，QED-072）：全部 LLM 调用收敛到 `qed-engine` → 8900 网关 → 本地 `qwen/qwen3.5-9b` 单通路并淘汰 dashscope 直连；含 W-0 取证结论（`max_tokens` ≤256 必吐空、1024 为硬下限、9000 预算下论文 `plan`/`assess` 契约一次通过零 repair、留痕 id=31~37 索引）、8196 旧预算表作废后的预算重设计口径、direct 分支移除顺序与命名同步面、待裁项 Q72-a~e；实现未开始，待用户评审。**2026-09-29 口径改判**：「通路唯一 / 完全屏蔽百炼」作废，改判为「默认本地 + API 备用」，逐条影响面见 [LLM 双链路口径与 prompt 资产台账](2026-09-29-llm-dual-link-prompt-ledger.md)。
- [探索链本地化](2026-09-28-exploration-pipeline-local.md)（2026-09-28 用户裁决立项，QED-073）：三条探索 prompt 链（`domain@v4`/`courses@v8`/`tutorials@v2`）改由本地 `qwen3.5-9b` 承载的设计草案：留痕负载表与九项勘察结论（本地零留痕、`name_check` 改判断链、`max_tokens≥16384` 硬下限与窗口冲突）、`domain@v5` system/user 全文草案与逐条改动理由、courses/tutorials 结构改造要点、链 A（单发 priors）与链 B1（LCEL + fixture 证据）A/B 判据与 S-1~S-4 试运行方案、待裁项 Q73-a~e；只落文档，代码未改。
- [LLM 双链路口径与 prompt 资产台账](2026-09-29-llm-dual-link-prompt-ledger.md)（2026-09-29 用户改判立项，QED-074）：把「LLM 从哪来」与「LLM 说什么」一次理清——① 改判 QED-072 的 D-1/D-3/D-7（由「百炼退役 + 本地独占」改为「v1.0 及之前默认本地 + API 备用链路可用」，DL-1~DL-6 六条守则）；② 全仓 prompt 资产台账（注册表在册 6 条 × 调用点 × 上游入口 × 可达链路、未入册 5 编号、修复重试骨架与注入面、死码与文档漂移四条）；③ 本地 vs API 同 payload 双跑的对比取证口径；④ 2.4 节登记「W-8 步骤 4 删除已落地又撤回」的工作树实况证据；待裁项 Q74-a~f。只落文档，代码未改。

- [缺陷修复台账](2026-09-14-bugfix-ledger.md)（2026-09-14，QED-070；2026-09-30 用户裁决移入 todo 普通任务轮滚动承载）：滚动缺陷登记与修复跟踪。


## 已完成计划

- [todo 任务管理治理轮](../history/baselines/2026-09-30-todo-governance-round.md)（2026-09-30 立项 + 同日关闭，QED-075）：todo 新增「普通任务轮」节 + v1.0 表逐行重审后冻结成功标准 + QED-070 移入普通任务轮滚动承载 + 三类产物落位规范（ADR 0011 + 既有标准扩写、不新增目录）+ logs/tmp 存量清扫；成功标准 1~7 全达成。**已按 ADR 0009 Retain 归档至 history/baselines/**。

- [存储链路治理实施计划（QED-071 拆岛 + staging 生命周期）](../history/baselines/2026-09-24-storage-json-island-retirement.md)（2026-09-24 立项 + 同日 A 轮收口，2026-09-26 B 轮执行完毕并关闭）：`qt_books` 内容身份三列手工迁移落 `qed_test`（D17 放宽为普通索引）+ 读路径全切 DB（M4 无岛回退）+ 资源岛停写退役、`Inventory` 类删除 + 全局反岛守护 + CLI 契约变更（D10/D11/D15/D16）；裁决 D1~D17、红线顺序与两轮举证全部留在正文。**已按 ADR 0009 Retain 归档至 history/baselines/**。

- [存储链路治理请求包（根仓库 ARCH-032 / ADR 0018）](../history/baselines/2026-09-24-storage-json-island-retirement-request.md)（2026-09-24 承接讨论稿，2026-09-26 随 QED-071 关闭）：R1/R2/R3 承接结论与勘误 C1~C4、遗漏 M3/M4 留档（M1/M2 原文从未落盘）。**已按 ADR 0009 Retain 归档至 history/baselines/**。

- [服务稳定性优化（REQ-017②③ + REQ-019）](../history/baselines/2026-09-service-hardening.md)（2026-09-14，QED-066）：重启后 orphaned running/queued → failed（dedup 解除）+ `verify_content` 下载内容校验（首页文本 vs 登记标题，软信号写入 qt_sources.note）+ 进度上报评估。**已按 ADR 0009 归档至 history/baselines/**。

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
