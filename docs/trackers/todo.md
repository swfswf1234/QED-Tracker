# 待办列表

状态：Current
最后更新：2026-09-26

## 上一期计划（全链路跑通，已收口 2026-09-11）

本期计划全部完成并验收关闭：跑通全链路 / 完善文档评估逻辑链路 / 完善文档下载链路 /
QED-014 验证最终效果，以及阶段三重复下载链路验证（QED-011，2026-09-11 人工验收通过）；
跨项目请求 QED-063/064/065（REQ-076/077/078）已完成。见[完成台账](completed.md)。

---

## 本期计划（v1.0：本地模型 + 论文链路 + 链路评估）

### 核心目标

本地小模型（qwen3.5 9B）经 8900 网关接入 + LangChain 编排；论文探索与下载链路整合；
下载渠道评估落地；缺陷修复台账化。

> 后续任务链条梳理（对照根仓库 ARCH-024 三线，2026-09-24 初稿 + 同日口径裁决）：
> **v1.0 = 三主线全部交付 + ARCH-024 三线优化收口**；批次顺序（A~E）、跨项目接口与集中
> 待裁决项见 [v1.0 后续任务链条梳理](../plans/2026-09-24-v1-task-chain.md)。
> 2026-09-24 用户评审确认链条与批次口径；余留待裁：调研稿 #4/#7、#11~#18 归属（批次 0 收口前）。

### 任务清单

| ID | 类型 | 状态 | 事项 | 成功标准 | 关联计划 |
| --- | --- | --- | --- | --- | --- |
| QED-067 | Plan | 进行中 | 本地 LLM 模型对接 + LangChain 编排（v1.0 主线，子任务 QED-067-1~5 承载于同一计划）：经 8900 网关（`qed-engine` 模式）接入 QED-Engine 本地 qwen3.5 9B；prompt/pipeline 以 LangChain(LCEL) + 声明式配置（pipeline YAML/skill/MCP 只读工具白名单）编排；示例链=领域探索（维基百科定义检索 → MIT/Stanford/清华课程编排 → 综合报告） | 计划设计章节评审通过（2026-09-21 已细化）；v1.0 口径：067-1~5 全交付（外部 REQ 降级须用户裁决） | [2026-09-14-local-llm-langchain.md](../plans/2026-09-14-local-llm-langchain.md)、[DeepTutor 调研稿](../plans/2026-09-21-deeptutor-survey.md) |
| QED-068 | Plan | 进行中 | 论文探索与下载链路整合：2026-09-21 升级为贴合本仓的详细方案（参照 [DeepTutor 调研稿](../plans/2026-09-21-deeptutor-survey.md) I 部分）——arXiv 检索参数（相关度排序/过量抓取/年份窗口）、查询纪律与确定性 fallback（plan@v2）、报告溯源与 coverage（schema v2）、8901 任务化、总体性优化收口（downloader 安全件/重复双报/文档收口）；子任务 QED-068-1~5 承载于同一计划，本轮不实现 | 计划详细方案评审通过（2026-09-21 细化 + 裁决：fallback 接受、years_limit 默认 3）；v1.0 口径：068-1~5 全交付并收口（B-1~B-5 落设计文档） | [2026-09-14-paper-pipeline-alignment.md](../plans/2026-09-14-paper-pipeline-alignment.md) |
| QED-069 | Plan | 待开始 | 下载链路评估落地：`qt_sources` 渠道表现状说明 + 数据利用简要计划（本轮只说明+简要计划） | 现状文档 + 简要计划评审通过；v1.0 口径：细化轮 + 统计口径落地 + 基线采集回填矩阵 + REQ-020② 回执 | [2026-09-14-download-channel-evaluation.md](../plans/2026-09-14-download-channel-evaluation.md) |
| QED-070 | Defect | 进行中 | 缺陷修复台账：后续发现问题/bug 集中登记与修复跟踪 | 台账建立，条目持续闭环；v1.0 末期条目全部闭环或经用户裁决移交下期 | [2026-09-14-bugfix-ledger.md](../plans/2026-09-14-bugfix-ledger.md) |
| QED-071 | Plan | 进行中 | （请求：QED-Engine 根仓库 ARCH-032 / ADR 0018）存储链路治理请求包：R1 `inventory.py` meta JSON 岛代码退役——**时序约束「先迁列、后拆岛」**（`qt_books` 先经迁移补 sha256/size 内容身份列并双源回填对账，再删 `meta/**` 写入；完整性校验 `inventory.verify` 现依赖岛侧，勿颠倒）+ 四处文档 JSON 岛口径同步（system-overview/database-private-tables/main-line/download-pipeline，含论文记录 DB 承载定谳）、R2 下载 staging 残留清理生命周期（实测 08-28 50MB `.download` 残留）、R3 `qt_books` 下载错误列与起止时间戳 | **A 轮完成（2026-09-24，2026-09-26 复验仍成立）**：D3 留痕判废 + R2 年龄清扫 + 死码清理 + 局部反岛守护 + B 轮设计契约定稿 + 存量清理执行完毕（定向 71 passed、两组 `rg` 零命中、`src/qed_tracker/db/` 零改动，证据见计划「A 轮收口记录」与「进度与复核记录」）；**B 轮待排期**：Q1~Q5 已裁决（2026-09-26，D10~D14，B 轮无待裁项），开工硬门只剩真实库基线 `(created,rebuilt)==(0,0)` + 用户 D 类授权（备份/ALTER/改模型红线顺序）；A 轮尾巴未闭环 = 分组提交（已授权，须与 QED-067 拆分）+ REQ-093 部分完成回执待交根仓 + 勘误 M1/M2 补录；届时终态回执 REQ-093 并迁 completed.md | [2026-09-24-storage-json-island-retirement-request.md](../plans/2026-09-24-storage-json-island-retirement-request.md)、[执行计划](../plans/2026-09-24-storage-json-island-retirement.md)（2026-09-24 立项 + 同日 A 轮收口；用户裁决 D1~D9；2026-09-26 进度复核 + Q1~Q5 裁决 D10~D14 回写；REQ-093 部分完成回执草稿已备，交用户提交根仓） |

