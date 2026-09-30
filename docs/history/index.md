# 历史索引

状态：Historical
最后更新：2026-09-30

本目录只保存无法由当前代码和文档替代的历史基线。内容中的路径、命令、库存和状态可能已经失效，不得作为当前操作或实现依据。

- [旧系统基线](baselines/pre-acquisition-cli.md)：聚焦 PDF 获取之前的职责，以及退出旧运行时的 Git 锚点。
- [Math-QE 人工盘点基线](baselines/math-qe-2026-05.md)：冻结目录形成前的课程范围、库存结论和已知缺口。
- [套标记字段 set_no 归档](baselines/catalog-set-field.md)：QED-024 早期 Draft（2026-08-12 用户裁决属 Plan 类别，方案确定后再进设计文档，本基线供未来重写参考）。
- [服务化与教材下载计划归档](baselines/2026-08-service-and-book-download.md)：QED-008~021 服务化轮计划（2026-08-12 归档，剩余 QED-010/011/014 独立跟踪；跨仓库联调审计证据）。
- [Exploration Stage Enhancement 归档](baselines/2026-08-31-req067-b10-b12-exploration-stage.md)：REQ-067-B10/B12 探索状态机增强（2026-09-01 归档，86 passed，Migration 0015，apply-results/re-explore 四端点）。
- [QED-039 文档体系范本对齐归档](baselines/2026-08-docs-restructure-alignment.md)：ADR 0010 三层结构对齐（2026-09-01 归档，15/15 任务完成，architecture/design/trackers 重构 + api.md 新建 + 契约测试同步）。
- [治理契约范本对齐归档](baselines/2026-08-governance-contract-alignment.md)：QED-022 承接根仓库 REQ-023（2026-09-01 归档，契约头六字段守护 + 守护面清单裁剪，确认状态暂定，已稳固实现）。
- [QED-Engine 探索对齐承接设计归档](baselines/2026-08-engine-exploration-alignment.md)：根仓库 REQ-064/065 配合清单（2026-09-01 归档，QED-047 课程 dry-run + QED-048 写权限修订，四项配合事项全部落地，实现轮 339 passed）。
- [qt_resources 退役归档](qed-030-retire-qt_resources/index.md)：QED-030 旧表 drop 证据快照（29 行全量备份、三表 4/12/16 现状、15 行清理备份）与一次性脚本归档说明。
- [人工评审优化归档](baselines/2026-08-review-round-dedup.md)：QED-020 evaluate 同源去重 + review_note（2026-09-07 归档；机制随 QED-030 qt_resources 退役，评审备注语义由专用表 notes 字段承接）。
- [生命周期脚本编码修复归档](baselines/2026-08-service-lifecycle-encoding-fix.md)：QED-035 `_pid_is_alive` GBK 解码修复（2026-09-07 归档；修复已合入 scripts/qed_tracker_service.py，test_service_scripts.py 持续回归守护）。
- [下载与清单设计归档](baselines/2026-07-acquisition-and-inventory.md)：来源协议/选书要求/通用下载器与资源登记原语（2026-09-07 归档，ADR 0008 整篇并入 design/download-pipeline.md）。
- [服务与外部接口设计归档](baselines/2026-08-tracker-service.md)：8901 端点/Axiom 消费面/配置/书单四职责（2026-09-07 归档，ADR 0008 拆散退役：Axiom 面→architecture/api.md、配置→design/service-management.md、书单→design/download-pipeline.md）。
- [服务生命周期脚本设计归档](baselines/2026-08-service-lifecycle.md)：启停脚本契约与运行事实（2026-09-07 归档，ADR 0008 并入 design/service-management.md）。
- [模型模式与密钥分置设计归档](baselines/2026-08-model-mode-config.md)：`.env` 密钥分置与模型模式（2026-09-07 归档，ADR 0008 并入 design/service-management.md）。
- [教程命名规范设计归档](baselines/2026-08-tutorial-naming.md)：教程 name 统一格式（2026-09-07 归档，ADR 0008 并入 design/knowledge-import.md「教程命名规范」节）。
- [探索契约对齐计划归档](baselines/2026-09-11-exploration-contract-alignment.md)：REQ-076/077/078（2026-09-11 归档，ADR 0009）：课程探索 5 态 + `PATCH /courses` 支持 `exploration_stage`/`explore_pending` + dataset JSON 例外口径确认，482 passed。
- [文档清理遗留问题清单归档](baselines/2026-09-doc-cleanup-leftovers.md)：QED-056/QED-057 遗留项处置（2026-09-11 归档，ADR 0009）：L-01/L-05/L-06/L-14 修复、L-07/L-08/L-10 维持现状关闭、L-09/L-11 PASS、L-13 保留于 QED-054。
- [服务稳定性优化计划归档](baselines/2026-09-service-hardening.md)：QED-066（REQ-017②③ + REQ-019）服务重启后 orphaned 任务恢复 + 下载后内容校验（2026-09-14 归档，ADR 0009）：`verify_content` 首页文本 vs 登记标题（软信号写入 qt_sources.note）+ 进度上报评估。
- [存储链路治理实施计划归档](baselines/2026-09-24-storage-json-island-retirement.md)：QED-071 A/B 两轮（2026-09-26 归档，ADR 0009 Retain）：`qt_books` 内容身份三列 + 资源 JSON 岛退役 + `Inventory` 删除 + staging 年龄清扫；裁决 D1~D17、红线顺序、门禁 533 passed 与 REQ-093 回执草稿留档。
- [存储链路治理请求包归档](baselines/2026-09-24-storage-json-island-retirement-request.md)：根仓库 ARCH-032 / ADR 0018 承接讨论稿（2026-09-26 随 QED-071 关闭归档）：勘误 C1~C4 与遗漏 M3/M4 评审原文（M1/M2 从未落盘）。
- [todo 任务管理治理轮归档](baselines/2026-09-30-todo-governance-round.md)：QED-075（2026-09-30 归档，ADR 0009 Retain）：todo 任务分层与过程叙述分离（普通任务轮节 + v1.0 六行冻结 + 冻结规则成文）+ 三类产物落位规范（ADR 0011 D-1~D-5）+ logs/tmp 存量清扫；全量 556 passed（唯一失败为台账在册并发会话项）。

