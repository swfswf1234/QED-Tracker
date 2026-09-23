# 下载链路评估（download-channel-evaluation）

状态：Draft
任务类型：Plan
最后更新：2026-09-24
需求方：用户（承接根仓库 REQ-020②「找得率榜单」）
目标项目：QED-Tracker
评审方：用户
关联设计：[下载管线设计](../design/download-pipeline.md)
关联计划：[来源探索与评估](2026-09-source-discovery.md)（QED-054）
关联 Tracker：QED-069
归档判定：待关闭时按 [ADR 0009](../history/adr/0009-closed-plan-archival.md) 做 Retain/Delete 两态判定

## 目标与成功标准

如实登记 `qt_sources` 渠道表现状，说明「表已建立但评估未实际应用」，并给出后续利用的简要计划。
**本轮只做现状说明与简要计划，不实现。**

成功标准：现状说明完整（表结构/写入点/读取点/缺口）、后续利用计划经用户评审通过。

**v1.0 交付口径裁决（2026-09-24，链条评审轮）**：本任务在 v1.0 期内须完成
「细化轮通过评审 → 找得率/成功率统计口径落地 → 基线采集首批结果回填来源评估矩阵 →
回执根仓库 REQ-020②」（v1.0 三主线中主线③的交付定义，落 [v1.0 任务链条梳理](2026-09-24-v1-task-chain.md)
批次 D）。细化前置 = 调研稿落点 #4/#7 裁决 + QED-068-4 收口完成（SSRF 逐跳/流式硬顶是
评估结论可信的前置）。

## 现状

- **表**：`qt_sources`（表 3，私有）——一行一次渠道尝试，字段 `channel` / `provider_id` /
  `page_url` / `download_url` / `file_keywords` / `ok` / `note`；DDL 注释即
  「用于归因成功来源与评估渠道有效性」（[数据库专用表设计](../architecture/database-private-tables.md)）。
- **写入点**：取书链路的自动尝试与人工导入（`channel=local_import`），见
  `src/qed_tracker/application/book_fetch.py`、`src/qed_tracker/api/main.py`。
- **读取点**：CLI `mainline channels`（按 qt_books 聚合本表）。
- **计划层**：[来源探索与评估](2026-09-source-discovery.md) 的「来源评估矩阵」与 REQ-020②
  找得率承接口径——数据源明确为 `qt_sources`，但基线「待采集」。
- **缺口**：数据**只写不评**——无找得率/渠道成功率统计产出，未回填矩阵、未回执根仓库 REQ-020②。

## 后续利用简要计划（待细化）

1. **找得率口径落地**：按 `channel` 统计「搜索返回有效候选占比」与「下载成功率」，
   对齐 [来源探索与评估](2026-09-source-discovery.md) 矩阵的「候选质量/下载成功率」列。
2. **渠道归因**：成功来源分布（manual / internet_archive / ...），服务课程下载流程优化。
3. **产出回填**：统计结果回填来源评估矩阵。
4. **回执根仓库**：REQ-020② 找得率基线采集后回执（口径已定义、基线已采集）。

## 非目标

- 不新增数据库表、不改 `qt_sources` 写权限与结构。
- 评估产出不写资源事实（判断与统计只作留痕/报表）。

## 关闭与归档

关闭时按 [ADR 0009](../history/adr/0009-closed-plan-archival.md) 做 Retain/Delete 两态判定。