> 下一阶段主线（v1.0）已立项：本地 LLM 模型替换 + 论文探索，见上表 QED-067~070。

---

## 长期任务

以下任务为持续进行的长期工作，不绑定具体 plans/ 文档：

| ID | 类型 | 状态 | 事项 | 说明 |
| --- | --- | --- | --- | --- |
| QED-043 | Plan | 进行中 | prompt 优化模块（领域/课程知识探索工作台）：领域管线 v2/v4/v8 已验证（13 门）；课程 tutorials@v2 实现完成 | 长期任务，持续优化 |
| QED-054 | Plan | 进行中 | 来源探索与评估（持续工作）：来源评估矩阵维护、渠道连通性/中文覆盖/候选质量实测、待探索清单推进；libgen_li 保持发现专用（metadata_only，永不自动落盘），annas_archive/zlib 保持退役 | 评估结论持续更新进计划矩阵；新来源按来源协议接入经通用下载器；REQ-020①② 承接口径已并入计划（L-04 已通过，找得率基线具备采集条件，随本任务采集并回执根仓库） | [2026-09-source-discovery.md](../plans/2026-09-source-discovery.md) |

---

## 规则

- 任务按类型分类（Plan / Defect / Validation / Candidate），状态只允许 `待开始 / 进行中 / 已完成 / 阻塞`；阻塞必须声明证据、恢复条件和责任位置。
- 任务关闭时从本表移除并追加到[完成台账](completed.md)。
- **本期计划**任务按阶段分组，关联 plans/ 文档；**长期任务**只列清单，不绑定 plans/ 文档。
- **子任务拆分**：一个目标任务可按阶段/契约拆为子任务（如 `QED-050-A~E`、`QED-067-1~5`），
  子任务在本表随目标任务登记或注记；计划承载体默认是目标任务的一份主计划（子任务作工作项
  分节跟踪，不逐子任务建计划文件），仅当子任务需独立评审口径时才建专表计划并在本表关联
  （守护 `test_documentation.py` 强制 plans/ 每个文件被 todo 引用）。
- **小 bug 不入任务表**：修复级小 bug 登记进本期缺陷台账（当前为 QED-070
  [缺陷修复台账](../plans/2026-09-14-bugfix-ledger.md)）作子项闭环，不单独立项、不建独立
  计划；涉及契约/架构变更或需独立评审的缺陷才升格为本表任务。