## 已承接归档 ADR（adr/，2026-09-21，[ADR 0010](../adr/0010-absorbed-adr-archival.md)）

决策内容已由稳定文档完整承接的 ADR 保留于此（各文头部「承接落点」行为准，登记表见
[ADR 索引](../adr/index.md)）：

- [ADR 0002](adr/0002-version-cleanup-governance.md)：版本末期文档整理长效机制 → doc-governance「版本末期文档整理」节。
- [ADR 0003](adr/0003-pending-design-location.md)：待评审设计的目录流转 → doc-governance 分类表与生命周期。
- [ADR 0004](adr/0004-standards-governance-alignment.md)：规范体系对齐根仓库治理模式 → standards/ 五文（产物即落点）。
- [ADR 0005](adr/0005-shared-tables-doc-location.md)：共享表文档迁入 architecture/ → database-shared-tables.md + 跨项目协作规范。
- [ADR 0007](adr/0007-database-docs-split-by-table-family.md)：数据库设计文档按表族拆分 → 两数据库设计文档自承载。
- [ADR 0008](adr/0008-design-doc-scope-reshuffle.md)：设计文档域职责重划 → design/index.md 职责登记处。
- [ADR 0009](adr/0009-closed-plan-archival.md)：关闭计划默认归档 → doc-governance「归档与删除」两态判定。

逐日工作记录、旧 tracker 和被当前设计完整承接的文档不再复制归档，可从 Git 历史恢复。当前事实入口是[文档索引](../index.md)。
